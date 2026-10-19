"""PinguinoBot Ears - local web UI + API. Listen-only: transcribes and learns, never acts.
Run:  run.bat   (http://127.0.0.1:8765)"""
import asyncio
import json
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import asr as asr_mod
import config as cfg
import db
import ingest
import learn
import live as live_mod
import twitch


class Hub:
    def __init__(self):
        self.clients, self.loop = set(), None

    def emit(self, ev):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._send(ev), self.loop)

    async def _send(self, ev):
        for ws in list(self.clients):
            try:
                await ws.send_json(ev)
            except Exception:
                self.clients.discard(ws)


hub = Hub()
state = {"asr": {"state": "loading", "detail": ""}}


def on_asr_state(s, d=""):
    state["asr"] = {"state": s, "detail": d}
    hub.emit({"type": "asr", **state["asr"]})


asr = asr_mod.ASR(on_asr_state)
mic = live_mod.Live(asr, hub.emit)
jobs = ingest.Jobs(asr, hub.emit)


def autolearn_loop():
    while True:
        if cfg.settings()["autolearn"]:
            _safe_sync()
        time.sleep(1800)  # turning the toggle on also syncs immediately (see /api/settings)


@asynccontextmanager
async def lifespan(app):
    hub.loop = asyncio.get_running_loop()
    threading.Thread(target=asr.load, daemon=True).start()
    threading.Thread(target=autolearn_loop, daemon=True).start()
    yield
    mic.stop()


