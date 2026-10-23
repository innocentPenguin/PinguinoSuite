"""YouTube / Google OAuth for an installed (Desktop) app: loopback redirect + PKCE, refresh token stored. Prepared flow only: Ivan consents himself.
Docs: https://developers.google.com/identity/protocols/oauth2/native-app

Config:  youtube_client_id, youtube_redirect_uri (default http://127.0.0.1:8766/auth/youtube/callback; any 127.0.0.1 port is allowed for Desktop clients)
Secret (Credential Manager, entered by Ivan):  youtube_client_secret
Stored here:  youtube_token (access token; connectors/stream_info/viewers read it), youtube_oauth {refresh_token, expires_at, scope}

How to (Ivan): 1) console.cloud.google.com: new project, enable "YouTube Data API v3". 2) OAuth consent screen: External, add yourself as test user, then
PUBLISH to "In production" (in Testing status refresh tokens die after 7 days; the "unverified app" warning is fine). 3) Credentials -> OAuth client ID ->
type "Desktop app"; client id into Multi settings, client secret into Credential Manager as PinguinoMulti/youtube_client_secret. 4) Click "Sign in to YouTube"
in the launcher, approve (scope youtube.force-ssl). Refresh is automatic afterwards. 5) Quota: chat polling costs 5 of 10,000 units/day, so Multi polls
no faster than every youtube_min_poll_s (default 10 s, about 5.5 h of chat per day).
"""
import secrets

import requests

import config
import secrets_store
from connectors import oauth_util

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_REDIRECT = "http://127.0.0.1:8766/auth/youtube/callback"
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def _cfg():
    s = config.settings()
    return str(s.get("youtube_client_id") or "").strip(), str(s.get("youtube_redirect_uri") or DEFAULT_REDIRECT).strip()


def authorize_url(client_id, redirect_uri, state, challenge, scope=SCOPE):
    """Pure. access_type=offline + prompt=consent make Google issue (and re-issue) a refresh token."""
    return oauth_util.build_url(AUTH_URL, client_id=client_id, response_type="code", redirect_uri=redirect_uri, scope=scope, state=state,
                                code_challenge=challenge, code_challenge_method="S256", access_type="offline", prompt="consent")


def start():
    cid, redirect = _cfg()
    if not cid:
        return {"ok": False, "error": "Set youtube_client_id first (Google Cloud -> Credentials -> OAuth client, type Desktop app)"}
    verifier, challenge = oauth_util.new_pkce()
    state = secrets.token_urlsafe(24)
    oauth_util.remember(state, verifier, redirect)
    return {"ok": True, "url": authorize_url(cid, redirect, state, challenge)}


def token_request_body(grant, client_id, client_secret, **kw):
    body = dict({"grant_type": grant, "client_id": client_id}, **kw)
    if client_secret:
        body["client_secret"] = client_secret
    return body


def _post(body):
    r = requests.post(TOKEN_URL, data=body, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Google token endpoint {r.status_code}: {r.text[:160]}")
    return r.json()


def handle_callback(code, state):
    p = oauth_util.take(state)
    if not p:
        return {"ok": False, "error": "unknown or expired sign-in (start again)"}
    cid, _ = _cfg()
    try:
        resp = _post(token_request_body("authorization_code", cid, secrets_store.get("youtube_client_secret"), code=code,
                                        redirect_uri=p["redirect_uri"], code_verifier=p["verifier"]))
        oauth_util.store_tokens("youtube", resp)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def refresh():
    rec = oauth_util._rec("youtube")
    if not rec.get("refresh_token"):
        raise RuntimeError("no YouTube refresh token; sign in again")
    cid, _ = _cfg()
    resp = _post(token_request_body("refresh_token", cid, secrets_store.get("youtube_client_secret"), refresh_token=rec["refresh_token"]))
    oauth_util.store_tokens("youtube", resp)      # Google omits refresh_token on refresh; store_tokens keeps the old one


def access_token():
    return oauth_util.fresh_token("youtube", refresh)


def status():
    cid, redirect = _cfg()
    return dict(oauth_util.status("youtube", cid, secrets_store.get("youtube_client_secret")), redirect_uri=redirect)
