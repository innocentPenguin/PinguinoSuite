"""Whisper wrapper (faster-whisper). One shared model; a lock keeps live mic + VOD jobs from colliding on the GPU."""
import glob
import os
import sys
import threading

import numpy as np

import config as cfg
import learn


def _add_cuda_dlls():
    # pip's nvidia-cublas / nvidia-cudnn wheels ship their DLLs inside site-packages/nvidia/*/bin
    for p in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
        try:
            os.add_dll_directory(p)
        except Exception:
            pass
        os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")


_add_cuda_dlls()


SEG_MAX_S = 12.0   # a subtitle line never spans more than this many seconds
SEG_GAP_S = 0.8    # a pause this long between two words also ends a line
_END = (".", "?", "!", "…")


def split_sentences(words, max_dur=SEG_MAX_S, gap=SEG_GAP_S):
    """Cut one Whisper segment's words into sentence-sized lines: after . ? ! ..., at a pause >= gap, and (so a run-on never goes past
    max_dur) at the last comma or biggest pause before the limit. Returns a list of word lists; nothing is dropped or reordered."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            break
        if w["w"].endswith(_END) or nxt["s"] - w["e"] >= gap:
            out.append(cur); cur = []
        elif nxt["e"] - cur[0]["s"] > max_dur:   # too long: break at the best spot already seen
            cut = max(range(len(cur)), key=lambda k: ((cur[k]["w"].endswith(",")), (words[i + 1]["s"] if k == len(cur) - 1 else cur[k + 1]["s"]) - cur[k]["e"], k))
            out.append(cur[:cut + 1]); cur = cur[cut + 1:]
    if cur:
        out.append(cur)
    return out


class ASR:
    def __init__(self, on_state=lambda s, d="": None):
        self.model = None
        self.device = None
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.on_state = on_state
        self.error = None

    def load(self):
        from faster_whisper import WhisperModel
        self.on_state("loading", f"Loading {cfg.MODEL} ...")
        silence = np.zeros(16000, dtype=np.float32)
        for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
            try:
                m = WhisperModel(cfg.MODEL, device=device, compute_type=ctype)
                list(m.transcribe(silence, language="en")[0])  # surfaces missing CUDA libs now, not mid-stream
                self.model, self.device = m, device
                self.ready.set()
                self.on_state("ready", f"{cfg.MODEL} on {device}")
                return
            except Exception as e:  # noqa: BLE001
                self.error = f"{device}: {e}"
                self.on_state("loading", f"{device} failed ({e}); trying next")
        self.on_state("error", self.error or "model failed to load")

    def iter_segments(self, audio, offset=0.0):
        """Yield {start,end,words:[{w,s,e,p}],avg_logprob} for a 16k mono float32 array or file path."""
        self.ready.wait()
        lang = None if cfg.LANGUAGE == "auto" else cfg.LANGUAGE
        hot = ", ".join(learn.vocab_terms()) or None
        with self.lock:
            segs, _info = self.model.transcribe(
                audio, language=lang, word_timestamps=True, hotwords=hot, beam_size=5,
                vad_filter=True, condition_on_previous_text=False)
            it = iter(segs)
        while True:
            with self.lock:  # released between segments so live mic can cut in during a long VOD
                s = next(it, None)
            if s is None:
                return
            words = [{"w": w.word.strip(), "s": w.start + offset, "e": w.end + offset, "p": float(w.probability)}
                     for w in (s.words or []) if w.word.strip()]
            for part in split_sentences(words):
                yield {"start": part[0]["s"], "end": part[-1]["e"], "words": part, "avg_logprob": float(s.avg_logprob)}
