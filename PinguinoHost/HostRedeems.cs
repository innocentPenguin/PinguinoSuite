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
    /// already inside the baseline is never added twice. Read with GET /api/redeems and the chat variable {redeem.&lt;group&gt;}. Seeded by Tools\seed-redeems.py.</summary>
    public static class RedeemCounts
    {
        static readonly object L = new object(); static JObject _groups, _counts; static DateTime _groupsStamp;
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
        static JObject Counts() { if (_counts == null) _counts = Read(CountsP); return _counts; }

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
                    e["live"] = ((int?)e["live"] ?? 0) + 1; if (key == "hydrate") announce = "Penguin has hydrated " + Total(e) + " times";
                    var lm = e["livePerMonth"] as JObject; if (lm == null) { lm = new JObject(); e["livePerMonth"] = lm; }
                    string mk = at.ToString("yyyy-MM", CultureInfo.InvariantCulture); lm[mk] = ((int?)lm[mk] ?? 0) + 1;
                    var prev = Through(e["lastRedeemAt"]); if (!prev.HasValue || at > prev.Value) e["lastRedeemAt"] = at.ToString("o");
                    Save(c);
                }
                if (announce != null) ChannelLore.SayCore(announce);   // one line per counted Hydrate redemption id (a repeated id returned above)
            }
            catch (Exception) { }
        }
        static void Save(JObject c) { try { Write(CountsP, c); } catch (Exception) { } }

        static int Total(JObject e) { return ((int?)e["baseline"] ?? 0) + ((int?)e["live"] ?? 0); }
        /// <summary>{redeem.pushups}: baseline + live ("0" for an unknown group)</summary>
        public static string Var(string key)
        {
            try { lock (L) { var g = Counts()["groups"] as JObject; var e = g == null ? null : g[(key ?? "").ToLowerInvariant()] as JObject; return e == null ? "0" : Total(e).ToString(CultureInfo.InvariantCulture); } }
            catch (Exception) { return "0"; }
        }

        /// <summary>GET /api/redeems: {ok, groups:{key:{title, total, baseline, baselineThrough, live, perMonth (baseline + live), lastRedeemAt, estimated?}}}</summary>
        public static JObject Api()
        {
            lock (L)
            {
                var groups = new JObject(); var g = Counts()["groups"] as JObject ?? new JObject(); var defs = Groups();
                foreach (var kv in g.Properties())
                {
                    var e = (JObject)kv.Value; var pm = new JObject();
                    foreach (var m in (e["perMonth"] as JObject ?? new JObject()).Properties()) pm[m.Name] = (int)m.Value;
                    foreach (var m in (e["livePerMonth"] as JObject ?? new JObject()).Properties()) pm[m.Name] = ((int?)pm[m.Name] ?? 0) + (int)m.Value;
                    var o = new JObject { { "title", (string)e["title"] ?? kv.Name }, { "total", Total(e) }, { "baseline", (int?)e["baseline"] ?? 0 }, { "baselineThrough", e["baselineThrough"] ?? JValue.CreateNull() }, { "live", (int?)e["live"] ?? 0 }, { "perMonth", new JObject(pm.Properties().OrderBy(p => p.Name, StringComparer.Ordinal)) }, { "lastRedeemAt", e["lastRedeemAt"] ?? JValue.CreateNull() } };
                    if (e["estimated"] != null) o["estimated"] = e["estimated"].DeepClone();
                    groups[kv.Name] = o;
                }
                foreach (var d in defs.Properties()) if (groups[d.Name] == null) groups[d.Name] = new JObject { { "title", (string)d.Value["title"] ?? d.Name }, { "total", 0 }, { "baseline", 0 }, { "baselineThrough", JValue.CreateNull() }, { "live", 0 }, { "perMonth", new JObject() }, { "lastRedeemAt", JValue.CreateNull() } };
                return new JObject { { "ok", true }, { "groups", groups } };
            }
        }

        /// <summary>sim/test hook: forget what is cached so a changed file on disk is read again</summary>
        public static void Reload() { lock (L) { _groups = null; _counts = null; } }
    }
}
