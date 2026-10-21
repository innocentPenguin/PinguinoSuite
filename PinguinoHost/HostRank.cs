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

        const int CacheSec = 900, ManualHours = 24, PauseMin = 30;   // ONE tracker call per Epic account per 15 min; that call reads every playlist, !rank only shows the one asked for
        static long _pausedUntil, _lastReq;
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

        static string Fetch(string epic)
        {
            string log = Environment.GetEnvironmentVariable("PINGUINO_RANK_CALLLOG"); if (!string.IsNullOrEmpty(log)) { try { File.AppendAllText(log, epic + "\n"); } catch (Exception) { } }
            string fx = Environment.GetEnvironmentVariable("PINGUINO_RANK_FIXTURE"); if (!string.IsNullOrEmpty(fx)) { string f2 = fx.Replace(".json", "." + epic + ".json"); if (File.Exists(f2)) return File.ReadAllText(f2); return File.Exists(fx) ? File.ReadAllText(fx) : null; }
            long wait = 2000 - (Environment.TickCount64 - _lastReq); if (wait > 0) System.Threading.Thread.Sleep((int)wait); _lastReq = Environment.TickCount64;
            var psi = new System.Diagnostics.ProcessStartInfo { FileName = "curl", RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true };
            foreach (var a in new[] { "-s", "-L", "--max-time", "10", "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "-H", "Accept: application/json", "https://api.tracker.gg/api/v2/rocket-league/standard/profile/epic/" + Uri.EscapeDataString(epic) }) psi.ArgumentList.Add(a);
            using (var pr = System.Diagnostics.Process.Start(psi))
            {
                var err = pr.StandardError.ReadToEndAsync(); string o = pr.StandardOutput.ReadToEnd();
                if (!pr.WaitForExit(14000)) { try { pr.Kill(); } catch (Exception) { } return null; }
                return pr.ExitCode == 0 ? o : null;
            }
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

        /// <summary>The ranks of one Epic account, every playlist at once. The tracker is called at most once per account per 15 minutes (a failed or empty answer counts too, and the
        /// cache survives a restart), so any number of !rank 2s / !rank dropshot / !rank hoops lines cost one call. status: ok | cached | notfound | blocked | pending.</summary>
        static JObject Lookup(string epic, out string status)
        {
            epic = epic.ToLowerInvariant(); long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); JObject c;
            lock (L)
            {
                LoadCache(); _cache.TryGetValue(epic, out c);
                if (c != null && now - ((long?)c["at"] ?? 0) < CacheSec) { string s = (string)c["status"] ?? "ok"; status = s == "ok" ? "cached" : s; return c["ranks"] as JObject ?? new JObject(); }
                if (now < _pausedUntil) { status = "blocked"; return c == null ? null : c["ranks"] as JObject; }
                if (c == null) c = new JObject { { "ranks", new JObject() } };
                c["at"] = now; c["status"] = "pending"; _cache[epic] = c;   // reserved: nobody else asks for this account for 15 min
            }
            string body = null; try { body = Fetch(epic); } catch (Exception ex) { Clog.Warn("rank", "lookup failed: " + ex.Message); }
            lock (L)
            {
                if (!string.IsNullOrWhiteSpace(body) && body.Contains("CollectorResultStatus::NotFound")) { c["status"] = "notfound"; status = "notfound"; SaveCache(); return c["ranks"] as JObject ?? new JObject(); }
                if (string.IsNullOrWhiteSpace(body) || !body.TrimStart().StartsWith("{")) { _pausedUntil = now + PauseMin * 60; c["status"] = "blocked"; status = "blocked"; SaveCache(); Clog.Warn("rank", "tracker lookup blocked or empty; paused " + PauseMin + " min"); return c["ranks"] as JObject; }
                var got = new JObject(); int n = 0; try { n = ParseProfile(body, got); } catch (Exception) { }
                if (n == 0) { _pausedUntil = now + PauseMin * 60; c["status"] = "blocked"; status = "blocked"; SaveCache(); Clog.Warn("rank", "tracker answered without ranked playlists"); return c["ranks"] as JObject; }
                try { string nm = (string)JObject.Parse(body)["data"]?["platformInfo"]?["platformUserHandle"]; if (!string.IsNullOrEmpty(nm)) c["name"] = Clean(nm); } catch (Exception) { }
                c["ranks"] = got; c["status"] = "ok"; status = "ok"; SaveCache();
                try { PublishProfiles(epic, got); } catch (Exception ex) { Clog.Warn("rank", "profile ranks not saved: " + ex.Message); }
                return got;
            }
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
            foreach (var a in args) { string l = ListOf(a); if (l != "") only = l; else if (who == "") who = a.TrimStart('@').ToLowerInvariant(); }
            JObject d; lock (L) d = Load();
            string owner = ((string)d["epic"] ?? "innocentpenguin").ToLowerInvariant(); if (owner == "") owner = "innocentpenguin";
            bool isOwner = who == "" || who == owner || who == "innocentpenguin_" || who == "innocentpenguin" || who == "ivan" || who == "penguin";
            string epic = isOwner ? owner : who; string linked = isOwner ? "" : EpicOfLogin(who); if (linked != "") epic = linked.ToLowerInvariant();   // !rank alice: a viewer who linked their Epic account is found by their twitch name
            if (!Regex.IsMatch(epic, @"^[A-Za-z0-9_.\- ]{2,32}$")) { say("That does not look like an Epic name."); return; }
            string status = "pending"; JObject ranks = null;
            try { var t = System.Threading.Tasks.Task.Run(() => { string st; var r = Lookup(epic, out st); return Tuple.Create(r, st); }); if (t.Wait(14000)) { ranks = t.Result.Item1; status = t.Result.Item2; } else status = "pending"; } catch (Exception) { status = "blocked"; }
            if (isOwner) { if (status == "ok") KeepLast(ranks); lock (L) d = Load(); }
            Func<string, string> val = k => isOwner ? Current(d, k) : ((string)ranks?[k] ?? "");
            var keys = only != "" ? new[] { only } : Lists;
            var parts = keys.Select(k => new { k, v = val(k) }).Where(x => x.v != "").Select(x => Label(x.k) + ": " + x.v).ToList();
            if (parts.Count == 0 && only == "") parts = AllLists.Select(k => new { k, v = val(k) }).Where(x => x.v != "").Select(x => Label(x.k) + ": " + x.v).ToList();
            string nm = isOwner ? "" : ((string)_cache.GetValueOrDefault(epic)?["name"] ?? epic);
            if (parts.Count == 0)
            {
                if (status == "notfound") say("Could not find " + epic + " on Epic.");
                else if (status == "pending") say("Looking that up, ask again in a few seconds.");
                else if (status == "blocked") say("The rank lookup is paused for a bit, try again later.");
                else if (only != "") say((isOwner ? "" : nm + ": ") + "No " + Label(only) + " rank found.");
                else say(isOwner ? "No rank saved yet, a mod can set it with !setrank 2v2 Champion I Div II (1400)." : "No ranked playlists found for " + nm + ".");
                return;
            }
            string line = (isOwner ? "" : nm + " - ") + string.Join(" | ", parts);
            if (isOwner && only == "" && !string.IsNullOrEmpty((string)d["peak"])) line += " | Peak: " + (string)d["peak"];
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
