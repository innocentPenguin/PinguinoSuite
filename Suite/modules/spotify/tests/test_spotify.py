"""Run: python -m unittest discover -s Suite/modules/spotify/tests   (stdlib only, no network)."""
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["PINGUINO_DATA_DIR"] = tempfile.mkdtemp(prefix="spotify-test-")

import rules  # noqa: E402
import spotify_api  # noqa: E402
import store  # noqa: E402
from engine import Engine  # noqa: E402
Engine._schedule_refresh = lambda self: None      # a delayed re-poll from one test must not touch the shared store during the next
from queue_core import Queue, QueueError, new_item  # noqa: E402


def T(n, dur=200000, explicit=False, artist="Artist"):
    return {"id": f"id{n}".ljust(22, "x"), "uri": f"spotify:track:t{n}", "name": f"Song {n}", "artists": [artist], "album": "Al",
            "art": "", "duration_ms": dur, "explicit": explicit}


def V(n, user, tier=0):
    return new_item(T(n), user, "viewer", tier)


class QueueTests(unittest.TestCase):
    def ids(self, q):
        return [it["uri"][-2:] for it in q.items]

    def test_fair_round_robin(self):
        q = Queue()
        for n, u in [(1, "a"), (2, "a"), (3, "a"), (4, "b"), (5, "c")]:
            q.add(V(n, u))
        # a's 2nd/3rd requests rank behind b and c's first
        self.assertEqual([it["name"] for it in q.items], ["Song 1", "Song 4", "Song 5", "Song 2", "Song 3"])

    def test_sub_priority_within_round(self):
        q = Queue()
        q.add(V(1, "a"))
        q.add(V(2, "b", tier=1))
        self.assertEqual(q.items[0]["name"], "Song 2")

    def test_streamer_next_and_locked_survive(self):
        q = Queue()
        q.add(V(1, "a"))
        q.add(new_item(T(9)), "next")
        q.add(V(2, "b"))
        self.assertEqual(q.items[0]["uri"], "spotify:track:t9")

    def test_pushed_head_frozen(self):
        q = Queue()
        q.add(V(1, "a"))
        q.add(V(2, "b"))
        q.items[0]["pushed"] = True
        q.add(new_item(T(9)), "next")
        self.assertEqual(q.items[1]["uri"], "spotify:track:t9")
        with self.assertRaises(QueueError):
            q.move(q.items[0]["id"], 2)
        self.assertEqual(q.remove(q.items[0]["id"]), "marked")
        self.assertTrue(q.items[0]["skip_on_play"])
        self.assertEqual(len(q.items), 3)

    def test_move_clamps_and_locks(self):
        q = Queue()
        for n in range(4):
            q.add(new_item(T(n)))
        q.items[0]["pushed"] = True
        q.move(q.items[3]["id"], 0)          # can't go before the pushed head
        self.assertEqual(q.items[1]["name"], "Song 3")
        self.assertTrue(q.items[1]["locked"])

    def test_undo(self):
        q = Queue()
        q.add(new_item(T(1)))
        q.add(new_item(T(2)))
        q.remove(q.items[0]["id"])
        self.assertEqual(len(q.items), 1)
        q.undo()
        self.assertEqual(len(q.items), 2)
        q.undo()
        q.undo()
        with self.assertRaises(QueueError):
            q.undo()
        self.assertEqual(q.items, [])

    def test_undo_keeps_pushed_head(self):
        q = Queue()
        q.add(new_item(T(1)))
        q.add(new_item(T(2)))
        q.items[0]["pushed"] = True
        q.undo()                              # undo of the 2nd add, pushed head must stay
        self.assertEqual([it["name"] for it in q.items], ["Song 1"])
        self.assertTrue(q.items[0]["pushed"])

    def test_oops_removes_last_unpushed(self):
        q = Queue()
        q.add(V(1, "a"))
        q.add(V(2, "a"))
        it = q.remove_last_of("A")
        self.assertEqual(it["name"], "Song 2")

    def test_history_capped(self):
        q = Queue()
        for i in range(250):
            q.add_history({"uri": str(i)})
        self.assertEqual(len(q.history), 200)
        self.assertEqual(q.history[0]["uri"], "249")


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.s = rules.merged({"requests_open": True})
        self.q = Queue()

    def ev(self, t, user="v", roles=(), now_uri=None):
        return rules.evaluate(self.s, t, user, roles, self.q, now_uri)

    def test_ok(self):
        self.assertTrue(self.ev(T(1))[0])

    def test_explicit_and_stream_safe(self):
        self.s["block_explicit"] = True
        self.assertEqual(self.ev(T(1, explicit=True))[1], "explicit")
        self.s.update(block_explicit=False, stream_safe=True)
        self.assertEqual(self.ev(T(1, explicit=True))[1], "explicit")

    def test_length(self):
        self.assertEqual(self.ev(T(1, dur=700000))[1], "too_long")

    def test_blocklist_by_artist_title_and_uri(self):
        self.s["blocklist"] = ["bad artist", "spotify:track:t5", "naughty"]
        self.assertEqual(self.ev(T(1, artist="The BAD  Artist"))[1], "blocked")
        self.assertEqual(self.ev(T(5))[1], "blocked")
        t = T(2)
        t["name"] = "Very Naughty Song"
        self.assertEqual(self.ev(t)[1], "blocked")

    def test_limit_and_sub_extra_and_mod_bypass(self):
        self.q.add(V(1, "v"))
        self.q.add(V(2, "v"))
        self.assertEqual(self.ev(T(3))[1], "limit")
        self.assertTrue(self.ev(T(3), roles={"sub"})[0])
        self.assertTrue(self.ev(T(3), roles={"mod"})[0])

    def test_duplicates(self):
        self.q.add(V(1, "x"))
        self.assertEqual(self.ev(T(1), user="y")[1], "dup_queue")
        self.assertEqual(self.ev(T(2), now_uri="spotify:track:t2")[1], "dup_queue")
        self.q.add_history({"uri": "spotify:track:t3", "played_at": time.time() - 60})
        self.assertEqual(self.ev(T(3))[1], "dup_recent")
        self.q.history[0]["played_at"] = time.time() - 7200
        self.assertTrue(self.ev(T(3))[0])

    def test_toggles(self):
        self.s["requests_open"] = False
        self.assertEqual(self.ev(T(1))[1], "closed")
        self.assertTrue(self.ev(T(1), roles={"mod"})[0])
        self.s.update(requests_open=True, mod_only=True)
        self.assertEqual(self.ev(T(1), roles={"sub"})[1], "mod_only")
        self.s.update(mod_only=False, sub_only=True)
        self.assertEqual(self.ev(T(1))[1], "sub_only")
        self.assertTrue(self.ev(T(1), roles={"vip"})[0])

    def test_broadcaster_bypasses_everything(self):
        self.s["blocklist"] = ["artist"]
        self.assertTrue(self.ev(T(1), roles={"broadcaster"})[0])

    def test_blocked_user_and_queue_full(self):
        self.s["blocked_users"] = ["Troll"]
        self.assertEqual(self.ev(T(1), user="troll")[1], "user_blocked")
        self.s.update(blocked_users=[], queue_max=1)
        self.q.add(V(2, "z"))
        self.assertEqual(self.ev(T(1))[1], "full")

    def test_parse_and_ids(self):
        self.assertEqual(rules.parse("!SR  hello world"), ("sr", "hello world"))
        self.assertEqual(rules.parse("!request x"), ("sr", "x"))
        self.assertEqual(rules.parse("hello"), (None, ""))
        self.assertEqual(rules.parse("!unknown x"), (None, ""))
        self.assertEqual(rules.track_id_from("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=abc"), "4uLU6hMCjMI75M1A2tKUQC")
        self.assertEqual(rules.track_id_from("spotify:track:4uLU6hMCjMI75M1A2tKUQC"), "4uLU6hMCjMI75M1A2tKUQC")
        self.assertIsNone(rules.track_id_from("never gonna"))

    def test_merged_drops_bad_types(self):
        m = rules.merged({"per_user_limit": "x", "requests_open": 0, "blocklist": ["a"], "nope": 1, "queue_max": 9})
        self.assertEqual(m["per_user_limit"], 2)
        self.assertFalse(m["requests_open"])
        self.assertEqual(m["queue_max"], 9)
        self.assertNotIn("nope", m)


class FakeApi:
    """Stands in for spotify_api.Client."""

    def __init__(self):
        self.tracks = {f"t{n}": T(n) for n in range(1, 30)}
        self.playing = None           # uri
        self.progress = 0
        self.is_playing = True
        self.real_queue = []
        self.calls = []
        self.fail_queue = None

    def connected(self):
        return True

    def playback(self):
        if not self.playing:
            return None
        t = self.tracks[self.playing.split(":")[-1]]
        return {"is_playing": self.is_playing, "progress_ms": self.progress, "device": {"id": "d1", "name": "PC", "volume_percent": 50},
                "item": {"uri": t["uri"], "id": t["id"], "name": t["name"], "duration_ms": t["duration_ms"], "explicit": t["explicit"],
                         "artists": [{"name": a} for a in t["artists"]], "album": {"name": "Al", "images": []}}}

    def queue(self):
        return {"queue": [{"uri": u} for u in self.real_queue]}

    def add_to_queue(self, uri, device_id=None):
        self.calls.append(("queue", uri))
        if self.fail_queue:
            raise self.fail_queue
        self.real_queue.append(uri)

    def next(self):
        self.calls.append(("next",))
        if self.real_queue:
            self.playing = self.real_queue.pop(0)
            self.progress = 0

    def search(self, q, limit=8):
        return [self.tracks[k] for k in sorted(self.tracks) if q.lower() in self.tracks[k]["name"].lower()][:limit]

    def track(self, tid):
        return self.tracks.get("t1")

    def play_uris(self, uris, device_id=None):
        self.playing = uris[0]
        self.progress = 0

    def resume(self):
        self.is_playing = True

    def pause(self):
        self.is_playing = False


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeAuth:
    last_error = ""
    client_id = "cid"

    def __init__(self, connected=True):
        self._c = connected

    def connected(self):
        return self._c

    def access_token(self):
        return "x"

    def seconds_left(self):
        return 100


