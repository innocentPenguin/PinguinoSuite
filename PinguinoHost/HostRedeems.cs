using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Channel point redeem counters. Data\runtime\redeem_groups.json maps a group key (pushups, hydrate...) to reward ids (prefix match, 8+ chars) and title aliases, so a renamed or re-created reward
    /// still folds into one group (id first, normalised title second). Data\runtime\redeem_counts.json holds per group {title, baseline, baselineThrough, perMonth, live, livePerMonth, lastRedeemAt}
    /// (+ "estimated" notes that never enter a total). Total = baseline + live. Live counts one redemption id once and only when it happened AFTER baselineThrough (the seed's cut-off), so the history that is
    /// already inside the baseline is never added twice. Read with GET /api/redeems and the chat variable {redeem.&lt;group&gt;}. Seeded by Tools\seed-redeems.py.
    /// Per stream-day history (DayCounts, the Periods helper): "days" = the seeded reconstruction (YYYY-MM-DD -> n, inside the baseline), "liveDays" = redemptions counted by the Host; today / week / month answer from both,
    /// all-time = baseline + live. "recordStart" = first day the group's source has records (nothing is known before it); "estimatedDays" is a separate series that never enters a total or a period.
    /// Chat: !hydrate [today|week|month|all] (and !mimimimi, !hellothere ... = the group key without underscores; pushups are !pushup).</summary>
    public static class RedeemCounts
    {
        static readonly object L = new object(); static JObject _groups, _counts; static DateTime _groupsStamp, _countsStamp;
        static string GroupsP { get { return Path.Combine(HostApi.DataDir, "runtime", "redeem_groups.json"); } }
        static string CountsP { get { return Path.Combine(HostApi.DataDir, "runtime", "redeem_counts.json"); } }
        const int SeenMax = 400;

        static string S(Dictionary<string, object> a, string k) { object v; return a.TryGetValue(k, out v) && v != null ? Convert.ToString(v, CultureInfo.InvariantCulture) : ""; }
        public static string Norm(string t) { return string.Join(" ", (t ?? "").Trim().ToLowerInvariant().Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries)); }

        static JObject Read(string p) { try { if (File.Exists(p)) return JObject.Parse(File.ReadAllText(p, Encoding.UTF8)); } catch (Exception) { } return new JObject(); }
        static void Write(string p, JObject o) { Directory.CreateDirectory(Path.GetDirectoryName(p)); string tmp = p + ".tmp"; File.WriteAllText(tmp, o.ToString(Newtonsoft.Json.Formatting.Indented), new UTF8Encoding(false)); if (File.Exists(p)) File.Replace(tmp, p, null); else File.Move(tmp, p); }
        static JObject Groups()
        {
            if (_groups == null || (File.Exists(GroupsP) && File.GetLastWriteTimeUtc(GroupsP) != _groupsStamp)) { _groups = Read(GroupsP); try { _groupsStamp = File.GetLastWriteTimeUtc(GroupsP); } catch (Exception) { } }
            return _groups;
        }
        static DateTime Mt(string p) { try { return File.Exists(p) ? File.GetLastWriteTimeUtc(p) : DateTime.MinValue; } catch (Exception) { return DateTime.MinValue; } }
        /// <summary>the counts in memory; a file on disk that is NEWER than the last time this Host read or wrote it (a seed written while the Host runs) is read again, so the next Save never overwrites it</summary>
        static JObject Counts() { DateTime mt = Mt(CountsP); if (_counts == null || mt > _countsStamp) { _counts = Read(CountsP); _countsStamp = mt; } return _counts; }

        /// <summary>the group key a reward belongs to ("" when none): reward id first (prefix of 8+ characters), normalised title second</summary>
        public static string GroupOf(string rewardId, string title)
        {
            var g = Groups(); string t = Norm(title), id = (rewardId ?? "").Trim().ToLowerInvariant();
            if (id != "") foreach (var kv in g.Properties()) foreach (var x in (kv.Value["ids"] as JArray ?? new JArray())) { string s = ((string)x ?? "").Trim().ToLowerInvariant(); if (s.Length >= 8 && id.StartsWith(s)) return kv.Name; }
            if (t != "") foreach (var kv in g.Properties()) { if (Norm((string)kv.Value["title"]) == t) return kv.Name; foreach (var x in (kv.Value["aliases"] as JArray ?? new JArray())) if (Norm((string)x) == t) return kv.Name; }
            return "";
        }

        static DateTimeOffset AtOf(Dictionary<string, object> a)
        {
            DateTimeOffset d; string r = S(a, "redeemedAt");
            if (r != "" && DateTimeOffset.TryParse(r, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out d)) return d.ToUniversalTime();
            return DateTimeOffset.UtcNow;
        }
        static DateTimeOffset? Through(JToken t)
        {
            DateTimeOffset d; string s = (string)t; if (string.IsNullOrEmpty(s)) return null;
            return DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out d) ? d.ToUniversalTime() : (DateTimeOffset?)null;
        }

        /// <summary>called for every channel event (Program.DispatchEvent). Never throws.</summary>
        public static void Note(Dictionary<string, object> a)
        {
            try
            {
                if (S(a, "eventType") != "TwitchRedeem") return;
                if (S(a, "sim") != "" && Environment.GetEnvironmentVariable("PINGUINO_ACTIVITY_SIM") != "1") return;
                string title = S(a, "title"), user = S(a, "userName"), announce = null; var at = AtOf(a);
                string id = S(a, "redemptionId"); if (id == "") id = S(a, "eventId"); if (id == "") id = "t:" + user + ":" + Norm(title) + ":" + at.ToUnixTimeSeconds();
                lock (L)
                {
                    string key = GroupOf(S(a, "rewardId"), title); if (key == "") return;
                    var c = Counts(); var seen = c["seen"] as JArray; if (seen == null) { seen = new JArray(); c["seen"] = seen; }
                    if (seen.Any(x => (string)x == id)) return;          // EventSub redelivers: one count per redemption id
                    seen.Add(id); while (seen.Count > SeenMax) seen.RemoveAt(0);
                    var grp = c["groups"] as JObject; if (grp == null) { grp = new JObject(); c["groups"] = grp; }
                    var e = grp[key] as JObject;
                    if (e == null) { e = new JObject { { "title", (string)Groups()[key]["title"] ?? key }, { "baseline", 0 }, { "baselineThrough", at.AddSeconds(-1).ToString("o") }, { "perMonth", new JObject() }, { "live", 0 }, { "livePerMonth", new JObject() } }; grp[key] = e; }   // never seeded: counts from its first sight
                    var cut = Through(e["baselineThrough"]);
                    if (cut.HasValue && at <= cut.Value) { Save(c); return; }   // already inside the baseline
                    e["live"] = ((int?)e["live"] ?? 0) + 1; var ld = e["liveDays"] as JObject; if (ld == null) { ld = new JObject(); e["liveDays"] = ld; } DayCounts.Add(ld, DayCounts.DayOf(at.ToUnixTimeSeconds()), 1); if (key == "hydrate") announce = "Penguin has hydrated " + Total(e) + " times";
                    var lm = e["livePerMonth"] as JObject; if (lm == null) { lm = new JObject(); e["livePerMonth"] = lm; }
                    string mk = at.ToString("yyyy-MM", CultureInfo.InvariantCulture); lm[mk] = ((int?)lm[mk] ?? 0) + 1;
                    var prev = Through(e["lastRedeemAt"]); if (!prev.HasValue || at > prev.Value) e["lastRedeemAt"] = at.ToString("o");
                    Save(c);
                }
                if (announce != null) ChannelLore.SayCore(announce);   // one line per counted Hydrate redemption id (a repeated id returned above)
            }
            catch (Exception) { }
        }
        static void Save(JObject c) { try { Write(CountsP, c); _countsStamp = Mt(CountsP); } catch (Exception) { } }

        static int Total(JObject e) { return ((int?)e["baseline"] ?? 0) + ((int?)e["live"] ?? 0); }
        /// <summary>{redeem.pushups}: baseline + live ("0" for an unknown group)</summary>
        public static string Var(string key)
        {
            try { lock (L) { var g = Counts()["groups"] as JObject; var e = g == null ? null : g[(key ?? "").ToLowerInvariant()] as JObject; return e == null ? "0" : Total(e).ToString(CultureInfo.InvariantCulture); } }
            catch (Exception) { return "0"; }
        }

        /// <summary>every day of a group: seeded days + live days (an old seed with only perMonth has none)</summary>
        static JObject MergedDays(JObject e)
        {
            var m = new JObject(); foreach (var src in new[] { e["days"] as JObject, e["liveDays"] as JObject }) if (src != null) foreach (var p in src.Properties()) m[p.Name] = ((int?)m[p.Name] ?? 0) + ((int?)p.Value ?? 0);
            return m;
        }
        /// <summary>per-month totals: from the seeded days when the group has them, else the seeded perMonth; plus the live months</summary>
        static JObject PerMonthOf(JObject e)
        {
            var seeded = e["days"] as JObject; var pm = seeded != null && seeded.Count > 0 ? DayCounts.PerMonth(seeded) : new JObject();
            if (pm.Count == 0) foreach (var m in (e["perMonth"] as JObject ?? new JObject()).Properties()) pm[m.Name] = (int)m.Value;
            var live = DayCounts.PerMonth(e["liveDays"] as JObject);
            if (live.Count == 0) live = e["livePerMonth"] as JObject ?? new JObject();   // counted before liveDays existed
            foreach (var m in live.Properties()) pm[m.Name] = ((int?)pm[m.Name] ?? 0) + (int)m.Value;
            return new JObject(pm.Properties().OrderBy(q => q.Name, StringComparer.Ordinal));
        }
        /// <summary>today | week | month | all of one group</summary>
        public static int PeriodTotal(JObject e, string period, long ts)
        {
            if (period == "all") return Total(e);
            if (period == "month") return (int?)PerMonthOf(e)[Periods.MonthKey(ts)] ?? 0;
            return DayCounts.Sum(MergedDays(e), period, ts);
        }

        /// <summary>GET /api/redeems: {ok, groups:{key:{title, total, all(=total), today, week, month, baseline, baselineThrough, live, perMonth (baseline + live), days, recordStart, lastRedeemAt, estimated?, estimatedDays?}}}</summary>
        public static JObject Api()
        {
            lock (L)
            {
                var groups = new JObject(); var g = Counts()["groups"] as JObject ?? new JObject(); var defs = Groups();
                foreach (var kv in g.Properties())
                {
                    var e = (JObject)kv.Value;
                    var o = new JObject { { "title", (string)e["title"] ?? kv.Name }, { "total", Total(e) }, { "baseline", (int?)e["baseline"] ?? 0 }, { "baselineThrough", e["baselineThrough"] ?? JValue.CreateNull() }, { "live", (int?)e["live"] ?? 0 }, { "perMonth", PerMonthOf(e) }, { "lastRedeemAt", e["lastRedeemAt"] ?? JValue.CreateNull() } };
                    long ts = DayCounts.Now(); o["all"] = Total(e); o["today"] = PeriodTotal(e, "today", ts); o["week"] = PeriodTotal(e, "week", ts); o["month"] = PeriodTotal(e, "month", ts);
                    o["days"] = MergedDays(e); o["recordStart"] = e["recordStart"] ?? JValue.CreateNull();
                    if (e["estimated"] != null) o["estimated"] = e["estimated"].DeepClone();
                    if (e["estimatedDays"] != null) o["estimatedDays"] = e["estimatedDays"].DeepClone();
                    groups[kv.Name] = o;
                }
                foreach (var d in defs.Properties()) if (groups[d.Name] == null) groups[d.Name] = new JObject { { "title", (string)d.Value["title"] ?? d.Name }, { "total", 0 }, { "all", 0 }, { "today", 0 }, { "week", 0 }, { "month", 0 }, { "baseline", 0 }, { "baselineThrough", JValue.CreateNull() }, { "live", 0 }, { "perMonth", new JObject() }, { "days", new JObject() }, { "recordStart", JValue.CreateNull() }, { "lastRedeemAt", JValue.CreateNull() } };
                return new JObject { { "ok", true }, { "groups", groups } };
            }
        }

        /// <summary>the group whose chat command is cmd (the key without underscores: !hydrate, !hellothere), "" when none. Pushups are the Pushups counter's.</summary>
        public static string GroupOfCommand(string cmd)
        {
            string c = (cmd ?? "").TrimStart('!').ToLowerInvariant(); if (c == "" || c == "pushups") return "";
            lock (L) { foreach (var kv in Groups().Properties()) if (kv.Name.Replace("_", "") == c) return kv.Name; }
            return "";
        }
        static bool IsDayOrMonth(string a, out bool isDay)
        {
            DateTime d; isDay = DateTime.TryParseExact(a, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out d);
            return isDay || DateTime.TryParseExact(a, "yyyy-MM", CultureInfo.InvariantCulture, DateTimeStyles.None, out d);
        }
        /// <summary>the chat answer for a group command; args[0] may be today | week | month | all | YYYY-MM-DD | YYYY-MM. A period that lies before the group's recordStart answers "No record before Feb 2026."</summary>
        public static string Answer(string key, string[] args)
        {
            lock (L)
            {
                var g = Counts()["groups"] as JObject; var e = g == null ? null : g[key] as JObject; var def = Groups()[key];
                string title = (def == null ? null : (string)def["title"]) ?? key;
                if (e == null) e = new JObject { { "baseline", 0 }, { "live", 0 } };
                long ts = DayCounts.Now(); string rs = (string)e["recordStart"]; string a = args.Length > 0 ? args[0] : "", per = DayCounts.ParsePeriod(a);
                bool hy = key == "hydrate";
                Func<int, string, string> one = (n, label) => hy ? "Penguin has hydrated " + n + " times " + label : title + ": " + n + " " + label;
                string nr = string.IsNullOrEmpty(rs) ? null : "No record before " + DayCounts.MonthYear(rs) + ".";
                if (a != "" && per == "")
                {
                    bool isDay;
                    if (!IsDayOrMonth(a, out isDay)) return "Usage: !" + key.Replace("_", "") + " [today | week | month | all | YYYY-MM-DD]";
                    if (nr != null && string.CompareOrdinal(isDay ? a : a + "-31", rs) < 0) return nr;
                    int n = isDay ? (int?)MergedDays(e)[a] ?? 0 : (int?)PerMonthOf(e)[a] ?? 0;
                    return one(n, "on " + a);
                }
                if (per == "")
                {
                    int t = PeriodTotal(e, "today", ts), all = Total(e);
                    return hy ? "Penguin has hydrated " + t + " times today, " + all + " all-time" : title + ": " + t + " today, " + PeriodTotal(e, "week", ts) + " this week, " + PeriodTotal(e, "month", ts) + " this month, " + all + " all-time";
                }
                if (per != "all" && nr != null && string.CompareOrdinal(per == "month" ? Periods.MonthKey(ts) + "-31" : Periods.DayKey(ts), rs) < 0) return nr;
                return one(PeriodTotal(e, per, ts), per == "all" ? "all-time" : DayCounts.Label(per));
            }
        }

        /// <summary>sim/test hook: forget what is cached so a changed file on disk is read again</summary>
        public static void Reload() { lock (L) { _groups = null; _counts = null; _countsStamp = DateTime.MinValue; } }
    }
}
