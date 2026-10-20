"""VOD / clip / file ingestion: download audio -> compact 16k opus -> transcribe in chunks -> segments. One job at a time."""
import queue
import re
import threading
import time
import uuid
from pathlib import Path

import config as cfg
import db
import learn
import twitch
from audioio import iter16k

CHUNK_S = 900  # transcribe long audio in 15-minute slices (bounded memory, steady progress)


def to_ogg(src: Path, dst: Path) -> float:
    """Any audio/video file -> mono 16 kHz opus. Returns duration in seconds."""
    import av
    inp = av.open(str(src))
    ain = next(s for s in inp.streams if s.type == "audio")
    out = av.open(str(dst), "w", format="ogg")
    ast = out.add_stream("libopus", rate=16000)
    ast.layout = "mono"
    ast.bit_rate = 32000
    rs = av.AudioResampler(format="s16", layout="mono", rate=16000, frame_size=320)
    total = 0
    for frame in inp.decode(ain):
        for f in rs.resample(frame):
            total += f.samples
            for p in ast.encode(f):
                out.mux(p)
    for f in rs.resample(None) or []:
        total += f.samples
        for p in ast.encode(f):
            out.mux(p)
    for p in ast.encode(None):
        out.mux(p)
    out.close()
    inp.close()
    return total / 16000


def load16k(path: Path):
    """Decode to a 16 kHz mono float32 array (faster-whisper's own decode_audio breaks on newer PyAV)."""
    import av
    import numpy as np
    chunks = []
    with av.open(str(path)) as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in c.decode(next(s for s in c.streams if s.type == "audio")):
            for f in rs.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32) / 32768.0


class Jobs:
    def __init__(self, asr, emit):
        self.asr, self.emit = asr, emit
        self.q = queue.Queue()
        self.jobs = {}
        self.recover()
        threading.Thread(target=self._worker, daemon=True).start()

    # -- submission -----------------------------------------------------------
    def recover(self) -> int:
        """Jobs live in memory only: after a restart any queued/running row is dead. Mark it so it can be re-queued."""
        live = "kind!='live' AND status IN ('queued','downloading','converting','transcribing')"
        db.run("UPDATE sessions SET status='done', error='partly transcribed before a Listen restart' "
               f"WHERE {live} AND EXISTS (SELECT 1 FROM segments g WHERE g.session_id=sessions.id)")  # keep what was learned
        cur = db.run("UPDATE sessions SET status='interrupted', error='interrupted by a Listen restart - press Learn again' "
                     f"WHERE {live}")
        return cur.rowcount

    def submit(self, kind, title, source_id, url=None, path=None) -> str | None:
        old = db.one("SELECT id,status FROM sessions WHERE source_id=?", (source_id,))
        if old and old["status"] not in ("interrupted", "error"):
            return None  # already ingested / queued
        if old:  # failed or interrupted earlier: drop the empty shell and queue it again
            if db.one("SELECT 1 x FROM segments WHERE session_id=?", (old["id"],)):
                return None  # has lines already: never throw learned/corrected text away
            db.run("DELETE FROM sessions WHERE id=?", (old["id"],))
        sid = f"{kind}-{uuid.uuid4().hex[:8]}"
        db.run("INSERT INTO sessions(id,kind,title,source_id,url,status,created) VALUES(?,?,?,?,?,?,?)",
               (sid, kind, title, source_id, url, "queued", time.time()))
        self.jobs[sid] = {"id": sid, "kind": kind, "title": title, "status": "queued", "progress": 0.0, "error": None}
        self.q.put((sid, url, path))
        self._push(sid)
        return sid

    def sync_twitch(self) -> int:
        st = cfg.settings()
        items = twitch.vods(st["channel"], st["autolearn_vods"]) + twitch.clips(st["channel"], st["autolearn_clip_days"], st["autolearn_clips"])
        return sum(1 for i in items if self.submit(i["kind"], i["title"], i["source_id"], url=i["url"]))

    # -- internals ------------------------------------------------------------
    def _push(self, sid, **upd):
        j = self.jobs.setdefault(sid, {"id": sid})
        j.update(upd)
        db.run("UPDATE sessions SET status=?,progress=?,error=? WHERE id=?", (j.get("status"), j.get("progress", 0), j.get("error"), sid))
        self.emit({"type": "job", "job": j})

    def _worker(self):
        while True:
            sid, url, path = self.q.get()
            try:
                self._run(sid, url, path)
            except Exception as e:  # noqa: BLE001
                self._push(sid, status="error", error=str(e)[:300])

    def _download(self, sid, url) -> Path:
        import yt_dlp
        out = cfg.SOURCES / sid

        def hook(d):
            if d.get("status") == "downloading":
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if tot:
                    self._push(sid, status="downloading", progress=min(0.99, d["downloaded_bytes"] / tot))

        opts = {"format": "bestaudio/audio_only/worst", "outtmpl": str(out) + ".%(ext)s", "noplaylist": True, "quiet": True,
                "no_warnings": True, "progress_hooks": [hook], "concurrent_fragment_downloads": 4}
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
        return next(cfg.SOURCES.glob(sid + ".*"))

    def _run(self, sid, url, path):
        self._push(sid, status="downloading", progress=0.0)
        src = Path(path) if path else self._download(sid, url)
        self._push(sid, status="converting", progress=0.0)
        rel = f"audio/{sid}.ogg"
        dur = to_ogg(src, cfg.DATA / rel)
        if not path:
            src.unlink(missing_ok=True)
        db.run("UPDATE sessions SET audio=?,duration=? WHERE id=?", (rel, dur, sid))

        self._push(sid, status="transcribing", progress=0.0)
        n = 0
        for off_s, chunk in iter16k(cfg.DATA / rel, CHUNK_S):  # one slice in memory at a time, never the whole VOD
            for s in self.asr.iter_segments(chunk, offset=off_s):
                final = learn.finalize(s["words"], s["avg_logprob"])
                db.add_segment(sid, s["start"], s["start"], s["end"], rel, s["words"], final)
                n += 1
                self._push(sid, status="transcribing", progress=min(0.99, s["end"] / max(dur, 1)))
        self._push(sid, status="done", progress=1.0, segments=n)