class EngineTests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True})

    def test_jit_push_and_track_change(self):
        self.e.add_track(T(2), "end", "bob", "viewer")
        self.api.playing, self.api.progress = "spotify:track:t1", 10000
        self.e.tick()
        self.assertEqual(self.api.real_queue, [], "far from the end: nothing pushed yet")
        self.api.progress = 180000                      # 20s left < 25s window
        self.e.tick()
        self.assertEqual(self.api.real_queue, ["spotify:track:t2"])
        self.assertTrue(self.e.queue.items[0]["pushed"])
        self.e.tick()
        self.assertEqual(len(self.api.real_queue), 1, "never pushed twice")
        self.api.playing, self.api.real_queue = "spotify:track:t2", []       # Spotify moved on
        self.e.tick()
        self.assertEqual(self.e.queue.items, [])
        self.assertEqual(self.e.now_item["requester"], "bob")
        self.assertEqual(self.e.queue.history[0]["uri"], "spotify:track:t1")
        self.assertIn("Song 2", store.folder().joinpath("nowplaying.txt").read_text(encoding="utf8"))

    def test_no_push_when_paused(self):
        self.e.add_track(T(2))
        self.api.playing, self.api.progress, self.api.is_playing = "spotify:track:t1", 199000, False
        self.e.tick()
        self.assertEqual(self.api.real_queue, [])

    def test_push_failure_is_retried_not_lost(self):
        self.e.add_track(T(2))
        self.api.playing, self.api.progress = "spotify:track:t1", 190000
        self.api.fail_queue = spotify_api.ApiError(404, "no device", "NO_ACTIVE_DEVICE")
        self.e.tick()
        self.assertFalse(self.e.queue.items[0]["pushed"])
        self.api.fail_queue = None
        self.e.tick()
        self.assertTrue(self.e.queue.items[0]["pushed"])

    def test_vanished_push_is_retried(self):
        self.e.add_track(T(2))
        self.api.playing, self.api.progress = "spotify:track:t1", 190000
        self.e.tick()
        self.api.real_queue = []                       # streamer cleared Spotify's queue
        self.clock.t += 30
        self.e.tick()
        self.assertFalse(self.e.queue.items[0]["pushed"])
        self.e.tick()
        self.assertEqual(self.api.real_queue, ["spotify:track:t2"])

    def test_skip_pushes_head_first(self):
        self.e.add_track(T(2))
        self.api.playing, self.api.progress = "spotify:track:t1", 1000
        self.e.tick()
        self.e.skip()
        self.assertEqual(self.api.calls, [("queue", "spotify:track:t2"), ("next",)])
        self.assertEqual(self.api.playing, "spotify:track:t2")

    def test_skip_on_play_marked_item(self):
        self.e.add_track(T(2))
        self.e.add_track(T(3))
        self.api.playing, self.api.progress = "spotify:track:t1", 190000
        self.e.tick()
        self.e.queue.remove(self.e.queue.items[0]["id"])    # already pushed -> marked
        self.api.playing = "spotify:track:t2"
        self.api.real_queue = ["spotify:track:t3"]
        self.e.tick()
        time.sleep(0.2)
        self.assertIn(("next",), self.api.calls)

    def test_chat_request_flow(self):
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        r = self.e.chat("alice", "!sr song 5", ["sub"])
        self.assertTrue(r["ok"], r)
        self.assertIn("added", r["reply"])
        self.assertEqual(self.e.queue.items[0]["tier"], 1)
        r = self.e.chat("alice", "!sr song 5", [])
        self.assertEqual(r["code"], "dup_queue")
        self.assertIn("Song 5", self.e.chat("x", "!queue", [])["reply"])
        self.assertIn("Song 1", self.e.chat("x", "!song", [])["reply"])
        self.assertEqual(self.e.chat("alice", "!oops", [])["code"], "removed")
        self.assertFalse(self.e.chat("x", "hello", [])["handled"])

    def test_chat_skips_blocked_candidate_and_uses_next(self):
        self.e.save_settings({"blocklist": ["spotify:track:t1"]})
        r = self.e.chat("bob", "!sr song 1", [])           # search returns Song 1, Song 10.. ; Song 1 blocked
        self.assertTrue(r["ok"], r)
        self.assertNotEqual(self.e.queue.items[0]["name"], "Song 1")

    def test_skip_votes(self):
        self.api.playing = "spotify:track:t1"
        self.api.real_queue = ["spotify:track:t2"]
        self.e.tick()
        self.assertEqual(self.e.chat("a", "!skip", [])["code"], "vote")
        self.assertEqual(self.e.chat("a", "!skip", [])["code"], "vote")     # same viewer twice counts once
        self.e.chat("b", "!skip", [])
        self.assertEqual(self.e.chat("c", "!skip", [])["code"], "skipped")

    def test_mod_skip_and_toggle(self):
        self.api.playing = "spotify:track:t1"
        self.api.real_queue = ["spotify:track:t2"]
        self.e.tick()
        self.assertEqual(self.e.chat("m", "!skip", ["mod"])["code"], "skipped")
        self.e.chat("m", "!sr close", ["mod"])
        self.assertEqual(self.e.chat("v", "!sr song 4", [])["code"], "closed")
        self.e.chat("m", "!sr open", ["mod"])
        self.assertTrue(self.e.chat("v", "!sr song 4", [])["ok"])

    def test_approval_inbox(self):
        self.e.save_settings({"require_approval": True})
        r = self.e.chat("v", "!sr song 4", [])
        self.assertEqual(r["code"], "pending")
        self.assertEqual(self.e.queue.items, [])
        rid = self.e.inbox[0]["id"]
        self.e.inbox_decide(rid, True)
        self.assertEqual(self.e.queue.items[0]["requester"], "v")
        self.assertTrue(self.e.chat("m", "!sr song 6", ["mod"])["code"] == "added", "mods skip approval unless stream-safe")

    def test_stream_safe_forces_approval_even_for_mods(self):
        self.e.save_settings({"stream_safe": True})
        self.assertEqual(self.e.chat("m", "!sr song 6", ["mod"])["code"], "pending")
        self.assertEqual(self.e.chat("ivan", "!sr song 7", ["broadcaster"])["code"], "added")

    def test_not_connected_and_replies_off(self):
        e = Engine(self.api, FakeAuth(False), self.clock)
        self.assertEqual(e.chat("v", "!sr x", [])["code"], "offline")
        self.e.save_settings({"chat_replies": False})
        self.assertEqual(self.e.chat("v", "!song", [])["reply"], "")

    def test_state_persists(self):
        self.e.add_track(T(2), "end", "bob", "viewer")
        e2 = Engine(self.api, FakeAuth(), self.clock)
        self.assertEqual(e2.queue.items[0]["name"], "Song 2")

    def test_rate_limit_backoff(self):
        def boom():
            raise spotify_api.RateLimited(7)
        self.api.playback = boom
        self.e.tick()
        self.assertGreaterEqual(self.e.backoff_until, self.clock.t + 7)

    def test_overlay_and_state_shape(self):
        self.api.playing, self.api.progress = "spotify:track:t1", 5000
        self.e.add_track(T(2))
        self.e.tick()
        o = self.e.overlay()
        self.assertEqual((o["title"], o["next"][0]["title"]), ("Song 1", "Song 2"))
        self.clock.t += 3
        self.assertGreaterEqual(self.e.overlay()["progress_ms"], 8000)
        json.dumps(self.e.public_state())

    def test_prestream_levels(self):
        e0 = Engine(self.api, FakeAuth(False), self.clock)
        self.assertEqual(e0.prestream()[0]["status"], "warn", "never connected = optional")
        e0.cfg["ever_connected"] = True
        self.assertEqual(e0.prestream()[0]["status"], "fail", "a lost login is a real failure")
        a = FakeAuth()
        a.client_id = ""
        self.assertEqual(Engine(self.api, a, self.clock).prestream()[0]["status"], "warn")
        self.api.me = lambda: {"display_name": "Ivan", "product": "free"}
        self.api.devices = lambda: []
        st = {i["id"]: i["status"] for i in self.e.prestream()}
        self.assertEqual(st, {"token": "pass", "premium": "fail", "device": "warn", "requests": "pass"})
        self.api.me = lambda: {"display_name": "Ivan", "product": "premium"}
        self.api.devices = lambda: [{"name": "PC", "is_active": True}]
        self.assertTrue(all(i["status"] == "pass" for i in self.e.prestream()))


