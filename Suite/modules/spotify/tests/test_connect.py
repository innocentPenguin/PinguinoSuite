"""Unit tests for connect.py (go-librespot child manager). No process, no network: popen/http/clock are injected."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp(prefix="spotify-connect-test-"))

import connect  # noqa: E402
from connect import Connect, find_binary, write_config  # noqa: E402


class FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid
        self.rc = None
        self.stdout = iter(())
        self.terminated = self.killed = False

    def poll(self):
        return self.rc

    def terminate(self):
        self.terminated = True
        self.rc = 0

    def kill(self):
        self.killed = True
        self.rc = -9


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Rig:
    """A Connect with everything injected."""

    def __init__(self):
        self.clock = Clock()
        self.procs, self.cmds, self.posts = [], [], []
        self.auth = {"status": 200, "body": {}}
        self.status = {"status": 200, "body": {}}
        self.post_status = 200
        self.stale = []
        self.exe = Path(tempfile.mkdtemp(prefix="fake-bin-")) / "go-librespot.exe"
        self.exe.write_text("x")
        self.c = Connect(popen=self.popen, http=self.http, clock=self.clock, binary=self.exe, outputs_fn=lambda: ["Speakers", "CABLE Input"],
                         kill_stale=lambda pid, *a: self.stale.append(pid) or True)
        self.c.folder().joinpath("pid").unlink(missing_ok=True)

    def popen(self, cmd, cwd):
        self.cmds.append(cmd)
        p = FakeProc(pid=1000 + len(self.procs))
        self.procs.append(p)
        return p

    def http(self, method, url, body=None, timeout=2.5):
        if method == "POST":
            self.posts.append((url.split("3678")[-1] if "3678" in url else url.rsplit(":", 1)[-1].split("/", 1)[-1], body))
            return self.post_status, {}
        if url.endswith("/auth/code"):
            return self.auth["status"], self.auth["body"]
        if url.endswith("/status"):
            return self.status["status"], self.status["body"]
        return 404, {}

    def on(self, **kw):
        s = {"connect_on": True, "connect_output": "", "connect_port": 3678, "connect_bitrate": 160, "connect_normalize": True, "player_volume": 70}
        s.update(kw)
        self.c.apply(s)

    def step(self, secs=4):
        self.clock.t += secs
        self.c.tick()


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.r = Rig()

    def tearDown(self):
        self.r.c.stop()

    def test_disabled_never_spawns(self):
        self.r.on(connect_on=False)
        for _ in range(5):
            self.r.step()
        self.assertEqual(self.r.procs, [])
        self.assertEqual(self.r.c.state, "off")
        self.assertEqual(self.r.c.ready_device(), "")

    def test_binary_missing_is_error_and_no_spawn(self):
        c = Connect(popen=self.r.popen, http=self.r.http, clock=self.r.clock, binary=Path(tempfile.gettempdir()) / "nope-go-librespot.exe")
        c.apply({"connect_on": True})
        c.tick()
        self.assertEqual(c.state, "error")
        self.assertIn("not installed", c.last_error)
        self.assertFalse(c.info()["installed"])
        self.assertEqual(self.r.procs, [])

    def test_spawn_uses_double_dash_config_dir_and_writes_config(self):
        self.r.on(connect_output="CABLE Input (VB-Audio Virtual Cable)")
        self.r.step()
        cmd = self.r.cmds[0]
        self.assertEqual(cmd[1], "--config_dir")
        cfg = (Path(cmd[2]) / "config.yml").read_text(encoding="utf-8")
        self.assertIn('device_name: "PinguinoSuite"', cfg)
        self.assertIn('audio_device: "CABLE Input (VB-Audio Virtual Cable)"', cfg)
        self.assertIn("port: 3678", cfg)
        self.assertNotIn("password", cfg.lower())
        self.assertEqual(Path(cmd[2]).name, "connect")
        self.assertEqual(Path(cmd[2]).parent, connect.store.folder())

    def test_login_code_then_ready_without_restarts(self):
        self.r.on()
        self.r.step()
        self.assertEqual(self.r.c.state, "starting")
        self.r.auth["body"] = {"code": "ABCD-1234", "url": "https://www.spotify.com/pair"}
        self.r.step()
        info = self.r.c.info()
        self.assertEqual((info["state"], info["code"]), ("waiting_login", "ABCD-1234"))
        for _ in range(10):
            self.r.step()
        self.assertEqual(len(self.r.procs), 1, "waiting for the user is not a crash")
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        self.assertEqual(self.r.c.state, "ready")
        self.assertEqual(self.r.c.ready_device(), "libre1")
        self.assertEqual(self.r.c.info()["code"], "")

    def test_ready_applies_output_and_volume(self):
        self.r.on(connect_output="CABLE Input", player_volume=33)
        self.r.step()
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        paths = [p for p, _ in self.r.posts]
        self.assertTrue(any("player/output" in p for p in paths), paths)
        self.assertIn(("player/volume", {"volume": 33}), [(p.split("/", 1)[-1] if p.startswith("/") else p, b) for p, b in self.r.posts] or [])
        self.assertEqual(self.r.c.info()["output_applied"], "CABLE Input")

    def test_output_failure_gives_volume_mixer_hint(self):
        self.r.on(connect_output="Nope")
        self.r.step()
        self.r.post_status = 500
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        self.assertEqual(self.r.c.info()["output_applied"], "")
        self.assertIn("Volume mixer", self.r.c.info()["output_note"]) if sys.platform.startswith("win") else self.assertTrue(self.r.c.info()["output_note"])

    def test_log_line_with_output_error_sets_note(self):
        self.r.on(connect_output="Ghost")
        self.r.step()
        self.r.c.feed("level=error msg=\"wasapi device not found\"")
        self.assertTrue(self.r.c.info()["output_note"])

    def test_volume_goes_to_child_only_when_ready(self):
        self.r.on()
        self.r.step()
        self.assertFalse(self.r.c.set_volume(40))
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        self.r.posts.clear()
        self.assertTrue(self.r.c.set_volume(40))
        self.assertTrue(any(b == {"volume": 40} for _, b in self.r.posts))
        self.assertFalse(self.r.c.set_volume(40) is False)

    def test_crash_backoff_then_give_up_then_manual_restart(self):
        self.r.on()
        self.r.step()
        delays = []
        for n in range(len(connect.BACKOFF_S) + 1):
            self.r.procs[-1].rc = 1
            before = self.r.clock.t
            self.r.c.tick()
            if self.r.c.state == "error" and "restarting in" in self.r.c.last_error:
                delays.append(self.r.c._next_start - before)
                self.r.step(connect.BACKOFF_S[n] + 0.1)
        self.assertEqual(delays, list(connect.BACKOFF_S))
        self.assertEqual(len(self.r.procs), len(connect.BACKOFF_S) + 1)
        self.assertIn("gave up", self.r.c.last_error)
        n = len(self.r.procs)
        for _ in range(5):
            self.r.step(100)
        self.assertEqual(len(self.r.procs), n, "no more automatic starts after giving up")
        self.assertTrue(self.r.c.restart())
        self.assertEqual(len(self.r.procs), n + 1)

    def test_stop_terminates_child_and_clears_pid(self):
        self.r.on()
        self.r.step()
        pid_file = self.r.c.folder() / "pid"
        self.assertTrue(pid_file.exists())
        self.r.on(connect_on=False)
        self.assertTrue(self.r.procs[0].terminated)
        self.assertEqual(self.r.c.state, "off")
        self.assertFalse(pid_file.exists())

    def test_stale_pid_is_cleaned_before_start(self):
        (self.r.c.folder() / "pid").write_text("777\n1000.0\nx")
        self.r.on()
        self.r.step()
        self.assertEqual(self.r.stale, [777])

    def test_port_or_bitrate_change_restarts_output_change_does_not(self):
        self.r.on()
        self.r.step()
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        self.r.on(connect_output="Speakers")
        self.assertEqual(len(self.r.procs), 1)
        self.assertEqual(self.r.c.info()["output_applied"], "Speakers")
        self.r.on(connect_output="Speakers", connect_bitrate=320)
        self.assertEqual(len(self.r.procs), 2)
        self.assertTrue(self.r.procs[0].terminated)

    def test_api_going_silent_drops_ready(self):
        self.r.on()
        self.r.step()
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        self.assertEqual(self.r.c.ready_device(), "libre1")
        self.r.status["status"] = 0
        self.r.step()
        self.assertEqual(self.r.c.ready_device(), "libre1")      # one slow poll is not "gone"
        self.r.step()
        self.r.step()
        self.assertEqual(self.r.c.ready_device(), "")

    def test_bad_credentials_line_switches_to_interactive_login(self):
        self.r.on()
        self.r.step()
        self.r.c.feed("level=fatal msg=\"invalid credentials type device_auth\"")
        self.assertEqual(self.r.c.cred, "interactive")
        self.r.c.restart()
        cfg = (Path(self.r.cmds[-1][2]) / "config.yml").read_text(encoding="utf-8")
        self.assertIn("type: interactive", cfg)

    def test_login_link_is_shown_but_not_logged(self):
        self.r.on()
        self.r.step()
        self.r.c.feed("please visit the following link to authorize: https://accounts.spotify.com/authorize?state=SECRETCHALLENGE")
        self.r.auth["body"] = {"url": self.r.c.code_url}
        self.r.step()
        info = self.r.c.info()
        self.assertEqual(info["state"], "waiting_login")
        self.assertTrue(info["code_url"].startswith("https://accounts.spotify.com/authorize"))
        self.assertNotIn("SECRETCHALLENGE", json.dumps(info["log"]))

    def test_info_has_no_tokens(self):
        self.r.on()
        self.r.step()
        self.r.auth["body"] = {"code": "ABCD-1234", "url": "https://www.spotify.com/pair", "access_token": "TOKEN123"}
        self.r.step()
        self.assertNotIn("TOKEN123", json.dumps(self.r.c.info()))

    def test_outputs_cached_and_listed(self):
        self.assertEqual(self.r.c.outputs(), ["Speakers", "CABLE Input"])


class ReviewFixTests(unittest.TestCase):
    """53's review of Connect."""

    def setUp(self):
        self.r = Rig()

    def ready(self, **kw):
        self.r.on(**kw)
        self.r.step()
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()

    def test_login_link_only_while_waiting_login(self):
        self.r.on()
        self.r.step()
        self.r.c.feed("please visit the following link https://accounts.spotify.com/authorize?x=1")
        self.assertEqual(self.r.c.info()["code_url"], "")           # starting: hidden
        self.r.auth["body"] = {"url": "https://accounts.spotify.com/authorize?x=1", "code": "AB-12"}
        self.r.step()
        self.assertEqual(self.r.c.info()["state"], "waiting_login")
        self.assertTrue(self.r.c.info()["code_url"].startswith("https://"))
        self.r.status["body"] = {"device_id": "libre1"}
        self.r.step()
        self.assertEqual(self.r.c.info()["code_url"], "")

    def test_username_masked_in_log(self):
        self.r.on()
        self.r.step()
        self.r.c.feed("msg=\"authenticated as bob_the_user\"")
        self.assertNotIn("bob_the_user", " ".join(self.r.c.info()["log"]))

    def test_one_failed_poll_keeps_ready_three_drop_it(self):
        self.ready()
        self.r.status["status"] = 0
        self.r.step()
        self.r.step()
        self.assertEqual(self.r.c.ready_device(), "libre1")
        self.r.status["status"] = 200
        self.r.step()                                               # recovered: counter resets
        self.r.status["status"] = 0
        self.r.step()
        self.r.step()
        self.assertEqual(self.r.c.ready_device(), "libre1")
        self.r.step()
        self.assertEqual(self.r.c.ready_device(), "")

    def test_spawn_failure_backs_off_and_gives_up(self):
        def boom(cmd, cwd):
            self.r.cmds.append(cmd)
            raise OSError("blocked")
        self.r.c.popen = boom
        self.r.on()
        n = len(self.r.cmds)
        self.assertEqual(n, 0)
        self.r.c.start()
        self.assertEqual(len(self.r.cmds), 1)
        for _ in range(5):                                          # same second: no retry storm
            self.r.c.tick()
        self.assertEqual(len(self.r.cmds), 1)
        for _ in range(40):
            self.r.step(30)
        self.assertEqual(len(self.r.cmds), 6)                       # 1 + 5 retries, then it stops
        self.assertEqual(self.r.c.state, "error")
        self.assertIn("gave up", self.r.c.info()["last_error"])

    def test_config_change_while_waiting_login_does_not_restart(self):
        self.r.on()
        self.r.step()
        self.r.auth["body"] = {"url": "https://x/y", "code": "AB-12"}
        self.r.step()
        self.r.on(connect_bitrate=320)
        self.assertEqual(len(self.r.procs), 1)
        self.assertFalse(self.r.procs[0].terminated)

    def test_garbage_port_does_not_raise(self):
        self.r.on(connect_port="abc")
        self.assertEqual(self.r.c.want["port"], 3678)

    def test_stale_reader_lines_ignored(self):
        self.r.on()
        self.r.step()
        old = self.r.procs[0]
        self.r.c.restart()
        self.r.c.feed("invalid credentials type device_auth", old)
        self.assertEqual(self.r.c.cred, "device_auth")

    def test_harmless_audio_cache_line_sets_no_output_note(self):
        self.r.on(connect_output="CABLE Input")
        self.r.step()
        self.r.c.feed("failed to load audio cache entry")
        self.assertEqual(self.r.c.info()["output_note"], "")
        self.r.c.feed("wasapi device CABLE Input not found")
        self.assertNotEqual(self.r.c.info()["output_note"], "")

    def test_empty_output_does_not_post_and_says_restart(self):
        self.ready(connect_output="CABLE Input")
        self.r.posts.clear()
        self.r.on(connect_output="")
        self.assertFalse([p for p in self.r.posts if "output" in p[0]])
        self.assertIn("Restart", self.r.c.info()["output_note"])

    def test_output_missing_flag(self):
        self.r.c.outputs()
        self.r.on(connect_output="Unplugged USB")
        self.assertTrue(self.r.c.info()["output_missing"])
        self.r.on(connect_output="Speakers")
        self.assertFalse(self.r.c.info()["output_missing"])

    def test_info_does_not_block_while_http_hangs(self):
        import threading
        gate = threading.Event()
        orig = self.r.c.http

        def slow(method, url, body=None, timeout=2.5):
            gate.wait(3)
            return orig(method, url, body, timeout)
        self.r.on()
        self.r.step()
        self.r.c.http = slow
        t = threading.Thread(target=lambda: self.r.step(), daemon=True)
        t.start()
        time.sleep(0.3)
        t0 = time.time()
        self.r.c.info()
        self.r.c.ready_device()
        self.assertLess(time.time() - t0, 0.5)
        gate.set()
        t.join(5)

    def test_stale_kill_gets_pid_start_and_binary(self):
        got = []
        self.r.c._kill_stale = lambda *a: got.append(a) or True
        (self.r.c.folder() / "pid").write_text("55\n123.5\nC:/x/go-librespot.exe")
        self.r.c.cleanup_stale()
        self.assertEqual(got, [(55, 123.5, "C:/x/go-librespot.exe")])
        self.assertFalse((self.r.c.folder() / "pid").exists())

    def test_old_style_pid_file_is_not_killed(self):
        got = []
        self.r.c._kill_stale = lambda *a: got.append(a) or True
        (self.r.c.folder() / "pid").write_text("55")
        self.r.c.cleanup_stale()
        self.assertEqual(got, [])


