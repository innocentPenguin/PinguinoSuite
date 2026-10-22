using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "ranktest": runs the !rank source chain against a fake fetcher (all fail / partial fail / stale / backoff / prefix / fuzzy) and prints PASS/FAIL lines</summary>
    public static class RankTest
    {
        const string Body = "{\"data\":{\"platformInfo\":{\"platformUserHandle\":\"Alice\"},\"segments\":[{\"type\":\"playlist\",\"attributes\":{\"playlistId\":11},\"metadata\":{\"name\":\"Ranked Doubles 2v2\"},\"stats\":{\"tier\":{\"metadata\":{\"name\":\"Champion I\"}},\"division\":{\"metadata\":{\"name\":\"Division II\"}},\"rating\":{\"value\":\"1400\"}}}]}}";
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        static string Ask(string who, params string[] extra)
        {
            string said = ""; Rank.Handle("viewer", "!rank", new[] { who }.Concat(extra).Where(x => x != "").ToArray(), false, m => said += (said == "" ? "" : " || ") + m); return said;
        }
        public static void Run()
        {
            var calls = new List<string>(); string dir = HostApi.DataDir;
            // 1. every source fails and nothing is cached: a plain "no data", never "paused"
            Rank.TestFetch = (s, p, n) => { calls.Add(s + "/" + p + "/" + n); return null; };
            string r = Ask("zoe123");
            Check(r != "" && !r.ToLowerInvariant().Contains("paused") && r.Contains("No rank data"), "all sources fail, no cache: '" + r + "'");
            // 2. partial failure: tracker-api fails, the next source works -> answered, becomes the first choice next time
            Rank.TestClearBackoff(); calls.Clear(); Rank.TestFetch = (s, p, n) => { calls.Add(s); return s == "tracker-api-alt" ? Body : null; };
            r = Ask("bob2000");
            Check(r.Contains("Ranked 2v2: Champion I Div II (1400)") && calls.SequenceEqual(new[] { "tracker-api", "tracker-api-alt" }), "partial failure answered by the 2nd source: " + r + " | " + string.Join(",", calls));
            Rank.TestAge("epic:bob2000", 4000);
            calls.Clear(); r = Ask("bob2000");
            Check(calls.FirstOrDefault() == "tracker-api-alt" && r.Contains("1400"), "the source that worked last time is asked first: " + string.Join(",", calls));
            // 3. per-source backoff: a failing source is not retried at once for another player
            calls.Clear(); Ask("carl9999");
            Check(!calls.Contains("tracker-api"), "tracker-api is in backoff, only the others are tried: " + string.Join(",", calls));
            // 4. stale: cache 5 h old, every source fails -> old values with the age
            Rank.TestFetch = (s, p, n) => Body; Rank.TestReset(); Ask("dave4444");
            Rank.TestAge("epic:dave4444", 5 * 3600); Rank.TestFetch = (s, p, n) => null; Rank.TestClearBackoff();
            r = Ask("dave4444");
            Check(r.Contains("1400") && r.Contains("(as of 5h ago)"), "stale cache answers with its age: " + r);
            // 5. platform prefix reaches the fetcher
            string seen = ""; Rank.TestFetch = (s, p, n) => { seen = p + "/" + n; return Body; }; Rank.TestClearBackoff();
            r = Ask("steam:SomeGuy");
            Check(seen.ToLowerInvariant() == "steam/someguy" && r.Contains("1400"), "steam: prefix: " + seen);
            // 6. fuzzy match against a known chatter (players.json) and the learned map
            File.WriteAllText(Path.Combine(dir, "players.json"), "{\"flipreset\":{\"Username\":\"flipreset\",\"Platform\":\"epic\",\"GameId\":\"FlipReset99\"}}");
            seen = ""; Rank.TestClearBackoff(); r = Ask("flipresett");
            Check(seen == "epic/flipreset99", "fuzzy chatter name -> epic name: " + seen);
            // 7. notfound is definitive, not a failure of the chain
            Rank.TestFetch = (s, p, n) => "{\"errors\":[{\"code\":\"CollectorResultStatus::NotFound\"}]}"; Rank.TestClearBackoff();
            r = Ask("nobodyhere1");
            Check(r.Contains("Could not find"), "not found: " + r);
            // 8. health is exposed per source
            var h = Rank.HealthJson();
            Check(h["sources"]["tracker-api"] != null && (string)h["lastGoodSource"] != null, "health lists every source: " + h["sources"].Count());
            Rank.TestFetch = null;
            Console.WriteLine(fails == 0 ? "[ranktest] ALL PASS" : "[ranktest] " + fails + " FAILED");
        }
    }
}