class AuthTests(unittest.TestCase):
    def setUp(self):
        store.save("tokens.json", {})
        store.save("config.json", {"client_id": "cid"})
        self.now = 1000.0
        self.calls = []

    def http(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if url == spotify_api.TOKEN_URL:
            form = urllib.parse.parse_qs(body.decode())
            if form["grant_type"] == ["authorization_code"]:
                return 200, {}, {"access_token": "A1", "refresh_token": "R1", "expires_in": 3600, "scope": "x"}
            if form["refresh_token"] == ["BAD"]:
                return 400, {}, {"error": "invalid_grant"}
            return 200, {}, {"access_token": "A2", "expires_in": 3600}
        if headers["Authorization"] == "Bearer A1" and getattr(self, "expire_a1", False):
            return 401, {}, {"error": {"message": "expired"}}
        return 200, {}, {"ok": 1}

    def mk(self):
        a = spotify_api.Auth(self.http, lambda: self.now)
        return a, spotify_api.Client(a, self.http)

    def login(self, a):
        url = a.begin("http://127.0.0.1:8771/callback")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", q)
        a.finish("CODE", q["state"][0], "http://127.0.0.1:8771/callback")
        return q

    def test_pkce_challenge_matches_verifier(self):
        a, _ = self.mk()
        q = self.login(a)
        form = urllib.parse.parse_qs(self.calls[-1][2].decode())
        self.assertEqual(spotify_api.b64url(__import__("hashlib").sha256(form["code_verifier"][0].encode()).digest()), q["code_challenge"][0])
        self.assertTrue(a.connected())
        self.assertIn("R1", (store.folder() / "tokens.json").read_text(encoding="utf8"))

    def test_bad_state_rejected(self):
        a, _ = self.mk()
        with self.assertRaises(spotify_api.ApiError):
            a.finish("c", "nope", "u")

    def test_auto_refresh_and_keeps_refresh_token(self):
        a, c = self.mk()
        self.login(a)
        self.now += 3600
        self.assertEqual(a.access_token(), "A2")
        self.assertEqual(a.tokens["refresh_token"], "R1")

    def test_401_triggers_one_refresh_retry(self):
        a, c = self.mk()
        self.login(a)
        self.expire_a1 = True
        self.assertEqual(c.me(), {"ok": 1})

    def test_revoked_refresh_token_disconnects(self):
        a, c = self.mk()
        self.login(a)
        a.tokens["refresh_token"] = "BAD"
        self.now += 3600
        with self.assertRaises(spotify_api.ApiError):
            a.access_token()
        self.assertFalse(a.connected())

    def test_not_connected(self):
        a, c = self.mk()
        with self.assertRaises(spotify_api.NotConnected):
            c.me()

    def test_rate_limit_and_errors(self):
        a, _ = self.mk()
        self.login(a)

        def h(m, u, hd, b):
            return (429, {"Retry-After": "3"}, None) if "limited" in u else (403, {}, {"error": {"message": "x", "reason": "PREMIUM_REQUIRED"}})
        c = spotify_api.Client(a, h)
        with self.assertRaises(spotify_api.RateLimited) as cm:
            c._req("GET", "/limited")
        self.assertEqual(cm.exception.retry_after, 3)
        with self.assertRaises(spotify_api.ApiError) as cm:
            c._req("GET", "/me/player")
        self.assertEqual(cm.exception.reason, "PREMIUM_REQUIRED")

    def test_norm_playback_ad_and_empty(self):
        self.assertIsNone(spotify_api.norm_playback(None))
        pb = spotify_api.norm_playback({"is_playing": True, "item": None, "progress_ms": 1})
        self.assertIsNone(pb["track"])


class BridgeTests(unittest.TestCase):
    def setUp(self):
        from site_bridge import Bridge
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True})
        self.sent = []
        self.responses = {}
        self.b = Bridge(self.e, self.http, lambda s: None)
        self.b.configure("https://site.test/", "KEY", True)

    def http(self, method, url, key, body, timeout):
        self.sent.append((method, url, key, body))
        for k, v in self.responses.items():
            if k in url:
                return v
        return 200, {}

    def test_push_shape_and_blocklist_pull(self):
        self.api.playing, self.api.progress = "spotify:track:t1", 5000
        self.e.add_track(T(2), "end", "bob", "viewer")
        self.e.tick()
        self.responses = {"/push": (200, {"ok": True, "blocklistVersion": 4}),
                          "/blocklist": (200, {"version": 4, "tracks": ["spotify:track:t9"], "artists": ["Bad"], "users": ["troll"]})}
        self.assertTrue(self.b.push_once())
        m, url, key, body = self.sent[0]
        self.assertEqual((m, url, key), ("POST", "https://site.test/api/spotify/push", "KEY"))
        self.assertEqual(body["v"], 1)
        self.assertEqual(body["nowPlaying"]["title"], "Song 1")
        self.assertEqual(body["queue"][0]["requestedBy"], "bob")
        self.assertEqual(self.e.site_block["users"], ["troll"])
        self.assertEqual(self.e.chat("troll", "!sr song 4", [])["code"], "user_blocked")
        self.assertNotIn("troll", json.dumps(self.e.public_state()["settings"]))

    def test_poll_loop_survives_odd_answers_without_spinning(self):
        sleeps = []

        def sleep(s):
            sleeps.append(s)
            if len(sleeps) >= 3:
                self.b.stop = True
        self.b.sleep = sleep

        def boom(*a):
            raise RuntimeError("IncompleteRead")
        self.b.http = boom
        self.b.poll_loop()
        self.assertTrue(sleeps and min(sleeps) >= 1.0, sleeps)
        self.assertGreaterEqual(self.b.f["poll"], 1, "back-off counter must advance")

    def test_push_loop_error_backs_off(self):
        sleeps = []

        def sleep(s):
            sleeps.append(s)
            self.b.stop = True
        self.b.sleep = sleep
        self.e.site_snapshot = lambda: (_ for _ in ()).throw(RuntimeError("x"))
        self.b.push_loop()
        self.assertGreaterEqual(self.b.f["push"], 1)
        self.assertGreaterEqual(sleeps[0], 3)

    def test_non_dict_json_answers_are_tolerated(self):
        self.responses = {"/push": (200, ["not", "a", "dict"]), "/poll": (200, ["x"])}
        self.assertTrue(self.b.push_once())
        self.assertEqual(self.b.poll_once(), 0)

    def test_poison_event_does_not_lose_the_batch(self):
        self.api.track = lambda tid: self.api.tracks["t4"]
        self.responses = {"/poll": (200, {"events": ["junk", None, 5,
                                                     {"id": "e1", "type": "request", "user": "Ann", "trackId": "x"}]})}
        self.b.poll_once()
        ack = [s for s in self.sent if s[1].endswith("/ack")][0][3]["results"]
        self.assertEqual([r["id"] for r in ack], ["e1"])
        self.assertTrue(ack[0]["ok"])

    def test_event_batch_is_capped(self):
        self.responses = {"/poll": (200, {"events": [{"id": f"e{i}", "type": "nope"} for i in range(120)]})}
        self.assertEqual(self.b.poll_once(), 50)

    def test_request_vote_events_and_ack(self):
        self.api.track = lambda tid: self.api.tracks["t4"]
        self.responses = {"/poll": (200, {"events": [
            {"id": "e1", "type": "request", "user": "Ann", "login": "ann", "trackId": "x"},
            {"id": "e2", "type": "request", "user": "Ann", "login": "ann", "trackId": "x"},
            {"id": "e3", "type": "vote", "kind": "up", "user": "Bo", "login": "bo", "rid": "nope"}]})}
        self.assertEqual(self.b.poll_once(), 3)
        ack = [s for s in self.sent if s[1].endswith("/ack")][0][3]["results"]
        self.assertTrue(ack[0]["ok"])
        self.assertEqual(ack[1], {"id": "e2", "ok": False, "reason": "duplicate"})
        self.assertEqual(ack[2]["reason"], "unknown_request")
        rid = ack[0]["rid"]
        self.assertIsNone(self.e.upvote(rid, "bo"))
        self.assertEqual(self.e.upvote(rid, "BO"), "already_voted")
        self.assertEqual(self.e.site_snapshot()["queue"][0]["votes"], 1)

    def test_mod_events_and_sub_flags(self):
        self.api.track = lambda tid: self.api.tracks["t4"]
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        self.responses = {"/poll": (200, {"events": [
            {"id": "e1", "type": "request", "user": "Ann", "trackId": "x", "sub": True},
            {"id": "e2", "type": "mod", "action": "close", "user": "M"},
            {"id": "e3", "type": "mod", "action": "pause", "user": "M"},
            {"id": "e4", "type": "mod", "action": "bogus", "user": "M"}]})}
        self.b.poll_once()
        ack = [s for s in self.sent if s[1].endswith("/ack")][0][3]["results"]
        self.assertEqual([a["ok"] for a in ack], [True, True, True, False])
        self.assertEqual(self.e.queue.items[0]["tier"], 1)
        self.assertFalse(self.e.settings["requests_open"])
        self.assertFalse(self.api.is_playing)
        rid = self.e.queue.items[0]["id"]
        self.assertTrue(self.b.handle_mod("x", "remove", rid, "M")["ok"])
        self.assertEqual(self.e.queue.items, [])

    def test_site_down_backs_off_and_local_keeps_working(self):
        self.responses = {"/push": (503, {})}
        self.assertFalse(self.b.push_once())
        self.assertEqual(self.b.fail, 1)
        self.assertTrue(self.e.chat("v", "!song", [])["handled"])
        self.responses = {"/push": (200, {})}
        self.b.push_once()
        self.assertEqual(self.b.fail, 0)

    def test_vault_key_preferred_and_refetched_after_401(self):
        keys = iter(["V1", "V2"])
        self.b.vault = lambda name: next(keys)
        self.assertEqual(self.b.conf()[1], "V1")
        self.assertEqual(self.b.status()["key_source"], "vault")
        self.responses = {"/push": (401, {})}
        self.b.push_once()
        self.assertIsNone(self.b.vault_key)
        self.responses = {"/push": (200, {})}
        self.assertTrue(self.b.push_once())
        self.assertEqual(self.sent[-1][2], "V2")

    def test_falls_back_to_config_key_when_vault_empty(self):
        self.b.vault = lambda name: None
        self.assertEqual(self.b.conf()[1], "KEY")
        self.assertEqual(self.b.status()["key_source"], "config")

    def test_test_key(self):
        self.responses = {"/blocklist": (200, {})}
        self.assertTrue(self.b.test()[0])
        self.responses = {"/blocklist": (401, {})}
        self.assertFalse(self.b.test()[0])

    def test_disabled_does_nothing(self):
        self.b.configure(enabled=False)
        self.assertFalse(self.b.push_once())
        self.assertEqual(self.sent, [])
        self.assertNotIn("KEY", json.dumps(self.b.status()))


class LyricsCacheTests(unittest.TestCase):
    def setUp(self):
        import lyrics
        self.ly = lyrics
        lyrics._cache.clear()
        self.now = 5000.0
        lyrics._now = lambda: self.now

    def tearDown(self):
        import time as _t
        self.ly._now = _t.time
        self.ly._cache.clear()

    def test_404_is_cached_for_good(self):
        calls = []

        def http(url):
            calls.append(url)
            raise self.ly.NotFound()
        self.assertFalse(self.ly.lookup("A", "T", 1000, http)["found"])
        self.now += 3600
        self.assertFalse(self.ly.lookup("A", "T", 1000, http)["found"])
        self.assertEqual(len(calls), 1)

    def test_network_failure_retried_only_after_a_minute(self):
        calls = []

        def http(url):
            calls.append(url)
            raise OSError("offline")
        self.ly.lookup("A", "T", 0, http)
        self.now += 10
        self.ly.lookup("A", "T", 0, http)
        self.assertEqual(len(calls), 1)
        self.now += 61
        self.ly.lookup("A", "T", 0, http)
        self.assertEqual(len(calls), 2)

    def test_multi_timestamp_lines_and_none_artist(self):
        r = self.ly.parse_lrc("[00:10.00][00:42.50] chorus\n[00:20.00] verse")
        self.assertEqual([(x["t"], x["text"]) for x in r], [(10000, "chorus"), (20000, "verse"), (42500, "chorus")])
        calls = []
        self.assertFalse(self.ly.lookup(None, "T", 0, lambda u: calls.append(u))["found"])
        self.assertEqual(calls, [], "no artist: no lookup")

    def test_result_is_a_copy(self):
        d = {"syncedLyrics": "[00:01.00] hi", "plainLyrics": "hi"}
        a = self.ly.lookup("A", "T", 0, lambda u: d)
        a["synced"].append("junk")
        self.assertEqual(len(self.ly.lookup("A", "T", 0, lambda u: d)["synced"]), 1)


