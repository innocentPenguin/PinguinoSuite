using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
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
                if (u == null) { u = new JObject { { "login", grp.Key }, { "tier", tier }, { "tenure", tenure }, { "streak", streak }, { "subscribed", firstDate == DateTime.MinValue ? "" : firstDate.ToString("yyyy-MM-ddTHH:mm:ssZ") }, { "founderCsv", founder }, { "founder", founder }, { "subType", newest.SubType }, { "lapsed", false }, { "firstImportedAt", now }, { "importedAt", now }, { "source", Path.GetFileName(file) } }; users[grp.Key] = u; added++; continue; }
                var before = u.ToString(Newtonsoft.Json.Formatting.None);
                u["tier"] = Math.Max((int?)u["tier"] ?? 0, tier); u["tenure"] = Math.Max((int?)u["tenure"] ?? 0, tenure); u["streak"] = Math.Max((int?)u["streak"] ?? 0, streak);
                string old = (string)u["subscribed"] ?? ""; string nw = firstDate == DateTime.MinValue ? "" : firstDate.ToString("yyyy-MM-ddTHH:mm:ssZ");
                if (nw != "" && (old == "" || string.CompareOrdinal(nw, old) < 0)) u["subscribed"] = nw;
                if (founder) u["founderCsv"] = true; else if (u["founderCsv"] == null) u["founderCsv"] = (bool?)u["founder"] == true;
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

        // ---- FOUNDERS: Twitch's "Founders Badge Holders" page is the authority (the CSV flags only some). Data/subs/founders.json = {founders:{login:{entitledOn}}}.
        // founder = in that list, or flagged by a CSV and not taken out of the list later. A CSV never clears it. A founders*.txt / founders*.json dropped in Data/subs/incoming REPLACES the list
        // (a name that is no longer in it stops being a founder). txt: one login per line, optional date after it.
        static string FoundersP { get { return Path.Combine(SubsDir, "founders.json"); } }
        static readonly string[][] SeedFounders = {
            new[] { "stinkyo1", "2026-03-13" }, new[] { "luhgeekski", "2026-03-13" }, new[] { "karebearr_", "2026-10-20" }, new[] { "yoohoo15", "2026-10-20" }, new[] { "wyatt104987", "2026-10-20" },
            new[] { "ash_wagawaga", "2026-10-20" }, new[] { "shinobisninja1", "2026-10-20" }, new[] { "syddneeyyyy", "2026-10-20" }, new[] { "cosmicryozen", "2026-10-20" }, new[] { "phil_flock", "2026-10-20" } };
        static JObject LoadFounders()
        {
            try { if (File.Exists(FoundersP)) { var f = ParseJ(File.ReadAllText(FoundersP)); if (f["founders"] == null) f["founders"] = new JObject(); if (f["processed"] == null) f["processed"] = new JObject(); return f; } } catch (Exception ex) { Clog.Warn("subs", "founders.json unreadable: " + ex.Message); }
            var d = new JObject(); foreach (var x in SeedFounders) d[x[0]] = new JObject { { "entitledOn", x[1] } };
            return new JObject { { "version", 1 }, { "updatedAt", DateTime.UtcNow.ToString("o") }, { "source", "seed (Twitch Founders Badge Holders page, Oct 20 2026)" }, { "founders", d }, { "processed", new JObject() } };
        }
        static JObject ParseFoundersFile(string text, string name)
        {
            var res = new JObject(); text = text.TrimStart('\uFEFF');
            if (name.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            {
                var t = JToken.Parse(text); if (t is JObject && ((JObject)t)["founders"] != null) t = ((JObject)t)["founders"];
                if (t is JArray) { foreach (var x in (JArray)t) { if (x.Type == JTokenType.String) res[((string)x).Trim().ToLowerInvariant()] = new JObject(); else if (x is JObject) { string lg = ((string)x["login"] ?? (string)x["username"] ?? "").Trim().ToLowerInvariant(); if (lg != "") res[lg] = new JObject { { "entitledOn", (string)x["entitledOn"] ?? "" } }; } } }
                else if (t is JObject) foreach (var p in ((JObject)t).Properties()) res[p.Name.ToLowerInvariant()] = new JObject { { "entitledOn", p.Value.Type == JTokenType.String ? (string)p.Value : (string)p.Value["entitledOn"] ?? "" } };
            }
            else foreach (var line in text.Split('\n'))
            {
                var m = Regex.Match(line.Trim(), @"^@?([A-Za-z0-9_]{2,25})\b[\s,;:(-]*(.*?)\)?$"); if (!m.Success) continue;
                if (line.TrimStart().StartsWith("#")) continue;
                res[m.Groups[1].Value.ToLowerInvariant()] = new JObject { { "entitledOn", m.Groups[2].Value.Trim() } };
            }
            return res;
        }
        static bool EffectiveFounder(string login, JObject u, JObject list)
        {
            if (list[login] != null) return true;
            return (bool?)u["founderCsv"] == true && (bool?)u["founderRemoved"] != true;
        }
        /// <summary>read the founders list (and any new founders file), then set master users' founder flag. returns true when the master changed.</summary>
        static bool RefreshFounders(JObject master)
        {
            bool changed = false; var f = LoadFounders(); var list = (JObject)f["founders"]; bool listChanged = !File.Exists(FoundersP);
            try
            {
                string inc = Path.Combine(SubsDir, "incoming");
                if (Directory.Exists(inc))
                    foreach (var fi in new DirectoryInfo(inc).GetFiles("founders*").Where(x => x.Extension.ToLowerInvariant() == ".txt" || x.Extension.ToLowerInvariant() == ".json").OrderBy(x => x.LastWriteTimeUtc))
                    {
                        string hash = BitConverter.ToString(SHA256.Create().ComputeHash(File.ReadAllBytes(fi.FullName))).Replace("-", "").ToLowerInvariant();
                        if (((JObject)f["processed"])[hash] != null) continue;
                        var nl = ParseFoundersFile(File.ReadAllText(fi.FullName, Encoding.UTF8), fi.Name);
                        if (nl.Count == 0) { Clog.Warn("subs", fi.Name + ": no founders found in it, ignored"); continue; }
                        foreach (var gone in list.Properties().Where(p => nl[p.Name] == null).Select(p => p.Name).ToList())   // taken out of the list = no longer a founder, whatever the CSV says
                        { var mu = ((JObject)master["users"])[gone] as JObject; if (mu != null) mu["founderRemoved"] = true; }
                        foreach (var p in nl.Properties()) { var mu = ((JObject)master["users"])[p.Name] as JObject; if (mu != null) mu["founderRemoved"] = false; }
                        list = nl; f["founders"] = list; f["source"] = fi.Name; f["updatedAt"] = DateTime.UtcNow.ToString("o"); ((JObject)f["processed"])[hash] = fi.Name; listChanged = true; changed = true;
                        Clog.Info("subs", "founders list replaced from " + fi.Name + " (" + list.Count + " founders)");
                    }
            }
            catch (Exception ex) { Clog.Warn("subs", "founders file: " + ex.Message); }
            foreach (var kv in ((JObject)master["users"]).Properties())
            {
                var u = (JObject)kv.Value; bool eff = EffectiveFounder(kv.Name, u, list);
                if ((bool?)u["founder"] != eff) { u["founder"] = eff; changed = true; }
                var fl = list[kv.Name] as JObject; string on = fl != null ? (string)fl["entitledOn"] ?? "" : ""; if (on != "" && (string)u["founderOn"] != on) { u["founderOn"] = on; changed = true; }
            }
            if (listChanged) { Directory.CreateDirectory(SubsDir); File.WriteAllText(FoundersP, f.ToString()); }
            _founders = list;
            return changed;
        }
        static JObject _founders = new JObject();

        /// <summary>roles.founder for founders that are not subscribers in the master (they have no other sub fields).</summary>
        static int ApplyFoundersToProfiles(JObject master)
        {
            int changed = 0; if (!Directory.Exists(ProfilesDir)) return 0;
            var users = (JObject)master["users"];
            foreach (var p in _founders.Properties().Where(p => users[p.Name] == null))
            {
                string f = Path.Combine(ProfilesDir, p.Name + ".json"); if (!File.Exists(f)) continue;
                try { var prof = ParseJ(File.ReadAllText(f)); var roles = prof["roles"] as JObject ?? new JObject(); if ((bool?)roles["founder"] == true) continue; roles["founder"] = true; prof["roles"] = roles; File.WriteAllText(f, prof.ToString()); changed++; }
                catch (Exception ex) { Clog.Warn("subs", "profile " + p.Name + ": " + ex.Message); }
            }
            return changed;
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
                if (RefreshFounders(master)) dirty = true;
                if (dirty) { Directory.CreateDirectory(SubsDir); File.WriteAllText(MasterP, master.ToString()); }
                profiles = ApplyToProfiles(master) + ApplyFoundersToProfiles(master);   // also catches profiles rebuilt since the last pass
                return new JObject { { "ok", true }, { "imported", results }, { "profilesUpdated", profiles }, { "users", ((JObject)master["users"]).Count } };
            }
        }

        /// <summary>the master record of a subscriber (tier, tenure, streak, founder, lapsed ...) or null; a founder who is no subscriber gets a record with founder:true only.</summary>
        public static JObject UserInfo(string login)
        {
            login = (login ?? "").ToLowerInvariant(); lock (L)
            {
                var u = (LoadMaster()["users"] as JObject)?[login] as JObject;
                if (u != null) return (JObject)u.DeepClone();
                if (LoadFounders()["founders"][login] != null) return new JObject { { "login", login }, { "tier", 0 }, { "tenure", 0 }, { "streak", 0 }, { "founder", true }, { "lapsed", true } };
                return null;
            }
        }
        /// <summary>the founders (login, display name), in the order of the list.</summary>
        public static List<KeyValuePair<string, string>> FoundersList()
        {
            lock (L) return ((JObject)LoadFounders()["founders"]).Properties().Select(p => new KeyValuePair<string, string>(p.Name, Boards.DisplayName(p.Name))).ToList();
        }

        public static JObject Api()
        {
            var m = LoadMaster(); var users = (JObject)m["users"];
            var active = users.Properties().Where(p => (bool?)p.Value["lapsed"] != true).ToList();
            return new JObject { { "ok", true }, { "lastExportAt", m["lastExportAt"] }, { "total", users.Count }, { "active", active.Count }, { "lapsed", users.Count - active.Count },
                { "tiers", new JObject { { "t1", active.Count(p => (int?)p.Value["tier"] == 1) }, { "t2", active.Count(p => (int?)p.Value["tier"] == 2) }, { "t3", active.Count(p => (int?)p.Value["tier"] == 3) } } },
                { "files", ((JObject)m["processed"]).Count }, { "watching", new JArray(WatchDirs()) }, { "founders", LoadFounders()["founders"] }, { "users", users } };
        }
    }
}
