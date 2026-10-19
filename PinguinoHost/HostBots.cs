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
            public string File, Key, Label, Hint = "", TextDefault = ""; public double Min, Max, Step; public bool Bool, Text;
            public Def(string f, string k, string l, double mn, double mx, double st, string h) { File = f; Key = k; Label = l; Min = mn; Max = mx; Step = st; Hint = h; }
            public Def(string f, string k, string l) { File = f; Key = k; Label = l; Bool = true; }
            public Def(string f, string k, string l, string dflt, string h) { File = f; Key = k; Label = l; Text = true; TextDefault = dflt; Hint = h; }
        }
        static readonly string[] BotIds = { "core", "chat", "helper" };
        static readonly string[] BotActions = { "PinguinoBot", "PinguinoChat", "PinguinoHelper" };
        static readonly string[] OwnFile = { null, "chat_settings.json", "helper_settings.json" };
        static readonly Def[][] Defs = {
            new Def[0],
            new[] { new Def("chat_settings.json", "LiveOnly", "Only reply while the stream is live"),
                    new Def("chat_settings.json", "RandomChance", "Chattiness (chance of chiming in unprompted)", 0, 0.02, 0.0005, "0 = only when addressed"),
                    new Def("chat_settings.json", "UserCooldownSec", "Reply cooldown per viewer (s)", 0, 60, 1, "lower = faster replies"),
                    new Def("chat_settings.json", "FactsInPrompt", "Lore depth (facts remembered per reply)", 0, 30, 1, "more = more personal, more tokens"),
                    new Def("chat_settings.json", "MaxCallsPerHour", "AI calls per hour (cost cap)", 0, 600, 10, ""),
                    new Def("chat_settings.json", "GateEnabled", "Activity gate: only talk when chat allows it"),
                    new Def("chat_settings.json", "GateQuietPerMin", "Quiet: may chime in at or below (chat lines/min)", 0, 200, 1, "example 5-10"),
                    new Def("chat_settings.json", "GateBusyPerMin", "Busy: completely silent at or above (lines/min)", 1, 500, 1, "example 50"),
                    new Def("chat_settings.json", "GateWindowSec", "Gate: counting window (s)", 10, 300, 5, "60 = last minute"),
                    new Def("chat_settings.json", "GateHysteresisPct", "Gate: margin before it switches back (%)", 0, 50, 1, "stops flapping"),
                    new Def("chat_settings.json", "GateBusyBlocksReplies", "Busy also stops answers to @mentions"),
                    new Def("chat_settings.json", "GateAuto", "Auto limits from recorded streams (instead of the fixed numbers)"),
                    new Def("chat_settings.json", "GateAutoQuietPct", "Auto: quiet = % of the average chat rate", 5, 100, 5, "e.g. 40"),
                    new Def("chat_settings.json", "GateAutoBusyPct", "Auto: busy = % of the average chat rate", 110, 1000, 10, "e.g. 250"),
                    new Def("chat_settings.json", "GateAutoMinMinutes", "Auto needs this many recorded stream minutes", 10, 3000, 10, "falls back to the fixed numbers before that"),
                    new Def("chat_settings.json", "RandomMinGapSec", "Min seconds between unprompted chime-ins", 0, 3600, 30, "cooldown"),
                    new Def("chat_settings.json", "CountdownEnabled", "Pre-stream countdown"),
                    new Def("chat_settings.json", "CountdownGoLiveAt", "Daily go-live time (HH:MM, this PC's clock)", "", "empty = no countdown"),
                    new Def("chat_settings.json", "CountdownOverrideAt", "One-off go-live (HH:MM or yyyy-MM-dd HH:mm)", "", "mods can set it in chat: !golive 17:30"),
                    new Def("chat_settings.json", "CountdownTimes", "Countdown at (before start)", "15m,10m,5m,1m,30s", "m = minutes, s = seconds, comma separated"),
                    new Def("chat_settings.json", "CountdownLine", "Countdown wording", "Stream starts in {left}! Grab a snack and get comfy.", "{left} = 15 minutes, {time} = start time"),
                    new Def("chat_settings.json", "CountdownLineNow", "Wording at the start time", "", "empty = nothing") },
            new[] { new Def("helper_settings.json", "LiveOnly", "Only reply while the stream is live"),
                    new Def("helper_settings.json", "UserCooldownSec", "Reply cooldown per viewer (s)", 0, 120, 1, "lower = faster replies"),
                    new Def("helper_settings.json", "InfoCooldownSec", "Info lookup cooldown (s)", 0, 60, 1, ""),
                    new Def("helper_settings.json", "MaxAiCallsPerHour", "AI calls per hour (cost cap)", 0, 200, 5, ""),
                    new Def("helper_settings.json", "UseAi", "Use AI for answers") } };

        // The bots' compiled defaults, shown when a key is missing from the settings file (a missing key must never look like 0).
        static readonly System.Collections.Generic.Dictionary<string, double> Dflt = new System.Collections.Generic.Dictionary<string, double> {
            { "RandomMinGapSec", 600 }, { "GateEnabled", 1 }, { "GateAutoQuietPct", 40 }, { "GateAutoBusyPct", 250 }, { "GateAutoMinMinutes", 120 }, { "GateQuietPerMin", 10 }, { "GateBusyPerMin", 50 }, { "GateWindowSec", 60 }, { "GateHysteresisPct", 20 }, { "GateBusyBlocksReplies", 1 }, { "CountdownEnabled", 1 },
            { "RandomChance", 0.001 }, { "FactsInPrompt", 14 }, { "MaxCallsPerHour", 300 },
            { "chat:UserCooldownSec", 3 }, { "helper:UserCooldownSec", 30 }, { "InfoCooldownSec", 8 }, { "MaxAiCallsPerHour", 40 }, { "UseAi", 1 }, { "LiveOnly", 1 } };
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
                    if (d.Text) { set.Add(new JObject { { "key", d.Key }, { "label", d.Label }, { "type", "text" }, { "hint", d.Hint }, { "value", v == null ? d.TextDefault : (string)v } }); continue; }
                    set.Add(d.Bool ? new JObject { { "key", d.Key }, { "label", d.Label }, { "type", "bool" }, { "value", v != null ? (bool)v : DefaultOf(d) != 0 } }
                                   : new JObject { { "key", d.Key }, { "label", d.Label }, { "type", "num" }, { "min", d.Min }, { "max", d.Max }, { "step", d.Step }, { "hint", d.Hint }, { "value", v == null ? DefaultOf(d) : (double)v } });
                }
                var sec = BotSecretsV()[BotIds[i]] as JObject; bool signedIn = sec != null && !string.IsNullOrEmpty((string)sec["UserToken"]);
                bool enabled = b == null || (bool?)b["Enabled"] != false;
                string health = "pass", hdetail = "";
                if (!enabled) { health = "warn"; hdetail = "switched off"; }
                else if (!signedIn && BotIds[i] == "core") { health = "fail"; hdetail = "not signed in"; }
                else if (!signedIn) { health = "warn"; hdetail = "no login of its own: PinguinoB0t speaks for it"; }
                if (err != null && DateTime.UtcNow - DateTime.Parse(err[0]).ToUniversalTime() < TimeSpan.FromMinutes(30)) { health = health == "fail" ? "fail" : "warn"; hdetail = (hdetail == "" ? "" : hdetail + "; ") + err[1]; }
                var cmds = new JArray();
                if (BotIds[i] == "core") foreach (var c in Program.CoreCommandList()) cmds.Add(c);
                else if (BotIds[i] == "chat") foreach (var c in new[] { "@ it or say its name", "!forgetme", "!rememberme", "!memory", "!chatbot on|off (mods)" }) cmds.Add(c);
                else foreach (var c in new[] { "how do I join", "minecraft ip / ip", "!discord", "lobby code / password", "register" }) cmds.Add(c);
                arr.Add(new JObject {
                    { "signedIn", signedIn }, { "signedInAs", (string)sec?["Login"] ?? "" }, { "health", health }, { "healthDetail", hdetail }, { "commands", cmds },
                    { "id", BotIds[i] }, { "title", (string)b?["Title"] ?? BotActions[i] }, { "action", act },
                    { "account", (string)b?["Account"] ?? "" }, { "sender", (string)b?["Sender"] ?? "streamerbot" },
                    { "enabled", b == null || (bool?)b["Enabled"] != false }, { "runs", runs },
                    { "lastRunAgoSec", has ? (int?)(DateTime.UtcNow - lr).TotalSeconds : null },
                    { "lastError", err == null ? null : err[1] },
                    { "lastErrorAgoSec", err == null ? null : (int?)(DateTime.UtcNow - DateTime.Parse(err[0]).ToUniversalTime()).TotalSeconds },
                    { "settings", set } });
            }
            string[] rerr; LastError.TryGetValue("PinguinoRouter", out rerr);
            return new JObject { { "ok", true }, { "bots", arr }, { "routerError", rerr == null ? null : rerr[1] }, { "note", "Changes apply within about 10 seconds." } };
        }

        // "Send test": the bot says one line in chat so you can see which account actually speaks for it (its own, or the first bot in its fallback chain that has one).
        static JObject BotTest(JObject b)
        {
            string id = (string)b["id"]; if (Array.IndexOf(BotIds, id) < 0) return new JObject { { "ok", false }, { "error", "unknown bot" } };
            var reg = LoadFile("bots.json"); var sec = BotSecretsV();
            string title = (string)reg["Bots"]?[id]?["Title"] ?? id;
            var chain = new System.Collections.Generic.List<string> { id };
            if (reg["Fallback"]?[id] is JArray fb) foreach (var x in fb) chain.Add((string)x);
            foreach (string r in chain)
            {
                var bot = reg["Bots"]?[r]; var s = sec[r] as JObject;
                if (bot == null || (bool?)bot["Enabled"] == false || s == null || string.IsNullOrEmpty((string)bot["Account"]) || ((string)bot["Sender"] ?? "") != "helix") continue;
                string tok = (string)s["UserToken"], cid = (string)s["ClientId"], sid = (string)s["SenderId"], bid = (string)s["BroadcasterId"];
                if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid) || string.IsNullOrEmpty(sid) || string.IsNullOrEmpty(bid)) continue;
                using (var http = new System.Net.Http.HttpClient())
                {
                    var rq = new System.Net.Http.HttpRequestMessage(System.Net.Http.HttpMethod.Post, Helix + "/chat/messages");
                    rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                    string who = (string)bot["Account"];
                    string text = "[test] " + title + " is working" + (r == id ? "." : " (speaking through " + (string)bot["Title"] + ").");
                    rq.Content = new System.Net.Http.StringContent(new JObject { { "broadcaster_id", bid }, { "sender_id", sid }, { "message", text } }.ToString(), System.Text.Encoding.UTF8, "application/json");
                    var resp = http.SendAsync(rq).Result;
                    if (resp.IsSuccessStatusCode) return new JObject { { "ok", true }, { "speaker", who }, { "own", r == id }, { "note", (r == id ? title + " spoke as " : title + " has no account of its own, so " + (string)bot["Title"] + " spoke as ") + who + "." } };
                    return new JObject { { "ok", false }, { "error", "Twitch refused the message from " + who + " (" + (int)resp.StatusCode + "). Sign that account in again." } };
                }
            }
            bool ok = Program.SayShared("[test] " + title + " is working (shared account).");
            return ok ? new JObject { { "ok", true }, { "speaker", "shared account" }, { "own", false }, { "note", title + " has no account yet, so the shared account spoke." } }
                      : new JObject { { "ok", false }, { "error", "No account could speak. Sign in first." } };
        }

        public static JObject SetBotEnabled(string id, bool on) { return SaveBot(new JObject { { "id", id }, { "enabled", on } }); }
        public static JObject BotsSnapshot() { return Bots(); }
        public static JObject StatusSnapshot() { return Status(); }
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
                    if (d.Text) f[d.Key] = ((string)kv.Value ?? "").Trim();
                    else if (d.Bool) f[d.Key] = (bool)kv.Value;
                    else { double v = Math.Max(d.Min, Math.Min(d.Max, (double)kv.Value)); f[d.Key] = d.Step >= 1 ? (JToken)(long)Math.Round(v) : (JToken)Math.Round(v, 4); }
                    SaveFile(d.File, f);
                }
            return new JObject { { "ok", true } };
        }
    }
}
