"""Offline stand-ins for Spotify (accounts + Web API) and for innocentpenguin.com, used by e2e.py."""
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def trk(n, dur=200000, explicit=False, artist="Artist"):
    return {"id": f"id{n}".ljust(22, "x"), "uri": f"spotify:track:t{n}", "name": f"Song {n}", "duration_ms": dur, "explicit": explicit,
            "artists": [{"name": artist}], "album": {"name": "Album", "images": [{"url": "http://x/a.jpg"}, {"url": "http://x/b.jpg"}]}}


class FakeSpotify:
    """State machine: one player, a user queue, devices, tokens. `sim` endpoints let the test steer time/faults."""

    def __init__(self):
        self.lock = threading.RLock()
        self.tracks = {f"t{n}": trk(n) for n in range(1, 40)}
        self.tracks["t30"] = trk(30, explicit=True, artist="Sweary")
        self.tracks["t31"] = trk(31, dur=900000)
        self.product = "premium"
        self.devices = [{"id": "dev1", "name": "PC", "is_active": True, "volume_percent": 50}]
        self.current = None
        self.progress = 0
        self.playing = False
        self.queue = []
        self.volume = 50
        self.valid_access = set()
        self.refresh = {"R-1"}
        self.fault = None           # (path_substring, status, reason, remaining)
        self.log = []
        self.token_n = 0
        self.expire_next = False

    def advance(self, ms):
        with self.lock:
            if not self.current or not self.playing:
                return
            self.progress += ms
            dur = self.tracks[self.current]["duration_ms"]
            if self.progress >= dur:
                self.progress = 0
                if self.queue:
                    self.current = self.queue.pop(0)
                else:                              # like Spotify's autoplay: carry on with filler from the context
                    self.filler = getattr(self, "filler", 100) + 1
                    self.tracks[f"t{self.filler}"] = trk(self.filler, artist="Filler")
                    self.current = f"t{self.filler}"

    def item(self):
        return self.tracks[self.current] if self.current else None

    def playback_json(self):
        if not self.current and not self.devices:
            return None
        if not self.current:
            return None
        d = next((d for d in self.devices if d["is_active"]), None)
        return {"is_playing": self.playing, "progress_ms": self.progress, "item": self.item(), "shuffle_state": False, "repeat_state": "off",
                "device": {**d, "volume_percent": self.volume} if d else None}


