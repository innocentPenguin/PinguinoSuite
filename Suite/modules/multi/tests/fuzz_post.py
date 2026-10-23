r"""POST/PUT/DELETE fuzz: every write route gets broken bodies and wrong-typed fields; none may answer 5xx (400/404/422 are fine).
Runs in its own process with a throwaway data dir (settings/profiles are written by some routes).
Run:  ..\..\.venv\Scripts\python.exe tests\fuzz_post.py     -> prints a JSON list of offenders ([] = clean)
Used by tests/test_post_fuzz.py."""
import inspect
import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
tmp = tempfile.mkdtemp(prefix="multi_fuzz_")
os.environ.update(PINGUINO_DATA_DIR=tmp, PINGUINO_CORE_URL="http://127.0.0.1:1", MULTI_NO_KEYRING="1", MULTI_NO_SEND="1",
                  MULTI_CONSOLE_FILE=os.path.join(tmp, "console.jsonl"))
os.environ.pop("PINGUINO_API_TOKEN", None)
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

SKIP = {"/hook/kick", "/api/open-connect", "/api/ding/test", "/api/ding/pick", "/api/pop/test", "/api/alerts/media", "/api/alerts/import-host",
        "/api/hotkey/{action}", "/api/voice/transcript", "/api/voice/confirm/{card_id}", "/auth/disconnect", "/auth/token",
        "/api/alerts/stress", "/api/alerts/testall"}
src = (ROOT / "server.py").read_text(encoding="utf-8")
KEYS = sorted(set(re.findall(r'b(?:\.get)?[\[(]"([a-z_0-9]+)"', src)))
JUNK = [None, "", "x", 0, -1, 10 ** 30, 1.5, float("inf"), True, [], [1, "a", None], {}, {"a": {"b": None}}, "x" * 5000, "\x00", "../../etc/passwd"]
RAW = [b"", b"{", b"null", b"[]", b'"x"', b"123", b"\xff\xfe", b"[1,2,3]", b"{}"]


def paths(route):
    return re.sub(r"\{[^}]+\}", "x", route.path)


def main():
    c = TestClient(server.app, base_url="http://127.0.0.1:8766", raise_server_exceptions=False)
    h = {"origin": "http://127.0.0.1:8766", "content-type": "application/json"}
    bad = {}
    for r in server.app.routes:
        ms = (getattr(r, "methods", None) or set()) & {"POST", "PUT", "DELETE"}
        if not ms or r.path in SKIP:
            continue
        print('route', r.path, flush=True)
        for m in ms:
            url = paths(r)
            try:
                rk = sorted(set(re.findall(r"""["']([a-z_0-9]+)["']""", inspect.getsource(r.endpoint)))) or KEYS[:5]
            except (OSError, TypeError):
                rk = KEYS[:5]
            bodies = [("raw", x) for x in RAW] + [("json", {k: j}) for k in rk for j in JUNK]
            for kind, body in bodies:
                try:
                    resp = c.request(m, url, content=body if kind == "raw" else json.dumps(body, allow_nan=True).encode(), headers=h)
                except Exception as e:                     # TestClient re-raises only for transport bugs
                    bad.setdefault(f"{m} {r.path}", []).append(f"{kind}:{str(body)[:60]} -> {type(e).__name__}")
                    continue
                if resp.status_code >= 500:
                    bad.setdefault(f"{m} {r.path}", []).append(f"{kind}:{str(body)[:60]} -> {resp.status_code}")
                    print(f"BAD {m} {r.path} {kind}:{str(body)[:60]} -> {resp.status_code}", flush=True)
    print("FUZZ_RESULT " + json.dumps({k: v[:3] + ([f"... {len(v)} total"] if len(v) > 3 else []) for k, v in sorted(bad.items())}))


if __name__ == "__main__":
    main()
