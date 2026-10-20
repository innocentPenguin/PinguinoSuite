using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>7TV channel emotes + how often chat used them. READ-ONLY use of the public 7TV API (GET https://7tv.io/v3/users/twitch/{id}, one call per 30 minutes, cached
    /// in Data\emotes\set.json). Usage is counted from the stored chat (Data\chat_logs\YYYY\MM\YYYY-MM-DD.txt, and Data\runtime\chat_logs\*.jsonl for days without a .txt)
    /// by whole-word match of the emote name, bots left out, alias accounts folded. Totals, per month and per person are kept in Data\emotes\usage.json.
    /// Chat: !emote name, !topemotes [month]. API: GET /api/emotes[?q=&amp;month=YYYY-MM&amp;limit=n] (for the website's emote search page).</summary>
    public static class Emotes
    {
        static readonly object L = new object();
        static JObject _set;                      // {id, name, emotes:[{id,name,animated}], fetchedAt}
        static JObject _usage;                    // {setHash, files:{path:bytes}, emotes:{name:{total, months:{yyyy-MM:n}, users:{login:n}, first, last}}}
        static bool _started; static DateTime _lastScan = DateTime.MinValue, _lastFetch = DateTime.MinValue; static string _note = "";
        static string SevenBase { get { return Environment.GetEnvironmentVariable("PINGUINO_SEVENTV_BASE") ?? "https://7tv.io/v3"; } }
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d; } }
        static string Dir { get { var d = Path.Combine(Root, "emotes"); Directory.CreateDirectory(d); return d; } }

        public static void Start()
        {
            if (_started) return; _started = true;
            var t = new Thread(() =>
            {
                Thread.Sleep(20000);
                while (true)
                {
                    try { Refresh(false); } catch (Exception ex) { Clog.Warn("emotes", "refresh failed: " + ex.Message); }
                    Thread.Sleep(10 * 60 * 1000);
                }
            }) { IsBackground = true };
            t.Start();
        }

        // ---- the 7TV set ----
        static void LoadSet()
        {
            if (_set != null) return;
            try { var f = Path.Combine(Dir, "set.json"); if (File.Exists(f)) _set = JObject.Parse(File.ReadAllText(f, Encoding.UTF8)); } catch (Exception) { }
            if (_set == null) _set = new JObject { { "id", "" }, { "name", "" }, { "emotes", new JArray() }, { "fetchedAt", "" } };
        }
        static string TwitchId()
        {
            string id = Environment.GetEnvironmentVariable("PINGUINO_EMOTE_TWITCH_ID");
            if (!string.IsNullOrEmpty(id)) return id;
            try { return (string)HostApi.StreamerCreds()["BroadcasterId"] ?? ""; } catch (Exception) { return ""; }
        }
        static bool FetchSet()
        {
            string id = TwitchId(); if (id == "") { _note = "no broadcaster id yet (sign the streamer in)"; return false; }
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(20) })
                {
                    h.DefaultRequestHeaders.UserAgent.ParseAdd("PinguinoHost/1.0");
                    var j = JObject.Parse(h.GetStringAsync(SevenBase + "/users/twitch/" + Uri.EscapeDataString(id)).Result);
                    var es = j["emote_set"] as JObject; if (es == null) { _note = "this channel has no active 7TV emote set"; return false; }
                    var list = new JArray();
                    foreach (var e in es["emotes"] as JArray ?? new JArray())
                    {
                        string eid = (string)e["id"] ?? "", nm = (string)e["name"] ?? ""; if (eid == "" || nm == "" || !Regex.IsMatch(eid, "^[A-Za-z0-9]{8,40}$")) continue;
                        list.Add(new JObject { { "id", eid }, { "name", nm }, { "animated", (bool?)e["data"]?["animated"] ?? false } });
                    }
                    if (list.Count == 0) { _note = "7TV returned an empty emote set"; return false; }
                    lock (L)
                    {
                        _set = new JObject { { "id", (string)es["id"] ?? "" }, { "name", (string)es["name"] ?? "" }, { "emotes", list }, { "fetchedAt", DateTime.UtcNow.ToString("o") } };
                        File.WriteAllText(Path.Combine(Dir, "set.json"), _set.ToString());
                    }
                    _note = "ok"; return true;
                }
            }
            catch (Exception ex) { _note = "7TV request failed: " + (ex.InnerException != null ? ex.InnerException.Message : ex.Message); return false; }
        }

        // ---- usage from the chat logs ----
        static readonly Regex TxtLine = new Regex(@"^\[(?<d>\d{4}-\d\d)-(?<dd>\d\d) \d\d:\d\d:\d\d\]\s+(?:#\S+\s+)?(?<u>[A-Za-z0-9_]{2,25}):\s(?<m>.*)$", RegexOptions.Compiled);
        static string Hash(JArray em) { return string.Join(",", em.Select(e => (string)e["name"]).OrderBy(x => x, StringComparer.Ordinal)).GetHashCode().ToString(); }

        /// <summary>fetch the set when it is older than 30 minutes (or force) and read new chat lines.</summary>
        public static JObject Refresh(bool force)
        {
            lock (L) LoadSet();
            if (force || (DateTime.UtcNow - _lastFetch).TotalMinutes >= 30 || ((JArray)_set["emotes"]).Count == 0) { _lastFetch = DateTime.UtcNow; FetchSet(); }
            Scan(force);
            return Api("", "", 0);
        }

        static void Scan(bool fullRescan)
        {
            lock (L)
            {
                LoadSet(); var emotes = (JArray)_set["emotes"]; if (emotes.Count == 0) return;
                if (_usage == null)
                {
                    try { var f = Path.Combine(Dir, "usage.json"); if (File.Exists(f)) _usage = JObject.Parse(File.ReadAllText(f, Encoding.UTF8)); } catch (Exception) { }
                }
                string hash = Hash(emotes);
                if (_usage == null || fullRescan || (string)_usage["setHash"] != hash) _usage = new JObject { { "setHash", hash }, { "files", new JObject() }, { "emotes", new JObject() } };
                var names = new HashSet<string>(emotes.Select(e => (string)e["name"]));
                var files = (JObject)_usage["files"]; var use = (JObject)_usage["emotes"]; bool changed = false;
                var al = Boards.AliasMap();
                Action<string, string, string, string> count = (login, month, day, msg) =>
                {
                    if (Boards.IsBot(login)) return;
                    string who = login.ToLowerInvariant(); for (int i = 0; i < 6 && al.ContainsKey(who); i++) who = al[who];
                    foreach (string tok in msg.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries))
                    {
                        if (!names.Contains(tok)) continue;
                        var e = use[tok] as JObject; if (e == null) use[tok] = e = new JObject { { "total", 0 }, { "months", new JObject() }, { "users", new JObject() }, { "first", day }, { "last", day } };
                        e["total"] = (int)e["total"] + 1;
                        var mo = (JObject)e["months"]; mo[month] = ((int?)mo[month] ?? 0) + 1;
                        var us = (JObject)e["users"]; us[who] = ((int?)us[who] ?? 0) + 1;
                        if (string.CompareOrdinal(day, (string)e["first"]) < 0) e["first"] = day; if (string.CompareOrdinal(day, (string)e["last"]) > 0) e["last"] = day;
                    }
                };
                var txtDays = new HashSet<string>();
                string logRoot = Path.Combine(Root, "chat_logs");
                if (Directory.Exists(logRoot))
                    foreach (var f in Directory.EnumerateFiles(logRoot, "*.txt", SearchOption.AllDirectories).OrderBy(x => x, StringComparer.Ordinal))
                    {
                        if (f.IndexOf("_original-downloads", StringComparison.OrdinalIgnoreCase) >= 0 || f.IndexOf("history", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                        string day = Path.GetFileNameWithoutExtension(f); if (!Regex.IsMatch(day, @"^\d{4}-\d\d-\d\d$")) continue; txtDays.Add(day);
                        long size = new FileInfo(f).Length, done = (long?)files[f] ?? 0; if (size <= done) continue;
                        try
                        {
                            using (var fs = new FileStream(f, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                            {
                                fs.Seek(done, SeekOrigin.Begin); using (var sr = new StreamReader(fs, Encoding.UTF8))
                                {
                                    string line; while ((line = sr.ReadLine()) != null)
                                    {
                                        var m = TxtLine.Match(line); if (!m.Success) continue;
                                        count(m.Groups["u"].Value, m.Groups["d"].Value, m.Groups["d"].Value + "-" + m.Groups["dd"].Value, m.Groups["m"].Value);
                                    }
                                }
                            }
                            files[f] = size; changed = true;
                        }
                        catch (Exception ex) { Clog.Warn("emotes", f + ": " + ex.Message); }
                    }
                var live = Path.Combine(HostApi.DataDir, "chat_logs");
                if (Directory.Exists(live))
                    foreach (var f in Directory.EnumerateFiles(live, "*.jsonl").OrderBy(x => x, StringComparer.Ordinal))
                    {
                        string day = Path.GetFileNameWithoutExtension(f); if (txtDays.Contains(day)) continue;                    // the .txt of that day already has these lines
                        long size = new FileInfo(f).Length, done = (long?)files[f] ?? 0; if (size <= done) continue;
                        try
                        {
                            using (var fs = new FileStream(f, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                            {
                                fs.Seek(done, SeekOrigin.Begin); using (var sr = new StreamReader(fs, new UTF8Encoding(false)))
                                {
                                    string line; while ((line = sr.ReadLine()) != null)
                                    {
                                        try
                                        {
                                            var j = JObject.Parse(line.TrimStart('\uFEFF')); if ((int?)j["c"] == 1) continue;
                                            string u = (string)j["u"] ?? "", msg = (string)j["m"] ?? ""; if (u == "" || msg == "") continue;
                                            var dt = DateTimeOffset.FromUnixTimeMilliseconds((long)j["t"]).UtcDateTime;
                                            count(u, dt.ToString("yyyy-MM"), dt.ToString("yyyy-MM-dd"), msg);
                                        }
                                        catch (Exception) { }
                                    }
                                }
                            }
                            files[f] = size; changed = true;
                        }
                        catch (Exception ex) { Clog.Warn("emotes", f + ": " + ex.Message); }
                    }
                if (changed) { try { File.WriteAllText(Path.Combine(Dir, "usage.json"), _usage.ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception) { } }
                _lastScan = DateTime.UtcNow;
            }
        }

        // some emotes are ordinary words ("no", "yes", "L", "uh"): their counts also hold normal use of the word, so they are flagged and left out of the top lists
        static HashSet<string> _words;
        static bool Ambiguous(string name)
        {
            if (_words == null)
            {
                _words = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                try { var f = Path.Combine(Root, "common-words.txt"); if (File.Exists(f)) foreach (var w in File.ReadLines(f)) _words.Add(w.Trim()); } catch (Exception) { }
            }
            return name.Length <= 2 || _words.Contains(name) || Regex.IsMatch(name, "^[a-z]{1,4}$");
        }

        // ---- queries ----
        static int Uses(JObject u, string month) { return u == null ? 0 : (month == "" ? (int)u["total"] : (int?)((JObject)u["months"])[month] ?? 0); }

        /// <summary>the emotes of the set with their usage. q filters by name (substring, any case); month = "" for all time or YYYY-MM; limit 0 = all.</summary>
        public static JObject Api(string q, string month, int limit)
        {
            lock (L)
            {
                LoadSet(); if (_usage == null) { try { var f = Path.Combine(Dir, "usage.json"); if (File.Exists(f)) _usage = JObject.Parse(File.ReadAllText(f, Encoding.UTF8)); } catch (Exception) { } }
                var use = _usage != null ? (JObject)_usage["emotes"] : new JObject();
                q = (q ?? "").Trim(); month = (month ?? "").Trim();
                var rows = new List<JObject>(); int total = 0;
                foreach (JObject e in (JArray)_set["emotes"])
                {
                    string nm = (string)e["name"]; var u = use[nm] as JObject; int n = Uses(u, month); total += n;
                    if (q != "" && nm.IndexOf(q, StringComparison.OrdinalIgnoreCase) < 0) continue;
                    var top = u == null ? new List<KeyValuePair<string, int>>() : ((JObject)u["users"]).Properties().Select(p => new KeyValuePair<string, int>(p.Name, (int)p.Value)).OrderByDescending(p => p.Value).ThenBy(p => p.Key, StringComparer.Ordinal).Take(3).ToList();
                    rows.Add(new JObject { { "id", e["id"] }, { "name", nm }, { "animated", e["animated"] }, { "url", "https://cdn.7tv.app/emote/" + (string)e["id"] + "/2x.webp" }, { "url4", "https://cdn.7tv.app/emote/" + (string)e["id"] + "/4x.webp" },
                        { "uses", n }, { "ambiguous", Ambiguous(nm) }, { "lastUsed", u == null ? "" : (string)u["last"] }, { "firstUsed", u == null ? "" : (string)u["first"] }, { "topUsers", new JArray(top.Select(t => new JObject { { "login", t.Key }, { "name", Boards.DisplayName(t.Key) }, { "uses", t.Value } })) } });
                }
                rows = rows.OrderByDescending(r => (int)r["uses"]).ThenBy(r => (string)r["name"], StringComparer.OrdinalIgnoreCase).ToList();
                int rank = 0; foreach (var r in rows) r["rank"] = ++rank;
                return new JObject { { "ok", true }, { "set", new JObject { { "id", _set["id"] }, { "name", _set["name"] }, { "count", ((JArray)_set["emotes"]).Count }, { "fetchedAt", _set["fetchedAt"] } } },
                    { "month", month }, { "totalUses", total }, { "matches", rows.Count }, { "note", _note }, { "emotes", new JArray(limit > 0 ? rows.Take(limit) : rows) } };
            }
        }

        // ---- chat ----
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();
        static bool Cooling(string key, int sec) { lock (Cool) { DateTime t; if (Cool.TryGetValue(key, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; Cool[key] = DateTime.UtcNow; return false; } }
        static int CoolSec(string env, int d) { int v; return int.TryParse(Environment.GetEnvironmentVariable(env), out v) ? v : d; }
        const string Link = "https://innocentpenguin.com/emotes";

        public static bool IsCommand(string cmd) { return cmd == "!emote" || cmd == "!topemotes" || cmd == "!topemote"; }

        public static bool Handle(string user, string cmd, string[] args, Action<string> say, Func<string, string> parseMonth, Func<string, string> monthLabel)
        {
            if (!IsCommand(cmd)) return false;
            if (Cooling("g|" + cmd, CoolSec("PINGUINO_STREAK_COOL_GLOBAL", 8)) || Cooling("u|" + cmd + "|" + user.ToLowerInvariant(), CoolSec("PINGUINO_STREAK_COOL_USER", 20))) return true;
            try
            {
                lock (L) { LoadSet(); if (((JArray)_set["emotes"]).Count == 0 || _usage == null) { Scan(false); } }
                if (cmd == "!emote")
                {
                    string name = args.Length > 0 ? args[0] : "";
                    if (name == "") { say("Usage: !emote <name> - how often an emote of the channel's 7TV set is used. Search them all: " + Link); return true; }
                    var all = Api("", "", 0); var arr = (JArray)all["emotes"];
                    var hit = arr.FirstOrDefault(e => (string)e["name"] == name) ?? arr.FirstOrDefault(e => string.Equals((string)e["name"], name, StringComparison.OrdinalIgnoreCase));
                    if (hit == null)
                    {
                        var like = arr.Where(e => ((string)e["name"]).IndexOf(name, StringComparison.OrdinalIgnoreCase) >= 0).Take(4).Select(e => (string)e["name"]).ToList();
                        say(name + " is not in the channel's 7TV emote set" + (like.Count > 0 ? ". Did you mean: " + string.Join(", ", like) + "?" : ".") + " " + Link); return true;
                    }
                    int uses = (int)hit["uses"], rank = (int)hit["rank"], of = arr.Count;
                    var top = hit["topUsers"] as JArray; string who = top != null && top.Count > 0 ? " Top user: " + (string)top[0]["name"] + " (" + (int)top[0]["uses"] + ")." : "";
                    string last = (string)hit["lastUsed"] != "" ? " Last used " + DateTime.Parse((string)hit["lastUsed"], CultureInfo.InvariantCulture).ToString("MMM d, yyyy", CultureInfo.InvariantCulture) + "." : "";
                    say((string)hit["name"] + (uses > 0 ? " has been used " + uses.ToString("N0", CultureInfo.InvariantCulture) + " times (#" + rank + " of " + of + ")." + who + last : " is in the 7TV set but nobody has used it in chat yet.") + ((bool)hit["ambiguous"] ? " (it is also an everyday word, so this includes normal use)" : "") + " " + Link);
                    return true;
                }
                string month = ""; foreach (var a in args) { month = parseMonth(a); if (month != "") break; }
                var d = Api("", month, 0); var list = ((JArray)d["emotes"]).Where(e => (int)e["uses"] > 0 && (bool)e["ambiguous"] == false).Take(8).ToList();
                string when = month == "" ? "all time" : monthLabel(month);
                if (list.Count == 0) { say("No 7TV emote uses recorded for " + when + " yet. " + Link); return true; }
                say("Top emotes (" + when + "): " + string.Join(" | ", list.Select((e, i) => (i + 1) + ". " + (string)e["name"] + " " + ((int)e["uses"]).ToString("N0", CultureInfo.InvariantCulture))) + " - search all: " + Link);
            }
            catch (Exception ex) { Clog.Warn("emotes", "command failed: " + ex.Message); }
            return true;
        }
    }
}
