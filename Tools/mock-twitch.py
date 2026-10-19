# Mock Twitch helix for PinguinoHost tests: python mock-twitch.py PORT LOGFILE
import sys, json
from http.server import BaseHTTPRequestHandler, HTTPServer
port, log = int(sys.argv[1]), sys.argv[2]
class H(BaseHTTPRequestHandler):
    def _r(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _log(self, body):
        ok = self.headers.get("Authorization") == "Bearer mocktoken" and self.headers.get("Client-Id") == "mockcid"
        open(log, "a").write(f"{self.command} {self.path} auth={'OK' if ok else 'BAD'} {body}\n"); return ok
    def do_GET(self):
        ok = self._log("")
        if not ok: return self._r(401, {})
        if self.path.startswith("/users"): return self._r(200, {"data": [{"id": "4242", "login": "mockstreamer"}]})
        self._r(404, {})
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        ok = self._log(body)
        if not ok: return self._r(401, {})
        self._r(200, {"data": [{"is_sent": True}]})
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
