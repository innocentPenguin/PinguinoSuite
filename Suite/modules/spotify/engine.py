"""Engine: polls Spotify, keeps our queue in step, pushes the next track just in time, runs chat commands."""
import copy
import math
import threading
import time
import uuid

import console_log
import rules
import store
from queue_core import Queue, QueueError, new_item
from spotify_api import ApiError, NotConnected, RateLimited, norm_playback

VERIFY_EVERY_S = 20
IDLE_UNPUSH_S = 8
LOG_MAX = 100


class Engine:
    def __init__(self, api, auth, clock=time.time):
        self.api, self.auth, self.clock = api, auth, clock
        self.lock = threading.RLock()
        cfg = store.load("config.json", {})
        self.cfg = cfg
        st = store.load("state.json", {})
        self.queue = Queue(st.get("items", []), st.get("history", []))
        self.inbox = st.get("inbox", [])
        self.log = st.get("log", [])
        self.pb = None                 # normalized playback
        self.pb_at = 0.0
        self.now_item = None           # our queue item that is playing (None = a track we didn't queue)
        self.last_uri = None
        self.skip_votes = set()
        self.backoff_until = 0.0
        self.last_error = ""
        self.last_verify = 0.0
        self.idle_since = None
        self._ann = []                 # announcements for the Host to post: {seq, ts, text}
        self._ann_seq = 0
        self._search_cache = {}
        self.artist_genres = {}
        self.alert = None
        self.last_track = None         # last track seen playing (survives short "nothing playing" blips)
        self.session_counts = {}       # viewer -> accepted requests since requests were opened
        self._sched_last = None
        self._fallback_try = 0.0
        self._autostart_try = 0.0
        self.last_req = {}             # viewer -> time of last accepted request (cooldown)
        self.me = None
        self.devices = []
        self.version = 0               # bumped on any visible change (UI/overlay can poll cheaply)
        self._last_np = None
        self.site_block = {}           # blocklist pulled from the site (tracks/artists/users)

    # ---- settings
    @property
    def settings(self):
        s = rules.merged(self.cfg.get("settings"))
        sb = self.site_block
        s["blocklist"] = s["blocklist"] + list(sb.get("tracks", [])) + list(sb.get("artists", []))
        s["blocked_users"] = s["blocked_users"] + list(sb.get("users", []))
        return s

    def _own_settings(self):
        return rules.merged(self.cfg.get("settings"))

    def save_settings(self, patch):
        with self.lock:
            was_open = self._own_settings()["requests_open"]
            cur = self.cfg.get("settings", {})
            for k, v in (patch if isinstance(patch, dict) else {}).items():
                if k not in rules.DEFAULTS:
                    continue
                if isinstance(v, dict):
                    cur[k] = {**(cur.get(k) if isinstance(cur.get(k), dict) else {}), **v}    # msgs / cmd_aliases: single entries
                elif rules.merged({k: v})[k] == v:                                           # invalid values keep the old setting
                    cur[k] = v
            self.cfg["settings"] = rules.merged(cur)
            if self.cfg["settings"]["requests_open"] and not was_open:
                self.session_counts.clear()
            self._save_cfg()
            self._bump()
            return self._own_settings()

    def apply_preset(self, name):
        import config_schema as cs
        if name not in cs.PRESETS:
            return self.apply_user_preset(name)
        return self.save_settings(dict(cs.PRESETS[name][2]))

    def reset_settings(self, keys=None):
        """Back to defaults: given keys, or everything (requests stay closed)."""
        with self.lock:
            cur = self.cfg.get("settings", {})
            for k in (keys or list(cur.keys())):
                cur.pop(k, None)
            self.cfg["settings"] = rules.merged(cur) if keys else {}
            self._save_cfg()
            self._bump()
            return self._own_settings()

    def preview_msg(self, template):
        import config_schema as cs
        return (self.settings["reply_prefix"] + str(template).format_map(_Blank(cs.VARS)))[:400]

    def set_client_id(self, cid):
        with self.lock:
            self.cfg["client_id"] = (cid or "").strip()
            self._save_cfg()

    def _save_cfg(self):
        disk = store.load("config.json", {})
        disk.update(self.cfg)
        store.save("config.json", disk)

    def _write_queue_file(self):
        n = self.settings["queue_file_lines"]
        if n > 0:
            lines = [f"{i + 1}. {it['name']} - {', '.join(it['artists'])}" + (f" ({it['requester']})" if it["requester"] else "")
                     for i, it in enumerate(self.queue.items[:n])]
            store.write_text("queue.txt", "\n".join(lines))

    def persist(self):
        self._write_queue_file()
        with self.lock:
            store.save("state.json", {"items": self.queue.items, "history": self.queue.history[:200],
                                      "inbox": self.inbox[-100:], "log": self.log[-LOG_MAX:]})

    def _bump(self):
        self.version += 1

    def _event(self, kind, user, text, ok=True):
        self.log.append({"ts": self.clock(), "kind": kind, "user": user, "text": text, "ok": ok})
        del self.log[:-LOG_MAX]

    # ---- polling
    def tick(self):
        if not self.auth.connected():
            with self.lock:
                self.pb = None
            return
        if self.clock() < self.backoff_until:
            return
        try:
            pb = norm_playback(self.api.playback())
            self.last_error = ""
        except RateLimited as e:
            self.backoff_until = self.clock() + e.retry_after + 1
            console_log.warn("api", f"rate limited, backing off {e.retry_after}s", dedupe_s=30)
            return
        except ApiError as e:
            self.last_error = str(e)
            self.backoff_until = self.clock() + (10 if e.status in (0, 401) else 3)
            console_log.warn("api", f"playback poll failed: {e}", dedupe_s=60)
            return
        with self.lock:
            self._apply(pb)
        try:
            self._jit()
        except RateLimited as e:
            self.backoff_until = self.clock() + e.retry_after + 1
        except ApiError as e:
            console_log.warn("queue", f"could not push next track: {e}", dedupe_s=30)
            self.last_error = str(e)

    def _apply(self, pb):
        prev = self.pb
        self.pb, self.pb_at = pb, self.clock()
        if pb and pb["track"]:
            self.idle_since = None
        else:
            self.idle_since = self.idle_since or self.clock()
            items = self.queue.items
            if items and items[0]["pushed"] and self.clock() - self.idle_since > IDLE_UNPUSH_S:
                items[0]["pushed"] = False          # Spotify went idle: a pushed head can no longer play by itself
                console_log.warn("queue", "Spotify is idle; will not wait for the queued song (use Start queue)")
        cur = pb["track"] if pb and pb["track"] else None
        cur_uri = cur["uri"] if cur else None
        if cur_uri != self.last_uri:
            self._track_changed(self.last_track, cur)
            self.last_uri = cur_uri
        if cur:
            self.last_track = cur
        self._bump()

    def _track_changed(self, prev_track, cur):
        if prev_track and not (self.now_item and self.now_item["skip_on_play"]):
            self.queue.add_history({"uri": prev_track["uri"], "id": prev_track["id"], "name": prev_track["name"], "artists": prev_track["artists"],
                                    "album": prev_track["album"], "duration_ms": prev_track["duration_ms"], "explicit": prev_track["explicit"],
                                    "art": prev_track["art"], "requester": self.now_item["requester"] if self.now_item else "",
                                    "source": self.now_item["source"] if self.now_item else "spotify", "played_at": self.clock()})
        self.skip_votes.clear()
        self.now_item = self.queue.pop_playing(cur["uri"]) if cur else None
        if cur:
            console_log.info("player", f"now playing: {cur['name']} - {', '.join(cur['artists'])}" +
                             (f" (requested by {self.now_item['requester']})" if self.now_item and self.now_item["requester"] else ""))
        self._write_np(cur)
        if cur and self.settings["announce_track_on"]:
            who = (self.now_item or {}).get("requester")
            self._announce("announce_track", song=f"{cur['name']} - {', '.join(cur['artists'])}", title=cur["name"], artist=", ".join(cur["artists"]),
                           by=f" (requested by {who})" if who else "", requester=who or "", link=f"https://open.spotify.com/track/{cur['id']}")
        self.persist()
        if self.now_item and self.now_item["skip_on_play"]:
            threading.Thread(target=self._safe, args=(self.skip,), daemon=True).start()   # skip() sends our next song first
        elif cur and not self.now_item and self._should_autoskip(cur):
            console_log.warn("player", f"auto-skipping blocked song: {cur['name']}")
            self._event("autoskip", "auto", cur["name"], False)
            threading.Thread(target=self._safe, args=(self.skip,), daemon=True).start()

    def _should_autoskip(self, t):
        s = self.settings
        return bool(s["autoskip_blocked"] and (rules.blocked_reason(s, t) or (s["stream_safe"] and t.get("explicit"))))

    def _safe(self, fn, *a):
        try:
            fn(*a)
        except ApiError as e:
            console_log.warn("api", f"{getattr(fn, '__name__', 'call')} failed: {e}", dedupe_s=10)

    def _announce(self, key, **v):
        text = self.say(key, **v)
        if text:
            self._ann_seq += 1
            self._ann.append({"seq": self._ann_seq, "ts": self.clock(), "text": text})
            del self._ann[:-30]

    def announcements(self, since=0):
        """The Host polls this and posts the lines to chat (we have no chat connection of our own)."""
        with self.lock:
            return {"seq": self._ann_seq, "lines": [a for a in self._ann if a["seq"] > since and self.clock() - a["ts"] < 120]}

    def _write_np(self, cur):
        s = self.settings
        text = s["np_idle_text"]
        if cur:
            text = s["np_template"].format_map(_Safe(title=cur["name"], artist=", ".join(cur["artists"]), album=cur["album"],
                                                     requester=(self.now_item or {}).get("requester", "")))
        if text != self._last_np:
            self._last_np = text
            store.write_text("nowplaying.txt", text)
            if s["json_file"] if "json_file" in s else True:
                import json as _json
                store.write_text("nowplaying.json", _json.dumps({"title": cur["name"] if cur else "", "artist": ", ".join(cur["artists"]) if cur else "",
                                                                  "album": cur["album"] if cur else "", "art": cur["art"] if cur else "",
                                                                  "uri": cur["uri"] if cur else "", "requester": (self.now_item or {}).get("requester", ""),
                                                                  "ts": self.clock()}, ensure_ascii=False))

    def _jit(self):
        """Push the head of our queue to Spotify's real queue when the current track is about to end."""
        with self.lock:
            pb, items = self.pb, self.queue.items
            if not pb or not pb["track"] or not items:
                return
            head = items[0]
            now = self.clock()
            if head["pushed"]:
                # make sure Spotify still has it (the streamer might have cleared Spotify's queue)
                remaining = pb["track"]["duration_ms"] - pb["progress_ms"]
                every = VERIFY_EVERY_S if remaining > self.settings["jit_ms"] + 5000 else 3     # check closely near the end
                if head["uri"] != pb["track"]["uri"] and now - self.last_verify > every:
                    self.last_verify = now
                    do_verify = True
                else:
                    do_verify = False
                if not do_verify:
                    return
            else:
                remaining = pb["track"]["duration_ms"] - pb["progress_ms"]
                if not pb["is_playing"] or remaining > self.settings["jit_ms"]:
                    return
                do_verify = False
        if do_verify:
            self._verify_pushed(head)
        else:
            self._push(head)

    def _verify_pushed(self, head):
        q = self.api.queue() or {}
        lst = q.get("queue") or []
        if any(t and t.get("uri") == head["uri"] for t in lst) or len(lst) >= 20:
            return
        if (q.get("currently_playing") or {}).get("uri") == head["uri"]:
            return
        with self.lock:
            if self.queue.items and self.queue.items[0]["id"] == head["id"]:
                head["pushed"] = False
                console_log.warn("queue", f"'{head['name']}' vanished from Spotify's queue; will push again")
                self._bump()

    def _push(self, item):
        q = self.api.queue() or {}
        already = any(t and t.get("uri") == item["uri"] for t in (q.get("queue") or [])[:3])
        if not already:
            dev = ((self.pb or {}).get("device") or {}).get("id")
            self.api.add_to_queue(item["uri"], dev)
        with self.lock:
            if self.queue.items and self.queue.items[0]["id"] == item["id"]:
                item["pushed"] = True
                self.persist()
                self._bump()
        console_log.info("queue", f"sent to Spotify queue: {item['name']}")

    # ---- reading
    def public_state(self):
        with self.lock:
            now = self.clock()
            pb = copy.deepcopy(self.pb)
            if pb and pb["is_playing"]:
                pb["progress_ms"] += int((now - self.pb_at) * 1000)
            return {"connected": self.auth.connected(), "client_id_set": bool(self.auth.client_id), "playback": pb,
                    "now_item": copy.deepcopy(self.now_item), "queue": self.queue.view(), "etas": [self.eta_ms(i) for i in range(len(self.queue.items))], "inbox": [i for i in self.inbox if i["status"] == "pending"],
                    "log": self.log[-40:][::-1], "settings": self._own_settings(), "skip_votes": len(self.skip_votes),
                    "error": self.last_error or self.auth.last_error, "me": self.me, "version": self.version}

    def overlay(self):
        with self.lock:
            now = self.clock()
            pb = self.pb
            cur = pb["track"] if pb and pb["track"] else None
            st = self.settings
            n = st["overlay_show_next"]
            return {"playing": bool(pb and pb["is_playing"]), "has_track": bool(cur),
                    "title": cur["name"] if cur else "", "artist": ", ".join(cur["artists"]) if cur else "",
                    "album": cur["album"] if cur else "", "art": cur["art"] if cur else "",
                    "progress_ms": (pb["progress_ms"] + (int((now - self.pb_at) * 1000) if pb["is_playing"] else 0)) if cur else 0,
                    "duration_ms": cur["duration_ms"] if cur else 0,
                    "requester": (self.now_item or {}).get("requester", ""),
                    "next": [{"title": i["name"], "artist": ", ".join(i["artists"]), "requester": i["requester"]} for i in self.queue.items[:n]],
                    "version": self.version,
                    "alert": ({"id": self.alert["id"], "text": self.alert["text"]} if self.alert and st["ov_alerts"] and now - self.alert["ts"] < st["ov_alert_s"] else None),
                    "style": {k[3:]: st[k] for k in st if k.startswith("ov_")}}

    # ---- adding tracks
    def resolve(self, q, limit=5):
        key = (str(q).strip().lower(), limit)
        hit = self._search_cache.get(key)
        if hit and self.clock() - hit[0] < 120:
            return [dict(t) for t in hit[1]]
        out = self._resolve(q, limit)
        if out:
            self._search_cache[key] = (self.clock(), out)
            if len(self._search_cache) > 200:
                self._search_cache.pop(next(iter(self._search_cache)))
        return [dict(t) for t in out]

    def _resolve(self, q, limit=5):
        tid = rules.track_id_from(q)
        if tid:
            t = self.api.track(tid)
            return [t] if t else []
        return [t for t in self.api.search(q, limit) if t]

    def add_track(self, track, where="end", requester="", source="streamer", tier=0):
        with self.lock:
            item = new_item(track, requester, source, tier)
            self.queue.add(item, where, fair=self.settings["fair_queue"])
            self._event("add", requester or "you", f"{track['name']} - {', '.join(track['artists'])}")
            self.persist()
            self._bump()
            return item

    # ---- replies (personal wording from settings)
    def say(self, key, **v):
        """Render message template `key`; empty template = silent. Unknown {placeholders} become empty."""
        s = self.settings
        tpl = s["msgs"].get(key, "")
        if not tpl:
            return ""
        text = tpl.format_map(_Blank(v))
        return (s["reply_prefix"] + text)[:400]

    def _r(self, ok, code, key=None, **v):
        return {"ok": ok, "code": code, "reply": self.say(key or code, **v)}

    # ---- viewer requests
    def request(self, user, query, roles, redeem=False, track=None):
        """Returns {ok, reply, code}. Shared by chat, the site and the Host."""
        s = self.settings
        roles = set(roles)
        if not query and not track:
            return self._r(False, "usage", user=user)
        if not self.auth.connected():
            return self._r(False, "offline", user=user)
        if query and not track and not rules.is_staff(roles):
            has_link = bool(rules.track_id_from(query))
            if has_link and not s["allow_links"]:
                return self._r(False, "no_links", user=user)
            if not has_link and not s["allow_search"]:
                return self._r(False, "no_search", user=user)
        try:
            cands = [track] if track else self.resolve(query)
        except ApiError as e:
            console_log.warn("request", f"lookup failed for {user}: {e}", dedupe_s=30)
            return self._r(False, "lookup", user=user)
        if not cands:
            self._event("reject", user, f"no result: {query}", False)
            return self._r(False, "none", "none", user=user)
        now_uri = self.pb["track"]["uri"] if self.pb and self.pb["track"] else None
        first_fail = None
        with self.lock:
            for t in cands:
                t = self._genre_tag(t, s, roles)
                ok, code, ctx = rules.evaluate(s, t, user, roles, self.queue, now_uri, self.clock(), self.last_req.get(user.lower()), self.session_counts.get(user.lower(), 0))
                if ok:
                    return self._accept(t, user, roles, redeem)
                first_fail = first_fail or (code, ctx, t)
                if code in ("user_blocked", "closed", "mod_only", "sub_only", "full", "limit", "cooldown"):
                    break           # not a track problem: trying other search results won't help
            code, ctx, t = first_fail
            self._event("reject", user, f"{t['name']}: {code}", False)
            self._bump()
            return self._r(False, code, **ctx)

    def _genre_tag(self, t, s, roles):
        """Adds t['_genre'] when one of the artist's Spotify genres is on the blocked list (lookups cached; failures allow)."""
        bad = [g.strip().lower() for g in s["block_genres"] if g.strip()]
        if not bad or "broadcaster" in roles or not t.get("artist_ids"):
            return t
        need = [a for a in t["artist_ids"] if a not in self.artist_genres]
        if need:
            try:
                got = self.api.artists(need)
                for a in need:
                    self.artist_genres[a] = got.get(a, [])
            except (ApiError, AttributeError):
                return t
        for a in t["artist_ids"]:
            for g in self.artist_genres.get(a, []):
                if any(b in g for b in bad):
                    return {**t, "_genre": g}
        return t

    def _accept(self, t, user, roles, redeem):
        s = self.settings
        tier = rules.tier_for(s, roles, redeem, user)
        self.session_counts[user.lower()] = self.session_counts.get(user.lower(), 0) + 1
        label = f"{t['name']} - {', '.join(t['artists'])}"
        self.last_req[user.lower()] = self.clock()
        base = {"user": user, "song": label, "title": t["name"], "artist": t["artists"][0] if t["artists"] else ""}
        if rules.needs_approval(s, roles, user):
            self.inbox.append({"id": uuid.uuid4().hex[:8], "track": t, "user": user, "roles": sorted(roles), "tier": tier,
                               "ts": self.clock(), "status": "pending"})
            self._event("pending", user, label)
            self.persist()
            self._bump()
            return self._r(True, "pending", **base)
        item = self.add_track(t, "end", user, "viewer", tier)
        idx = self.queue.index(item["id"])
        mins = round(self.eta_ms(idx) / 60000)
        self.alert = {"id": item["id"], "text": f"{user} requested {t['name']}", "ts": self.clock()}
        if s["announce_request_on"]:
            self._announce("announce_request", user=user, song=label, title=t["name"], artist=base["artist"])
        r = self._r(True, "added", **base, pos=idx + 1, eta=f", plays in ~{mins} min" if mins >= 2 else "")
        r["item"] = item["id"]
        return r

    def eta_ms(self, idx):
        """Milliseconds until queue item `idx` starts (rest of the current track + everything before it)."""
        left = 0
        if self.pb and self.pb["track"]:
            left = max(0, self.pb["track"]["duration_ms"] - self.pb["progress_ms"])
        return left + sum(i["duration_ms"] for i in self.queue.items[:idx])

    def inbox_decide(self, rid, approve):
        with self.lock:
            r = next((x for x in self.inbox if x["id"] == rid and x["status"] == "pending"), None)
            if not r:
                raise QueueError("request not found")
            r["status"] = "approved" if approve else "denied"
            if approve:
                self.add_track(r["track"], "end", r["user"], "viewer", r["tier"])
            else:
                self._event("deny", r["user"], r["track"]["name"], False)
            self.persist()
            self._bump()

    # ---- chat
    def chat(self, user, text, roles=(), redeem=False):
        """Entry for the Host / Streamer.bot. -> {handled, ok, reply, code}. `reply` is empty when chat_replies is off."""
        cmd, arg = rules.parse(text, self.settings)
        if not cmd:
            return {"handled": False, "ok": False, "reply": "", "code": "not_a_command"}
        roles = set(r.lower() for r in roles)
        staff = rules.is_staff(roles)
        out = self._chat_cmd(cmd, arg, user, roles, staff, redeem)
        out["handled"] = True
        if not self.settings["chat_replies"]:
            out["reply"] = ""
        return out

    def _chat_cmd(self, cmd, arg, user, roles, staff, redeem):
        s = self.settings
        if cmd == "sr":
            low = arg.lower()
            if staff and low in ("open", "close", "on", "off"):
                opened = low in ("open", "on")
                self.save_settings({"requests_open": opened})
                return self._r(True, "toggle", "toggle_open" if opened else "toggle_closed", user=user)
            if staff and low in ("safe on", "safe off", "safe"):
                on = low != "safe off"
                self.save_settings({"stream_safe": on})
                return self._r(True, "toggle", "safe_on" if on else "safe_off", user=user)
            if staff and low == "clear":
                return self._chat_cmd("clear", "", user, roles, staff, False)
            return self.request(user, arg, roles, redeem)
        if cmd == "song":
            return self.song_reply(user)
        if cmd == "queue":
            return self.queue_reply(user)
        if cmd == "skip":
            return self.vote_skip(user, staff)
        if cmd == "last":
            h = self.queue.history[0] if self.queue.history else None
            if not h:
                return self._r(True, "last", "last_none", user=user)
            return self._r(True, "last", "last", user=user, last=f"{h['name']} - {', '.join(h['artists'])}")
        if cmd == "mine":
            mine = [it for it in self.queue.items if it["source"] == "viewer" and it["requester"].lower() == user.lower()]
            if not mine:
                return self._r(True, "mine", "mine_none", user=user)
            return self._r(True, "mine", user=user, mine=", ".join(f"{it['name']} (#{self.queue.index(it['id']) + 1})" for it in mine))
        if cmd == "volume" and staff:
            cur = (self.pb or {}).get("device") or {}
            if arg.strip().lstrip("+-").isdigit():
                v = int(arg.strip())
                v = self.clamp_volume(v if not arg.strip()[0] in "+-" else (cur.get("volume") or 0) + v)
                self.api.volume(v)
                return self._r(True, "volume", "volume_set", user=user, vol=v)
            return self._r(True, "volume", user=user, vol=cur.get("volume") if cur.get("volume") is not None else "?")
        if cmd == "playnext" and staff:
            if not arg:
                return self._r(False, "usage", user=user)
            cands = self.resolve(arg, 1)
            if not cands:
                return self._r(False, "none", user=user)
            t = cands[0]
            item = self.add_track(t, "next", user, "streamer")
            return self._r(True, "playnext", user=user, title=t["name"], song=f"{t['name']} - {', '.join(t['artists'])}")
        if cmd == "help":
            p = s["prefix"]
            shown = [p + s["cmd_aliases"][c][0] for c in ("sr", "song", "queue", "skip", "oops", "mine", "last") if s["cmd_aliases"].get(c)]
            return self._r(True, "help", user=user, cmds=" ".join(shown))
        if cmd == "oops":
            it = self.queue.remove_last_of(user)
            if not it:
                return self._r(False, "none", "oops_none", user=user)
            self._event("remove", user, it["name"])
            self.persist()
            self._bump()
            return self._r(True, "removed", user=user, title=it["name"], song=it["name"])
        if cmd == "clear" and staff:
            self.queue.clear(only_viewers=True)
            self.persist()
            self._bump()
            return self._r(True, "clear", "cleared", user=user)
        if cmd == "blocksong" and staff:
            t = self.pb["track"] if self.pb and self.pb["track"] else None
            if not t:
                return self._r(False, "none", "skip_none", user=user)
            self.save_settings({"blocklist": self._own_settings()["blocklist"] + [t["uri"]]})
            self.skip(force=True)
            return self._r(True, "blocked", "blocked_song", user=user, title=t["name"], artist=t["artists"][0] if t["artists"] else "")
        return {"ok": False, "code": "denied", "reply": ""}

    def song_reply(self, user=""):
        t = self.pb["track"] if self.pb and self.pb["track"] else None
        if not t:
            return self._r(True, "song", "song_idle", user=user)
        who = (self.now_item or {}).get("requester")
        return self._r(True, "song", user=user, song=f"{t['name']} - {', '.join(t['artists'])}", title=t["name"], artist=", ".join(t["artists"]),
                       by=f" (requested by {who})" if who else "", requester=who or "", link=f"https://open.spotify.com/track/{t['id']}")

    def queue_reply(self, user=""):
        items = self.queue.items
        if not items:
            return self._r(True, "queue", "queue_empty", user=user)
        nxt = " | ".join(f"{i + 1}. {it['name']} - {it['artists'][0] if it['artists'] else ''}" for i, it in enumerate(items[:3]))
        return self._r(True, "queue", user=user, count=len(items), next=nxt)

    def song_line(self):
        return self.song_reply()["reply"]

    def queue_line(self):
        return self.queue_reply()["reply"]

    def vote_skip(self, user, staff):
        s = self.settings
        if not (self.pb and self.pb["track"]):
            return self._r(False, "none", "skip_none", user=user)
        if staff and s["skip_mod_instant"]:
            self.skip(force=True)
            return self._r(True, "skipped", user=user)
        self.skip_votes.add(user.lower())
        need = max(1, int(s["skip_votes"]))
        n = len(self.skip_votes)
        if n >= need:
            self.skip(force=True)
            return self._r(True, "skipped", "vote_skipped", user=user, votes=n, need=need)
        self._bump()
        return self._r(True, "vote", user=user, votes=n, need=need)

    # ---- playback control (UI + chat)
    def skip(self, force=False):
        with self.lock:
            head = self.queue.items[0] if self.queue.items else None
        if head and not head["pushed"]:
            self._push(head)          # JIT means Spotify's queue may be empty: send ours first so "next" plays it
        self.api.next()
        self.backoff_until = 0
        self._schedule_refresh()

    def _schedule_refresh(self):
        threading.Timer(0.6, self.tick).start()

    def control(self, action, value=None):
        a = self.api
        if action == "pause":
            a.pause()
        elif action in ("play", "resume"):
            if self.pb is None or (self.pb and not self.pb["track"]):
                self.start_queue()
            else:
                a.resume()
        elif action == "next":
            self.skip()
            return
        elif action == "previous":
            a.previous()
        elif action == "seek":
            a.seek(int(value))
        elif action == "volume":
            a.volume(self.clamp_volume(value))
        elif action == "transfer":
            a.transfer(str(value), play=True)
        else:
            raise QueueError("unknown action")
        self._schedule_refresh()

    def clamp_volume(self, v):
        s = self.settings
        return max(s["volume_min"], min(s["volume_max"], int(v)))

    def start_queue(self):
        """Nothing is playing: start our head track directly."""
        with self.lock:
            head = self.queue.items[0] if self.queue.items else None
        if not head:
            raise QueueError("queue is empty")
        self.api.play_uris([head["uri"]])
        with self.lock:
            head["pushed"] = True
        self._schedule_refresh()

    def play_now(self, iid):
        with self.lock:
            self.queue.play_next(iid)
        self.skip()

    def upvote(self, rid, who):
        with self.lock:
            it = next((i for i in self.queue.items if i["id"] == rid), None)
            if not it:
                return "unknown_request"
            voters = it.setdefault("voters", [])
            if who.lower() in voters:
                return "already_voted"
            voters.append(who.lower())
            self._bump()
            return None

    def site_snapshot(self):
        """State mirror for innocentpenguin.com (docs/SPOTIFY_CONTRACT.md v1)."""
        with self.lock:
            now = self.clock()
            s = self._own_settings()
            pb = self.pb
            t = pb["track"] if pb and pb["track"] else None
            ms = int(now * 1000)
            np = None
            if t:
                np = {"id": t["id"], "title": t["name"], "artists": t["artists"], "album": t["album"], "art": t["art"],
                      "durationMs": t["duration_ms"], "progressMs": pb["progress_ms"], "isPlaying": pb["is_playing"],
                      "requestedBy": (self.now_item or {}).get("requester") or None, "progressAt": int(self.pb_at * 1000)}
            return {"v": 1, "updatedAt": ms,
                    "status": {"requestsOpen": bool(s["requests_open"]), "paused": bool(pb and not pb["is_playing"]), "maxQueue": s["queue_max"]},
                    "nowPlaying": np,
                    "queue": [{"rid": i["id"], "id": i["track_id"], "title": i["name"], "artists": i["artists"], "art": i["art"],
                               "durationMs": i["duration_ms"], "requestedBy": i["requester"] or "", "votes": len(i.get("voters", []))}
                              for i in self.queue.items[:100]],
                    "history": [{"id": h["uri"].split(":")[-1], "title": h["name"], "artists": h["artists"], "art": h.get("art", ""),
                                 "playedAt": int(h["played_at"] * 1000), "requestedBy": h.get("requester") or None}
                                for h in self.queue.history[:50]]}

    def now_info(self):
        t = self.pb["track"] if self.pb and self.pb["track"] else None
        if not t:
            return {"title": "", "artist": "", "url": "", "requestedBy": ""}
        return {"title": t["name"], "artist": ", ".join(t["artists"]), "url": f"https://open.spotify.com/track/{t['id']}",
                "requestedBy": (self.now_item or {}).get("requester", "")}

    def add_context(self, link, shuffle=False, limit=50, where="end"):
        import re as _re
        m = _re.search(r"(?:spotify:|open\.spotify\.com/(?:intl-[a-z]+/)?)(playlist|album)[:/]([A-Za-z0-9]{22})", link or "")
        if not m:
            raise QueueError("paste a Spotify playlist or album link")
        tracks = self.api.context_tracks(m.group(1), m.group(2), max(1, min(int(limit), 200)))
        if not tracks:
            raise QueueError("no playable tracks found (private playlist? reconnect Spotify to grant playlist access)")
        if shuffle:
            import random
            random.shuffle(tracks)
        with self.lock:
            have = {i["uri"] for i in self.queue.items}
            n = 0
            for t in tracks:
                if t["uri"] in have:
                    continue
                self.add_track(t, "end", "", "streamer")
                have.add(t["uri"])
                n += 1
            return n

    # ---- user presets (snapshots of the current settings)
    def save_user_preset(self, name):
        name = str(name).strip()[:40]
        if not name:
            raise QueueError("name required")
        with self.lock:
            up = self.cfg.setdefault("user_presets", {})
            if len(up) >= 30 and name not in up:
                raise QueueError("too many presets (30)")
            snap = {k: v for k, v in self._own_settings().items() if k != "requests_open"}
            up[name] = snap
            self._save_cfg()
            return sorted(up)

    def apply_user_preset(self, name):
        with self.lock:
            snap = (self.cfg.get("user_presets") or {}).get(name)
            if snap is None:
                raise QueueError("unknown preset")
            return self.save_settings(dict(snap))

    def delete_user_preset(self, name):
        with self.lock:
            up = self.cfg.get("user_presets") or {}
            up.pop(name, None)
            disk = store.load("config.json", {})
            disk["user_presets"] = up
            store.save("config.json", disk)
            self.cfg["user_presets"] = up
            return sorted(up)

    def shuffle_queue(self):
        with self.lock:
            n = self.queue.shuffle()
            self.persist()
            self._bump()
            return n

    def remove_user(self, requester):
        with self.lock:
            n = self.queue.remove_by(requester)
            self.persist()
            self._bump()
            return n

    def stats(self):
        from collections import Counter
        with self.lock:
            hist = list(self.queue.history)
            who = Counter(h["requester"] for h in hist if h.get("requester"))
            songs = Counter((h["name"], ", ".join(h.get("artists", []))) for h in hist)
            queued = Counter(i["requester"] for i in self.queue.items if i["requester"])
            return {"played": len(hist), "requested_played": sum(who.values()),
                    "top_requesters": who.most_common(8), "top_songs": [[f"{n} - {a}", c] for (n, a), c in songs.most_common(8) if c > 1],
                    "queued_by": queued.most_common(8), "session": sorted(self.session_counts.items(), key=lambda x: -x[1])[:8]}

    # ---- schedule + idle behaviour (called from the engine loop)
    def automation_tick(self):
        s = self._own_settings()
        now = self.clock()
        if s["schedule_enabled"]:
            self._schedule(s, now)
        pb = self.pb
        idle = (self.idle_since is not None) and (now - self.idle_since)
        if self.auth.connected() and pb is None and idle:
            if self.queue.items and s["autostart_queue"] and idle > 5 and now - self._autostart_try > 30:
                self._autostart_try = now
                try:
                    self.start_queue()
                    console_log.info("player", "idle with songs queued: started the queue")
                except ApiError as e:
                    console_log.warn("player", f"autostart failed: {e}", dedupe_s=60)
            elif (not self.queue.items and s["fallback_playlist"] and idle > s["fallback_after_s"] and now - self._fallback_try > 60
                  and (s["requests_open"] or not s["fallback_only_open"])):
                self._fallback_try = now
                uri = _context_uri(s["fallback_playlist"])
                if uri:
                    try:
                        if s["fallback_shuffle"]:
                            self.api.shuffle(True)
                        self.api.play_context(uri)
                        console_log.info("player", "idle: started the background playlist")
                    except ApiError as e:
                        console_log.warn("player", f"background playlist failed: {e}", dedupe_s=60)

    def _schedule(self, s, now):
        lt = time.localtime(now)
        day = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[lt.tm_wday]
        days = {d.strip().lower()[:3] for d in s["schedule_days"].split(",")}
        o, c = _hhmm(s["schedule_open"]), _hhmm(s["schedule_close"])
        if o is None or c is None:
            return
        m = lt.tm_hour * 60 + lt.tm_min
        inside = (o <= m < c) if o < c else (m >= o or m < c)
        if inside and o >= c and m < c:                      # after midnight: the window belongs to yesterday's day
            day = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")[lt.tm_wday]
        want = inside and day in days
        if self._sched_last is not None and want != self._sched_last:
            self.save_settings({"requests_open": want})
            console_log.info("schedule", "song requests " + ("opened" if want else "closed") + " by schedule")
        self._sched_last = want

    # ---- readiness
    def prestream(self):
        items = []
        if not self.auth.client_id:
            return [{"id": "token", "label": "Spotify connected", "status": "warn", "detail": "not set up (open the Spotify page)"}]
        if not self.auth.connected():
            return [{"id": "token", "label": "Spotify connected", "status": "fail", "detail": "not signed in - open the Spotify page and press Connect"}]
        try:
            self.auth.access_token()
            items.append({"id": "token", "label": "Spotify token valid", "status": "pass"})
        except ApiError as e:
            return [{"id": "token", "label": "Spotify token valid", "status": "fail", "detail": str(e.message or e)[:120]}]
        try:
            me = self.api.me() or {}
            self.me = {"name": me.get("display_name") or me.get("id"), "product": me.get("product")}
            prem = me.get("product") == "premium"
            items.append({"id": "premium", "label": "Spotify Premium (needed for playback control)", "status": "pass" if prem else "fail",
                          "detail": "" if prem else f"plan is '{me.get('product', 'unknown')}'"})
            devs = self.api.devices()
            self.devices = devs
            act = [d for d in devs if d.get("is_active")]
            items.append({"id": "device", "label": "Active Spotify device", "status": "pass" if act else "warn",
                          "detail": act[0]["name"] if act else ("open Spotify on the streaming PC and press play once" if not devs else "devices idle: " + ", ".join(d["name"] for d in devs)[:100])})
        except ApiError as e:
            items.append({"id": "api", "label": "Spotify API reachable", "status": "warn", "detail": str(e)[:120]})
        opened = self._own_settings()["requests_open"]
        items.append({"id": "requests", "label": "Song requests", "status": "pass",
                      "detail": "open to viewers" if opened else "closed (default): a mod opens them with !sr open"})
        return items


def _hhmm(t):
    try:
        h, m = str(t).strip().split(":")
        h, m = int(h), int(m)
        return h * 60 + m if 0 <= h < 24 and 0 <= m < 60 else None
    except ValueError:
        return None


def _context_uri(v):
    import re as _re
    v = str(v).strip()
    m = _re.search(r"spotify:(playlist|album|artist):([A-Za-z0-9]{22})", v) or _re.search(r"open\.spotify\.com/(?:intl-[a-z]+/)?(playlist|album|artist)/([A-Za-z0-9]{22})", v)
    return f"spotify:{m.group(1)}:{m.group(2)}" if m else None


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


class _Blank(dict):
    def __missing__(self, k):
        return ""
