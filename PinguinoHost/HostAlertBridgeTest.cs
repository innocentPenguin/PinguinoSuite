using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "alerttest": !tip, !alert -> Multi calls, enriched activity items, streak/watchtime/anniversary/comeback fires</summary>
    public static class AlertBridgeTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        public static void Run()
        {
            var calls = new List<KeyValuePair<string, JObject>>(); var said = new List<string>();
            AlertBridge.TestPost = (p, b) => { lock (calls) calls.Add(new KeyValuePair<string, JObject>(p, (JObject)b.DeepClone())); return new JObject { { "ok", true }, { "text", "test " + (string)b["type"] + " queued" } }; };
            Action<string> say = s => said.Add(s);

            // 1. !alert (mods only, silent for others), forwarded to Multi with the parsed args
            FeatureCommands.Handle("viewer1", "!alert test follow", 1, say); Check(said.Count == 0 && calls.Count == 0, "!alert is silent for non-mods");
            FeatureCommands.Handle("modguy", "!alert test sub penguin 5 tier2 msg", 3, say);
            var c = calls.LastOrDefault();
            Check(c.Key == "/api/alerts/test" && (string)c.Value["type"] == "sub" && (string)c.Value["user"] == "penguin" && (double)c.Value["amount"] == 5 && (string)c.Value["tier"] == "2" && (string)c.Value["source"] == "chat" && ((JArray)c.Value["variant"]).Count == 2, "!alert test sub penguin 5 tier2 msg -> body " + c.Value);
            Check(said.Count == 1 && said[0] == "test sub queued", "chat gets Multi's text only: " + string.Join("|", said));
            FeatureCommands.Handle("modguy", "!alert test follow", 3, say); Check((string)calls.Last().Value["user"] == "modguy", "no user given = the caller");
            FeatureCommands.Handle("modguy", "!alert testall", 3, say); FeatureCommands.Handle("modguy", "!alert stress 5", 3, say); FeatureCommands.Handle("modguy", "!alert profile night", 3, say); FeatureCommands.Handle("modguy", "!alert skip", 3, say); FeatureCommands.Handle("modguy", "!alert clear", 3, say);
            var paths = calls.Select(x => x.Key).ToList();
            Check(paths.Skip(2).SequenceEqual(new[] { "/api/alerts/testall", "/api/alerts/stress", "/api/alerts/control", "/api/alerts/control", "/api/alerts/control" }) && (string)calls[paths.Count - 3].Value["action"] == "profile:night", "testall / stress / profile / skip / clear go to the right Multi routes");

            // 2. !tip (mods), idempotent
            said.Clear(); long b0 = Economy.TBal("tipguy");
            FeatureCommands.Handle("viewer1", "!tip tipguy 5", 1, say); Check(Economy.TBal("tipguy") == b0 && said.Count == 0, "!tip is silent and pays nothing for non-mods");
            FeatureCommands.Handle("modguy", "!tipped tipguy 5", 3, say); FeatureCommands.Handle("modguy", "!tip tipguy 5", 3, say);
            Check(Economy.TBal("tipguy") - b0 == 7000 && said.Count >= 1 && said[0].Contains("7,000"), "!tip tipguy 5 pays 7000 once (repeat in the same minute is the same id): " + string.Join("|", said));
            FeatureCommands.Handle("modguy", "!tip tipguy 10 receipt-77", 3, say); FeatureCommands.Handle("modguy", "!tip tipguy 10 receipt-77", 3, say);
            Check(Economy.TBal("tipguy") - b0 == 27000, "explicit id: $10 = 20000, same id twice pays once");
            var tv = Economy.TippedView("tipguy"); Check((double)tv["total"] == 15 && (int)tv["count"] == 2 && (long)tv["last"] > 0 && (double)Economy.Me2("tipguy")["tipped"]["total"] == 15, "tipped {total,count,last} counts each tip id once, shown in /api/economy/me: " + tv);

            // 3. enriched activity items
            long since = (long)Latest.Activity(0, 1, "")["seq"];
            EventSub.Simulate("channel.subscription.message", "{\"user_login\":\"resubber\",\"tier\":\"2000\",\"cumulative_months\":14,\"streak_months\":6,\"message\":{\"text\":\"hello there\"}}", x => Program.DispatchEvent(x));
            EventSub.Simulate("channel.follow", "{\"user_login\":\"newfollower\"}", x => Program.DispatchEvent(x));
            var items = (JArray)Latest.Activity(since, 10, "")["items"]; var rs = items.OfType<JObject>().FirstOrDefault(i => (string)i["user"] == "resubber"); var fo = items.OfType<JObject>().FirstOrDefault(i => (string)i["user"] == "newfollower");
            Check(rs != null && !string.IsNullOrEmpty((string)rs["id"]) && (string)rs["tier"] == "2" && (int)rs["months"] == 14 && (int)rs["streak_months"] == 6 && (string)rs["message"] == "hello there" && (bool?)rs["sim"] == true, "resub item: id, tier 2, months 14, streak 6, message, sim flag: " + rs);
            Check(fo != null && (bool?)fo["first_time"] == true && (bool?)fo["sim"] == true, "follow item: first_time true, sim flag");
            Check(Economy.TBal("resubber") == 0 && Economy.TBal("newfollower") == 0, "simulated events pay nothing");

            // 3b. raids always alert (a 2-viewer raid is below RaidMinViewers 3 and still alerts); outgoing names the TARGET; sim/test and replays never fire
            AlertBridge.TestReset(); calls.Clear();
            Latest.Record("raid", new Dictionary<string, string> { { "userName", "aaronpryan" }, { "viewers", "2" }, { "eventId", "rd-1" } });
            Latest.Record("raid", new Dictionary<string, string> { { "userName", "aaronpryan" }, { "viewers", "2" }, { "eventId", "rd-1" } });
            Latest.Record("raid_out", new Dictionary<string, string> { { "userName", "pinguino" }, { "target", "evuto_" }, { "viewers", "12" }, { "eventId", "ro-1" } });
            Latest.Record("raid", new Dictionary<string, string> { { "userName", "simraider" }, { "viewers", "9" }, { "eventId", "rd-2" }, { "sim", "true" } });
            Thread.Sleep(500);
            var rf = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            var rin = rf.FirstOrDefault(f => (string)f["type"] == "raid"); var rout = rf.FirstOrDefault(f => (string)f["type"] == "raid_out");
            Check(rf.Count == 2, "raid + raid_out fire once each (replay and sim dropped): " + rf.Count);
            Check(rin != null && (string)rin["user"] == "aaronpryan" && (int)rin["amount"] == 2 && (string)rin["id"] == "raid:rd-1" && (string)rin["platform"] == "twitch", "2-viewer incoming raid alerts: raider + viewers + stable id: " + rin);
            Check(rout != null && (string)rout["user"] == "evuto_" && (string)rout["target"] == "evuto_" && (int)rout["amount"] == 12 && (string)rout["id"] == "raid_out:ro-1", "outgoing raid alerts with the target + viewers: " + rout);

            // 4. real watch celebrations: streak, watchtime, anniversary, comeback; stable ids, never sim
            AlertBridge.TestReset(); calls.Clear();
            AlertBridge.OnStreak("streaker", "notif-1", 10); AlertBridge.OnStreak("streaker", "notif-1", 10); AlertBridge.OnStreak("streaker", "notif-2", 11); Thread.Sleep(400);
            var fires = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            var f10 = fires.FirstOrDefault(f => (string)f["id"] == "streak:notif-1"); Check(fires.Count == 2 && f10 != null && (string)f10["type"] == "streak" && (long)f10["amount"] == 10, "every streak notification fires once per id: " + fires.Count + " " + f10);
            calls.Clear(); string dir = Path.Combine(Economy.RootDir, "profiles"); Directory.CreateDirectory(dir);
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            File.WriteAllText(Path.Combine(dir, "ptanniv.json"), "{\"seen\":{\"firstSeen\":\"" + DateTimeOffset.FromUnixTimeSeconds(now - (long)(2.01 * 365.25 * 86400)).ToString("yyyy-MM-ddTHH:mm:ssZ") + "\"}}");
            Economy.TSetMinutes("ptwatch", 590 * 60 / 60.0 * 1); Economy.TSetMinutes("ptanniv", 5);
            AlertBridge.TestSeed("lastSeen", "ptback", now - 40 * 86400);
            AlertBridge.OnPresent(new[] { "ptwatch", "ptanniv", "ptback" }, now); Thread.Sleep(400);
            fires = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            Check(fires.Any(f => (string)f["type"] == "anniversary" && (string)f["user"] == "ptanniv" && (long)f["years"] == 2), "anniversary: 2 years, once");
            Check(fires.Any(f => (string)f["type"] == "comeback" && (string)f["user"] == "ptback" && ((string)f["message"]).Contains("40 days")), "comeback after 40 days with 'last seen' message");
            Check(!fires.Any(f => (string)f["type"] == "watchtime"), "first sighting of watch time fires nothing (no flood from history)");
            calls.Clear(); Economy.TSetMinutes("ptwatch", 610); AlertBridge.OnPresent(new[] { "ptwatch", "ptanniv", "ptback" }, now + 60); Thread.Sleep(400);
            fires = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            Check(fires.Count == 1 && (string)fires[0]["type"] == "watchtime" && (long)fires[0]["hours"] == 10 && (string)fires[0]["id"] == "watchtime:ptwatch:10", "crossing 10 hours fires watchtime once; anniversary / comeback do not repeat");
            calls.Clear(); AlertBridge.OnPresent(new[] { "ptwatch", "sim_p1" }, now + 120); Thread.Sleep(300);
            Check(calls.Count == 0, "no repeats and no sim players");


            // 4b. hype train + tips for Multi: off by default, then start / each new level / end once, tips with currency, never sim/test
            AlertBridge.TestReset(); AlertBridge.TestResetHype(); calls.Clear();
            Func<string, string, string, Dictionary<string, string>> hy = (st, lv, id) => new Dictionary<string, string> { { "state", st }, { "x.level", lv }, { "x.id", id }, { "x.progress", "40" }, { "x.goal", "100" }, { "x.total", "700" } };
            string abp = Path.Combine(HostApi.DataDir, "alert_bridge.json"); var abs = AlertBridge.Settings(); abs["EmitHypeTip"] = false; File.WriteAllText(abp, abs.ToString());
            AlertBridge.OnHype(hy("begin", "1", "ht1")); AlertBridge.OnTip("tipper", 5, "usd", "tp-1"); AlertBridge.OnGameNow("slots", "jackpot", "p", "P", 100, 1000, "", "", "g0");
            Check(calls.Count == 0, "all emits are silent when EmitHypeTip is switched off");
            abs["EmitHypeTip"] = true; File.WriteAllText(abp, abs.ToString());
            AlertBridge.OnHype(hy("begin", "1", "ht1")); AlertBridge.OnHype(hy("begin", "1", "ht1")); AlertBridge.OnHype(hy("progress", "1", "ht1")); AlertBridge.OnHype(hy("progress", "2", "ht1")); AlertBridge.OnHype(hy("progress", "2", "ht1")); AlertBridge.OnHype(hy("progress", "3", "ht1")); AlertBridge.OnHype(hy("end", "3", "ht1")); AlertBridge.OnHype(hy("end", "3", "ht1"));
            var hf = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            Check(hf.Select(f => (string)f["phase"] + ((int)f["level"])).SequenceEqual(new[] { "start1", "level2", "level3", "end3" }) && hf.All(f => ((string)f["type"]).StartsWith("hype_") && (string)f["type"] == "hype_" + (string)f["phase"]) && (string)hf[1]["id"] == "hype:ht1:level2" && (long)hf[0]["goal"] == 100 && (long)hf[0]["total"] == 700, "hype: start, one alert per new level, end; repeats ignored: " + string.Join(",", hf.Select(f => (string)f["id"])));
            var simh = hy("begin", "1", "ht2"); simh["sim"] = "true"; calls.Clear(); AlertBridge.OnHype(simh); Check(calls.Count == 0, "sim hype train fires nothing");
            AlertBridge.OnTip("tipper", 5, "usd", "tp-1"); AlertBridge.OnTip("tipper", 5, "usd", "tp-1");
            var tf = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            Check(tf.Count == 1 && (string)tf[0]["type"] == "tip" && (string)tf[0]["user"] == "tipper" && (long)tf[0]["amount"] == 5 && (string)tf[0]["currency"] == "USD" && (string)tf[0]["id"] == "tip:tp-1", "tip: amount + currency, stable id, once: " + tf.Count);
            // tips without an id each fire (no shared "tip:" id); a train without an id keeps one id from begin to end
            calls.Clear(); AlertBridge.OnTip("tipper", 3, "usd", ""); AlertBridge.OnTip("tipper", 4, "usd", "");
            Check(calls.Count(x => x.Key == "/api/alerts/fire") == 2 && calls.Select(x => (string)x.Value["id"]).Distinct().Count() == 2, "id-less tips are not dropped as one id");
            AlertBridge.TestResetHype(); calls.Clear(); Func<string, string, Dictionary<string, string>> hn = (st, lv) => { var d = hy(st, lv, ""); d.Remove("x.id"); return d; };
            AlertBridge.OnHype(hn("begin", "1")); AlertBridge.OnHype(hn("progress", "2")); AlertBridge.OnHype(hn("progress", "2")); AlertBridge.OnHype(hn("end", "2"));
            var hn2 = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => (string)x.Value["id"]).ToList(); var tids = hn2.Select(i => i.Split(':')[1]).Distinct().ToList();
            Check(hn2.Count == 3 && tids.Count == 1, "id-less hype train: one stable train id, each phase once: " + string.Join(",", hn2));
            // game / economy emits, names as agreed with Multi
            calls.Clear();
            AlertBridge.OnGameNow("slots", "jackpot", "winner", "Winner", 100, 1000, "", "", "g1"); AlertBridge.OnGameNow("slots", "jackpot", "winner", "Winner", 100, 1000, "", "", "g1");
            AlertBridge.OnGameNow("gamble", "win", "gam", "Gam", 50, 100, "", "", "g2"); AlertBridge.OnGameNow("gamble", "lose", "gam", "Gam", 50, 0, "", "", "g3");
            AlertBridge.OnGameNow("shop", "bought", "buyer", "Buyer", 500, 0, "", "get_sub", "g4"); AlertBridge.OnGameNow("shop", "invalid", "buyer", "Buyer", 0, 0, "", "get_sub", "g5");
            AlertBridge.OnGameNow("guess", "start", "gu", "Gu", 100, 200, "", "", "g6"); AlertBridge.OnGameNow("guess", "expired", "gu", "Gu", 100, 0, "", "", "g6");
            AlertBridge.OnGameNow("give", "win", "giver", "Giver", 40, 40, "Taker", "", "g7"); AlertBridge.OnGameNow("slots", "win", "p", "P", 1, 2, "", "", "");
            var gf = calls.Where(x => x.Key == "/api/alerts/fire").Select(x => x.Value).ToList();
            Func<string, JObject> by = t => gf.FirstOrDefault(f => (string)f["type"] == t);
            Check(gf.Count == 5 && gf.Count(f => (string)f["type"] == "gamble_win") == 2 && (long)gf.First(f => (string)f["id"] == "game:slots:g1:jackpot")["amount"] == 1000 && (string)gf.First(f => (string)f["id"] == "game:slots:g1:jackpot")["message"] == "jackpot!", "gamble_win: winnings as amount, jackpot message, once per game id; losses, invalid and idless results fire nothing: " + gf.Count);
            Check(by("shop") != null && (string)by("shop")["message"] == "get_sub" && by("guess") != null && (string)by("guess")["user"] == "gu", "shop (item name) and guess (on start only)");
            Check(by("give") != null && (string)by("give")["recipient"] == "Taker" && (long)by("give")["amount"] == 40, "give: user, recipient, amount");
            calls.Clear(); AlertBridge.Emit("loan", "loan:ln-1", "lender", "Lender", 300, "Borrower"); AlertBridge.Emit("loan", "loan:ln-1", "lender", "Lender", 300, "Borrower");
            Check(calls.Count == 1 && (string)calls[0].Value["type"] == "loan" && (string)calls[0].Value["recipient"] == "Borrower" && (long)calls[0].Value["amount"] == 300, "loan: lender, recipient, amount, once");
            abs["EmitHypeTip"] = false; File.WriteAllText(abp, abs.ToString()); calls.Clear();

            // 5. raid emote line: fires when the raid is SCHEDULED (raid_start), not when it lands (raid_out)
            var adoc = Auto.Doc(); var acts = (JArray)adoc["actions"];
            var rs0 = acts.OfType<JObject>().FirstOrDefault(a => (string)a["id"] == "sb-raidstart"); var ro0 = acts.OfType<JObject>().FirstOrDefault(a => (string)a["id"] == "sb-raidout");
            Check(rs0 != null && (string)rs0["triggers"][0]["type"] == "raid_start" && ((JArray)rs0["steps"]).ToString().Contains("Prepare your emotes") && ro0 != null && !((JArray)ro0["steps"]).ToString().Contains("Prepare your emotes"), "fresh install: emotes line on raid_start, raid_out only stops the stream");
            acts.Remove(rs0); ro0["steps"] = new JArray { new JObject { { "type", "say" }, { "as", "core" }, { "text", "Raid started! Prepare your emotes! x" } }, new JObject { { "type", "delay" }, { "ms", 3000 } }, new JObject { { "type", "say" }, { "as", "core" }, { "text", "discord" } }, new JObject { { "type", "delay" }, { "ms", 20000 } }, new JObject { { "type", "obs_request" }, { "request", "StopStream" } } };
            var sd = (JArray)adoc["seeded"]; foreach (var t in sd.Where(x => (string)x == "raidstart1").ToList()) sd.Remove(t); Auto.Save(adoc);
            Auto.MigrateRaidStart(); adoc = Auto.Doc(); acts = (JArray)adoc["actions"];
            rs0 = acts.OfType<JObject>().FirstOrDefault(a => (string)a["id"] == "sb-raidstart"); ro0 = acts.OfType<JObject>().FirstOrDefault(a => (string)a["id"] == "sb-raidout");
            Check(rs0 != null && ((JArray)rs0["steps"]).Count == 3 && ((JArray)ro0["steps"]).Count == 2 && !((JArray)ro0["steps"]).ToString().Contains("emotes"), "old install: the emotes + discord lines moved to raid_start, the 20 s stop stayed on raid_out");
            Auto.MigrateRaidStart(); Check(((JArray)Auto.Doc()["actions"]).OfType<JObject>().Count(a => (string)a["id"] == "sb-raidstart") == 1, "migration runs once");

            // raid prep fires once per raid, however it was started (!confirm raid, the Master View button, or the outgoing channel.raid event)
            Auto.ResetRaidStart(); Check(Auto.OnRaidScheduled("somebody"), "raid prep: first signal fires");
            Check(!Auto.OnRaidScheduled("somebody"), "raid prep: the later signal for the same raid does not repeat it");
            Auto.ResetRaidStart(); Check(Auto.OnRaidScheduled("other"), "raid prep: a new raid fires again");
            // the raid lines go out the moment the raid is picked (Twitch's countdown starts): no hold
            Auto.ResetRaidStart(); int f0 = Auto.RaidStartFires;
            Check(Auto.OnRaidScheduled("late") && Auto.RaidStartFires == f0 + 1, "raid line: said at once when the countdown starts");
            // a goodnight (stream_offline) must not be said while the raid is on its way: held until raid_out, !unraid, or ~3 min
            var off = new Dictionary<string, object> { { "eventType", "StreamOffline" } }; int q0 = Auto.OfflineFires;
            Auto.ResetRaidStart(); Auto.OnEvent(off); Check(Auto.OfflineFires == q0 + 1, "offline without a raid: said at once"); q0 = Auto.OfflineFires;
            Auto.ResetRaidStart(); Auto.OnRaidScheduled("t1"); Auto.OnEvent(off); Check(Auto.OfflineFires == q0, "offline during a pending raid: held");
            Auto.CancelRaidStart(); Check(Auto.OfflineFires == q0 + 1, "raid cancelled (!unraid): the held goodnight runs"); q0 = Auto.OfflineFires;
            Auto.ResetRaidStart(); Auto.OnRaidScheduled("t2"); Auto.OnEvent(off); Auto.RaidDelayOverrideSec = 2;
            Auto.OnEvent(new Dictionary<string, object> { { "eventType", "TwitchRaidOut" }, { "userName", "t2" }, { "viewers", 5 } });
            Check(Auto.OfflineFires == q0, "offline held until the raid lands"); System.Threading.Thread.Sleep(3000); Check(Auto.OfflineFires == q0 + 1, "raid_out: the held goodnight runs after the raid"); Auto.RaidDelayOverrideSec = -1; q0 = Auto.OfflineFires;
            Auto.ResetRaidStart(); Auto.HoldMaxSec = 2; Auto.OnRaidScheduled("t3"); Auto.OnEvent(off); Check(Auto.OfflineFires == q0, "offline held (short max)"); System.Threading.Thread.Sleep(3300);
            Check(Auto.OfflineFires == q0 + 1, "the hold runs out: the goodnight runs anyway"); Auto.HoldMaxSec = 180;
            // the landing says the goodnight FIRST, then runs raid_out (StopStream)
            { var od = Auto.Doc(); var oa = (JArray)od["actions"];
              oa.Add(new JObject { { "id", "t-ro" }, { "name", "t-ro" }, { "enabled", true }, { "triggers", new JArray(new JObject { { "type", "raid_out" } }) }, { "steps", new JArray(new JObject { { "type", "delay" }, { "ms", 800 } }) } });
              oa.Add(new JObject { { "id", "t-gn" }, { "name", "t-gn" }, { "enabled", true }, { "triggers", new JArray(new JObject { { "type", "stream_offline" } }) }, { "steps", new JArray(new JObject { { "type", "log" }, { "text", "t-gn" } }) } }); Auto.Save(od); }
            Auto.ResetRaidStart(); Auto.RaidDelayOverrideSec = 1; Auto.OnRaidScheduled("t4"); Auto.OnEvent(off);
            Auto.OnEvent(new Dictionary<string, object> { { "eventType", "TwitchRaidOut" }, { "userName", "t4" }, { "viewers", 5 } }); System.Threading.Thread.Sleep(3500);
            { JObject lro = null, lgn = null; foreach (JObject e in Auto.Log(50)) { if ((string)e["id"] == "t-ro" && lro == null) lro = e; if ((string)e["id"] == "t-gn" && lgn == null) lgn = e; }
              Check(lro != null && lgn != null && string.CompareOrdinal((string)lgn["ts"], (string)lro["ts"]) <= 0, "goodnight is said BEFORE the raid_out run (StopStream) finishes (raid_out " + (lro == null ? "-" : (string)lro["ts"]) + ", goodnight " + (lgn == null ? "-" : (string)lgn["ts"]) + ")"); }
            { var od = Auto.Doc(); var oa = (JArray)od["actions"]; foreach (var x in oa.OfType<JObject>().Where(x => ((string)x["id"]).StartsWith("t-")).ToList()) oa.Remove(x); Auto.Save(od); }
            // stream online / offline tell the Spotify module (reopen requests at go-live, close them at the end), also while a raid holds the goodnight
            { var mp = new List<string>(); Auto.ModuleLiveTest = pth => mp.Add(pth); Auto.ResetRaidStart();
              Auto.OnEvent(new Dictionary<string, object> { { "eventType", "StreamOnline" } }); Auto.OnRaidScheduled("t5"); Auto.OnEvent(off); Auto.CancelRaidStart();
              Check(mp.SequenceEqual(new[] { "/api/live/auto", "/api/live/stop" }), "spotify module: /api/live/auto on stream online, /api/live/stop on offline (" + string.Join(",", mp) + ")"); Auto.ModuleLiveTest = null; Auto.ResetRaidStart(); }
            // Songify owns the song-request redeems while the module says songify:true: the preset does not run at all; false / failed call = runs as before
            { var od = Auto.Doc(); var oa = (JArray)od["actions"]; foreach (var x in oa.OfType<JObject>().Where(x => (string)x["id"] == "spotify-redeem").ToList()) oa.Remove(x);
              oa.Add(new JObject { { "id", "spotify-redeem" }, { "name", "t-sr" }, { "enabled", true }, { "triggers", new JArray(new JObject { { "type", "redeem" }, { "title", "*" } }) }, { "steps", new JArray(new JObject { { "type", "log" }, { "text", "t-sr" } }) } }); Auto.Save(od);
              var rd = new Dictionary<string, object> { { "eventType", "TwitchRedeem" }, { "userName", "v1" }, { "title", "Song Request" } };
              Func<int> runs = () => Auto.Log(200).OfType<JObject>().Count(e => (string)e["id"] == "spotify-redeem");
              int s0 = runs(); Auto.SongifyTest = () => true; Auto.OnEvent(rd); System.Threading.Thread.Sleep(600); Check(runs() == s0, "songify true: the song request redeem does nothing");
              Auto.SongifyTest = () => false; Auto.OnEvent(rd); System.Threading.Thread.Sleep(600); Check(runs() == s0 + 1, "songify false: runs as before");
              Auto.SongifyTest = () => null; Auto.OnEvent(rd); System.Threading.Thread.Sleep(600); Check(runs() == s0 + 2, "songify unknown (call failed / key missing): runs as before"); Auto.SongifyTest = null;
              od = Auto.Doc(); oa = (JArray)od["actions"]; foreach (var x in oa.OfType<JObject>().Where(x => (string)x["id"] == "spotify-redeem").ToList()) oa.Remove(x); Auto.Save(od); }
            // an incoming raid too small for a shoutout does not wait the 12 s before the (skipped) shoutout; an older saved action gets the flag once
            { var od = Auto.Doc(); var sr = ((JArray)od["actions"]).OfType<JObject>().First(x => (string)x["id"] == "sb-raid"); foreach (var st in ((JArray)sr["steps"]).OfType<JObject>()) st.Remove("skipSmallRaid");
              foreach (var t in ((JArray)od["seeded"]).Where(x => (string)x == "raidshout1").ToList()) ((JArray)od["seeded"]).Remove(t); sr["enabled"] = true; Auto.Save(od); Auto.SkipSmallRaidWait();
              Check(((JArray)((JArray)Auto.Doc()["actions"]).OfType<JObject>().First(x => (string)x["id"] == "sb-raid")["steps"]).OfType<JObject>().Count(st => (bool?)st["skipSmallRaid"] == true) == 1, "migration: exactly the wait before the shoutout is flagged"); }
            Auto.OnEvent(new Dictionary<string, object> { { "eventType", "TwitchRaid" }, { "userName", "smallraider" }, { "viewers", 2 } }); System.Threading.Thread.Sleep(9000);
            { JObject lr = null; foreach (JObject e in Auto.Log(80)) if ((string)e["id"] == "sb-raid") { lr = e; break; }
              Check(lr != null && (long)lr["ms"] < 7000 && lr["output"].ToString().Contains("too small"), "2-viewer raid: no 12 s wait (took " + (lr == null ? "no run; log ids " + string.Join(",", Auto.Log(30).Select(e => (string)e["id"])) : (string)lr["ms"]) + " ms)"); }
            Auto.ResetRaidStart(); Auto.RaidDelayOverrideSec = 2;
            // raid_out (the 20 s StopStream) must run after the raid landed, once per raid, and be cancellable
            Auto.ResetRaidStart(); int o0 = Auto.RaidOutFires; var ro = new Dictionary<string, object> { { "eventType", "TwitchRaidOut" }, { "userName", "streamer" }, { "viewers", 5 } };
            Auto.OnEvent(ro); Auto.OnEvent(ro); Check(Auto.RaidOutFires == o0, "raid_out: not run when the countdown starts");
            System.Threading.Thread.Sleep(3000); Check(Auto.RaidOutFires == o0 + 1, "raid_out: run once after the delay (the second signal of the same raid is ignored)");
            Auto.ResetRaidStart(); Auto.OnEvent(ro); Auto.CancelRaidStart(); System.Threading.Thread.Sleep(3000); Check(Auto.RaidOutFires == o0 + 1, "raid_out: !unraid / stream offline cancels it");
            Auto.RaidDelayOverrideSec = -1;
            AlertBridge.TestPost = null;
            Console.WriteLine(fails == 0 ? "[alerttest] ALL PASS" : "[alerttest] " + fails + " FAILED");
        }
    }
}
