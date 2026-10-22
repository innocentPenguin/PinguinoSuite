"""Ogg/opus start-offset repair (no db / config imports, so it is cheap to test).

Root cause of "the clip does not match the subtitle": a VOD's audio was written with the SOURCE's timestamps, so the .ogg timeline started at ~62 s
(Twitch HLS streams start there) while the transcript times are sample counts from 0. The browser plays an ogg on its own timeline, so every
clip played ~62 s away from its text (and times before 62 s clamped to the start). to_ogg() now writes from 0; normalize() fixes files made before.
normalize() only shifts packet timestamps: the opus packets themselves are copied byte for byte and checked before the file is replaced.
"""
import hashlib
import os
from pathlib import Path

TOL_S = 0.5   # a normal file starts at ~0 (a few ms of opus pre-skip); anything beyond this is a source-timeline offset


def _packets(path):
    import av
    with av.open(str(path)) as c:
        s = c.streams.audio[0]
        for p in c.demux(s):
            if p.pts is not None and p.size:
                yield p, s


def first_pts_s(path):
    """Seconds at which the file's audio timeline starts (0 for a healthy file)."""
    for p, s in _packets(path):
        return float(p.pts * s.time_base)
    return 0.0


def _digest(path):
    h, n = hashlib.sha256(), 0
    for p, _ in _packets(path):
        h.update(bytes(p))
        n += 1
    return h.hexdigest(), n


def normalize(path):
    """Rewrite `path` so its timeline starts at 0. Returns the removed offset in seconds, or 0.0 when nothing was needed. Lossless; the old file is
    only replaced after the new one has the same packets (count + sha256 of the payloads) and the right length."""
    import av
    path = Path(path)
    off = first_pts_s(path)
    if abs(off) <= TOL_S:
        return 0.0
    tmp = path.with_suffix(".fixing.ogg")
    try:
        with av.open(str(path)) as src, av.open(str(tmp), "w", format="ogg") as dst:
            ss = src.streams.audio[0]
            ds = dst.add_stream_from_template(ss)
            base = None
            for p in src.demux(ss):
                if p.pts is None or not p.size:
                    continue
                if base is None:
                    base = p.pts
                p.pts -= base
                p.dts = p.pts
                p.stream = ds
                dst.mux(p)
        a, b = _digest(path), _digest(tmp)
        if a != b or abs(first_pts_s(tmp)) > TOL_S:
            raise ValueError("the rewritten file does not match the original")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return off


def repair_all(folder, log=print):
    """Fix every offset .ogg in a folder (one at a time; a file that is being played or written is skipped and retried next start)."""
    fixed = 0
    for f in sorted(Path(folder).glob("*.ogg")):
        try:
            off = normalize(f)
            if off:
                fixed += 1
                log(f"audio timeline fixed: {f.name} (was starting at {off:.1f}s)")
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the rest
            log(f"audio timeline repair skipped {f.name}: {e}")
    return fixed