class StoreSafetyTests(unittest.TestCase):
    def test_corrupt_file_is_kept_and_default_returned(self):
        store.save("sx.json", {"a": 1})
        (store.folder() / "sx.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(store.load("sx.json", {}), {})
        self.assertTrue(list(store.folder().glob("sx.json.bad-*")))

    def test_wrong_type_returns_default(self):
        (store.folder() / "sy.json").write_text("null", encoding="utf-8")
        self.assertEqual(store.load("sy.json", {"k": 1}), {"k": 1})
        (store.folder() / "sy.json").write_text("[1]", encoding="utf-8")
        self.assertEqual(store.load("sy.json", {}), {})

    def test_save_survives_unserialisable_data_and_leaves_old_file(self):
        store.save("sz.json", {"ok": 1})
        store.save("sz.json", {"bad": object()})
        self.assertEqual(store.load("sz.json", {}), {"ok": 1})
        self.assertFalse((store.folder() / "sz.json.tmp").exists())

    def test_save_retries_a_dict_changed_during_dump(self):
        class Flaky(dict):
            n = 0

            def items(self):
                Flaky.n += 1
                if Flaky.n == 1:
                    raise RuntimeError("dictionary changed size during iteration")
                return super().items()
        store.save("sw.json", Flaky(a=1))
        self.assertEqual(store.load("sw.json", {}), {"a": 1})


class SettingsSanityTests(unittest.TestCase):
    def test_non_string_blocklist_items_dropped_and_evaluate_works(self):
        s = rules.merged({"blocklist": ["bad", 5, None, {"a": 1}, "x" * 500]})
        self.assertEqual(s["blocklist"][0], "bad")
        self.assertTrue(all(isinstance(x, str) and len(x) <= 200 for x in s["blocklist"]))
        self.assertIsNone(rules.blocked_reason(s, T(1)))

    def test_inf_nan_and_negative_numbers_rejected(self):
        d = rules.merged({})
        s = rules.merged({"queue_max": float("inf"), "max_length_s": -5, "per_user_limit": float("nan"), "limit_vip": -1, "limit_sub": -7})
        self.assertEqual(s["queue_max"], d["queue_max"])
        self.assertEqual(s["max_length_s"], d["max_length_s"])
        self.assertEqual(s["per_user_limit"], d["per_user_limit"])
        self.assertEqual(s["limit_vip"], -1)
        self.assertEqual(s["limit_sub"], d["limit_sub"])

    def test_long_strings_are_capped(self):
        s = rules.merged({"announce_template": "y" * 100000}) if "announce_template" in rules.DEFAULTS else rules.merged({})
        self.assertTrue(all(len(v) <= 2000 for v in s.values() if isinstance(v, str)))


class RobustLoadTests(unittest.TestCase):
    def test_queue_repairs_damaged_items(self):
        q = Queue([{"uri": "spotify:track:a"}, {"uri": "spotify:track:b", "requester": None, "pushed": None}, "junk", None, {"name": "no uri"}],
                  ["x", {"uri": "spotify:track:h"}])
        self.assertEqual([i["uri"] for i in q.items], ["spotify:track:a", "spotify:track:b"])
        self.assertEqual(q.pending_for("bob"), 0)
        self.assertEqual(q.frozen(), 0)
        self.assertEqual(q.items[1]["requester"], "")
        self.assertEqual(len(q.history), 1)
        q.remove_by("bob")

    def test_queue_non_list_state(self):
        q = Queue("oops", {"a": 1})
        self.assertEqual((q.items, q.history), ([], []))

    def test_new_item_null_duration(self):
        self.assertEqual(new_item({"uri": "spotify:track:z", "duration_ms": None}, "a", "viewer")["duration_ms"], 0)

    def test_track_id_must_look_like_an_id(self):
        cls = [v for v in vars(spotify_api).values() if isinstance(v, type) and hasattr(v, "track") and v.__name__ != "FakeApi"][0]
        c = cls.__new__(cls)
        for bad in ("../me/player", "", None, "abc", "x" * 23):
            with self.assertRaises(spotify_api.ApiError):
                c.track(bad)


class ArtistIdBanTests(unittest.TestCase):
    QUEEN, OTHER = "1dfeR4HaWDbWqFHLkxsg1d", "2ABCDEFGHIJKLMNOPQRSTu"

    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True})

    def _playing(self, n=1, artists=("Queen",), ids=None):
        t = T(n)
        t["artists"], t["artist_ids"] = list(artists), list(ids if ids is not None else [self.QUEEN][:len(artists)])
        self.api.tracks[f"t{n}"] = t
        self.api.playing = f"spotify:track:t{n}"
        self.e.tick()
        self.e.pb["track"] = t
        return t

    def test_id_ban_blocks_collab_not_lookalike(self):
        self._playing()
        self.assertTrue(self.e.chat("boss", "!banartist", ["broadcaster"])["ok"])
        self.assertIn(f"{self.QUEEN}|Queen", self.e.settings["blocked_artists"])
        self.assertEqual(self.e.settings["blocklist"], [], "no word entry for an artist with an id")
        collab = {**T(5), "artists": ["Other", "Queen"], "artist_ids": [self.OTHER, self.QUEEN]}
        self.assertTrue(rules.blocked_reason(self.e.settings, collab))
        lookalike = {**T(6), "name": "Queen of Hearts", "artists": ["Queensryche"], "artist_ids": [self.OTHER]}
        self.assertIsNone(rules.blocked_reason(self.e.settings, lookalike))

    def test_old_word_ban_is_upgraded(self):
        self.e.save_settings({"blocklist": ["queen", "other word"]})
        self._playing()
        self.e.chat("boss", "!banartist", ["broadcaster"])
        self.assertEqual(self.e.settings["blocklist"], ["other word"])

    def test_local_file_without_ids_falls_back_to_word(self):
        self._playing(artists=("Local Band",), ids=[])
        self.e.chat("boss", "!banartist", ["broadcaster"])
        self.assertEqual(self.e.settings["blocklist"], ["Local Band"])
        self.assertEqual(self.e.settings["blocked_artists"], [])

    def test_unban_by_name_and_site_ids(self):
        self._playing()
        self.e.chat("boss", "!banartist", ["broadcaster"])
        self.assertTrue(self.e.chat("boss", "!unbanartist queen", ["broadcaster"])["ok"])
        self.assertEqual(self.e.settings["blocked_artists"], [])
        self.e.site_block = {"artists": [self.OTHER, "some word"]}
        s = self.e.settings
        self.assertIn(self.OTHER + "|", s["blocked_artists"])
        self.assertIn("some word", s["blocklist"])
        self.assertTrue(rules.blocked_reason(s, {**T(7), "artist_ids": [self.OTHER]}))


class AnnounceTierTests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True, "announce_track_on": True})

    def _play(self, n, item=None):
        if item:
            self.e.queue.items.insert(0, item)
        self.api.playing = f"spotify:track:t{n}"
        self.e.tick()

    def test_default_skips_fallback_and_streamer_songs(self):
        self._play(1)
        self.assertEqual(self.e.announcements(0)["lines"], [])
        self._play(2, new_item(T(2), "boss", "streamer"))
        self.assertEqual(self.e.announcements(0)["lines"], [])

    def test_viewer_tiers_announced_with_fields(self):
        self._play(1, V(1, "ann", 0))
        self.clock.t += 30
        self._play(2, V(2, "sue", 1))
        self.clock.t += 30
        self._play(3, V(3, "rob", 2))
        lines = self.e.announcements(0)["lines"]
        self.assertEqual([(l["tier"], l["requester"]) for l in lines], [("normal", "ann"), ("sub", "sue"), ("redeem", "rob")])
        self.assertEqual(lines[0]["kind"], "track")
        self.assertEqual(lines[2]["uri"], "spotify:track:t3")
        self.assertEqual([l["seq"] for l in lines], sorted(l["seq"] for l in lines))

    def test_tier_template_with_fallback_to_default(self):
        self.e.save_settings({"msgs": {"announce_track_sub": "Sub pick ({tier}): {song}"}})
        self._play(1, V(1, "sue", 1))
        self.clock.t += 30
        self._play(2, V(2, "ann", 0))
        texts = [l["text"] for l in self.e.announcements(0)["lines"]]
        self.assertTrue(texts[0].endswith("Sub pick (sub): Song 1 - Artist"), texts)
        self.assertIn("Now playing: Song 2", texts[1])

    def test_fast_changes_keep_only_newest_line(self):
        self._play(1, V(1, "a", 0))
        self.clock.t += 5
        self._play(2, V(2, "b", 0))
        lines = self.e.announcements(0)["lines"]
        self.assertEqual(len(lines), 1)
        self.assertIn("Song 2", lines[0]["text"])

    def test_tiers_filter_can_include_fallback(self):
        self.e.save_settings({"announce_tiers": ["fallback"]})
        self._play(1)
        self.assertEqual(len(self.e.announcements(0)["lines"]), 1)


class PeriodBoardTests(unittest.TestCase):
    def setUp(self):
        import datetime as dt
        self.dt = dt
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)

    def at(self, iso):             # Chicago wall time (CDT, UTC-5) as a clock value
        self.clock.t = self.dt.datetime.fromisoformat(iso).replace(tzinfo=self.dt.timezone(self.dt.timedelta(hours=-5))).timestamp()

    def test_local_day_rolls_over_at_chicago_midnight(self):
        import engine as eng
        self.at("2026-10-23T23:59:00")
        self.assertEqual(eng.local_day(self.clock.t), "2026-10-23")
        self.at("2026-10-24T00:01:00")
        self.assertEqual(eng.local_day(self.clock.t), "2026-10-24")

    def test_week_month_and_all(self):
        self.at("2026-10-24T12:00:00")                                  # Saturday, ISO week 43
        self.e._board_add(T(1), "played", "Ann")
        self.at("2026-10-26T09:00:00")                                  # Monday: new ISO week
        self.e._board_add(T(2), "played", "ann")
        self.e._board_add(T(2), "skipped", "Bob")
        wk = self.e.leaderboard(10, "week")
        self.assertEqual((wk["period"], wk["key"]), ("week", "2026-W44"))
        self.assertEqual({r["name"].lower(): r["count"] for r in wk["requesters"]}, {"ann": 1, "bob": 1})
        self.assertEqual([m["title"] for m in wk["most_played"]], ["Song 2"])
        self.at("2026-11-01T12:00:00")                                   # month boundary
        self.e._board_add(T(3), "played", "Ann")
        self.assertEqual(self.e.leaderboard(10, "month")["key"], "2026-11")
        self.assertEqual([m["title"] for m in self.e.leaderboard(10, "month")["most_played"]], ["Song 3"])
        old = self.e.leaderboard(10)
        self.assertEqual(set(old), {"v", "requesters", "most_played", "most_skipped"}, "period=all keeps the old shape")
        self.assertEqual(old["requesters"][0], {"name": "Ann", "count": 2}, "all-time keeps the old per-spelling counts")

    def test_case_merge_and_blocked_users_hidden(self):
        self.at("2026-10-26T09:00:00")
        for u in ("Ann", "ann", "ANN", "troll"):
            self.e._board_add(T(1), "played", u)
        self.e.save_settings({"blocked_users": ["Troll"]})
        r = self.e.leaderboard(10, "day")["requesters"]
        self.assertEqual(r, [{"name": "ANN", "count": 3}])

    def test_old_days_are_pruned(self):
        self.at("2026-01-01T12:00:00")
        for i in range(410):
            self.clock.t += 86400
            self.e._board_add(T(1), "played", "ann")
        self.assertLessEqual(len(self.e.board["days"]), 400)


