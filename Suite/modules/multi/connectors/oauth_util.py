"""Shared OAuth helpers for the Kick and YouTube sign-in flows (pure functions + one tiny token-store wrapper). No network here."""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import secrets_store

PENDING_TTL = 600           # an authorize link is good for 10 minutes
_pending = {}               # state -> {"verifier", "ts", "redirect_uri"}; in memory only


def new_pkce():
    """-> (code_verifier, S256 code_challenge). Verifier is 64 url-safe chars (spec: 43-128)."""
    verifier = secrets.token_urlsafe(48)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_url(base, **params):
    return base + "?" + urlencode({k: v for k, v in params.items() if v not in (None, "")})


def remember(state, verifier, redirect_uri, now=None):
    now = now or time.time()
    for s in [s for s, v in _pending.items() if now - v["ts"] > PENDING_TTL]:
        _pending.pop(s, None)
    _pending[state] = {"verifier": verifier, "ts": now, "redirect_uri": redirect_uri}


def take(state, now=None):
    """-> pending dict or None (unknown / expired / already used). One use only: guards against replayed or forged callbacks."""
    p = _pending.pop(state or "", None)
    if p and (now or time.time()) - p["ts"] <= PENDING_TTL:
        return p
    return None


def store_tokens(prefix, resp, now=None):
    """Keep the access token under `<prefix>_token` (what the connectors already read) and the rest under `<prefix>_oauth`."""
    now = now or time.time()
    old = _rec(prefix)
    rec = {"refresh_token": resp.get("refresh_token") or old.get("refresh_token", ""),
           "expires_at": now + int(resp.get("expires_in") or 3600), "scope": resp.get("scope", old.get("scope", ""))}
    secrets_store.put(f"{prefix}_token", resp["access_token"])
    secrets_store.put(f"{prefix}_oauth", rec)
    return rec


def fresh_token(prefix, refresh_fn, margin=120, now=None):
    """Access token for `prefix`, refreshed first when it expires within `margin` s. Falls back to the stored token (never raises)."""
    tok = secrets_store.get(f"{prefix}_token")
    rec = _rec(prefix)
    if rec.get("refresh_token") and (now or time.time()) > rec.get("expires_at", 0) - margin:
        try:
            refresh_fn()
            tok = secrets_store.get(f"{prefix}_token")
        except Exception:
            pass
    return tok


def status(prefix, client_id, has_secret):
    rec = _rec(prefix)
    return {"client_id_set": bool(client_id), "client_secret_set": bool(has_secret), "signed_in": bool(secrets_store.get(f"{prefix}_token")),
            "can_refresh": bool(rec.get("refresh_token")), "expires_at": rec.get("expires_at", 0), "scope": rec.get("scope", "")}


def _rec(prefix):
    r = secrets_store.get(f"{prefix}_oauth")
    return r if isinstance(r, dict) else {}
