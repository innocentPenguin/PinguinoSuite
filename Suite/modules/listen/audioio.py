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


def peaks(path, start, end, n=120):
    """n loudness bars (0..1, relative to the loudest bar) for path between start and end seconds; decodes only that window."""
    import av
    import numpy as np
    n = max(8, min(400, int(n)))
    start = max(0.0, float(start))
    end = max(start + 0.05, float(end))
    chunks, t0 = [], None
    with av.open(str(path)) as c:
        st = next(s for s in c.streams if s.type == "audio")
        if start > 1:
            try:
                c.seek(int((start - 0.5) * 1_000_000))
            except Exception:
                pass
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in c.decode(st):
            ft = float(frame.time) if frame.time is not None else 0.0
            if ft > end:
                break
            for f in rs.resample(frame):
                a = f.to_ndarray().reshape(-1)
                if t0 is None:
                    t0 = ft
                chunks.append(a)
    if not chunks:
        return [0.0] * n
    x = np.abs(np.concatenate(chunks).astype(np.float32)) / 32768.0
    i0 = max(0, int((start - t0) * 16000))
    i1 = max(i0 + 1, int((end - t0) * 16000))
    x = x[i0:i1]
    if len(x) == 0:
        return [0.0] * n
    edges = np.linspace(0, len(x), n + 1).astype(int)
    out = np.array([x[a:max(b, a + 1)].max() if a < len(x) else 0.0 for a, b in zip(edges[:-1], edges[1:])])
    m = float(out.max())
    return [round(float(v / m), 3) if m > 0 else 0.0 for v in out]
