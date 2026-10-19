"""Live mic listening: capture -> energy VAD -> utterances -> Whisper -> segments. Listen-only; it triggers nothing."""
import collections
import queue
import threading
import time
import uuid
import wave

import numpy as np
import sounddevice as sd

import config as cfg
import db
import learn

SR = 16000
BLOCK_S = 0.032
SILENCE_END_S = 0.8
MAX_UTT_S = 25.0
MIN_UTT_S = 0.4


def list_devices() -> list:
    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append({"index": i, "name": d["name"], "api": apis.get(d["hostapi"], ""), "rate": int(d["default_samplerate"])})
    return out


def _to16k(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == SR:
        return x
    if rate % SR == 0:
        k = rate // SR
        return x[: len(x) // k * k].reshape(-1, k).mean(axis=1)
    return np.interp(np.linspace(0, len(x), int(len(x) * SR / rate), endpoint=False), np.arange(len(x)), x).astype(np.float32)


class Live:
    def __init__(self, asr, emit):
        self.asr, self.emit = asr, emit
        self.running = False
        self.session_id = None
        self._blocks = queue.Queue()
        self._utts = queue.Queue()
        self._stream = None
        self._t0 = 0.0

    def start(self, device=None):
        if self.running:
            raise RuntimeError("already listening")
        self.session_id = "live-" + time.strftime("%Y%m%d-%H%M%S")
        db.run("INSERT INTO sessions(id,kind,title,source_id,status,created) VALUES(?,?,?,?,?,?)",
               (self.session_id, "live", "Live mic " + time.strftime("%Y-%m-%d %H:%M"), self.session_id, "listening", time.time()))
        (cfg.LIVE_AUDIO / self.session_id).mkdir(exist_ok=True)
        rate = SR
        for rate in (SR, None):
            try:
                r = rate or int(sd.query_devices(device, "input")["default_samplerate"])
                self._rate = r
                self._stream = sd.InputStream(device=device, channels=1, samplerate=r, blocksize=int(r * BLOCK_S),
                                              dtype="float32", callback=self._cb)
                self._stream.start()
                break
            except Exception as e:  # noqa: BLE001
                self._stream = None
                err = e
        if not self._stream:
            raise RuntimeError(f"could not open mic: {err}")
        self.running = True
        self._t0 = time.time()
        threading.Thread(target=self._vad_loop, daemon=True).start()
        threading.Thread(target=self._asr_loop, daemon=True).start()
        self.emit({"type": "live", "state": "listening", "session": self.session_id})
        return self.session_id

    def stop(self):
        if not self.running:
            return
        self.running = False
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._blocks.put(None)
        db.run("UPDATE sessions SET status='done', duration=? WHERE id=?", (time.time() - self._t0, self.session_id))
        self.emit({"type": "live", "state": "stopped", "session": self.session_id})

    def _cb(self, indata, frames, t, status):
        self._blocks.put(indata[:, 0].copy())

    def _vad_loop(self):
        floor, n, silent, voiced = 0.0, 0, 0, 0
        preroll = collections.deque(maxlen=8)
        buf, active, utt_start = [], False, 0.0
        while True:
            b = self._blocks.get()
            if b is None:
                break
            b = _to16k(b, self._rate)
            rms = float(np.sqrt(np.mean(b * b)) + 1e-9)
            if floor == 0 or rms < floor * 1.5:
                floor = rms if floor == 0 else 0.97 * floor + 0.03 * rms
            speaking = rms > max(0.006, floor * 4)
            n += 1
            if n % 3 == 0:
                self.emit({"type": "level", "rms": min(1.0, rms * 8), "speaking": speaking})
            if not active:
                preroll.append(b)
                voiced = voiced + 1 if speaking else 0
                if voiced >= 2:
                    active, silent = True, 0
                    buf = list(preroll)
                    utt_start = time.time() - self._t0 - len(buf) * BLOCK_S
            else:
                buf.append(b)
                silent = 0 if speaking else silent + 1
                dur = len(buf) * BLOCK_S
                if silent * BLOCK_S >= SILENCE_END_S or dur >= MAX_UTT_S:
                    if dur - silent * BLOCK_S >= MIN_UTT_S:
                        self._utts.put((utt_start, np.concatenate(buf)))
                    active, voiced = False, 0
                    buf = []
                    preroll.clear()
        self._utts.put(None)

    def _asr_loop(self):
        k = 0
        while True:
            item = self._utts.get()
            if item is None:
                break
            t, audio = item
            k += 1
            rel = f"audio/live/{self.session_id}/{k:05d}.wav"
            with wave.open(str(cfg.DATA / rel), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
            try:
                for s in self.asr.iter_segments(audio):
                    final = learn.finalize(s["words"], s["avg_logprob"])
                    seg = db.add_segment(self.session_id, t + s["start"], s["start"], s["end"], rel, s["words"], final)
                    self.emit({"type": "segment", "segment": seg})
            except Exception as e:  # noqa: BLE001
                self.emit({"type": "error", "message": f"transcribe failed: {e}"})
