# INDEX: Audio: Sapi (PowerShell worker), Cloud (OpenAI/ElevenLabs, vault keys), numpy FX (stretch, pitch, echo, reverb, robot, radio, distortion, tremolo), stingers, render(), Player (sounddevice/winsound), devices(). Related: brain.py.
"""Speech engine: Windows SAPI (System.Speech via a resident PowerShell worker) -> numpy pitch/effects -> WAV -> winsound.

Synthesis and playback are separate: `synth()` returns WAV bytes (used by page previews, which never touch the PC speakers),
`Player` plays WAV bytes on the default output and can be stopped at once. Nothing here decides *whether* to speak; that is brain.py.
"""
import io
import json
import os
import urllib.error
import urllib.parse
import subprocess
import tempfile
import threading
import time
import wave

import numpy as np

import console_log

SR = 22050
_PS = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
[Console]::OutputEncoding=[Text.Encoding]::UTF8
[Console]::InputEncoding=[Text.Encoding]::UTF8
while (($line = [Console]::In.ReadLine()) -ne $null) {
  try {
    $j = $line | ConvertFrom-Json
    if ($j.cmd -eq 'voices') { $v = @($s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }); (@{ok=$true;voices=$v} | ConvertTo-Json -Compress); continue }
    if ($j.voice) { try { $s.SelectVoice($j.voice) } catch { } }
    $s.Rate = [int]$j.rate
    $s.Volume = 100
    $s.SetOutputToWaveFile($j.out)
    $s.Speak([string]$j.text)
    $s.SetOutputToNull()
    (@{ok=$true} | ConvertTo-Json -Compress)
  } catch { (@{ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Compress) }
}
"""


class Sapi:
    def __init__(self):
        self.p = None
        self.lock = threading.Lock()
        self.script = None
        self._voices = None

    def _start(self):
        if self.p and self.p.poll() is None:
            return
        self.script = self.script or self._write_script()
        self.p = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", self.script],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def _write_script():
        d = tempfile.mkdtemp(prefix="pinguinovoice-")
        f = os.path.join(d, "sapi.ps1")
        with open(f, "w", encoding="utf-8-sig") as fh:
            fh.write(_PS)
        return f

    def _call(self, req, timeout=40):
        with self.lock:
            for attempt in (1, 2):
                try:
                    self._start()
                    self.p.stdin.write(json.dumps(req) + "\n")
                    self.p.stdin.flush()
                    out = {}

                    def rd():
                        out["l"] = self.p.stdout.readline()
                    t = threading.Thread(target=rd, daemon=True)
                    t.start()
                    t.join(timeout)
                    if "l" not in out or not out["l"]:
                        raise RuntimeError("speech worker did not answer")
                    return json.loads(out["l"])
                except Exception as e:
                    self.close()
                    if attempt == 2:
                        return {"ok": False, "error": str(e)[:200]}

    def voices(self, refresh=False):
        if self._voices is None or refresh:
            r = self._call({"cmd": "voices"}, 25)
            self._voices = r.get("voices") or [] if r.get("ok") else []
            if isinstance(self._voices, str):
                self._voices = [self._voices]
        return self._voices

    def speak_to_wav(self, text, voice, rate):
        fd, out = tempfile.mkstemp(suffix=".wav", prefix="pv-")
        os.close(fd)
        try:
            r = self._call({"text": text, "voice": voice, "rate": int(rate), "out": out})
            if not r.get("ok"):
                raise RuntimeError(r.get("error") or "speech failed")
            with open(out, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(out)
            except OSError:
                pass

    def close(self):
        try:
            if self.p and self.p.poll() is None:
                self.p.kill()
        except Exception:
            pass
        self.p = None


sapi = Sapi()


# ------------------------------------------------------------------ cloud voices (optional; keys come from the vault, memory only)
import urllib.request

CLOUD_HOSTS = {"openai": "https://api.openai.com", "elevenlabs": "https://api.elevenlabs.io"}
KEY_NAMES = {"openai": "VOICE_OPENAI_KEY", "elevenlabs": "VOICE_ELEVENLABS_KEY"}


class Cloud:
    def __init__(self, hosts=None, key_fetch=None):
        self.hosts = dict(hosts or CLOUD_HOSTS)
        self.key_fetch = key_fetch or self._vault
        self.keys = {}
        self.tried = {}

    @staticmethod
    def _vault(name):
        core, tok = os.environ.get("PINGUINO_CORE_URL"), os.environ.get("PINGUINO_API_TOKEN")
        if not core or not tok:
            return None
        try:
            req = urllib.request.Request(core.rstrip("/") + "/api/vault/" + name, headers={"Authorization": "Bearer " + tok})
            with urllib.request.urlopen(req, timeout=5) as r:
                return str(json.loads(r.read()).get("value") or "") or None
        except Exception:
            return None

    def key(self, eng, force=False):
        k = self.keys.get(eng)
        if k and not force:
            return k
        if time.time() - self.tried.get(eng, 0) < (1 if force else 30):
            return self.keys.get(eng)
        self.tried[eng] = time.time()
        k = self.key_fetch(KEY_NAMES[eng])
        if k:
            self.keys[eng] = k
        return k

    def has_key(self, eng):
        return bool(self.key(eng))

    def _post(self, url, body, headers, timeout=30):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def synth(self, eng, text, voice, cfg_cloud, style="", rate=0):
        """-> WAV bytes. Raises RuntimeError with a short, key-free reason."""
        key = self.key(eng)
        if not key:
            raise RuntimeError("no " + KEY_NAMES[eng] + " in the vault")
        base = self.hosts[eng]
        try:
            if eng == "openai":
                body = {"model": cfg_cloud.get("openai_model") or "gpt-4o-mini-tts", "input": text, "voice": voice or "alloy", "response_format": "wav"}
                if style and "mini-tts" in body["model"]:
                    body["instructions"] = style
                else:
                    body["speed"] = max(0.25, min(4.0, 1.0 + rate * 0.06))
                return self._post(base + "/v1/audio/speech", body, {"Authorization": "Bearer " + key})
            vid = urllib.parse.quote(voice or "21m00Tcm4TlvDq8ikWAM")
            body = {"text": text, "model_id": cfg_cloud.get("elevenlabs_model") or "eleven_turbo_v2_5",
                    "voice_settings": {"stability": cfg_cloud.get("stability", 50) / 100.0, "similarity_boost": 0.75}}
            pcm = self._post(base + "/v1/text-to-speech/" + vid + "?output_format=pcm_22050", body, {"xi-api-key": key})
            bio = io.BytesIO()
            with wave.open(bio, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(pcm)
            return bio.getvalue()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self.keys.pop(eng, None)
            raise RuntimeError(eng + " answered HTTP " + str(e.code) + (" (key rejected)" if e.code in (401, 403) else ""))
        except Exception as e:
            raise RuntimeError(eng + " unreachable: " + type(e).__name__)

    def test(self, eng):
        key = self.key(eng, force=True)
        if not key:
            return {"ok": False, "error": "no " + KEY_NAMES[eng] + " in the vault"}
        url, hdr = ((self.hosts[eng] + "/v1/models", {"Authorization": "Bearer " + key}) if eng == "openai" else (self.hosts[eng] + "/v1/user", {"xi-api-key": key}))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=10) as r:
                return {"ok": r.status == 200}
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": "HTTP " + str(e.code) + (" (key rejected)" if e.code in (401, 403) else "")}
        except Exception as e:
            return {"ok": False, "error": "unreachable: " + type(e).__name__}


cloud = Cloud()


# ------------------------------------------------------------------ audio helpers
def wav_to_np(b):
    with wave.open(io.BytesIO(b)) as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.uint8).astype(np.float32)
    if sw == 1:
        a = (a - 128) * 256
    a /= 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def np_to_wav(a, sr=SR):
    a = np.clip(a, -1, 1)
    pcm = (a * 32767).astype("<i2").tobytes()
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return bio.getvalue()


def resample(a, ratio):
    """ratio > 1 = faster/higher (fewer samples)."""
    if abs(ratio - 1) < 1e-4 or len(a) < 8:
        return a
    n = int(len(a) / ratio)
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


def stretch(a, factor, win=1024):
    """Overlap-add time stretch: factor > 1 = longer, pitch unchanged (enough for speech)."""
    if abs(factor - 1) < 1e-3 or len(a) < win * 3:
        return a
    hop_out = win // 2
    hop_in = max(1, int(hop_out / factor))
    w = np.hanning(win).astype(np.float32)
    nfr = max(1, (len(a) - win) // hop_in)
    out = np.zeros(nfr * hop_out + win, dtype=np.float32)
    norm = np.zeros_like(out)
    for i in range(nfr):
        seg = a[i * hop_in:i * hop_in + win]
        if len(seg) < win:
            break
        out[i * hop_out:i * hop_out + win] += seg * w
        norm[i * hop_out:i * hop_out + win] += w
    norm[norm < 1e-3] = 1
    return out / norm


def pitch_shift(a, semitones):
    if not semitones:
        return a
    ratio = 2 ** (semitones / 12.0)
    return stretch(resample(a, ratio), ratio)


def fx_echo(a, sr, amt):
    d = int(sr * 0.22)
    out = np.concatenate([a, np.zeros(d * 3, dtype=np.float32)])
    for k, g in ((1, 0.5), (2, 0.28), (3, 0.14)):
        out[k * d:k * d + len(a)] += a * g * amt
    return out


def fx_reverb(a, sr, amt):
    out = np.concatenate([a, np.zeros(int(sr * 0.5), dtype=np.float32)])
    for ms, g in ((29, .35), (37, .3), (53, .25), (71, .2), (97, .15), (131, .1)):
        d = int(sr * ms / 1000)
        out[d:d + len(a)] += a * g * amt
    return out


def fx_robot(a, sr, amt):
    t = np.arange(len(a)) / sr
    mod = np.sin(2 * np.pi * 55 * t).astype(np.float32)
    return a * (1 - amt) + (a * mod) * amt * 1.4


def fx_radio(a, sr, amt):
    spec = np.fft.rfft(a)
    f = np.fft.rfftfreq(len(a), 1 / sr)
    band = ((f > 300) & (f < 3200)).astype(np.float32)
    spec = spec * (1 - amt + band * amt)
    y = np.fft.irfft(spec, len(a)).astype(np.float32)
    y = np.tanh(y * (1 + amt * 2.5)) * 0.9
    return y


def fx_distortion(a, sr, amt):
    return np.tanh(a * (1 + amt * 8)) / (1 + amt * 0.6)


def fx_tremolo(a, sr, amt):
    t = np.arange(len(a)) / sr
    return a * (1 - amt * 0.5 * (1 + np.sin(2 * np.pi * 7 * t))).astype(np.float32)


FX = {"echo": fx_echo, "reverb": fx_reverb, "robot": fx_robot, "radio": fx_radio, "distortion": fx_distortion, "tremolo": fx_tremolo}
FX_ORDER = ["robot", "radio", "distortion", "tremolo", "echo", "reverb"]


def load_sound(name, sound_dir):
    """A user WAV from the sounds folder (file name only, no paths). Silence when missing or unreadable."""
    try:
        f = os.path.join(str(sound_dir), os.path.basename(name))
        if not sound_dir or not f.lower().endswith(".wav") or os.path.getsize(f) > 2_000_000:
            return np.zeros(0, dtype=np.float32)
        with open(f, "rb") as fh:
            a, sr = wav_to_np(fh.read())
        return (resample(a, sr / SR) if sr != SR else a)[:SR * 8]
    except Exception:
        return np.zeros(0, dtype=np.float32)


def stinger(name, sr=SR):
    def tone(f, d, v=0.5, kind="sine"):
        t = np.arange(int(sr * d)) / sr
        w = np.sin(2 * np.pi * f * t) if kind == "sine" else np.sign(np.sin(2 * np.pi * f * t))
        env = np.minimum(1, t * 80) * np.exp(-t * (4 / d))
        return (w * env * v).astype(np.float32)
    sil = lambda d: np.zeros(int(sr * d), dtype=np.float32)
    if name == "ding":
        return np.concatenate([tone(1175, 0.5, .5), sil(0.05)])
    if name == "bloop":
        return np.concatenate([tone(300, 0.08), tone(520, 0.12), sil(0.05)])
    if name == "fanfare":
        return np.concatenate([tone(523, .12), tone(659, .12), tone(784, .12), tone(1047, .4), sil(.05)])
    if name == "airhorn":
        return np.concatenate([tone(440, .35, .35, "sq") + tone(554, .35, .25, "sq"), sil(.05)])
    if name == "sparkle":
        return np.concatenate([tone(1568, .08, .3), tone(2093, .08, .3), tone(2637, .25, .3), sil(.05)])
    if name == "drumroll":
        n = np.random.default_rng(1).standard_normal(int(sr * .6)).astype(np.float32)
        env = np.linspace(.05, .5, len(n)) * (0.5 + 0.5 * np.sin(np.arange(len(n)) / sr * 90))
        return np.concatenate([n * env * .5, tone(220, .25, .5), sil(.05)])
    if name == "sad":
        return np.concatenate([tone(392, .25, .4), tone(370, .25, .4), tone(349, .5, .4), sil(.05)])
    return np.zeros(0, dtype=np.float32)


def render(text, persona, volume=100, extra_gain=1.0, sting="none", sapi_obj=None, output_volume=100, normalize=True, whisper=False, cloud_obj=None, cloud_cfg=None, sound_dir=None):
    """Persona + text -> (wav bytes, seconds). Raises RuntimeError when the engine is unavailable.
    Cloud personas are used only when cloud_cfg["allow"] is true; on failure they fall back to the Windows voice when cloud_cfg["fallback"]."""
    sp = sapi_obj or sapi
    eng, cc, raw = persona.get("engine", "sapi"), cloud_cfg or {}, None
    if eng in KEY_NAMES and cc.get("allow"):
        try:
            raw = (cloud_obj or cloud).synth(eng, text, persona.get("cloud_voice"), cc, persona.get("style", ""), persona.get("rate", 0))
        except RuntimeError as e:
            console_log.warn("cloud", str(e), dedupe_s=120)
            if not cc.get("fallback", True):
                raise
    if raw is None:
        raw = sp.speak_to_wav(text, persona.get("voice") or "", persona.get("rate", 0))
        eng = "sapi"
    a, sr = wav_to_np(raw)
    if sr != SR:
        a = resample(a, sr / SR)
    if eng == "elevenlabs" and persona.get("rate"):
        a = stretch(a, 1.0 - persona["rate"] * 0.05)
    a = pitch_shift(a, persona.get("pitch", 0))
    eff = persona.get("effects", {})
    for k in FX_ORDER:
        amt = eff.get(k, 0) / 100.0
        if amt > 0:
            a = FX[k](a, SR, amt)
    if normalize and len(a):
        peak = float(np.max(np.abs(a))) or 1.0
        a = a / peak * 0.8
    a = a * (persona.get("volume", 100) / 100.0) * (output_volume / 100.0) * extra_gain * (0.25 if whisper else 1.0)
    st = load_sound(sting[5:], sound_dir) if sting.startswith("file:") else stinger(sting)
    if len(st):
        st = st * (output_volume / 100.0) * extra_gain * (0.25 if whisper else 1.0)
        a = np.concatenate([st, a])
    return np_to_wav(a), len(a) / SR


class Player:
    """One thing at a time on the default Windows output; stop() cuts it immediately."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.playing_until = 0.0
        self.stopped = threading.Event()
        try:
            import winsound
            self.ws = winsound
        except ImportError:
            self.ws = None
        self._tmp = None

    def play(self, wav, seconds, device=""):
        """Blocks until finished or stopped. Returns True when played to the end. `device` = part of an output device name, empty = Windows default."""
        self.stopped.clear()
        if not (self.enabled and self.ws):
            return True
        if device:
            dev = find_device(device)
            if dev is not None:
                return self._play_sd(wav, seconds, dev)
            console_log.warn("output", "output device '" + device[:40] + "' not found, using the default", dedupe_s=300)
        with self.lock:
            fd, f = tempfile.mkstemp(suffix=".wav", prefix="pvp-")
            os.close(fd)
            open(f, "wb").write(wav)
            try:
                self.playing_until = time.time() + seconds
                self.ws.PlaySound(f, self.ws.SND_FILENAME | self.ws.SND_ASYNC)
                end = time.time() + seconds + 0.15
                while time.time() < end:
                    if self.stopped.wait(0.05):
                        self.ws.PlaySound(None, self.ws.SND_PURGE)
                        return False
                return True
            finally:
                self.playing_until = 0.0
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def _play_sd(self, wav, seconds, dev):
        import sounddevice as sd
        a, sr = wav_to_np(wav)
        with self.lock:
            try:
                self.playing_until = time.time() + seconds
                sd.play(a, sr, device=dev)
                end = time.time() + seconds + 0.2
                while time.time() < end:
                    if self.stopped.wait(0.05):
                        sd.stop()
                        return False
                sd.wait()
                return True
            finally:
                self.playing_until = 0.0

    def stop(self):
        self.stopped.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        if self.ws and self.enabled:
            try:
                self.ws.PlaySound(None, self.ws.SND_PURGE)
            except Exception:
                pass

    @property
    def busy(self):
        return time.time() < self.playing_until


def devices():
    """Output devices as [{index, name}] (empty list when sounddevice is unavailable)."""
    try:
        import sounddevice as sd
        out, seen = [], set()
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0 and d["name"] not in seen:
                seen.add(d["name"])
                out.append({"index": i, "name": d["name"]})
        return out
    except Exception:
        return []


def find_device(part):
    part = (part or "").lower()
    for d in devices():
        if part and part in d["name"].lower():
            return d["index"]
    return None
