"""Connector contract. Each platform declares capabilities so the UI never offers what it cannot do."""

import asyncio
import os
import time

import console_log

SEND_WINDOW_S = 30           # the same line to the same place is never sent twice inside this window, whatever happened to the first attempt


class SendRejected(RuntimeError):
    """The platform (or a check of ours) refused the line BEFORE it could go out: nothing was sent, a retry is safe."""


class DuplicateSend(RuntimeError):
    """The same line was already sent (or may have been: timeout) a moment ago, or is still in flight. Never repeated."""


def send_disabled():
    """Rehearsal/sim switch: MULTI_NO_SEND=1 makes every connector refuse to send."""
    return os.environ.get("MULTI_NO_SEND", "").strip().lower() in ("1", "true", "yes", "on")


def refused(code, text):
    """HTTP error answer to a send -> exception. 4xx is a definite refusal (retry is safe); 5xx may have been processed (outcome unknown, not retried)."""
    return (SendRejected if 400 <= int(code) < 500 else RuntimeError)(text)

_LVL = {"connected": "info", "reconnecting": "warn", "needs_auth": "warn", "error": "error"}


class Connector:
    platform = ""
    label = ""
    official = True                  # False => UI shows an UNOFFICIAL badge
    capabilities = {"read": False, "send": False, "reply": False, "badges": False, "history": False}

    def __init__(self, inbox, emit):
        self.inbox, self.emit = inbox, emit
        self.state = {"status": "disconnected", "detail": "", "reconnects": 0, "last_message": 0, "latency_ms": None}

    def set_status(self, status, detail=""):
        prev = self.state.get("status")
        self.state.update(status=status, detail=detail)
        sig = (status, detail, self.state.get("reconnects"))
        now = time.time()
        if sig == getattr(self, "_sig", None) and now - getattr(self, "_sig_ts", 0) < 30:      # retry loops call this every 10-30 s: repeat only as a slow heartbeat
            return
        self._sig, self._sig_ts = sig, now
        if status in _LVL and (status != prev or status == "error"):
            console_log.log(_LVL[status], self.platform, f"{status}: {detail}", dedupe_s=300)
        elif prev in ("connected",) and status in ("disconnected", "disabled"):
            console_log.warn(self.platform, f"{status}: {detail}", dedupe_s=300)
        self.emit({"type": "conn.status", "platform": self.platform, **self.describe()})

    def describe(self):
        return {"platform": self.platform, "label": self.label, "official": self.official,
                "capabilities": self.capabilities, **self.state}

    async def run(self):            # long-running; reconnects internally
        raise NotImplementedError

    async def send(self, text, reply_to=None):
        raise NotImplementedError("this platform is read-only here")

    async def send_once(self, text, reply_to, do_send):
        """Run `do_send()` (a coroutine function) at most once per (line, reply target) per SEND_WINDOW_S.
        Success, a timeout / dropped connection / unreadable answer (outcome unknown) and a send still in flight all block a repeat;
        only a definite refusal (SendRejected) frees the line again. Lives in the connector so a retry from any caller (UI double click,
        server retry, Host fallback) cannot produce a second message."""
        if send_disabled():
            raise SendRejected("sending is switched off (MULTI_NO_SEND)")
        now = time.time()
        sends = self.__dict__.setdefault("_sends", {})
        for k in [k for k, v in sends.items() if now - v > SEND_WINDOW_S]:
            del sends[k]
        key = (" ".join(str(text).lower().split()), str(reply_to or ""))
        if key in sends:
            raise DuplicateSend("this line was already sent (or may have gone out) a moment ago: not sent again")
        sends[key] = now
        try:
            return await do_send()
        except SendRejected:
            sends.pop(key, None)
            raise
        except asyncio.CancelledError:
            raise                                  # cancelled mid-flight: the request may be out, keep the line blocked
        except Exception:
            raise                                  # outcome unknown (timeout, reset, unreadable answer, 5xx): the line stays blocked for the window
