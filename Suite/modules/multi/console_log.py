"""Token-free structured log for the Pinguino Console: one JSON line per event appended to
<PINGUINO_DATA_DIR>/console/multi.jsonl  {ts,module,level,source,msg}. Never raises; secrets are scrubbed."""
import json
import os
import re
import threading
import time
from pathlib import Path

LEVELS = ("debug", "info", "warn", "error")
_lock = threading.Lock()
_last = {}
MAX_BYTES = 2_000_000
_SECRET = re.compile(r"(?i)(bearer\s+\S+|(?:token|key|secret|password|authorization)[\"']?\s*[=:]\s*\S+|[A-Za-z0-9_\-\.]{32,})")


def path():
    if os.environ.get("MULTI_CONSOLE_FILE"):
        return Path(os.environ["MULTI_CONSOLE_FILE"])
    base = Path(os.environ["PINGUINO_DATA_DIR"]) if os.environ.get("PINGUINO_DATA_DIR") else Path(__file__).parent / "data"
    return base / "console" / "multi.jsonl"


def scrub(s):
    return _SECRET.sub("<redacted>", str(s))[:400]


def log(level, source, msg, dedupe_s=0):
    """Append one event. dedupe_s>0 drops an identical (level, source, msg) repeated within that many seconds."""
    try:
        level = level if level in LEVELS else "info"
        msg = scrub(msg)
        now = time.time()
        if dedupe_s:
            k = (level, source, msg)
            if now - _last.get(k, 0) < dedupe_s:
                return
            _last[k] = now
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "module": "multi", "level": level,
                           "source": source, "msg": msg}, ensure_ascii=False)
        with _lock:
            if p.exists() and p.stat().st_size > MAX_BYTES:
                p.replace(p.with_suffix(".jsonl.1"))
            with p.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


def info(source, msg, **k): log("info", source, msg, **k)
def warn(source, msg, **k): log("warn", source, msg, **k)
def error(source, msg, **k): log("error", source, msg, **k)
