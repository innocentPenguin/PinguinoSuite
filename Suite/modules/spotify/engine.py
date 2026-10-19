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
            cur = self.cfg.get("settings", {})
            cur.update(patch if isinstance(patch, dict) else {})
            self.cfg["settings"] = rules.merged(cur)
            self._save_cfg()
            self._bump()
            return self._own_settings()

    def set_client_id(self, cid):
        with self.lock:
            self.cfg["client_id"] = (cid or "").strip()
            self._save_cfg()

    def _save_cfg(self):
        disk = store.load("config.json", {})
        disk.update(self.cfg)
        store.save("config.json", disk)

    def persist(self):
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
        cur = pb["track"] if pb and pb["track"] else None
        cur_uri = cur["uri"] if cur else None
        if cur_uri != self.last_uri:
            self._track_changed(prev["track"] if prev and prev["track"] else None, cur)
            self.last_uri = cur_uri
        self._bump()

    def _track_changed(self, prev_track, cur):
        if prev_track:
            self.queue.add_history({"uri": prev_track["uri"], "name": prev_track["name"], "artists": prev_track["artists"],
                                    "art": prev_track["art"], "requester": self.now_item["requester"] if self.now_item else "",
                                    "source": self.now_item["source"] if self.now_item else "spotify", "played_at": self.clock()})
        self.skip_votes.clear()
        self.now_item = self.queue.pop_playing(cur["uri"]) if cur else None
        if cur:
            console_log.info("player", f"now playing: {cur['name']} - {', '.join(cur['artists'])}" +
                             (f" (requested by {self.now_item['requester']})" if self.now_item and self.now_item["requester"] else ""))
        self._write_np(cur)
        self.persist()
        if self.now_item and self.now_item["skip_on_play"]:
            threading.Thread(target=self._safe, args=(self.api.next,), daemon=True).start()

    def _safe(self, fn, *a):
        try:
            fn(*a)
        except ApiError as e:
            console_log.warn("api", f"{getattr(fn, '__name__', 'call')} failed: {e}", dedupe_s=10)

    def _write_np(self, cur):
        s = self.settings
        text = s["np_idle_text"]
        if cur:
            text = s["np_template"].format_map(_Safe(title=cur["name"], artist=", ".join(cur["artists"]), album=cur["album"],
                                                     requester=(self.now_item or {}).get("requester", "")))
        if text != self._last_np:
            self._last_np = text
            store.write_text("nowplaying.txt", text)

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
                if head["uri"] != pb["track"]["uri"] and now - self.last_verify > VERIFY_EVERY_S:
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
                    "now_item": copy.deepcopy(self.now_item), "queue": self.queue.view(), "inbox": [i for i in self.inbox if i["status"] == "pending"],
                    "log": self.log[-40:][::-1], "settings": self._own_settings(), "skip_votes": len(self.skip_votes),
                    "error": self.last_error or self.auth.last_error, "me": self.me, "version": self.version}

    def overlay(self):
        with self.lock:
            now = self.clock()
            pb = self.pb
            cur = pb["track"] if pb and pb["track"] else None
            n = self.settings["overlay_show_next"]
            return {"playing": bool(pb and pb["is_playing"]), "has_track": bool(cur),
                    "title": cur["name"] if cur else "", "artist": ", ".join(cur["artists"]) if cur else "",
                    "album": cur["album"] if cur else "", "art": cur["art"] if cur else "",
                    "progress_ms": (pb["progress_ms"] + (int((now - self.pb_at) * 1000) if pb["is_playing"] else 0)) if cur else 0,
                    "duration_ms": cur["duration_ms"] if cur else 0,
                    "requester": (self.now_item or {}).get("requester", ""),
                    "next": [{"title": i["name"], "artist": ", ".join(i["artists"]), "requester": i["requester"]} for i in self.queue.items[:n]],
                    "version": self.version}

    # ---- adding tracks
    def resolve(self, q, limit=5):
        tid = rules.track_id_from(q)
        if tid:
            t = self.api.track(tid)
            return [t] if t else []
        return [t for t in self.api.search(q, limit) if t]

    def add_track(self, track, where="end", requester="", source="streamer", tier=0):
        with self.lock:
            item = new_item(track, requester, source, tier)
            self.queue.add(item, where)
            self._event("add", requester or "you", f"{track['name']} - {', '.join(track['artists'])}")
            self.persist()
            self._bump()
            return item

    # ---- viewer requests
    def request(self, user, query, roles, redeem=False, track=None):
        """Returns {ok, reply, code}. Shared by chat and the UI's manual 'add as viewer'."""
        s = self.settings
        roles = set(roles)
        if not query and not track:
            return {"ok": False, "code": "usage", "reply": f"@{user} usage: !sr <song name or Spotify link>"}
        if not self.auth.connected():
            return {"ok": False, "code": "offline", "reply": "Song requests aren't available right now."}
        try:
            cands = [track] if track else self.resolve(query)
        except ApiError as e:
            console_log.warn("request", f"lookup failed for {user}: {e}", dedupe_s=30)
            return {"ok": False, "code": "lookup", "reply": f"@{user} couldn't reach Spotify, try again."}
        if not cands:
            self._event("reject", user, f"no result: {query}", False)
            return {"ok": False, "code": "none", "reply": f"@{user} no song found for that."}
        now_uri = self.pb["track"]["uri"] if self.pb and self.pb["track"] else None
        first_fail = None
        with self.lock:
            for t in cands:
                ok, code, msg = rules.evaluate(s, t, user, roles, self.queue, now_uri, self.clock())
                if ok:
                    return self._accept(t, user, roles, redeem)
                first_fail = first_fail or (code, msg, t)
                if code in ("user_blocked", "closed", "mod_only", "sub_only", "full", "limit"):
                    break           # not a track problem: trying other search results won't help
            code, msg, t = first_fail
            self._event("reject", user, f"{t['name']}: {code}", False)
            self._bump()
            return {"ok": False, "code": code, "reply": msg}

    def _accept(self, t, user, roles, redeem):
        s = self.settings
        tier = rules.tier_for(s, roles, redeem)
        label = f"{t['name']} - {', '.join(t['artists'])}"
        if rules.needs_approval(s, roles):
            self.inbox.append({"id": uuid.uuid4().hex[:8], "track": t, "user": user, "roles": sorted(roles), "tier": tier,
                               "ts": self.clock(), "status": "pending"})
            self._event("pending", user, label)
            self.persist()
            self._bump()
            return {"ok": True, "code": "pending", "reply": f"@{user} '{label}' is waiting for approval."}
        item = self.add_track(t, "end", user, "viewer", tier)
        pos = self.queue.index(item["id"]) + 1
        return {"ok": True, "code": "added", "reply": f"@{user} added '{label}' (#{pos} in queue).", "item": item["id"]}

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
        """Entry for Streamer.bot/Host. -> {handled, ok, reply, code}. `reply` is empty when chat_replies is off."""
        cmd, arg = rules.parse(text)
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
                self.save_settings({"requests_open": low in ("open", "on")})
                return {"ok": True, "code": "toggle", "reply": "Song requests are now " + ("open." if low in ("open", "on") else "closed.")}
            if staff and low == "clear":
                return self._chat_cmd("clear", "", user, roles, staff, False)
            return self.request(user, arg, roles, redeem)
        if cmd == "song":
            return {"ok": True, "code": "song", "reply": self.song_line()}
        if cmd == "queue":
            return {"ok": True, "code": "queue", "reply": self.queue_line()}
        if cmd == "skip":
            return self.vote_skip(user, staff)
        if cmd == "oops":
            it = self.queue.remove_last_of(user)
            if not it:
                return {"ok": False, "code": "none", "reply": f"@{user} you have nothing to remove."}
            self._event("remove", user, it["name"])
            self.persist()
            self._bump()
            return {"ok": True, "code": "removed", "reply": f"@{user} removed '{it['name']}'."}
        if cmd == "clear" and staff:
            self.queue.clear(only_viewers=True)
            self.persist()
            self._bump()
            return {"ok": True, "code": "clear", "reply": "Viewer requests cleared."}
        if cmd == "blocksong" and staff:
            t = self.pb["track"] if self.pb and self.pb["track"] else None
            if not t:
                return {"ok": False, "code": "none", "reply": "Nothing is playing."}
            self.save_settings({"blocklist": self._own_settings()["blocklist"] + [t["uri"]]})
            self.skip(force=True)
            return {"ok": True, "code": "blocked", "reply": f"Blocked '{t['name']}' and skipped it."}
        return {"ok": False, "code": "denied", "reply": ""}

    def song_line(self):
        t = self.pb["track"] if self.pb and self.pb["track"] else None
        if not t:
            return "Nothing is playing right now."
        who = (self.now_item or {}).get("requester")
        return f"Now playing: {t['name']} - {', '.join(t['artists'])}" + (f" (requested by {who})" if who else "") + f" https://open.spotify.com/track/{t['id']}"

    def queue_line(self):
        items = self.queue.items
        if not items:
            return "The queue is empty. Request a song with !sr <song or link>."
        nxt = " | ".join(f"{i + 1}. {it['name']} - {it['artists'][0] if it['artists'] else ''}" for i, it in enumerate(items[:3]))
        return f"{len(items)} in queue. Next: {nxt}"

    def vote_skip(self, user, staff):
        s = self.settings
        if not (self.pb and self.pb["track"]):
            return {"ok": False, "code": "none", "reply": "Nothing is playing."}
        if staff and s["skip_mod_instant"]:
            self.skip(force=True)
            return {"ok": True, "code": "skipped", "reply": "Skipped."}
        self.skip_votes.add(user.lower())
        need = max(1, int(s["skip_votes"]))
        n = len(self.skip_votes)
        if n >= need:
            self.skip(force=True)
            return {"ok": True, "code": "skipped", "reply": f"Skip vote passed ({n}/{need}). Skipping."}
        self._bump()
        return {"ok": True, "code": "vote", "reply": f"Skip vote {n}/{need}."}

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
            a.volume(int(value))
        elif action == "transfer":
            a.transfer(str(value), play=True)
        else:
            raise QueueError("unknown action")
        self._schedule_refresh()

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
        return items


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"
