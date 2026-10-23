using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Strike check-in (quiet, no chat/site/command text): a player with TEMPORARY strikes who has watched the live stream for one continuous stretch of N minutes (default 15, from the economy watch tracking, WatchStep)
    /// loses strikes once per day (default 1, "day" = local date). Permanent strikes and bans are never touched. The Host decides and writes the request to Data\runtime\strike_checkin_queue.json; Core (the only writer of players.json)
    /// applies it in its 30 s live check and writes strike_checkin_done.jsonl; each removal is then logged in the mod audit log (actor: system).
    /// Settings (Suite > Queue, or Data\runtime\strike_checkin_settings.json): on (default true), minutes (15), perDay (1).</summary>
    public static class StrikeCheckIn
    {
        static readonly object L = new object(); static bool _started;
        static string Dir { get { return Path.Combine(HostApi.DataDir, "runtime"); } }
        static string SetP { get { return Path.Combine(Dir, "strike_checkin_settings.json"); } }
        static string StateP { get { return Path.Combine(Dir, "strike_checkin_state.json"); } }
        static string QueueP { get { return Path.Combine(Dir, "strike_checkin_queue.json"); } }
        static string DoneP { get { return Path.Combine(Dir, "strike_checkin_done.jsonl"); } }
        static readonly Dictionary<string, long[]> Track = new Dictionary<string, long[]>();   // login -> {stretch start, last seen}
        static string _day = ""; static HashSet<string> _done = new HashSet<string>(); static bool _loaded;
        static DateTime _pMt = DateTime.MinValue; static Dictionary<string, int> _temp = new Dictionary<string, int>();
        internal static Func<string, int> TestTemp;   // test hook: temporary strikes of a login

        public static JObject Settings()
        {
            var j = SiteHttp.ReadJ(SetP);
            return new JObject { { "on", (bool?)j["on"] ?? true }, { "minutes", Math.Max(0.01, Math.Min(240, (double?)j["minutes"] ?? 15)) }, { "perDay", Math.Max(1, Math.Min(10, (int?)j["perDay"] ?? 1)) } };
        }
        public static void SetSetting(string key, JToken v) { var j = SiteHttp.ReadJ(SetP); j[key] = v; Directory.CreateDirectory(Dir); SiteHttp.WriteJ(SetP, j); }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(12000); while (true) { try { ReadDone(); } catch (Exception) { } await Task.Delay(20000); } });
        }

        static string DayOf(long now) { return DateTimeOffset.FromUnixTimeSeconds(now).ToLocalTime().ToString("yyyy-MM-dd"); }

        static int TempStrikes(string login)
        {
            if (TestTemp != null) return TestTemp(login);
            try
            {
                string f = Path.Combine(HostApi.DataDir, "players.json"); string g = Path.Combine(Dir, "players.json");
                if (!File.Exists(f) || (File.Exists(g) && File.GetLastWriteTimeUtc(g) > File.GetLastWriteTimeUtc(f))) f = g; if (!File.Exists(f)) return 0;
                var mt = File.GetLastWriteTimeUtc(f);
                if (mt != _pMt)
                {
                    var j = JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)); var m = new Dictionary<string, int>();
                    foreach (var p in j.Properties()) { var o = p.Value as JObject; if (o == null) continue; int t = ((int?)o["Strikes"] ?? 0) + ((int?)o["Fn"]?["Strikes"] ?? 0); if (t > 0) m[p.Name.ToLowerInvariant()] = t; }
                    _temp = m; _pMt = mt;
                }
                int n; return _temp.TryGetValue(login, out n) ? n : 0;
            }
            catch (Exception) { return 0; }
        }

        /// <summary>one watch step (about once a minute while live) with everybody present now. Never throws.</summary>
        public static void Step(long now, IEnumerable<string> present)
        {
            try
            {
                var set = Settings(); if ((bool?)set["on"] != true) return;
                long need = (long)Math.Round((double)set["minutes"] * 60); int per = (int)set["perDay"]; const long gap = 150;
                var add = new List<JObject>();
                lock (L)
                {
                    if (!_loaded) { _loaded = true; var s = SiteHttp.ReadJ(StateP); _day = (string)s["day"] ?? ""; _done = new HashSet<string>((s["done"] as JArray ?? new JArray()).Select(x => (string)x)); }
                    string day = DayOf(now); if (day != _day) { _day = day; _done = new HashSet<string>(); Save(); }
                    var here = new HashSet<string>(present);
                    foreach (var c in here)
                    {
                        long[] t; if (!Track.TryGetValue(c, out t) || now - t[1] > gap) Track[c] = t = new long[] { now, now }; t[1] = now;
                        if (now - t[0] < need || _done.Contains(c)) continue;
                        if (TempStrikes(c) <= 0) continue;   // nothing to remove: the day's check-in stays available
                        _done.Add(c); add.Add(new JObject { { "login", c }, { "n", per }, { "at", now } });
                    }
                    foreach (var k in Track.Where(kv => !here.Contains(kv.Key) && now - kv.Value[1] > gap).Select(kv => kv.Key).ToList()) Track.Remove(k);
                    if (add.Count > 0) { Save(); var q = SiteHttp.ReadJ(QueueP); var arr = q["items"] as JArray ?? new JArray(); foreach (var a in add) arr.Add(a); q["items"] = arr; Directory.CreateDirectory(Dir); SiteHttp.WriteJ(QueueP, q); }
                }
            }
            catch (Exception ex) { Clog.Warn("strikes", "check-in step failed: " + ex.Message); }
        }
        static void Save() { Directory.CreateDirectory(Dir); SiteHttp.WriteJ(StateP, new JObject { { "day", _day }, { "done", new JArray(_done) } }); }

        /// <summary>what Core did: log each removal (actor: system)</summary>
        static void ReadDone()
        {
            if (!File.Exists(DoneP)) return; string[] lines;
            lock (L) { lines = File.ReadAllLines(DoneP, Encoding.UTF8); File.Delete(DoneP); }
            foreach (var l in lines) { JObject j; try { j = JObject.Parse(l); } catch (Exception) { continue; } int b = (int?)j["before"] ?? 0, a = (int?)j["after"] ?? 0; ModAudit.Log("system", "system", "strike check-in", (string)j["login"], b + " temporary strikes", a + " temporary strikes"); }
        }
        internal static void TestReadDone() { ReadDone(); }
    }
}
