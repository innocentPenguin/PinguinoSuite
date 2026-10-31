"""Shell (webview) errors persisted for bug-checks: POST /api/shell-log appends redacted one-line entries to Data\logs\shell.log (2 MB x 3 rotation)."""
import re
import threading
import time
from pathlib import Path

import safetext

MAX_ENTRIES = 50      # per request
MAX_MSG = 400
MAX_BYTES = 2 * 1024 * 1024
KEEP = 3              # shell.log, shell.log.1, shell.log.2

_SECRET = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}|((?:authorization|token|api[_-]?key|apikey|secret|password|passwd|x-pinguino-token|x-link-token|access_token)\s*[=:]\s*(?:bearer\s+)?)[^\s,;&\"']+")
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
_URL_QUERY = re.compile(r"(https?://[^\s?#\"')]+)\?[^\s\"')]*")


def redact(text, limit=MAX_MSG):
    s = str(text)
    s = _URL_QUERY.sub(r"\1?…", s)
    s = _SECRET.sub(lambda m: (m.group(1) or m.group(2)) + "[redacted]", s)
    s = _LONG_TOKEN.sub("[redacted]", s)
    s = " ".join(s.split())     # one line
    s = safetext.clean(s)
    return s[:limit]


class ShellLog:
    def __init__(self, folder, name="shell.log", max_bytes=MAX_BYTES, keep=KEEP):
        self.path = Path(folder) / name
        self.max_bytes, self.keep = max_bytes, keep
        self._lock = threading.Lock()

    def _rotate(self):
        for i in range(self.keep - 1, 0, -1):
            src = self.path if i == 1 else self.path.with_name(f"{self.path.name}.{i - 1}")
            dst = self.path.with_name(f"{self.path.name}.{i}")
            if src.exists():
                dst.unlink(missing_ok=True)
                src.replace(dst)

    def add(self, entries, now=None):
        """Write cleaned entries; returns the list of (level, text) lines written."""
        t = time.strftime("%H:%M:%S", time.localtime(now or time.time()))
        lines = []
        for e in list(entries or [])[:MAX_ENTRIES]:
            if not isinstance(e, dict):
                continue
            level = "error" if e.get("level") == "error" else "warn"
            n = e.get("n")
            cnt = f" (x{int(n)})" if isinstance(n, (int, float)) and n > 1 else ""
            src = redact(e.get("src") or "", 80)
            msg = redact(e.get("msg") or "")
            if not msg:
                continue
            lines.append((level, f"{t} [shell] {level}: {msg}{cnt}" + (f" [{src}]" if src else "")))
        if not lines:
            return []
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
                    self._rotate()
            except OSError:
                pass
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("\n".join(l for _, l in lines) + "\n")
        return lines
