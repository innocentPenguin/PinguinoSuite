"""52's Voice security review (2026-10-23): headers, token rules, body limits, secret filter, spoken-control timeout, file names, log rotation.
A real server on a free port with a fake brain; temp data dir; nothing is played."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

os.environ.setdefault("PINGUINO_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import server
import textproc
import voicectl

TOKEN = "module-token-for-tests"


class FakeBrain:
    def __init__(self):
        self.cfg = config.defaults()
        self.got = []
        self.intervals = []
        self.current = None
        self.player = type('P', (), {'busy': False})()
        self.now = __import__('time').time

    def handle(self, ev):
        self.got.append(ev)
        return {"outcome": "queued"}

    def tail(self, n):
        return []


class Web(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_brain, cls.old_env = server.brain, os.environ.get("PINGUINO_API_TOKEN")
        os.environ["PINGUINO_API_TOKEN"] = TOKEN
        server.brain = FakeBrain()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.srv.daemon_threads = True
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.host = "127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        server.brain = cls.old_brain
        if cls.old_env is None:
            os.environ.pop("PINGUINO_API_TOKEN", None)
        else:
            os.environ["PINGUINO_API_TOKEN"] = cls.old_env

    def req(self, method, path, headers=None, body=None, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": self.host}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None:
            h["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = r.status, dict((k.lower(), v) for k, v in r.getheaders()), r.read()
        c.close()
        return out

    # ---- #3 headers
    def test_page_cannot_be_framed_by_other_sites(self):
        st, hd, _ = self.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("frame-ancestors", hd["content-security-policy"])
        self.assertNotIn("evil", hd["content-security-policy"])
        self.assertEqual(hd["x-content-type-options"], "nosniff")
        self.assertEqual(hd["referrer-policy"], "no-referrer")

    def test_json_answers_have_nosniff(self):
        _, hd, _ = self.req("GET", "/api/status")
        self.assertEqual(hd["x-content-type-options"], "nosniff")

    # ---- origin exactness
    def test_origin_must_be_exactly_local(self):
        for o in ("http://127.0.0.1", "http://127.0.0.1:8772", "http://localhost:3000", "tauri://localhost", ""):
            self.assertTrue(server.origin_ok(o), o)
        for o in ("http://127.0.0.1.evil.com", "http://localhost.evil.com:80", "http://127.0.0.1@evil.com", "https://127.0.0.1", "http://evil.com"):
            self.assertFalse(server.origin_ok(o), o)

    # ---- token rules
    def test_token_fails_closed_without_env(self):
        old = os.environ.pop("PINGUINO_API_TOKEN")
        try:
            self.assertFalse(server.token_ok({}))
            self.assertFalse(server.token_ok({"x-pinguino-token": "anything"}))
        finally:
            os.environ["PINGUINO_API_TOKEN"] = old

    def test_sensitive_gets_need_token_or_the_page_itself(self):
        for p in ("/api/history", "/api/history.csv", "/api/export", "/api/incidents", "/api/review/report?id=x", "/api/control", "/api/config"):
            self.assertEqual(self.req("GET", p)[0], 401, p)                                       # a bare local program
            self.assertEqual(self.req("GET", p, {"Origin": "http://evil.com"})[0], 401, p)         # another site
            self.assertEqual(self.req("GET", p, {"Sec-Fetch-Site": "cross-site"})[0], 401, p)
        # the Suite core / Host send the module token in either header form
        self.assertEqual(self.req("GET", "/api/config", {"Authorization": "Bearer " + TOKEN})[0], 200)
        self.assertEqual(self.req("GET", "/api/config", {"X-Pinguino-Token": TOKEN})[0], 200)
        self.assertEqual(self.req("GET", "/api/config", {"Authorization": "Bearer wrong"})[0], 401)
        # the Voice page in a browser (same origin, with or without Referer) keeps working
        self.assertEqual(self.req("GET", "/api/config", {"Sec-Fetch-Site": "same-origin"})[0], 200)
        self.assertEqual(self.req("GET", "/api/history", {"Referer": "http://%s/" % self.host})[0], 200)
        self.assertEqual(self.req("GET", "/api/config", {"Origin": "tauri://localhost"})[0], 200)
        self.assertEqual(self.req("GET", "/api/config", {"Referer": "http://evil.com/"})[0], 401)

    def test_non_sensitive_gets_stay_open_for_other_modules(self):
        self.assertEqual(self.req("GET", "/api/speech-intervals?since=0")[0], 200)     # Listen reads this without a token
        self.assertEqual(self.req("GET", "/api/sounds")[0], 200)

    def test_host_chat_command_call_still_works(self):
        """The Host posts with no Origin and (today) no token; with the token as well it must work too."""
        body = {"command": "nothing-here", "args": "", "user": "kara", "role": "4"}
        self.assertEqual(self.req("POST", "/api/chat-command", body=body)[0], 200)
        self.assertEqual(self.req("POST", "/api/chat-command", {"Authorization": "Bearer " + TOKEN}, body=body)[0], 200)

    def test_post_rules_unchanged(self):
        self.assertEqual(self.req("POST", "/api/mute", body={})[0], 401)                                           # no Origin, no token
        self.assertEqual(self.req("POST", "/api/mute", {"Origin": "http://evil.com"}, body={})[0], 403)
        self.assertEqual(self.req("POST", "/api/mute", {"Origin": "http://127.0.0.1.evil.com"}, body={})[0], 403)
        self.assertNotIn(self.req("POST", "/api/mute", {"Origin": "http://" + self.host}, body={})[0], (401, 403))   # the page's own call
        self.assertNotIn(self.req("POST", "/api/mute", {"Authorization": "Bearer " + TOKEN}, body={})[0], (401, 403))

    # ---- #10 request limits
    def test_oversize_and_chunked_bodies_are_refused_loudly(self):
        big = b'{"x":"' + b"a" * 4_100_000 + b'"}'
        st, _, out = self.req("POST", "/api/chat-command", raw=big)
        self.assertEqual(st, 413)
        self.assertIn(b"body over", out)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.putrequest("POST", "/api/chat-command")
        c.putheader("Host", self.host)
        c.putheader("Transfer-Encoding", "chunked")
        c.endheaders()
        c.send(b"2\r\n{}\r\n0\r\n\r\n")
        self.assertEqual(c.getresponse().status, 413)
        c.close()

    def test_handler_has_a_socket_timeout(self):
        self.assertEqual(server.H.timeout, 15)


class Secrets(unittest.TestCase):
    def scrub(self, t):
        return textproc.scrub_secrets(t)

    def test_passphrase_words_are_swallowed(self):
        out, found = self.scrub("my password is correct horse battery staple ok")
        self.assertTrue(found)
        for w in ("correct", "horse", "battery", "staple"):
            self.assertNotIn(w, out)

    def test_pin_and_digit_runs_and_phone_numbers(self):
        for t in ("my pin is 1 2 3 4", "call me 5551234567 now", "text 555-123-4567 please", "my number 555 123 4567"):
            self.assertTrue(self.scrub(t)[1], t)

    def test_obfuscated_keywords(self):
        for t in ("ｐａｓｓｗｏｒｄ is hunter2", "pass​word: hunter2", "p a s s w o r d is hunter2", "t.o.k.e.n abc123xyz", "my pass‍word hunter2"):
            out, found = self.scrub(t)
            self.assertTrue(found, t)
            self.assertNotIn("hunter2", out)
            self.assertNotIn("abc123xyz", out)

    def test_discord_style_token(self):
        self.assertTrue(self.scrub("MTIzNDU2Nzg5MDEyMzQ1Njc4.GabcDe.abcdefghijklmnopqrstuvwxyz1234")[1])

    def test_normal_chat_is_untouched(self):
        for t in ("great stream tonight", "the 2026 season has 12 games", "hello 3 friends", "see you at 10 30", "ünal says héllo"):
            self.assertEqual(self.scrub(t), (t, False), t)


class Control(unittest.TestCase):
    def mk(self, **ctl):
        cfgd = config.defaults()
        cfgd["control"].update({"enabled": True, "allow": {"game": True, "title": True, "timeout": True}, "cooldown_s": 0, **ctl})
        posts, said = [], []
        c = voicectl.Control(lambda: cfgd, lambda path, body: posts.append((path, body)) or {"ok": True}, speak=said.append, chatters=lambda: ["someviewer"], overlaps=lambda a, b: False)
        return c, posts, said

    def test_timeout_cannot_be_confirmed_by_voice(self):
        c, posts, said = self.mk()
        c.propose({"action": "timeout", "user": "someviewer", "seconds": 60})
        r = c.confirm(by="voice")
        self.assertEqual(posts, [])
        self.assertIsNotNone(c.pending)                       # still waiting for the page
        self.assertEqual(r.get("outcome"), "blocked")
        self.assertTrue(any("Confirm button on the page" in str(x) or "page" in str(x) for x in said + [c.log[-1]["detail"]]))

    def test_timeout_confirmed_from_the_page_works(self):
        c, posts, _ = self.mk()
        c.propose({"action": "timeout", "user": "someviewer", "seconds": 60})
        c.confirm(by="page")
        self.assertEqual([p[0] for p in posts], ["/api/mod/timeout"])

    def test_require_confirm_off_never_auto_runs_a_timeout(self):
        c, posts, _ = self.mk(require_confirm=False)
        c.propose({"action": "timeout", "user": "someviewer", "seconds": 60})
        self.assertEqual(posts, [])
        self.assertIsNotNone(c.pending)

    def test_game_still_confirms_by_voice_and_auto(self):
        c, posts, _ = self.mk()
        c.propose({"action": "game", "value": "Chess"})
        c.confirm(by="voice")
        self.assertEqual(len(posts), 1)
        c2, posts2, _ = self.mk(require_confirm=False)
        c2.propose({"action": "title", "value": "Hello"})
        self.assertEqual(len(posts2), 1)


class Files(unittest.TestCase):
    def test_device_names_are_made_safe(self):
        for n in ("CON", "nul", "AUX.wav", "com1", "LPT2.txt", "prn."):
            self.assertFalse(config._DEVICE_NAME.match(config.dev_safe(n)), n)
        self.assertEqual(config.dev_safe("my sound"), "my sound")
        self.assertEqual(config.dev_safe("console"), "console")

    def test_sound_upload_with_a_device_name(self):
        import base64, io, wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b"\x00\x00" * 2000)
        r = server.p_sound_upload(None, {"name": "CON.wav", "data": base64.b64encode(buf.getvalue()).decode()})
        self.assertNotEqual(r["name"].lower(), "con.wav")
        self.assertTrue((server._sounds_dir() / r["name"]).is_file())
        server.p_sound_delete(None, {"name": r["name"]})
        self.assertFalse((server._sounds_dir() / r["name"]).exists())

    def test_restore_backup_rejects_folders_and_device_names(self):
        config.path("backups").mkdir(exist_ok=True)
        (config.path("backups") / "sub").mkdir(exist_ok=True)
        for n in ("sub", "..", "NUL", "nothing.json"):
            with self.assertRaises(ValueError):
                config.restore_backup(n)

    def test_preset_name_cannot_be_a_device(self):
        self.assertFalse(config._DEVICE_NAME.match(config._pname("CON")))

    def test_append_line_rotates_like_history(self):
        p = config.path("rot-test.jsonl")
        p.write_text("x" * 100, encoding="utf8")
        config.append_line("rot-test.jsonl", "new", cap=50)
        self.assertEqual(p.read_text(encoding="utf8").strip(), "new")
        self.assertTrue(config.path("rot-test.1.jsonl").exists())
        config.append_line("rot-test.jsonl", "again", cap=50)
        self.assertEqual(p.read_text(encoding="utf8").split(), ["new", "again"])


if __name__ == "__main__":
    unittest.main()
