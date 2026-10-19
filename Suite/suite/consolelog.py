"""Console: one live log stream for the core and every module (see Docs/MODULE_CONTRACT.md, "Console logging").

Modules append JSON lines to <data dir>/console/<module id>.jsonl without any token; the core tails those files,
tails each module's captured stdout/stderr for error-looking lines, adds its own events, keeps a ring buffer for the
UI (GET /api/console) and rotates the files at 2 MB x 3.
"""
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

LEVELS = {"debug": 0, "info": 1, "warn": 2, "error": 3}
MAX_MSG = 2000
_ERR = re.compile(r"traceback|exception|\bfatal\b|unhandled|\berror\b|\[err", re.I)
_WARN = re.compile(r"\bwarn(ing)?\b|\bfailed\b", re.I)


def _parse_ts(v):
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
        except ValueError:
            pass
    return None


class Console:
    def __init__(self, directory, logs_dir, max_bytes=2_000_000, keep=3, ring=3000):
        self.dir, self.logs = Path(directory), Path(logs_dir)
        self.max_bytes, self.keep, self.ring = max_bytes, keep, ring
        self.entries, self.seq = [], 0
        self.redact = None  # optional text filter (the vault hides stored secrets in every line that reaches the Console)
        self._off = {}      # file path -> read offset
        self._pend = {}     # file path -> unterminated tail bytes
        self._lock = threading.Lock()
        self._wlock = threading.Lock()
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- adding
    def add(self, module, level, source, msg, ts=None):
        level = level if level in LEVELS else "info"
        if self.redact:
            msg = self.redact(str(msg))
        e = {"ts": ts or time.time(), "module": str(module)[:40], "level": level,
             "source": str(source or "")[:60], "msg": str(msg)[:MAX_MSG]}
        with self._lock:
            self.seq += 1
            e["seq"] = self.seq
            self.entries.append(e)
            if len(self.entries) > self.ring:
                del self.entries[:len(self.entries) - self.ring]
        return e

    def log(self, level, source, msg, module="core"):
        """The core's own entries: ring + core.jsonl (so they survive a restart and rotate like the rest)."""
        e = self.add(module, level, source, msg)
        try:
            with self._wlock, open(self.dir / "core.jsonl", "a", encoding="utf8") as f:
                f.write(json.dumps({k: e[k] for k in ("ts", "module", "level", "source", "msg")}) + "\n")
        except OSError:
            pass
        return e

    # ---- tailing
    def _read_new(self, path, start_at_end=False):
        key = str(path)
        try:
            size = path.stat().st_size
        except OSError:
            self._off.pop(key, None)
            return []
        if key not in self._off:
            self._off[key] = size if start_at_end else max(0, size - 64_000)
        if size < self._off[key]:  # truncated / rotated underneath us
            self._off[key], self._pend[key] = 0, b""
        if size == self._off[key]:
            return []
        try:
            with open(path, "rb") as f:
                f.seek(self._off[key])
                data = f.read(512_000)
        except OSError:
            return []
        self._off[key] += len(data)
        data = self._pend.pop(key, b"") + data
        cut = data.rfind(b"\n")
        if cut < 0:
            self._pend[key] = data[-16_000:]
            return []
        if cut < len(data) - 1:
            self._pend[key] = data[cut + 1:]
        return data[:cut].decode("utf8", "replace").splitlines()

    def ingest(self, module_ids=()):
        """Call about once a second: pull new lines from module console files and captured stdout/stderr."""
        try:
            files = list(self.dir.glob("*.jsonl"))
        except OSError:
            files = []
        for p in files:
            mid = p.stem
            first = str(p) not in self._off
            for ln in self._read_new(p):
                try:
                    o = json.loads(ln)
                    if not isinstance(o, dict):
                        continue
                except ValueError:
                    continue
                if mid == "core" and first is False:
                    continue  # our own writes are already in the ring; core.jsonl is only read once, at startup
                self.add(str(o.get("module", mid)) if mid == "core" else mid, o.get("level"), o.get("source"), o.get("msg", ""), _parse_ts(o.get("ts")))
            self._maybe_rotate(p)
        for mid in module_ids:
            for ln in self._read_new(self.logs / f"{mid}.log", start_at_end=True):
                lvl = "error" if _ERR.search(ln) else "warn" if _WARN.search(ln) else None
                if lvl:
                    self.add(mid, lvl, "stdout", ln.strip())

    def _maybe_rotate(self, p):
        try:
            if p.stat().st_size <= self.max_bytes:
                return
            with self._wlock:
                for i in range(self.keep, 0, -1):
                    src = p if i == 1 else p.with_name(f"{p.name}.{i - 1}")
                    if src.exists():
                        os.replace(src, p.with_name(f"{p.name}.{i}"))
            self._off.pop(str(p), None)
        except OSError:
            pass  # a writer still has it open; try again next tick

    # ---- querying
    def query(self, since=0, limit=300, min_level="debug", module="", q=""):
        lo, q, module = LEVELS.get(min_level, 0), q.lower(), module.lower()
        out = []
        with self._lock:
            snap = self.entries[-self.ring:]
        for e in snap:
            if e["seq"] <= since or LEVELS[e["level"]] < lo:
                continue
            if module and e["module"].lower() != module:
                continue
            if q and q not in (e["msg"] + " " + e["source"] + " " + e["module"]).lower():
                continue
            out.append(e)
        return out[-limit:]

    def errors_since(self, seconds):
        cut = time.time() - seconds
        with self._lock:
            return sum(1 for e in self.entries if e["level"] == "error" and e["ts"] >= cut and e["source"] != "prestream")
