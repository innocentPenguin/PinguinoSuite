"""Connection checks for the Twitch connect path. Each check returns {id, label, ok, detail, fix?}.
Never returns or logs token values."""
import requests

import config
import secrets_store

NEED = {"user:read:chat", "user:write:chat"}


def _r(id, label, ok, detail, fix=""):
    return {"id": id, "label": label, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix}


def site_url():
    return secrets_store.get("site_url") or "https://innocentpenguin.com"


def run(tw, port=None):
    out = []
    site = site_url()

    # 1 credential store
    probe = "_check_probe"
    try:
        import keyring
        backend = type(keyring.get_keyring()).__name__
        keyring.set_password(secrets_store.SERVICE, probe, "1")
        good = keyring.get_password(secrets_store.SERVICE, probe) == "1"
        keyring.delete_password(secrets_store.SERVICE, probe)
        out.append(_r("keyring", "Secure token storage", good, f"Windows Credential Manager ({backend})" if good else "read-back failed",
                      "Tokens would only last until Multi restarts."))
    except Exception as e:
        out.append(_r("keyring", "Secure token storage", False, f"unavailable: {type(e).__name__}",
                      "Tokens would only last until Multi restarts."))

    # 2 site reachable
    try:
        r = requests.get(site, timeout=8)
        out.append(_r("site", "Site reachable", r.status_code < 500, f"{site} -> HTTP {r.status_code}",
                      "Check your internet or that the site is deployed."))
    except Exception as e:
        out.append(_r("site", "Site reachable", False, f"{site}: {type(e).__name__}", "Check your internet or that the site is deployed."))

    # 3 connect endpoint exists (does not follow into Twitch)
    url = site + "/auth/twitch/login?multi=1"
    try:
        r = requests.get(url, timeout=8, allow_redirects=False)
        loc = r.headers.get("location", "")
        from urllib.parse import parse_qs, urlparse
        sc = set(parse_qs(urlparse(loc).query).get("scope", [""])[0].split())
        ok = r.status_code in (301, 302, 303, 307, 308) and bool(loc) and NEED <= sc
        out.append(_r("connect", "Connect link asks for chat permission", ok,
                      f"HTTP {r.status_code}; scopes asked: {', '.join(sorted(sc)) or 'none'}",
                      "The live site has not deployed the Connect Multi flow (push/deploy the PinguinoSite commit)."))
    except Exception as e:
        out.append(_r("connect", "Connect link works", False, type(e).__name__, "Site unreachable."))

    # 4 refresh endpoint is deployed (no token sent: expect 400, not 404)
    try:
        r = requests.post(site + "/api/multi/refresh", json={}, timeout=8)
        out.append(_r("refresh", "Token refresh endpoint deployed", r.status_code in (400, 401, 403),
                      f"HTTP {r.status_code}", "Deploy the site commit with /api/multi/refresh."))
    except Exception as e:
        out.append(_r("refresh", "Token refresh endpoint deployed", False, type(e).__name__, "Site unreachable."))

    # 5 token stored, 6 valid + scopes
    tok = secrets_store.get("twitch_tokens")
    out.append(_r("token", "Twitch token saved", bool(tok and tok.get("access_token")),
                  "saved" if tok else "none yet", "Click Connect Twitch and approve."))
    if tok and tok.get("access_token"):
        info = None
        try:
            info = tw.validate(tok)
            how = "valid"
            if info is None:
                tok = tw.refresh(tok)
                info = tok and tw.validate(tok)
                how = "refreshed"
        except Exception as e:
            how = type(e).__name__
        scopes = set((info or {}).get("scopes", []))
        out.append(_r("valid", "Token accepted by Twitch", bool(info),
                      f"{how} as {info['login']}" if info else how, "Reconnect Twitch."))
        miss = sorted(NEED - scopes)
        out.append(_r("scopes", "Chat read + send permission", bool(info) and not miss,
                      "user:read:chat, user:write:chat" if not miss else "missing " + ", ".join(miss), "Reconnect Twitch and approve all permissions."))

    # 7 connector state
    if tw is not None:
        st = tw.state
        out.append(_r("connector", "Chat connection", st["status"] in ("connected", "live", "ok"),
                      f"{st['status']} {st.get('detail') or ''}".strip(), "Fix the failed checks above, then Restart connection."))
    return out
