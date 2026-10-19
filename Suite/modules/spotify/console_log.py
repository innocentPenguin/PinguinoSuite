"""Console contract logger: one JSON line per event in <PINGUINO_DATA_DIR>/console/spotify.jsonl. Never raises; scrubs secrets."""
import json
import os
import re
import threading
import time
from pathlib import Path

MODULE = "spotify"
LEVELS = ("debug", "info", "warn", "error")
_lock = threading.Lock()
_last = {}
_SECRET = re.compile(r"(?i)(bearer\s+\S+|(?:token|key|secret|password|authorization|code)[\"']?\s*[=:]\s*\S+|[A-Za-z0-9_\-\.]{40,})")


def data_dir():
    d = os.environ.get("PINGUINO_DATA_DIR")
    return Path(d) if d else Path(__file__).parent / "data"


def log(level, source, msg, dedupe_s=0):
    try:
        level = level if level in LEVELS else "info"
        msg = _SECRET.sub("<redacted>", str(msg))[:1000]
        now = time.time()
        if dedupe_s:
            k = (level, source, msg)
            if now - _last.get(k, 0) < dedupe_s:
                return
            _last[k] = now
        p = data_dir() / "console" / (MODULE + ".jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": round(now, 3), "module": MODULE, "level": level, "source": source, "msg": msg}, ensure_ascii=False)
        with _lock:
            for attempt in (1, 2):
                try:
                    with p.open("a", encoding="utf-8") as f:
                        f.write(line + "\n")
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(0.2)
    except Exception:
        pass


def info(source, msg, **kw):
    log("info", source, msg, **kw)


def warn(source, msg, **kw):
    log("warn", source, msg, **kw)


def error(source, msg, **kw):
    log("error", source, msg, **kw)
