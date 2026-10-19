using System;
using System.Collections.Concurrent;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    // Bot control: status + the settings the Suite shell shows (replaces opening Streamer.bot).
    public static partial class HostApi
    {
        class Def
        {
            public string File, Key, Label, Hint = ""; public double Min, Max, Step; public bool Bool;
            public Def(string f, string k, string l, double mn, double mx, double st, string h) { File = f; Key = k; Label = l; Min = mn; Max = mx; Step = st; Hint = h; }
            public Def(string f, string k, string l) { File = f; Key = k; Label = l; Bool = true; }
        }
        static readonly string[] BotIds = { "core", "chat", "helper" };
        static readonly string[] BotActions = { "PinguinoBot", "PinguinoChat", "PinguinoHelper" };
        static readonly string[] OwnFile = { null, "chat_settings.json", "helper_settings.json" };
        static readonly Def[][] Defs = {
            new Def[0],
            new[] { new Def("chat_settings.json", "RandomChance", "Chattiness (chance of chiming in unprompted)", 0, 0.02, 0.0005, "0 = only when addressed"),
                    new Def("chat_settings.json", "UserCooldownSec", "Reply cooldown per viewer (s)", 0, 60, 1, "lower = faster replies"),
                    new Def("chat_settings.json", "FactsInPrompt", "Lore depth (facts remembered per reply)", 0, 30, 1, "more = more personal, more tokens"),
                    new Def("chat_settings.json", "MaxCallsPerHour", "AI calls per hour (cost cap)", 0, 600, 10, "") },
            new[] { new Def("helper_settings.json", "UserCooldownSec", "Reply cooldown per viewer (s)", 0, 120, 1, "lower = faster replies"),
                    new Def("helper_settings.json", "InfoCooldownSec", "Info lookup cooldown (s)", 0, 60, 1, ""),
                    new Def("helper_settings.json", "MaxAiCallsPerHour", "AI calls per hour (cost cap)", 0, 200, 5, ""),
                    new Def("helper_settings.json", "UseAi", "Use AI for answers") } };

        // The bots' compiled defaults, shown when a key is missing from the settings file (a missing key must never look like 0).
        static readonly System.Collections.Generic.Dictionary<string, double> Dflt = new System.Collections.Generic.Dictionary<string, double> {
            { "RandomChance", 0.001 }, { "FactsInPrompt", 14 }, { "MaxCallsPerHour", 300 },
            { "chat:UserCooldownSec", 3 }, { "helper:UserCooldownSec", 30 }, { "InfoCooldownSec", 8 }, { "MaxAiCallsPerHour", 40 }, { "UseAi", 1 } };
        static double DefaultOf(Def d) { double r; return Dflt.TryGetValue(d.File.StartsWith("chat") ? "chat:" + d.Key : "helper:" + d.Key, out r) || Dflt.TryGetValue(d.Key, out r) ? r : 0; }

        static readonly ConcurrentDictionary<string, string[]> LastError = new ConcurrentDictionary<string, string[]>();
        static readonly ConcurrentDictionary<string, long> Runs = new ConcurrentDictionary<string, long>();
        static readonly ConcurrentDictionary<string, DateTime> LastRun = new ConcurrentDictionary<string, DateTime>();
        public static void NoteRun(string action) { if (action == null) return; Runs.AddOrUpdate(action, 1, (k, v) => v + 1); LastRun[action] = DateTime.UtcNow; }
        public static void NoteLog(string action, string level, string text)
        { text = text ?? ""; LastError[action ?? "host"] = new[] { DateTime.UtcNow.ToString("o"), level + ": " + (text.Length > 300 ? text.Substring(0, 300) : text) }; }

        static JObject LoadFile(string name) { try { var f = Path.Combine(DataDir, name); return File.Exists(f) ? JObject.Parse(File.ReadAllText(f)) : new JObject(); } catch (Exception) { return new JObject(); } }
        static void SaveFile(string name, JObject o)
        { var f = Path.Combine(DataDir, name); var tmp = f + ".tmp"; File.WriteAllText(tmp, o.ToString()); if (File.Exists(f)) File.Replace(tmp, f, null); else File.Move(tmp, f); }

        static JObject Bots()
        {
            var reg = LoadFile("bots.json"); var arr = new JArray();
            for (int i = 0; i < BotIds.Length; i++)
            {
                var b = reg["Bots"]?[BotIds[i]]; string act = (string)b?["Action"] ?? BotActions[i];
                string[] err; LastError.TryGetValue(act, out err); long runs; Runs.TryGetValue(act, out runs); DateTime lr; bool has = LastRun.TryGetValue(act, out lr);
                var set = new JArray();
                foreach (var d in Defs[i])
                {
                    var v = LoadFile(d.File)[d.Key];
                    set.Add(d.Bool ? new JObject { { "key", d.Key }, { "label", d.Label }, { "type", "bool" }, { "value", v != null ? (bool)v : DefaultOf(d) != 0 } }
                                   : new JObject { { "key", d.Key }, { "label", d.Label }, { "type", "num" }, { "min", d.Min }, { "max", d.Max }, { "step", d.Step }, { "hint", d.Hint }, { "value", v == null ? DefaultOf(d) : (double)v } });
                }
                arr.Add(new JObject {
                    { "id", BotIds[i] }, { "title", (string)b?["Title"] ?? BotActions[i] }, { "action", act },
                    { "enabled", b == null || (bool?)b["Enabled"] != false }, { "runs", runs },
                    { "lastRunAgoSec", has ? (int?)(DateTime.UtcNow - lr).TotalSeconds : null },
                    { "lastError", err == null ? null : err[1] },
                    { "lastErrorAgoSec", err == null ? null : (int?)(DateTime.UtcNow - DateTime.Parse(err[0]).ToUniversalTime()).TotalSeconds },
                    { "settings", set } });
            }
            string[] rerr; LastError.TryGetValue("PinguinoRouter", out rerr);
            return new JObject { { "ok", true }, { "bots", arr }, { "routerError", rerr == null ? null : rerr[1] }, { "note", "Changes apply within about 10 seconds." } };
        }

        static JObject SaveBot(JObject b)
        {
            string id = (string)b["id"]; int i = Array.IndexOf(BotIds, id);
            if (i < 0) return new JObject { { "ok", false }, { "error", "unknown bot" } };
            if (b["enabled"] != null)
            {
                bool on = (bool)b["enabled"]; var reg = LoadFile("bots.json");
                if (reg["Bots"]?[id] == null) return new JObject { { "ok", false }, { "error", "bots.json has no entry for " + id } };
                reg["Bots"][id]["Enabled"] = on; SaveFile("bots.json", reg);
                if (OwnFile[i] != null) { var f = LoadFile(OwnFile[i]); f["Enabled"] = on; SaveFile(OwnFile[i], f); }
            }
            var st = b["settings"] as JObject;
            if (st != null)
                foreach (var kv in st)
                {
                    var d = Array.Find(Defs[i], x => x.Key == kv.Key); if (d == null) return new JObject { { "ok", false }, { "error", "unknown setting " + kv.Key } };
                    var f = LoadFile(d.File);
                    if (d.Bool) f[d.Key] = (bool)kv.Value;
                    else { double v = Math.Max(d.Min, Math.Min(d.Max, (double)kv.Value)); f[d.Key] = d.Step >= 1 ? (JToken)(long)Math.Round(v) : (JToken)Math.Round(v, 4); }
                    SaveFile(d.File, f);
                }
            return new JObject { { "ok", true } };
        }
    }
}
