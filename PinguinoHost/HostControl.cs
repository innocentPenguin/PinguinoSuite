using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Channel-control chat commands (Plan 5): polls, predictions, chat settings, announcements, shield mode, markers, ads, VIPs and the guarded raid.
    /// Everything is behind the master switch Data\config\control.json {"enabled":false}. Mod-tier commands live in the mod list only. Every use is appended to Data\runtime\control_log.jsonl.
    /// RAIDS are never automatic: only the broadcaster, only a name from Data\config\raid_list.json, two steps (!raid name, then !confirm raid within 20 s), and the confirm is refused
    /// when the line did not come from real Twitch chat (Stream Deck, /api/run, voice, timers can only open the request).</summary>
    public static class Control
    {
        [ThreadStatic] public static bool Synthetic;   // set around Dispatch calls that do not come from Twitch chat
        static readonly string[] Cmds = { "!poll", "!predict", "!lock", "!resolve", "!cancel", "!slow", "!emote-only", "!emoteonly", "!followers", "!subs-only", "!subsonly", "!announce", "!title", "!game", "!shield", "!marker", "!ad", "!vip", "!unvip", "!raid", "!confirm", "!unraid" };
        public static bool IsCommand(string cmd) { return Cmds.Contains(cmd); }
        static string CfgP { get { return Path.Combine(HostApi.DataDir, "config", "control.json"); } }
        static string RaidP { get { return Path.Combine(HostApi.DataDir, "config", "raid_list.json"); } }
        static string LogP { get { return Path.Combine(HostApi.DataDir, "runtime", "control_log.jsonl"); } }
        static readonly object L = new object();

        static JObject Cfg()
        {
            try { if (File.Exists(CfgP)) return JObject.Parse(File.ReadAllText(CfgP).TrimStart((char)0xFEFF)); } catch (Exception) { }
            try { Directory.CreateDirectory(Path.GetDirectoryName(CfgP)); File.WriteAllText(CfgP, new JObject { { "note", "master switch for the channel-control chat commands. Set enabled to true to use them. predictMods = mods allowed to run predictions besides the broadcaster." }, { "enabled", false }, { "predictMods", new JArray() } }.ToString()); } catch (Exception) { }
            return new JObject { { "enabled", false } };
        }
        public static bool Enabled { get { return (bool?)Cfg()["enabled"] == true; } }
        static List<string> RaidList()
        {
            try
            {
                if (!File.Exists(RaidP)) { Directory.CreateDirectory(Path.GetDirectoryName(RaidP)); File.WriteAllText(RaidP, new JObject { { "note", "Ivan-owned list of channels the bot may raid after !raid <name> and !confirm raid. Edit by hand." }, { "names", new JArray("patfromearth") } }.ToString()); }
                return ((JArray)JObject.Parse(File.ReadAllText(RaidP).TrimStart((char)0xFEFF))["names"] ?? new JArray()).Select(x => ((string)x ?? "").Trim().TrimStart('@').ToLowerInvariant()).Where(x => x != "").ToList();
            }
            catch (Exception) { return new List<string>(); }
        }
        static void Log(string user, string cmd, string args, string result)
        {
            try { lock (L) { Directory.CreateDirectory(Path.GetDirectoryName(LogP)); File.AppendAllText(LogP, new JObject { { "ts", DateTime.UtcNow.ToString("o") }, { "user", user }, { "cmd", cmd }, { "args", args }, { "synthetic", Synthetic }, { "result", result } }.ToString(Newtonsoft.Json.Formatting.None) + "\n"); } } catch (Exception) { }
        }

        static double CoolSec() { double v; return double.TryParse(Environment.GetEnvironmentVariable("PINGUINO_CONTROL_COOL"), out v) ? v : 2; }
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();
        static bool Cooling(string key, double sec) { lock (L) { DateTime t; if (Cool.TryGetValue(key, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; Cool[key] = DateTime.UtcNow; return false; } }

        // raid request
        static string _raidName = ""; static DateTime _raidAt = DateTime.MinValue; static DateTime _raidStarted = DateTime.MinValue;

        static string Call(HttpMethod m, string path, JObject body, out JToken data)
        {
            string err; var code = TwitchApi.Call(m, path, body, out data, out err);
            return err != "" ? "!" + err : code;
        }
        static string Mod { get { return TwitchApi.BroadcasterId(); } }
        static bool Ok(string r) { return r.Length > 0 && r[0] != '!' && (r == "200" || r == "201" || r == "202" || r == "204"); }
        static string Why(string r) { return r.StartsWith("!") ? r.Substring(1) : "Twitch answered HTTP " + r; }

        public static bool Handle(string user, string cmd, string[] args, int role, Action<string> say)
        {
            bool mod = role >= 3, owner = role >= 4;
            if (!mod) return true;                                   // viewers get nothing (the word may belong to another bot)
            if (!Enabled) { say("Channel control is switched off (Data\\config\\control.json)."); return true; }
            if (Cooling("c|" + cmd, CoolSec())) return true;
            string a = string.Join(" ", args), res = "";
            try
            {
                switch (cmd)
                {
                    case "!poll": res = Poll(args, a, say); break;
                    case "!predict": case "!lock": case "!resolve": case "!cancel":
                        if (!(owner || ((JArray)Cfg()["predictMods"] ?? new JArray()).Any(x => string.Equals((string)x, user, StringComparison.OrdinalIgnoreCase)))) { res = "refused: not allowed"; say("Predictions are for the streamer and mods they allow."); break; }
                        res = Prediction(cmd, args, a, say); break;
                    case "!slow": res = Settings("slow", args, say); break;
                    case "!emote-only": case "!emoteonly": res = Settings("emote", args, say); break;
                    case "!followers": res = Settings("followers", args, say); break;
                    case "!subs-only": case "!subsonly": res = Settings("subs", args, say); break;
                    case "!announce": res = Announce(args, say); break;
                    case "!title": case "!game": res = Retitle(cmd == "!title", a, say); break;
                    case "!marker": res = Marker(a, say); break;
                    case "!shield": if (!owner) { res = "refused: broadcaster only"; break; } res = Shield(args, say); break;
                    case "!ad": if (!owner) { res = "refused: broadcaster only"; break; } res = Ad(args, say); break;
                    case "!vip": case "!unvip": if (!owner) { res = "refused: broadcaster only"; break; } res = Vip(cmd == "!vip", args, say); break;
                    case "!raid": case "!confirm": case "!unraid":
                        if (!owner) { res = "refused: broadcaster only"; break; }
                        res = Raid(cmd, args, say); break;
                }
            }
            catch (Exception ex) { res = "error: " + ex.Message; say("That did not work: " + ex.Message); }
            Log(user, cmd, a, res);
            return true;
        }

        // ---- polls ----
        static List<string> Quoted(string a, out string rest)
        {
            var m = Regex.Match(a, "^\\s*[\"“](.+?)[\"”]\\s*(.*)$"); rest = a; var r = new List<string>();
            if (!m.Success) return r;
            r.Add(m.Groups[1].Value.Trim()); rest = m.Groups[2].Value.Trim(); return r;
        }
        static string Clip(string s, int n) { s = (s ?? "").Trim(); return s.Length > n ? s.Substring(0, n) : s; }
        static string Poll(string[] args, string a, Action<string> say)
        {
            string rest; var q = Quoted(a, out rest);
            if (q.Count == 0) { say("Use: !poll \"question\" option1|option2|option3 [seconds]"); return "usage"; }
            int dur = 60; var m = Regex.Match(rest, "^(.*?)\\s+(\\d{2,4})$"); if (m.Success) { rest = m.Groups[1].Value; dur = int.Parse(m.Groups[2].Value); }
            dur = Math.Max(15, Math.Min(1800, dur));
            var choices = rest.Split('|').Select(x => Clip(x, 25)).Where(x => x != "").ToList();
            if (choices.Count < 2 || choices.Count > 5) { say("A poll needs 2 to 5 options separated by |"); return "usage"; }
            JToken d; var r = Call(HttpMethod.Post, "/polls", new JObject { { "broadcaster_id", TwitchApi.BroadcasterId() }, { "title", Clip(q[0], 60) }, { "choices", new JArray(choices.Select(c => new JObject { { "title", c } })) }, { "duration", dur } }, out d);
            if (!Ok(r)) { say("Could not start the poll: " + Why(r)); return Why(r); }
            say("Poll started: " + Clip(q[0], 60) + " (" + dur + "s). Vote in the poll box!"); return "ok";
        }

        // ---- predictions ----
        static string Prediction(string cmd, string[] args, string a, Action<string> say)
        {
            JToken d;
            if (cmd == "!predict")
            {
                string rest; var q = Quoted(a, out rest);
                if (q.Count == 0) { say("Use: !predict \"question\" outcome1|outcome2 [seconds]"); return "usage"; }
                int win = 120; var m = Regex.Match(rest, "^(.*?)\\s+(\\d{2,4})$"); if (m.Success) { rest = m.Groups[1].Value; win = int.Parse(m.Groups[2].Value); }
                win = Math.Max(30, Math.Min(1800, win));
                var outs = rest.Split('|').Select(x => Clip(x, 25)).Where(x => x != "").ToList();
                if (outs.Count < 2 || outs.Count > 10) { say("A prediction needs 2 to 10 outcomes separated by |"); return "usage"; }
                var r0 = Call(HttpMethod.Post, "/predictions", new JObject { { "broadcaster_id", TwitchApi.BroadcasterId() }, { "title", Clip(q[0], 45) }, { "outcomes", new JArray(outs.Select(c => new JObject { { "title", c } })) }, { "prediction_window", win } }, out d);
                if (!Ok(r0)) { say("Could not start the prediction: " + Why(r0)); return Why(r0); }
                say("Prediction open for " + win + "s: " + Clip(q[0], 45)); return "ok";
            }
            var g = Call(HttpMethod.Get, "/predictions?broadcaster_id={bid}&first=1", null, out d);
            var cur = (d as JArray)?.FirstOrDefault() as JObject;
            if (!Ok(g) || cur == null) { say("There is no prediction to change."); return "none"; }
            string id = (string)cur["id"], status = ((string)cur["status"] ?? "").ToUpperInvariant();
            if (status == "RESOLVED" || status == "CANCELED") { say("There is no active prediction."); return "none"; }
            if (cmd == "!lock")
            {
                var r1 = Call(new HttpMethod("PATCH"), "/predictions", new JObject { { "broadcaster_id", TwitchApi.BroadcasterId() }, { "id", id }, { "status", "LOCKED" } }, out d);
                say(Ok(r1) ? "Prediction locked. No more votes." : "Could not lock it: " + Why(r1)); return Ok(r1) ? "ok" : Why(r1);
            }
            if (cmd == "!cancel")
            {
                var r2 = Call(new HttpMethod("PATCH"), "/predictions", new JObject { { "broadcaster_id", TwitchApi.BroadcasterId() }, { "id", id }, { "status", "CANCELED" } }, out d);
                say(Ok(r2) ? "Prediction cancelled, points refunded." : "Could not cancel it: " + Why(r2)); return Ok(r2) ? "ok" : Why(r2);
            }
            var outcomes = (cur["outcomes"] as JArray) ?? new JArray(); if (a.Trim() == "") { say("Use: !resolve <outcome number or name>"); return "usage"; }
            JToken pick = null; int n;
            if (int.TryParse(a.Trim(), out n) && n >= 1 && n <= outcomes.Count) pick = outcomes[n - 1];
            else { var hits = outcomes.Where(o => ((string)o["title"] ?? "").StartsWith(a.Trim(), StringComparison.OrdinalIgnoreCase)).ToList(); if (hits.Count == 1) pick = hits[0]; }
            if (pick == null) { say("Which outcome? " + string.Join(", ", outcomes.Select((o, i) => (i + 1) + "=" + (string)o["title"]))); return "ambiguous"; }
            var r3 = Call(new HttpMethod("PATCH"), "/predictions", new JObject { { "broadcaster_id", TwitchApi.BroadcasterId() }, { "id", id }, { "status", "RESOLVED" }, { "winning_outcome_id", (string)pick["id"] } }, out d);
            if (!Ok(r3)) { say("Could not resolve it: " + Why(r3)); return Why(r3); }
            return "ok";   // the result line comes from the EventSub end event (OnEvent)
        }

        // ---- chat settings ----
        static string Settings(string what, string[] args, Action<string> say)
        {
            string w = args.Length > 0 ? args[0].ToLowerInvariant() : ""; var b = new JObject(); string line;
            bool off = w == "off" || w == "0" || w == "false";
            switch (what)
            {
                case "slow": { int s; if (off) { b["slow_mode"] = false; line = "Slow mode off."; } else { s = 30; if (w != "" && !int.TryParse(w, out s)) { say("Use: !slow [seconds 3-120|off]"); return "usage"; } s = Math.Max(3, Math.Min(120, s)); b["slow_mode"] = true; b["slow_mode_wait_time"] = s; line = "Slow mode: one message every " + s + "s."; } break; }
                case "emote": if (off) { b["emote_mode"] = false; line = "Emote-only off."; } else { b["emote_mode"] = true; line = "Emote-only on."; } break;
                case "subs": if (off) { b["subscriber_mode"] = false; line = "Subscriber-only off."; } else { b["subscriber_mode"] = true; line = "Subscriber-only on."; } break;
                default: { int min; if (off) { b["follower_mode"] = false; line = "Followers-only off."; } else { min = 0; if (w != "" && !int.TryParse(w, out min)) { say("Use: !followers [minutes|off]"); return "usage"; } min = Math.Max(0, Math.Min(129600, min)); b["follower_mode"] = true; b["follower_mode_duration"] = min; line = "Followers-only on" + (min > 0 ? " (" + min + " min)." : "."); } break; }
            }
            JToken d; var r = Call(new HttpMethod("PATCH"), "/chat/settings?broadcaster_id={bid}&moderator_id=" + Mod, b, out d);
            say(Ok(r) ? line : "Could not change chat settings: " + Why(r)); return Ok(r) ? "ok" : Why(r);
        }

        // ---- announcements ----
        static string Announce(string[] args, Action<string> say)
        {
            string color = "primary"; var list = args.ToList();
            if (list.Count > 0 && new[] { "blue", "green", "orange", "purple", "primary" }.Contains(list[0].ToLowerInvariant())) { color = list[0].ToLowerInvariant(); list.RemoveAt(0); }
            string text = string.Join(" ", list).Trim(); if (text == "") { say("Use: !announce [blue|green|orange|purple] <text>"); return "usage"; }
            JToken d; var r = Call(HttpMethod.Post, "/chat/announcements?broadcaster_id={bid}&moderator_id=" + Mod, new JObject { { "message", Clip(text, 500) }, { "color", color } }, out d);
            if (!Ok(r)) say("Could not announce: " + Why(r)); return Ok(r) ? "ok" : Why(r);
        }

        static string Retitle(bool title, string a, Action<string> say)
        {
            if (a == "") { say(title ? "Use: !title <new stream title>" : "Use: !game <category name>"); return "usage"; }
            var r = ChannelControl.Update(title ? a : null, title ? null : a);
            if ((bool?)r["ok"] == true) { say(title ? "Title changed to: " + Clip((string)r["title"], 120) : "Game changed to: " + (string)r["game"]); return "ok"; }
            string e = (string)r["error"] ?? "unknown"; say("Could not change the " + (title ? "title" : "game") + ": " + Clip(e, 140)); return e;
        }
        static string Marker(string a, Action<string> say)
        {
            JToken d; var body = new JObject { { "user_id", TwitchApi.BroadcasterId() } }; if (a != "") body["description"] = Clip(a, 140);
            var r = Call(HttpMethod.Post, "/streams/markers", body, out d);
            say(Ok(r) ? "Marker added." : "Could not add a marker" + (r == "404" || r == "400" ? " (is the stream live?)" : ": " + Why(r))); return Ok(r) ? "ok" : Why(r);
        }
        static string Shield(string[] args, Action<string> say)
        {
            string w = args.Length > 0 ? args[0].ToLowerInvariant() : ""; if (w != "on" && w != "off") { say("Use: !shield on|off"); return "usage"; }
            JToken d; var r = Call(HttpMethod.Put, "/moderation/shield_mode?broadcaster_id={bid}&moderator_id=" + Mod, new JObject { { "is_active", w == "on" } }, out d);
            say(Ok(r) ? "Shield mode " + w + "." : "Could not change shield mode: " + Why(r)); return Ok(r) ? "ok" : Why(r);
        }
        static string Ad(string[] args, Action<string> say)
        {
            int len = 30; if (args.Length > 0 && !int.TryParse(args[0], out len)) { say("Use: !ad [30|60|90|120|150|180]"); return "usage"; }
            if (!new[] { 30, 60, 90, 120, 150, 180 }.Contains(len)) { say("Ad length must be 30, 60, 90, 120, 150 or 180 seconds."); return "usage"; }
            say("Ad break in 30 seconds (" + len + "s). Thanks for sticking with us!");
            Task.Run(async () =>
            {
                await Task.Delay(AdWarnMs());
                JToken d; var r = Call(HttpMethod.Post, "/channels/commercial", new JObject { { "broadcaster_id", TwitchApi.BroadcasterId() }, { "length", len } }, out d);
                Log("system", "!ad", len.ToString(), Ok(r) ? "started" : Why(r)); if (!Ok(r)) say("The ad did not start: " + Why(r));
            });
            return "warned";
        }
        static int AdWarnMs() { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_AD_WARN_MS"), out v) ? v : 30000; }
        static string Vip(bool add, string[] args, Action<string> say)
        {
            string name = args.Length > 0 ? args[0].TrimStart('@').ToLowerInvariant() : ""; if (!Regex.IsMatch(name, "^[a-z0-9_]{2,25}$")) { say("Use: " + (add ? "!vip" : "!unvip") + " <name>"); return "usage"; }
            string err; string uid = TwitchApi.UserId(name, out err); if (uid == "") { say("I could not find " + name + "."); return err; }
            JToken d; var r = Call(add ? HttpMethod.Post : HttpMethod.Delete, "/channels/vips?broadcaster_id={bid}&user_id=" + uid, null, out d);
            say(Ok(r) ? (add ? name + " is a VIP now." : name + " is no longer a VIP.") : "Could not change VIP: " + Why(r)); return Ok(r) ? "ok" : Why(r);
        }

        // ---- raids ----
        static string Raid(string cmd, string[] args, Action<string> say)
        {
            if (cmd == "!raid")
            {
                string name = args.Length > 0 ? args[0].TrimStart('@').ToLowerInvariant() : "";
                if (name == "") { say("Use: !raid <channel> (only channels on the raid list)"); return "usage"; }
                if (!RaidList().Contains(name)) { say(name + " is not on the raid list."); return "refused: not on list"; }
                _raidName = name; _raidAt = DateTime.UtcNow; say("Raid " + name + "? Say !confirm raid within 20 seconds. !unraid cancels."); return "pending";
            }
            if (cmd == "!unraid")
            {
                bool had = _raidName != "" || (DateTime.UtcNow - _raidStarted).TotalSeconds < 90; _raidName = "";
                if ((DateTime.UtcNow - _raidStarted).TotalSeconds < 90) { JToken d; Call(HttpMethod.Delete, "/raids?broadcaster_id={bid}", null, out d); _raidStarted = DateTime.MinValue; }
                say(had ? "Raid cancelled." : "No raid to cancel."); return had ? "cancelled" : "none";
            }
            // !confirm raid
            if (args.Length == 0 || args[0].ToLowerInvariant() != "raid") return "ignored";
            if (Synthetic) { say("Raids can only be confirmed by typing in Twitch chat."); return "refused: not from chat"; }
            if (_raidName == "" || (DateTime.UtcNow - _raidAt).TotalSeconds > 20) { _raidName = ""; say("No raid waiting (or it timed out). Start again with !raid <channel>."); return "expired"; }
            string target = _raidName; _raidName = "";
            if (!RaidList().Contains(target)) { say(target + " is not on the raid list."); return "refused: not on list"; }
            string err; string uid = TwitchApi.UserId(target, out err); if (uid == "") { say("I could not find " + target + "."); return err; }
            JToken d2; var r = Call(HttpMethod.Post, "/raids?from_broadcaster_id={bid}&to_broadcaster_id=" + uid, null, out d2);
            if (!Ok(r)) { say("The raid did not start: " + Why(r)); return Why(r); }
            _raidStarted = DateTime.UtcNow; say("Raiding " + target + " now. !unraid cancels it before it goes."); return "started";
        }

        // ---- live state for the overlays: GET /api/live-state -> {poll, prediction, hype}, each the latest stored data block plus state (an ended item stays 20 s, then null) ----
        static readonly Dictionary<string, JObject> Live = new Dictionary<string, JObject>(); static readonly Dictionary<string, DateTime> LiveEnd = new Dictionary<string, DateTime>();
        static void TrackLive(Dictionary<string, object> args)
        {
            string et = Convert.ToString(args["eventType"]); string k = et == "TwitchPoll" ? "poll" : et == "TwitchPrediction" ? "prediction" : et == "TwitchHype" ? "hype" : null; if (k == null) return;
            var data = new JObject { { "state", args.ContainsKey("state") ? Convert.ToString(args["state"]) : "" } };
            foreach (var kv in args) if (kv.Key.StartsWith("x.")) { string v = Convert.ToString(kv.Value) ?? ""; JToken jt = null; if (v.StartsWith("[") || v.StartsWith("{")) { try { jt = JToken.Parse(v); } catch (Exception) { } } data[kv.Key.Substring(2)] = jt ?? (JToken)v; }
            lock (L) { Live[k] = data; if ((string)data["state"] == "end") LiveEnd[k] = DateTime.UtcNow; else LiveEnd.Remove(k); }
        }
        public static JObject LiveState()
        {
            lock (L)
            {
                var o = new JObject { { "ok", true }, { "offlineMode", OfflineMode.Enabled } };
                foreach (var k in new[] { "poll", "prediction", "hype" })
                {
                    JObject v; DateTime e; bool has = Live.TryGetValue(k, out v);
                    if (has && LiveEnd.TryGetValue(k, out e) && (DateTime.UtcNow - e).TotalSeconds > 20) { Live.Remove(k); LiveEnd.Remove(k); has = false; }
                    o[k] = has ? (JToken)v.DeepClone() : JValue.CreateNull();
                }
                return o;
            }
        }

        // ---- result lines for poll / prediction end (from EventSub) ----
        public static void OnEvent(Dictionary<string, object> args)
        {
            try
            {
                object et; if (!args.TryGetValue("eventType", out et)) return;
                TrackLive(args);
                if (!Enabled) return;
                string t = Convert.ToString(et), st = args.ContainsKey("state") ? Convert.ToString(args["state"]) : ""; if (st != "end") return;
                Func<string, string> g = k => args.ContainsKey(k) ? Convert.ToString(args[k]) : "";
                string line = null;
                if (t == "TwitchPoll" && g("x.status") == "completed")
                {
                    var ch = JArray.Parse(g("x.choices")).OfType<JObject>().OrderByDescending(c => (int?)c["votes"] ?? 0).ToList();
                    if (ch.Count > 0) { int top = (int?)ch[0]["votes"] ?? 0; bool tie = ch.Count > 1 && ((int?)ch[1]["votes"] ?? 0) == top; line = tie || top == 0 ? "Poll over: " + g("x.title") + " ended in a tie." : "Poll over: " + (string)ch[0]["title"] + " wins with " + top + " votes!"; }
                }
                else if (t == "TwitchPrediction" && g("x.status") == "resolved")
                {
                    var w = JArray.Parse(g("x.outcomes")).OfType<JObject>().FirstOrDefault(o => (string)o["id"] == g("x.winningOutcomeId"));
                    line = w != null ? "Prediction result: " + (string)w["title"] + " wins!" : "Prediction resolved.";
                }
                if (line != null) { if (HostApi.SimMode) Console.WriteLine("[say] " + line); else { string via; HostApi.SendAs("core", line, out via); } }
            }
            catch (Exception) { }
        }
    }
}
