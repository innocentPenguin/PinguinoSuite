using System;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "givelimittest": give limit = percent of the CURRENT balance, per stream (counter resets on a new stream, carries over offline), min/max, shared !give/site door</summary>
    public static class GiveLimitTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        public static void Run()
        {
            Economy.TReset();
            Gamble.SaveConfig(new JObject { { "enabled", true }, { "giveEnabled", true }, { "giveDailyPct", 10 }, { "giveDailyMin", 0 }, { "giveDailyMax", 0 }, { "giveMin", 1 } });
            Economy.TestSid = "s1";
            Economy.Credit("glt-a", "gla", 100000, "test"); Economy.Credit("glt-b", "glb", 0, "test");
            Check(Gamble.GiveLimit("gla") == 10000, "10% of 100,000 = 10,000: " + Gamble.GiveLimit("gla"));
            var r = Gamble.Give("gla", "glb", 10000, "t1"); Check((bool)r["ok"], "give exactly the limit works");
            Check(Gamble.GiveLimit("gla") == 9000 && Gamble.GiveToday("gla") == 10000, "balance went down: limit 9,000, counter stays 10,000");
            r = Gamble.Give("gla", "glb", 1, "t2"); Check(!(bool)r["ok"] && ((string)r["error"]).Contains("this stream"), "over the limit is refused with given/limit: " + (string)r["error"]);
            Economy.Credit("glt-c", "gla", 200000, "test");
            Check(Gamble.GiveLimit("gla") == 29000, "balance up: limit follows live (29,000)");
            r = Gamble.Give("gla", "glb", 19000, "t3"); Check((bool)r["ok"], "balance up lets them give more in the same stream (total 29,000)");
            Economy.TestSid = "off";
            r = Gamble.Give("gla", "glb", 1, "t4"); Check(!(bool)r["ok"] && Gamble.GiveToday("gla") == 29000, "offline between streams: the counter carries over");
            Economy.TestSid = "s2";
            Check(Gamble.GiveToday("gla") == 0, "a new stream clears the counter");
            r = Gamble.Give("gla", "glb", 1000, "t5"); Check((bool)r["ok"], "can give again in the new stream");
            // balance dropped below what was given: still allowed to see the numbers, e.g. 30,000 given / 3,000 limit
            Gamble.SaveConfig(new JObject { { "giveDailyMin", 500 } });
            Economy.Credit("glt-d", "glc", 100, "test"); Check(Gamble.GiveLimit("glc") == 500, "minimum applies to a small balance");
            Gamble.SaveConfig(new JObject { { "giveDailyMin", 0 }, { "giveDailyMax", 2000 } });
            Check(Gamble.GiveLimit("gla") == 2000, "maximum caps the limit");
            Gamble.SaveConfig(new JObject { { "giveDailyMax", 0 } });
            // site and chat share one counter (both go through Give)
            long before = Gamble.GiveToday("gla"); Gamble.Give("gla", "glb", 10, "t6"); Check(Gamble.GiveToday("gla") == before + 10, "one counter for the door");
            Economy.TestSid = null;
            Console.WriteLine(fails == 0 ? "[givelimittest] ALL PASS" : "[givelimittest] " + fails + " FAIL");
        }
    }
}
