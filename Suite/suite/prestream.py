"""Pre-stream readiness: schedule (4:30 and 4:45 pm Central, stream at 5:00 pm) and the check runner.
See Docs/MODULE_CONTRACT.md, "Pre-stream readiness checks". Pure functions + callables so it is testable on its own."""
import json
import shutil
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import helpdb

SLOTS = ("16:30", "16:45")  # Central wall-clock time; the stream starts at 17:00
WINDOW_MIN = 5              # a slot still fires if the core wakes up to 5 min late
STALE_SECS = 600            # a module's prestream-<id>.json older than this is "stale"


def _nth_sunday(year, month, n):
    d = datetime(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)  # first Sunday
    return d + timedelta(weeks=n - 1)


def central_now(utc=None):
    """Current wall-clock time in America/Chicago without needing a tz database (US rule: DST from the 2nd Sunday of
    March 02:00 to the 1st Sunday of November 02:00 local)."""
    utc = utc or datetime.now(timezone.utc)
    y = utc.year
    start = _nth_sunday(y, 3, 2).replace(hour=2) + timedelta(hours=6)    # 02:00 CST == 08:00 UTC
    end = _nth_sunday(y, 11, 1).replace(hour=2) + timedelta(hours=5)     # 02:00 CDT == 07:00 UTC
    naive = utc.replace(tzinfo=None)
    off = -5 if start <= naive < end else -6
    return naive + timedelta(hours=off), off


DEFAULT_SCHEDULE = {"enabled": True, "slots": list(SLOTS), "days": [0, 1, 2, 3, 4, 5, 6], "tz": "central"}   # days: Monday=0 ... Sunday=6


def clean_schedule(s):
    """Validated schedule from untrusted input: up to 6 HH:MM slots, weekdays 0-6, tz 'central' (Chicago, DST-aware) or 'local' (this PC)."""
    s = s if isinstance(s, dict) else {}
    out = {"enabled": bool(s.get("enabled", True))}
    slots = []
    for x in (s.get("slots") if isinstance(s.get("slots"), list) else DEFAULT_SCHEDULE["slots"])[:6]:
        try:
            h, m = str(x).split(":")
            if 0 <= int(h) <= 23 and 0 <= int(m) <= 59 and f"{int(h):02d}:{int(m):02d}" not in slots:
                slots.append(f"{int(h):02d}:{int(m):02d}")
        except ValueError:
            pass
    out["slots"] = sorted(slots)
    days = sorted({int(d) for d in (s.get("days") if isinstance(s.get("days"), list) else DEFAULT_SCHEDULE["days"]) if str(d).isdigit() and 0 <= int(d) <= 6})
    out["days"] = days
    out["tz"] = s.get("tz") if s.get("tz") in ("central", "local") else "central"
    return out


def due_slot(utc, done, sched=None):
    """Slot label ('16:30'/'16:45') that should run now and has not yet today, else None. `done` is a set of 'date slot'.
    sched = clean_schedule() dict (default: 16:30 + 16:45 Central every day)."""
    sched = sched or DEFAULT_SCHEDULE
    if not sched.get("enabled", True):
        return None
    local = central_now(utc)[0] if sched.get("tz", "central") == "central" else utc.astimezone().replace(tzinfo=None)
    if local.weekday() not in sched.get("days", DEFAULT_SCHEDULE["days"]):
        return None
    for slot in sched.get("slots", SLOTS):
        h, m = map(int, slot.split(":"))
        at = local.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{local.date()} {slot}"
        if at <= local < at + timedelta(minutes=WINDOW_MIN) and key not in done:
            return slot, key
    return None


def _item(module, id_, label, status, detail=""):
    return {"module": module, "id": id_, "label": label, "status": status, "detail": detail}


def _tcp(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def _ts(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _module_items(mid, spec, token, console_dir, now):
    """Readiness items a module reports: HTTP endpoint (manifest `prestream`) or prestream-<id>.json."""
    path = spec.get("prestream")
    raw = None
    if path:
        try:
            r = requests.get(spec["url"] + path, headers={"Authorization": f"Bearer {token}", "X-Pinguino-Token": token}, timeout=15)
            r.raise_for_status()
            raw = r.json()
        except Exception as e:  # noqa: BLE001
            return [_item(mid, "readiness", "Readiness report", "warn", f"{path} failed: {str(e)[:120]}")]
    else:
        f = Path(console_dir) / f"prestream-{mid}.json"
        if not f.exists():
            return []
        try:
            raw = json.loads(f.read_text("utf8"))
        except (OSError, ValueError):
            return [_item(mid, "readiness", "Readiness report", "warn", "prestream file unreadable")]
        t = _ts(raw.get("ts")) if isinstance(raw, dict) else None
        if t is None or now - t > STALE_SECS:
            return [_item(mid, "readiness", "Readiness report", "warn", "no recent readiness report from the module")]
    items = (raw.get("items") or raw.get("checks") or []) if isinstance(raw, dict) else []
    out = []
    for i in items[:60]:
        if isinstance(i, dict):
            st = i.get("status") if i.get("status") in ("pass", "warn", "fail") else "warn"
            it = _item(mid, str(i.get("id", ""))[:40], str(i.get("label", i.get("id", "")))[:80], st, str(i.get("detail", ""))[:200])
            h = helpdb.clean_help(i.get("help"))
            if h:
                it["help"] = h
            out.append(it)
    return out


def run_checks(modules, token_for, console_dir, errors_30min, disk_path, slot=None, scheduled=False, extra=None):
    """modules: [{id, spec, state, always_start}], token_for(id)->str, errors_30min()->int. Returns the report dict."""
    now = time.time()
    items = []
    from concurrent.futures import ThreadPoolExecutor  # module endpoints can take several seconds each: ask them all at once
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {m["id"]: pool.submit(_module_items, m["id"], m["spec"], token_for(m["id"]), console_dir, now) for m in modules if m["state"] == "running"}
        for m in modules:
            up = m["state"] == "running"
            items.append(_item(m["id"], "up", f"{m['spec'].get('name', m['id'])} is running", "pass" if up else ("fail" if m["always_start"] else "warn"),
                               "" if up else f"state: {m['state']}"))
            if up:
                items += futs[m["id"]].result()
    sb = _tcp("127.0.0.1", 8080)
    items.append(_item("core", "streamerbot", "Streamer.bot reachable (:8080)", "pass" if sb else "warn", "" if sb else "not reachable (fine once Host replaces it)"))
    obs = _tcp("127.0.0.1", 4455)
    items.append(_item("core", "obs", "OBS websocket reachable (:4455)", "pass" if obs else "warn", "" if obs else "OBS closed or websocket off"))
    try:
        free = shutil.disk_usage(disk_path).free / 1e9
        items.append(_item("core", "disk", "Disk space", "fail" if free < 1 else "warn" if free < 5 else "pass", f"{free:.1f} GB free"))
    except OSError as e:
        items.append(_item("core", "disk", "Disk space", "warn", str(e)[:80]))
    n = errors_30min()
    items.append(_item("core", "errors", "Errors in the last 30 min", "warn" if n else "pass", f"{n} error(s) - see Console" if n else ""))
    items += list(extra or [])
    summary = {s: sum(1 for i in items if i["status"] == s) for s in ("pass", "warn", "fail")}
    return {"ts": now, "scheduled": scheduled, "slot": slot, "summary": summary, "items": items}
