using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Management surface for the shell (Quick actions, variables, triggers, hotkeys, export, pause): everything Streamer.bot's side panels showed.</summary>
    public static partial class Auto
    {
        static int _waiting; static bool _paused;
        static readonly Dictionary<string, string> _running = new Dictionary<string, string>();
        static readonly Dictionary<string, long> _fires = new Dictionary<string, long>(); static readonly Dictionary<string, DateTime> _last = new Dictionary<string, DateTime>();
        static readonly Dictionary<string, JObject> _varMeta = new Dictionary<string, JObject>();
        public static bool Paused { get { return _paused; } }
        public static bool Has(string idOrName) { return FindAction(idOrName) != null; }

        static void NoteFire(string id) { lock (L) { long n; _fires.TryGetValue(id, out n); _fires[id] = n + 1; _last[id] = DateTime.UtcNow; } }

        static string Display(JObject t)
        {
            switch (((string)t["type"] ?? "").ToLowerInvariant())
            {
                case "command": return string.Join(", ", (t["names"] as JArray ?? new JArray()).Select(n => (string)n));
                case "redeem": return (string)t["title"] ?? "*";
                case "hotkey": return (string)t["key"] ?? "";
                case "timer": return "every " + ((int?)t["everySec"] ?? 0) + " s";
                case "chat": return (string)t["pattern"] ?? "";
                case "sub": return "tier " + ((string)t["tier"] ?? "any");
                case "cheer": return ((int?)t["min"] ?? -1) < 0 ? "any amount" : "at least " + (int)t["min"] + " bits";
                case "raid": case "gift": return ((int?)t["min"] ?? -1) < 0 ? "any size" : "at least " + (int)t["min"];
                default: return "";
            }
        }
        /// <summary>every trigger of every action, with last-fired time, fire count and cooldown settings.</summary>
        public static JObject TriggerList()
        {
            var rows = new JArray();
            foreach (var a in ((JArray)Doc()["actions"]).OfType<JObject>())
            {
                string id = (string)a["id"]; long n; DateTime last; bool has; lock (L) { _fires.TryGetValue(id, out n); has = _last.TryGetValue(id, out last); }
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                    rows.Add(new JObject { { "actionId", id }, { "action", a["name"] }, { "group", a["group"] }, { "enabled", (bool?)a["enabled"] != false }, { "type", t["type"] }, { "display", Display(t) },
                        { "permission", t["permission"] }, { "cooldownSec", t["cooldownSec"] ?? 0 }, { "userCooldownSec", t["userCooldownSec"] ?? 0 }, { "fires", n }, { "lastFiredAgoSec", has ? (int?)(DateTime.UtcNow - last).TotalSeconds : null } });
            }
            return new JObject { { "ok", true }, { "triggers", rows } };
        }
        public static JObject HotkeyList()
        {
            var rows = new JArray();
            foreach (var a in ((JArray)Doc()["actions"]).OfType<JObject>())
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>().Where(t => string.Equals((string)t["type"], "hotkey", StringComparison.OrdinalIgnoreCase)))
                    rows.Add(new JObject { { "hotkey", t["key"] }, { "action", a["name"] }, { "actionId", a["id"] }, { "enabled", (bool?)a["enabled"] != false } });
            return new JObject { { "ok", true }, { "hotkeys", rows }, { "how", "POST /api/automations/fire {\"hotkey\":\"name\"}" } };
        }
        public static JObject Enable(string id, string group, bool on)
        {
            var doc = Doc(); int n = 0;
            foreach (var a in ((JArray)doc["actions"]).OfType<JObject>().Where(a => (id != null && (string)a["id"] == id) || (group != null && string.Equals((string)a["group"], group, StringComparison.OrdinalIgnoreCase)))) { a["enabled"] = on; n++; }
            if (n == 0) return new JObject { { "ok", false }, { "error", "no such action or group" } };
            string err = Save(doc); return err == null ? new JObject { { "ok", true }, { "changed", n } } : new JObject { { "ok", false }, { "error", err } };
        }
        public static JObject Export() { return new JObject { { "ok", true }, { "doc", Doc() }, { "vars", Vars() }, { "exportedAt", DateTime.UtcNow.ToString("o") } }; }

        // ---- variables ----
        public static JObject VarList()
        {
            var rows = new JArray();
            lock (L) foreach (var p in Vars().Properties()) { JObject m; _varMeta.TryGetValue(p.Name, out m); rows.Add(new JObject { { "name", p.Name }, { "value", (string)p.Value }, { "persist", (bool?)m?["persist"] ?? true }, { "updated", m?["updated"] } }); }
            return new JObject { { "ok", true }, { "vars", rows } };
        }
        public static JObject VarSet(string name, string value, bool persist)
        {
            if (string.IsNullOrWhiteSpace(name)) return new JObject { { "ok", false }, { "error", "name required" } };
            SetVar(name.Trim(), value ?? "", true); lock (L) _varMeta[name.Trim()] = new JObject { { "persist", persist }, { "updated", DateTime.UtcNow.ToString("o") } };
            return new JObject { { "ok", true } };
        }
        public static JObject VarDelete(string name)
        {
            lock (L) { if (Vars().Remove(name)) { try { System.IO.File.WriteAllText(VarsPath, Vars().ToString()); } catch (Exception) { } _varMeta.Remove(name); return new JObject { { "ok", true } }; } }
            return new JObject { { "ok", false }, { "error", "no such variable" } };
        }
        // ---- run queue / pause ----
        public static JObject QueueState()
        {
            lock (L) return new JObject { { "ok", true }, { "queues", new JArray { new JObject { { "name", "actions" }, { "paused", _paused }, { "blocking", false }, { "length", _waiting },
                { "items", new JArray(_running.Select(r => new JObject { { "id", r.Key }, { "action", r.Value }, { "args", "" }, { "age", 0 }, { "state", "running" } })) } } } },
                { "note", "each action runs one at a time; a second trigger of the same action waits (length = how many wait). Pause stops new automatic runs; Test and Run buttons still work." } };
        }
        public static JObject QueueControl(string cmd)
        {
            switch (cmd) { case "pause": _paused = true; break; case "resume": _paused = false; break; case "clear": break; default: return new JObject { { "ok", false }, { "error", "use pause, resume or clear" } }; }
            Clog.Info("automation", "automations " + (cmd == "clear" ? "queue cleared (nothing waits to be cleared: runs are immediate)" : cmd == "pause" ? "PAUSED (no automatic runs)" : "resumed")); return QueueState();
        }
        public static JObject Endpoints()
        {
            string b = "http://127.0.0.1:" + HostApi.Port;
            return new JObject { { "ok", true }, { "base", b }, { "auth", "Calls from this PC need no key for GET. POST needs the Suite app/module token (Authorization: Bearer ...) or the same origin; the token is never shown here: take it from Settings." }, { "endpoints", new JArray {
                new JObject { { "method", "POST" }, { "url", b + "/api/automations/fire" }, { "body", "{\"hotkey\":\"brb\"}" }, { "for", "Stream Deck / buttons: runs every action with that Hotkey trigger" } },
                new JObject { { "method", "POST" }, { "url", b + "/api/automations/test" }, { "body", "{\"id\":\"<action id>\",\"dry\":false,\"args\":{\"user\":\"Name\"}}" }, { "for", "run one action now (dry:true only shows what it would do)" } },
                new JObject { { "method", "POST" }, { "url", b + "/api/automations/enable" }, { "body", "{\"id\":\"<action id>\",\"on\":true} or {\"group\":\"Spotify\",\"on\":false}" }, { "for", "switch an action or a whole group on/off" } },
                new JObject { { "method", "GET" }, { "url", b + "/api/activity?since=0" }, { "for", "events feed (follows, subs, cheers ...)" } },
                new JObject { { "method", "POST" }, { "url", b + "/api/shoutouts" }, { "body", "{\"user\":\"name\"}" }, { "for", "queue a shoutout" } },
                new JObject { { "method", "GET" }, { "url", b + "/overlay/latest" }, { "for", "OBS browser source: latest follower / sub / cheer / raid" } },
                new JObject { { "method", "POST" }, { "url", b + "/api/cutover" }, { "body", "{\"on\":true}" }, { "for", "switch the Streamer.bot replacements on/off" } } } } };
        }
    }
}
