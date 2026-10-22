using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Leaderboard cards for the queue overlay's idle mode (GET /api/queue-idle). The overlay shows them while nobody is in the queue and no match is running.
    /// Config: Data\runtime\queue_idle.json (written with these defaults when missing; edit freely):
    ///   enabled, idleSeconds (quiet time before the cards start), secondsPerCard, top (rows per card, 3-10),
    ///   sequence = list of items; an item is a card {metric, period} or a CHAIN [card, card, ...] that is always shown in that order (similar boards flowing into each other).
    ///   The overlay shuffles the items (a shuffle bag, so the order differs each round) but keeps the order inside a chain.
    /// metric: gifts, bits, level, watchtime, points, messages, wins, follows, commands.  period: week, month, lastmonth, year, all.
    /// Data comes from the public boards (Periods.Query): bots and !optmeout viewers are already left out, nothing private is read. Cached 60 s, empty cards are left out.</summary>
    public static class QueueIdle
    {
        static readonly object L = new object();
        static JObject _cache; static DateTime _at = DateTime.MinValue; static string _cfgStamp = "";
        static string Path_ { get { return Path.Combine(HostApi.DataDir, "queue_idle.json"); } }

        public static JObject DefaultConfig()
        {
            Func<string, string, JObject> c = (m, p) => new JObject { { "metric", m }, { "period", p } };
            return new JObject
            {
                { "enabled", true }, { "idleSeconds", 20 }, { "secondsPerCard", 8 }, { "top", 8 },
                { "sequence", new JArray {
                    new JArray { c("gifts", "month"), c("bits", "month") },
                    new JArray { c("gifts", "month"), c("gifts", "all") },
                    new JArray { c("gifts", "month"), c("gifts", "lastmonth") },
                    new JArray { c("bits", "month"), c("bits", "lastmonth") },
                    new JArray { c("watchtime", "month"), c("watchtime", "all") },
                    new JArray { c("level", "month"), c("level", "all") },
                    c("points", "all"), c("messages", "month") } }
            };
        }
        static JObject Config()
        {
            var def = DefaultConfig();
            try
            {
                if (!File.Exists(Path_)) { File.WriteAllText(Path_, def.ToString()); return def; }
                var j = JObject.Parse(File.ReadAllText(Path_).TrimStart((char)0xFEFF));
                foreach (var p in def.Properties()) if (j[p.Name] == null) j[p.Name] = p.Value;
                return j;
            }
            catch (Exception) { return def; }
        }
        static string PrevMonth(string k)
        {
            try { int y = int.Parse(k.Substring(0, 4)), m = int.Parse(k.Substring(5, 2)); if (--m < 1) { m = 12; y--; } return y.ToString("0000") + "-" + m.ToString("00"); } catch (Exception) { return k; }
        }
        static readonly Dictionary<string, string> Names = new Dictionary<string, string> { { "gifts", "TOP GIFTERS" }, { "bits", "TOP CHEERERS" }, { "level", "TOP LEVELS" }, { "watchtime", "MOST WATCH TIME" }, { "points", "TOP POINTS" }, { "messages", "TOP CHATTERS" }, { "wins", "MOST WINS" }, { "follows", "TOP FOLLOWS" }, { "commands", "TOP COMMANDS" } };
        static readonly Dictionary<string, string> Per = new Dictionary<string, string> { { "week", "THIS WEEK" }, { "month", "THIS MONTH" }, { "lastmonth", "LAST MONTH" }, { "year", "THIS YEAR" }, { "all", "ALL TIME" } };
        static readonly Dictionary<string, string> Unit = new Dictionary<string, string> { { "gifts", "subs" }, { "bits", "bits" }, { "level", "level" }, { "watchtime", "time" }, { "points", "pts" }, { "messages", "msgs" } };

        static JObject Card(JToken t, int top)
        {
            string metric = Periods.Metric((string)t["metric"] ?? ""); string per = ((string)t["period"] ?? "month").ToLowerInvariant();
            if (metric == "" || !Per.ContainsKey(per)) return null;
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); string period = per, key = "";
            if (per == "lastmonth") { period = "month"; key = PrevMonth(Periods.KeyFor("month", now)); }
            var q = Periods.Query(metric, period, key, null, top);
            var rows = q["rows"] as JArray; if (rows == null || rows.Count == 0) return null;
            string nm; if (!Names.TryGetValue(metric, out nm)) nm = metric.ToUpperInvariant(); string un; if (!Unit.TryGetValue(metric, out un)) un = "";
            return new JObject { { "id", metric + "|" + per }, { "metric", metric }, { "period", per }, { "title", nm + " · " + Per[per] }, { "unit", un },
                { "rows", new JArray(rows.Select(r => { var o = new JObject { { "rank", r["rank"] }, { "name", r["name"] }, { "value", r["value"] } }; if (r["pct"] != null) o["pct"] = r["pct"]; return o; })) } };
        }
        /// <summary>{enabled, idleSeconds, secondsPerCard, items:[ [card,...], ... ]} - every item is a chain of 1+ cards; empty cards and empty chains are dropped.</summary>
        public static JObject Api()
        {
            lock (L)
            {
                if (_cache != null && (DateTime.UtcNow - _at).TotalSeconds < 60) return _cache;
                var cfg = Config(); int top = Math.Max(3, Math.Min(10, (int?)cfg["top"] ?? 8));
                var items = new JArray(); var seen = new Dictionary<string, JObject>();
                foreach (var it in cfg["sequence"] as JArray ?? new JArray())
                {
                    var chain = new JArray();
                    foreach (var t in it is JArray ? ((JArray)it).Cast<JToken>() : new[] { it })
                    {
                        string id = ((string)t["metric"] ?? "") + "|" + ((string)t["period"] ?? ""); JObject card;
                        if (!seen.TryGetValue(id, out card)) { card = Card(t, top); seen[id] = card; }
                        if (card != null) chain.Add(card);
                    }
                    if (chain.Count > 0) items.Add(chain);
                }
                _cache = new JObject { { "ok", true }, { "enabled", (bool?)cfg["enabled"] ?? true }, { "idleSeconds", Math.Max(3, (int?)cfg["idleSeconds"] ?? 20) }, { "secondsPerCard", Math.Max(3, (int?)cfg["secondsPerCard"] ?? 8) }, { "items", items } };
                _at = DateTime.UtcNow; return _cache;
            }
        }
    }
}