app = FastAPI(lifespan=lifespan)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402  (the Suite dashboard on :8760 reads Listen's status)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8760", "http://localhost:8760"], allow_methods=["*"], allow_headers=["*"])
app.mount("/media", StaticFiles(directory=cfg.DATA), name="media")


@app.get("/")
def index():
    return FileResponse(cfg.ROOT / "static" / "index.html")


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    hub.clients.add(sock)
    await sock.send_json({"type": "asr", **state["asr"]})
    try:
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        hub.clients.discard(sock)


# ------------------------------------------------------------------ status / settings
@app.get("/api/status")
def status():
    st = cfg.settings()
    return {"asr": state["asr"], "listening": mic.running, "live_session": mic.session_id if mic.running else None, "settings": st,
            "stats": db.one("SELECT COUNT(*) total, SUM(status='corrected') corrected, SUM(status='approved') approved, "
                            "SUM(status='new' AND unsure>0) to_review, SUM(CASE WHEN status!='new' THEN end-start ELSE 0 END) reviewed_secs FROM segments")}


class Settings(BaseModel):
    channel: str | None = None
    autolearn: bool | None = None
    yellow: float | None = None
    red: float | None = None
    device: int | None = None


@app.post("/api/settings")
def set_settings(s: Settings):
    st = cfg.save_settings({k: v for k, v in s.model_dump().items() if v is not None})
    if s.autolearn:
        threading.Thread(target=lambda: _safe_sync(), daemon=True).start()
    return st


def _safe_sync():
    try:
        n = jobs.sync_twitch()
        hub.emit({"type": "toast", "message": f"Auto-learn queued {n} new VOD/clip(s)"})
    except Exception as e:  # noqa: BLE001
        hub.emit({"type": "error", "message": f"auto-learn: {e}"})


# ------------------------------------------------------------------ live mic
@app.get("/api/devices")
def devices():
    return live_mod.list_devices()


class Start(BaseModel):
    device: int | None = None


@app.post("/api/live/start")
def live_start(b: Start):
    try:
        cfg.save_settings({"device": b.device})
        return {"session": mic.start(b.device)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.post("/api/live/auto")
def live_auto():
    """Called by PinguinoSuite when the stream goes live: start the remembered mic (idempotent)."""
    if mic.running:
        return {"session": mic.session_id, "already": True}
    try:
        return {"session": mic.start(cfg.settings()["device"])}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.post("/api/live/stop")
def live_stop():
    mic.stop()
    return {"ok": True}


# ------------------------------------------------------------------ sources (Twitch / url / upload)
@app.get("/api/twitch")
def twitch_list(channel: str | None = None):
    st = cfg.settings()
    ch = channel or st["channel"]
    try:
        items = twitch.vods(ch, 20) + twitch.clips(ch, st["autolearn_clip_days"], 30)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    for i in items:
        s = db.one("SELECT id,status,progress FROM sessions WHERE source_id=?", (i["source_id"],))
        i["session"] = s
    return items


class Queue(BaseModel):
    kind: str
    title: str
    source_id: str
    url: str


@app.post("/api/queue")
def queue_item(b: Queue):
    return {"session": jobs.submit(b.kind, b.title, b.source_id, url=b.url)}


class UrlIn(BaseModel):
    url: str


@app.post("/api/ingest-url")
def ingest_url(b: UrlIn):
    return {"session": jobs.submit("url", b.url, "url:" + b.url, url=b.url)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    dst = cfg.SOURCES / f"up-{uuid.uuid4().hex[:8]}-{file.filename}"
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"session": jobs.submit("upload", file.filename, "upload:" + dst.name, path=str(dst))}


@app.get("/api/jobs")
def list_jobs():
    return db.rows("SELECT id,kind,title,status,progress,error,duration FROM sessions WHERE kind!='live' ORDER BY created DESC LIMIT 60")


@app.get("/api/sessions")
def sessions():
    return db.rows("SELECT s.id,s.kind,s.title,s.status,s.duration,s.created,(SELECT COUNT(*) FROM segments g WHERE g.session_id=s.id) segments,"
                   "(SELECT COUNT(*) FROM segments g WHERE g.session_id=s.id AND g.status='new' AND g.unsure>0) to_review "
                   "FROM sessions s ORDER BY s.created DESC LIMIT 200")


# ------------------------------------------------------------------ segments / learning
@app.get("/api/segments")
def segments(session: str, after: int = 0, limit: int = 300):
    return [db.seg_json(r) for r in db.rows("SELECT * FROM segments WHERE session_id=? AND id>? ORDER BY id LIMIT ?", (session, after, limit))]


@app.get("/api/review/next")
def review_next(session: str | None = None, exclude: str = "", confident: bool = False):
    ex = [int(x) for x in exclude.split(",") if x.strip().isdigit()]
    where = "status='new'" + ("" if confident else " AND unsure>0")
    args = []
    if session:
        where += " AND session_id=?"
        args.append(session)
    if ex:
        where += f" AND id NOT IN ({','.join('?' * len(ex))})"
        args += ex
    r = db.one(f"SELECT * FROM segments WHERE {where} ORDER BY unsure DESC, id LIMIT 1", args)
    left = db.one(f"SELECT COUNT(*) n FROM segments WHERE {where}", args)["n"]
    return {"segment": db.seg_json(r) if r else None, "left": left}


class Correction(BaseModel):
    text: str


@app.post("/api/segments/{sid}/correct")
def correct(sid: int, b: Correction):
    r = db.one("SELECT * FROM segments WHERE id=?", (sid,))
    if not r:
        raise HTTPException(404)
    text = " ".join(b.text.split())
    learned = {"rules": [], "vocab": []}
    if text == r["text"]:
        status = "approved"
    else:
        status = "corrected"
        learned = learn.learn_from_correction(json.loads(r["raw_words"]), text)
    db.run("UPDATE segments SET status=?, corrected_text=? WHERE id=?", (status, text if status == "corrected" else None, sid))
    with open(cfg.DATA / "gold.jsonl", "a", encoding="utf8") as f:  # (audio, text) pairs = future fine-tuning set
        f.write(json.dumps({"audio": r["audio"], "start": r["start"], "end": r["end"], "raw": r["raw_text"], "text": text, "status": status}) + "\n")
    return {"status": status, "learned": learned}


@app.post("/api/regrade")
def regrade():
    return {"updated": learn.regrade_unreviewed()}


@app.get("/api/vocab")
def vocab():
    return {"vocab": db.rows("SELECT term,count,source FROM vocab ORDER BY count DESC, term"),
            "rules": db.rows("SELECT wrong,right,count FROM rules ORDER BY count DESC, wrong")}


class Term(BaseModel):
    term: str


@app.post("/api/vocab")
def vocab_add(b: Term):
    learn.add_vocab(b.term, "manual")
    return {"ok": True}


@app.delete("/api/vocab")
def vocab_del(term: str):
    db.run("DELETE FROM vocab WHERE term=?", (term,))
    return {"ok": True}


class Rule(BaseModel):
    wrong: str
    right: str


@app.post("/api/rules")
def rule_add(b: Rule):
    db.run("INSERT INTO rules(wrong,right,count) VALUES(?,?,2) ON CONFLICT(wrong) DO UPDATE SET right=excluded.right", (learn.norm(b.wrong) if " " not in b.wrong.strip() else " ".join(learn.norm(w) for w in b.wrong.split()), b.right))
    return {"ok": True}


@app.delete("/api/rules")
def rule_del(wrong: str):
    db.run("DELETE FROM rules WHERE wrong=?", (wrong,))
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=cfg.PORT, log_level="warning")
