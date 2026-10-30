using System;
using System.Globalization;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The pushup counter: !pushup / !pushups / !pu. Anyone reads the count; only mods change it (add, remove, set N, reset, on, off). The count and the enabled flag live in Data\runtime\pushups.json (atomic write)
    /// and survive restarts; GET /api/pushup {enabled,count} feeds the pushup widget, POST /api/pushup {action,value} is the Master View write route (same gating as /api/customs/mod).</summary>
    public static class Pushups
    {
        static readonly object L = new object();
        static bool _loaded, _enabled = true; static int _count;
        const int Max = 100000, MaxStep = 1000;
        static string FilePath { get { return Path.Combine(HostApi.DataDir, "pushups.json"); } }

        public static bool IsCommand(string cmd) { return cmd == "!pushup" || cmd == "!pushups" || cmd == "!pu"; }

        static void Load()
        {
            if (_loaded) return;
            _loaded = true;
            try
            {
                if (!File.Exists(FilePath)) return;
                var o = JObject.Parse(File.ReadAllText(FilePath).TrimStart((char)0xFEFF));
                _enabled = (bool?)o["enabled"] ?? true; _count = Math.Max(0, Math.Min(Max, (int?)o["count"] ?? 0));
            }
            catch (Exception ex) { Clog.Warn("pushup", "pushups.json: " + ex.Message); }
        }
        static void Save()
        {
            try
            {
                string f = FilePath, tmp = f + ".tmp"; Directory.CreateDirectory(Path.GetDirectoryName(f));
                File.WriteAllText(tmp, new JObject { { "enabled", _enabled }, { "count", _count } }.ToString());
                if (File.Exists(f)) File.Delete(f); File.Move(tmp, f);
            }
            catch (Exception ex) { Clog.Warn("pushup", "could not save pushups.json: " + ex.Message); }
        }

        public static JObject State() { lock (L) { Load(); return new JObject { { "enabled", _enabled }, { "count", _count } }; } }

        /// <summary>one change: add|remove|set|reset|on|off; value is the amount (add / remove default 1, set needs it). Returns the new state plus ok / error.</summary>
        public static JObject Apply(string action, int? value)
        {
            lock (L)
            {
                Load(); string a = (action ?? "").Trim().ToLowerInvariant();
                switch (a)
                {
                    case "add": _count = Clamp((long)_count + Step(value)); break;
                    case "remove": _count = Clamp((long)_count - Step(value)); break;
                    case "set": if (value == null) return Err("set needs a number"); _count = Clamp(value.Value); break;
                    case "reset": _count = 0; break;
                    case "on": _enabled = true; break;
                    case "off": _enabled = false; break;
                    default: return Err("unknown action (add, remove, set, reset, on, off)");
                }
                Save();
                return new JObject { { "ok", true }, { "enabled", _enabled }, { "count", _count } };
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
            if (first == "" || !mod)
            {
                var s = State();
                if (!(bool)s["enabled"]) { if (mod) say(who + "Pushups are off (!pushup on)."); return; }
                if (first != "" && !mod) { say(who + "Only mods change the pushups. Pushups: " + (int)s["count"]); return; }
                say(who + "Pushups: " + (int)s["count"]); return;
            }
            string action = ""; int? val = null; int n;
            if (first.Length > 1 && (first[0] == '+' || first[0] == '-') && int.TryParse(first.Substring(1), NumberStyles.None, CultureInfo.InvariantCulture, out n)) { action = first[0] == '+' ? "add" : "remove"; val = n; }
            else if (int.TryParse(first, NumberStyles.None, CultureInfo.InvariantCulture, out n)) { action = "add"; val = n; }
            else if (Array.IndexOf(AddWords, first) >= 0) action = "add";
            else if (Array.IndexOf(RemoveWords, first) >= 0) action = "remove";
            else if (first == "set" || first == "reset" || first == "on" || first == "off") action = first;
            else { say(who + "Mods: !pushup [+N | -N | N | set N | reset | on | off]"); return; }
            if (val == null && args.Length > 1 && int.TryParse(args[1], NumberStyles.None, CultureInfo.InvariantCulture, out n)) val = n;
            if (action == "set" && val == null) { say(who + "!pushup set <number>"); return; }
            ModAudit.Log(user, "mod", "!pushup", string.Join(" ", args));
            var r = Apply(action, val);
            if (action == "on") say(who + "Pushups are on. Pushups: " + (int)r["count"]);
            else if (action == "off") say(who + "Pushups are off.");
            else say(who + "Pushups: " + (int)r["count"]);
        }
    }
}
