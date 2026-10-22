using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "pointstest": the points rework rules (calculator, 5-minute watch, tier change, extension bits, follow once, raid threshold, idempotency, hot reload, streams view)</summary>
    public static class PointsTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        static long Pre(string type, double amt, int tier = 0) { return (long)Economy.Preview(new JObject { { "type", type }, { "amount", amt }, { "tier", tier } })["points"]; }
        static Dictionary<string, object> Ev(string type, string user, string id, long n = 0, string tier = "1", string bt = "")
        {
            return new Dictionary<string, object> { { "eventType", type }, { "userName", user }, { "eventId", id }, { "bits", n }, { "viewers", n }, { "total", n }, { "tier", tier }, { "bitsType", bt } };
        }
        public static void Run()
        {
            // 1. calculator
            Check(Pre("cheer", 100) == 1000 && Pre("cheer", 499) == 4990 && Pre("cheer", 500) == 5500 && Pre("cheer", 999) == 10989 && Pre("cheer", 1000) == 15000, "cheer tiers: 100->1000, 500->5500, 1000->15000");
            Check(Pre("tip", 1) == 1250 && Pre("tip", 5) == 7000 && Pre("tip", 10) == 20000 && Pre("tip", 3) == 4125 && Pre("tip", 0.5) == 625, "tip curve: $1/$5/$10 and interpolation, floor below $1");
            Check(Pre("sub", 0, 1) == 6000 && Pre("sub", 0, 2) == 12000 && Pre("sub", 0, 3) == 30000 && Pre("gift", 3, 2) == 36000 && Pre("gift_recipient", 0) == 1500, "sub tiers, gift bomb and recipient");
            Check(Pre("watch", 0, 0) == 10 && Pre("watch", 0, 1) == 15 && Pre("watch", 0, 2) == 20 && Pre("watch", 0, 3) == 30 && Pre("follow", 0) == 150 && Pre("raid_leader", 3) == 0 && Pre("raid_leader", 4) == 1000, "watch rates, follow, raid leader threshold");

            // 2. watch: entry once, full 5-minute stretches only, partial stretch earns nothing
            long b = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); string sid = "off"; Economy.TReset(); Economy.TestTier = l => 0;
            long b0 = Economy.TBal("ptuser1");
            for (int t = 0; t <= 240; t += 60) Economy.WatchStep(b + t, new[] { "ptuser1" }, sid);
            Check(Economy.TBal("ptuser1") - b0 == 100, "entry bonus only, partial stretch earns nothing: +" + (Economy.TBal("ptuser1") - b0));
            for (int t = 300; t <= 540; t += 60) Economy.WatchStep(b + t, new[] { "ptuser1" }, sid);
            long g1 = Economy.TBal("ptuser1") - b0; Check(g1 == 110, "first full 5 minutes pays the viewer rate once: +" + g1);
            Economy.TestTier = l => 1; for (int t = 600; t <= 840; t += 60) Economy.WatchStep(b + t, new[] { "ptuser1" }, sid);
            Economy.TestTier = l => 2; for (int t = 900; t <= 1140; t += 60) Economy.WatchStep(b + t, new[] { "ptuser1" }, sid);
            long g2 = Economy.TBal("ptuser1") - b0; Check(g2 == 100 + 10 + 10 + 15 + 20 - 10, "tier change mid-stream: viewer, T1 then T2 stretch (got +" + g2 + ")");
            for (int t = 1200; t <= 1260; t += 60) Economy.WatchStep(b + t, new string[0], sid);
            Economy.WatchStep(b + 1700, new[] { "ptuser1" }, sid); long g3 = Economy.TBal("ptuser1") - b0;
            Check(g3 == g2, "away for a while then back: no new entry bonus, nothing for the gap: +" + (g3 - g2));
            var sv = Economy.StreamsView("ptuser1", sid); var rows = (JArray)sv[0]["rows"];
            Check(sv.Count >= 1 && rows.Any(r => (string)r["label"] == "Watched 5 min (sub T2 rate)") && rows.Any(r => (string)r["label"] == "Joined the stream") && (long)sv[0]["total"] == g3, "streams view: labels and total match (" + rows.Count + " rows, total " + sv[0]["total"] + " vs " + g3 + ")");
            Check(rows.Count > 1 && (long)rows[0]["at"] >= (long)rows[rows.Count - 1]["at"], "rows newest first");

            // 3. extension bits ignored, chat cheers paid, same event id pays once
            long c0 = Economy.TBal("ptuser2");
            Economy.PointsEvent(Ev("TwitchCheer", "ptuser2", "e-ext", 500, "1", "extension")); Check(Economy.TBal("ptuser2") == c0, "Bits in Extension ignored");
            Economy.PointsEvent(Ev("TwitchCheer", "ptuser2", "e-1", 500)); Economy.PointsEvent(Ev("TwitchCheer", "ptuser2", "e-1", 500));
            Check(Economy.TBal("ptuser2") - c0 == 5500, "chat cheer 500 bits = 5500, replay of the same id pays once: +" + (Economy.TBal("ptuser2") - c0));

            // 4. subs / gifts / recipient / tip
            long s0 = Economy.TBal("ptuser3");
            Economy.PointsEvent(Ev("TwitchSub", "ptuser3", "e-sub", 0, "2000")); Economy.PointsEvent(Ev("TwitchSub", "ptuser3", "e-sub", 0, "2000"));
            Economy.PointsEvent(Ev("TwitchGiftBomb", "ptuser3", "e-gift", 5, "1000")); Economy.PointsEvent(Ev("TwitchGiftRecipient", "ptuser3", "e-rx", 0, "1000"));
            Check(Economy.TBal("ptuser3") - s0 == 12000 + 30000 + 1500, "sub T2 + 5 gifted T1 + received gift: +" + (Economy.TBal("ptuser3") - s0));
            long tip0 = Economy.TBal("ptuser3"); var tr = Economy.EventApi(new JObject { { "type", "tip" }, { "login", "ptuser3" }, { "amount", 5 }, { "id", "tip-1" } }); Economy.EventApi(new JObject { { "type", "tip" }, { "login", "ptuser3" }, { "amount", 5 }, { "id", "tip-1" } });
            Check((bool)tr["ok"] && Economy.TBal("ptuser3") - tip0 == 7000, "tip $5 = 7000 once");

            // 5. follow once per account, refollow zero
            long f0 = Economy.TBal("ptuser4");
            Economy.PointsEvent(Ev("TwitchFollow", "ptuser4", "f-1"), true); Check(Economy.TBal("ptuser4") == f0, "refollow pays zero");
            Economy.PointsEvent(Ev("TwitchFollow", "ptuser5", "f-2"), false); Economy.PointsEvent(Ev("TwitchFollow", "ptuser5", "f-3"), false);
            var fv = Economy.StreamsView("ptuser5", sid);
            Check(fv.Count == 1 && (long)fv[0]["total"] == 150, "new follow 150, a second follow event for the same account pays nothing");

            // 6. raids
            long r0 = Economy.TBal("ptleader1"); Economy.PointsEvent(Ev("TwitchRaid", "ptleader1", "r-1", 3)); Check(Economy.TBal("ptleader1") == r0, "raid of 3 viewers: leader gets nothing");
            Economy.PointsEvent(Ev("TwitchRaid", "ptleader2", "r-2", 12)); Economy.PointsEvent(Ev("TwitchRaid", "ptleader2", "r-2", 12));
            Check(Economy.TBal("ptleader2") == 1000, "raid of 12 viewers: leader 1000 once");
            Economy.TReset(); Economy.PointsEvent(Ev("TwitchRaid", "ptleader3", "r-3", 12));
            long a0 = Economy.TBal("ptraider1"); long nowU = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            Economy.WatchStep(nowU, new[] { "ptraider1" }, sid); Check(Economy.TBal("ptraider1") - a0 == 250, "raider arriving in the window: 100 entry + 150 = 250: +" + (Economy.TBal("ptraider1") - a0));
            long a1 = Economy.TBal("ptlate1"); Economy.WatchStep(nowU + 3600, new[] { "ptlate1" }, sid); Check(Economy.TBal("ptlate1") - a1 == 100, "arriving after the raid window: entry only");

            // 7. hot reload
            string sp = Path.Combine(HostApi.DataDir, "economy", "settings.json");
            if (File.Exists(sp))
            {
                string orig = File.ReadAllText(sp); var j = JObject.Parse(orig); j["CheerLow"] = 20; File.WriteAllText(sp, j.ToString()); System.Threading.Thread.Sleep(2300);
                Check(Economy.CheerPoints(100) == 2000, "settings.json edit is picked up without a restart: " + Economy.CheerPoints(100));
                File.WriteAllText(sp, orig); System.Threading.Thread.Sleep(2300); Check(Economy.CheerPoints(100) == 1000, "and back");
            }
            else Check(false, "settings.json exists at " + sp);
            // 8. match awards = minutes of watching x multiplier at the player's own rate; settings page API with live preview
            Check(Economy.MatchPoints(0, false) == 28 && Economy.MatchPoints(0, true) == 42, "viewer: played 7 min x2 = 28, won x3 = 42: " + Economy.MatchPoints(0, false) + "/" + Economy.MatchPoints(0, true));
            Check(Economy.MatchPoints(1, false) == 42 && Economy.MatchPoints(1, true) == 63 && Economy.MatchPoints(3, true) == 126, "sub T1 42/63, T3 win 126");
            var pv = Economy.Preview(new JObject { { "type", "match_win" }, { "tier", "2" } }); Check((long)pv["points"] == 84, "preview match_win T2 = 84: " + pv);
            var dry = Economy.PointsSettingsApi(JObject.FromObject(new { values = new { MatchPlayMult = 4, MatchMinutes = 10 }, dry = true }), true);
            Check((bool)dry["ok"] && (long)dry["examples"]["match"]["viewer"]["play"] == 80 && Economy.MatchPoints(0, false) == 28, "dry run shows 80 for 10 min x4 but saves nothing");
            var bad = Economy.PointsSettingsApi(JObject.FromObject(new { values = new { Exclude = 1 } }), true); Check((bool)bad["ok"] == false, "keys outside the points settings are refused");
            var neg = Economy.PointsSettingsApi(JObject.FromObject(new { values = new { EntryBonus = -5 } }), true); Check((bool)neg["ok"] == false, "negative values are refused");
            var g = Economy.PointsSettingsApi(new JObject(), false); Check((bool)g["ok"] && g["values"]["MatchMinutes"] != null && g["examples"]["watch"]["viewer"]["per_hour"] != null, "GET lists values + examples (watch per hour = " + g["examples"]["watch"]["viewer"]["per_hour"] + ")");
            // 9. the pushed summary groups points by category with exact totals
            Economy.EventApi(new JObject { { "type", "cheer" }, { "login", "catuser" }, { "amount", 100 }, { "id", "cat-c1" } });
            Economy.EventApi(new JObject { { "type", "follow" }, { "login", "catuser" }, { "id", "cat-f1" } });
            Economy.EventApi(new JObject { { "type", "tip" }, { "login", "catuser" }, { "amount", 5 }, { "id", "cat-t1" } });
            var cats = (JArray)Economy.Me2("catuser")["categories"]; Func<string, JObject> cat = k => cats.OfType<JObject>().FirstOrDefault(x => (string)x["key"] == k);
            Check(cat("cheers") != null && (long)cat("cheers")["total"] == 1000 && (int)cat("cheers")["count"] == 1 && ((JArray)cat("cheers")["rows"]).Count == 1, "categories: cheers total 1000 with its row: " + cats);
            Check(cat("follows") != null && (long)cat("follows")["total"] == 150 && cat("subs") != null && (long)cat("subs")["total"] > 0, "categories: follow 150 under Follows/Raids, tip under Subs/Gifts");
            Check(cats.Count > 0 && (string)cats[0]["label"] != null && ((JArray)cat("cheers")["rows"])[0]["label"] != null, "categories carry labels and rows with labels");
            Economy.TestTier = null;
            Console.WriteLine(fails == 0 ? "[pointstest] ALL PASS" : "[pointstest] " + fails + " FAILED");
        }
    }
}
