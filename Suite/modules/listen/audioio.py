"""Bounded-memory audio decoding (no db / config imports, so it is cheap to test)."""


def iter16k(path, chunk_s=900):
    """Yield (offset_seconds, float32 mono 16 kHz array) slices of at most chunk_s seconds.

    A 6-hour VOD is ~1.4 GB as float32; the old load-everything path peaked at several times that
    (int16 list + concatenate + float32 + /32768) and could take the whole Listen process down.
    This keeps one slice (~58 MB for 15 min) in memory at a time.
    """
    import av
    import numpy as np
    per = int(chunk_s * 16000)
    buf, have, done = [], 0, 0

    def flush(n):
        nonlocal buf, have, done
        joined = np.concatenate(buf)
        out, rest = joined[:n], joined[n:]
        buf = [rest] if len(rest) else []
        have = len(rest)
        off = done / 16000
        done += len(out)
        return off, out.astype(np.float32) / 32768.0

    with av.open(str(path)) as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in c.decode(next(s for s in c.streams if s.type == "audio")):
            for f in rs.resample(frame):
                a = f.to_ndarray().reshape(-1)
                buf.append(a)
                have += len(a)
                while have >= per:
                    yield flush(per)
    if have:
        yield flush(have)
