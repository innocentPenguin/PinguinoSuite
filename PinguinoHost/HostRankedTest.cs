using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "rankedtest": marks, undo, limit, reset, the day and week boundaries (the clock is moved), the week answer, chat lines; prints PASS/FAIL lines</summary>
    public static class RankedTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        static string Say(string user, string text, int role) { string said = ""; string[] p = text.Split(' '); RankedActivity.Intercept(user, p[0], System.Linq.Enumerable.ToArray(System.Linq.Enumerable.Skip(p, 1)), role, m => said += (said == "" ? "" : " || ") + m); return said; }
        static string G(JObject s) { return string.Join("", s["games"].ToObject<string[]>()); }
        public static void Run()
        {
            // Wednesday 2026-10-28 18:00 UTC = 13:00 in Chicago
            long wed = new DateTimeOffset(2026, 10, 28, 18, 0, 0, TimeSpan.Zero).ToUnixTimeSeconds(); RankedActivity.NowFn = () => wed;
            var s = RankedActivity.State(); Check(!(bool)s["active"] && (int)s["limit"] == 5 && G(s) == "" && (int)s["inProgress"] == 1 && (int)s["net"] == 0, "starts off, limit 5, game 1 in progress: " + s);
            Check(RankedActivity.Apply("win", null)["ok"].Value<bool>() == false, "a mark while ranked is off is refused");
            Check(Say("m", "!win", 3) == "" , "!win while ranked is off is not ours (nothing said)");
            Check(Say("m", "!ranked start", 3) == "@m Ranked is on. Ranked today: 0-0 (0)", "start: " + Say("m", "!ranked start", 3));
            Check(Say("m", "!win", 3) == "@m Ranked today: 1-0 (+1)", "!win");
            Check(Say("m", "!loss", 3) == "@m Ranked today: 1-1 (0)", "!loss");
            Check(Say("m", "!w", 3) == "@m Ranked today: 2-1 (+1)" && Say("m", "!l", 3) == "@m Ranked today: 2-2 (0)" && Say("m", "!ranked win", 3) == "@m Ranked today: 3-2 (+1)" && Say("m", "!ranked l", 3) == "@m Ranked today: 3-3 (0)", "!w !l !ranked win|l");
            Check(Say("m", "!ranked w", 3) == "@m Ranked today: 4-3 (+1)" && Say("m", "!win", 3) == "@m Ranked today: 5-3 (+2)", "5-3");
            s = RankedActivity.State(); Check(G(s) == "WLWLWLWW" && (int)s["inProgress"] == 9 && (int)s["net"] == 2 && (int)s["wins"] == 5, "games W/L list: " + G(s));
            Check(s["visible"].ToObject<string[]>().Length == 5 && string.Join("", s["visible"].ToObject<string[]>()) == "LWLWW", "visible = the last 5");
            Check(Say("m", "!undo", 3) == "@m Undone. Ranked today: 4-3 (+1)", "!undo: " + Say("m", "!ranked undo", 3));
            Check(Say("m", "!ranked limit 3", 3) == "@m Ranked shows the last 3 games." && (int)RankedActivity.State()["limit"] == 3 && RankedActivity.State()["visible"].ToObject<string[]>().Length == 3, "limit 3");
            Check(Say("m", "!ranked limit 0", 3).Contains("1 to") && Say("m", "!ranked limit 99", 3).Contains("1 to") && (int)RankedActivity.State()["limit"] == 3, "limit out of range refused");
            Check(Say("viewer", "!win", 1) == "" && Say("viewer", "!ranked win", 1) == "" && Say("viewer", "!undo", 1) == "" && G(RankedActivity.State()) == "WLWLWL", "a viewer cannot mark: " + G(RankedActivity.State()));
            Check(Say("viewer", "!ranked", 1) == "@viewer Ranked today: 3-3 (0)", "viewer reads one line: " + Say("viewer", "!ranked", 1));
            // next day (Thursday), same ISO week
            long thu = wed + 86400; RankedActivity.NowFn = () => thu;
            Check(G(RankedActivity.State()) == "" && (int)RankedActivity.State()["inProgress"] == 1, "a new stream day starts empty");
            RankedActivity.Apply("win", null); RankedActivity.Apply("win", null); RankedActivity.Apply("loss", null);
            s = RankedActivity.State(); var w = (JObject)s["week"]; Check((int)w["wins"] == 5 && (int)w["losses"] == 4 && (int)w["net"] == 1, "week adds both days: " + w);
            Check(Say("v2", "!ranked week", 1) == "@v2 Ranked this week: 5-4 (+1)", "!ranked week: " + Say("v3", "!ranked week", 1));
            // next week (the following Wednesday)
            long nextWed = wed + 7 * 86400; RankedActivity.NowFn = () => nextWed; s = RankedActivity.State(); w = (JObject)s["week"];
            Check((int)w["wins"] == 0 && (int)w["losses"] == 0 && G(s) == "", "a new week starts at 0-0: " + w);
            RankedActivity.NowFn = () => thu;
            Check(Say("m", "!ranked reset", 3) == "@m Ranked reset. Ranked today: 0-0 (0)" && G(RankedActivity.State()) == "", "reset clears today");
            w = (JObject)RankedActivity.State()["week"]; Check((int)w["wins"] == 3 && (int)w["losses"] == 3, "reset keeps the other days: " + w);
            Check(Say("m", "!undo", 3).Contains("nothing to undo"), "undo on an empty day says so");
            Check(Say("m", "!ranked stop", 3) == "@m Ranked is off." && !(bool)RankedActivity.State()["active"], "stop");
            RankedActivity.Apply("start", null); Check(Say("m", "!activity end", 3) == "" && (bool)RankedActivity.State()["active"], "!activity end (customs) leaves ranked running");
            Check(Say("m", "!win blue", 3) == "" && G(RankedActivity.State()) == "", "!win <team> is customs', not ranked");
            Check(Say("m", "!customs win", 3).Contains("!customs win|loss") && Say("viewer", "!customs win blue", 1) == "" && G(RankedActivity.State()) == "", "!customs needs a team; viewers get nothing");
            Check(Say("m", "!activity ranked", 3).StartsWith("@m Ranked is on.") && (bool)RankedActivity.State()["active"], "!activity ranked starts it");
            // breaks: defaults 3 games / 2 losses in a row
            RankedActivity.Apply("reset", null); RankedActivity.Apply("resume", null); s = RankedActivity.State(); var b = (JObject)s["break"];
            Check(!(bool)b["active"] && (int)b["afterGames"] == 3 && (int)b["lossStreak"] == 2 && (int)s["breakAfter"] == 3, "break off, defaults 3 / 2: " + b);
            Say("m", "!win", 3); Say("m", "!loss", 3); Check(!(bool)RankedActivity.State()["break"]["active"], "no break after 2 mixed games");
            Say("m", "!win", 3); b = (JObject)RankedActivity.State()["break"]; Check((bool)b["active"] && (string)b["reason"] == "3 games" && ((JArray)RankedActivity.State()["breaks"]).Count == 1, "break after 3 games: " + b);
            Check(Say("m", "!ranked break", 3).Contains("already on a break"), "a second break is refused");
            Say("m", "!win", 3); Check(((JArray)RankedActivity.State()["breaks"]).Count == 1 && (int)RankedActivity.State()["wins"] == 3, "marks during a break count, no second break");
            Check(Say("m", "!ranked resume", 3) == "@m Ranked is back. Ranked today: 3-1 (+2)" && !(bool)RankedActivity.State()["break"]["active"] && (int)RankedActivity.State()["sinceBreak"] == 0, "resume: counters restart, day record continues");
            Say("m", "!loss", 3); Check(!(bool)RankedActivity.State()["break"]["active"], "one loss is not a streak");
            Say("m", "!loss", 3); b = (JObject)RankedActivity.State()["break"]; Check((bool)b["active"] && (string)b["reason"] == "2 losses in a row", "break after 2 losses in a row: " + b);
            Say("m", "!undo", 3); Check(!(bool)RankedActivity.State()["break"]["active"] && ((JArray)RankedActivity.State()["breaks"]).Count == 1, "undo of the triggering game cancels the break");
            Check(Say("m", "!ranked breakafter 0", 3) == "@m Break after games: off." && Say("m", "!ranked lossstreak 0", 3) == "@m Break after losses in a row: off.", "rules off");
            Say("m", "!win", 3); Say("m", "!win", 3); Say("m", "!loss", 3); Say("m", "!loss", 3); Check(!(bool)RankedActivity.State()["break"]["active"], "with both rules off no break comes");
            Check(Say("m", "!ranked breakafter 4", 3) == "@m Break after 4 games." && Say("m", "!ranked lossstreak 3", 3) == "@m Break after 3 losses in a row." && (int)RankedActivity.State()["lossStreak"] == 3, "rules set");
            Check(Say("m", "!ranked breakafter x", 3).Contains("<0-") && Say("m", "!ranked lossstreak 99", 3).Contains("0 (off)"), "bad rule values refused");
            Check(Say("m", "!ranked break", 3) == "" && (string)RankedActivity.State()["break"]["reason"] == "manual", "manual break (the one announcement line is the answer)");
            Check(Say("viewer", "!ranked resume", 1) == "" && (bool)RankedActivity.State()["break"]["active"], "a viewer cannot resume");
            Say("m", "!ranked stop", 3); Check(!(bool)RankedActivity.State()["break"]["active"], "stop ends the break");
            var pp = RankedActivity.PushPayload(); Check(pp["days"].Count() >= 2 && pp["weeks"].Count() >= 1 && pp["months"].Count() >= 1 && (string)pp["generatedAt"] != null && pp["settings"]["breakAfter"] != null, "push payload shape");
            var k1 = RankedPush.Key(pp); pp["generatedAt"] = "2000-01-01T00:00:00Z"; Check(k1 == RankedPush.Key(pp), "push key ignores generatedAt"); RankedActivity.Apply("start", null); RankedActivity.Apply("win", null); Check(k1 != RankedPush.Key(RankedActivity.PushPayload()), "push key changes with a game");
            Say("m", "!ranked start", 3);
            string f = Path.Combine(HostApi.DataDir, "ranked.json"); var j = JObject.Parse(File.ReadAllText(f));
            Check((bool)j["active"] && j["days"]["2026-10-28"] != null && File.Exists(f), "state file written");
            RankedActivity.NowFn = () => DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            Console.WriteLine(fails == 0 ? "[rankedtest] ALL PASS" : "[rankedtest] FAIL " + fails);
        }
    }
}
