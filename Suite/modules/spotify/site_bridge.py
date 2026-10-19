"""Outbound-only bridge to innocentpenguin.com (Docs/SPOTIFY_CONTRACT.md v1).
push: state mirror every 3 s while playing / 10 s idle / at once on change.  poll: long-poll viewer events -> rules -> ack.
Site down = we back off (3 s -> 30 s) and keep working locally. The API key never leaves config.json."""
import json
import threading
import time
import urllib.error
import urllib.request

import console_log
from queue_core import QueueError
from spotify_api import ApiError

REASON = {"closed": "requests_closed", "mod_only": "requests_closed", "sub_only": "requests_closed", "offline": "requests_closed",
          "lookup": "requests_closed", "blocked": "blocked", "user_blocked": "blocked", "explicit": "explicit_blocked",
          "too_long": "too_long", "full": "queue_full", "dup_queue": "duplicate", "dup_recent": "duplicate", "limit": "cooldown",
          "none": "unknown_request", "usage": "unknown_request"}


def default_http(method, url, key, body, timeout):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return 0, {"error": str(e)}


class Bridge:
    def __init__(self, engine, http=default_http, sleep=time.sleep):
        self.e, self.http, self.sleep = engine, http, sleep
        self.stop = False
        self.last_ok = 0.0
        self.last_error = ""
        self.blocklist_version = None
        self._pushed_version = -1
        self._last_push = 0.0
        self.fail = 0

    # ---- config
    def conf(self):
        c = self.e.cfg.get("site") or {}
        url = (c.get("url") or "").rstrip("/")
        return (url, c.get("key") or "") if c.get("enabled") and url and c.get("key") else (None, None)

    def status(self):
        c = self.e.cfg.get("site") or {}
        return {"enabled": bool(c.get("enabled")), "url": c.get("url", ""), "has_key": bool(c.get("key")),
                "online": time.time() - self.last_ok < 30, "last_error": self.last_error}

    def configure(self, url=None, key=None, enabled=None):
        with self.e.lock:
            c = dict(self.e.cfg.get("site") or {})
            if url is not None:
                c["url"] = str(url).strip().rstrip("/")
            if key:
                c["key"] = str(key).strip()
            if enabled is not None:
                c["enabled"] = bool(enabled)
            self.e.cfg["site"] = c
            self.e._save_cfg()

    # ---- push
    def push_once(self, force=False):
        url, key = self.conf()
        if not url:
            return False
        snap = self.e.site_snapshot()
        st, js = self.http("POST", url + "/api/spotify/push", key, snap, 10)
        if st == 200:
            self._ok()
            self._pushed_version = self.e.version
            v = (js or {}).get("blocklistVersion")
            if v is not None and v != self.blocklist_version:
                self.pull_blocklist(v)
            return True
        self._bad(f"push HTTP {st}")
        return False

    def pull_blocklist(self, version=None):
        url, key = self.conf()
        st, js = self.http("GET", url + "/api/spotify/blocklist", key, None, 10)
        if st == 200 and isinstance(js, dict):
            self.e.site_block = {k: [str(x) for x in js.get(k, [])] for k in ("tracks", "artists", "users")}
            self.blocklist_version = js.get("version", version)
            console_log.info("site", f"blocklist v{self.blocklist_version} applied")

    def push_loop(self):
        while not self.stop:
            try:
                playing = bool(self.e.pb and self.e.pb["is_playing"])
                gap = 3 if playing else 10
                if self.conf()[0] and (self.e.version != self._pushed_version or time.time() - self._last_push >= gap):
                    self._last_push = time.time()
                    self.push_once()
            except Exception as ex:
                console_log.error("site", f"push loop: {type(ex).__name__}: {ex}", dedupe_s=60)
            self.sleep(0.5 if not self.fail else min(30, 3 * (2 ** self.fail)))

    # ---- poll / events
    def poll_once(self):
        url, key = self.conf()
        if not url:
            return 0
        st, js = self.http("GET", url + "/api/spotify/poll?wait=1", key, None, 30)
        if st != 200:
            self._bad(f"poll HTTP {st}")
            return 0
        self._ok()
        events = (js or {}).get("events") or []
        results = []
        for ev in events:
            try:
                results.append(self.handle_event(ev))
            except Exception as ex:
                console_log.error("site", f"event {ev.get('id')} failed: {type(ex).__name__}: {ex}", dedupe_s=30)
                results.append({"id": ev.get("id"), "ok": False, "reason": "requests_closed"})
        if results:
            self.http("POST", url + "/api/spotify/ack", key, {"v": 1, "results": results}, 10)
        return len(events)

    def poll_loop(self):
        while not self.stop:
            try:
                if self.conf()[0]:
                    self.poll_once()
                else:
                    self.sleep(3)
                    continue
            except Exception as ex:
                console_log.error("site", f"poll loop: {type(ex).__name__}: {ex}", dedupe_s=60)
            if self.fail:
                self.sleep(min(30, 3 * (2 ** self.fail)))

    def handle_event(self, ev):
        eid, typ = ev.get("id"), ev.get("type")
        user = str(ev.get("user") or ev.get("login") or "viewer")
        if typ == "request":
            track = None
            try:
                track = self.e.api.track(str(ev.get("trackId", ""))) if ev.get("trackId") else None
            except ApiError:
                track = None
            if not track:
                return {"id": eid, "ok": False, "reason": "unknown_request"}
            roles = [r for r in ("sub", "vip") if ev.get(r)] + (["mod"] if ev.get("staff") else [])
            r = self.e.request(user, "", roles, False, track=track)
            if r["ok"]:
                return {"id": eid, "ok": True, "rid": r.get("item") or r.get("code")}
            return {"id": eid, "ok": False, "reason": REASON.get(r["code"], "blocked")}
        if typ == "vote":
            if ev.get("kind") == "skip":
                r = self.e.vote_skip(user, False)
                return {"id": eid, "ok": r["ok"], **({} if r["ok"] else {"reason": "unknown_request"})}
            err = self.e.upvote(str(ev.get("rid", "")), str(ev.get("login") or user))
            return {"id": eid, "ok": err is None, **({"reason": err} if err else {})}
        if typ == "mod":
            return self.handle_mod(eid, str(ev.get("action", "")), str(ev.get("value") or ""), user)
        return {"id": eid, "ok": False, "reason": "unknown_request"}

    def handle_mod(self, eid, action, value, user):
        e = self.e
        try:
            if action == "skip":
                e.skip(force=True)
            elif action == "remove":
                e.queue.remove(value)
                e.persist()
                e._bump()
            elif action in ("open", "close"):
                e.save_settings({"requests_open": action == "open"})
            elif action == "pause":
                e.control("pause")
            elif action == "resume":
                e.control("resume")
            else:
                return {"id": eid, "ok": False, "reason": "unknown_request"}
        except (QueueError, ApiError) as ex:
            console_log.warn("site", f"mod {action} by {user} failed: {ex}", dedupe_s=10)
            return {"id": eid, "ok": False, "reason": "unknown_request"}
        console_log.info("site", f"mod action {action} by {user}")
        return {"id": eid, "ok": True}

    # ---- bookkeeping
    def _ok(self):
        self.last_ok, self.fail, self.last_error = time.time(), 0, ""

    def _bad(self, msg):
        self.fail = min(self.fail + 1, 4)
        self.last_error = msg
        console_log.warn("site", f"{msg}; backing off", dedupe_s=60)

    def start(self):
        for fn in (self.push_loop, self.poll_loop):
            threading.Thread(target=fn, daemon=True).start()
