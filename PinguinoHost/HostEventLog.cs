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
    /// <summary>Structured logs for the Master View (and the bots): GET /api/eventlog?kind=chat|players|backend&amp;since=&amp;before=&amp;limit=&amp;user=&amp;type=&amp;group=&amp;level=
    /// Every event is {id, ts (ms), kind, type, user, text, group, detail}. chat = Data\chat_logs\live (recorded by LiveLog); backend = the Host/Core console logs (info and up);
    /// players = Data\runtime\eventlog\players.jsonl: derived once a second from the customs state (queue joins/leaves/kicks, teams as blue/orange lists, game end, bulk removals tagged with a group id + count),
    /// strike changes (players.json) and wheel entrants; backfilled from matches.json and the chat log the first time. Staff view: the Host API is loopback-only.</summary>
    public static class EventLog
    {
        static readonly object L = new object(); static bool _started; static List<JObject> _players = new List<JObject>();
        static string Dir { get { return Path.Combine(HostApi.DataDir, "runtime", "eventlog"); } }
        static string PlayersP { get { return Path.Combine(Dir, "players.jsonl"); } }
        class Cmd { public long Ts; public string User, Cmd1, Args; public int Role; }
        static readonly List<Cmd> _cmds = new List<Cmd>();

        // ---------------- event shape ----------------
        static string Short(string s) { using (var h = SHA1.Create()) return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(s ?? ""))).Replace("-", "").Substring(0, 6).ToLowerInvariant(); }
        public static JObject Ev(long ts, string kind, string type, string user, string text, string group = null, JObject detail = null)
        {
            return new JObject { { "id", kind + ":" + ts + ":" + Short(type + "|" + user + "|" + text + "|" + group) }, { "ts", ts }, { "kind", kind }, { "type", type }, { "user", user ?? "" }, { "text", text ?? "" }, { "group", group }, { "detail", detail ?? new JObject() } };
        }
        static long NowMs() { return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(); }

        // ---------------- chat / backend readers ----------------
        class FileCache { public long Len; public DateTime Mt; public List<JObject> Rows; }
        static readonly Dictionary<string, FileCache> _fc = new Dictionary<string, FileCache>();
        static List<JObject> Cached(string path, Func<string, List<JObject>> parse)
        {
            try
            {
                var fi = new FileInfo(path); if (!fi.Exists) return new List<JObject>();
                lock (_fc) { FileCache c; if (_fc.TryGetValue(path, out c) && c.Len == fi.Length && c.Mt == fi.LastWriteTimeUtc) return c.Rows; }
                string txt; using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)) using (var sr = new StreamReader(fs, Encoding.UTF8)) txt = sr.ReadToEnd();
                var rows = parse(txt); lock (_fc) _fc[path] = new FileCache { Len = fi.Length, Mt = fi.LastWriteTimeUtc, Rows = rows }; return rows;
            }
            catch (Exception) { return new List<JObject>(); }
        }
        static IEnumerable<string> Lines(string t) { foreach (var l in t.Split('\n')) { var s = l.Trim(); if (s != "") yield return s; } }
        static List<JObject> ParseChat(string txt)
        {
            var bots = Boards.AllBots(); var o = new List<JObject>();
            foreach (var l in Lines(txt))
            {
                try
                {
                    var j = JObject.Parse(l); string u = (string)j["u"] ?? "", m = (string)j["m"] ?? ""; long t = (long?)j["t"] ?? 0; bool cmd = ((int?)j["c"] ?? 0) == 1;
                    bool bot = bots.Contains(u.ToLowerInvariant()) || Boards.IsBot(u);
                    o.Add(Ev(t, "chat", bot ? "bot" : cmd ? "command" : "chat", u, m, null, new JObject { { "userId", (string)j["i"] ?? "" }, { "bot", bot } }));
                }
                catch (Exception) { }
            }
            return o;
        }
        static List<JObject> ParseConsole(string txt, string module)
        {
            var o = new List<JObject>();
            foreach (var l in Lines(txt))
            {
                try
                {
                    var j = JObject.Parse(l); string lvl = ((string)j["level"] ?? "info").ToLowerInvariant(); if (lvl == "debug") continue;
                    long t = (long)(((double?)j["ts"] ?? 0) * 1000); string src = (string)j["source"] ?? "";
                    o.Add(Ev(t, "backend", src == "" ? "log" : src, "", (string)j["msg"] ?? "", null, new JObject { { "level", lvl }, { "module", module } }));
                }
                catch (Exception) { }
            }
            return o;
        }
        static List<JObject> AllChat(long since, long before, int need)
        {
            string dir = LiveLog.LiveDir; if (!Directory.Exists(dir)) return new List<JObject>();
            var res = new List<JObject>();
            foreach (var f in Directory.GetFiles(dir, "*.jsonl").OrderByDescending(x => x))
            {
                var rows = Cached(f, ParseChat); res.AddRange(rows);
                if (since > 0) { if (rows.Count > 0 && rows.Max(r => (long)r["ts"]) < since) break; }
                else if (res.Count(r => (long)r["ts"] < before) >= need) break;
            }
            return res;
        }
        /// <summary>overlay file change for the backend feed: {type:"overlay", text:"players.html changed", detail:{file, action: changed|created|deleted|renamed, by}}</summary>
        public static void Overlay(string file, string action, string by, string note = null)
        {
            try
            {
                var d = new JObject { { "file", file }, { "action", action }, { "by", by ?? "" }, { "level", "info" }, { "module", "host" } }; if (note != null) d["note"] = note;
                var e = Ev(NowMs(), "backend", "overlay", by ?? "", file + " " + action + (by != null && by != "" ? " by " + by : ""), null, d);
                lock (L) { Directory.CreateDirectory(Dir); File.AppendAllText(Path.Combine(Dir, "backend.jsonl"), e.ToString(Newtonsoft.Json.Formatting.None) + "\n", new UTF8Encoding(false)); }
                try { Events.Publish("backendlog", e); } catch (Exception) { }
            }
            catch (Exception) { }
        }
        static List<JObject> AllBackend()
        {
            var res = new List<JObject>(); res.AddRange(Cached(Path.Combine(Dir, "backend.jsonl"), t => Lines(t).Select(l => { try { return JObject.Parse(l); } catch (Exception) { return null; } }).Where(x => x != null).ToList())); string dir = Path.Combine(HostApi.DataDir, "runtime", "console");
            foreach (var m in new[] { "host", "core" }) { string mm = m; res.AddRange(Cached(Path.Combine(dir, mm + ".jsonl"), t => ParseConsole(t, mm))); }
            return res;
        }

        // ---------------- query ----------------
        public static JObject Query(System.Collections.Specialized.NameValueCollection q)
        {
            string kind = (q["kind"] ?? "chat").ToLowerInvariant(); if (kind != "chat" && kind != "players" && kind != "backend") return new JObject { { "ok", false }, { "error", "kind must be chat, players or backend" } };
            long since = 0, before = long.MaxValue; long.TryParse(q["since"], out since); if (!long.TryParse(q["before"], out before) || before <= 0) before = long.MaxValue;
            int limit = 200; if (!int.TryParse(q["limit"], out limit)) limit = 200; limit = Math.Max(1, Math.Min(1000, limit));
            string user = (q["user"] ?? "").ToLowerInvariant(), type = (q["type"] ?? "").ToLowerInvariant(), group = q["group"] ?? "", level = (q["level"] ?? "").ToLowerInvariant();
            IEnumerable<JObject> src;
            if (kind == "chat") src = AllChat(since, before, limit * 3);
            else if (kind == "backend") src = AllBackend();
            else lock (L) src = _players.ToList();
            var f = src.Where(e => (long)e["ts"] > since && (long)e["ts"] < before
                && (user == "" || ((string)e["user"]).ToLowerInvariant() == user || DetailHas(e, user))
                && (type == "" || ((string)e["type"]).ToLowerInvariant() == type)
                && (group == "" || (string)e["group"] == group)
                && (level == "" || ((string)e["detail"]["level"] ?? "") == level)).OrderBy(e => (long)e["ts"]).ThenBy(e => (string)e["id"]).ToList();
            List<JObject> page; bool more;
            if (since > 0) { page = f.Take(limit).ToList(); more = f.Count > limit; }   // forward: everything after `since`, oldest first
            else { page = f.Skip(Math.Max(0, f.Count - limit)).ToList(); more = f.Count > limit; }   // newest `limit` before `before`; more = older ones exist
            long latest = page.Count > 0 ? (long)page[page.Count - 1]["ts"] : since; long oldest = page.Count > 0 ? (long)page[0]["ts"] : 0;
            return new JObject { { "ok", true }, { "kind", kind }, { "count", page.Count }, { "more", more }, { "latest", latest }, { "oldest", oldest }, { "next", since > 0 ? latest : oldest }, { "events", new JArray(page) } };
        }
        static bool DetailHas(JObject e, string user)
        {
            var d = e["detail"] as JObject; if (d == null) return false;
            foreach (var k in new[] { "blue", "orange", "players" }) { var a = d[k] as JArray; if (a != null && a.Any(x => string.Equals((string)x, user, StringComparison.OrdinalIgnoreCase))) return true; }
            return false;
        }

        // ---------------- players log (live derivation) ----------------
        public static void OnChat(string user, string text, int role)
        {
            text = (text ?? "").Trim(); if (!text.StartsWith("!")) return;
            var p = text.Split(new[] { ' ' }, 2); lock (L) { _cmds.Add(new Cmd { Ts = NowMs(), User = (user ?? "").ToLowerInvariant(), Role = role, Cmd1 = p[0].ToLowerInvariant(), Args = p.Length > 1 ? p[1].Trim() : "" }); if (_cmds.Count > 40) _cmds.RemoveAt(0); }
        }
        static Cmd Recent(Func<Cmd, bool> f, int ms = 6000) { lock (L) { long now = NowMs(); return _cmds.LastOrDefault(c => now - c.Ts <= ms && f(c)); } }
        static void Add(JObject e)
        {
            lock (L) { _players.Add(e); if (_players.Count > 20000) _players.RemoveAt(0); try { Directory.CreateDirectory(Dir); File.AppendAllText(PlayersP, e.ToString(Newtonsoft.Json.Formatting.None) + "\n", new UTF8Encoding(false)); } catch (Exception) { } }
            try { Events.Publish("playerlog", e); } catch (Exception) { }
        }

        static List<string> _pq; static string _pMatch; static bool? _pOpen; static Dictionary<string, int> _pStrikes; static HashSet<string> _pWheel; static DateTime _pPlayersMt = DateTime.MinValue;
        static JArray _pBlue, _pOrange;
        public static void Start()
        {
            if (_started) return; _started = true;
            try { Load(); } catch (Exception ex) { Clog.Warn("eventlog", "load failed: " + ex.Message); }
            Task.Run(async () => { await Task.Delay(3000); while (true) { try { Tick(); } catch (Exception ex) { Clog.Warn("eventlog", "tick failed: " + ex.Message); } await Task.Delay(1000); } });
        }
        static void Load()
        {
            if (File.Exists(PlayersP)) { foreach (var l in File.ReadAllLines(PlayersP, Encoding.UTF8)) { try { _players.Add(JObject.Parse(l)); } catch (Exception) { } } return; }
            var back = Backfill(); Directory.CreateDirectory(Dir);
            File.WriteAllText(PlayersP, string.Concat(back.Select(e => e.ToString(Newtonsoft.Json.Formatting.None) + "\n")), new UTF8Encoding(false)); _players = back;
            Clog.Info("eventlog", "players log backfilled with " + back.Count + " events");
        }
        static string Names(JToken t) { return string.Join(", ", (t as JArray ?? new JArray()).Select(x => (string)x)); }
        static void TeamEvents(List<JObject> o, long ts, string id, string format, string mode, JArray blue, JArray orange, string winner, long? endTs)
        {
            o.Add(Ev(ts, "players", "teams", "", "Match #" + id + (string.IsNullOrEmpty(format) ? "" : " " + format) + ": blue " + Names(blue) + " vs orange " + Names(orange), "match-" + id,
                new JObject { { "id", id }, { "format", format }, { "mode", mode }, { "blue", blue }, { "orange", orange } }));
            if (endTs.HasValue)
            {
                o.Add(Ev(endTs.Value, "players", "game_end", "", "Match #" + id + " finished" + (!string.IsNullOrEmpty(winner) ? ", " + winner + " won" : ""), "match-" + id, new JObject { { "id", id }, { "winner", winner ?? "" } }));
                int n = blue.Count + orange.Count;
                foreach (var team in new[] { "blue", "orange" })
                    foreach (var u in (team == "blue" ? blue : orange)) o.Add(Ev(endTs.Value, "players", "match_clear", (string)u, (string)u + " left the match", "end-" + id, new JObject { { "team", team }, { "count", n }, { "match", id } }));
            }
        }
        static JArray MatchNames(JToken t) { return new JArray((t as JArray ?? new JArray()).Select(x => x is JObject ? ((string)x["Username"] ?? (string)x["username"] ?? "") : (string)x).Where(x => !string.IsNullOrEmpty(x))); }
        static List<JObject> Backfill()
        {
            var o = new List<JObject>();
            try
            {
                foreach (var f in new[] { Path.Combine(HostApi.DataDir, "runtime", "matches.json"), Path.Combine(HostApi.DataDir, "matches.json") })
                {
                    if (!File.Exists(f)) continue;
                    foreach (var m in JArray.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)).OfType<JObject>())
                    {
                        long cr = (long?)m["CreatedAt"] ?? 0; if (cr == 0) continue; long? fin = (long?)m["FinishedAt"];
                        if (fin == null && m["Winner"] != null && m["Winner"].Type != JTokenType.Null && (string)m["Winner"] != "") fin = cr + 1;
                        TeamEvents(o, cr * 1000, ((int?)m["Id"] ?? 0).ToString(), (string)m["Format"], (string)m["Mode"], MatchNames(m["Blue"]), MatchNames(m["Orange"]), (string)m["Winner"], fin.HasValue ? fin * 1000 : (long?)null);
                    }
                    break;
                }
            }
            catch (Exception ex) { Clog.Warn("eventlog", "matches backfill failed: " + ex.Message); }
            try
            {
                string dir = LiveLog.LiveDir;
                if (Directory.Exists(dir))
                    foreach (var f in Directory.GetFiles(dir, "*.jsonl").OrderBy(x => x))
                        foreach (var e in Cached(f, ParseChat))
                        {
                            if ((bool)e["detail"]["bot"] || (string)e["type"] != "command") continue;
                            var p = ((string)e["text"]).Trim().Split(new[] { ' ' }, 2); string c = p[0].ToLowerInvariant(), a = p.Length > 1 ? p[1].Trim() : ""; string u = (string)e["user"]; long ts = (long)e["ts"];
                            var d = new JObject { { "derived", true }, { "source", "chat log" } };
                            if (c == "!join") o.Add(Ev(ts, "players", "join", u, u + " typed !join", null, d));
                            else if (c == "!leave" || c == "!notme") o.Add(Ev(ts, "players", "leave", u, u + " typed " + c, null, d));
                            else if ((c == "!kick" || c == "!strike" || c == "!unstrike") && a != "")
                            { string t = a.Split(' ')[0].TrimStart('@').ToLowerInvariant(); d["by"] = u; d["unverified"] = true; o.Add(Ev(ts, "players", c == "!kick" ? "kick" : c == "!strike" ? "strike" : "strike_removed", t, u + " typed " + c + " " + t, null, d)); }
                        }
            }
            catch (Exception ex) { Clog.Warn("eventlog", "chat backfill failed: " + ex.Message); }
            return o.OrderBy(e => (long)e["ts"]).ToList();
        }
        static JObject LastMatchOf(string id)
        {
            try { foreach (var f in new[] { Path.Combine(HostApi.DataDir, "runtime", "matches.json"), Path.Combine(HostApi.DataDir, "matches.json") }) if (File.Exists(f)) return JArray.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)).OfType<JObject>().FirstOrDefault(m => ((int?)m["Id"] ?? -1).ToString() == id); } catch (Exception) { }
            return null;
        }
        static void Tick()
        {
            long now = NowMs(); var st = CustomsView.State();
            if ((bool?)st["ok"] == true)
            {
                var q = (st["queue"] as JArray ?? new JArray()).Select(x => (string)x["username"] ?? "").Where(x => x != "").ToList();
                var match = st["match"] as JObject; string mid = match == null ? null : ((string)match["id"] ?? "");
                bool open = (bool?)st["open"] ?? false;
                var blueNow = MatchNames(match == null ? null : match["blue"]); var orangeNow = MatchNames(match == null ? null : match["orange"]);
                if (_pq != null)
                {
                    if (_pOpen.HasValue && open != _pOpen.Value) { var c = Recent(x => x.Cmd1 == "!queue" && x.Role >= 3); Add(Ev(now, "players", open ? "queue_open" : "queue_close", c == null ? "" : c.User, "Queue " + (open ? "opened" : "closed") + (c == null ? "" : " by " + c.User))); }
                    if (mid != null && mid != _pMatch)
                    {
                        var tl = new List<JObject>(); TeamEvents(tl, now, mid, (string)st["format"], (string)st["mode"], blueNow, orangeNow, null, null); foreach (var e in tl) Add(e);
                    }
                    var inMatch = new HashSet<string>(blueNow.Concat(orangeNow).Select(x => (string)x));
                    foreach (var u in q.Except(_pq)) Add(Ev(now, "players", "join", u, u + " joined the queue", null, new JObject { { "position", q.IndexOf(u) + 1 } }));
                    var gone = _pq.Except(q).Where(u => !inMatch.Contains(u)).ToList();
                    string grp = gone.Count >= 3 ? "bulk-" + now : null;
                    foreach (var u in gone)
                    {
                        var self = Recent(x => x.User == u && (x.Cmd1 == "!leave" || x.Cmd1 == "!notme")); var kick = Recent(x => x.Role >= 3 && (x.Cmd1 == "!kick" || x.Cmd1 == "!remove") && x.Args.TrimStart('@').ToLowerInvariant().StartsWith(u));
                        var clear = Recent(x => x.Role >= 3 && x.Cmd1 == "!queue" && x.Args.ToLowerInvariant().StartsWith("clear"));
                        string type = self != null ? "leave" : kick != null ? "kick" : clear != null ? "queue_clear" : "removed";
                        string by = kick != null ? kick.User : clear != null ? clear.User : "";
                        var d = new JObject(); if (by != "") d["by"] = by; if (grp != null) d["count"] = gone.Count;
                        Add(Ev(now, "players", type, u, u + (type == "leave" ? " left the queue" : type == "kick" ? " was kicked by " + by : type == "queue_clear" ? " removed (queue cleared)" : " was removed from the queue"), grp, d));
                    }
                    if (_pMatch != null && mid != _pMatch)
                    {
                        var last = LastMatchOf(_pMatch); string winner = last == null ? "" : ((string)last["Winner"] ?? "");
                        var pb = _pBlue ?? new JArray(); var po = _pOrange ?? new JArray(); int cnt = pb.Count + po.Count;
                        Add(Ev(now, "players", "game_end", "", "Match #" + _pMatch + " finished" + (winner != "" ? ", " + winner + " won" : ""), "match-" + _pMatch, new JObject { { "id", _pMatch }, { "winner", winner } }));
                        foreach (var team in new[] { "blue", "orange" }) foreach (var u in (team == "blue" ? pb : po)) Add(Ev(now, "players", "match_clear", (string)u, (string)u + " left the match", "end-" + _pMatch, new JObject { { "team", team }, { "count", cnt }, { "match", _pMatch } }));
                    }
                }
                _pq = q; _pMatch = mid; _pOpen = open; _pBlue = blueNow; _pOrange = orangeNow;
            }
            StrikeTick(now); WheelTick(now);
        }
        static int StrikeTotal(JObject p) { return ((int?)p["Strikes"] ?? 0) + ((int?)p["PermaStrikes"] ?? 0); }
        static void StrikeTick(long now)
        {
            string f = Path.Combine(HostApi.DataDir, "runtime", "players.json"); if (!File.Exists(f)) f = Path.Combine(HostApi.DataDir, "players.json"); if (!File.Exists(f)) return;
            var mt = File.GetLastWriteTimeUtc(f); if (mt == _pPlayersMt) return; _pPlayersMt = mt;
            JObject j; try { j = JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { return; }
            var cur = new Dictionary<string, int>(); var perma = new Dictionary<string, string>();
            foreach (var kv in j.Properties()) { var p = kv.Value as JObject; if (p == null) continue; cur[kv.Name.ToLowerInvariant()] = StrikeTotal(p); perma[kv.Name.ToLowerInvariant()] = (string)p["PermaReason"] ?? ""; }
            if (_pStrikes != null)
                foreach (var kv in cur)
                {
                    int before; _pStrikes.TryGetValue(kv.Key, out before); if (kv.Value == before) continue;
                    string key = kv.Key;
                    var c = Recent(x => x.Role >= 3 && (x.Cmd1 == "!strike" || x.Cmd1 == "!unstrike" || x.Cmd1 == "!pardon") && x.Args.TrimStart('@').ToLowerInvariant().StartsWith(key), 15000);
                    bool up = kv.Value > before; string type = up ? "strike" : c != null ? "strike_removed" : "strike_expired";
                    var d = new JObject { { "total", kv.Value }, { "was", before } }; if (c != null) { d["by"] = c.User; if (c.Args.Contains(" ")) d["reason"] = c.Args.Substring(c.Args.IndexOf(' ') + 1).Trim(); }
                    if (perma[kv.Key] != "" && up) d["permaReason"] = perma[kv.Key];
                    Add(Ev(now, "players", type, kv.Key, up ? kv.Key + " got a strike (" + kv.Value + " total)" : kv.Key + (type == "strike_removed" ? " had a strike removed" : "'s strike wore off") + " (" + kv.Value + " total)", null, d));
                }
            _pStrikes = cur;
        }
        static void WheelTick(long now)
        {
            JObject w; try { w = Events.WheelState(); } catch (Exception) { return; }
            var ent = new HashSet<string>((w["entrants"] as JArray ?? new JArray()).Select(x => (string)x));
            if (_pWheel != null)
            {
                foreach (var u in ent.Except(_pWheel)) Add(Ev(now, "players", "wheel_join", u, u + " signed up for the wheel"));
                var gone = _pWheel.Except(ent).ToList(); string grp = gone.Count >= 3 ? "wheel-" + now : null;
                foreach (var u in gone) Add(Ev(now, "players", "wheel_leave", u, u + " left the wheel", grp, grp == null ? null : new JObject { { "count", gone.Count } }));
            }
            _pWheel = ent;
        }
    }
}
