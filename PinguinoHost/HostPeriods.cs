using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Everything that can be counted, by day / ISO week / month / year / all time, with old periods kept and browsable (nothing is ever reset).
    /// SOURCE OF TRUTH: the append-only event log Data\boards\metric_events.jsonl, one JSON line per event {ts (unix s), user (lowercase login), metric, amount, id?, grain?}.
    ///   id   makes an event apply ONCE (a retry, a restart or a re-run of the backfill never counts it twice).
    ///   grain "month" / "year" marks an event that is only known for that month / year (an old monthly total): it counts for that month, year and all time, never for a day or a week.
    /// DERIVED (rebuildable at any time, POST /api/boards/reload or Tools\rebuild-buckets.py): the in-memory buckets metric > period key > user > sum.
    /// Period keys are in ONE timezone (Tz below, America/Chicago): day YYYY-MM-DD, ISO week YYYY-Www, month YYYY-MM, year YYYY, "all". A "stream day" can be shifted so a late stream stays on
    /// the day it started (DayShiftHours, 0 = plain local midnight).
    /// Metrics: watchtime (minutes), points (earned), points_spent, messages, xp (derived: 1 per watched minute + 2 per chat message), gifts, bits, follows, refollows, commands, wins.
    /// API metric "level" ranks by xp gained in the period and shows the level (value) and % to the next one (pct).</summary>
    public static class Periods
    {
        public const string Tz = "America/Chicago";            // the one timezone constant (env PINGUINO_BOARD_TZ overrides it for tests)
        public const double DayShiftHours = 0;                  // 0 = local midnight. 4 would keep a stream that runs until 3 am on the day it started.
        public const double XpPerLevelSq = 50;                  // level = 1 + floor(sqrt(xp / 50))
        public const double XpPerMinute = 1, XpPerMessage = 2;
        public static readonly string[] Known = { "watchtime", "points", "points_spent", "points_backpay", "messages", "xp", "gifts", "bits", "follows", "refollows", "commands", "wins" };
        public static readonly string[] Pers = { "day", "week", "month", "year", "all" };

        static readonly object L = new object();
        static readonly Dictionary<string, Dictionary<string, Dictionary<string, double>>> B = new Dictionary<string, Dictionary<string, Dictionary<string, double>>>();
        static readonly Dictionary<string, SortedDictionary<string, double>> XpCum = new Dictionary<string, SortedDictionary<string, double>>();   // user > "yyyy-MM-dd" (month grain: "yyyy-MM-99") > xp
        static readonly HashSet<string> Ids = new HashSet<string>();
        static readonly Dictionary<string, JObject> Pending = new Dictionary<string, JObject>();   // coalesced high-frequency events, written every FlushSec
        static bool _loaded, _started; static DateTime _updated = DateTime.UtcNow; static TimeZoneInfo _zone;
        static string FileP { get { return Path.Combine(Boards.RootDir, "boards", "metric_events.jsonl"); } }
        static int FlushSec { get { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_BOARD_FLUSH_SEC"), out v) && v > 0 ? v : 300; } }

        static TimeZoneInfo Zone
        {
            get
            {
                if (_zone != null) return _zone;
                string id = Environment.GetEnvironmentVariable("PINGUINO_BOARD_TZ"); if (string.IsNullOrEmpty(id)) id = Tz;
                foreach (var t in new[] { id, id == "America/Chicago" ? "Central Standard Time" : id })
                    try { return _zone = TimeZoneInfo.FindSystemTimeZoneById(t); } catch (Exception) { }
                Clog.Warn("boards", "timezone " + id + " not found: using UTC"); return _zone = TimeZoneInfo.Utc;
            }
        }

        // ---------- keys ----------
        static DateTime LocalDay(long ts) { var u = DateTimeOffset.FromUnixTimeSeconds(ts).UtcDateTime; return TimeZoneInfo.ConvertTimeFromUtc(u, Zone).AddHours(-DayShiftHours); }
        public static string DayKey(long ts) { return LocalDay(ts).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture); }
        public static string WeekKey(long ts) { var d = LocalDay(ts); return ISOWeek.GetYear(d).ToString("0000") + "-W" + ISOWeek.GetWeekOfYear(d).ToString("00"); }
        public static string MonthKey(long ts) { return LocalDay(ts).ToString("yyyy-MM", CultureInfo.InvariantCulture); }
        public static string YearKey(long ts) { return LocalDay(ts).ToString("yyyy", CultureInfo.InvariantCulture); }
        public static string KeyFor(string period, long ts) { switch (period) { case "day": return DayKey(ts); case "week": return WeekKey(ts); case "month": return MonthKey(ts); case "year": return YearKey(ts); default: return "all"; } }
        static string PeriodOfKey(string k) { if (k == "all") return "all"; if (k.Contains("W")) return "week"; return k.Length == 10 ? "day" : k.Length == 7 ? "month" : "year"; }
        /// <summary>the last sortable day of a period ("yyyy-MM-dd"; month-grain uses -99 so it sorts after real days): the level a person had when it ended</summary>
        static string EndOfKey(string k)
        {
            switch (PeriodOfKey(k))
            {
                case "day": return k;
                case "month": return k + "-99";
                case "year": return k + "-12-99";
                case "week": { int y = int.Parse(k.Substring(0, 4)), w = int.Parse(k.Substring(6)); return ISOWeek.ToDateTime(y, w, DayOfWeek.Sunday).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture); }
                default: return "9999-99-99";
            }
        }

        // ---------- ingest ----------
        public static void Start()
        {
            if (_started) return; _started = true;
            var t = new Thread(() => { while (true) { Thread.Sleep(FlushSec * 1000); try { Flush(); } catch (Exception ex) { Clog.Warn("boards", "periods flush: " + ex.Message); } } }) { IsBackground = true, Name = "periods-flush" };
            t.Start();
        }

        static void EnsureLoaded() { if (!_loaded) { _loaded = true; LoadFile(); } }
        static void LoadFile()
        {
            B.Clear(); XpCum.Clear(); Ids.Clear(); int bad = 0;
            try
            {
                if (File.Exists(FileP))
                    foreach (var line in File.ReadLines(FileP))
                    {
                        if (line.Length < 5) continue;
                        try { var o = JObject.Parse(line); Ingest(o, false); } catch (Exception) { bad++; }
                    }
            }
            catch (Exception ex) { Clog.Warn("boards", "metric_events.jsonl unreadable: " + ex.Message); }
            if (bad > 0) Clog.Warn("boards", bad + " unreadable lines in metric_events.jsonl were skipped");
        }

        static void Bump(string metric, string key, string user, double amount)
        {
            Dictionary<string, Dictionary<string, double>> m; if (!B.TryGetValue(metric, out m)) B[metric] = m = new Dictionary<string, Dictionary<string, double>>();
            Dictionary<string, double> k; if (!m.TryGetValue(key, out k)) m[key] = k = new Dictionary<string, double>();
            double v; k.TryGetValue(user, out v); k[user] = v + amount;
        }
        static void BumpAll(string metric, string user, double amount, long ts, string grain)
        {
            if (grain == null || grain == "") { Bump(metric, DayKey(ts), user, amount); Bump(metric, WeekKey(ts), user, amount); }
            if (grain == null || grain == "" || grain == "month") Bump(metric, MonthKey(ts), user, amount);
            Bump(metric, YearKey(ts), user, amount); Bump(metric, "all", user, amount);
        }
        static void Ingest(JObject o, bool fresh)
        {
            string user = ((string)o["user"] ?? "").Trim().TrimStart('@').ToLowerInvariant(), metric = ((string)o["metric"] ?? "").ToLowerInvariant(), id = (string)o["id"], grain = (string)o["grain"];
            double amount = (double?)o["amount"] ?? 0; long ts = (long?)o["ts"] ?? 0;
            if (user == "" || user == "anonymous" || metric == "" || amount <= 0 || ts <= 0) return;
            if (!string.IsNullOrEmpty(id) && !Ids.Add(id)) return;
            if (metric == "points" && id != null && (id.StartsWith("ap:backfill:") || id.StartsWith("ap:grant-") || id.StartsWith("ap:backpay"))) metric = "points_backpay";   // back-pay and admin grants are not points GAINED by playing: kept apart (also for lines logged before this rule)
            BumpAll(metric, user, amount, ts, grain);
            double xp = metric == "watchtime" ? amount * XpPerMinute : metric == "messages" ? amount * XpPerMessage : 0;
            if (xp > 0)
            {
                BumpAll("xp", user, xp, ts, grain);
                SortedDictionary<string, double> sd; if (!XpCum.TryGetValue(user, out sd)) XpCum[user] = sd = new SortedDictionary<string, double>(StringComparer.Ordinal);
                string dk = grain == "year" ? YearKey(ts) + "-12-99" : grain == "month" ? MonthKey(ts) + "-99" : DayKey(ts); double v; sd.TryGetValue(dk, out v); sd[dk] = v + xp;
            }
            _updated = DateTime.UtcNow;
        }

        /// <summary>count one event now (appended to the log at once). Returns false when the id was already applied or the event is empty.</summary>
        public static bool Add(string user, string metric, double amount, long ts = 0, string id = null, string grain = null)
        {
            try
            {
                if (ts <= 0) ts = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                var o = new JObject { { "ts", ts }, { "user", (user ?? "").Trim().TrimStart('@').ToLowerInvariant() }, { "metric", metric }, { "amount", amount } };
                if (!string.IsNullOrEmpty(id)) o["id"] = id; if (!string.IsNullOrEmpty(grain)) o["grain"] = grain;
                lock (L)
                {
                    EnsureLoaded(); int ids = Ids.Count; double before = Total(metric, (string)o["user"]); Ingest(o, true);
                    if (!string.IsNullOrEmpty(id) ? Ids.Count == ids : Total(metric, (string)o["user"]) == before) return false;
                    Append(new[] { o.ToString(Newtonsoft.Json.Formatting.None) }); return true;
                }
            }
            catch (Exception ex) { Clog.Warn("boards", "period event: " + ex.Message); return false; }
        }
        static double Total(string metric, string user) { Dictionary<string, Dictionary<string, double>> m; Dictionary<string, double> k; double v = 0; if (B.TryGetValue(metric, out m) && m.TryGetValue("all", out k)) k.TryGetValue(user, out v); return v; }

        /// <summary>count a frequent event (a watched minute, a chat message): buckets move now, the log gets one coalesced line per person, metric and day every few minutes</summary>
        public static void AddBuffered(string user, string metric, double amount, long ts = 0)
        {
            try
            {
                if (ts <= 0) ts = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); user = (user ?? "").Trim().TrimStart('@').ToLowerInvariant();
                lock (L)
                {
                    EnsureLoaded(); var o = new JObject { { "ts", ts }, { "user", user }, { "metric", metric }, { "amount", amount } }; Ingest(o, true);
                    string key = user + "|" + metric + "|" + DayKey(ts); JObject p;
                    if (Pending.TryGetValue(key, out p)) { p["amount"] = (double)p["amount"] + amount; p["ts"] = ts; } else Pending[key] = o;
                }
            }
            catch (Exception ex) { Clog.Warn("boards", "period event: " + ex.Message); }
        }
        public static void Flush()
        {
            lock (L)
            {
                if (Pending.Count == 0) return;
                Append(Pending.Values.Select(p => p.ToString(Newtonsoft.Json.Formatting.None))); Pending.Clear();
            }
        }
        static void Append(IEnumerable<string> lines)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FileP)); File.AppendAllText(FileP, string.Join("\n", lines) + "\n", new UTF8Encoding(false));
        }
        /// <summary>throw the derived buckets away and read the log again (also picks up lines a backfill script appended)</summary>
        public static JObject Reload() { lock (L) { Flush(); _loaded = true; LoadFile(); return new JObject { { "ok", true }, { "metrics", B.Count }, { "ids", Ids.Count } }; } }

        // ---------- queries ----------
        static string Mapped(string metric)
        {
            metric = (metric ?? "").ToLowerInvariant();
            switch (metric) { case "watch": case "watchtime": case "watch_time": return "watchtime"; case "point": case "points": case "points_gained": case "gained": case "earned": return "points"; case "points_backpay": return "points_backpay"; case "spent": case "points_spent": return "points_spent"; case "chat": case "yap": case "messages": return "messages"; case "level": case "levels": case "lvl": return "level"; case "gift": case "gifts": return "gifts"; case "bit": case "bits": return "bits"; case "xp": return "xp"; case "follow": case "follows": return "follows"; case "refollows": return "refollows"; case "command": case "commands": return "commands"; case "win": case "wins": return "wins"; default: return ""; }
        }
        public static string Metric(string s) { return Mapped(s); }
        static Dictionary<string, double> Folded(string metric, string key)
        {
            var o = new Dictionary<string, double>(); Dictionary<string, Dictionary<string, double>> m; Dictionary<string, double> k;
            if (!B.TryGetValue(metric, out m) || !m.TryGetValue(key, out k)) return o;
            foreach (var kv in k)
            {
                if (Boards.IsBot(kv.Key) || Boards.IsAnon(kv.Key)) continue;
                string c = Boards.CanonLogin(kv.Key); if (Boards.IsBot(c)) continue; double v; o.TryGetValue(c, out v); o[c] = v + kv.Value;
            }
            return o;
        }
        static double Lifetime(string user, string uptoSortKey)
        {
            double t = 0; SortedDictionary<string, double> sd;
            foreach (var kv in Boards.AliasMap().Where(a => a.Value == user).Select(a => a.Key).Concat(new[] { user }))
                if (XpCum.TryGetValue(kv, out sd)) foreach (var e in sd) { if (string.CompareOrdinal(e.Key, uptoSortKey) > 0) break; t += e.Value; }
            return t;
        }
        public static int LevelOf(double xp) { return 1 + (int)Math.Floor(Math.Sqrt(Math.Max(0, xp) / XpPerLevelSq)); }
        public static double LevelPct(double xp) { int l = LevelOf(xp); double lo = XpPerLevelSq * (l - 1) * (l - 1), hi = XpPerLevelSq * l * l; return Math.Round(100.0 * (xp - lo) / (hi - lo), 1); }

        /// <summary>GET /api/boards?metric=&period=&key=&login=&top=</summary>
        public static JObject Query(string metricIn, string period, string key, string me = null, int top = 10)
        {
            string metric = Mapped(metricIn); period = (period ?? "").ToLowerInvariant(); if (period == "") period = "week";
            if (metric == "") return new JObject { { "ok", false }, { "error", "metric must be one of watchtime, points, messages, level, gifts, bits (also spent, xp, follows, refollows, commands, wins)" } };
            if (!Pers.Contains(period)) return new JObject { { "ok", false }, { "error", "period must be day, week, month, year or all" } };
            top = Math.Max(1, Math.Min(100, top));
            lock (L)
            {
                EnsureLoaded(); string src = metric == "level" ? "xp" : metric;
                long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); key = (key ?? "").Trim();
                if (period == "all") key = "all"; else if (key == "") key = KeyFor(period, now);
                var keys = new List<string>(); Dictionary<string, Dictionary<string, double>> mm;
                if (period == "all") keys.Add("all");
                else if (B.TryGetValue(src, out mm)) keys.AddRange(mm.Keys.Where(k => PeriodOfKey(k) == period).OrderByDescending(k => k, StringComparer.Ordinal));
                var f = Folded(src, key); string endKey = EndOfKey(key);
                var ranked = f.Where(kv => kv.Value > 0).OrderByDescending(kv => kv.Value).ThenBy(kv => kv.Key, StringComparer.Ordinal).ToList();
                Func<KeyValuePair<string, double>, JToken> val = kv => { if (metric == "level") return LevelOf(Lifetime(kv.Key, endKey)); double x = Math.Floor(kv.Value * 100) / 100; return x == Math.Floor(x) ? (JToken)(long)x : (JToken)x; };
                var rows = new JArray(); int rank = 0;
                foreach (var kv in ranked.Take(top))
                {
                    rank++; var r = new JObject { { "rank", rank }, { "login", kv.Key }, { "name", Boards.DisplayName(kv.Key) }, { "value", val(kv) } };
                    if (metric == "level") r["pct"] = LevelPct(Lifetime(kv.Key, endKey)); rows.Add(r);
                }
                var res = new JObject { { "ok", true }, { "metric", metric }, { "period", period }, { "key", key }, { "keys", new JArray(keys) }, { "updatedAt", _updated.ToString("yyyy-MM-ddTHH:mm:ssZ") }, { "total", ranked.Count }, { "rows", rows }, { "tz", Tz } };
                string who = Boards.CanonLogin(me ?? ""); if (who != "")
                {
                    int i = ranked.FindIndex(kv => kv.Key == who);
                    if (i >= 0) { var m = new JObject { { "rank", i + 1 }, { "value", val(ranked[i]) } }; if (metric == "level") m["pct"] = LevelPct(Lifetime(who, endKey)); res["me"] = m; }
                }
                return res;
            }
        }

        /// <summary>value of one person for the current day / week / month / year / all (chat one-liners)</summary>
        public static double Value(string login, string metric, string period)
        {
            lock (L)
            {
                EnsureLoaded(); string who = Boards.CanonLogin(login); long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); double v;
                Folded(metric, KeyFor(period, now)).TryGetValue(who, out v); return v;
            }
        }
        /// <summary>" | today X, this week Y, this month Z" (empty when there is nothing at all)</summary>
        public static string Line(string login, string metric)
        {
            try
            {
                Func<double, string> fmt = v => metric == "watchtime" ? Economy.Dur(v) : Economy.Num(v);
                double d = Value(login, metric, "day"), w = Value(login, metric, "week"), m = Value(login, metric, "month");
                if (d <= 0 && w <= 0 && m <= 0) return "";
                return " | " + (metric == "points" ? "earned " : "") + "today " + fmt(d) + ", this week " + fmt(w) + ", this month " + fmt(m);
            }
            catch (Exception) { return ""; }
        }

        static string PeriodWord(string p) { return p == "day" ? "today" : p == "week" ? "this week" : p == "month" ? "this month" : p == "year" ? "this year" : "all time"; }
        /// <summary>!top / !leaders &lt;metric&gt; [day|week|month|year|all]</summary>
        public static void ChatTop(string[] args, Action<string> say, string link)
        {
            string metric = "", period = "";
            foreach (var a in args)
            {
                string x = a.ToLowerInvariant();
                switch (x) { case "day": case "today": case "daily": period = "day"; continue; case "week": case "weekly": period = "week"; continue; case "month": case "monthly": period = "month"; continue; case "year": case "yearly": period = "year"; continue; case "all": case "alltime": case "lifetime": period = "all"; continue; }
                string m = Mapped(x); if (m != "" && metric == "") metric = m;
            }
            if (metric == "") { say("Usage: !top <watchtime|points|messages|level|gifts|bits> [day|week|month|year|all]"); return; }
            if (period == "") period = "week";
            var q = Query(metric, period, "", null, 5); var rows = (JArray)q["rows"];
            string title = metric == "watchtime" ? "Most watch time" : metric == "points" ? "Most " + Economy.CurrencyName + " earned" : metric == "messages" ? "Most chat messages" : metric == "level" ? "Top levels" : metric == "gifts" ? "Most gifted subs" : metric == "bits" ? "Most bits" : "Top " + metric;
            if (rows.Count == 0) { say("Nobody on the " + metric + " board " + PeriodWord(period) + " yet. " + link); return; }
            Func<JObject, string> fmt = r => metric == "watchtime" ? Economy.Dur((double)r["value"]) : metric == "level" ? "lvl " + (int)r["value"] : Economy.Num((double)r["value"]);
            say(title + " " + PeriodWord(period) + ": " + string.Join(" | ", rows.OfType<JObject>().Select(r => (int)r["rank"] + ". " + (string)r["name"] + " " + fmt(r))) + " - " + link);
        }

        /// <summary>what the site push carries: for the main metrics the top rows of the current and recent periods, every month and year, and all time (old periods stay browsable)</summary>
        public static JObject ForSite()
        {
            var o = new JObject(); Dictionary<string, int> keep = new Dictionary<string, int> { { "day", 14 }, { "week", 12 }, { "month", 1000 }, { "year", 1000 } };
            foreach (var met in new[] { "watchtime", "points", "points_gained", "messages", "level", "gifts", "bits" })
            {
                var pm = new JObject();
                foreach (var per in Pers)
                {
                    var first = Query(met, per, "", null, 100); var all = new JObject(); var keys = ((JArray)first["keys"]).Select(x => (string)x).ToList();
                    int n = per == "all" ? 1 : keep[per];
                    string cur = (string)first["key"]; if (!keys.Contains(cur)) keys.Insert(0, cur);
                    foreach (var k in keys.Take(n)) { var r = k == cur ? first : Query(met, per, k, null, 100); if (((JArray)r["rows"]).Count > 0) all[k] = new JObject { { "total", r["total"] }, { "rows", r["rows"] } }; }
                    pm[per] = new JObject { { "current", cur }, { "keys", new JArray(keys) }, { "boards", all } };
                }
                o[met] = pm;
            }
            try { o["firsts"] = Firsts.ForSite(); } catch (Exception ex) { Clog.Warn("boards", "firsts for the site: " + ex.Message); }
            return o;
        }
        /// <summary>live Twitch events (called from Program.DispatchEvent). Gifts and bits come through Boards.Add (one door, same ledger).</summary>
        public static void OnEvent(Dictionary<string, object> a)
        {
            try
            {
                object et, u; if (!a.TryGetValue("eventType", out et) || !a.TryGetValue("userName", out u)) return;
                if (Convert.ToString(et) != "TwitchFollow") return;
                string who = (Convert.ToString(u) ?? "").ToLowerInvariant(); if (who == "") return;
                long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); bool again; lock (L) { EnsureLoaded(); again = Total("follows", who) + Total("refollows", who) > 0; }
                Add(who, again ? "refollows" : "follows", 1, now, "follow:" + who + ":" + (now / 60));
            }
            catch (Exception ex) { Clog.Warn("boards", "follow event: " + ex.Message); }
        }

        /// <summary>POST /api/boards/event (only with PINGUINO_ECONOMY_TESTHOOK=1): {user, metric, amount, ts, id, grain}</summary>
        public static JObject TestEvent(JObject b)
        {
            if (Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_TESTHOOK") != "1") return new JObject { { "ok", false }, { "error", "test hook is off" } };
            bool ok = Add((string)b["user"], (string)b["metric"], (double?)b["amount"] ?? 0, (long?)b["ts"] ?? 0, (string)b["id"], (string)b["grain"]);
            return new JObject { { "ok", true }, { "applied", ok } };
        }

        public static JObject Status() { lock (L) { EnsureLoaded(); return new JObject { { "tz", Tz }, { "metrics", new JArray(B.Keys) }, { "ids", Ids.Count }, { "pending", Pending.Count }, { "file", FileP } }; } }
    }
}
