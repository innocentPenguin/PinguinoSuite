using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "strikechecktest": 14 vs 15 minutes, once per day, day rollover, permanent strikes untouched, settings</summary>
    public static class StrikeCheckInTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        static string Q { get { return Path.Combine(HostApi.DataDir, "runtime", "strike_checkin_queue.json"); } }
        static int Queued(string login)
        {
            if (!File.Exists(Q)) return 0;
            return ((SiteHttp.ReadJ(Q)["items"] as JArray) ?? new JArray()).OfType<JObject>().Count(o => (string)o["login"] == login);
        }
        static void Walk(long from, int minutes, params string[] who) { for (int m = 0; m <= minutes; m++) StrikeCheckIn.Step(from + m * 60L, who); }
        public static void Run()
        {
            if (File.Exists(Q)) File.Delete(Q);
            StrikeCheckIn.SetSetting("on", true); StrikeCheckIn.SetSetting("minutes", 15); StrikeCheckIn.SetSetting("perDay", 1);
            StrikeCheckIn.TestTemp = l => l == "temp" ? 2 : l == "perma" ? 0 : 0;
            long d1 = new DateTimeOffset(DateTime.Today.AddHours(12)).ToUnixTimeSeconds() + 3 * 86400;
            Walk(d1, 14, "temp");
            Check(Queued("temp") == 0, "14 minutes watched: no check-in");
            StrikeCheckIn.Step(d1 + 15 * 60, new[] { "temp" });
            Check(Queued("temp") == 1, "15 minutes watched: one check-in queued");
            Walk(d1 + 16 * 60, 60, "temp");
            Check(Queued("temp") == 1, "same day, more watching: still once");
            Walk(d1 + 86400, 15, "temp");
            Check(Queued("temp") == 2, "next day: one more");
            Walk(d1, 30, "perma"); Walk(d1 + 2 * 86400, 30, "perma");
            Check(Queued("perma") == 0, "player with no temporary strikes (only permanent): never queued");
            // a break longer than the away gap restarts the stretch
            long d3 = d1 + 3 * 86400; Walk(d3, 9, "temp"); Walk(d3 + 20 * 60, 9, "temp");
            Check(Queued("temp") == 2, "a long break restarts the stretch: 10 + 10 minutes is not 15");
            // off switch
            StrikeCheckIn.SetSetting("on", false); long d4 = d1 + 4 * 86400; Walk(d4, 20, "temp");
            Check(Queued("temp") == 2, "switched off: nothing queued");
            StrikeCheckIn.SetSetting("on", true); StrikeCheckIn.SetSetting("minutes", 5); StrikeCheckIn.SetSetting("perDay", 2);
            long d5 = d1 + 5 * 86400; Walk(d5, 5, "temp");
            var last = ((SiteHttp.ReadJ(Q)["items"] as JArray)).OfType<JObject>().Last();
            Check(Queued("temp") == 3 && (int)last["n"] == 2, "minutes=5, perDay=2 are honoured");
            Check(StrikeCheckIn.Settings()["minutes"].Value<double>() == 5, "settings read back");
            StrikeCheckIn.TestTemp = null; StrikeCheckIn.SetSetting("minutes", 15); StrikeCheckIn.SetSetting("perDay", 1);
            Console.WriteLine(fails == 0 ? "[strikechecktest] ALL PASS" : "[strikechecktest] " + fails + " FAIL");
        }
    }
}
