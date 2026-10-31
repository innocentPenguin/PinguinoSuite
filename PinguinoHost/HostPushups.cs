using System;
using System.Globalization;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The pushup counter: !pushup / !pushups / !pu. Anyone reads the counts; only mods change them (add, remove, set N, reset, on, off). Two counters: allTime (what the overlay shows; "count" in the API is the same number)
    /// and a per stream-day history (Periods' Chicago day; "session" = today) that answers today / this week / this month (DayCounts). add / remove move allTime and today; set N sets allTime; reset clears today only. They and the enabled flag live in Data\pushups.json (atomic write) and survive restarts.
    /// A one-time baseline: when the file carries "baseline" (written by Tools\seed-pushups.py, which backs the file up first) and "baselineApplied" is not true, the Host adds it to allTime once and marks it applied (a restart never re-adds).
    /// GET /api/pushup {enabled,count,allTime,session(=today),today,week,month,days,baseline?,baselineNote?,baselineApplied?}; POST /api/pushup {action,value} is the Master View write route (same gating as /api/customs/mod).</summary>
    public static class Pushups
    {
        static readonly object L = new object();
        static DateTime _mt; static bool _loaded, _enabled = true; static int _count; static JObject _days = new JObject(); static int _baseline; static string _baselineNote = ""; static bool _baselineApplied;
        const int Max = 100000, MaxStep = 1000;
        static string FilePath { get { return Path.Combine(HostApi.DataDir, "pushups.json"); } }

        public static bool IsCommand(string cmd) { return cmd == "!pushup" || cmd == "!pushups" || cmd == "!pu"; }

        static void Load()
        {
            if (_loaded && !(File.Exists(FilePath) && File.GetLastWriteTimeUtc(FilePath) > _mt)) return;   // a file NEWER than this Host's last read / write (a seed written while it runs) is read again, so the next Save never overwrites it
            _loaded = true;
            try
            {
                if (!File.Exists(FilePath)) return;
                _mt = File.GetLastWriteTimeUtc(FilePath);
                var o = JObject.Parse(File.ReadAllText(FilePath).TrimStart((char)0xFEFF));
                _enabled = (bool?)o["enabled"] ?? true;
                _count = Math.Max(0, Math.Min(Max, (int?)o["allTime"] ?? (int?)o["count"] ?? 0));   // an older file has only "count": that is the all-time number and today's too
                _days = o["days"] as JObject ?? new JObject();
                if (o["days"] == null) { int old = Math.Max(0, Math.Min(Max, (int?)o["session"] ?? (int?)o["count"] ?? 0)); if (old > 0) _days[DayCounts.DayOf(DayCounts.Now())] = old; }   // an older file kept one session number: it was today's
                _baseline = Math.Max(0, (int?)o["baseline"] ?? 0); _baselineNote = (string)o["baselineNote"] ?? ""; _baselineApplied = (bool?)o["baselineApplied"] == true;
                if (_baseline > 0 && !_baselineApplied) { _count = Clamp((long)_count + _baseline); _baselineApplied = true; Save(); }
            }
            catch (Exception ex) { Clog.Warn("pushup", "pushups.json: " + ex.Message); }
        }
        static void Save()
        {
            try
            {
                string f = FilePath, tmp = f + ".tmp"; Directory.CreateDirectory(Path.GetDirectoryName(f));
                File.WriteAllText(tmp, Json().ToString());
                if (File.Exists(f)) File.Delete(f); File.Move(tmp, f);
                _mt = File.GetLastWriteTimeUtc(f);
            }
            catch (Exception ex) { Clog.Warn("pushup", "could not save pushups.json: " + ex.Message); }
        }

        static JObject Json()
        {
            var o = new JObject { { "enabled", _enabled }, { "count", _count }, { "allTime", _count } };
            long ts = DayCounts.Now(); int today = DayCounts.Sum(_days, "today", ts);
            o["session"] = today; o["today"] = today; o["week"] = DayCounts.Sum(_days, "week", ts); o["month"] = DayCounts.Sum(_days, "month", ts); o["days"] = _days.DeepClone();
            if (_baseline > 0) { o["baseline"] = _baseline; o["baselineNote"] = _baselineNote; o["baselineApplied"] = _baselineApplied; }
            return o;
        }
        /// <summary>read pushups.json again now (POST /api/seeds/reload): a seed written while the Host runs needs no restart</summary>
        public static JObject Reload() { lock (L) { _loaded = false; Load(); return Json(); } }
        public static JObject State() { lock (L) { Load(); return Json(); } }
        static string Line(JObject s) { return "Pushups: " + (int)s["today"] + " today, " + (int)s["week"] + " this week, " + (int)s["month"] + " this month, " + (int)s["allTime"] + " all-time"; }
        static string PeriodLine(JObject s, string p) { return "Pushups " + DayCounts.Label(p) + ": " + (int)(p == "all" ? s["allTime"] : s[p == "today" ? "today" : p]); }

        /// <summary>one change: add|remove|set|reset|on|off; value is the amount (add / remove default 1, set needs it). Returns the new state plus ok / error.</summary>
        public static JObject Apply(string action, int? value)
        {
            lock (L)
            {
                Load(); string a = (action ?? "").Trim().ToLowerInvariant();
                switch (a)
                {
                    case "add": { int st = Step(value); _count = Clamp((long)_count + st); DayCounts.Add(_days, DayCounts.DayOf(DayCounts.Now()), st); break; }
                    case "remove": { int st = Step(value); _count = Clamp((long)_count - st); DayCounts.Add(_days, DayCounts.DayOf(DayCounts.Now()), -st); break; }
                    case "set": if (value == null) return Err("set needs a number"); _count = Clamp(value.Value); break;
                    case "reset": _days.Remove(DayCounts.DayOf(DayCounts.Now())); break;   // today / session only: the all-time number keeps its baseline
                    case "on": _enabled = true; break;
                    case "off": _enabled = false; break;
                    default: return Err("unknown action (add, remove, set, reset, on, off)");
                }
                Save();
                var r = Json(); r["ok"] = true; return r;
            }
        }
        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }
        static int Step(int? v) { return Math.Max(0, Math.Min(MaxStep, v ?? 1)); }
        static int Clamp(long v) { return (int)Math.Max(0, Math.Min(Max, v)); }

        /// <summary>POST /api/pushup {action, value?}</summary>
        public static JObject Mod(JObject b)
        {
            int? v = null; try { if (b != null && b["value"] != null && b["value"].Type != JTokenType.Null) v = (int)Math.Round((double)b["value"]); } catch (Exception) { return Err("value must be a number"); }
            return Apply(b == null ? "" : (string)b["action"], v);
        }

        static readonly string[] AddWords = { "add", "plus", "+", "up", "inc", "done", "did" };
        static readonly string[] RemoveWords = { "remove", "minus", "-", "sub", "down", "dec", "undo" };

        public static void Handle(string user, string[] args, int role, Action<string> say)
        {
            string who = "@" + PlatformUsers.Shown(user) + " "; bool mod = role >= 3;
            string first = args.Length > 0 ? args[0].ToLowerInvariant() : "";
            string per = DayCounts.ParsePeriod(first);
            if (per != "" && (args.Length == 1 || !mod)) { var ps = State(); if (!(bool)ps["enabled"]) { if (mod) say(who + "Pushups are off (!pushup on)."); return; } say(who + PeriodLine(ps, per)); return; }   // !pushup today|week|month|all
            if (first == "" || !mod)
            {
                var s = State();
                if (!(bool)s["enabled"]) { if (mod) say(who + "Pushups are off (!pushup on)."); return; }
                if (first != "" && !mod) { say(who + "Only mods change the pushups. " + Line(s)); return; }
                say(who + Line(s)); return;
            }
            string action = ""; int? val = null; int n;
            if (first.Length > 1 && (first[0] == '+' || first[0] == '-') && int.TryParse(first.Substring(1), NumberStyles.None, CultureInfo.InvariantCulture, out n)) { action = first[0] == '+' ? "add" : "remove"; val = n; }
            else if (int.TryParse(first, NumberStyles.None, CultureInfo.InvariantCulture, out n)) { action = "add"; val = n; }
            else if (Array.IndexOf(AddWords, first) >= 0) action = "add";
            else if (Array.IndexOf(RemoveWords, first) >= 0) action = "remove";
            else if (first == "set" || first == "reset" || first == "on" || first == "off") action = first;
            else { say(who + "Mods: !pushup [today | week | month | all | +N | -N | N | set N | reset (today only) | on | off]"); return; }
            if (val == null && args.Length > 1 && int.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out n)) val = n;
            if (action == "set" && val == null) { say(who + "!pushup set <number>"); return; }
            ModAudit.Log(user, "mod", "!pushup", string.Join(" ", args));
            var r = Apply(action, val);
            if (action == "on") say(who + "Pushups are on. " + Line(r));
            else if (action == "off") say(who + "Pushups are off.");
            else if (action == "reset") say(who + "Pushups today reset. " + Line(r));
            else say(who + Line(r));
        }
    }
}