class LyricsToggleTests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)

    def test_toggle_alternates_without_a_song(self):
        self.assertTrue(self.e.now_info()["lyrics_on"])
        r = self.e.mod_action("lyrics_toggle")
        self.assertEqual((r["ok"], r["code"], r["lyrics_on"]), (True, "lyrics_off", False))
        self.assertFalse(self.e.now_info()["lyrics_on"])
        self.assertEqual(self.e.mod_action("lyrics_toggle")["code"], "lyrics_on")

    def test_explicit_value_is_idempotent_and_persisted(self):
        self.e.mod_action("lyrics_toggle", value=False)
        self.e.mod_action("lyrics_toggle", value=False)
        self.assertFalse(self.e.settings["lyrics_on"])
        self.assertFalse(store.load("config.json", {})["settings"]["lyrics_on"])

    def test_now_info_reports_state_while_playing_and_unknown_action_raises(self):
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        self.assertIn("lyrics_on", self.e.now_info())
        with self.assertRaises(QueueError):
            self.e.mod_action("nope")


class ManifestHelpTests(unittest.TestCase):
    def test_every_prestream_item_id_has_help(self):
        m = json.load(open(os.path.join(os.path.dirname(HERE), "module.json"), encoding="utf8"))
        for k in ("_module", "token", "premium", "device", "api", "requests", "site", "voice_skip"):
            h = m["help"][k]
            self.assertTrue(h["title"] and h["summary"] and h["steps"] and len(h["steps"]) <= 14, k)
            if "link" in h:
                self.assertTrue(h["link"]["url"].startswith("https://"), k)
        self.assertIn("help", m["secrets"][0])


class ClosedByDefaultTests(unittest.TestCase):
    def test_ships_closed_and_voice_skip_works(self):
        import server
        store.save("state.json", {})
        store.save("config.json", {})
        api = FakeApi()
        api.playing = "spotify:track:t1"
        api.real_queue = ["spotify:track:t2"]
        server.engine = Engine(api, FakeAuth(), Clock())
        e = server.engine
        self.assertFalse(e.settings["requests_open"])
        e.tick()
        self.assertEqual(e.chat("v", "!sr song 4", [])["code"], "closed")
        self.assertFalse(e.overlay() is None or e.site_snapshot()["status"]["requestsOpen"])
        r = server.p_chat_command(None, {"command": "skip", "role": "broadcaster", "isMod": True, "user": "ivan", "silent": True})
        self.assertTrue(r["ok"])
        self.assertEqual((r["say"], r["code"]), ("", "skipped"))
        self.assertEqual(api.playing, "spotify:track:t2")


class ChatCommandTests(unittest.TestCase):
    def test_host_contract(self):
        import server
        store.save("state.json", {})
        api = FakeApi()
        server.engine = Engine(api, FakeAuth(), Clock())
        server.engine.save_settings({"requests_open": True})
        r = server.p_chat_command(None, {"command": "sr", "args": "song 5", "user": "ann", "display": "Ann", "role": "viewer", "isSub": True})
        self.assertTrue(r["ok"], r)
        self.assertIn("added", r["say"])
        self.assertEqual(server.engine.queue.items[0]["tier"], 1)
        self.assertEqual(server.p_chat_command(None, {"command": "nope", "user": "a"})["error"], "unknown command")
        self.assertEqual(server.p_chat_command(None, {"command": "sr", "args": "", "user": "a"})["error"], "usage")


class PersonalizationTests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True})

    def test_schema_is_consistent(self):
        import config_schema as cs
        self.assertEqual(set(cs.DEFAULTS), {k for g in cs.SCHEMA for k, *_ in g["items"]})
        self.assertEqual(set(cs.DEFAULTS["msgs"]), set(cs.MSGS))
        self.assertEqual(set(cs.DEFAULTS["cmd_aliases"]), set(cs.COMMANDS))
        for k, (label, tpl, helptext) in cs.MSGS.items():
            self.assertTrue(label and helptext, k)
            tpl.format_map(type("D", (dict,), {"__missing__": lambda s, k: ""})(cs.VARS))
        for k, kind, d, label, hlp in [i for g in cs.SCHEMA for i in g["items"]]:
            self.assertTrue(label, k)
        for name, (label, hlp, patch) in cs.PRESETS.items():
            self.assertTrue(set(patch) <= set(cs.DEFAULTS), name)
            self.assertEqual(rules.merged(patch)["requests_open"], patch.get("requests_open", False))

    def test_custom_reply_template_and_prefix_and_silence(self):
        self.e.save_settings({"msgs": {"added": "{user}: queued {title} at spot {pos}!"}, "reply_prefix": "🎵 "})
        r = self.e.chat("ann", "!sr song 5", [])
        self.assertEqual(r["reply"], "🎵 ann: queued Song 5 at spot 1!")
        self.e.save_settings({"msgs": {"dup_queue": ""}})
        self.assertEqual(self.e.chat("bob", "!sr song 5", [])["reply"], "")
        self.assertEqual(self.e.chat("bob", "!sr song 5", [])["code"], "dup_queue")       # still refused, just silent
        self.assertIn("added", self.e.settings["msgs"]["closed"] + "added")                # other templates untouched
        self.assertTrue(self.e.settings["msgs"]["limit"])

    def test_bad_template_placeholder_is_blank_not_crash(self):
        self.e.save_settings({"msgs": {"added": "hi {nonsense} {user}"}})
        self.assertEqual(self.e.chat("ann", "!sr song 5", [])["reply"], "hi  ann")

    def test_aliases_and_prefix(self):
        self.e.save_settings({"cmd_aliases": {"sr": "tune, Add-Song"}, "prefix": "?"})
        self.assertTrue(self.e.chat("ann", "?tune song 5", [])["ok"])
        self.assertTrue(self.e.chat("ann", "?addsong song 6", [])["ok"])
        self.assertFalse(self.e.chat("ann", "!sr song 7", [])["handled"])
        self.assertTrue(self.e.chat("ann", "?song", [])["handled"])
        self.e.save_settings({"prefix": "!!!!!"})                       # too long: rejected, keeps the old one
        self.assertEqual(self.e.settings["prefix"], "?")
        self.e.save_settings({"cmd_aliases": {"nope": "x", "skip": ""}})   # unknown command / empty list ignored
        self.assertIn("skip", self.e.settings["cmd_aliases"]["skip"])

    def test_per_role_limits(self):
        self.e.save_settings({"per_user_limit": 1, "limit_sub": 3, "limit_vip": 2, "sub_extra": 0})
        self.assertTrue(self.e.chat("v", "!sr song 5", [])["ok"])
        self.assertEqual(self.e.chat("v", "!sr song 6", [])["code"], "limit")
        for n in (7, 8, 9):
            self.assertTrue(self.e.chat("s", f"!sr song {n}", ["sub"])["ok"], n)
        self.assertEqual(self.e.chat("s", "!sr song 10", ["sub"])["code"], "limit")
        for n in (11, 12):
            self.assertTrue(self.e.chat("p", f"!sr song {n}", ["vip"])["ok"], n)
        self.assertEqual(self.e.chat("p", "!sr song 13", ["vip"])["code"], "limit")
        self.e.save_settings({"per_user_limit": 0})                      # 0 = unlimited
        self.assertTrue(self.e.chat("v", "!sr song 14", [])["ok"])

    def test_cooldown_per_role(self):
        self.e.save_settings({"cooldown_s": 60, "cooldown_sub_s": 10, "per_user_limit": 0})
        self.assertTrue(self.e.chat("v", "!sr song 5", [])["ok"])
        r = self.e.chat("v", "!sr song 6", [])
        self.assertEqual(r["code"], "cooldown")
        self.assertIn("60", r["reply"])
        self.clock.t += 61
        self.assertTrue(self.e.chat("v", "!sr song 6", [])["ok"])
        self.assertTrue(self.e.chat("s", "!sr song 7", ["sub"])["ok"])
        self.clock.t += 5
        self.assertEqual(self.e.chat("s", "!sr song 8", ["sub"])["code"], "cooldown")
        self.clock.t += 6
        self.assertTrue(self.e.chat("s", "!sr song 8", ["sub"])["ok"])
        self.assertTrue(self.e.chat("m", "!sr song 9", ["mod"])["ok"] and self.e.chat("m", "!sr song 10", ["mod"])["ok"])

    def test_artist_cap_and_min_length_and_sub_max_length(self):
        self.e.save_settings({"max_per_artist": 2, "per_user_limit": 0})
        self.assertTrue(self.e.chat("a", "!sr song 5", [])["ok"] and self.e.chat("b", "!sr song 6", [])["ok"])
        self.assertEqual(self.e.chat("c", "!sr song 7", [])["code"], "artist_cap")
        self.e.save_settings({"max_per_artist": 0, "min_length_s": 300})
        self.assertEqual(self.e.chat("c", "!sr song 7", [])["code"], "too_short")
        self.e.save_settings({"min_length_s": 0, "max_length_s": 100, "max_length_sub_s": 400})
        self.assertEqual(self.e.chat("c", "!sr song 7", [])["code"], "too_long")
        self.assertTrue(self.e.chat("c", "!sr song 7", ["sub"])["ok"])

    def test_links_and_search_toggles(self):
        self.api.track = lambda tid: self.api.tracks["t4"]
        self.e.save_settings({"allow_links": False})
        self.assertEqual(self.e.chat("a", "!sr https://open.spotify.com/track/" + "x" * 22, [])["code"], "no_links")
        self.assertTrue(self.e.chat("a", "!sr song 5", [])["ok"])
        self.e.save_settings({"allow_links": True, "allow_search": False})
        self.assertEqual(self.e.chat("b", "!sr song 6", [])["code"], "no_search")
        self.assertTrue(self.e.chat("b", "!sr https://open.spotify.com/track/" + "x" * 22, [])["ok"])

    def test_approval_for_choices(self):
        self.e.save_settings({"require_approval": True, "approval_for": "non_subs"})
        self.assertEqual(self.e.chat("v", "!sr song 5", [])["code"], "pending")
        self.assertEqual(self.e.chat("s", "!sr song 6", ["sub"])["code"], "added")
        self.e.save_settings({"approval_for": "everyone"})
        self.assertEqual(self.e.chat("m", "!sr song 7", ["mod"])["code"], "pending")
        self.assertEqual(self.e.chat("ivan", "!sr song 8", ["broadcaster"])["code"], "added")

    def test_fair_queue_off_is_fifo_and_redeem_toggle(self):
        self.e.save_settings({"fair_queue": False, "per_user_limit": 0})
        for n, u in [(5, "a"), (6, "a"), (7, "b")]:
            self.e.chat(u, f"!sr song {n}", [])
        self.assertEqual(self.e.queue.items[2]["requester"], "b")
        self.e.save_settings({"redeem_priority": False})
        self.e.chat("z", "!sr song 8", [], redeem=True)
        self.assertEqual(self.e.queue.items[-1]["tier"], 0)

    def test_new_commands(self):
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        self.assertEqual(self.e.chat("a", "!lastsong", [])["code"], "last")
        self.assertIn("No previous", self.e.chat("a", "!lastsong", [])["reply"])
        self.e.chat("a", "!sr song 5", [])
        self.assertIn("Song 5", self.e.chat("a", "!mysongs", [])["reply"])
        self.assertIn("no requests", self.e.chat("zz", "!mysongs", [])["reply"])
        self.assertIn("!sr", self.e.chat("a", "!songhelp", [])["reply"])

    def test_presets_reset_and_merge_semantics(self):
        self.e.apply_preset("strict")
        s = self.e.settings
        self.assertEqual((s["per_user_limit"], s["block_explicit"], s["requests_open"]), (1, True, True))   # preset leaves open/closed alone
        self.e.save_settings({"msgs": {"added": "A"}})
        self.e.save_settings({"msgs": {"closed": "C"}})
        self.assertEqual((self.e.settings["msgs"]["added"], self.e.settings["msgs"]["closed"]), ("A", "C"))
        self.e.reset_settings(["msgs"])
        self.assertNotEqual(self.e.settings["msgs"]["added"], "A")
        self.assertEqual(self.e.settings["per_user_limit"], 1)
        self.e.reset_settings()
        self.assertEqual(self.e.settings["per_user_limit"], 2)
        self.assertFalse(self.e.settings["requests_open"])
        with self.assertRaises(QueueError):
            self.e.apply_preset("nope")

    def test_preview_uses_samples(self):
        self.assertIn("Ann", self.e.preview_msg("hi {user} {unknown}"))

    def test_overlay_style_exposed_and_validated(self):
        self.e.save_settings({"ov_theme": "glass", "ov_accent": "#00ff88", "ov_width": 300})
        st = self.e.overlay()["style"]
        self.assertEqual((st["theme"], st["accent"], st["width"]), ("glass", "#00ff88", 300))
        self.e.save_settings({"ov_theme": "neon", "ov_accent": "red"})
        st = self.e.overlay()["style"]
        self.assertEqual((st["theme"], st["accent"]), ("glass", "#00ff88"))


