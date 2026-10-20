using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The Host's own recording of ALL chat (every user, always, live or not, independent of ChattyPinguino): Data\chat_logs\live\YYYY-MM-DD.jsonl (UTC day), one
    /// {t (ms), u, i (user id), m, c (1 = a !command)} per line, the same shape as Chatty's own log.
    /// Some people opted out of the public log sites (rustlog), so the day files never have them. Data\chat_logs\hidden_sources.json lists them:
    /// {users:{login:{since:"YYYY-MM-DD" (first day the sites have nothing), note, offset}}}. For those logins the boards add the lines of this recording
    /// (from "since" on) at read time; the day files are never touched.</summary>
    public static class LiveLog
    {
        static readonly object L = new object();
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(d) : d; } }
        public static string LiveDir { get { return Path.Combine(Root, "chat_logs", "live"); } }
        static string HiddenP { get { return Path.Combine(Root, "chat_logs", "hidden_sources.json"); } }

        public static void Record(string user, string userId, string text, bool command)
        {
            try
            {
                if (string.IsNullOrEmpty(user) || text == null) return;
                long t = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                string line = new JObject { { "t", t }, { "u", user.ToLowerInvariant() }, { "i", userId ?? "" }, { "m", text.Length > 500 ? text.Substring(0, 500) : text }, { "c", command ? 1 : 0 } }.ToString(Newtonsoft.Json.Formatting.None) + "\n";
                lock (L) { Directory.CreateDirectory(LiveDir); File.AppendAllText(Path.Combine(LiveDir, DateTime.UtcNow.ToString("yyyy-MM-dd") + ".jsonl"), line, new UTF8Encoding(false)); }
            }
            catch (Exception ex) { Clog.Warn("livelog", "could not record chat: " + ex.Message); }
        }

        static JObject Hidden()
        {
            try
            {
                if (!File.Exists(HiddenP))
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(HiddenP));
                    var d = new JObject { { "note", "Logins the public chat-log sites will not serve (they opted out). Their messages are counted from Data\\chat_logs\\live from 'since' on. Day files are never edited." },
                        { "users", new JObject() } };
                    File.WriteAllText(HiddenP, d.ToString(), new UTF8Encoding(false)); return d;
                }
                return JObject.Parse(File.ReadAllText(HiddenP, Encoding.UTF8).TrimStart('﻿'));
            }
            catch (Exception ex) { Clog.Warn("livelog", "hidden_sources.json: " + ex.Message); return new JObject { { "users", new JObject() } }; }
        }

        public class Tally { public int Total; public SortedDictionary<string, int> PerMonth = new SortedDictionary<string, int>(); public long LastAt; public string LastText = ""; }

        /// <summary>login -> messages recorded for the opted-out users (lines newer than their "since" day, plus the sidecar offset).</summary>
        public static Dictionary<string, Tally> Overlay()
        {
            var res = new Dictionary<string, Tally>(); var hid = (Hidden()["users"] as JObject) ?? new JObject();
            if (hid.Count == 0) return res;
            var since = new Dictionary<string, long>();
            foreach (var p in hid.Properties())
            {
                DateTime dt; long cut = 0; if (DateTime.TryParse((string)p.Value["since"] ?? "", System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out dt)) cut = new DateTimeOffset(dt).ToUnixTimeMilliseconds();
                since[p.Name.ToLowerInvariant()] = cut; res[p.Name.ToLowerInvariant()] = new Tally { Total = (int?)p.Value["offset"] ?? 0 };
            }
            try
            {
                if (!Directory.Exists(LiveDir)) return res;
                foreach (var f in Directory.EnumerateFiles(LiveDir, "*.jsonl").OrderBy(x => x))
                    foreach (var line in File.ReadLines(f, Encoding.UTF8))
                    {
                        if (line.Length < 10 || line.IndexOf("\"u\"", StringComparison.Ordinal) < 0) continue;
                        try
                        {
                            var j = JObject.Parse(line.TrimStart('﻿')); string u = ((string)j["u"] ?? "").ToLowerInvariant(); Tally ta; if (!res.TryGetValue(u, out ta)) continue;
                            long t = (long?)j["t"] ?? 0; if (t < since[u]) continue;
                            ta.Total++; string mo = DateTimeOffset.FromUnixTimeMilliseconds(t).UtcDateTime.ToString("yyyy-MM"); int c; ta.PerMonth.TryGetValue(mo, out c); ta.PerMonth[mo] = c + 1;
                            if (t >= ta.LastAt) { ta.LastAt = t; ta.LastText = (string)j["m"] ?? ""; }
                        }
                        catch (Exception) { }
                    }
            }
            catch (Exception ex) { Clog.Warn("livelog", "overlay: " + ex.Message); }
            return res;
        }

        public class Extra { public int Total; public int NewDays; public SortedDictionary<string, int> PerMonth = new SortedDictionary<string, int>(); public string First = "", Last = ""; public int PeakCount; public string PeakDay = ""; public long ExtraSb, ExtraHost; }

        static string ChatRoot { get { return Path.Combine(Root, "chat_logs"); } }
        static Dictionary<string, Dictionary<string, int>> _siteCache; static string _siteSig = "";

        /// <summary>login -> UTC day -> messages in the public log site day files (Data\chat_logs\YYYY\MM\YYYY-MM-DD.txt), cached until a file changes.</summary>
        static Dictionary<string, Dictionary<string, int>> SiteDays()
        {
            var files = new List<FileInfo>();
            try { foreach (var y in Directory.EnumerateDirectories(ChatRoot)) { string yn = Path.GetFileName(y); if (yn.Length != 4 || !yn.All(char.IsDigit)) continue; foreach (var f in Directory.EnumerateFiles(y, "*.txt", SearchOption.AllDirectories)) files.Add(new FileInfo(f)); } } catch (Exception) { }
            string sig = files.Count + "|" + files.Sum(f => f.Length) + "|" + (files.Count == 0 ? 0 : files.Max(f => f.LastWriteTimeUtc.Ticks));
            if (_siteCache != null && sig == _siteSig) return _siteCache;
            var res = new Dictionary<string, Dictionary<string, int>>();
            foreach (var fi in files)
            {
                string fday = Path.GetFileNameWithoutExtension(fi.Name); if (fday.Length != 10) continue;
                try
                {
                    foreach (var line in File.ReadLines(fi.FullName, Encoding.UTF8))
                    {   // [2026-02-15 03:52:29] #channel user: text   (system lines are "* text")
                        int h = line.IndexOf("] #", StringComparison.Ordinal); if (h < 0) continue;
                        string day = line.Length > 11 && line[0] == '[' && line[11] == ' ' ? line.Substring(1, 10) : fday;
                        int sp = line.IndexOf(' ', h + 3); if (sp < 0) continue;
                        int co = line.IndexOf(':', sp + 1); if (co < 0) continue;
                        string u = line.Substring(sp + 1, co - sp - 1).Trim().ToLowerInvariant(); if (u.Length == 0 || u == "*" || u.IndexOf(' ') >= 0) continue;
                        Dictionary<string, int> d; if (!res.TryGetValue(u, out d)) res[u] = d = new Dictionary<string, int>();
                        int c; d.TryGetValue(day, out c); d[day] = c + 1;
                    }
                }
                catch (Exception) { }
            }
            _siteCache = res; _siteSig = sig; return res;
        }

        /// <summary>login (raw, not alias-folded) -> total and per-month message counts straight from the day files; the viewer profiles are built at one moment and can lag behind newer day files.</summary>
        public static Dictionary<string, KeyValuePair<int, Dictionary<string, int>>> SiteCounts()
        {
            var res = new Dictionary<string, KeyValuePair<int, Dictionary<string, int>>>();
            foreach (var kv in SiteDays()) { var pm = new Dictionary<string, int>(); int tot = 0; foreach (var d in kv.Value) { tot += d.Value; string mo = d.Key.Substring(0, 7); int c; pm.TryGetValue(mo, out c); pm[mo] = c + d.Value; } res[kv.Key] = new KeyValuePair<int, Dictionary<string, int>>(tot, pm); }
            return res;
        }

        /// <summary>Message counts that the public log sites lack. Per user (aliases folded onto the main login) and per UTC day the board count is
        /// max(public log sites, Streamer.bot debug-log sidecar, Host recording); this returns the part above the site count, so profiles/boards can add it.
        /// Inputs are read-only: Data\chat_logs\sidecar\streamerbot_daily_counts.json (counts only), Data\chat_logs\live\*.jsonl, the day files.</summary>
        public static Dictionary<string, Extra> Extras()
        {
            var res = new Dictionary<string, Extra>();
            try
            {
                Func<string, string> canon = l => Boards.CanonLogin(l);
                var site = new Dictionary<string, Dictionary<string, int>>(); var sbD = new Dictionary<string, Dictionary<string, int>>(); var hoD = new Dictionary<string, Dictionary<string, int>>();
                Action<Dictionary<string, Dictionary<string, int>>, string, string, int> add = (m, u, day, n) => { Dictionary<string, int> d; if (!m.TryGetValue(u, out d)) m[u] = d = new Dictionary<string, int>(); int c; d.TryGetValue(day, out c); d[day] = c + n; };
                foreach (var kv in SiteDays()) foreach (var dn in kv.Value) add(site, canon(kv.Key), dn.Key, dn.Value);
                string sbp = Path.Combine(ChatRoot, "sidecar", "streamerbot_daily_counts.json");
                if (File.Exists(sbp))
                {
                    var j = JObject.Parse(File.ReadAllText(sbp, Encoding.UTF8).TrimStart('﻿'));
                    if (j["counts"] is JObject cs) foreach (var up in cs.Properties()) if (up.Value is JObject dd) foreach (var dp in dd.Properties()) add(sbD, canon(up.Name.ToLowerInvariant()), dp.Name, (int?)dp.Value ?? 0);
                }
                if (Directory.Exists(LiveDir))
                    foreach (var f in Directory.EnumerateFiles(LiveDir, "*.jsonl"))
                        foreach (var line in File.ReadLines(f, Encoding.UTF8))
                        {
                            if (line.Length < 10 || line.IndexOf("\"u\"", StringComparison.Ordinal) < 0) continue;
                            try { var j = JObject.Parse(line.TrimStart('﻿')); string u = ((string)j["u"] ?? "").ToLowerInvariant(); if (u == "") continue; long t = (long?)j["t"] ?? 0; add(hoD, canon(u), DateTimeOffset.FromUnixTimeMilliseconds(t).UtcDateTime.ToString("yyyy-MM-dd"), 1); }
                            catch (Exception) { }
                        }
                var users = new HashSet<string>(sbD.Keys); users.UnionWith(hoD.Keys);
                foreach (var u in users)
                {
                    Dictionary<string, int> s, b, h; site.TryGetValue(u, out s); sbD.TryGetValue(u, out b); hoD.TryGetValue(u, out h);
                    var days = new HashSet<string>(); if (b != null) days.UnionWith(b.Keys); if (h != null) days.UnionWith(h.Keys);
                    Extra ex = null;
                    foreach (var day in days)
                    {
                        int sv = 0, bv = 0, hv = 0; if (s != null) s.TryGetValue(day, out sv); if (b != null) b.TryGetValue(day, out bv); if (h != null) h.TryGetValue(day, out hv);
                        int best = Math.Max(sv, Math.Max(bv, hv)); if (best <= sv) continue;
                        if (ex == null) ex = new Extra();
                        int more = best - sv; ex.Total += more; if (sv == 0) ex.NewDays++;
                        string mo = day.Substring(0, 7); int c; ex.PerMonth.TryGetValue(mo, out c); ex.PerMonth[mo] = c + more;
                        if (ex.First == "" || string.CompareOrdinal(day, ex.First) < 0) ex.First = day;
                        if (string.CompareOrdinal(day, ex.Last) > 0) ex.Last = day;
                        if (best > ex.PeakCount) { ex.PeakCount = best; ex.PeakDay = day; }
                        if (hv >= bv) ex.ExtraHost += more; else ex.ExtraSb += more;
                    }
                    if (ex != null) res[u] = ex;
                }
            }
            catch (Exception e) { Clog.Warn("livelog", "extras: " + e.Message); }
            return res;
        }

        /// <summary>Writes Data\chat_logs\sidecar\message_extra.json for Pipeline\push-profiles.mjs (profiles add these on top of the log-site counts).</summary>
        public static void WriteExtras(Dictionary<string, Extra> ex)
        {
            try
            {
                var u = new JObject(); foreach (var kv in ex.OrderBy(k => k.Key)) u[kv.Key] = new JObject { { "messages", kv.Value.Total }, { "newDays", kv.Value.NewDays }, { "first", kv.Value.First }, { "last", kv.Value.Last }, { "peakDay", kv.Value.PeakDay }, { "peakCount", kv.Value.PeakCount }, { "perMonth", JObject.FromObject(kv.Value.PerMonth) } };
                string dir = Path.Combine(ChatRoot, "sidecar"); Directory.CreateDirectory(dir);
                File.WriteAllText(Path.Combine(dir, "message_extra.json"), new JObject { { "rule", "per user per UTC day: max(public log sites, Streamer.bot sidecar, Host recording); this file holds the part above the log-site count, aliases folded onto the main login" }, { "at", DateTime.UtcNow.ToString("o") }, { "users", u } }.ToString(), new UTF8Encoding(false));
            }
            catch (Exception e) { Clog.Warn("livelog", "write extras: " + e.Message); }
        }

        /// <summary>GET /api/livelog: what the recording holds, the opted-out users and a rough "estimated missing" note (report only, never added to the boards).</summary>
        public static JObject Api()
        {
            int files = 0; long lines = 0; string first = ""; try { if (Directory.Exists(LiveDir)) { var fs = Directory.EnumerateFiles(LiveDir, "*.jsonl").OrderBy(x => x).ToList(); files = fs.Count; if (fs.Count > 0) first = Path.GetFileNameWithoutExtension(fs[0]); foreach (var f in fs) lines += File.ReadLines(f).Count(); } } catch (Exception) { }
            var users = new JObject(); var hid = (Hidden()["users"] as JObject) ?? new JObject(); var ov = Overlay();
            foreach (var p in hid.Properties())
            {
                Tally t; ov.TryGetValue(p.Name.ToLowerInvariant(), out t); t = t ?? new Tally();
                var u = new JObject { { "since", p.Value["since"] }, { "recorded", t.Total }, { "perMonth", JObject.FromObject(t.PerMonth) }, { "lastAt", t.LastAt } };
                if (t.PerMonth.Count > 0 && first != "")
                {   // days with chat between 'since' and the first recorded day x the average per recorded day
                    int recDays = t.PerMonth.Count > 0 ? Math.Max(1, Directory.EnumerateFiles(LiveDir, "*.jsonl").Count(f => File.ReadLines(f).Any(l => l.Contains("\"u\":\"" + p.Name.ToLowerInvariant() + "\"")))) : 1;
                    string root = Path.Combine(Root, "chat_logs"); int gap = 0; DateTime s0, f0;
                    if (DateTime.TryParse((string)p.Value["since"], out s0) && DateTime.TryParse(first, out f0)) for (var d = s0.AddDays(1); d < f0; d = d.AddDays(1)) { string fp = Path.Combine(root, d.ToString("yyyy"), d.ToString("MM"), d.ToString("yyyy-MM-dd") + ".txt"); if (File.Exists(fp) && new FileInfo(fp).Length > 20000) gap++; }
                    u["estimatedMissing"] = new JObject { { "note", "rough, report only, NOT on the boards" }, { "chatDaysInGap", gap }, { "avgPerRecordedDay", t.Total / recDays }, { "roughMessages", gap * (t.Total / recDays) } };
                }
                users[p.Name] = u;
            }
            return new JObject { { "ok", true }, { "liveDir", LiveDir }, { "files", files }, { "lines", lines }, { "firstDay", first }, { "hiddenUsers", users } };
        }

        /// <summary>Copies the hidden users' lines from Chatty's own recordings (Data\runtime\chat_logs\*.jsonl) that the live recording does not have yet. Returns the number copied.</summary>
        public static int BackfillFromChatty()
        {
            int added = 0;
            try
            {
                var hid = new HashSet<string>(((Hidden()["users"] as JObject) ?? new JObject()).Properties().Select(p => p.Name.ToLowerInvariant()));
                string src = Path.Combine(HostApi.DataDir, "chat_logs"); if (!Directory.Exists(src) || hid.Count == 0) return 0;
                var have = new HashSet<string>(); lock (L)
                {
                    Directory.CreateDirectory(LiveDir);
                    if (Directory.Exists(LiveDir)) foreach (var f in Directory.EnumerateFiles(LiveDir, "*.jsonl")) foreach (var l in File.ReadLines(f, Encoding.UTF8)) { try { var j = JObject.Parse(l.TrimStart('﻿')); have.Add(j["t"] + "|" + j["u"]); } catch (Exception) { } }
                    foreach (var f in Directory.EnumerateFiles(src, "*.jsonl"))
                        foreach (var l in File.ReadLines(f, Encoding.UTF8))
                        {
                            try
                            {
                                var j = JObject.Parse(l.TrimStart('﻿')); string u = ((string)j["u"] ?? "").ToLowerInvariant(); if (!hid.Contains(u)) continue;
                                string key = j["t"] + "|" + u; if (!have.Add(key)) continue;
                                long t = (long)j["t"]; string day = DateTimeOffset.FromUnixTimeMilliseconds(t).UtcDateTime.ToString("yyyy-MM-dd");
                                File.AppendAllText(Path.Combine(LiveDir, day + ".jsonl"), new JObject { { "t", t }, { "u", u }, { "i", j["i"] ?? "" }, { "m", j["m"] ?? "" }, { "c", j["c"] ?? 0 } }.ToString(Newtonsoft.Json.Formatting.None) + "\n", new UTF8Encoding(false)); added++;
                            }
                            catch (Exception) { }
                        }
                }
            }
            catch (Exception ex) { Clog.Warn("livelog", "backfill: " + ex.Message); }
            return added;
        }
    }
}
