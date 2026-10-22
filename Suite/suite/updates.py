"""In-app updates: thin wrapper around the PinguinoUpdater (Suite/updater/updater.mjs, Node). The core never swaps files itself.

check()   -> what a release changes, per part (shell, core, Host, each module, scripts/docs)
apply()   -> one job in a background thread: module parts = stop that module, swap its files, start it again; app parts = verified and staged, swapped at the next start
rollback()-> put the previous version back (same stop/start around module files)
Never while live (the core's own live state AND the updater's Host check), never one job at a time, never touches Data\\ or secrets.
"""
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
MODULE_PARTS = {"listen", "multi", "link", "spotify", "voice"}
KNOWN_PARTS = MODULE_PARTS | {"shell", "core", "host", "lite", "tools"}
APP_PARTS = {"shell", "core", "host", "lite"}


class Updates:
    def __init__(self, install_dir, updater_js, port, modules, is_live, log=lambda *a, **k: None):
        self.install = Path(install_dir)
        self.js = Path(updater_js)
        self.port = port
        self.modules = modules        # dict id -> Module (needs .wanted, .stop(), .start())
        self.is_live = is_live        # () -> bool
        self.log = log
        self.lock = threading.Lock()
        self.job = {"state": "idle"}

    # ---- plumbing
    def supported(self):
        """Only a release install (it has install.json) updates itself. A development tree is updated with git."""
        return (self.install / "install.json").is_file() and self.js.is_file()

    def node(self):
        found = shutil.which("node")
        if found:
            return found
        local = self.install / "node.exe"
        return str(local) if local.is_file() else None

    def run(self, *args, timeout=900):
        node = self.node()
        if not node:
            return {"ok": False, "message": "Node.js is not installed on this PC (Setup installs it); updates are unavailable"}
        cmd = [node, str(self.js), *args, "--install", str(self.install), "--core-port", str(self.port)]
        kw = {"creationflags": 0x08000000} if IS_WIN else {}
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": "the update step timed out"}
        except OSError as e:
            return {"ok": False, "message": f"could not run the updater: {e}"[:200]}
        for line in reversed((p.stdout or "").strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except ValueError:
                    break
        return {"ok": False, "message": ((p.stderr or p.stdout or "the updater gave no answer").strip()[:200])}

    def _save(self, name, obj):
        try:
            d = self.install / "Data" / "updates"
            d.mkdir(parents=True, exist_ok=True)
            (d / name).write_text(json.dumps(obj), "utf8")
        except OSError:
            pass

    # ---- public
    def check(self):
        if not self.supported():
            return {"ok": True, "supported": False, "message": "This is a development copy (no install.json); update it with git."}
        r = self.run("check", timeout=60)
        r["supported"] = True
        r["live"] = bool(self.is_live()) or r.get("live") is not False
        r["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if r.get("ok"):
            self._save("last_check.json", {k: r.get(k) for k in ("available", "version", "checked_at", "components")})
        return r

    def last_check(self):
        try:
            return json.loads((self.install / "Data" / "updates" / "last_check.json").read_text("utf8"))
        except (OSError, ValueError):
            return None

    def status(self):
        return {"job": self.job, "last_check": self.last_check()}

    def _start_job(self, kind, target, parts):
        with self.lock:
            if self.job.get("state") == "running":
                return None
            self.job = {"state": "running", "kind": kind, "parts": parts, "message": "starting", "started": time.time()}
        threading.Thread(target=target, daemon=True).start()
        return self.job

    def _set(self, **kw):
        self.job = {**self.job, **kw}

    def _stop_modules(self, ids):
        """Stop each module that is wanted (running); returns the ids to start again. Gives the OS a moment to release file locks."""
        again = []
        for mid in ids:
            m = self.modules.get(mid)
            if m is not None and (m.wanted or getattr(m, "healthy", False)):
                m.stop()
                again.append(mid)
        if again:
            time.sleep(2)
        return again

    def _start_modules(self, ids):
        for mid in ids:
            m = self.modules.get(mid)
            if m is not None:
                try:
                    m.start()
                except Exception as e:  # noqa: BLE001 - the swap is already done or rolled back; report, do not crash the job
                    self.log("warn", "updates", f"could not restart {mid}: {e}")

    def apply(self, parts):
        parts = [p for p in dict.fromkeys(parts or []) if p in KNOWN_PARTS]
        if not parts:
            return {"ok": False, "status": 400, "message": "pick at least one part to update"}
        if not self.supported():
            return {"ok": False, "status": 400, "message": "this copy does not update itself (no install.json)"}
        if self.is_live():
            return {"ok": False, "status": 409, "message": "You are live. Updates wait until the stream is over."}
        job = self._start_job("apply", lambda: self._apply(parts), parts)
        if job is None:
            return {"ok": False, "status": 409, "message": "an update is already running"}
        return {"ok": True, "job": job}

    def _apply(self, parts):
        live_now = [p for p in parts if p not in APP_PARTS]
        app = [p for p in parts if p in APP_PARTS]
        modules = [p for p in live_now if p in MODULE_PARTS]
        results, restart_needed = [], False
        try:
            if live_now:
                self._set(message="updating " + ", ".join(live_now))
                again = self._stop_modules(modules)
                try:
                    r = self.run("apply", "--only", ",".join(live_now))
                finally:
                    self._start_modules(again)
                results.append(r)
                if not r.get("ok") or r.get("deferred"):
                    return self._finish(False if not r.get("ok") else None, r.get("message", "the update did not apply"), results)
            if app:
                self._set(message="getting " + ", ".join(app) + " ready")
                r = self.run("apply", "--only", ",".join(app), "--stage")
                results.append(r)
                if not r.get("ok"):
                    return self._finish(False, r.get("message", "could not stage the app update"), results)
                restart_needed = True
            msg = ("Updated " + ", ".join(live_now) + ". " if live_now else "") + ("Restart the Suite to finish " + ", ".join(app) + "." if app else "")
            self._finish(True, msg.strip() or "done", results, restart_needed)
        except Exception as e:  # noqa: BLE001
            self._finish(False, f"update failed: {e}"[:200], results)

    def _finish(self, ok, message, results, restart=False):
        self._set(state="done" if ok else ("blocked" if ok is None else "failed"), ok=bool(ok), message=message, restart_needed=restart, finished=time.time())
        self.log("info" if ok else "warn", "updates", message)

    def rollback(self):
        if not self.supported():
            return {"ok": False, "status": 400, "message": "this copy does not update itself (no install.json)"}
        if self.is_live():
            return {"ok": False, "status": 409, "message": "You are live. Roll back after the stream."}
        plan = self.run("rollback", "--plan", timeout=30)
        if not plan.get("ok"):
            return {"ok": False, "status": 404, "message": plan.get("message", "there is nothing to roll back to")}
        job = self._start_job("rollback", lambda: self._rollback(plan), plan.get("components", []))
        if job is None:
            return {"ok": False, "status": 409, "message": "an update is already running"}
        return {"ok": True, "job": job, "plan": plan}

    def _rollback(self, plan):
        mods = [c for c in plan.get("components", []) if c in MODULE_PARTS]
        try:
            again = self._stop_modules(mods)
            try:
                r = self.run("rollback")
            finally:
                self._start_modules(again)
            self._finish(bool(r.get("ok")), r.get("message", "rolled back"), [r], bool(r.get("staged")))
        except Exception as e:  # noqa: BLE001
            self._finish(False, f"rollback failed: {e}"[:200], [])
