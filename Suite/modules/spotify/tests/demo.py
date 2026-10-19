"""Starts fake Spotify + the real server pre-connected with a queue, for looking at the UI: python tests/demo.py  (UI on :8792)."""
import os
import sys
import time

sys.argv = sys.argv[:1]
import e2e  # noqa: E402

sp, _ = e2e.fakes.start_spotify(e2e.SP_PORT)
e2e.fakes.start_site(e2e.SITE_PORT)
e2e.start_server()
e2e.post("/api/setup", {"client_id": "cid"})
q = e2e.urllib.parse.parse_qs(e2e.urllib.parse.urlparse(e2e.post("/api/auth/start")[1]["url"]).query)
e2e.get(f"/callback?code=GOODCODE&state={q['state'][0]}")
e2e.sim("play", t="t1", progress=60000)
e2e.post("/api/settings", {"requests_open": True})
for n, u in [(2, "ann"), (3, "bob"), (4, "ann"), (5, "sue")]:
    e2e.chat(u, f"!sr song {n}", ["sub"] if u == "sue" else [])
e2e.post("/api/queue/add", {"query": "Song 6", "where": "end"})
e2e.chat("zed", "!sr sweary")
print("demo running on", e2e.BASE, flush=True)
while True:
    time.sleep(5)
