"""Sign-in routes for Kick and YouTube (worker 42). Wire in server.py with ONE line:   app.include_router(platform_api.router)   (after `import platform_api`)
Ivan opens the link from POST /auth/<p>/start himself and consents in his own browser; the callback only exchanges the code. No tokens are ever returned."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import config
import secrets_store
from connectors import kick_auth, youtube_auth

router = APIRouter()
_MODS = {"kick": kick_auth, "youtube": youtube_auth}


@router.get("/auth/{platform}/status")
def auth_status(platform: str):
    m = _MODS.get(platform)
    return m.status() if m else {"ok": False, "error": "unknown platform"}


@router.post("/auth/{platform}/start")
def auth_start(platform: str):
    m = _MODS.get(platform)
    return m.start() if m else {"ok": False, "error": "unknown platform"}


@router.post("/auth/{platform}/client")
async def auth_client(platform: str, request: Request):
    """{client_id?, client_secret?} typed by Ivan in the launcher: id -> settings, secret -> Credential Manager. Nothing is echoed back."""
    if platform not in _MODS:
        return {"ok": False, "error": "unknown platform"}
    b = await request.json()
    cid, sec = str(b.get("client_id") or "").strip()[:200], str(b.get("client_secret") or "").strip()[:300]
    ru = str(b.get("redirect_uri") or "").strip()[:200]
    if ru.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")) and ru.endswith(f"/auth/{platform}/callback"):
        config.save_settings({f"{platform}_redirect_uri": ru})          # loopback only: the consent page must send the code back to this PC
    if cid:
        config.save_settings({f"{platform}_client_id": cid})
    if sec:
        secrets_store.put(f"{platform}_client_secret", sec)
    return _MODS[platform].status()


@router.get("/auth/{platform}/callback", response_class=HTMLResponse)
def auth_callback(platform: str, code: str = "", state: str = "", error: str = ""):
    m = _MODS.get(platform)
    if not m:
        return HTMLResponse("unknown platform", 404)
    res = {"ok": False, "error": error or "no code"} if error or not code else m.handle_callback(code, state)
    msg = "Signed in. You can close this tab." if res["ok"] else "Sign-in failed: " + str(res.get("error", ""))[:200].replace("<", "&lt;")
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{platform}</title><body style='font:16px system-ui;background:#111;color:#f60;padding:2em'>{msg}")
