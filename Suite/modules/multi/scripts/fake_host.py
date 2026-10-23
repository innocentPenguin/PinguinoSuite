"""Tiny fake Host for rehearsing viewer intros and shoutout clips WITHOUT the real Host (no chat, no bots, nothing leaves this PC).

  python scripts/fake_host.py serve [--port 8798]         serves GET /api/intro/viewer and /api/intro ({text, sound_id, status:"approved"}), /clip.webm (or clip.mp4 if present)
                                                          and POST /upload?name=clip.webm (store a test clip next to this script)
  python scripts/fake_host.py shoutout --multi http://127.0.0.1:8786 --token T --clip http://127.0.0.1:8798/clip.webm [--user penguin]
                                                          fires a shoutout alert with that clip into Multi through POST /api/alerts/fire

Point Multi at it with MULTI_HOST_URL=http://127.0.0.1:8798 and allow its clip host with MULTI_CLIP_EXTRA_HOSTS=127.0.0.1:8798 (both rehearsal-only env vars)."""
import argparse
import json
import pathlib
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
INTRO = {"text": "Hi chat, the colony's newest penguin is here!", "sound_id": "", "status": "approved"}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _viewer_intro(self, uid):
        """user ids pick a behaviour so a rehearsal can hit every case: pending / link / long / err / slow, anything else = approved"""
        if uid.startswith("pending"):
            return self._send(200, dict(INTRO, status="pending"))
        if uid.startswith("link"):
            return self._send(200, dict(INTRO, text="follow me at example.com for more"))
        if uid.startswith("long"):
            return self._send(200, dict(INTRO, text="x" * 300))
        if uid.startswith("err"):
            return self._send(500, {"ok": False})
        if uid.startswith("slow"):
            time.sleep(4)
        self._send(200, dict(INTRO, text=f"Hi chat, {uid} has arrived!"))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/intro/viewer":
            uid = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("user_id") or [""])[0]
            return self._viewer_intro(uid)
        if path == "/api/intro":
            return self._send(200, INTRO)
        if path == "/clip.mkv":                           # a clip the browser cannot play (not mp4/webm): the overlay must fall back to the text card
            return self._send(200, b"not a video", "video/x-matroska")
        for name, ctype in (("clip.mp4", "video/mp4"), ("clip.webm", "video/webm")):
            if path == "/" + name and (HERE / name).is_file():
                return self._send(200, (HERE / name).read_bytes(), ctype)
        self._send(404, {"ok": False})

    def do_POST(self):
        if self.path.startswith("/upload"):
            name = "clip.mp4" if "mp4" in self.path else "clip.webm"
            n = int(self.headers.get("Content-Length") or 0)
            (HERE / name).write_bytes(self.rfile.read(n))
            return self._send(200, {"ok": True, "name": name})
        self._send(404, {"ok": False})

    def log_message(self, *a):
        pass


def shoutout(multi, token, clip, user):
    body = {"type": "shoutout", "user": user, "message": "go follow them!", "id": f"fakehost:{user}:{__import__('time').time_ns()}",
            "clip": {"url": clip, "title": "rehearsal clip", "duration_s": 6}}
    req = urllib.request.Request(multi + "/api/alerts/fire", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token, "Origin": multi})
    with urllib.request.urlopen(req, timeout=8) as r:
        print(r.read().decode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["serve", "shoutout"])
    ap.add_argument("--port", type=int, default=8798)
    ap.add_argument("--multi", default="http://127.0.0.1:8766")
    ap.add_argument("--token", default="")
    ap.add_argument("--clip", default="")
    ap.add_argument("--user", default="penguin")
    a = ap.parse_args()
    if a.cmd == "serve":
        print(f"fake host on http://127.0.0.1:{a.port}")
        ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
    else:
        shoutout(a.multi, a.token, a.clip, a.user)
