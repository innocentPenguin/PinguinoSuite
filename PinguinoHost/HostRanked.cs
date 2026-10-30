using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The "Ranked" activity for competitive sessions: after every game a mod marks a win or a loss and the ranked.html overlay shows the row of slots.
    /// Ranked is an activity but NOT joinable (no queue, !join, roster or wheel) and it runs CONCURRENTLY with customs: while it is active a bare !win / !loss / !w / !l / !undo
    /// always mean ranked; customs results come from the Master View buttons or "!customs win|loss &lt;team&gt;" (the Core still owns "!win &lt;team&gt;" with a team). Ending customs
    /// does not touch ranked and the other way round.
    /// State: Data\runtime\ranked.json { active, limit, breakAfter, lossStreak, brk{active,reason,since,said}, since:"WL", days:{"YYYY-MM-DD":"WLW"}, meta:{"YYYY-MM-DD":{startedAt,endedAt,breaks:[{at,reason,afterGames}]}} }
    /// (atomic write, survives restarts); the day is the Host's stream day (Periods.DayKey), the week its ISO week.
    /// Breaks: after N games (default 3) or M losses in a row (default 2) since the last resume (0 turns a rule off) ranked goes on a break: the overlay shows "Break", ONE chat line goes out,
    /// the Master View offers Open queue / YT 1v1 orders / Resume. Resume restarts the break counters; the day record continues.
    /// Chat (mods mark, everybody reads): !win !w / !loss !l / !undo / !ranked [win|loss|undo|limit N|reset|start|stop|break|resume|breakafter N|lossstreak M|week|day].
    /// API: GET /api/ranked, POST /api/ranked {action: start|stop|win|loss|undo|reset|limit|break|resume|breakafter|lossstreak, value}.</summary>
    public static class RankedActivity
    {
        sealed class Meta { public string StartedAt = "", EndedAt = ""; public List<Tuple<string, string, int>> Breaks = new List<Tuple<string, string, int>>(); }
        static readonly object L = new object();
        static bool _loaded, _active, _brk, _brkSaid; static int _limit = DefaultLimit, _breakAfter = DefaultBreakAfter, _lossStreak = DefaultLossStreak;
        static string _brkReason = "", _brkSince = "", _since = "";   // _since = the games since the last resume ("WLW"), what the break rules count
        static readonly SortedDictionary<string, string> Days = new SortedDictionary<string, string>(StringComparer.Ordinal);
        static readonly Dictionary<string, Meta> Metas = new Dictionary<string, Meta>();
        public const int DefaultLimit = 5, MaxLimit = 20, KeepDays = 120, MaxGamesPerDay = 200, DefaultBreakAfter = 3, DefaultLossStreak = 2;
        public const string BreakLine = "Break time: customs / 1v1 / play with viewers";
        /// <summary>unix seconds; the sim test moves it to cross a day / week boundary</summary>
        public static Func<long> NowFn = () => DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        static string FilePath { get { return Path.Combine(HostApi.DataDir, "ranked.json"); } }
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();

        static string Iso(long t) { return DateTimeOffset.FromUnixTimeSeconds(t).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture) + "Z"; }
        static Meta MetaOf(string day) { Meta m; if (!Metas.TryGetValue(day, out m)) Metas[day] = m = new Meta(); return m; }

        static void Load()
        {
            if (_loaded) return; _loaded = true;
            try
            {
                if (!File.Exists(FilePath)) return;
                var o = JObject.Parse(File.ReadAllText(FilePath).TrimStart((char)0xFEFF));
                _active = (bool?)o["active"] ?? false; _limit = Math.Max(1, Math.Min(MaxLimit, (int?)o["limit"] ?? DefaultLimit));
                _breakAfter = Math.Max(0, Math.Min(MaxLimit, (int?)o["breakAfter"] ?? DefaultBreakAfter)); _lossStreak = Math.Max(0, Math.Min(MaxLimit, (int?)o["lossStreak"] ?? DefaultLossStreak));
                var b = o["brk"] as JObject; if (b != null) { _brk = (bool?)b["active"] ?? false; _brkReason = (string)b["reason"] ?? ""; _brkSince = (string)b["since"] ?? ""; _brkSaid = (bool?)b["said"] ?? false; }
                _since = new string((((string)o["since"]) ?? "").Where(ch => ch == 'W' || ch == 'L').ToArray());
                foreach (var p in (o["days"] as JObject) ?? new JObject()) { string g = new string(((string)p.Value ?? "").Where(ch => ch == 'W' || ch == 'L').ToArray()); if (g != "") Days[p.Key] = g; }
                foreach (var p in (o["meta"] as JObject) ?? new JObject())
                {
                    var mo = p.Value as JObject; if (mo == null) continue; var m = new Meta { StartedAt = (string)mo["startedAt"] ?? "", EndedAt = (string)mo["endedAt"] ?? "" };
                    foreach (var bt in (mo["breaks"] as JArray) ?? new JArray()) m.Breaks.Add(Tuple.Create((string)bt["at"] ?? "", (string)bt["reason"] ?? "", (int?)bt["afterGames"] ?? 0));
                    Metas[p.Key] = m;
                }
            }
            catch (Exception ex) { Clog.Warn("ranked", "ranked.json: " + ex.Message); }
        }
        static void Save()
        {
            try
            {
                while (Days.Count > KeepDays) Days.Remove(Days.Keys.First());
                foreach (var k in Metas.Keys.Where(k => !Days.ContainsKey(k) && string.CompareOrdinal(k, Days.Count > 0 ? Days.Keys.First() : "") < 0).ToList()) Metas.Remove(k);
                var days = new JObject(); foreach (var p in Days) days[p.Key] = p.Value;
                var meta = new JObject(); foreach (var p in Metas) meta[p.Key] = new JObject { { "startedAt", p.Value.StartedAt }, { "endedAt", p.Value.EndedAt },
                    { "breaks", new JArray(p.Value.Breaks.Select(b => (JToken)new JObject { { "at", b.Item1 }, { "reason", b.Item2 }, { "afterGames", b.Item3 } })) } };
                string f = FilePath, tmp = f + ".tmp"; Directory.CreateDirectory(Path.GetDirectoryName(f));
                File.WriteAllText(tmp, new JObject { { "active", _active }, { "limit", _limit }, { "breakAfter", _breakAfter }, { "lossStreak", _lossStreak },
                    { "brk", new JObject { { "active", _brk }, { "reason", _brkReason }, { "since", _brkSince }, { "said", _brkSaid } } }, { "since", _since }, { "days", days }, { "meta", meta } }.ToString());
                if (File.Exists(f)) File.Delete(f); File.Move(tmp, f);
            }
            catch (Exception ex) { Clog.Warn("ranked", "could not save ranked.json: " + ex.Message); }
        }

        static string Today() { return Periods.DayKey(NowFn()); }
        static string WeekOf(string day) { DateTime d; if (!DateTime.TryParseExact(day, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out d)) return ""; return Periods.WeekKey(new DateTimeOffset(d.Year, d.Month, d.Day, 12, 0, 0, TimeSpan.Zero).ToUnixTimeSeconds()); }
        static string GamesToday() { string g; return Days.TryGetValue(Today(), out g) ? g : ""; }
        static int Count(string g, char c) { return g.Count(x => x == c); }
        static string Net(int n) { return n > 0 ? "+" + n : n.ToString(CultureInfo.InvariantCulture); }
        static JObject Err(string m) { var o = Snapshot(); o["ok"] = false; o["error"] = m; return o; }
        static int TrailingLosses(string g) { int n = 0; for (int i = g.Length - 1; i >= 0 && g[i] == 'L'; i--) n++; return n; }
        static JObject Totals(Func<string, bool> pick)
        {
            int w = 0, l = 0, d = 0; foreach (var p in Days) if (pick(p.Key)) { w += Count(p.Value, 'W'); l += Count(p.Value, 'L'); d++; }
            return new JObject { { "wins", w }, { "losses", l }, { "net", w - l }, { "days", d } };
        }

        /// <summary>the state as the overlay and the Master View read it (caller holds the lock and has loaded)</summary>
        static JObject Snapshot()
        {
            string day = Today(), g = GamesToday(); int w = Count(g, 'W'), l = Count(g, 'L'); string wk = WeekOf(day), mo = day.Length >= 7 ? day.Substring(0, 7) : "";
            string vis = g.Length > _limit ? g.Substring(g.Length - _limit) : g; Meta m; Metas.TryGetValue(day, out m);
            var week = Totals(k => WeekOf(k) == wk); week.Remove("days"); var month = Totals(k => k.StartsWith(mo, StringComparison.Ordinal)); month.Remove("days");
            return new JObject { { "ok", true }, { "active", _active }, { "limit", _limit }, { "games", new JArray(g.Select(c => (JToken)c.ToString())) }, { "net", w - l }, { "inProgress", g.Length + 1 },
                { "wins", w }, { "losses", l }, { "day", day }, { "week", week }, { "month", month },
                { "visible", new JArray(vis.Select(c => (JToken)c.ToString())) },   // visible = the last `limit` games (additive field for the overlay)
                { "break", new JObject { { "active", _brk }, { "reason", _brk ? _brkReason : "" }, { "afterGames", _breakAfter }, { "lossStreak", _lossStreak }, { "since", _brk ? _brkSince : "" } } },
                { "breakAfter", _breakAfter }, { "lossStreak", _lossStreak }, { "sinceBreak", _since.Length },
                { "breaks", new JArray((m == null ? new List<Tuple<string, string, int>>() : m.Breaks).Select(b => (JToken)new JObject { { "at", b.Item1 }, { "reason", b.Item2 }, { "afterGames", b.Item3 } })) },
                { "startedAt", m == null ? "" : m.StartedAt }, { "endedAt", m == null ? "" : m.EndedAt } };
        }
        public static JObject State() { lock (L) { Load(); return Snapshot(); } }
        public static bool Active { get { lock (L) { Load(); return _active; } } }

        /// <summary>the history the site gets (POST /api/bot/ranked): last 30 days with games, last 12 weeks and months, the live break and settings</summary>
        public static JObject PushPayload()
        {
            lock (L)
            {
                Load(); var days = new JArray();
                foreach (var p in Days.Reverse().Take(30).Reverse())
                {
                    Meta m; Metas.TryGetValue(p.Key, out m); int w = Count(p.Value, 'W'), l = Count(p.Value, 'L');
                    days.Add(new JObject { { "day", p.Key }, { "games", new JArray(p.Value.Select(c => (JToken)c.ToString())) }, { "wins", w }, { "losses", l }, { "net", w - l },
                        { "startedAt", m == null ? "" : m.StartedAt }, { "endedAt", m == null ? "" : m.EndedAt },
                        { "breaks", new JArray((m == null ? new List<Tuple<string, string, int>>() : m.Breaks).Select(b => (JToken)new JObject { { "at", b.Item1 }, { "reason", b.Item2 }, { "afterGames", b.Item3 } })) } });
                }
                var weeks = new SortedDictionary<string, int[]>(StringComparer.Ordinal); var months = new SortedDictionary<string, int[]>(StringComparer.Ordinal);
                foreach (var p in Days)
                {
                    int w = Count(p.Value, 'W'), l = Count(p.Value, 'L'); string wk = WeekOf(p.Key), mo = p.Key.Substring(0, 7);
                    foreach (var pair in new[] { Tuple.Create(weeks, wk), Tuple.Create(months, mo) })
                    { int[] a; if (!pair.Item1.TryGetValue(pair.Item2, out a)) pair.Item1[pair.Item2] = a = new int[3]; a[0] += w; a[1] += l; a[2]++; }
                }
                Func<SortedDictionary<string, int[]>, string, JArray> list = (d, key) => new JArray(d.Reverse().Take(12).Reverse().Select(p => (JToken)new JObject { { key, p.Key }, { "wins", p.Value[0] }, { "losses", p.Value[1] }, { "net", p.Value[0] - p.Value[1] }, { "days", p.Value[2] } }));
                return new JObject { { "generatedAt", Iso(NowFn()) }, { "active", _active },
                    { "break", new JObject { { "active", _brk }, { "reason", _brk ? _brkReason : "" }, { "afterGames", _breakAfter }, { "lossStreak", _lossStreak } } },
                    { "settings", new JObject { { "limit", _limit }, { "breakAfter", _breakAfter }, { "lossStreak", _lossStreak } } },
                    { "days", days }, { "weeks", list(weeks, "week") }, { "months", list(months, "month") } };
            }
        }

        /// <summary>the break rules for the games since the last resume; null = no break due</summary>
        static string Due(string since)
        {
            if (_breakAfter > 0 && since.Length >= _breakAfter) return _breakAfter + (_breakAfter == 1 ? " game" : " games");
            if (_lossStreak > 0 && TrailingLosses(since) >= _lossStreak) return _lossStreak + (_lossStreak == 1 ? " loss" : " losses") + " in a row";
            return null;
        }
        static void StartBreak(string reason, string day)
        {
            long now = NowFn(); _brk = true; _brkReason = reason; _brkSince = Iso(now); _brkSaid = false; _pendingSay = true;
            MetaOf(day).Breaks.Add(Tuple.Create(_brkSince, reason, _since.Length));
        }
        static bool _pendingSay;

        /// <summary>start|stop|win|loss|undo|reset|limit|break|resume|breakafter|lossstreak (value = the number). Win / loss / undo / break need ranked to be running.</summary>
        public static JObject Apply(string action, int? value)
        {
            lock (L)
            {
                Load(); string a = (action ?? "").Trim().ToLowerInvariant(); string day = Today(), g = GamesToday(); long now = NowFn();
                switch (a)
                {
                    case "start": case "on": _active = true; break;
                    case "stop": case "off": case "end":
                        _active = false; _brk = false; _brkReason = ""; _brkSince = ""; _since = ""; Meta ms; if (Metas.TryGetValue(day, out ms) && ms.StartedAt != "") ms.EndedAt = Iso(now); break;
                    case "win": case "w": case "loss": case "l": case "lose":
                        if (!_active) return Err("ranked is not running (start it first)");
                        if (g.Length >= MaxGamesPerDay) return Err("too many games today");
                        char c = a[0] == 'w' ? 'W' : 'L'; Days[day] = g + c; _since += c;
                        var m = MetaOf(day); if (m.StartedAt == "") m.StartedAt = Iso(now); m.EndedAt = Iso(now);
                        if (!_brk) { string due = Due(_since); if (due != null) StartBreak(due, day); }
                        break;
                    case "undo":
                        if (!_active) return Err("ranked is not running (start it first)");
                        if (g == "") return Err("nothing to undo today");
                        if (g.Length == 1) Days.Remove(day); else Days[day] = g.Substring(0, g.Length - 1);
                        if (_since.Length > 0) _since = _since.Substring(0, _since.Length - 1);
                        if (_brk && _brkReason != "manual" && Due(_since) == null)   // the break came from the game just taken back
                        { _brk = false; _brkReason = ""; _brkSince = ""; _pendingSay = false; Meta mu; if (Metas.TryGetValue(day, out mu) && mu.Breaks.Count > 0) mu.Breaks.RemoveAt(mu.Breaks.Count - 1); }
                        break;
                    case "reset": if (g != "") Days.Remove(day); Metas.Remove(day); _since = ""; _brk = false; _brkReason = ""; _brkSince = ""; _pendingSay = false; break;
                    case "limit":
                        if (value == null || value < 1 || value > MaxLimit) return Err("limit must be 1 to " + MaxLimit);
                        _limit = value.Value; break;
                    case "break":
                        if (!_active) return Err("ranked is not running (start it first)");
                        if (_brk) return Err("already on a break");
                        StartBreak("manual", day); break;
                    case "resume":
                        if (!_brk) return Err("not on a break");
                        _brk = false; _brkReason = ""; _brkSince = ""; _since = ""; _pendingSay = false; break;
                    case "breakafter":
                        if (value == null || value < 0 || value > MaxLimit) return Err("breakafter must be 0 (off) to " + MaxLimit);
                        _breakAfter = value.Value; break;
                    case "lossstreak":
                        if (value == null || value < 0 || value > MaxLimit) return Err("lossstreak must be 0 (off) to " + MaxLimit);
                        _lossStreak = value.Value; break;
                    default: return Err("unknown action (start, stop, win, loss, undo, reset, limit, break, resume, breakafter, lossstreak)");
                }
                Save(); return Snapshot();
            }
        }

        /// <summary>The one chat line of a break, posted at most once per break (also across a restart); call after Apply, after the caller's own reply.</summary>
        public static void FlushBreakSay()
        {
            bool say; lock (L) { Load(); say = _pendingSay && _brk && !_brkSaid; _pendingSay = false; if (say) { _brkSaid = true; Save(); } }
            if (say) ChannelLore.Say(BreakLine);
        }

        /// <summary>POST /api/ranked {action, value?}</summary>
        public static JObject Mod(JObject b)
        {
            int? v = null; try { if (b != null && b["value"] != null && b["value"].Type != JTokenType.Null) v = (int)Math.Round((double)b["value"]); } catch (Exception) { return Err("value must be a number"); }
            var r = Apply(b == null ? "" : (string)b["action"], v); FlushBreakSay(); return r;
        }

        static string Line(JObject s) { return "Ranked today: " + (int)s["wins"] + "-" + (int)s["losses"] + " (" + Net((int)s["net"]) + ")"; }
        static string WeekLine(JObject s) { var w = (JObject)s["week"]; return "Ranked this week: " + (int)w["wins"] + "-" + (int)w["losses"] + " (" + Net((int)w["net"]) + ")"; }
        static bool Cooling(string user) { lock (Cool) { DateTime t; if (Cool.TryGetValue(user, out t) && (DateTime.UtcNow - t).TotalSeconds < 5) return true; Cool[user] = DateTime.UtcNow; return false; } }

        /// <summary>Called first for every chat command. True = the Host handled it (the Core must not); false = not ours.</summary>
        public static bool Intercept(string user, string cmd, string[] args, int role, Action<string> say)
        {
            bool mod = role >= 3; string who = "@" + PlatformUsers.Shown(user) + " "; string first = args.Length > 0 ? args[0].ToLowerInvariant() : "";
            switch (cmd)
            {
                case "!win": case "!w": case "!loss": case "!l": case "!lose":
                    if (args.Length > 0 || !Active) return false;   // "!win blue" and every !win while ranked is off belong to customs
                    if (!mod) return true;   // ranked is running: a viewer's !win gets nothing (not the Core's customs refusal)
                    return Mark(user, cmd.Substring(1), who, say);
                case "!undo":
                    if (!mod || !Active) return false;
                    return Mark(user, "undo", who, say);
                case "!activity":   // "!activity ranked" starts it; "!activity end" is customs' alone and leaves ranked running
                    if (mod && (first == "ranked" || (args.Length > 1 && args[1].ToLowerInvariant() == "ranked" && (first == "rl" || first == "fn"))))
                    { ModAudit.Log(user, "mod", "!activity", string.Join(" ", args)); Apply("start", null); say(who + "Ranked is on. " + Line(State())); return true; }
                    return false;
                case "!customs":   // the explicit customs result while ranked owns the bare !win
                    if (first != "win" && first != "loss" && first != "lose") return false;
                    if (!mod) return true;
                    string team = args.Length > 1 ? args[1].ToLowerInvariant() : "";
                    if (team != "blue" && team != "orange") { say(who + "!customs win|loss <blue|orange>"); return true; }
                    if (first != "win") team = team == "blue" ? "orange" : "blue";   // a loss for one team is the win of the other
                    ModAudit.Log(user, "mod", "!customs", string.Join(" ", args)); Program.Dispatch(user, "!win " + team, null, role, "", false, null); return true;
                case "!ranked": break;
                default: return false;
            }
            if (first == "" || first == "today" || first == "day" || first == "week")
            {
                if (Cooling(user.ToLowerInvariant())) return true;
                var s = State(); if (!(bool)s["active"] && (int)s["wins"] + (int)s["losses"] == 0 && first != "week") return true;   // nothing running, nothing today: silent
                say(who + (first == "week" ? WeekLine(s) : Line(s))); return true;
            }
            if (!mod) return true;   // the word is ours; viewers get nothing for the mod forms
            string a = first; int n;
            if (a == "win" || a == "w" || a == "loss" || a == "l" || a == "lose" || a == "undo") return Mark(user, a, who, say, true);
            if (a == "start" || a == "on" || a == "stop" || a == "off" || a == "reset")
            {
                ModAudit.Log(user, "mod", "!ranked", string.Join(" ", args)); var r = Apply(a, null);
                say(who + (a == "start" || a == "on" ? "Ranked is on. " + Line(r) : a == "reset" ? "Ranked reset. " + Line(r) : "Ranked is off.")); return true;
            }
            if (a == "limit")
            {
                if (args.Length < 2 || !int.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out n)) { say(who + "!ranked limit <1-" + MaxLimit + ">"); return true; }
                ModAudit.Log(user, "mod", "!ranked", string.Join(" ", args)); var r = Apply("limit", n);
                say(who + ((bool)r["ok"] ? "Ranked shows the last " + (int)r["limit"] + " games." : "Ranked limit is 1 to " + MaxLimit + ".")); return true;
            }
            if (a == "break" || a == "resume")
            {
                ModAudit.Log(user, "mod", "!ranked", a); var r = Apply(a, null);
                if (!(bool)r["ok"]) say(who + (string)r["error"] + "."); else if (a == "resume") say(who + "Ranked is back. " + Line(r));
                FlushBreakSay(); return true;   // the break itself is announced by its one line
            }
            if (a == "breakafter" || a == "lossstreak")
            {
                if (args.Length < 2 || !int.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out n)) { say(who + "!ranked " + a + " <0-" + MaxLimit + "> (0 = off)"); return true; }
                ModAudit.Log(user, "mod", "!ranked", string.Join(" ", args)); var r = Apply(a, n);
                if (!(bool)r["ok"]) say(who + (string)r["error"] + ".");
                else if (a == "breakafter") say(who + (n == 0 ? "Break after games: off." : "Break after " + n + (n == 1 ? " game." : " games.")));
                else say(who + (n == 0 ? "Break after losses in a row: off." : "Break after " + n + (n == 1 ? " loss" : " losses") + " in a row."));
                return true;
            }
            say(who + "Mods: !win / !loss / !undo, !ranked [win|loss|undo|limit N|reset|start|stop|break|resume|breakafter N|lossstreak M|week]; customs: !customs win|loss <team>"); return true;
        }

        static bool Mark(string user, string action, string who, Action<string> say, bool explicitForm = false)
        {
            ModAudit.Log(user, "mod", explicitForm ? "!ranked" : "!" + action, action);
            var r = Apply(action, null);
            if (!(bool)r["ok"]) { say(who + (string)r["error"] + "."); return true; }
            say(who + (action == "undo" ? "Undone. " : "") + Line(r)); FlushBreakSay(); return true;
        }
    }
}