class _H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, js=None, headers=None):
        body = json.dumps(js).encode() if js is not None else b""
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        S = self.server.sp
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n) if n else b""
        path = u.path
        with S.lock:
            S.log.append((method, path, q))
            if path == "/api/token":
                form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                if form.get("grant_type") == "authorization_code":
                    if form.get("code") != "GOODCODE" or not form.get("code_verifier"):
                        return self._send(400, {"error": "invalid_grant", "error_description": "bad code"})
                    rt = "R-1"
                elif form.get("refresh_token") in S.refresh:
                    rt = form["refresh_token"]
                else:
                    return self._send(400, {"error": "invalid_grant"})
                S.token_n += 1
                at = f"A-{S.token_n}"
                S.valid_access.add(at)
                return self._send(200, {"access_token": at, "refresh_token": rt, "expires_in": 3600, "scope": "x"})
            if path.startswith("/_sim/"):
                return self._sim(path[6:], q, raw)
            if not path.startswith("/v1/"):
                return self._send(404, {})
            tok = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if tok not in S.valid_access or S.expire_next:
                S.expire_next = False
                S.valid_access.discard(tok)
                return self._send(401, {"error": {"status": 401, "message": "The access token expired"}})
            if S.fault and S.fault[0] in path and S.fault[3] > 0:
                S.fault = (S.fault[0], S.fault[1], S.fault[2], S.fault[3] - 1)
                hd = {"Retry-After": "2"} if S.fault[1] == 429 else {}
                return self._send(S.fault[1], {"error": {"status": S.fault[1], "message": "fault", "reason": S.fault[2]}}, hd)
            p = path[3:]
            body = json.loads(raw) if raw else {}
            if p == "/me":
                return self._send(200, {"display_name": "Ivan", "id": "ivan", "product": S.product})
            if p == "/me/player" and method == "GET":
                j = S.playback_json()
                return self._send(200, j) if j else self._send(204)
            if p == "/me/player" and method == "PUT":
                for d in S.devices:
                    d["is_active"] = d["id"] in body.get("device_ids", [])
                S.playing = S.playing or bool(body.get("play"))
                return self._send(204)
            if p == "/me/player/devices":
                return self._send(200, {"devices": S.devices})
            if S.product != "premium" and method != "GET":
                return self._send(403, {"error": {"status": 403, "message": "Premium required", "reason": "PREMIUM_REQUIRED"}})
            if not any(d["is_active"] for d in S.devices) and p.startswith("/me/player") and method != "GET":
                return self._send(404, {"error": {"status": 404, "message": "No active device", "reason": "NO_ACTIVE_DEVICE"}})
            if p == "/me/player/queue" and method == "GET":
                return self._send(200, {"currently_playing": S.item(), "queue": [S.tracks[t] for t in S.queue]})
            if p == "/me/player/queue":
                S.queue.append(q["uri"].split(":")[-1])
                return self._send(204)
            if p == "/me/player/next":
                S.progress = S.tracks[S.current]["duration_ms"] if S.current else 0
                S.advance(0)
                return self._send(204)
            if p == "/me/player/previous":
                S.progress = 0
                return self._send(204)
            if p == "/me/player/pause":
                S.playing = False
                return self._send(204)
            if p == "/me/player/play":
                if body.get("uris"):
                    S.current, S.progress = body["uris"][0].split(":")[-1], 0
                S.playing = True
                return self._send(204)
            if p == "/me/player/seek":
                S.progress = int(q["position_ms"])
                return self._send(204)
            if p == "/me/player/volume":
                S.volume = int(q["volume_percent"])
                return self._send(204)
            if p == "/search":
                s = q.get("q", "").lower()
                hits = [t for t in S.tracks.values() if s in t["name"].lower() or s in t["artists"][0]["name"].lower()]
                return self._send(200, {"tracks": {"items": hits[:int(q.get("limit", 5))]}})
            if p.startswith("/tracks/"):
                t = next((t for t in S.tracks.values() if t["id"] == p.split("/")[-1]), None)
                return self._send(200, t) if t else self._send(404, {"error": {"status": 404, "message": "no such track"}})
            return self._send(404, {})

    def _sim(self, what, q, raw):
        S = self.server.sp
        if what == "play":
            S.current, S.progress, S.playing = q["t"], int(q.get("progress", 0)), True
        elif what == "advance":
            S.advance(int(q["ms"]))
        elif what == "fault":
            S.fault = (q["path"], int(q["status"]), q.get("reason", ""), int(q.get("n", 1)))
        elif what == "product":
            S.product = q["p"]
        elif what == "nodevice":
            for d in S.devices:
                d["is_active"] = False
        elif what == "clearqueue":
            S.queue.clear()
        elif what == "expire":
            S.expire_next = True
        elif what == "state":
            return self._send(200, {"current": S.current, "queue": S.queue, "playing": S.playing, "progress": S.progress, "volume": S.volume,
                                    "calls": [c[0] + " " + c[1] for c in S.log]})
        return self._send(200, {"ok": True})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")


def serve(handler_cls, attr, obj, port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    setattr(srv, attr, obj)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def start_spotify(port):
    sp = FakeSpotify()
    return sp, serve(_H, "sp", sp, port)


# ------------------------------------------------------------------ site
class FakeSite:
    def __init__(self):
        self.lock = threading.RLock()
        self.pushes = []
        self.events = []
        self.acks = []
        self.blocklist = {"version": 1, "tracks": [], "artists": [], "users": []}
        self.fail = 0              # next N requests answer 503
        self.key = "SITEKEY"


class _S(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, js):
        body = json.dumps(js).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _go(self, method):
        S = self.server.site
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n)) if n else {}
        with S.lock:
            if u.path.startswith("/_sim/"):
                if u.path == "/_sim/event":
                    S.events.append(body)
                elif u.path == "/_sim/fail":
                    S.fail = body["n"]
                elif u.path == "/_sim/blocklist":
                    S.blocklist = body
                elif u.path == "/_sim/dump":
                    return self._send(200, {"pushes": len(S.pushes), "last": S.pushes[-1] if S.pushes else None, "acks": S.acks})
                return self._send(200, {"ok": True})
            if self.headers.get("Authorization") != "Bearer " + S.key:
                return self._send(401, {})
            if S.fail > 0:
                S.fail -= 1
                return self._send(503, {})
            if u.path == "/api/spotify/push":
                S.pushes.append(body)
                return self._send(200, {"ok": True, "blocklistVersion": S.blocklist["version"]})
            if u.path == "/api/spotify/poll":
                ev, S.events = S.events, []
                return self._send(200, {"v": 1, "events": ev})
            if u.path == "/api/spotify/ack":
                S.acks.extend(body.get("results", []))
                return self._send(200, {"ok": True})
            if u.path == "/api/spotify/blocklist":
                return self._send(200, {"v": 1, **S.blocklist})
        return self._send(404, {})

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")


def start_site(port):
    s = FakeSite()
    return s, serve(_S, "site", s, port)