class Cycle1Tests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.api.vol = None
        self.api.contexts = []
        self.api.volume = lambda p: setattr(self.api, "vol", p)
        self.api.play_context = lambda uri, device_id=None: self.api.contexts.append(uri)
        self.api.shuffle = lambda on: None
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True, "per_user_limit": 0})

    def at(self, hh, mm, day=0):
        """Set the fake clock to a local time on a given weekday (0=Mon) of Oct 2026."""
        import calendar
        self.clock.t = time.mktime((2026, 10, 12 + day, hh, mm, 0, 0, 0, -1))

    def test_history_survives_a_nothing_playing_blip(self):
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        self.api.playing = None
        self.e.tick()                                    # Spotify answered 204 between songs
        self.api.playing = "spotify:track:t2"
        self.e.tick()
        self.assertEqual(self.e.queue.history[0]["uri"], "spotify:track:t1")

    def test_session_limit_resets_when_requests_reopen(self):
        self.e.save_settings({"session_limit": 2})
        self.assertTrue(self.e.chat("a", "!sr song 5", [])["ok"] and self.e.chat("a", "!sr song 6", [])["ok"])
        r = self.e.chat("a", "!sr song 7", [])
        self.assertEqual(r["code"], "session_limit")
        self.assertTrue(self.e.chat("m", "!sr song 7", ["mod"])["ok"] and self.e.chat("m", "!sr song 8", ["mod"])["ok"] and self.e.chat("m", "!sr song 9", ["mod"])["ok"])
        self.e.save_settings({"requests_open": False})
        self.e.save_settings({"requests_open": True})
        r = self.e.chat("a", "!sr song 10", []); self.assertTrue(r["ok"], r)

    def test_queue_minutes_cap(self):
        self.e.save_settings({"queue_max_minutes": 7})                 # songs are 200 s
        self.assertTrue(all(self.e.chat(u, f"!sr song {n}", [])["ok"] for u, n in (("a", 5), ("b", 6))))
        self.assertTrue(self.e.chat("c", "!sr song 7", [])["ok"])       # 400 s queued < 7 min
        self.assertEqual(self.e.chat("d", "!sr song 8", [])["code"], "full")  # 600 s >= 7 min? 3*200=600>=420

    def test_priority_and_trusted_users(self):
        self.e.save_settings({"priority_users": ["Friend"], "trusted_users": ["Friend"], "require_approval": True})
        self.assertEqual(self.e.chat("rand", "!sr song 5", [])["code"], "pending")
        r = self.e.chat("friend", "!sr song 6", [])
        self.assertEqual(r["code"], "added")
        self.assertEqual(self.e.queue.items[0]["tier"], 1)

    def test_volume_command_and_clamp(self):
        self.e.save_settings({"volume_max": 60, "volume_min": 10})
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        self.assertEqual(self.e.chat("v", "!volume 30", [])["code"], "denied")                  # mods only
        r = self.e.chat("m", "!volume 90", ["mod"])
        self.assertEqual((self.api.vol, r["code"]), (60, "volume"))
        self.e.chat("m", "!volume 1", ["mod"])
        self.assertEqual(self.api.vol, 10)
        self.e.control("volume", 99)
        self.assertEqual(self.api.vol, 60)
        self.assertIn("%", self.e.chat("m", "!volume", ["mod"])["reply"])

    def test_playnext_command(self):
        self.e.chat("a", "!sr song 5", [])
        r = self.e.chat("m", "!playnext song 6", ["mod"])
        self.assertTrue(r["ok"])
        self.assertEqual(self.e.queue.items[0]["name"], "Song 6")
        self.assertEqual(self.e.chat("v", "!playnext song 7", [])["code"], "denied")

    def test_shuffle_and_remove_user(self):
        for n, u in [(5, "a"), (6, "b"), (7, "c"), (8, "d"), (9, "e"), (10, "f")]:
            self.e.chat(u, f"!sr song {n}", [])
        self.e.add_track(T(20), "next")
        head = self.e.queue.items[0]["name"]
        names = sorted(i["name"] for i in self.e.queue.items)
        self.assertEqual(self.e.shuffle_queue(), 6)
        self.assertEqual(self.e.queue.items[0]["name"], head)                        # locked item stays
        self.assertEqual(sorted(i["name"] for i in self.e.queue.items), names)
        self.assertEqual(self.e.remove_user("B"), 1)
        self.assertNotIn("Song 6", [i["name"] for i in self.e.queue.items])
        self.e.queue.undo()
        self.assertIn("Song 6", [i["name"] for i in self.e.queue.items])

    def test_stats(self):
        for u, n in (("a", 1), ("a", 2), ("b", 3)):
            self.e.queue.add_history({"uri": f"u{n}", "name": f"S{n}", "artists": ["X"], "requester": u, "played_at": 1})
        self.e.queue.add_history({"uri": "u1", "name": "S1", "artists": ["X"], "requester": "b", "played_at": 2})
        st = self.e.stats()
        self.assertEqual(st["top_requesters"][0], ("a", 2) if st["top_requesters"][0][0] == "a" else st["top_requesters"][0])
        self.assertEqual(st["top_songs"][0][1], 2)

    def test_autoskip_blocked_from_any_source(self):
        self.api.tracks["t5"]["name"] = "Bad Song"
        self.e.save_settings({"autoskip_blocked": True, "blocklist": ["bad song"]})
        self.api.playing = "spotify:track:t5"
        self.api.real_queue = ["spotify:track:t6"]
        self.e.tick()
        time.sleep(0.3)
        self.assertIn(("next",), self.api.calls)
        self.api.calls.clear()
        self.e.save_settings({"autoskip_blocked": False})
        self.api.playing = "spotify:track:t5"
        self.e.last_uri = None
        self.e.tick()
        time.sleep(0.2)
        self.assertNotIn(("next",), self.api.calls)

    def test_schedule_opens_and_closes_on_transitions_only(self):
        self.e.save_settings({"requests_open": False, "schedule_enabled": True, "schedule_open": "17:00", "schedule_close": "21:00",
                              "schedule_days": "mon,tue"})
        self.at(16, 0)
        self.e.automation_tick()
        self.at(17, 5)
        self.e.automation_tick()
        self.assertTrue(self.e.settings["requests_open"])
        self.e.save_settings({"requests_open": False})                  # manual close inside the window is respected
        self.e.automation_tick()
        self.assertFalse(self.e.settings["requests_open"])
        self.at(21, 5)
        self.e.save_settings({"requests_open": True})
        self.e.automation_tick()
        self.assertFalse(self.e.settings["requests_open"])
        self.at(17, 30, day=2)                                          # Wednesday: not a scheduled day
        self.e.automation_tick()
        self.assertFalse(self.e.settings["requests_open"])

    def test_schedule_overnight_window(self):
        self.e.save_settings({"requests_open": False, "schedule_enabled": True, "schedule_open": "22:00", "schedule_close": "02:00", "schedule_days": "mon"})
        self.at(21, 0)
        self.e.automation_tick()
        self.at(22, 30)
        self.e.automation_tick()
        self.assertTrue(self.e.settings["requests_open"])
        self.at(1, 0, day=1)                                            # Tuesday 01:00 still belongs to Monday's window
        self.e.automation_tick()
        self.assertTrue(self.e.settings["requests_open"])
        self.at(2, 30, day=1)
        self.e.automation_tick()
        self.assertFalse(self.e.settings["requests_open"])

    def test_autostart_and_fallback_playlist(self):
        self.e.add_track(T(5))
        self.e.save_settings({"autostart_queue": True})
        self.e.tick()
        self.e.idle_since = self.clock.t - 10
        self.e.automation_tick()
        self.assertEqual(self.api.playing, "spotify:track:t5")
        self.e.queue.items.clear()
        self.api.playing = None
        self.e.tick()
        self.e.idle_since = self.clock.t - 30
        self.e.save_settings({"fallback_playlist": "https://open.spotify.com/playlist/" + "a" * 22})
        self.e.automation_tick()
        self.assertEqual(self.api.contexts, ["spotify:playlist:" + "a" * 22])
        self.e.automation_tick()
        self.assertEqual(len(self.api.contexts), 1, "not repeated within 60 s")
        self.clock.t += 61
        self.e.save_settings({"requests_open": False})
        self.e.automation_tick()
        self.assertEqual(len(self.api.contexts), 1, "fallback_only_open respected")

    def test_text_files(self):
        self.e.save_settings({"queue_file_lines": 2})
        self.e.add_track(T(5), "end", "bob", "viewer")
        self.e.add_track(T(6))
        self.e.add_track(T(7))
        q = (store.folder() / "queue.txt").read_text(encoding="utf8").splitlines()
        self.assertEqual(len(q), 2)
        self.assertIn("(bob)", q[0])
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        self.assertEqual(json.loads((store.folder() / "nowplaying.json").read_text(encoding="utf8"))["title"], "Song 1")

    def test_context_uri_parser(self):
        from engine import _context_uri, _hhmm
        self.assertEqual(_context_uri("spotify:album:" + "b" * 22), "spotify:album:" + "b" * 22)
        self.assertIsNone(_context_uri("nonsense"))
        self.assertEqual((_hhmm("17:00"), _hhmm("24:00"), _hhmm("x")), (1020, None, None))


