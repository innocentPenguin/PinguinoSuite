using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The "Ranked" activity for competitive sessions: after every game a mod marks a win or a loss and the ranked.html overlay shows the row of slots.
    /// State: Data\runtime\ranked.json { active, limit, days: { "YYYY-MM-DD": "WLW" } } (atomic write, survives restarts); the day is the Host's stream day (Periods.DayKey), the week its ISO week.
    /// Chat (mods mark, everybody reads): !win !w / !loss !l / !undo / !ranked [win|loss|undo|limit N|reset|start|stop|on|off|week|day]. !win/!loss/!w/!l mean ranked only while ranked is active and customs is NOT
    /// (customs wins when both run; "!ranked win|loss" is the explicit form). "!activity ranked" starts it, "!activity end" ends it (the Core still answers its own end).
    /// API: GET /api/ranked, POST /api/ranked {action: start|stop|win|loss|undo|reset|limit, value} -> {ok, active, limit, games, net, inProgress, wins, losses, day, week:{wins,losses,net}, visible}.</summary>
    public static class RankedActivity
    {
        static readonly object L = new object();
        static bool _loaded, _active; static int _limit = DefaultLimit;
        static readonly SortedDictionary<string, string> Days = new SortedDictionary<string, string>(StringComparer.Ordinal);
        public const int DefaultLimit = 5, MaxLimit = 20, KeepDays = 120, MaxGamesPerDay = 200;
        /// <summary>unix seconds; the sim test moves it to cross a day / week boundary</summary>
        public static Func<long> NowFn = () => DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        static string FilePath { get { return Path.Combine(HostApi.DataDir, "ranked.json"); } }
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();

        static void Load()
        {
            if (_loaded) return; _loaded = true;
            try
            {
                if (!File.Exists(FilePath)) return;
                var o = JObject.Parse(File.ReadAllText(FilePath).TrimStart((char)0xFEFF));
                _active = (bool?)o["active"] ?? false; _limit = Math.Max(1, Math.Min(MaxLimit, (int?)o["limit"] ?? DefaultLimit));
                foreach (var p in (o["days"] as JObject) ?? new JObject()) { string g = new string(((string)p.Value ?? "").Where(ch => ch == 'W' || ch == 'L').ToArray()); if (g != "") Days[p.Key] = g; }
            }
            catch (Exception ex) { Clog.Warn("ranked", "ranked.json: " + ex.Message); }
        }
        static void Save()
        {
            try
            {
                while (Days.Count > KeepDays) Days.Remove(Days.Keys.First());
                var days = new JObject(); foreach (var p in Days) days[p.Key] = p.Value;
                string f = FilePath, tmp = f + ".tmp"; Directory.CreateDirectory(Path.GetDirectoryName(f));
                File.WriteAllText(tmp, new JObject { { "active", _active }, { "limit", _limit }, { "days", days } }.ToString());
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

        /// <summary>the state as the overlay and the Master View read it (caller holds the lock and has loaded)</summary>
        static JObject Snapshot()
        {
            string g = GamesToday(); int w = Count(g, 'W'), l = Count(g, 'L'); string wk = WeekOf(Today()); int ww = 0, wl = 0;
            foreach (var p in Days) if (WeekOf(p.Key) == wk) { ww += Count(p.Value, 'W'); wl += Count(p.Value, 'L'); }
            string vis = g.Length > _limit ? g.Substring(g.Length - _limit) : g;
            return new JObject { { "ok", true }, { "active", _active }, { "limit", _limit }, { "games", new JArray(g.Select(c => (JToken)c.ToString())) }, { "net", w - l }, { "inProgress", g.Length + 1 },
                { "wins", w }, { "losses", l }, { "day", Today() }, { "week", new JObject { { "wins", ww }, { "losses", wl }, { "net", ww - wl } } },
                { "visible", new JArray(vis.Select(c => (JToken)c.ToString())) } };   // visible = the last `limit` games (additive field for the overlay)
        }
        public static JObject State() { lock (L) { Load(); return Snapshot(); } }
        public static bool Active { get { lock (L) { Load(); return _active; } } }

        /// <summary>start|stop|win|loss|undo|reset|limit (value = the limit). Win / loss / undo need ranked to be running.</summary>
        public static JObject Apply(string action, int? value)
        {
            lock (L)
            {
                Load(); string a = (action ?? "").Trim().ToLowerInvariant(); string day = Today(), g = GamesToday();
                switch (a)
                {
                    case "start": case "on": _active = true; break;
                    case "stop": case "off": case "end": _active = false; break;
                    case "win": case "w": case "loss": case "l": case "lose":
                        if (!_active) return Err("ranked is not running (start it first)");
                        if (g.Length >= MaxGamesPerDay) return Err("too many games today");
                        Days[day] = g + (a[0] == 'w' ? "W" : "L"); break;
                    case "undo":
                        if (!_active) return Err("ranked is not running (start it first)");
                        if (g == "") return Err("nothing to undo today");
                        if (g.Length == 1) Days.Remove(day); else Days[day] = g.Substring(0, g.Length - 1); break;
                    case "reset": if (g != "") Days.Remove(day); break;
                    case "limit":
                        if (value == null || value < 1 || value > MaxLimit) return Err("limit must be 1 to " + MaxLimit);
                        _limit = value.Value; break;
                    default: return Err("unknown action (start, stop, win, loss, undo, reset, limit)");
                }
                Save(); return Snapshot();
            }
        }

        /// <summary>POST /api/ranked {action, value?}</summary>
        public static JObject Mod(JObject b)
        {
            int? v = null; try { if (b != null && b["value"] != null && b["value"].Type != JTokenType.Null) v = (int)Math.Round((double)b["value"]); } catch (Exception) { return Err("value must be a number"); }
            return Apply(b == null ? "" : (string)b["action"], v);
        }

        static bool CustomsActive()
        {
            try { var s = CustomsView.State(); if (!((bool?)s["ok"] ?? false)) return false; string a = ((string)s["activity"] ?? "").Trim().ToLowerInvariant(); return a != "" && a != "none"; }
            catch (Exception) { return false; }
        }
        static string Line(JObject s) { return "Ranked today: " + (int)s["wins"] + "-" + (int)s["losses"] + " (" + Net((int)s["net"]) + ")"; }
        static string WeekLine(JObject s) { var w = (JObject)s["week"]; return "Ranked this week: " + (int)w["wins"] + "-" + (int)w["losses"] + " (" + Net((int)w["net"]) + ")"; }
        static bool Cooling(string user) { lock (Cool) { DateTime t; if (Cool.TryGetValue(user, out t) && (DateTime.UtcNow - t).TotalSeconds < 5) return true; Cool[user] = DateTime.UtcNow; return false; } }

        /// <summary>Called first for every chat command. True = the Host handled it (the Core must not); false = not ours (or only noted, like "!activity end").</summary>
        public static bool Intercept(string user, string cmd, string[] args, int role, Action<string> say)
        {
            bool mod = role >= 3; string who = "@" + PlatformUsers.Shown(user) + " "; string first = args.Length > 0 ? args[0].ToLowerInvariant() : "";
            switch (cmd)
            {
                case "!win": case "!w": case "!loss": case "!l": case "!lose":
                    if (!Active || CustomsActive()) return false;   // customs keeps its own !win
                    if (!mod) return true;   // ranked is running: a viewer's !win gets nothing (not the Core's customs refusal)
                    return Mark(user, cmd.Substring(1), who, say);
                case "!undo":
                    if (!mod || !Active) return false;
                    return Mark(user, "undo", who, say);
                case "!activity":
                    if (first == "end" && Active) { lock (L) { Apply("stop", null); } return false; }   // ranked ends with the activity; the Core still answers its own end
                    if (mod && (first == "ranked" || (args.Length > 1 && args[1].ToLowerInvariant() == "ranked" && (first == "rl" || first == "fn"))))
                    { ModAudit.Log(user, "mod", "!activity", string.Join(" ", args)); Apply("start", null); say(who + "Ranked is on. " + Line(State())); return true; }
                    return false;
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
            say(who + "Mods: !win / !loss / !undo, !ranked [win|loss|undo|limit N|reset|start|stop|week]"); return true;
        }

        static bool Mark(string user, string action, string who, Action<string> say, bool explicitForm = false)
        {
            ModAudit.Log(user, "mod", explicitForm ? "!ranked" : "!" + action, action);
            var r = Apply(action, null);
            if (!(bool)r["ok"]) { say(who + (string)r["error"] + "."); return true; }
            say(who + (action == "undo" ? "Undone. " : "") + Line(r)); return true;
        }
    }
}
