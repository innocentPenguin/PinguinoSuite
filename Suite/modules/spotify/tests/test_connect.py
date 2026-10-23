"""Unit tests for connect.py (go-librespot child manager). No process, no network: popen/http/clock are injected."""
import json
import os
import sys
import tempfile
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
                         kill_stale=lambda pid: self.stale.append(pid) or True)
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
        (self.r.c.folder() / "pid").write_text("777")
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
        info = self.r.c.info()
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
