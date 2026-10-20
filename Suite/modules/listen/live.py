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
SILENT_RMS = 0.0015       # below this the input is dead-quiet (a live mic always has some noise floor)
SILENT_ALERT_S = 30.0     # this long without signal while listening = alert


def list_devices() -> list:
    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append({"index": i, "name": d["name"], "api": apis.get(d["hostapi"], ""), "rate": int(d["default_samplerate"])})
    return out


def resolve_device(st: dict, devices: list | None = None, default_index: int | None = None) -> dict | None:
    """Which input device to open NOW. The mic is saved by name because sounddevice indexes shift whenever a device is plugged in,
    removed or reordered (Voicemeeter, CABLE). Returns {index, name, how, wanted} or None when there is no input device at all.
    how: name | name_ci | name_part | index | default | default_fallback (the chosen mic is gone, the Windows default was used instead)."""
    devs = list_devices() if devices is None else devices
    if not devs:
        return None
    name, api, idx = (st.get("device_name") or ""), (st.get("device_hostapi") or ""), st.get("device")
    wanted = name or (f"device #{idx}" if idx is not None else "")

    def hit(d, how):
        return {"index": d["index"], "name": d["name"], "how": how, "wanted": wanted}
    if name:
        for ok, how in ((lambda d: d["name"] == name and (not api or d["api"] == api), "name"),
                        (lambda d: d["name"] == name, "name"),
                        (lambda d: d["name"].lower() == name.lower(), "name_ci"),
                        (lambda d: name.lower() in d["name"].lower() or d["name"].lower() in name.lower(), "name_part")):
            for d in devs:
                if ok(d):
                    return hit(d, how)
    elif idx is not None:
        for d in devs:
            if d["index"] == idx:
                return hit(d, "index")
    if default_index is None:
        try:
            default_index = sd.default.device[0]
        except Exception:  # noqa: BLE001
            default_index = None
    d = next((x for x in devs if x["index"] == default_index), None) or devs[0]
    r = hit(d, "default_fallback" if wanted else "default")
    return r


API_RANK = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}   # WDM-KS and anything else last: it often refuses to open (PaErrorCode -9996)
_GENERIC = {"microphone", "input", "audio", "stereo", "mono", "usb", "wave", "webcam", "capture", "driver", "sound", "mic", "line", "device", "virtual"}


def _tokens(name: str) -> set:
    import re
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3 and w not in _GENERIC}


def candidates(st: dict, devices: list | None = None, default_index: int | None = None) -> list:
    """Every device worth trying, best first: the chosen mic, the same mic on other host APIs (MME/DirectSound/WASAPI before WDM-KS),
    a similar name (shares a distinctive word such as 'Yeti'), then the Windows default input. Opening can fail on a device that is listed
    (PaErrorCode -9996), so the caller walks this list until one opens."""
    first = resolve_device(st, devices, default_index)
    if first is None:
        return []
    devs = list_devices() if devices is None else devices
    out, seen = [], set()

    def add(d, how):
        if d["index"] not in seen:
            seen.add(d["index"])
            out.append({"index": d["index"], "name": d["name"], "api": d.get("api", ""), "how": how, "wanted": first["wanted"]})
    rank = lambda d: API_RANK.get(d.get("api", ""), 3)  # noqa: E731
    if first["how"] != "default_fallback":
        add(next(d for d in devs if d["index"] == first["index"]), first["how"])
        base = first["name"].lower()
        for d in sorted(devs, key=rank):
            if d["name"].lower() == base:
                add(d, "same_name")
        tk = _tokens(first["name"])
        if tk:
            for d in sorted(devs, key=lambda d: (-len(_tokens(d["name"]) & tk), rank(d))):
                if _tokens(d["name"]) & tk:
                    add(d, "similar_name")
    elif first["wanted"]:
        tk = _tokens(first["wanted"])
        if tk:
            for d in sorted(devs, key=lambda d: (-len(_tokens(d["name"]) & tk), rank(d))):
                if _tokens(d["name"]) & tk:
                    add(d, "similar_name")
    # the Windows default input, then anything that is not WDM-KS
    di = first["index"] if first["how"] in ("default", "default_fallback") else None
    if di is None:
        try:
            di = sd.default.device[0] if default_index is None else default_index
        except Exception:  # noqa: BLE001
            di = None
    for d in devs:
        if d["index"] == di:
            add(d, "default")
    for d in sorted(devs, key=rank):
        if rank(d) < 3 and "voicemeeter" not in d["name"].lower() and "cable" not in d["name"].lower():
            add(d, "default")
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
        self.alert = None          # {"kind": "silent"|..., "message": ...} while the mic looks dead
        self.resolver = None       # callable -> device index; used to reopen the stream when it dies
        self._last_loud = 0.0
        self._reopened = False

    def start(self, device=None):
        if self.running:
            raise RuntimeError("already listening")
        rate = SR
        err = None
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
        self.session_id = "live-" + time.strftime("%Y%m%d-%H%M%S")
        db.run("INSERT INTO sessions(id,kind,title,source_id,status,created) VALUES(?,?,?,?,?,?)",
               (self.session_id, "live", "Live mic " + time.strftime("%Y-%m-%d %H:%M"), self.session_id, "listening", time.time()))
        (cfg.LIVE_AUDIO / self.session_id).mkdir(exist_ok=True)
        self.running = True
        self._t0 = time.time()
        self._last_loud = self._t0
        self._reopened = False
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

    def _health(self, now: float, rms: float | None):
        """Watchdog: if the input stays dead-quiet (or stops delivering blocks) for SILENT_ALERT_S, raise an alert once and try one reopen.
        An alert clears as soon as real signal returns."""
        if rms is not None and rms > SILENT_RMS:
            self._last_loud = now
            if self.alert:
                self.alert = None
                self.emit({"type": "mic_alert", "alert": None})
            return
        if self.alert or now - self._last_loud < SILENT_ALERT_S:
            return
        self.alert = {"kind": "silent", "message": f"The microphone has been silent for {int(now - self._last_loud)} s. Nothing is being recorded; check the mic."}
        self.emit({"type": "mic_alert", "alert": self.alert})
        if not self._reopened and self.resolver:
            self._reopened = True
            self._reopen()

    def _reopen(self):
        try:
            old = self._stream
            if old is not None:
                try:
                    old.stop()
                    old.close()
                except Exception:  # noqa: BLE001
                    pass
            dev = self.resolver()
            self._stream = sd.InputStream(device=dev, channels=1, samplerate=self._rate, blocksize=int(self._rate * BLOCK_S), dtype="float32", callback=self._cb)
            self._stream.start()
            self._last_loud = time.time()
        except Exception as e:  # noqa: BLE001
            self.emit({"type": "error", "message": f"could not reopen the mic: {e}"})

    def _cb(self, indata, frames, t, status):
        self._blocks.put(indata[:, 0].copy())

    def _vad_loop(self):
        floor, n, silent, voiced = 0.0, 0, 0, 0
        preroll = collections.deque(maxlen=8)
        buf, active, utt_start = [], False, 0.0
        while True:
            try:
                b = self._blocks.get(timeout=2.0)
            except queue.Empty:
                self._health(time.time(), None)   # no audio blocks at all: the device is gone or hung
                continue
            if b is None:
                break
            b = _to16k(b, self._rate)
            rms = float(np.sqrt(np.mean(b * b)) + 1e-9)
            self._health(time.time(), rms)
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