class ConfigAndBinaryTests(unittest.TestCase):
    def test_backend_per_platform(self):
        self.assertEqual(connect.backend_for("win"), "wasapi")
        self.assertEqual(connect.backend_for("mac"), "audio-toolbox")
        self.assertEqual(connect.backend_for("linux"), "alsa")

    def test_write_config_mac_and_clamps(self):
        p = Path(tempfile.mkdtemp()) / "config.yml"
        write_config(p, 4000, 250, "", 200, False, platform="mac")
        s = p.read_text(encoding="utf-8")
        self.assertIn("audio_backend: audio-toolbox", s)
        self.assertNotIn("audio_device", s)
        self.assertIn("initial_volume: 100", s)
        self.assertIn("bitrate: 160", s)
        self.assertIn("normalisation_disabled: true", s)

    def test_output_name_is_quoted(self):
        p = Path(tempfile.mkdtemp()) / "config.yml"
        write_config(p, 3678, 50, 'Weird "name": x', platform="win")
        self.assertIn('audio_device: "Weird \\"name\\": x"', p.read_text(encoding="utf-8"))

    def test_find_binary_both_layouts(self):
        old = os.environ.pop("SPOTIFY_CONNECT_BIN", None)
        try:
            base = Path(tempfile.mkdtemp())
            self.assertIsNone(find_binary(base, "win"))
            (base / "go-librespot.exe").write_text("x")
            self.assertEqual(find_binary(base, "win"), base / "go-librespot.exe")
            (base / "win").mkdir()
            (base / "win" / "go-librespot.exe").write_text("x")
            self.assertEqual(find_binary(base, "win"), base / "win" / "go-librespot.exe")
            (base / "mac").mkdir()
            (base / "mac" / "go-librespot").write_text("x")
            self.assertEqual(find_binary(base, "mac"), base / "mac" / "go-librespot")
        finally:
            if old is not None:
                os.environ["SPOTIFY_CONNECT_BIN"] = old


