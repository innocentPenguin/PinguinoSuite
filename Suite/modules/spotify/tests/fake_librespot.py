"""Stand-in for go-librespot used by e2e.py (SPOTIFY_CONNECT_BIN points here). Usage: fake_librespot.py --config_dir DIR
Reads the port from DIR/config.yml; serves /auth/code until POST /_pair, then /status with a device id; records /player/* calls (GET /_calls)."""
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

args = sys.argv[1:]
cdir = args[args.index("--config_dir") + 1] if "--config_dir" in args else "."
cfg = open(cdir + "/config.yml", encoding="utf-8").read()
port = int(re.search(r"port: (\d+)", cfg).group(1))
S = {"paired": False, "calls": [], "volume": int((re.search(r"initial_volume: (\d+)", cfg) or [0, 50])[1]), "cfg": cfg}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, js=None):
        b = json.dumps(js).encode() if js is not None else b""
        self.send_response(code)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def _go(self, m):
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n)) if n else {}
        p = self.path
        if p == "/auth/code":
            return self._send(404) if S["paired"] else self._send(200, {"url": "http://127.0.0.1:9/pair", "code": "ABCD-1234", "expires_at": int(time.time()) + 600})
        if p == "/status":
            return self._send(200, {"device_id": "libre1", "volume": S["volume"]}) if S["paired"] else self._send(200, {})
        if p == "/_pair":
            S["paired"] = True
            return self._send(200, {"ok": True})
        if p == "/_calls":
            return self._send(200, {"calls": S["calls"], "cfg": S["cfg"]})
        if p.startswith("/player/"):
            S["calls"].append([p, body])
            if p == "/player/volume":
                S["volume"] = body.get("volume", S["volume"])
            return self._send(200, {})
        return self._send(404)

    do_GET = lambda self: self._go("GET")
    do_POST = lambda self: self._go("POST")


print("time=x level=info msg=\"to complete authentication visit the following link: http://127.0.0.1:9/pair?code_challenge=abc\"", flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
