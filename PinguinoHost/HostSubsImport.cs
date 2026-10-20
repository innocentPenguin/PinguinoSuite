using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Twitch subscriber roster import. Ivan exports the roster from the Twitch dashboard (subscriber-list*.csv: Username, Subscribe Date, Current Tier, Tenure, Streak, Sub Type, Founder).
    /// One MASTER list (Data\subs\subscribers_master.json, keyed by lowercase login) is kept; every file merges into it and nothing is ever duplicated:
    /// per user the highest tier, the longest tenure and streak, the earliest subscribe date, founder if any row says so, the sub type of the newest row.
    /// Files are remembered by content hash (a re-import is a no-op). Someone missing from a NEWER export is marked lapsed (history stays), never deleted.
    /// The master is then written into the viewer profiles (Data\profiles\&lt;login&gt;.json, roles.sub / subTier / subMonths / subStreak / founder / subType / lapsed) so the site badges can use it.
    /// Watches C:\Users\&lt;you&gt;\Downloads (subscriber-list*.csv) and Data\subs\incoming. API: GET /api/subs, POST /api/subs/import.</summary>
    public static class SubsImport
    {
        static readonly object L = new object();
        static bool _started;
        static readonly Dictionary<string, string> Seen = new Dictionary<string, string>();   // path -> "size|mtime" already looked at (so a scan does not re-hash)

        // Data\runtime -> Data\subs and Data\profiles; any other data folder (tests) keeps them inside itself
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(d) : d; } }
        public static string SubsDir { get { return Path.Combine(Root, "subs"); } }
        static string ProfilesDir { get { return Path.Combine(Root, "profiles"); } }
        static string MasterP { get { return Path.Combine(SubsDir, "subscribers_master.json"); } }
        static string[] WatchDirs()
        {
            var l = new List<string> { Path.Combine(SubsDir, "incoming") };
            string dl = Environment.GetEnvironmentVariable("PINGUINO_SUBS_DOWNLOADS");
            if (dl == null) dl = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
            if (dl != "") l.Add(dl);
            return l.ToArray();
        }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () =>
            {
                await Task.Delay(12000);
                while (true)
                {
                    try { ScanAndImport(); } catch (Exception ex) { Clog.Warn("subs", "scan failed: " + ex.Message); }
                    await Task.Delay(60000);
                }
            });
        }

        // dates stay text: the default parser would turn "2026-10-20" into a DateTime and write it back in another format
        public static JObject ParseJ(string json)
        {
            using (var r = new Newtonsoft.Json.JsonTextReader(new StringReader(json)) { DateParseHandling = Newtonsoft.Json.DateParseHandling.None }) return JObject.Load(r);
        }

        static JObject LoadMaster()
        {
            try { if (File.Exists(MasterP)) { var m = ParseJ(File.ReadAllText(MasterP)); if (m["users"] == null) m["users"] = new JObject(); if (m["processed"] == null) m["processed"] = new JObject(); return m; } } catch (Exception ex) { Clog.Warn("subs", "master unreadable: " + ex.Message); }
            return new JObject { { "version", 1 }, { "lastExportAt", "" }, { "users", new JObject() }, { "processed", new JObject() } };
        }

        static List<string[]> ParseCsv(string text)
        {
            var rows = new List<string[]>(); var row = new List<string>(); var sb = new StringBuilder(); bool q = false, any = false;
            foreach (char ch in text.TrimStart('\uFEFF') + "\n")
            {
                if (q) { if (ch == '"') q = false; else sb.Append(ch); continue; }
                if (ch == '"') { q = true; any = true; }
                else if (ch == ',') { row.Add(sb.ToString()); sb.Clear(); any = true; }
                else if (ch == '\n' || ch == '\r')
                {
                    if (any || sb.Length > 0) { row.Add(sb.ToString()); rows.Add(row.ToArray()); }
                    row = new List<string>(); sb.Clear(); any = false;
                }
                else { sb.Append(ch); any = true; }
            }
            return rows;
        }

        static int TierNum(string s)
        {
            s = (s ?? "").ToLowerInvariant();
            if (s.Contains("3") || s.Contains("3000")) return 3;
            if (s.Contains("2") || s.Contains("2000")) return 2;
            return s.Contains("1") || s.Contains("prime") || s.Contains("1000") ? 1 : 0;
        }
        static int IntOf(string s) { int v; return int.TryParse((s ?? "").Trim(), out v) ? v : 0; }

        class Row { public string Login, Date, SubType; public int Tier, Tenure, Streak; public bool Founder; public DateTime When; }

        static List<Row> ReadRows(string text)
        {
            var rows = ParseCsv(text); var res = new List<Row>(); if (rows.Count == 0) return res;
            var head = rows[0].Select(h => h.Trim().ToLowerInvariant()).ToList();
            Func<string, int> ix = n => head.IndexOf(n);
            int iu = ix("username"), id = ix("subscribe date"), it = ix("current tier"), ite = ix("tenure"), isr = ix("streak"), ist = ix("sub type"), ifo = ix("founder");
            if (iu < 0) throw new InvalidDataException("not a subscriber list (no Username column)");
            Func<string[], int, string> g = (r, i) => i >= 0 && i < r.Length ? r[i].Trim() : "";
            foreach (var r in rows.Skip(1))
            {
                string u = g(r, iu).ToLowerInvariant().TrimStart('@'); if (u == "") continue;
                DateTime w; DateTime.TryParse(g(r, id), null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out w);
                res.Add(new Row { Login = u, Date = g(r, id), When = w, Tier = Math.Max(1, TierNum(g(r, it))), Tenure = IntOf(g(r, ite)), Streak = IntOf(g(r, isr)), SubType = g(r, ist).ToLowerInvariant(), Founder = g(r, ifo).ToLowerInvariant() == "true" });
            }
            return res;
        }

        /// <summary>merge one file's text into the master. exportAt = when the file was exported (its modified time). Returns a summary.</summary>
        static JObject Merge(JObject master, string text, string file, string hash, DateTime exportAt)
        {
            var rows = ReadRows(text); var users = (JObject)master["users"]; string now = DateTime.UtcNow.ToString("o");
            int added = 0, updated = 0, lapsed = 0;
            foreach (var grp in rows.GroupBy(r => r.Login))
            {
                var rs = grp.ToList(); var newest = rs.OrderByDescending(r => r.When).First();
                int tier = rs.Max(r => r.Tier), tenure = rs.Max(r => r.Tenure), streak = rs.Max(r => r.Streak);
                var firstDate = rs.Where(r => r.When > DateTime.MinValue).Select(r => r.When).DefaultIfEmpty(DateTime.MinValue).Min();
                bool founder = rs.Any(r => r.Founder);
                var u = users[grp.Key] as JObject;
                if (u == null) { u = new JObject { { "login", grp.Key }, { "tier", tier }, { "tenure", tenure }, { "streak", streak }, { "subscribed", firstDate == DateTime.MinValue ? "" : firstDate.ToString("yyyy-MM-ddTHH:mm:ssZ") }, { "founder", founder }, { "subType", newest.SubType }, { "lapsed", false }, { "firstImportedAt", now }, { "importedAt", now }, { "source", Path.GetFileName(file) } }; users[grp.Key] = u; added++; continue; }
                var before = u.ToString(Newtonsoft.Json.Formatting.None);
                u["tier"] = Math.Max((int?)u["tier"] ?? 0, tier); u["tenure"] = Math.Max((int?)u["tenure"] ?? 0, tenure); u["streak"] = Math.Max((int?)u["streak"] ?? 0, streak);
                string old = (string)u["subscribed"] ?? ""; string nw = firstDate == DateTime.MinValue ? "" : firstDate.ToString("yyyy-MM-ddTHH:mm:ssZ");
                if (nw != "" && (old == "" || string.CompareOrdinal(nw, old) < 0)) u["subscribed"] = nw;
                if (founder) u["founder"] = true; else if (u["founder"] == null) u["founder"] = false;
                bool newerFile = string.CompareOrdinal(exportAt.ToString("o"), (string)master["lastExportAt"] ?? "") >= 0;
                if (newerFile && newest.SubType != "") u["subType"] = newest.SubType;
                if (newerFile) u["lapsed"] = false;
                if (u.ToString(Newtonsoft.Json.Formatting.None) != before) { u["importedAt"] = now; u["source"] = Path.GetFileName(file); updated++; }
            }
            // a NEWER export is the current roster: whoever is not in it has lapsed (kept, flagged)
            if (string.CompareOrdinal(exportAt.ToString("o"), (string)master["lastExportAt"] ?? "") >= 0)
            {
                var present = new HashSet<string>(rows.Select(r => r.Login));
                foreach (var p in users.Properties()) if (!present.Contains(p.Name) && (bool?)p.Value["lapsed"] != true) { p.Value["lapsed"] = true; p.Value["lapsedAt"] = now; lapsed++; }
                master["lastExportAt"] = exportAt.ToString("o");
            }
            ((JObject)master["processed"])[hash] = new JObject { { "file", Path.GetFileName(file) }, { "rows", rows.Count }, { "exportAt", exportAt.ToString("o") }, { "importedAt", now } };
            return new JObject { { "file", Path.GetFileName(file) }, { "rows", rows.Count }, { "added", added }, { "updated", updated }, { "lapsed", lapsed } };
        }

        /// <summary>write the master into the profile files (only files that exist; a chatter without a profile is only in the master). Idempotent.</summary>
        public static int ApplyToProfiles(JObject master)
        {
            int changed = 0; if (!Directory.Exists(ProfilesDir)) return 0;
            foreach (var kv in ((JObject)master["users"]).Properties())
            {
                string f = Path.Combine(ProfilesDir, kv.Name + ".json"); if (!File.Exists(f)) continue;
                try
                {
                    var prof = ParseJ(File.ReadAllText(f)); var roles = prof["roles"] as JObject ?? new JObject(); var u = (JObject)kv.Value; bool lapsed = (bool?)u["lapsed"] == true;
                    var want = new JObject { { "sub", !lapsed }, { "subTier", (int?)u["tier"] ?? 1 }, { "subMonths", (int?)u["tenure"] ?? 0 }, { "subStreak", (int?)u["streak"] ?? 0 }, { "founder", (bool?)u["founder"] == true }, { "subType", (string)u["subType"] ?? "" }, { "lapsed", lapsed } };
                    bool diff = false; foreach (var p in want.Properties()) if (roles[p.Name] == null || !JToken.DeepEquals(roles[p.Name], p.Value)) { roles[p.Name] = p.Value; diff = true; }
                    if (diff) { prof["roles"] = roles; File.WriteAllText(f, prof.ToString()); changed++; }
                }
                catch (Exception ex) { Clog.Warn("subs", "profile " + kv.Name + ": " + ex.Message); }
            }
            return changed;
        }

        /// <summary>look for new subscriber-list*.csv files and merge them (oldest export first). Safe to call any time, from any thread.</summary>
        public static JObject ScanAndImport()
        {
            lock (L)
            {
                Directory.CreateDirectory(Path.Combine(SubsDir, "incoming")); Directory.CreateDirectory(Path.Combine(SubsDir, "files"));
                var master = LoadMaster(); var done = (JObject)master["processed"]; var results = new JArray(); bool dirty = false;
                var cands = new List<FileInfo>();
                foreach (var d in WatchDirs())
                {
                    try { if (Directory.Exists(d)) cands.AddRange(new DirectoryInfo(d).GetFiles("subscriber-list*.csv")); } catch (Exception) { }
                }
                foreach (var fi in cands.OrderBy(f => f.LastWriteTimeUtc))
                {
                    string sig = fi.Length + "|" + fi.LastWriteTimeUtc.Ticks; string have;
                    if (Seen.TryGetValue(fi.FullName, out have) && have == sig) continue;
                    try
                    {
                        byte[] bytes = File.ReadAllBytes(fi.FullName); string hash = BitConverter.ToString(SHA256.Create().ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
                        Seen[fi.FullName] = sig;
                        if (done[hash] != null) continue;                                     // same content already imported (the "(1)", "(2)" copies)
                        var r = Merge(master, Encoding.UTF8.GetString(bytes), fi.Name, hash, fi.LastWriteTimeUtc);
                        File.WriteAllBytes(Path.Combine(SubsDir, "files", hash.Substring(0, 10) + "-" + fi.Name), bytes);   // keep a copy next to the master
                        results.Add(r); dirty = true;
                        Clog.Info("subs", "imported " + fi.Name + ": " + r.ToString(Newtonsoft.Json.Formatting.None));
                    }
                    catch (Exception ex) { Seen.Remove(fi.FullName); results.Add(new JObject { { "file", fi.Name }, { "error", ex.Message } }); Clog.Warn("subs", fi.Name + ": " + ex.Message); }
                }
                int profiles = 0;
                if (dirty) { Directory.CreateDirectory(SubsDir); File.WriteAllText(MasterP, master.ToString()); }
                if (dirty || File.Exists(MasterP)) profiles = ApplyToProfiles(master);   // also catches profiles rebuilt since the last pass
                return new JObject { { "ok", true }, { "imported", results }, { "profilesUpdated", profiles }, { "users", ((JObject)master["users"]).Count } };
            }
        }

        public static JObject Api()
        {
            var m = LoadMaster(); var users = (JObject)m["users"];
            var active = users.Properties().Where(p => (bool?)p.Value["lapsed"] != true).ToList();
            return new JObject { { "ok", true }, { "lastExportAt", m["lastExportAt"] }, { "total", users.Count }, { "active", active.Count }, { "lapsed", users.Count - active.Count },
                { "tiers", new JObject { { "t1", active.Count(p => (int?)p.Value["tier"] == 1) }, { "t2", active.Count(p => (int?)p.Value["tier"] == 2) }, { "t3", active.Count(p => (int?)p.Value["tier"] == 3) } } },
                { "files", ((JObject)m["processed"]).Count }, { "watching", new JArray(WatchDirs()) }, { "users", users } };
        }
    }
}
