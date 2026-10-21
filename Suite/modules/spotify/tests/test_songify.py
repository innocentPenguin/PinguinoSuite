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

