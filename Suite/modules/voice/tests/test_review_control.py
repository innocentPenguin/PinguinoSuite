"""Hourly review + spoken control tests (no network, no audio). Run from modules/voice: python -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
import urllib.error

os.environ["PINGUINO_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import review as rv
import voicectl as vc

W = ["pinguinobot", "pinguino bot", "penguino bot"]


class Parse(unittest.TestCase):
    def test_wake_word_is_fuzzy_and_must_lead(self):
        self.assertEqual(vc.strip_wake("Pinguino bot, change the game to Rocket League", W), "change the game to rocket league".split())
        self.assertEqual(vc.strip_wake("hey pinguinobot confirm", W), ["confirm"])
        self.assertEqual(vc.strip_wake("penguino but cancel", W), ["cancel"])
        self.assertIsNone(vc.strip_wake("I told pinguinobot to change the game", W))
        self.assertIsNone(vc.strip_wake("change the game to anything", W))

    def test_game_title_timeout(self):
        p = lambda t: vc.parse(vc.strip_wake("pinguinobot " + t, W))
        self.assertEqual(p("change the game to Rocket League"), {"action": "game", "value": "rocket league"})
        self.assertEqual(p("set my title to Chill ranked grind"), {"action": "title", "value": "chill ranked grind"})
        self.assertEqual(p("change the stream title to hello world"), {"action": "title", "value": "hello world"})
        self.assertEqual(p("timeout snowy roses for 5 minutes"), {"action": "timeout", "user": "snowyroses", "seconds": 300})
        self.assertEqual(p("time out user bob for thirty seconds")["seconds"], 30)
        self.assertEqual(p("timeout bob for an hour")["seconds"], 3600)
        self.assertEqual(p("timeout bob for twenty five minutes")["seconds"], 1500)
        self.assertTrue(p("timeout bob for a while")["bad"])
        self.assertEqual(p("confirm"), {"control": "confirm"})
        self.assertEqual(p("never mind"), {"control": "cancel"})
        self.assertIsNone(p("tell me a joke"))

    def test_name_matching_is_careful(self):
        ch = ["snowyroses_", "pineyapplie", "karacius25", "karacius26"]
        self.assertEqual(vc.resolve_user("snowy roses", ch), "snowyroses_")
        self.assertEqual(vc.resolve_user("piney applie", ch), "pineyapplie")
        self.assertIsNone(vc.resolve_user("karacius", ch))        # two close candidates: refuse to guess
        self.assertIsNone(vc.resolve_user("zzzz", ch))


class Flow(unittest.TestCase):
    def setUp(self):
        self.cfg = config.defaults()
        self.cfg["control"]["enabled"] = True
        self.sent, self.said, self.t = [], [], [1000.0]
        self.boom = None
        self.ctl = vc.Control(lambda: self.cfg, self.host, speak=self.said.append, chatters=lambda: ["snowyroses_", "modguy"], now=lambda: self.t[0],
                              overlaps=lambda a, b: self.bot and a < 500 < b)
        self.bot = False

    def host(self, path, body):
        if self.boom:
            raise self.boom
        self.sent.append((path, body))
        return {"ok": True}

    def test_bot_itself_is_never_a_timeout_target(self):
        self.ctl.chatters = lambda: ["pinguinobot", "snowyroses_"]
        r = self.ctl.hear("pinguinobot timeout pinguinobot for 5 minutes")
        self.assertEqual(r["outcome"], "refused")
        self.assertEqual(self.sent, [])

    def test_suggestion_tolerates_missing_section(self):
        import review as rv
        new = rv.apply_suggestion({"output.volume": 45}, {})
        self.assertEqual(new["output"]["volume"], 45)

    def test_off_by_default_and_nothing_without_wake(self):
        self.cfg["control"]["enabled"] = False
        self.assertIsNone(self.ctl.hear("pinguinobot change the game to x"))
        self.cfg["control"]["enabled"] = True
        self.assertIsNone(self.ctl.hear("just talking about the game"))
        self.assertEqual(self.sent, [])

    def test_confirm_then_act(self):
        r = self.ctl.hear("pinguinobot change the game to rocket league")
        self.assertEqual(r["outcome"], "pending")
        self.assertEqual(self.sent, [])                                   # nothing happened yet
        self.assertIn("Confirm", self.said[-1])
        self.assertNotIn("pinguinobot", self.said[-1].lower())            # its own voice must never contain the wake word
        r = self.ctl.hear("pinguinobot confirm")
        self.assertEqual(r["outcome"], "done")
        self.assertEqual(self.sent, [("/api/channel/update", {"game": "Rocket League"})])

    def test_timeout_resolves_real_chatter_and_caps(self):
        self.ctl.hear("pinguinobot timeout snowy roses for 5 minutes")
        self.ctl.confirm()
        self.assertEqual(self.sent[0][0], "/api/mod/timeout")
        self.assertEqual(self.sent[0][1]["user"], "snowyroses_")
        self.assertEqual(self.sent[0][1]["seconds"], 300)
        self.t[0] += 10
        self.assertEqual(self.ctl.hear("pinguinobot timeout snowy roses for 3 hours")["outcome"], "refused")   # over the cap
        self.assertEqual(self.ctl.hear("pinguinobot timeout nobody here for 1 minute")["outcome"], "refused")  # not a chatter today
        self.cfg["control"]["protected"] = ["modguy"]
        self.assertEqual(self.ctl.hear("pinguinobot timeout modguy for 1 minute")["outcome"], "refused")

    def test_unsafe_values_refused(self):
        for t in ("change the title to my password is hunter2 and key sk-abcdefghijklmnopqrstuvwxyz123456", "change the title to you are a fucking idiot", "change the game to x"):
            self.assertEqual(self.ctl.hear("pinguinobot " + t)["outcome"], "refused", t)
        self.assertEqual(self.ctl.hear("pinguinobot change the title to " + "word " * 60)["outcome"], "refused")
        self.assertEqual(self.sent, [])

    def test_allow_switch_and_cooldown(self):
        self.cfg["control"]["allow"]["game"] = False
        self.assertEqual(self.ctl.hear("pinguinobot change the game to rocket league")["outcome"], "blocked")
        self.cfg["control"]["require_confirm"] = False
        self.assertEqual(self.ctl.hear("pinguinobot change the title to hello there")["outcome"], "done")
        self.assertEqual(self.ctl.hear("pinguinobot change the title to again")["outcome"], "blocked")    # too soon
        self.t[0] += 10
        self.assertEqual(self.ctl.hear("pinguinobot change the title to again")["outcome"], "done")

    def test_expires_and_cancel(self):
        self.ctl.hear("pinguinobot change the title to hello there")
        self.t[0] += 60
        self.assertEqual(self.ctl.hear("pinguinobot confirm")["outcome"], "expired")
        self.assertEqual(self.sent, [])
        self.ctl.hear("pinguinobot change the title to hello there")
        self.assertEqual(self.ctl.hear("pinguinobot cancel")["outcome"], "cancelled")
        self.assertEqual(self.ctl.hear("pinguinobot confirm")["outcome"], "ignored")                    # nothing waiting

    def test_never_obeys_its_own_voice(self):
        self.bot = True
        self.assertEqual(self.ctl.hear("pinguinobot change the game to rocket league", at=(499, 501))["outcome"], "ignored")
        self.assertIsNone(self.ctl.pending)

    def test_unsure_line_ignored(self):
        self.assertEqual(self.ctl.hear("pinguinobot change the game to rocket league", unsure=0.9)["outcome"], "ignored")

    def test_host_without_endpoint_or_failing(self):
        self.cfg["control"]["require_confirm"] = False
        self.boom = urllib.error.HTTPError("u", 404, "nf", {}, None)
        self.assertEqual(self.ctl.hear("pinguinobot change the title to hello there")["outcome"], "unsupported")
        self.t[0] += 10
        self.boom = OSError("down")
        self.assertEqual(self.ctl.hear("pinguinobot change the title to hello there")["outcome"], "failed")


class Review(unittest.TestCase):
    def data(self, **kw):
        d = {"since": 0, "until": 3600, "speak": [], "lines": [], "chat": [], "console": [], "vlog": [], "control": [], "missing": []}
        d.update(kw)
        return d

    def ids(self, rep):
        return {f["id"] for f in rep["findings"]}

    def test_quiet_hour_is_clean(self):
        rep = rv.analyse(self.data(speak=[{"ts": 100, "kind": "follow", "outcome": "spoken", "text": "Hi a", "user": "a"}]), config.defaults()["review"])
        self.assertEqual(rep["findings"], [])
        self.assertEqual(rep["score"], 100)

    def test_talk_over_and_complaint(self):
        sp = [{"ts": 100 + i * 100, "kind": "follow", "outcome": "spoken", "text": f"welcome person {i}", "seconds": 3} for i in range(4)]
        lines = [{"s": 98 + i * 100, "e": 103 + i * 100, "text": "so then I went mid and got the boost", "unsure": 0} for i in range(4)]
        lines.append({"s": 305, "e": 308, "text": "okay that bot is too loud", "unsure": 0})
        rep = rv.analyse(self.data(speak=sp, lines=lines), config.defaults()["review"])
        self.assertIn("talk_over", self.ids(rep))
        self.assertIn("complaints", self.ids(rep))
        self.assertLess(rep["score"], 100)
        sug = next(f for f in rep["findings"] if f["id"] == "complaints")["suggest"]
        self.assertIn("limits.rate_per_min", sug["set"])

    def test_repeats_drops_errors_console_control(self):
        sp = [{"ts": 10 + i, "kind": "follow", "outcome": "spoken", "text": "hello again friend"} for i in range(4)]
        sp += [{"ts": 50 + i, "kind": "chat", "outcome": "rate_limited", "detail": "x"} for i in range(8)]
        sp += [{"ts": 70, "kind": "sub", "outcome": "error", "detail": "no device"}]
        con = [{"_t": 5, "module": "listen", "level": "error", "msg": "mic gone"}] * 2
        ctl = [{"_t": 6, "ts": 6, "outcome": "failed", "detail": "Host refused"}]
        rep = rv.analyse(self.data(speak=sp, console=con, control=ctl), config.defaults()["review"])
        self.assertTrue({"repeats", "drops", "play_errors", "console", "control"} <= self.ids(rep))
        self.assertEqual(rep["findings"][0]["sev"], "high")               # most serious first

    def test_check_can_be_switched_off(self):
        c = config.defaults()["review"]
        c["checks"]["console"] = False
        rep = rv.analyse(self.data(console=[{"_t": 5, "module": "x", "level": "error", "msg": "m"}]), c)
        self.assertNotIn("console", self.ids(rep))

    def test_apply_suggestion_is_allow_listed_and_clamped(self):
        cur = config.defaults()
        new = rv.apply_suggestion({"output.volume": 400, "limits.rate_per_min": 8}, cur)
        self.assertEqual(new["output"]["volume"], 100)
        self.assertEqual(new["limits"]["rate_per_min"], 8)
        self.assertEqual(cur["output"]["volume"], 60)                     # original untouched
        for bad in ({"master": True}, {"control.enabled": True}, {"cloud.allow": True}):
            with self.assertRaises(ValueError):
                rv.apply_suggestion(bad, cur)

    def test_reports_saved_listed_and_incident_written(self):
        sp = [{"ts": 70, "kind": "sub", "outcome": "error", "detail": "no device"}]
        rep = rv.analyse(self.data(speak=sp), config.defaults()["review"])
        rv.save_report(rep, 3)
        self.assertEqual(rv.list_reports()[0]["id"], rep["id"])
        self.assertEqual(rv.get_report(rep["id"])["score"], rep["score"])
        self.assertTrue(os.path.getsize(config.path("incidents.jsonl")) > 0)
        with self.assertRaises(ValueError):
            rv.get_report("../../etc/passwd")

    def test_scheduler_hourly_only_while_live(self):
        t = [1000.0]
        live = [False]
        cfgd = config.defaults()
        cfgd["review"]["interval_min"] = 60
        r = rv.Reviewer(lambda: cfgd, lambda: [], "http://127.0.0.1:9", lambda: live[0], now=lambda: t[0])
        self.assertIsNone(r.tick())                                       # offline: nothing
        live[0] = True
        self.assertIsNone(r.tick())                                       # just went live
        t[0] += 3500
        self.assertIsNone(r.tick())
        t[0] += 200
        first = r.tick()
        self.assertEqual(first["reason"], "hourly")
        self.assertTrue(any("Listen" in m for m in first["missing"]))     # unreachable Listen is reported, not fatal
        t[0] += 400
        live[0] = False
        self.assertEqual(r.tick()["reason"], "stream ended")
        cfgd["review"]["enabled"] = False
        self.assertIsNone(r.tick())


class ReadJsonl(unittest.TestCase):
    def test_text_or_odd_times_in_other_modules_logs_do_not_crash(self):
        path = os.path.join(tempfile.mkdtemp(), "x.jsonl")
        with open(path, "w", encoding="utf8") as f:
            f.write('{"ts": "100"}\n{"ts": "abc"}\n{"ts": [1]}\n[1,2]\n{"ts": 120.5}\nnot json\n{"ts": "1970-01-01T00:03:20+0000"}\n')
        rows = rv.read_jsonl(path, 0, 1000)
        self.assertEqual(sorted(r["_t"] for r in rows), [100.0, 120.5, 200.0])


if __name__ == "__main__":
    unittest.main()
