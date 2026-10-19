"""Device model: every Suite install has a stable device id; exactly ONE alive device is the *master* and holds the
singletons (bots/Host, Spotify, schedulers, pre-stream checks). Others are auxiliary and run only local things.
No central server: devices gossip small heartbeats over PinguinoLink and each computes the same answer from the same
inputs (see Docs/MODULE_CONTRACT.md, "Devices: master / auxiliary").

Rule, in order: (1) a manual pin ("Take control here") to a device that is alive; (2) a device that is streaming;
(3) the alive device with the highest priority (ties: lowest device id). A device counts as a candidate only after it has
been alive for STABLE_SECS, so a PC that just booted does not yank the bots away from a Mac mid-session.
"""
import json
import os
import socket
import time
import uuid
from pathlib import Path

HEARTBEAT_SECS = 5
DEAD_AFTER = 20      # no heartbeat for this long = device is gone
STABLE_SECS = 30     # a (re)appearing device must be alive this long before it can take over by priority
WARMUP_SECS = 10     # a device that knows peers waits this long after start before assuming it is master


class Devices:
    def __init__(self, path, clock=time.time, name=None, existing_install=False):
        self.path, self.clock = Path(path), clock
        self.started = clock()
        d = {}
        try:
            d = json.loads(self.path.read_text("utf8"))
        except (OSError, ValueError):
            pass
        self.me = {
            "id": d.get("id") or uuid.uuid4().hex[:12],
            "name": d.get("name") or name or socket.gethostname(),
            "priority": int(d.get("priority", 50)),
            "role_pref": d.get("role_pref", "auxiliary"),   # what the user said this machine is: "master" | "auxiliary"
            "known": list(d.get("known", [])),                 # ids of peers ever paired/seen
            # first-run wizard done? An install that already had settings before device.json existed counts as done.
            "setup_done": d["setup_done"] if "setup_done" in d else bool(existing_install or d),  # a device.json from before the wizard existed = already set up
        }
        if "priority" not in d and self.me["role_pref"] == "master":
            self.me["priority"] = 100
        self.pin = d.get("pin") or {"to": None, "ts": 0.0}
        self.peers = {}                                        # id -> {name, priority, streaming, last_seen, alive_since}
        self.streaming, self.streaming_ts = False, 0.0
        self.status = None   # compact snapshot of this device's integration / pre-stream state, gossiped to peers (see green_merge)
        self._save()

    # ---- persistence
    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({**self.me, "pin": self.pin}, indent=2), "utf8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def configure(self, name=None, priority=None, role_pref=None, setup_done=None):
        if name:
            self.me["name"] = str(name)[:40]
        if priority is not None:
            self.me["priority"] = max(0, min(1000, int(priority)))
        if role_pref in ("master", "auxiliary"):
            self.me["role_pref"] = role_pref
        if setup_done is not None:
            self.me["setup_done"] = bool(setup_done)
        self._save()

    # ---- gossip
    def heartbeat(self):
        """What we tell peers about ourselves."""
        return {"id": self.me["id"], "name": self.me["name"], "priority": self.me["priority"], "streaming": self.streaming,
                "streaming_ts": self.streaming_ts, "pin": self.pin, "sent": self.clock(), "status": self.status}

    def receive(self, hb):
        """A peer's heartbeat (delivered by the Link module). Returns True if it was accepted."""
        if not isinstance(hb, dict) or not hb.get("id") or hb["id"] == self.me["id"]:
            return False
        now, pid = self.clock(), str(hb["id"])
        p = self.peers.get(pid)
        if p is None or now - p["last_seen"] > DEAD_AFTER:
            p = {"alive_since": now}
        p.update({"name": str(hb.get("name", pid))[:40], "priority": int(hb.get("priority", 0)), "streaming": bool(hb.get("streaming")),
                  "last_seen": now})
        if isinstance(hb.get("status"), dict):
            p["status"] = hb["status"]
        self.peers[pid] = p
        if pid not in self.me["known"]:
            self.me["known"].append(pid)
            self._save()
        pin = hb.get("pin")
        if isinstance(pin, dict) and float(pin.get("ts", 0)) > float(self.pin.get("ts", 0)):  # last write wins
            self.pin = {"to": pin.get("to"), "ts": float(pin["ts"])}
            self._save()
        return True

    def set_status(self, snap):
        self.status = snap

    def peer_statuses(self, now=None):
        """[(device name, status snapshot)] of alive peers that published one."""
        return [(p["name"], p["status"]) for p in self._alive_peers(now or self.clock()).values() if p.get("status")]

    # ---- user actions
    def take_control(self):
        self.pin = {"to": self.me["id"], "ts": self.clock()}
        self._save()

    def release_pin(self):
        self.pin = {"to": None, "ts": self.clock()}
        self._save()

    def set_streaming(self, on):
        if bool(on) != self.streaming:
            self.streaming, self.streaming_ts = bool(on), self.clock()

    # ---- the decision
    def _alive_peers(self, now):
        return {i: p for i, p in self.peers.items() if now - p["last_seen"] <= DEAD_AFTER}

    def candidates(self, now=None):
        """[(id, name, priority, streaming, stable)] of alive devices including this one."""
        now = now or self.clock()
        out = [(self.me["id"], self.me["name"], self.me["priority"], self.streaming, True)]
        for i, p in self._alive_peers(now).items():
            out.append((i, p["name"], p["priority"], p["streaming"], now - p["alive_since"] >= STABLE_SECS))
        return out

    def master_id(self, now=None):
        now = now or self.clock()
        c = self.candidates(now)
        alive = {x[0] for x in c}
        if self.pin.get("to") in alive:
            return self.pin["to"]
        streaming = [x for x in c if x[3]]
        if streaming:
            return sorted(streaming, key=lambda x: (-x[2], x[0]))[0][0]
        stable = [x for x in c if x[4]] or c
        return sorted(stable, key=lambda x: (-x[2], x[0]))[0][0]

    def warming_up(self, now=None):
        now = now or self.clock()
        return bool(self.me["known"]) and not self.peers and now - self.started < WARMUP_SECS

    def is_master(self, now=None):
        now = now or self.clock()
        return not self.warming_up(now) and self.master_id(now) == self.me["id"]

    def solo(self, now=None):
        return not self._alive_peers(now or self.clock())

    def state(self, now=None):
        now = now or self.clock()
        mid = self.master_id(now)
        names = {x[0]: x[1] for x in self.candidates(now)}
        return {"me": {**self.me, "streaming": self.streaming}, "master_id": mid, "master_name": names.get(mid, mid),
                "is_master": self.is_master(now), "solo": self.solo(now), "warming_up": self.warming_up(now), "pin": self.pin,
                "devices": [{"id": i, "name": n, "priority": pr, "streaming": st, "me": i == self.me["id"], "master": i == mid, "stable": ok}
                            for i, n, pr, st, ok in self.candidates(now)]}


def green_merge(items, peers, key, field, green, skip=lambda it: False, section="i"):
    """The master is the source of truth, but if any alive peer reports the same item GREEN while this view has it
    warn/fail, the merged view shows green and says which device it came from (the information that works wins).
    Applies to status/connection info only, never to secrets. items: dicts; peers: [(name, snapshot)]; snapshot[section] = {key: status}."""
    for it in items:
        if it.get(field) in green or skip(it):
            continue
        for name, snap in peers:
            if (snap.get(section) or {}).get(key(it)) in green:
                it[field] = next(iter(green))
                it["from"] = name
                it["detail"] = (str(it.get("detail", "")) + f" (OK on {name})").strip()
                break
    return items
