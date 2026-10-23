r"""Real-server check of the Kick/YouTube sign-in routes through the origin/token middleware (throwaway port 8797, temp data dir, no network).
Run:  ..\..\.venv\Scripts\python.exe tests\e2e_connect.py"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 8797
BASE = f"http://127.0.0.1:{PORT}"
fails = []


def call(method, path, body=None, origin=BASE):
    h = {"content-type": "application/json"}
    if origin:
        h["origin"] = origin
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw[:1] in "[{" else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name, str(detail)[:120] if not ok else "")
    if not ok:
        fails.append(name)


def main():
    tmp = tempfile.mkdtemp(prefix="multi_connect_")
    import os
    env = dict(os.environ, MULTI_PORT=str(PORT), PINGUINO_DATA_DIR=tmp, PINGUINO_API_TOKEN="e2e-token", PINGUINO_CORE_URL="http://127.0.0.1:1", MULTI_NO_KEYRING="1")
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        c, d = call("GET", "/auth/kick/callback?code=x&state=forged", origin=None)
        check("callback GET without Origin/token passes middleware (200 page, forged state refused)", c == 200 and "Sign-in failed" in d, (c, d))
        c, d = call("GET", "/auth/youtube/callback?error=access_denied", origin=None)
        check("callback with error param renders failure page", c == 200 and "access_denied" in d, (c, d))
        c, d = call("POST", "/auth/kick/start", origin=None)
        check("POST /auth/kick/start without Origin/token is refused", c in (401, 403), (c, d))
        c, d = call("POST", "/auth/kick/start")
        check("POST start same-origin reaches handler (asks for client id)", c == 200 and d["ok"] is False and "kick_client_id" in d["error"], (c, d))
        c, d = call("POST", "/api/settings", {"kick_client_id": "KID", "youtube_client_id": "YID", "youtube_min_poll_s": 10, "tiktok_sign_url": "", "kick_scopes": "chat:write", "kick_redirect_uri": f"{BASE}/auth/kick/callback", "youtube_redirect_uri": f"{BASE}/auth/youtube/callback"})
        check("settings accept all new keys", c == 200 and d["kick_client_id"] == "KID" and d["youtube_client_id"] == "YID", (c, d))
        c, d = call("POST", "/auth/kick/client", {"client_secret": "SECRET-VALUE"})
        check("client secret saved, not echoed", c == 200 and d["client_secret_set"] is True and "SECRET-VALUE" not in json.dumps(d), (c, d))
        c, d = call("POST", "/auth/kick/start")
        q = parse_qs(urlparse(d["url"]).query) if c == 200 and d.get("ok") else {}
        check("kick start returns PKCE authorize URL", q.get("client_id") == ["KID"] and q.get("code_challenge_method") == ["S256"] and "state" in q, (c, d))
        c, d = call("POST", "/auth/youtube/start")
        q = parse_qs(urlparse(d["url"]).query) if c == 200 and d.get("ok") else {}
        check("youtube start returns PKCE authorize URL", q.get("client_id") == ["YID"] and q.get("access_type") == ["offline"], (c, d))
        c, d = call("GET", "/auth/kick/callback?code=x&state=" + q.get("state", [""])[0], origin=None)
        check("youtube state is not valid for kick callback", "Sign-in failed" in d, (c, d))
        c, d = call("GET", "/assets/connect.js", origin=None)
        check("connect.js served", c == 200 and "conn42" in d, c)
        c, d = call("GET", "/?type=launcher", origin=None)
        check("index includes connect.js", c == 200 and "/assets/connect.js" in d, c)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    print("ALL PASS" if not fails else "FAILED: " + ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