class Cycle2Tests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.api.artist_calls = 0
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True, "per_user_limit": 0})

    def test_genre_block_uses_cache_and_fails_open(self):
        for n in (5, 6):
            self.api.tracks[f"t{n}"]["artist_ids"] = ["artX" if n == 5 else "artY"]

        def artists(ids):
            self.api.artist_calls += 1
            return {"artX": ["brutal death metal"], "artY": ["pop"]}
        self.api.artists = artists
        self.e.save_settings({"block_genres": ["death metal"]})
        r = self.e.chat("a", "!sr song 5", [])
        self.assertEqual(r["code"], "genre")
        self.assertIn("death metal", r["reply"])
        self.assertEqual(self.e.chat("a", "!sr song 6", [])["code"], "added")
        calls = self.api.artist_calls
        self.e.chat("b", "!sr song 5", [])
        self.assertEqual(self.api.artist_calls, calls, "artist genres cached")
        self.assertEqual(self.e.chat("ivan", "!sr song 5", ["broadcaster"])["code"], "added")      # broadcaster bypass

        def boom(ids):
            raise spotify_api.ApiError(500, "x")
        self.api.artists = boom
        self.api.tracks["t7"]["artist_ids"] = ["artZ"]
        self.assertEqual(self.e.chat("c", "!sr song 7", [])["code"], "added")                       # lookup failure = allow

    def test_add_context_dedupes_shuffles_and_validates(self):
        self.api.context_tracks = lambda kind, cid, limit=100: [self.api.tracks[f"t{n}"] for n in range(5, 11)]
        self.e.add_track(T(5))
        n = self.e.add_context("https://open.spotify.com/playlist/" + "p" * 22, shuffle=True)
        self.assertEqual(n, 5)
        self.assertEqual(len({i["uri"] for i in self.e.queue.items}), 6)
        with self.assertRaises(QueueError):
            self.e.add_context("https://example.com/nope")
        self.api.context_tracks = lambda *a, **k: []
        with self.assertRaises(QueueError):
            self.e.add_context("spotify:album:" + "a" * 22)

    def test_user_presets_roundtrip(self):
        self.e.save_settings({"per_user_limit": 4, "msgs": {"added": "Mine {user}"}, "requests_open": True})
        self.assertEqual(self.e.save_user_preset("Friday"), ["Friday"])
        self.e.reset_settings()
        self.assertEqual(self.e.settings["per_user_limit"], 2)
        self.e.apply_preset("Friday")                       # same entry point as built-ins
        self.assertEqual((self.e.settings["per_user_limit"], self.e.settings["msgs"]["added"]), (4, "Mine {user}"))
        self.assertFalse(self.e.settings["requests_open"])  # presets never touch open/closed
        self.assertEqual(self.e.delete_user_preset("Friday"), [])
        with self.assertRaises(QueueError):
            self.e.apply_preset("Friday")
        with self.assertRaises(QueueError):
            self.e.save_user_preset("  ")
        e2 = Engine(self.api, FakeAuth(), self.clock)
        self.assertEqual(e2.cfg.get("user_presets"), {})

    def test_overlay_alert_expires_and_can_be_off(self):
        self.e.chat("ann", "!sr song 5", [])
        a = self.e.overlay()["alert"]
        self.assertIn("ann requested Song 5", a["text"])
        self.clock.t += 7
        self.assertIsNone(self.e.overlay()["alert"])
        self.e.chat("bob", "!sr song 6", [])
        self.e.save_settings({"ov_alerts": False})
        self.assertIsNone(self.e.overlay()["alert"])

    def test_sr_safe_toggle_mods_only(self):
        self.assertEqual(self.e.chat("m", "!sr safe on", ["mod"])["code"], "toggle")
        self.assertTrue(self.e.settings["stream_safe"])
        self.assertEqual(self.e.chat("m", "!sr safe off", ["mod"])["code"], "toggle")
        self.assertFalse(self.e.settings["stream_safe"])
        r = self.e.chat("v", "!sr safe on", [])             # a viewer's "safe on" is just a search
        self.assertFalse(self.e.settings["stream_safe"])

    def test_announcements_feed(self):
        self.e.save_settings({"announce_track_on": True, "announce_request_on": True, "announce_tiers": ["fallback", "normal"]})
        self.e.chat("ann", "!sr song 5", [])
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        a = self.e.announcements(0)
        self.assertEqual([l["text"] for l in a["lines"]], ["Now playing: Song 1 - Artist"])
        self.assertEqual(self.e.announcements(a["seq"])["lines"], [])
        self.clock.t += 200
        self.assertEqual(self.e.announcements(0)["lines"], [], "stale lines are not replayed")
        self.e.save_settings({"announce_track_on": False, "announce_request_on": False})
        self.e.chat("bob", "!sr song 6", [])
        self.assertEqual(self.e.announcements(0)["lines"], [])

    def test_search_cache(self):
        calls = []
        orig = self.api.search
        self.api.search = lambda q, limit=8: (calls.append(q), orig(q, limit))[1]
        self.e.resolve("Song 5")
        self.e.resolve("  song 5 ")
        self.assertEqual(len(calls), 1)
        self.clock.t += 130
        self.e.resolve("song 5")
        self.assertEqual(len(calls), 2)

    def test_norm_track_has_artist_ids_and_context_parsing(self):
        t = spotify_api.norm_track({"uri": "spotify:track:x", "id": "x", "name": "N", "artists": [{"name": "A", "id": "a1"}], "album": {"name": "Al", "images": []}})
        self.assertEqual(t["artist_ids"], ["a1"])
        calls = []

        def http(m, url, hd, body):
            calls.append(url)
            if "/albums/" in url:
                return 200, {}, {"items": [{"uri": "spotify:track:1", "id": "1", "name": "A", "artists": []}, {"uri": "spotify:local:x", "name": "L"}], "next": None}
            return 200, {}, {"items": [{"track": {"uri": "spotify:track:2", "id": "2", "name": "P", "artists": [], "album": {"images": []}}}, {"track": None},
                                       {"track": {"uri": "spotify:track:3", "id": "3", "name": "Loc", "is_local": True, "artists": []}}], "next": None}
        auth = spotify_api.Auth(lambda *a: (200, {}, {}), lambda: 0)
        auth.tokens = {"refresh_token": "r", "access_token": "a", "expires_at": 10 ** 12}
        c = spotify_api.Client(auth, http)
        self.assertEqual([t["name"] for t in c.context_tracks("album", "x" * 22)], ["A"])
        self.assertEqual([t["name"] for t in c.context_tracks("playlist", "x" * 22)], ["P"])


class PlayerApi(FakeApi):
    def __init__(self):
        super().__init__()
        self.devs = [{"id": "d1", "name": "PC", "is_active": True}, {"id": "pg", "name": "PinguinoSuite", "is_active": False}]
        self.transfers, self.plays = [], []

    def devices(self):
        return self.devs

    def transfer(self, dev, play=False):
        self.transfers.append((dev, play))

    def play_uris(self, uris, device_id=None):
        self.plays.append(device_id)
        super().play_uris(uris, device_id)

    def volume(self, pct):
        self.calls.append(("volume", pct))


class PlayerTests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = PlayerApi(), Clock()
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.api.playing = "spotify:track:t1"

    def test_scopes_include_streaming(self):
        self.assertIn("streaming", spotify_api.SCOPES.split())
        self.assertIn("user-read-email", spotify_api.SCOPES.split())

    def test_not_selected_until_page_reports(self):
        self.e.tick()
        self.assertEqual(self.api.transfers, [])
        self.assertFalse(self.e.player_info()["live"])

    def test_selected_when_it_appears_and_not_repeated(self):
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.tick()
        self.assertEqual(self.api.transfers, [("pg", True)])
        self.clock.t += 7
        self.api.devs[0]["is_active"] = False
        self.e.tick()                                    # pb still reports d1 (fake) -> retried only after the check interval
        self.assertEqual(len(self.api.transfers), 2)

    def test_device_not_visible_to_spotify_yet(self):
        self.api.devs = self.api.devs[:1]
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.tick()
        self.assertEqual(self.api.transfers, [])

    def test_stale_page_or_switched_off_is_ignored(self):
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.clock.t += 60                               # page stopped reporting
        self.e.tick()
        self.assertEqual(self.api.transfers, [])
        self.assertEqual(self.e.player_info()["state"], "closed")
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.save_settings({"player_native": False})
        self.e.tick()
        self.assertEqual(self.api.transfers, [])

    def test_manual_transfer_is_respected_then_released(self):
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.control("transfer", "d1")
        self.clock.t += 7
        self.e.tick()
        self.assertEqual(self.api.transfers[-1], ("d1", True))
        self.assertEqual(len(self.api.transfers), 1)
        self.clock.t += 700
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.tick()
        self.assertEqual(self.api.transfers[-1], ("pg", True))

    def test_start_queue_targets_the_player(self):
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.add_track(T(2), "end", "bob", "viewer")
        self.e.start_queue()
        self.assertEqual(self.api.plays, ["pg"])

    def test_volume_is_stored_for_the_page(self):
        self.api.playing = None
        self.e.player_report({"device_id": "pg", "state": "ready"})
        self.e.control("volume", 40)
        self.assertEqual(self.e.player_info()["volume"], 40)

    def test_player_info_flags_missing_scope(self):
        self.e.auth.tokens = {"scope": "user-read-private"}
        self.assertTrue(self.e.player_info()["needs_reauth"])
        self.e.auth.tokens = {"scope": "streaming user-read-private"}
        self.assertFalse(self.e.player_info()["needs_reauth"])

    def test_report_truncates_and_never_holds_a_token(self):
        self.e.player_report({"device_id": "x" * 500, "state": "ready", "error": "e" * 999, "access_token": "SECRET"})
        self.assertNotIn("SECRET", json.dumps(self.e.player_info()))
        self.assertLessEqual(len(self.e.player["device_id"]), 80)


