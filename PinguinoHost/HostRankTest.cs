using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>sim line "ranktest": stored ranks with a fake live source (register fetches once, !rank answers from the store with its date, !refreshrank fetches once, no source = by hand) and prints PASS/FAIL lines</summary>
    public static class RankTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        static string Say(string user, string cmd, bool mod, params string[] args) { string said = ""; Rank.Handle(user, cmd, args, mod, m => said += (said == "" ? "" : " || ") + m); return said; }
        public static void Run()
        {
            string dir = HostApi.DataDir; var calls = new System.Collections.Generic.List<string>(); Rank.RegisterDelayMs = 50;
            File.WriteAllText(Path.Combine(dir, "players.json"), "{\"bob\":{\"Username\":\"bob\",\"Platform\":\"epic\",\"GameId\":\"BobRL\"}}");
            // 1. no live source: register saves the name only, !rank says so, a mod writes it by hand
            Rank.Fetcher = null; Rank.OnRegister("bob", new[] { "BobRL" }, false); System.Threading.Thread.Sleep(400);
            string r = Say("v", "!rank", false, "bob");
            Check(r.Contains("BobRL is registered but has no saved rank yet"), "registered, no rank: " + r);
            r = Say("m", "!refreshrank", true, "bob"); Check(r.Contains("Live rank lookup is off"), "refresh without a source: " + r);
            r = Say("m", "!setrank", true, "bob", "2v2", "Champion", "I", "Div", "II", "(1400)"); Check(r.StartsWith("Saved BobRL's rank (as of "), "setrank: " + r);
            r = Say("v", "!rank", false, "bob"); Check(r.StartsWith("BobRL - Ranked 2v2: Champion I Div II (1400) (as of "), "answers from the store: " + r);
            // 2. the streamer is RocketRankBot's: nothing from us
            Check(Say("v", "!rank", false) == "" && Say("v", "!rank", false, "innocentpenguin_") == "" && Say("v", "!rank", false, "2s") == "", "bare !rank and the streamer's name stay silent");
            // 3. a live source: one fetch at register, none at !rank, one at !refreshrank
            File.WriteAllText(Path.Combine(dir, "players.json"), "{\"bob\":{\"Username\":\"bob\",\"Platform\":\"epic\",\"GameId\":\"BobRL\"},\"amy\":{\"Username\":\"amy\",\"Platform\":\"epic\",\"GameId\":\"AmyRL\"}}");
            Rank.Fetcher = (p, e) => { calls.Add(p + ":" + e); return new JObject { { "1v1", "Gold I Div I (500)" }, { "2v2", "Platinum II Div III (800)" }, { "3v3", "Diamond I Div II (900)" }, { "hoops", "Silver II Div I (400)" } }; };
            Rank.OnRegister("amy", new[] { "AmyRL" }, false); System.Threading.Thread.Sleep(400);
            r = Say("v", "!rank", false, "amy"); Check(calls.Count == 1 && r.StartsWith("AmyRL - Ranked 1v1: Gold I Div I (500) | Ranked 2v2: Platinum II Div III (800) | Ranked 3v3: Diamond I Div II (900) (as of "), "register fetched once: " + r + " | " + string.Join(",", calls));
            Say("v", "!rank", false, "amy"); Say("v", "!rank", false, "amy", "hoops"); Check(calls.Count == 1, "!rank never fetches");
            r = Say("v", "!rank", false, "amy", "hoops"); Check(r.StartsWith("AmyRL - Ranked hoops") == false && r.Contains("Hoops: Silver II Div I (400)"), "one playlist: " + r);
            Rank.OnRegister("amy", new[] { "AmyRL" }, false); System.Threading.Thread.Sleep(400); Check(calls.Count == 1, "registering the same name again does not fetch again");
            r = Say("m", "!refreshrank", true, "amy"); Check(calls.Count == 2 && r.StartsWith("Refreshed AmyRL"), "!refreshrank fetches once: " + r);
            Check(Say("v", "!refreshrank", false, "amy") == "" && calls.Count == 2, "viewers cannot refresh");
            // 4. a mod registering someone else
            File.WriteAllText(Path.Combine(dir, "players.json"), "{\"cat\":{\"Username\":\"cat\",\"Platform\":\"epic\",\"GameId\":\"CatRL\"}}");
            Rank.OnRegister("modguy", new[] { "@cat", "CatRL" }, true); System.Threading.Thread.Sleep(400); Check(calls.Count == 3 && calls.Last() == "epic:CatRL", "mod !register @viewer fetches for the viewer: " + string.Join(",", calls));
            // 5. unknown / failing
            r = Say("v", "!rank", false, "nobodyhere"); Check(r.Contains("has no saved rank"), "unknown player: " + r);
            Rank.Fetcher = (p, e) => null; r = Say("m", "!refreshrank", true, "amy"); Check(r.Contains("Could not read") && Say("v", "!rank", false, "amy").Contains("Gold I"), "failed refresh keeps the old rank: " + r);
            Rank.Fetcher = null;
            // 6. !rank lookup <user|epic>: no live source = one honest line plus the stored rank; nothing is fetched or stored
            r = Say("v1", "!rank", false, "lookup", "amy"); Check(r.StartsWith("Live lookup isn't available yet; stored rank: AmyRL - Ranked 1v1: Gold I Div I (500)"), "lookup without a source shows the stored rank: " + r);
            r = Say("v2", "!rank", false, "lookup", "AmyRL", "hoops"); Check(r.StartsWith("Live lookup isn't available yet; stored rank: AmyRL - Hoops: Silver II Div I (400)"), "lookup by Epic name, one playlist: " + r);
            r = Say("v3", "!rank", false, "lookup", "zedd"); Check(r == "Live lookup isn't available yet; no stored rank for zedd.", "lookup of an unknown name: " + r);
            r = Say("v4", "!rank", false, "lookup"); Check(r.StartsWith("Usage: !rank lookup <Twitch name or Epic name>"), "lookup without a name: " + r);
            r = Say("v5", "!rank", false, "lookup", "innocentpenguin_"); Check(r == "That is the streamer: a bare !rank shows his rank.", "lookup of the streamer: " + r);
            Check(Say("v6", "!rank", false) == "", "bare !rank is still silent (RocketRankBot's one reply)");
            // 7. with a live source: a focused search by Epic name, nothing stored, per-person cooldown (mods exempt)
            calls.Clear(); Rank.Fetcher = (p, e) => { calls.Add(p + ":" + e); return e == "SomeEpic" ? new JObject { { "1v1", "Platinum I Div I (700)" }, { "2v2", "Diamond I Div II (900)" } } : null; };
            string lr = null; Rank.Handle("v7", "!rank", new[] { "lookup", "SomeEpic" }, false, m => lr = m); System.Threading.Thread.Sleep(300);
            Check(lr == "SomeEpic - Ranked 1v1: Platinum I Div I (700) | Ranked 2v2: Diamond I Div II (900) (live)" && calls.Count == 1 && calls[0] == "epic:SomeEpic", "live lookup by Epic name: " + lr + " | " + string.Join(",", calls));
            Check(Say("v8", "!rank", false, "someepic").Contains("has no saved rank"), "a lookup stores nothing");
            string cd = null; Rank.Handle("v7", "!rank", new[] { "lookup", "SomeEpic" }, false, m => cd = m); System.Threading.Thread.Sleep(200); Check(cd == null && calls.Count == 1, "30 s cooldown per person: no second answer, no second fetch");
            string md = null; Rank.Handle("m1", "!rank", new[] { "lookup", "SomeEpic" }, true, m => md = m); Rank.Handle("m1", "!rank", new[] { "lookup", "SomeEpic" }, true, m => md = m); System.Threading.Thread.Sleep(300); Check(calls.Count == 3 && md != null, "mods are not rate limited");
            string nf = null; Rank.Handle("v9", "!rank", new[] { "lookup", "amy" }, false, m => nf = m); System.Threading.Thread.Sleep(300);
            Check(nf != null && nf.StartsWith("Could not read AmyRL's rank right now; stored rank: AmyRL - Ranked 1v1: Gold I Div I (500)"), "a failed live read still shows the stored rank: " + nf);
            Rank.Fetcher = null;
            Console.WriteLine(fails == 0 ? "[ranktest] ALL PASS" : "[ranktest] " + fails + " FAILED");
        }
    }
}
