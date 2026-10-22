"""Sentence-level subtitle lines: split_sentences cuts one Whisper segment at . ? ! pauses and run-ons, losing nothing."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asr  # noqa: E402


def W(text, start, dur=0.3):
    out, t = [], start
    for w in text.split():
        out.append({"w": w, "s": t, "e": t + dur, "p": 0.9})
        t += dur + 0.05
    return out


class Split(unittest.TestCase):
    def test_sentence_ends(self):
        ws = W("Hello chat. How are you? Fine!", 0)
        got = [" ".join(w["w"] for w in p) for p in asr.split_sentences(ws)]
        self.assertEqual(got, ["Hello chat.", "How are you?", "Fine!"])

    def test_pause_splits(self):
        a, b = W("so we go", 0), W("and then", 5)
        self.assertEqual([len(p) for p in asr.split_sentences(a + b)], [3, 2])

    def test_runon_is_cut_at_a_comma_and_nothing_is_lost(self):
        ws = W("one two three four five six, seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen", 0)
        parts = asr.split_sentences(ws, max_dur=5)
        self.assertGreater(len(parts), 1)
        self.assertEqual([w for p in parts for w in p], ws)
        self.assertTrue(parts[0][-1]["w"].endswith(","))
        for p in parts[:-1]:
            self.assertLessEqual(p[-1]["e"] - p[0]["s"], 5.5)

    def test_short_and_empty(self):
        self.assertEqual(asr.split_sentences([]), [])
        ws = W("ok", 0)
        self.assertEqual(asr.split_sentences(ws), [ws])


if __name__ == "__main__":
    unittest.main()
