"""Songify-parity features: reward-only requests, refunds, global cooldown, playlist add, !songpos/!songnext/!songlike, role gates, blocklist import."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules  # noqa: E402
import store  # noqa: E402
from engine import Engine  # noqa: E402
from test_spotify import Clock, FakeApi, FakeAuth, T  # noqa: E402


class SongifyTests(unittest.TestCase):
    def setUp(self):
        store.save("state.json", {})
        store.save("config.json", {})
        self.api, self.clock = FakeApi(), Clock()
        self.api.added, self.api.liked = [], []
        self.api.playlist_add = lambda pid, uri: self.api.added.append((pid, uri))
        self.api.save_track = lambda tid: self.api.liked.append(tid)
        self.e = Engine(self.api, FakeAuth(), self.clock)
        self.e.save_settings({"requests_open": True, "per_user_limit": 0})

    def sr(self, user, n, roles=("viewer",), redeem=False):
        return self.e.chat(user, f"!sr song {n}", roles, redeem)

    def play(self, n, progress=0):
        self.api.playing, self.api.progress = f"spotify:track:t{n}", progress
        self.e.tick()

    def test_bonus_queues_per_sub_tier(self):
        st = {"per_user_limit": 2, "bonus_t1": 1, "bonus_t2": 3, "bonus_t3": 5, "bonus_vip": 2, "limit_sub": -1, "limit_vip": -1}
        self.e.save_settings(st)
        s = self.e.settings
        lim = lambda *r: rules.limit_for(s, set(r))
        self.assertEqual(lim("viewer"), 2)
        self.assertEqual(lim("sub"), 3)          # plain "sub" = Tier 1
        self.assertEqual(lim("sub", "sub_t1"), 3)
        self.assertEqual(lim("sub", "sub_t2"), 5)
        self.assertEqual(lim("sub", "sub_t3"), 7)
        self.assertEqual(lim("vip"), 4)
        self.assertEqual(lim("vip", "sub", "sub_t3"), 7)   # best bonus wins, not the sum
        self.assertEqual(rules.merged({"sub_extra": 4})["bonus_t3"], 4)    # old setting migrates

    def test_outcomes_played_vs_skipped(self):
        self.play(1, 5000)
        self.play(2, 5000)                                   # cut off 195s early by hand in Spotify
        self.assertEqual(self.e.queue.history[0]["outcome"], "skipped")
        self.assertEqual(self.e.queue.history[0]["skipped_by"], "spotify")
        self.play(2, 199000)
        self.play(3, 0)                                      # ran to the end
        self.assertEqual(self.e.queue.history[0]["outcome"], "played")
        self.play(3, 10000)
        self.e.chat("mod", "!skip", ("mod",))                # skipped through chat
        self.e._prev_pb = None
        self.play(4, 0)
        self.assertEqual((self.e.queue.history[0]["outcome"], self.e.queue.history[0]["skipped_by"]), ("skipped", "mod"))

    def test_skipped_song_cooldown_and_song_log(self):
        self.e.save_settings({"skip_cooldown_min": 60, "dup_cooldown_min": 0})
        self.play(5, 1000)
        self.play(6, 0)                                      # t5 skipped
        r = self.sr("ann", 5)
        self.assertEqual(r["code"], "dup_skipped")
        self.e.save_settings({"skip_cooldown_min": 0})
        self.assertTrue(self.sr("ann", 5)["ok"])
        self.e.chat("ann", "!oops", ("viewer",))             # wrong song
        log = self.e.song_log()
        self.assertEqual(log["now"]["title"], "Song 6")
        self.assertEqual(log["recent"][0]["outcome"], "skipped")
        self.assertEqual(log["skipped"][0]["title"], "Song 5")
        self.assertEqual([x["title"] for x in log["lastHour"]], ["Song 5"])
        self.assertEqual((log["withdrawn"][0]["reason"], log["withdrawn"][0]["user"]), ("oops", "ann"))

    def test_host_sub_tier_fields_drive_bonus_queues(self):
        import server
        server.engine = self.e
        self.e.save_settings({"per_user_limit": 1, "bonus_t1": 1, "bonus_t2": 2, "bonus_t3": 4, "bonus_vip": 3})

        def n_accepted(user, **host):
            ok = 0
            for i in range(10, 20):
                r = server.p_chat_command(None, {"command": "sr", "args": f"song {i + hash(user) % 5 * 0}", "user": user, "role": "viewer", **host})
                ok += bool(r["ok"])
            return ok
        self.assertEqual(n_accepted("v0", subTier=0), 1)
        self.e.queue.clear()
        self.assertEqual(n_accepted("t1", isSub=True, subTier=1), 2)
        self.e.queue.clear()
        self.assertEqual(n_accepted("t2", isSub=True, subTier=2), 3)
        self.e.queue.clear()
        self.assertEqual(n_accepted("t3", isSub=True, subTier=3000), 5)
        self.e.queue.clear()
        self.assertEqual(n_accepted("vv", isVip=True, subTier=0), 4)

    def test_higher_sub_tiers_rank_first_in_a_round(self):
        for user, roles, n in (("v", {"viewer"}, 3), ("a", {"sub", "sub_t1"}, 4), ("c", {"sub", "sub_t3"}, 5), ("b", {"sub", "sub_t2"}, 6)):
            self.assertTrue(self.e.chat(user, f"!sr song {n}", roles)["ok"])
        self.assertEqual([i["requester"] for i in self.e.queue.items], ["c", "b", "a", "v"])
        self.e.save_settings({"sub_tier_priority": False})
        self.assertEqual(rules.tier_for(self.e.settings, {"sub", "sub_t3"}), 1)

    def test_srban_srunban(self):
        self.assertEqual(self.e.chat("ann", "!srban troll", ("viewer",))["code"], "denied")      # viewers can't
        self.assertTrue(self.sr("troll", 2)["ok"])
        r = self.e.chat("mod", "!srban @Troll", ("mod",))
        self.assertTrue(r["ok"])
        self.assertIn("troll", r["reply"])
        self.assertEqual(self.e._own_settings()["blocked_users"], ["troll"])
        self.assertEqual(self.sr("troll", 3)["code"], "user_blocked")
        self.assertTrue(self.sr("ann", 3)["ok"])
        self.e.chat("mod", "!srban troll", ("mod",))                                              # no duplicate entries
        self.assertEqual(self.e._own_settings()["blocked_users"], ["troll"])
        self.assertEqual(Engine(self.api, FakeAuth(), self.clock)._own_settings()["blocked_users"], ["troll"])   # persists
        self.assertFalse(self.e.chat("mod", "!srban", ("mod",))["ok"])                            # usage
        self.assertTrue(self.e.chat("mod", "!srunban troll", ("mod",))["ok"])
        self.assertEqual(self.e._own_settings()["blocked_users"], [])
        self.assertTrue(self.sr("troll", 4)["ok"])

    def test_reward_only_blocks_chat_but_not_redeem_or_mods(self):
        self.e.save_settings({"chat_requests": False})
        r = self.sr("ann", 3)
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], "reward_only")
        self.assertTrue(self.sr("ann", 3, redeem=True)["ok"])
        self.assertTrue(self.sr("mod", 2, roles=("mod",))["ok"])

    def test_refund_flag_on_redeem_rejections_only(self):
        self.e.save_settings({"max_length_s": 60})
        r = self.sr("ann", 3, redeem=True)               # 200s track > 60s
        self.assertEqual(r["code"], "too_long")
        self.assertTrue(r["refund"])
        self.assertIn("refunded", r["reply"])
        self.assertFalse(self.sr("bob", 3)["refund"], "a typed !sr has no points to refund")
        self.e.save_settings({"refund_on": []})
        self.assertFalse(self.sr("cy", 3, redeem=True)["refund"])

    def test_refund_rule_trolls_get_nothing(self):
        self.e.save_settings({"blocklist": ["song 9"], "refund_on": ["blocked", "dup_recent", "dup_skipped", "full"]})
        self.assertFalse(self.sr("ann", 9, redeem=True)["refund"], "banned song: no refund even if listed")
        self.assertTrue(self.sr("bo", 4, redeem=True)["ok"])
        self.play(4, 199000)
        self.assertFalse(self.sr("cy", 4, redeem=True)["refund"], "same song within the hour: no refund")
        self.assertIn("full", self.e.settings["refund_on"])

    def test_skipped_or_removed_redeem_is_refunded(self):
        self.sr("ann", 1, redeem=True)
        self.sr("bo", 2, redeem=True)
        self.sr("cy", 3)                                     # typed, no points
        self.play(1, 5000)
        self.e.chat("mod", "!skip", ("mod",))
        self.e._prev_pb = None
        self.play(2, 0)
        r = self.e.pending_refunds(0)["refunds"]
        self.assertEqual([x["user"] for x in r], ["ann"])
        self.assertEqual(r[0]["why"], "skipped")
        self.assertEqual(self.e.pending_refunds(r[0]["seq"])["refunds"], [])
        self.e.save_settings({"blocklist": ["song 2"]})           # banned after the fact: troll, no refund
        self.e.chat("mod", "!skip", ("mod",))
        self.e._prev_pb = None
        self.play(3, 0)
        self.assertEqual(len(self.e.pending_refunds(0)["refunds"]), 1)

    def test_public_queue_widget_payload(self):
        self.sr("ann", 3)
        q = self.e.public_queue()
        self.assertEqual(q["count"], 1)
        self.assertEqual(q["items"][0]["requester"], "ann")
        self.assertNotIn("id", q["items"][0])
        self.assertNotIn("uri", q["items"][0])

    def test_global_cooldown_between_any_two_requests(self):
        self.e.save_settings({"global_cooldown_s": 30})
        self.assertTrue(self.sr("ann", 3)["ok"])
        r = self.sr("bob", 2)
        self.assertEqual(r["code"], "cooldown")
        self.assertTrue(self.sr("mod", 4, roles=("mod",))["ok"], "mods bypass")
        self.clock.t += 31
        self.assertTrue(self.sr("bob", 2)["ok"])

    def test_playlist_add_on_accept_and_failure_is_harmless(self):
        self.e.save_settings({"playlist_add": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x"})
        self.assertTrue(self.sr("ann", 3)["ok"])
        self.assertEqual(self.api.added, [("37i9dQZF1DXcBWIGoYBM5M", "spotify:track:t3")])
        self.api.playlist_add = lambda *a: (_ for _ in ()).throw(RuntimeError("403"))
        self.assertTrue(self.sr("bob", 2)["ok"])

    def test_master_view_mod_actions(self):
        self.assertFalse(self.e.mod_action("like")["ok"], "nothing playing")
        self.play(5)
        self.assertTrue(self.e.mod_action("like")["ok"])
        self.assertEqual(self.api.liked, ["id5xxxxxxxxxxxxxxxxxxx"])
        r = self.e.mod_action("ban_artist")
        self.assertTrue(r["ok"] and r["artist"])
        self.assertIn(r["artist"].lower(), [b.lower() for b in self.e.settings["blocklist"]])
        self.play(6)
        self.assertTrue(self.e.mod_action("ban_song")["ok"])
        self.api.previous = lambda: None
        self.assertTrue(self.e.mod_action("previous")["ok"])
        with self.assertRaises(Exception):
            self.e.mod_action("nope")

    def test_ban_unban_pardon_and_suspend(self):
        mod = ("mod",)
        self.play(5)
        r = self.e.chat("mod", "!bansong", mod)
        self.assertEqual(r["code"], "blocked")
        self.assertTrue(self.e.settings["blocklist"])
        self.assertEqual(self.e.chat("mod", "!unbansong", mod)["code"], "unbansong")
        self.assertFalse(self.e.settings["blocklist"])
        self.play(6)
        self.assertEqual(self.e.chat("mod", "!banartist", mod)["code"], "artist_blocked")
        self.assertTrue(self.e.settings["blocklist"])
        self.assertEqual(self.e.chat("mod", "!pardon artist", mod)["code"], "unbanartist")
        self.assertFalse(self.e.settings["blocklist"])
        self.assertFalse(self.e.chat("mod", "!unbanartist", mod)["ok"], "nothing to unban")
        self.assertFalse(self.e.chat("viewer1", "!bansong", ("viewer",))["ok"], "viewers cannot")
        # suspend: blocked until the time is up, then back
        self.assertFalse(self.e.chat("mod", "!srsuspend bob", mod)["ok"], "needs a time")
        self.assertEqual(self.e.chat("mod", "!srsuspend bob 10m", mod)["code"], "srsuspend")
        self.assertEqual(self.sr("bob", 2)["code"], "user_blocked")
        self.clock.t += 11 * 60
        self.assertTrue(self.sr("bob", 2)["ok"])
        self.assertEqual(self.e.chat("mod", "!songclear", mod)["code"], "clear")

    def test_seq_survives_restart_and_now_info_idle(self):
        self.assertGreaterEqual(self.e._ann_seq, int(self.clock()))
        self.assertGreaterEqual(self.e._ref_seq, int(self.clock()))
        self.e.pb = None
        n = self.e.now_info()
        self.assertEqual((n["title"], n["is_playing"], n["volume"]), ("", False, None))
        self.play(5)
        n = self.e.now_info()
        self.assertTrue(n["title"] and n["duration_ms"] >= n["progress_ms"] >= 0)

    def test_mod_queue_commands(self):
        mod = ("mod",)
        for u, n in (("ann", 3), ("bob", 4), ("cy", 5)):
            self.assertTrue(self.sr(u, n)["ok"])
        names = lambda: [i["requester"] for i in self.e.queue.items]
        self.assertEqual(self.e.chat("mod", "!srtop 3", mod)["code"], "srtop")
        self.assertEqual(names()[0], "cy")
        self.assertEqual(self.e.chat("mod", "!srmove 1 3", mod)["code"], "srmove")
        self.assertEqual(names()[2], "cy")
        self.assertFalse(self.e.chat("mod", "!srmove 9 1", mod)["ok"])
        self.assertFalse(self.e.chat("mod", "!srremove", mod)["ok"])
        self.assertEqual(self.e.chat("mod", "!srremove 1", mod)["code"], "srremove")
        self.assertEqual(len(names()), 2)
        self.assertEqual(self.e.chat("mod", "!srremove bob", mod)["code"], "srremove")
        self.assertNotIn("bob", names())
        self.assertFalse(self.e.chat("mod", "!srremove nobody", mod)["ok"])
        self.assertFalse(self.e.chat("viewer1", "!srremove 1", ("viewer",))["ok"], "viewers cannot")

    def test_lyrics_toggle_and_parse(self):
        import lyrics
        lyrics._cache.clear()
        self.assertEqual(lyrics.parse_lrc("[00:01.50] hi\n[01:02.00]yo")[1], {"t": 62000, "text": "yo"})
        self.e.lyrics_http = lambda url: {"syncedLyrics": "[00:01.00] a", "plainLyrics": "a"}
        self.play(3)
        r = self.e.lyrics()
        self.assertTrue(r["enabled"] and r["found"] and r["synced"][0]["text"] == "a")
        self.e.cfg.setdefault("settings", {})["lyrics_on"] = False
        self.assertFalse(self.e.lyrics()["enabled"])

    def test_vote_skip_scaled_once_and_vol_read(self):
        self.sr("ann", 3)
        self.play(3)
        calls = []
        orig = self.e.skip
        self.e.skip = lambda *a, **k: (calls.append(k), orig(*a, **k))[1]
        r = self.e.chat("v1", "!skip", ("viewer",), active_chatters=10)       # 40% of 10 = need 4
        self.assertEqual((r["ok"], r["code"]), (True, "vote"))
        for u in ("v2", "v3"):
            self.e.chat(u, "!skip", ("viewer",), active_chatters=10)
        self.assertEqual(calls, [])
        self.e.chat("v4", "!skip", ("viewer",), active_chatters=10)
        self.e.chat("v5", "!skip", ("viewer",), active_chatters=10)           # still the same track: no second skip
        self.e.chat("v6", "!skip", ("viewer",), active_chatters=10)
        self.assertEqual(len(calls), 1)
        self.play(10)
        self.e.chat("w1", "!skip", ("viewer",), skip_need=2)
        self.assertEqual(self.e.chat("w2", "!skip", ("viewer",), active_chatters=50, skip_need=2)["code"], "skipped")   # Host skipNeed wins
        self.assertEqual(self.e.chat("v1", "!skip", ("viewer",), active_chatters=1)["code"], "vote")    # floor 2 applies
        v = self.e.chat("anyone", "!vol", ("viewer",))
        self.assertEqual(v["code"], "volume")                                  # viewers can read the volume
        self.assertNotEqual(self.e.chat("anyone", "!vol 99", ("viewer",))["code"], "volume_set")   # but not set it

    def test_channel_playlist_add(self):
        self.assertEqual(self.e.playlist_add("mod")["code"], "no_playlist")
        pid = "P" * 22
        self.e.set_channel_playlist(pid, "Stream faves")
        added = []
        self.api.context_tracks = lambda kind, cid, limit=100: []
        self.api.playlist_add = lambda p, u: added.append((p, u))
        self.assertEqual(self.e.playlist_add("mod")["code"], "none")           # nothing playing
        self.play(3)
        r = self.e.playlist_add("mod")
        self.assertEqual((r["ok"], r["code"], r["playlist"]), (True, "added", "Stream faves"))
        self.assertEqual(added[0][0], pid)
        self.assertEqual(self.e.playlist_add("mod2")["code"], "duplicate")     # already in it
        self.assertEqual(len(added), 1)
        self.assertEqual(self.e.playlist_add("mod", "bad id")["code"], "none")
        for n in range(4, 9):
            self.e.playlist_add("spam", ("id%d" % n).ljust(22, "x"))
        self.assertEqual(self.e.playlist_add("spam", "idzzzzzzzzzzzzzzzzzzzz"[:22].ljust(22, "z"))["code"], "rate")
        self.assertEqual(self.e.site_snapshot()["status"]["channelPlaylist"], {"name": "Stream faves"})

    def test_youtube_link_request(self):
        import ytlink
        from fakes import trk
        self.e.yt_http = lambda url: {"title": "Artist - Song 3 (Official Video) [4K]", "author_name": "ArtistVEVO"}
        good = trk(3)
        good["name"], good["artists"] = "Song 3", ["Artist"]
        self.api.search = lambda q, limit=8: [{"id": good["id"], "uri": good["uri"], "name": "Song 3", "artists": ["Artist"], "duration_ms": 200000, "explicit": False, "album": "A", "art": ""}]
        url = "https://youtu.be/dQw4w9WgXcQ?si=abc"
        got = self.e.resolve(url)
        self.assertEqual(got and got[0]["name"], "Song 3")
        self.e.yt_http = lambda url: {"title": "Totally Different Thing", "author_name": "Someone Else"}
        self.e._search_cache.clear()
        self.assertEqual(self.e.resolve("https://www.youtube.com/watch?v=aaaaaaaaaaa&list=PLx"), [])         # below threshold: not found
        self.e.yt_http = lambda url: None
        self.e._search_cache.clear()
        self.assertEqual(self.e.resolve("https://music.youtube.com/watch?v=bbbbbbbbbbb"), [])
        self.e.cfg.setdefault("settings", {})["yt_links"] = False
        self.e.yt_http = lambda url: {"title": "Artist - Song 3", "author_name": "x"}
        self.e._search_cache.clear()
        self.assertEqual(self.e.resolve(url), [])                                                            # switched off
        self.assertIsNone(ytlink.video_id("https://notyoutube.com/watch?v=dQw4w9WgXcQ"))

    def test_leaderboard(self):
        self.sr("ann", 3)
        self.play(3)
        self.play(3, progress=199000)
        self.play(9)
        self.e.skip(force=True, by="mod")
        self.play(10)
        lb = self.e.leaderboard()
        self.assertEqual(lb["requesters"][0], {"name": "ann", "count": 1})
        self.assertTrue(lb["most_played"] and lb["most_played"][0]["count"] >= 1)
        self.assertTrue(lb["most_skipped"])
        self.assertNotIn("token", str(lb).lower())

    def test_pos_next_and_like(self):
        self.sr("ann", 3)
        self.sr("bob", 2)
        self.assertIn("#2", self.e.chat("bob", "!songpos", ("viewer",))["reply"])
        self.assertIn("nothing", self.e.chat("zed", "!songpos", ("viewer",))["reply"])
        self.assertIn("Song 3", self.e.chat("zed", "!songnext", ("viewer",))["reply"])
        self.api.playing = "spotify:track:t5"
        self.e.tick()
        self.assertEqual(self.e.chat("mod", "!songlike", ("mod",))["code"], "liked")
        self.assertEqual(self.api.liked, ["id5xxxxxxxxxxxxxxxxxxx"])
        self.assertFalse(self.e.chat("zed", "!songlike", ("viewer",))["ok"], "viewers cannot like")

    def test_skip_redeem_skips_immediately(self):
        self.api.playing = "spotify:track:t1"
        self.e.tick()
        r = self.e.chat("ann", "!skip", ("viewer",), redeem=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["code"], "skipped")
        self.assertIn(("next",), [c[:1] for c in self.api.calls])

    def test_command_role_gate(self):
        self.e.save_settings({"cmd_roles": ["songnext=sub,mod", "!queue=mod"]})
        self.assertFalse(self.e.chat("zed", "!songnext", ("viewer",))["ok"])
        self.assertTrue(self.e.chat("sue", "!songnext", ("sub",))["ok"])
        self.assertTrue(self.e.chat("mo", "!queue", ("mod",))["ok"])
        self.assertEqual(self.e.chat("zed", "!queue", ("viewer",))["code"], "denied")
        self.assertTrue(self.e.chat("boss", "!queue", ("broadcaster",))["ok"])
        self.assertTrue(rules.command_allowed(self.e.settings, "song", ("viewer",)))

    def test_blocklist_import_dedupes_and_blocks(self):
        txt = "# comment\n4uLU6hMCjMI75M1A2tKUQC\nspotify:track:4uLU6hMCjMI75M1A2tKUQC\n\nBad Word\n"
        r = self.e.import_blocklist(txt)
        self.assertEqual(r["added"], 2)
        self.assertEqual(self.e.import_blocklist(txt)["added"], 0)
        t = T(1)
        t["id"], t["uri"] = "4uLU6hMCjMI75M1A2tKUQC", "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
        self.assertTrue(rules.blocked_reason(self.e.settings, t))


if __name__ == "__main__":
    unittest.main()



class NonJsonSuccessTest(unittest.TestCase):
    def test_2xx_text_body_is_not_a_crash(self):
        import io, urllib.request
        from unittest import mock
        import spotify_api

        class R(io.BytesIO):
            status = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(urllib.request, "urlopen", return_value=R(b"Player command ok")):
            st, hd, js = spotify_api.default_http("PUT", "https://x", {}, None)
        self.assertEqual((st, js), (200, None))

