"""Replay of Kick webhooks that the SITE collected (contract: side-session-notes 40-kick-webhook-relay.md).

The site stores Kick's signed webhook as {seq, id, type, version, ts, sig, body_b64} and serves
GET /api/bot/kick/events?since=<seq>&limit=200 -> {seq, events:[...]} (bot key). Whoever pulls (the Host, or Multi's own poller below) feeds each event
to Kick.ingest_webhook, which re-verifies Kick's RSA signature, so the site is never trusted. Pure functions + an injected fetch: no network here.
"""
import base64
import binascii


def to_webhook(ev):
    """Site event row -> (headers dict with lower-case Kick-* names, raw body bytes) | None when the row is malformed. Pure."""
    if not isinstance(ev, dict):
        return None
    try:
        body = base64.b64decode(ev.get("body_b64") or "", validate=True)
    except (binascii.Error, ValueError):
        return None
    if not body or not ev.get("id") or not ev.get("sig"):
        return None
    return ({"kick-event-message-id": str(ev["id"]), "kick-event-message-timestamp": str(ev.get("ts", "")),
             "kick-event-signature": str(ev["sig"]), "kick-event-type": str(ev.get("type", "")), "kick-event-version": str(ev.get("version", 1))}, body)


async def replay(events, ingest, seen=None):
    """Feed rows to `ingest(headers, body) -> (status, text)` in seq order. Duplicates (same message id) are skipped.
    -> {"ok", "rejected", "malformed", "dupes", "last_seq"}. 401 (bad signature) rows are counted and skipped, never retried."""
    seen = seen if seen is not None else set()
    out = {"ok": 0, "rejected": 0, "malformed": 0, "dupes": 0, "last_seq": None}
    for ev in sorted((e for e in events or [] if isinstance(e, dict)), key=lambda e: e.get("seq", 0)):
        if isinstance(ev.get("seq"), int):
            out["last_seq"] = ev["seq"]
        if ev.get("id") in seen:
            out["dupes"] += 1
            continue
        w = to_webhook(ev)
        if not w:
            out["malformed"] += 1
            continue
        code, _ = await ingest(*w)
        if code == 200:
            seen.add(ev["id"])
            out["ok"] += 1
        elif code in (401, 400):
            seen.add(ev["id"])
            out["rejected"] += 1
        else:
            raise RuntimeError(f"ingest failed with {code}; will retry from seq {ev.get('seq')}")      # transient: leave the cursor behind this row
    return out


async def pull_once(fetch, ingest, since, seen=None, limit=200):
    """fetch(since, limit) -> the site's JSON dict (async callable, injected). -> new cursor. Never moves the cursor past a row that raised."""
    data = await fetch(since, limit) or {}
    events = data.get("events") or []
    try:
        res = await replay(events, ingest, seen)
    except RuntimeError:
        return since
    return res["last_seq"] if res["last_seq"] is not None else since