if __name__ == "__main__":
    unittest.main()


class Audit2RestTests(BridgeTests):
    def test_redelivered_event_is_not_run_twice(self):
        self.api.track = lambda tid: self.api.tracks["t4"]
        self.responses = {"/poll": (200, {"events": [{"id": "e1", "type": "request", "user": "Ann", "trackId": "x"}]}), "/ack": (500, {})}
        self.b.poll_once()
        n = len(self.e.queue.items)
        self.b.poll_once()                                         # the site redelivers e1 because the ack failed
        self.assertEqual(len(self.e.queue.items), n)
        acks = [s for s in self.sent if s[1].endswith("/ack")]
        self.assertEqual(len(acks), 4)                             # each poll acks twice (one retry)
        self.assertEqual(acks[0][3]["results"], acks[2][3]["results"])

    def test_site_text_is_cleaned_and_capped(self):
        from site_bridge import clean
        self.assertEqual(clean("Ann" + chr(7) + chr(10) + "X" * 100, 10), "AnnXXXXXXX")

    def test_null_blocklist_keys_do_not_break_pull(self):
        self.responses = {"/push": (200, {"blocklistVersion": 7}), "/blocklist": (200, {"version": 7, "tracks": None, "users": ["a"]})}
        self.b.push_once()
        self.assertEqual(self.b.blocklist_version, 7)
        self.assertEqual(self.e.site_block["users"], ["a"])
        self.assertEqual(self.e.site_block["tracks"], [])

    def test_start_twice_starts_one_pair_of_threads(self):
        import threading
        n = threading.active_count()
        self.b.stop = True
        self.b.start()
        self.b.start()
        time.sleep(0.2)
        self.assertLessEqual(threading.active_count() - n, 2)

    def test_mod_failure_reasons(self):
        from spotify_api import ApiError
        self.e.skip = lambda force=False: (_ for _ in ()).throw(ApiError(429, "slow"))
        self.assertEqual(self.b.handle_mod("m1", "skip", "", "mod")["reason"], "rate_limited")
        self.e.skip = lambda force=False: (_ for _ in ()).throw(ApiError(500, "boom"))
        self.assertEqual(self.b.handle_mod("m2", "skip", "", "mod")["reason"], "error")


class Audit2RuleTests(unittest.TestCase):
    def setUp(self):
        self.s = rules.merged({"requests_open": True, "blocklist": ["a", "xx", "Bad Band"]})
        self.q = Queue()

    def test_short_blocklist_entries_match_whole_words_only(self):
        self.assertTrue(rules.evaluate(self.s, T(1), "v", (), self.q, None)[0])          # "a" in "Song 1"/"Artist 1" must not block
        t = dict(T(2), name="Hello a friend")
        self.assertEqual(rules.evaluate(self.s, t, "v", (), self.q, None)[1], "blocked")
        t = dict(T(3), artists=["The Bad Band"])
        self.assertEqual(rules.evaluate(self.s, t, "v", (), self.q, None)[1], "blocked")

    def test_none_user_and_null_duration(self):
        t = dict(T(1), duration_ms=None)
        self.assertTrue(rules.evaluate(self.s, t, None, (), self.q, None)[0])

    def test_parse_splits_on_any_whitespace(self):
        self.assertEqual(rules.parse("!sr" + chr(9) + "name")[1], "name")
        self.assertEqual(rules.parse("!sr" + chr(160) + "name")[1], "name")
        self.assertEqual(rules.parse("!lastsong")[1], "")


class Audit2MiscTests(unittest.TestCase):
    def test_oembed_cached(self):
        import ytlink
        ytlink._meta.clear()
        calls = []

        def http(url):
            calls.append(url)
            return {"title": "A - B", "author_name": "C"}
        for _ in range(5):
            self.assertEqual(ytlink.fetch_meta("abcdefghijk", http)["title"], "A - B")
        self.assertEqual(len(calls), 1)
        ytlink._meta.clear()

    def test_oembed_failure_cached_briefly(self):
        import ytlink
        ytlink._meta.clear()
        calls = []

        def http(url):
            calls.append(1)
            raise OSError("down")
        t = [1000.0]
        for _ in range(3):
            self.assertIsNone(ytlink.fetch_meta("zzzzzzzzzzz", http, lambda: t[0]))
        self.assertEqual(len(calls), 1)
        t[0] += 130
        ytlink.fetch_meta("zzzzzzzzzzz", http, lambda: t[0])
        self.assertEqual(len(calls), 2)
        ytlink._meta.clear()


class Review53Tests(AnnounceTierTests):
    def test_fast_poller_gets_no_burst(self):
        self._play(1, V(1, "a", 0))
        self.assertEqual(len(self.e.announcements(0)["lines"]), 1)       # the Host took it
        self.clock.t += 5
        self._play(2, V(2, "b", 0))
        self.assertEqual(len(self.e.announcements(0)["lines"]), 1)       # still only the first: second is inside the gap
        self.clock.t += 60
        self._play(3, V(3, "c", 0))
        self.assertIn("Song 3", self.e.announcements(0)["lines"][-1]["text"])

    def test_announce_never_starts_with_a_command_char(self):
        self.e.save_settings({"msgs": {"announce_track_default": "/ban {song}"}, "reply_prefix": ""})
        self._play(1, V(1, "a", 0))
        for l in self.e.announcements(0)["lines"]:
            self.assertNotIn(l["text"][:1], "/.!")

    def test_idless_credit_becomes_word_ban_and_bad_ids_are_dropped(self):
        t = dict(T(1), artists=["Queen"], artist_ids=[""])
        self.assertFalse(self.e._ban_artist(t))
        self.assertEqual(self.e.settings["blocked_artists"], [])
        self.assertIn("Queen", self.e.settings["blocklist"])
        m = rules.merged({"blocked_artists": ["short|X", "1dfeR4HaWDbWqFHLkxsg1d|Queen", "|Name"]})
        self.assertEqual(m["blocked_artists"], ["1dfeR4HaWDbWqFHLkxsg1d|Queen"])

    def test_local_day_dst_boundaries(self):
        import datetime
        from engine import local_day
        u = lambda *a: datetime.datetime(*a, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual(local_day(u(2026, 3, 8, 5, 59)), "2026-03-07")      # 23:59 CST the evening before the switch
        self.assertEqual(local_day(u(2026, 3, 8, 6, 0)), "2026-03-08")       # midnight CST
        self.assertEqual(local_day(u(2026, 3, 9, 4, 59)), "2026-03-08")      # after the switch midnight moves to 05:00 UTC
        self.assertEqual(local_day(u(2026, 3, 9, 5, 0)), "2026-03-09")
        self.assertEqual(local_day(u(2026, 11, 1, 4, 59)), "2026-10-31")     # last CDT midnight is 05:00 UTC
        self.assertEqual(local_day(u(2026, 11, 1, 5, 0)), "2026-11-01")
        self.assertEqual(local_day(u(2026, 11, 2, 5, 59)), "2026-11-01")     # then CST: midnight is 06:00 UTC
        self.assertEqual(local_day(u(2026, 11, 2, 6, 0)), "2026-11-02")

    def test_bad_copies_are_pruned(self):
        d = store.folder()
        for i in range(8):
            (d / f"junk.json.bad-{1000 + i}").write_text("x")
        (d / "junk.json").write_text("{not json")
        store.load("junk.json", {})
        self.assertLessEqual(len(list(d.glob("junk.json.bad-*"))), 5)
        for f in d.glob("junk.json*"):
            f.unlink()


class SongifyHandoffTests(AnnounceTierTests):
    def test_hand_off_and_back_restores_previous_values(self):
        self.e.save_settings({"requests_open": True, "chat_replies": False, "announce_track_on": True, "ov_alerts": True, "autostart_queue": True})
        self.assertFalse(self.e.songify_active())
        self.assertTrue(self.e.songify(True))
        s = self.e.settings
        for k in ("requests_open", "chat_requests", "chat_replies", "announce_track_on", "announce_request_on", "ov_alerts", "autostart_queue"):
            self.assertFalse(s[k], k)
        self.assertTrue(s["fallback_only_open"])
        self.assertTrue(self.e.public_state()["songify"])
        self.assertTrue(self.e.songify(True))                         # second press changes nothing, keeps the saved values
        self.assertFalse(self.e.songify(False))
        s = self.e.settings
        self.assertTrue(s["requests_open"] and s["announce_track_on"] and s["ov_alerts"] and s["autostart_queue"])
        self.assertFalse(s["chat_replies"])
        self.assertNotIn("songify_prev", store.load("config.json", {}))

    def test_take_back_without_saved_values_uses_the_normal_preset(self):
        self.e.apply_preset("songify")
        self.assertTrue(self.e.songify_active())
        self.assertFalse(self.e.songify(False))
        s = self.e.settings
        self.assertTrue(s["requests_open"] and s["chat_requests"] and s["chat_replies"] and s["ov_alerts"])

    def test_presets_are_hidden_from_the_list_but_exist(self):
        import config_schema as cs
        self.assertIn("songify", cs.PRESETS)
        self.assertIn("takeback", cs.PRESETS)
        for k in cs.PRESETS["songify"][2]:
            self.assertIn(k, rules.DEFAULTS if hasattr(rules, "DEFAULTS") else rules.merged({}))