if __name__ == "__main__":
    unittest.main()


class LiveHookAuthTests(unittest.TestCase):
    """The Host pings /api/live/auto + /api/live/stop with no Origin; a token mismatch (401 at every go-live) must not stop it."""

    def _guard(self, path, headers):
        import server
        sent = []
        h = type("H", (), {"headers": headers, "_send": lambda self, *a, **k: sent.append(a[0])})()
        old = os.environ.get("PINGUINO_API_TOKEN")
        os.environ["PINGUINO_API_TOKEN"] = "x" * 8
        try:
            ok = server.H._guard(h, "POST", path)
        finally:
            if old is None:
                os.environ.pop("PINGUINO_API_TOKEN", None)
            else:
                os.environ["PINGUINO_API_TOKEN"] = old
        return ok, sent

    def test_live_hooks_open_to_local_no_origin_callers_only(self):
        for path in ("/api/live/auto", "/api/live/stop"):
            self.assertTrue(self._guard(path, {"host": "127.0.0.1:8771"})[0], path)
            ok, sent = self._guard(path, {"host": "127.0.0.1:8771", "origin": "http://evil.com"})
            self.assertFalse(ok)
            self.assertEqual(sent, [403])
        ok, sent = self._guard("/api/settings", {"host": "127.0.0.1:8771"})        # other writes still need the token
        self.assertFalse(ok)
        self.assertEqual(sent, [401])
