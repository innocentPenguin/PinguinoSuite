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
            AlertBridge.TestPost = null;
            Console.WriteLine(fails == 0 ? "[alerttest] ALL PASS" : "[alerttest] " + fails + " FAILED");
        }
    }
}
