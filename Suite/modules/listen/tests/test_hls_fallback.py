import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ingest  # noqa: E402


class Fake:
    calls = []
    fail_on = ()

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        Fake.calls.append(self.opts["format"])
        if len(Fake.calls) in Fake.fail_on:
            raise Exception("ERROR: m3u8 download detected but ffmpeg could not be found")


class HlsFallback(unittest.TestCase):
    def run_dl(self, fail_on):
        Fake.calls, Fake.fail_on = [], fail_on
        mod = types.SimpleNamespace(YoutubeDL=Fake)
        d = ingest.Jobs.__new__(ingest.Jobs)
        with mock.patch.dict(sys.modules, {"yt_dlp": mod}), \
             mock.patch.object(ingest, "finished_source", side_effect=[None, Path("x.mp4")]), \
             mock.patch.object(ingest, "sources_bytes", return_value=0):
            return d._download("s", "http://v", "stem")

    def test_markers(self):
        self.assertTrue(ingest.needs_ffmpeg(Exception("Initialization fragment found after media fragments, x")))
        self.assertFalse(ingest.needs_ffmpeg(Exception("HTTP 403")))

    def test_retry_once_non_hls(self):
        self.assertEqual(self.run_dl({1}), Path("x.mp4"))
        self.assertEqual(len(Fake.calls), 2)
        self.assertEqual(Fake.calls[1], ingest.NON_HLS_FORMAT)

    def test_no_loop_when_retry_fails(self):
        with self.assertRaises(RuntimeError):
            self.run_dl({1, 2})
        self.assertEqual(len(Fake.calls), 2)


if __name__ == "__main__":
    unittest.main()
