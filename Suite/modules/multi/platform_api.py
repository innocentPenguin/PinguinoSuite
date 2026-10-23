"""Sign-in routes for Kick and YouTube (worker 42). Wire in server.py with ONE line:   app.include_router(platform_api.router)   (after `import platform_api`)
Ivan opens the link from POST /auth/<p>/start himself and consents in his own browser; the callback only exchanges the code. No tokens are ever returned."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

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


@router.get("/auth/{platform}/callback", response_class=HTMLResponse)
def auth_callback(platform: str, code: str = "", state: str = "", error: str = ""):
    m = _MODS.get(platform)
    if not m:
        return HTMLResponse("unknown platform", 404)
    res = {"ok": False, "error": error or "no code"} if error or not code else m.handle_callback(code, state)
    msg = "Signed in. You can close this tab." if res["ok"] else "Sign-in failed: " + str(res.get("error", ""))[:200].replace("<", "&lt;")
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{platform}</title><body style='font:16px system-ui;background:#111;color:#f60;padding:2em'>{msg}")
