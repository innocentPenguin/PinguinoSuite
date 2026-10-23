"""Kick OAuth 2.1 (authorization code + PKCE) sign-in. Prepared flow only: `start()` returns the link Ivan opens and consents on HIMSELF;
this module never signs in for him. Docs: https://docs.kick.com/getting-started/generating-tokens-oauth2-flow

Config (Multi settings, nothing hard-coded):  kick_client_id, kick_redirect_uri (default http://127.0.0.1:8766/auth/kick/callback), kick_scopes (optional)
Secret (Credential Manager, entered by Ivan):  kick_client_secret
Stored by this module:  kick_token (access token, read by stream_info / send), kick_oauth {refresh_token, expires_at, scope}

How to (Ivan): 1) kick.com -> Settings -> Developer -> create an app; redirect URI = the value of kick_redirect_uri; copy the client id into Multi settings,
put the client secret into Credential Manager as PinguinoMulti/kick_client_secret. 2) Click "Sign in to Kick" in the launcher (POST /auth/kick/start),
approve on kick.com. 3) Multi receives the code on /auth/kick/callback and stores the tokens; refresh is automatic.
"""
import secrets

import requests

import config
import secrets_store
from connectors import oauth_util

AUTH_URL = "https://id.kick.com/oauth/authorize"
TOKEN_URL = "https://id.kick.com/oauth/token"
DEFAULT_REDIRECT = "http://127.0.0.1:8766/auth/kick/callback"
DEFAULT_SCOPES = "user:read channel:read channel:write chat:write events:subscribe"


def _cfg():
    s = config.settings()
    return (str(s.get("kick_client_id") or "").strip(), str(s.get("kick_redirect_uri") or DEFAULT_REDIRECT).strip(),
            str(s.get("kick_scopes") or DEFAULT_SCOPES).strip())


def authorize_url(client_id, redirect_uri, scopes, state, challenge):
    """Pure. The link Ivan opens."""
    return oauth_util.build_url(AUTH_URL, client_id=client_id, response_type="code", redirect_uri=redirect_uri, scope=scopes, state=state,
                                code_challenge=challenge, code_challenge_method="S256")


def start():
    """-> {"ok", "url"} or {"ok": False, "error"}. Remembers the PKCE verifier for the callback."""
    cid, redirect, scopes = _cfg()
    if not cid:
        return {"ok": False, "error": "Set kick_client_id first (Kick Settings -> Developer -> your app)"}
    if not secrets_store.get("kick_client_secret"):
        return {"ok": False, "error": "Put the Kick client secret into Credential Manager as PinguinoMulti/kick_client_secret"}
    verifier, challenge = oauth_util.new_pkce()
    state = secrets.token_urlsafe(24)
    oauth_util.remember(state, verifier, redirect)
    return {"ok": True, "url": authorize_url(cid, redirect, scopes, state, challenge)}


def token_request_body(grant, client_id, client_secret, **kw):
    """Pure. Form body for POST /oauth/token."""
    return dict({"grant_type": grant, "client_id": client_id, "client_secret": client_secret}, **kw)


def _post(body):
    r = requests.post(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Kick token endpoint {r.status_code}: {r.text[:160]}")
    return r.json()


def handle_callback(code, state):
    """Called with the ?code=&state= Kick redirects back with. -> {"ok"} | {"ok": False, "error"}. Never echoes tokens."""
    p = oauth_util.take(state)
    if not p:
        return {"ok": False, "error": "unknown or expired sign-in (start again)"}
    cid, _, _ = _cfg()
    try:
        resp = _post(token_request_body("authorization_code", cid, secrets_store.get("kick_client_secret") or "", code=code,
                                        redirect_uri=p["redirect_uri"], code_verifier=p["verifier"]))
        oauth_util.store_tokens("kick", resp)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def refresh():
    """Exchange the stored refresh token (Kick rotates it: the new one is stored). Raises on failure."""
    rec = oauth_util._rec("kick")
    if not rec.get("refresh_token"):
        raise RuntimeError("no Kick refresh token; sign in again")
    cid, _, _ = _cfg()
    resp = _post(token_request_body("refresh_token", cid, secrets_store.get("kick_client_secret") or "", refresh_token=rec["refresh_token"]))
    oauth_util.store_tokens("kick", resp)


def access_token():
    return oauth_util.fresh_token("kick", refresh)


def status():
    cid, redirect, _ = _cfg()
    return dict(oauth_util.status("kick", cid, secrets_store.get("kick_client_secret")), redirect_uri=redirect)
