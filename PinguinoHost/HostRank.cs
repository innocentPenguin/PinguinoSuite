using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>!rank [epicname] [1s|2s|3s|4s|hoops|rumble|dropshot|snowday|heatseeker|tournament] and mod !setrank: the channel owner's ranked playlists, from a small file (replaces RocketRankBot's !rank, same output shape:
    /// "Ranked 1v1: Champion I Div II (999) | Ranked 2v2: ... | Ranked 3v3: ..."). Data\runtime\rank.json {"1v1","2v2","3v3","peak","updated"}; seeded once from the
    /// last line RocketRankBot posted. The owner's ranks refresh themselves from the same unofficial tracker.gg profile endpoint the BVQ bot uses (every playlist in ONE call per Epic account, curl, cache 15 min per account, restart-proof,
    /// polite 2 s gap, 30 min pause when blocked, last known values as the fallback). A mod !setrank override wins for 24 h. Viewer lookups (linked accounts) come later.</summary>
    public static class Rank
    {
        static readonly object L = new object();
        static string FileP { get { return Path.Combine(HostApi.DataDir, "rank.json"); } }
        static readonly string[] Lists = { "1v1", "2v2", "3v3" };
        public static bool IsCommand(string cmd) { return cmd == "!rank" || cmd == "!setrank"; }
        public static bool IsModCommand(string cmd) { return cmd == "!setrank"; }

        const int CacheSec = 900, ManualHours = 24, RetryGapSec = 60, ChatWaitMs = 3000;   // ONE tracker call per Epic account per 15 min; that call reads every playlist, !rank only shows the one asked for
        
        static readonly string[] AllLists = { "1v1", "2v2", "3v3", "4v4", "hoops", "rumble", "dropshot", "snowday", "heatseeker", "tournament" };
        // ids 10 11 13 27 28 29 30 34 checked against the Psyonix playlist table (rlapi PopulationPlaylist: Ranked Duel/Doubles/Standard/Hoops/Rumble/Dropshot/Snow Day, Official Tournament); 61 (Quads) and 63 (Heatseeker) are not in any public table, so the name match is what carries them
        static readonly int[] PlaylistIds = { 10, 11, 13, 61, 27, 28, 29, 30, 63, 34 };
        static readonly string[] Names = { "Ranked Duel 1v1", "Ranked Doubles 2v2", "Ranked Standard 3v3", "Ranked Quads 4v4", "Hoops", "Rumble", "Dropshot", "Snowday", "Heatseeker", "Tournament Matches" };
        static readonly Dictionary<string, JObject> _cache = new Dictionary<string, JObject>(); static bool _cacheLoaded;
        static string CacheP { get { return Path.Combine(HostApi.DataDir, "rank_cache.json"); } }

        static string Label(string k) { return char.IsDigit(k[0]) ? "Ranked " + k : char.ToUpperInvariant(k[0]) + k.Substring(1); }

        /// <summary>playlist names compare without case, spaces and a leading "Ranked", so "Ranked Hoops" = "Hoops", "Ranked 4v4 Quads" = "Quads 4v4"; these are the same playlist</summary>
        static string NameKey(string n) { var w = System.Text.RegularExpressions.Regex.Matches((n ?? "").ToLowerInvariant(), "[a-z0-9]+").Cast<System.Text.RegularExpressions.Match>().Select(m => m.Value).Where(x => x != "ranked").OrderBy(x => x, StringComparer.Ordinal); return string.Concat(w); }   // word order does not matter: "Ranked Quads 4v4" = "Ranked 4v4 Quads"
        static string FlatKey(string n) { return string.Concat(System.Text.RegularExpressions.Regex.Matches((n ?? "").ToLowerInvariant(), "[a-z0-9]+").Cast<System.Text.RegularExpressions.Match>().Select(m => m.Value).Where(x => x != "ranked")); }   // "Snow Day" = "Snowday"
        static bool SameName(string a, string b) { return NameKey(a) != "" && (NameKey(a) == NameKey(b) || FlatKey(a) == FlatKey(b)); }

        /// <summary>fills every playlist it finds ("1v1".."tournament") with "Champion I Div II (999)" from a tracker.gg profile JSON; returns how many were read. Playlists match by id first, then by name.</summary>
        public static int ParseProfile(string body, JObject into)
        {
            int n = 0; var segs = JObject.Parse(body)["data"]?["segments"] as JArray; if (segs == null) return 0;
            for (int i = 0; i < AllLists.Length; i++)
            {
                var seg = segs.OfType<JObject>().FirstOrDefault(x => (string)x["type"] == "playlist" && ((int?)x["attributes"]?["playlistId"] == PlaylistIds[i] || SameName((string)x["metadata"]?["name"], Names[i]))); if (seg == null) continue;
                string tier = (string)seg["stats"]?["tier"]?["metadata"]?["name"] ?? ""; string div = ((string)seg["stats"]?["division"]?["metadata"]?["name"] ?? "").Replace("Division", "Div");
                double r; bool has = double.TryParse((string)seg["stats"]?["rating"]?["value"], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out r);
                if (tier == "" && !has) continue;
                into[AllLists[i]] = (tier + (div != "" ? " " + div : "") + (has ? " (" + (int)Math.Round(r) + ")" : "")).Trim(); n++;
            }
            return n;
        }

        static void LoadCache()
        {
            if (_cacheLoaded) return; _cacheLoaded = true;
            try { if (File.Exists(CacheP)) foreach (var p in JObject.Parse(File.ReadAllText(CacheP, Encoding.UTF8).TrimStart((char)0xFEFF)).Properties()) if (p.Value is JObject) _cache[p.Name] = (JObject)p.Value; } catch (Exception) { }
        }
        static void SaveCache()
        {
            try
            {
                if (_cache.Count > 400) foreach (var k in _cache.OrderBy(x => (long?)x.Value["at"] ?? 0).Take(_cache.Count - 300).Select(x => x.Key).ToList()) _cache.Remove(k);
                var o = new JObject(); foreach (var kv in _cache) o[kv.Key] = kv.Value; File.WriteAllText(CacheP, o.ToString(), new UTF8Encoding(false));
            }
            catch (Exception) { }
        }

        // ================= source chain: several sources tried in turn, each with its own backoff =================
        sealed class Src { public string Name; public bool Tracker; public string Format = "tracker"; public Func<string, string, string> Get; }
        sealed class SrcHealth { public int Fails, Oks, LastMs; public long BackoffUntil, LastOk, LastTry; public string LastStatus = "never tried"; }
        static readonly Dictionary<string, SrcHealth> _health = new Dictionary<string, SrcHealth>();
        static string _lastGood = "";
        static readonly Dictionary<string, System.Threading.Tasks.Task> _inflight = new Dictionary<string, System.Threading.Tasks.Task>();
        /// <summary>test hook: (source name, platform, name) -> raw body, or null = that source failed. When set, no real network is touched.</summary>
        public static Func<string, string, string, string> TestFetch;
        public static void TestAge(string key, long sec) { lock (L) { LoadCache(); JObject c; if (_cache.TryGetValue(key, out c)) { c["at"] = Now() - sec; c.Remove("retryAt"); } } }
        public static void TestReset() { lock (L) { _cache.Clear(); _health.Clear(); _lastGood = ""; } }
        public static void TestClearBackoff() { lock (L) { foreach (var h in _health.Values) { h.BackoffUntil = 0; h.Fails = 0; } foreach (var c in _cache.Values) c.Remove("retryAt"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        /// <summary>old test hooks: PINGUINO_RANK_FIXTURE (a profile JSON, or file.<name>.json per account) and PINGUINO_RANK_CALLLOG (one line per account looked up)</summary>
        static string EnvFixture(string epic)
        {
            string log = Environment.GetEnvironmentVariable("PINGUINO_RANK_CALLLOG"); if (!string.IsNullOrEmpty(log)) { try { File.AppendAllText(log, epic + "\n"); } catch (Exception) { } }
            string fx = Environment.GetEnvironmentVariable("PINGUINO_RANK_FIXTURE"); if (string.IsNullOrEmpty(fx)) return null;
            string f2 = fx.Replace(".json", "." + epic + ".json"); if (File.Exists(f2)) return File.ReadAllText(f2); return File.Exists(fx) ? File.ReadAllText(fx) : null;
        }
        static string TrackerPlat(string p) { return p == "xbox" ? "xbl" : p == "ps" || p == "playstation" ? "psn" : p; }

        static string Curl(string url, int maxSec, params string[] headers)
        {
            var psi = new System.Diagnostics.ProcessStartInfo { FileName = "curl", RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true };
            foreach (var a in new[] { "-s", "-L", "--compressed", "--max-time", maxSec.ToString() }) psi.ArgumentList.Add(a);
            foreach (var h in headers) { psi.ArgumentList.Add("-H"); psi.ArgumentList.Add(h); }
            psi.ArgumentList.Add(url);
            using (var pr = System.Diagnostics.Process.Start(psi))
            {
                var err = pr.StandardError.ReadToEndAsync(); string o = pr.StandardOutput.ReadToEnd();
                if (!pr.WaitForExit((maxSec + 3) * 1000)) { try { pr.Kill(); } catch (Exception) { } return null; }
                return pr.ExitCode == 0 ? o : null;
            }
        }

        const string BrowserUa = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
        static string TrackerUrl(string plat, string name) { return "https://api.tracker.gg/api/v2/rocket-league/standard/profile/" + TrackerPlat(plat) + "/" + Uri.EscapeDataString(name); }

        /// <summary>headless Edge (already on the PC) loads the profile JSON like a browser would; slow, so it is the last resort</summary>
        static string EdgeFetch(string plat, string name)
        {
            string exe = new[] { @"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", @"C:\Program Files\Microsoft\Edge\Application\msedge.exe" }.FirstOrDefault(File.Exists); if (exe == null) return null;
            string prof = Path.Combine(Path.GetTempPath(), "pgh_rank_edge");
            var psi = new System.Diagnostics.ProcessStartInfo { FileName = exe, RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true };
            foreach (var a in new[] { "--headless=new", "--disable-gpu", "--user-data-dir=" + prof, "--virtual-time-budget=12000", "--dump-dom", TrackerUrl(plat, name) }) psi.ArgumentList.Add(a);
            using (var pr = System.Diagnostics.Process.Start(psi))
            {
                var err = pr.StandardError.ReadToEndAsync(); string o = pr.StandardOutput.ReadToEnd();
                if (!pr.WaitForExit(25000)) { try { pr.Kill(true); } catch (Exception) { } return null; }
                var m = Regex.Match(o ?? "", @"<pre[^>]*>(.*?)</pre>", RegexOptions.Singleline); string j = m.Success ? System.Net.WebUtility.HtmlDecode(m.Groups[1].Value) : o;
                return j != null && j.TrimStart().StartsWith("{") ? j : null;
            }
        }

        /// <summary>Data\rank_sources.json (optional): [{"name":"mysource","url":"https://host/{platform}/{name}","headers":{"Authorization":"Bearer ..."},"format":"tracker|flat"}] - any public JSON endpoint, tried BEFORE tracker.gg</summary>
        static List<Src> CustomSources()
        {
            var l = new List<Src>();
            try
            {
                string f = Path.Combine(HostApi.DataDir, "rank_sources.json"); if (!File.Exists(f)) return l;
                foreach (var o in JArray.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)).OfType<JObject>())
                {
                    string nm = (string)o["name"], url = (string)o["url"]; if (string.IsNullOrEmpty(nm) || string.IsNullOrEmpty(url)) continue;
                    var hs = (o["headers"] as JObject)?.Properties().Select(p => p.Name + ": " + p.Value).ToArray() ?? new string[0];
                    l.Add(new Src { Name = nm, Format = ((string)o["format"] ?? "tracker").ToLowerInvariant(), Get = (pl, n) => Curl(url.Replace("{platform}", Uri.EscapeDataString(pl)).Replace("{name}", Uri.EscapeDataString(n)), 6, hs.Concat(new[] { "User-Agent: " + BrowserUa, "Accept: application/json" }).ToArray()) });
                }
            }
            catch (Exception ex) { Clog.Warn("rank", "rank_sources.json: " + ex.Message); }
            return l;
        }

        static List<Src> BuiltIn()
        {
            return new List<Src> {
                new Src { Name = "tracker-api", Tracker = true, Get = (pl, n) => Curl(TrackerUrl(pl, n), 6, "User-Agent: " + BrowserUa, "Accept: application/json, text/plain, */*", "Accept-Language: en-US,en;q=0.9", "Origin: https://rocketleague.tracker.network", "Referer: https://rocketleague.tracker.network/") },
                new Src { Name = "tracker-api-alt", Tracker = true, Get = (pl, n) => Curl(TrackerUrl(pl, n) + "?forceCollect=false", 6, "User-Agent: " + BrowserUa, "Accept: */*", "Accept-Language: en,en-US;q=0.9", "sec-fetch-site: same-site", "sec-fetch-mode: cors", "sec-fetch-dest: empty", "Referer: https://rocketleague.tracker.network/") },
                new Src { Name = "edge", Tracker = true, Get = EdgeFetch } };
        }

        /// <summary>custom (non-tracker) sources first, tracker.gg last; inside each group the source that answered last time goes first; sources in backoff are skipped</summary>
        static List<Src> Order(out int skipped)
        {
            var all = CustomSources().Concat(BuiltIn()).ToList(); long now = Now(); skipped = 0;
            lock (L) { foreach (var s in all) if (!_health.ContainsKey(s.Name)) _health[s.Name] = new SrcHealth(); }
            Func<Src, int> rank = s => (s.Tracker ? 10 : 0) + (s.Name == _lastGood ? 0 : 1);
            var ord = all.OrderBy(rank).ToList(); var ready = new List<Src>();
            lock (L) foreach (var s in ord) { if (_health[s.Name].BackoffUntil > now) skipped++; else ready.Add(s); }
            return ready;
        }

        /// <summary>one body -> ranks (n playlists) | notfound | fail</summary>
        static string Interpret(Src s, string body, JObject got)
        {
            if (string.IsNullOrWhiteSpace(body)) return "empty";
            if (body.Contains("CollectorResultStatus::NotFound")) return "notfound";
            if (!body.TrimStart().StartsWith("{")) return "blocked";
            int n = 0;
            try
            {
                if (s.Format == "flat") { var jo = JObject.Parse(body); foreach (var k in AllLists) if (!string.IsNullOrWhiteSpace((string)jo[k])) { got[k] = Clean((string)jo[k]); n++; } }
                else n = ParseProfile(body, got);
            }
            catch (Exception) { return "unreadable"; }
            return n > 0 ? "ok" : "no ranks";
        }

        static void Mark(Src s, string status, long ms)
        {
            lock (L)
            {
                var h = _health[s.Name]; long now = Now(); h.LastTry = now; h.LastStatus = status; h.LastMs = (int)ms;
                if (status == "ok" || status == "notfound") { h.Fails = 0; h.BackoffUntil = 0; h.LastOk = now; h.Oks++; }
                else { h.Fails++; h.BackoffUntil = now + Math.Min(60, 1 << Math.Min(h.Fails, 6)) * 60; }   // 2, 4, 8 ... 60 min, per source
            }
        }

        /// <summary>asks the sources in turn until one answers; fills c (cache entry) and returns "ok" | "notfound" | "failed"</summary>
        static string Refresh(string key, string plat, string name, JObject c)
        {
            int skipped; var srcs = Order(out skipped); string result = "failed";
            foreach (var s in srcs)
            {
                var sw = System.Diagnostics.Stopwatch.StartNew(); string body = null;
                try { body = TestFetch != null ? TestFetch(s.Name, plat, name) : EnvFixture(name) ?? (Environment.GetEnvironmentVariable("PINGUINO_RANK_FIXTURE") != null ? null : s.Get(plat, name)); } catch (Exception ex) { Clog.Warn("rank", s.Name + ": " + ex.Message); }
                var got = new JObject(); string st = Interpret(s, body, got); Mark(s, st, sw.ElapsedMilliseconds);
                if (st == "ok")
                {
                    lock (L)
                    {
                        _lastGood = s.Name; c["ranks"] = got; c["at"] = Now(); c["status"] = "ok"; c["source"] = s.Name; c.Remove("retryAt");
                        try { string nm = (string)JObject.Parse(body)["data"]?["platformInfo"]?["platformUserHandle"]; if (!string.IsNullOrEmpty(nm)) c["name"] = Clean(nm); } catch (Exception) { }
                        SaveCache();
                    }
                    Clog.Info("rank", key + " answered by " + s.Name + " (" + sw.ElapsedMilliseconds + " ms)");
                    try { if (plat == "epic") PublishProfiles(name.ToLowerInvariant(), got); } catch (Exception ex) { Clog.Warn("rank", "profile ranks not saved: " + ex.Message); }
                    return "ok";
                }
                if (st == "notfound") { lock (L) { c["status"] = "notfound"; c["at"] = Now(); SaveCache(); } return "notfound"; }
                Clog.Warn("rank", key + ": " + s.Name + " -> " + st);
            }
            lock (L) { c["retryAt"] = Now() + RetryGapSec; SaveCache(); }   // all failed: do not hammer; the old values stay
            if (srcs.Count == 0) Clog.Warn("rank", key + ": every source is in backoff, served from cache");
            return result;
        }

        /// <summary>cached answer first; a stale or missing one is refreshed in the background and the chat waits at most waitMs for it. status: ok | cached | stale | notfound | pending | none</summary>
        static JObject Lookup(string plat, string name, int waitMs, out string status, out long ageSec)
        {
            string key = plat + ":" + name.ToLowerInvariant(); long now = Now(); JObject c; System.Threading.Tasks.Task t = null;
            lock (L)
            {
                LoadCache(); if (!_cache.TryGetValue(key, out c)) { c = new JObject(); _cache[key] = c; }
                long at = (long?)c["at"] ?? 0; bool has = (c["ranks"] as JObject)?.HasValues == true; string cs = (string)c["status"] ?? "";
                if (at > 0 && now - at < CacheSec && (has || cs == "notfound")) { status = cs == "notfound" ? "notfound" : "cached"; ageSec = now - at; return c["ranks"] as JObject; }
                if (now >= ((long?)c["retryAt"] ?? 0))
                {
                    if (!_inflight.TryGetValue(key, out t) || t.IsCompleted) { var cc = c; t = System.Threading.Tasks.Task.Run(() => { try { return Refresh(key, plat, name, cc); } catch (Exception ex) { Clog.Warn("rank", "refresh: " + ex.Message); return "failed"; } finally { lock (L) _inflight.Remove(key); } }); _inflight[key] = t; }
                }
            }
            bool done = t != null && waitMs > 0 && t.Wait(waitMs);
            lock (L)
            {
                long at = (long?)c["at"] ?? 0; var r = c["ranks"] as JObject; bool has = r != null && r.HasValues; string cs = (string)c["status"] ?? "";
                ageSec = at > 0 ? Now() - at : -1;
                if (done && cs == "notfound" && Now() - at < 30) status = "notfound";
                else if (done && has && Now() - at < 30) status = "ok";
                else if (has) status = "stale";
                else if (cs == "notfound") status = "notfound";
                else status = t != null && !t.IsCompleted ? "pending" : "none";
                return r;
            }
        }

        static string Ago(long sec)
        {
            if (sec < 3600) return Math.Max(1, sec / 60) + " min ago"; if (sec < 172800) return sec / 3600 + "h ago"; return sec / 86400 + " days ago";
        }

        /// <summary>status of every source for the System page: last result, failures in a row, when it may be tried again</summary>
        public static JObject HealthJson()
        {
            var o = new JObject(); long now = Now();
            lock (L)
            {
                foreach (var s in CustomSources().Concat(BuiltIn()))
                {
                    SrcHealth h; if (!_health.TryGetValue(s.Name, out h)) h = new SrcHealth();
                    o[s.Name] = new JObject { { "tracker", s.Tracker }, { "lastStatus", h.LastStatus }, { "ok", h.Oks }, { "failsInARow", h.Fails }, { "lastMs", h.LastMs }, { "lastOkAgoSec", h.LastOk == 0 ? (long?)null : now - h.LastOk }, { "retryInSec", Math.Max(0, h.BackoffUntil - now) } };
                }
            }
            return new JObject { { "lastGoodSource", _lastGood }, { "sources", o }, { "cached", _cache.Count } };
        }

        // ================= who is being asked about =================
        static string NormName(string s) { return Regex.Replace((s ?? "").ToLowerInvariant(), "[^a-z0-9]", ""); }
        static int Lev(string a, string b)
        {
            var d = new int[a.Length + 1, b.Length + 1]; for (int i = 0; i <= a.Length; i++) d[i, 0] = i; for (int j = 0; j <= b.Length; j++) d[0, j] = j;
            for (int i = 1; i <= a.Length; i++) for (int j = 1; j <= b.Length; j++) d[i, j] = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1));
            return d[a.Length, b.Length];
        }
        static string NamesP { get { return Path.Combine(HostApi.DataDir, "rank_names.json"); } }
        static string[] Platforms = { "epic", "steam", "xbox", "xbl", "psn", "ps", "playstation", "switch" };

        /// <summary>"steam:Name" / "epic:Name" -> (platform, name); no prefix -> platform ""</summary>
        public static void SplitPlatform(string raw, out string plat, out string name)
        {
            plat = ""; name = raw ?? ""; int i = name.IndexOf(':');
            if (i > 0 && Platforms.Contains(name.Substring(0, i).ToLowerInvariant())) { plat = name.Substring(0, i).ToLowerInvariant(); if (plat == "xbl") plat = "xbox"; name = name.Substring(i + 1); }
        }

        /// <summary>twitch login or typed name -> (platform, name): prefix, learned map, linked account, fuzzy match against known chatters, else the text itself as an Epic name</summary>
        static void Resolve(string who, out string plat, out string name, out string how)
        {
            SplitPlatform(who, out plat, out name); how = "typed";
            if (plat != "") return;
            string lg = name.ToLowerInvariant().TrimStart('@'); plat = "epic"; name = lg;
            try { if (File.Exists(NamesP)) { var m = JObject.Parse(File.ReadAllText(NamesP, Encoding.UTF8).TrimStart((char)0xFEFF)); var e = m[lg] as JObject; if (e != null) { plat = (string)e["platform"] ?? "epic"; name = (string)e["name"] ?? lg; how = "learned"; return; } } } catch (Exception) { }
            string linked = EpicOfLogin(lg); if (linked != "") { name = linked.ToLowerInvariant(); how = "linked"; return; }
            try
            {
                var pj = JObject.Parse(File.ReadAllText(Path.Combine(HostApi.DataDir, "players.json"), Encoding.UTF8).TrimStart((char)0xFEFF)); string nk = NormName(lg); JObject best = null; int bestD = 99; int ties = 0;
                foreach (var p in pj.Properties())
                {
                    var o = p.Value as JObject; if (o == null || string.IsNullOrWhiteSpace((string)o["GameId"])) continue;
                    foreach (var cand in new[] { NormName((string)o["Username"] ?? p.Name), NormName((string)o["GameId"]) })
                    {
                        if (cand == "") continue; int dd = cand == nk ? 0 : (nk.Length >= 5 && cand.Length >= 5 ? Lev(nk, cand) : 99);
                        if (dd <= 1 && dd < bestD) { best = o; bestD = dd; ties = 1; } else if (dd <= 1 && dd == bestD && best != o) ties++;
                    }
                }
                if (best != null && ties == 1) { string pf = ((string)best["Platform"] ?? "epic").ToLowerInvariant(); plat = Platforms.Contains(pf) ? pf : "epic"; name = ((string)best["GameId"]).Trim().ToLowerInvariant(); how = "fuzzy"; }
            }
            catch (Exception) { }
        }

        static void Learn(string login, string plat, string name)
        {
            try
            {
                lock (L)
                {
                    JObject m = File.Exists(NamesP) ? JObject.Parse(File.ReadAllText(NamesP, Encoding.UTF8).TrimStart((char)0xFEFF)) : new JObject();
                    if (m.Count > 2000) return; m[login] = new JObject { { "platform", plat }, { "name", name } };
                    File.WriteAllText(NamesP, m.ToString(), new UTF8Encoding(false));
                }
            }
            catch (Exception) { }
        }

        static readonly Dictionary<string, long> _said = new Dictionary<string, long>();
        static void SayOnce(Action<string> say, string text)
        {   // the "checking" / "no data" lines never repeat within 30 s (duplicate guard)
            long now = Now(); lock (L) { long t; if (_said.TryGetValue(text, out t) && now - t < 30) return; _said[text] = now; }
            say(text);
        }

        static string DataRoot { get { string d = HostApi.DataDir.TrimEnd((char)92, '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d; } }
        static string RanksP { get { return Path.Combine(DataRoot, "ranks", "rl_ranks.json"); } }

        /// <summary>twitch login -> Epic name for people who linked an account in matchmaking (Core's players.json: Platform epic + GameId)</summary>
        static string EpicOfLogin(string login)
        {
            try
            {
                var pj = JObject.Parse(File.ReadAllText(Path.Combine(HostApi.DataDir, "players.json"), Encoding.UTF8).TrimStart((char)0xFEFF));
                foreach (var p in pj.Properties()) { var o = p.Value as JObject; if (o == null) continue; string u = ((string)o["Username"] ?? p.Name).ToLowerInvariant(); if (u == login && string.Equals((string)o["Platform"], "epic", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace((string)o["GameId"])) return ((string)o["GameId"]).Trim(); }
            }
            catch (Exception) { }
            return "";
        }

        /// <summary>every twitch login that belongs to this Epic account: the channel owner, plus matchmaking players who linked it. Aliases fold onto the main login.</summary>
        static List<string> LoginsOfEpic(string epic)
        {
            var l = new List<string>(); JObject d; lock (L) d = Load();
            if (epic == ((string)d["epic"] ?? "innocentpenguin").ToLowerInvariant()) l.Add(((string)d["login"] ?? "innocentpenguin_").ToLowerInvariant());
            try
            {
                var pj = JObject.Parse(File.ReadAllText(Path.Combine(HostApi.DataDir, "players.json"), Encoding.UTF8).TrimStart((char)0xFEFF));
                foreach (var p in pj.Properties()) { var o = p.Value as JObject; if (o == null) continue; if (string.Equals((string)o["Platform"], "epic", StringComparison.OrdinalIgnoreCase) && string.Equals(((string)o["GameId"] ?? "").Trim(), epic, StringComparison.OrdinalIgnoreCase)) l.Add(((string)o["Username"] ?? p.Name).ToLowerInvariant()); }
            }
            catch (Exception) { }
            return l.Select(x => { try { return Boards.CanonLogin(x); } catch (Exception) { return x; } }).Distinct().ToList();
        }

        /// <summary>Saves each fresh rank pull to Data/ranks/rl_ranks.json for the profile push (rocketLeague). Only linked accounts, never a random lookup.</summary>
        static void PublishProfiles(string epic, JObject ranks)
        {
            var logins = LoginsOfEpic(epic); if (logins.Count == 0 || ranks == null || !ranks.HasValues) return;
            lock (L)
            {
                JObject doc = null; try { if (File.Exists(RanksP)) doc = JObject.Parse(File.ReadAllText(RanksP, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { }
                if (doc == null) doc = new JObject(); var users = doc["users"] as JObject ?? new JObject(); doc["users"] = users;
                long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                foreach (var lg in logins) users[lg] = new JObject { { "at", now }, { "ranks", ranks.DeepClone() } };
                doc["updatedAt"] = now;
                Directory.CreateDirectory(Path.GetDirectoryName(RanksP)); string tmp = RanksP + ".tmp";
                File.WriteAllText(tmp, doc.ToString(), new UTF8Encoding(false)); if (File.Exists(RanksP)) File.Delete(RanksP); File.Move(tmp, RanksP);
            }
        }

        /// <summary>the channel owner's fallback file keeps the latest tracker values (the manual !setrank override still wins for 24 h)</summary>
        static void KeepLast(JObject ranks)
        {
            if (ranks == null || !ranks.HasValues) return;
            lock (L)
            {
                var d = Load(); var last = d["last"] as JObject ?? new JObject(); foreach (var k in AllLists) if (!string.IsNullOrEmpty((string)ranks[k])) last[k] = ranks[k];
                last["at"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); last["source"] = "tracker"; d["last"] = last;
                try { File.WriteAllText(FileP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            }
        }

        static string Current(JObject d, string k)
        {   // manual override (24 h) > latest tracker values > old values
            var man = d["manual"] as JObject; long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            if (man != null && !string.IsNullOrEmpty((string)man[k]) && now - ((long?)man["at"] ?? 0) < ManualHours * 3600) return (string)man[k];
            var last = d["last"] as JObject; if (last != null && !string.IsNullOrEmpty((string)last[k])) return (string)last[k];
            return ((string)d[k] ?? "").Trim();
        }

        static JObject Load()
        {
            try { if (File.Exists(FileP)) return JObject.Parse(File.ReadAllText(FileP, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { }
            var d = new JObject { { "1v1", "Champion I Div II (999)" }, { "2v2", "Grand Champion I Div III (1532)" }, { "3v3", "Champion II Div III (1276)" }, { "peak", "" }, { "updated", "2026-10-19" }, { "source", "seeded from RocketRankBot's last post" } };
            try { File.WriteAllText(FileP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            return d;
        }

        static string Clean(string s)
        {   // no pings, links or command starts in anything the bot repeats
            s = Regex.Replace(s ?? "", @"https?://\S+|www\.\S+|@\w+", "").Trim(); s = Regex.Replace(s, @"\s+", " ");
            while (s.StartsWith("!") || s.StartsWith("/") || s.StartsWith(".")) s = s.Substring(1).TrimStart();
            return s.Length > 80 ? s.Substring(0, 80) : s;
        }

        static string ListOf(string w)
        {
            w = (w ?? "").ToLowerInvariant().Replace("'", "").Trim('/', '-', ' ');
            switch (w)
            {
                case "1s": case "1v1": case "ones": case "duel": case "solo": return "1v1";
                case "2s": case "2v2": case "twos": case "doubles": return "2v2";
                case "3s": case "3v3": case "threes": case "standard": return "3v3";
                case "4s": case "4v4": case "quads": case "fours": return "4v4";
                case "hoops": case "hoop": case "basketball": return "hoops";
                case "rumble": return "rumble";
                case "dropshot": case "drop": return "dropshot";
                case "snowday": case "snow": case "hockey": case "puck": return "snowday";
                case "heatseeker": case "heatseek": case "heat": case "hs": case "seeker": return "heatseeker";
                case "tournament": case "tournaments": case "tourney": return "tournament";
            }
            return "";
        }

        public static void Handle(string user, string cmd, string[] args, bool mod, Action<string> say)
        {
            if (cmd == "!setrank") { if (mod) Set(args, say); return; }
            string only = ""; string who = "";
            foreach (var a in args) { string l = ListOf(a); if (l != "") only = l; else if (who == "") who = a.TrimStart('@'); }
            JObject d; lock (L) d = Load();
            string owner = ((string)d["epic"] ?? "innocentpenguin").ToLowerInvariant(); if (owner == "") owner = "innocentpenguin";
            string wl = who.ToLowerInvariant();
            bool isOwner = wl == "" || wl == owner || wl == "innocentpenguin_" || wl == "innocentpenguin" || wl == "ivan" || wl == "penguin";
            string plat = "epic", epic = owner, how = "owner";
            if (!isOwner) Resolve(who, out plat, out epic, out how);
            if (!Regex.IsMatch(epic, @"^[A-Za-z0-9_.\- ]{2,32}$")) { say("That does not look like an Epic name. Try !rank epic:name, steam:name, xbox:name or psn:name."); return; }
            string status; long age; JObject ranks = Lookup(plat, epic, ChatWaitMs, out status, out age);
            if (isOwner) { if (status == "ok") KeepLast(ranks); lock (L) d = Load(); }
            else if (status == "ok" && (how == "fuzzy" || who.Contains(":"))) { string pl0, nm0; SplitPlatform(who, out pl0, out nm0); Learn(nm0.ToLowerInvariant(), plat, epic); }   // remembered for next time
            Func<string, string> val = k => isOwner ? Current(d, k) : ((string)ranks?[k] ?? "");
            var keys = only != "" ? new[] { only } : Lists;
            var parts = keys.Select(k => new { k, v = val(k) }).Where(x => x.v != "").Select(x => Label(x.k) + ": " + x.v).ToList();
            if (parts.Count == 0 && only == "") parts = AllLists.Select(k => new { k, v = val(k) }).Where(x => x.v != "").Select(x => Label(x.k) + ": " + x.v).ToList();
            string nm = isOwner ? "" : ((string)_cache.GetValueOrDefault(plat + ":" + epic.ToLowerInvariant())?["name"] ?? epic);
            if (parts.Count == 0)
            {
                if (status == "notfound") say("Could not find " + epic + " on " + (plat == "epic" ? "Epic" : plat) + ". Try !rank epic:name, steam:name, xbox:name or psn:name.");
                else if (status == "pending") SayOnce(say, "Checking " + (isOwner ? "the ranks" : nm) + "... ask again in a few seconds.");
                else if (only != "" && (status == "ok" || status == "cached" || status == "stale")) say((isOwner ? "" : nm + ": ") + "No " + Label(only) + " rank found.");
                else if (status == "none" || status == "stale") SayOnce(say, "No rank data for " + (isOwner ? "the streamer" : nm) + " right now, try again in a bit." + (isOwner ? " A mod can set it with !setrank 2v2 Champion I Div II (1400)." : ""));
                else say(isOwner ? "No rank saved yet, a mod can set it with !setrank 2v2 Champion I Div II (1400)." : "No ranked playlists found for " + nm + ".");
                return;
            }
            string line = (isOwner ? "" : nm + " - ") + string.Join(" | ", parts);
            if (isOwner && only == "" && !string.IsNullOrEmpty((string)d["peak"])) line += " | Peak: " + (string)d["peak"];
            long shownAge = age; if (isOwner && status != "ok" && status != "cached") { long la = (long?)(d["last"] as JObject)?["at"] ?? 0; shownAge = la > 0 ? Now() - la : age; }
            if (status != "ok" && status != "cached" && shownAge >= 3600) line += " (as of " + Ago(shownAge) + ")";
            say(line);
        }

        static void Set(string[] args, Action<string> say)
        {
            string rest = string.Join(" ", args).Trim();
            if (rest == "") { say("Usage: !setrank 2v2 Champion I Div II (1400), or !setrank peak GC2."); return; }
            lock (L)
            {
                var d = Load(); int n = 0; var man = d["manual"] as JObject; if (man == null) { man = new JObject(); d["manual"] = man; }
                var bulk = Regex.Matches(rest, @"Ranked\s+(1v1|2v2|3v3)\s*:\s*(.+?)(?=\s*\|\s*Ranked\s|\s*$)", RegexOptions.IgnoreCase);
                if (bulk.Count > 0) foreach (Match m in bulk) { string v = Clean(m.Groups[2].Value); if (v != "") { man[m.Groups[1].Value.ToLowerInvariant()] = v; n++; } }
                else
                {
                    string key = args[0].ToLowerInvariant() == "peak" ? "peak" : ListOf(args[0]);
                    if (key == "") { say("Which one? Use 1v1, 2v2, 3v3 or peak, like !setrank 2v2 Champion I Div II (1400)."); return; }
                    string v = Clean(string.Join(" ", args.Skip(1)));
                    if (key == "peak") { d["peak"] = v.ToLowerInvariant() == "clear" ? "" : v; n = 1; }
                    else if (v == "" || v.ToLowerInvariant() == "clear") { man.Remove(key); n = 1; } else { man[key] = v; n = 1; }
                }
                if (n == 0) { say("Could not read that rank."); return; }
                man["at"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); d["updated"] = DateTime.UtcNow.ToString("yyyy-MM-dd");
                try { File.WriteAllText(FileP, d.ToString(), new UTF8Encoding(false)); } catch (Exception ex) { Clog.Warn("rank", ex.Message); say("Could not save the rank."); return; }
            }
            say("Rank saved for 24 h, then the tracker takes over again. Thanks!");
        }
    }
}
