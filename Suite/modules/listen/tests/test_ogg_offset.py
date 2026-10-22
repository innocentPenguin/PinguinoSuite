r"""Regression: a VOD's ogg started at the source's timestamp (~62 s) while the transcript counts from 0, so clips played ~62 s away from their text.
Run: cd Suite\modules\listen ; ..\..\.venv\Scripts\python.exe -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oggfix  # noqa: E402


def tone(seconds, hz, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    return (np.sin(2 * np.pi * hz * t) * 12000).astype(np.int16)


def write_ogg(path, pcm, start_s=0.0, rate=16000):
    """An opus ogg whose audio timeline starts at start_s (how the old to_ogg wrote a VOD that began at 62 s)."""
    import av
    out = av.open(str(path), "w", format="ogg")
    st = out.add_stream("libopus", rate=rate)
    st.layout = "mono"
    n0 = int(start_s * rate)
    for i in range(0, len(pcm) - 319, 320):
        f = av.AudioFrame.from_ndarray(pcm[i:i + 320].reshape(1, -1), format="s16", layout="mono")
        f.sample_rate = rate
        f.pts = n0 + i
        f.time_base = __import__("fractions").Fraction(1, rate)
        for p in st.encode(f):
            out.mux(p)
    for p in st.encode(None):
        out.mux(p)
    out.close()


def length_s(path):
    import av
    with av.open(str(path)) as c:
        last = 0.0
        for p in c.demux(c.streams.audio[0]):
            if p.pts is not None:
                last = max(last, float((p.pts + (p.duration or 0)) * c.streams.audio[0].time_base))
        return last


class OggStart(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_the_old_bug_is_visible(self):
        f = self.d / "vod.ogg"
        write_ogg(f, tone(4, 440), start_s=62.0)
        self.assertGreater(oggfix.first_pts_s(f), 61.0)

    def test_normalize_moves_the_start_to_zero_and_keeps_every_packet(self):
        f = self.d / "vod.ogg"
        write_ogg(f, tone(4, 440), start_s=62.0)
        before = oggfix._digest(f)
        off = oggfix.normalize(f)
        self.assertAlmostEqual(off, 62.0, delta=0.1)
        self.assertLess(oggfix.first_pts_s(f), 0.1)
        self.assertEqual(oggfix._digest(f), before)           # same packets, byte for byte
        self.assertAlmostEqual(length_s(f), 4.0, delta=0.1)
        self.assertFalse(list(self.d.glob("*.fixing.ogg")))

    def test_a_healthy_file_is_left_alone(self):
        f = self.d / "clip.ogg"
        write_ogg(f, tone(2, 330))
        data = f.read_bytes()
        self.assertEqual(oggfix.normalize(f), 0.0)
        self.assertEqual(f.read_bytes(), data)

    def test_repair_all_fixes_only_offset_files(self):
        write_ogg(self.d / "a.ogg", tone(2, 440), start_s=62.0)
        write_ogg(self.d / "b.ogg", tone(2, 440))
        self.assertEqual(oggfix.repair_all(self.d, log=lambda m: None), 1)
        self.assertEqual(oggfix.repair_all(self.d, log=lambda m: None), 0)

    def test_to_ogg_no_longer_copies_the_source_start_time(self):
        import ingest
        src = self.d / "src.ogg"
        write_ogg(src, tone(4, 440), start_s=62.0)
        dst = self.d / "out.ogg"
        dur = ingest.to_ogg(src, dst)
        self.assertAlmostEqual(dur, 4.0, delta=0.1)
        self.assertLess(oggfix.first_pts_s(dst), 0.1)


if __name__ == "__main__":
    unittest.main()
