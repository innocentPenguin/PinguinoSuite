using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Twitch Helix calls with the streamer token, for the Actions &amp; Events steps that replace Streamer.bot (create_clip, ad_schedule, channel_info, native shoutouts).
    /// Needs the streamer signed in with clips:edit, channel:read:ads and moderator:manage:shoutouts (the sign-in asks for them). Never logs a token.</summary>
    public static class TwitchApi
    {
        public static string Call(HttpMethod method, string pathAndQuery, JObject body, out JToken data, out string error)
        {
            data = null; error = ""; var s = HostApi.StreamerCreds();
            string tok = (string)s["UserToken"] ?? "", cid = (string)s["ClientId"] ?? "", bid = (string)s["BroadcasterId"] ?? "";
            if (tok == "" || cid == "" || bid == "") { error = "the streamer account is not signed in (Host page > Sign in as streamer)"; return "0"; }
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(10) })
                {
                    var rq = new HttpRequestMessage(method, HostApi.Helix + pathAndQuery.Replace("{bid}", bid));
                    rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                    if (body != null) rq.Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json");
                    var r = h.SendAsync(rq).Result; string txt = r.Content.ReadAsStringAsync().Result; int code = (int)r.StatusCode;
                    try { var j = JObject.Parse(txt); data = j["data"]; if (!r.IsSuccessStatusCode) error = (string)j["message"] ?? txt; } catch (Exception) { if (!r.IsSuccessStatusCode) error = txt; }
                    if (code == 401 || code == 403) error = "HTTP " + code + ": the streamer token is missing a permission; sign the streamer in again on the Host page" + (error != "" ? " (" + error + ")" : "");
                    return code.ToString();
                }
            }
            catch (Exception ex) { error = ex.Message; return "0"; }
        }
        /// <summary>like Call, but hands back the whole Helix body (pagination cursor included).</summary>
        public static string CallFull(HttpMethod method, string pathAndQuery, out JObject json, out string error)
        {
            json = null; error = ""; var s = HostApi.StreamerCreds();
            string tok = (string)s["UserToken"] ?? "", cid = (string)s["ClientId"] ?? "", bid = (string)s["BroadcasterId"] ?? "";
            if (tok == "" || cid == "" || bid == "") { error = "the streamer account is not signed in (Host page > Sign in as streamer)"; return "0"; }
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(15) })
                {
                    var rq = new HttpRequestMessage(method, HostApi.Helix + pathAndQuery.Replace("{bid}", bid));
                    rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                    var r = h.SendAsync(rq).Result; string txt = r.Content.ReadAsStringAsync().Result;
                    try { json = JObject.Parse(txt); } catch (Exception) { }
                    if (!r.IsSuccessStatusCode) error = (json != null ? (string)json["message"] : null) ?? txt;
                    return ((int)r.StatusCode).ToString();
                }
            }
            catch (Exception ex) { error = ex.Message; return "0"; }
        }
        public static string BroadcasterId() { return (string)HostApi.StreamerCreds()["BroadcasterId"] ?? ""; }

        public static string Fmt(long sec) { if (sec < 0) sec = 0; return sec >= 60 ? (sec / 60) + ":" + (sec % 60).ToString("D2") : sec + " seconds"; }
        public static string UserId(string login, out string error)
        {
            JToken d; Call(HttpMethod.Get, "/users?login=" + Uri.EscapeDataString(login.TrimStart('@').ToLowerInvariant()), null, out d, out error);
            var first = (d as JArray)?.FirstOrDefault(); if (first == null) { if (error == "") error = "no Twitch user named " + login; return ""; }
            return (string)first["id"] ?? "";
        }
    }

    public static partial class Auto
    {
        /// <summary>the Streamer.bot replacements. Returns the line for the run log, or null when the step type is not one of these.</summary>
        static string ExtraStep(string type, JObject st, Dictionary<string, string> ctx, bool test, Func<string, string> x)
        {
            JToken d; string err;
            switch (type)
            {
                case "create_clip":   // Twitch clip (title + length like the old action: "Clip! cmd", 60 s)
                {
                    string title = x("title"); if (title == "") title = "Clip! cmd"; int dur = Math.Max(5, Math.Min(60, (int?)st["duration"] ?? 60));
                    if (test) return "(dry run) would create a Twitch clip '" + title + "' (" + dur + " s)";
                    string code = TwitchApi.Call(HttpMethod.Post, "/clips?broadcaster_id={bid}&title=" + Uri.EscapeDataString(title) + "&duration=" + dur, null, out d, out err);
                    var c = (d as JArray)?.FirstOrDefault(); if (c == null || (code != "202" && code != "200")) { Clog.Warn("clip", "Twitch clip failed (HTTP " + code + "): " + (err != "" ? err : "is the stream live?")); return "Twitch clip failed (HTTP " + code + "): " + (err != "" ? err : "the stream may be offline"); }
                    string id = (string)c["id"]; ctx["clip.id"] = id; ctx["clip.edit"] = (string)c["edit_url"] ?? "";
                    for (int i = 0; i < 6; i++)   // a clip shows up a few seconds after it is requested
                    {
                        Thread.Sleep(3000); TwitchApi.Call(HttpMethod.Get, "/clips?id=" + id, null, out d, out err);
                        var f = (d as JArray)?.FirstOrDefault(); if (f != null) { ctx["clip.url"] = (string)f["url"] ?? ""; Latest.Record("clip", ctx); return "Twitch clip created: " + ctx["clip.url"]; }
                    }
                    ctx["clip.url"] = ctx["clip.edit"]; Latest.Record("clip", ctx); return "Twitch clip requested (link not ready yet): " + id;
                }
                case "obs_replay_save":   // the OBS replay buffer (what the old !clip finished with); reports honestly when the buffer is not running
                {
                    if (test) return "(dry run) would save the OBS replay buffer";
                    if (!HostApi.ObsConnected()) { Clog.Warn("clip", "OBS is not connected: the replay was NOT saved"); return "OBS is not connected: replay NOT saved"; }
                    var status = Program.ObsData("GetReplayBufferStatus", null);
                    if (status == null) { Clog.Warn("clip", "OBS did not answer GetReplayBufferStatus: replay NOT saved"); return "OBS did not answer: replay NOT saved"; }
                    if (!((bool?)status["outputActive"] ?? false)) { Clog.Warn("clip", "the OBS replay buffer is not running: start it in OBS (Controls > Start Replay Buffer)"); ctx["replay.ok"] = "false"; return "OBS replay buffer is NOT running: replay not saved (start it in OBS)"; }
                    string before = (string)Program.ObsData("GetLastReplayBufferReplay", null)?["savedReplayPath"] ?? "";
                    if (!Program.ObsRaw("SaveReplayBuffer", null)) { Clog.Warn("clip", "OBS refused SaveReplayBuffer"); return "OBS refused to save the replay"; }
                    string path = "";
                    for (int i = 0; i < 8 && path == ""; i++)   // the file appears a moment after the request
                    {
                        Thread.Sleep(750); string now = (string)Program.ObsData("GetLastReplayBufferReplay", null)?["savedReplayPath"] ?? "";
                        if (now != "" && now != before) path = now;
                    }
                    ctx["replay.ok"] = "true"; ctx["replay.path"] = path; ctx["replay.file"] = path == "" ? "" : Path.GetFileName(path);
                    var rc = new Dictionary<string, string>(ctx); rc["clip.url"] = ctx["replay.file"]; Latest.Record("replay", rc);
                    return path == "" ? "replay saved (OBS has not reported the file name yet)" : "replay saved: " + path;
                }
                case "ad_schedule":
                {
                    if (test) { ctx["adPrerollFree"] = "12:34"; ctx["adIn"] = "4:00"; return "(dry run) would read the ad schedule"; }
                    string code = TwitchApi.Call(HttpMethod.Get, "/channels/ads?broadcaster_id={bid}", null, out d, out err);
                    var a = (d as JArray)?.FirstOrDefault(); if (a == null) return "ad_schedule failed (HTTP " + code + "): " + (err != "" ? err : "no data (is the stream live?)");
                    long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), next = (long?)a["next_ad_at"] ?? 0, free = (long?)a["preroll_free_time"] ?? 0;
                    ctx["adPrerollSec"] = free.ToString(); ctx["adPrerollFree"] = TwitchApi.Fmt(free);
                    ctx["adIn"] = next > now ? TwitchApi.Fmt(next - now) : "unknown"; ctx["adNextAt"] = next.ToString();
                    ctx["adLengthSec"] = ((int?)a["duration"] ?? 0).ToString(); ctx["adSnoozes"] = ((int?)a["snooze_count"] ?? 0).ToString();
                    return "ads: next in " + ctx["adIn"] + ", preroll-free " + ctx["adPrerollFree"];
                }
                case "channel_info":   // sets {game} and {title}
                {
                    if (test) { ctx["game"] = "a game"; ctx["title"] = "a title"; return "(dry run) would read the channel title and category"; }
                    TwitchApi.Call(HttpMethod.Get, "/channels?broadcaster_id={bid}", null, out d, out err); var ch = (d as JArray)?.FirstOrDefault();
                    if (ch == null) return "channel_info failed: " + err; ctx["game"] = (string)ch["game_name"] ?? ""; ctx["title"] = (string)ch["title"] ?? ""; return "channel: " + ctx["game"];
                }
                case "shoutout_queue":   // adds a streamer to the shoutout queue (see Shout in HostLatest.cs)
                {
                    string who = x("user").TrimStart('@'); if (who == "") return "shoutout: no streamer given";
                    if (test) return "(dry run) would queue a shoutout for " + who;
                    return "shoutout " + Shout.Enqueue(who, x("by"), (bool?)st["auto"] == true) + ": " + who;
                }
                case "alert_settings":   // sets {popup.scene}, {popup.source}, {popup.ms} from alerts_settings.json
                {
                    var al = AlertCfg.Settings(); ctx["popup.scene"] = (string)al["PopupScene"]; ctx["popup.source"] = (string)al["PopupSource"]; ctx["popup.ms"] = ((int)(((double?)al["PopupSeconds"] ?? 10) * 1000)).ToString();
                    return "popup: " + ctx["popup.scene"] + " / " + ctx["popup.source"] + " for " + ctx["popup.ms"] + " ms";
                }
                case "alert_sound":   // plays the sound Ivan set for this kind in alerts_settings.json (none set = nothing)
                {
                    var al = AlertCfg.Settings(); if ((bool?)al["MuteSounds"] == true) return "alert sounds are muted";
                    var so = al["Sounds"]?[x("kind")]; string file = (string)so?["File"] ?? ""; if (file == "") return "no sound set for " + x("kind");
                    return Sounds.Play(x("kind"), file, (double?)so["Volume"] ?? 0.6, test);
                }
                case "session_say": ctx["session.line"] = Session.Line(); try { var rc = Recap.Build(true); ctx["session.line"] = (string)rc["line"]; var cp = rc["clip"] as JObject; ctx["session.clip"] = cp == null ? "" : " Best clip: " + (string)cp["url"]; } catch (Exception) { ctx["session.clip"] = ""; } return "session: " + ctx["session.line"];
                case "goal_say": ctx["goal.line"] = Session.GoalLine(x("id")); return "goal: " + ctx["goal.line"];
                case "press_key": return test ? "(dry run) would press " + x("key") : PressKey(x("key"));
                case "latest_say":   // sets {latest.line}: the newest follower / sub / cheer / raid
                    ctx["latest.line"] = "Latest " + Latest.Summary(); return "latest: " + ctx["latest.line"];
                case "append_file":
                {
                    string name = Path.GetFileName(x("file")); if (name == "") name = "notes.txt";   // only inside Data\runtime\files: no paths
                    string line = x("text"); if (test) return "(dry run) would add a line to files\\" + name + ": " + line;
                    try { string dir = Path.Combine(DataDir, "files"); Directory.CreateDirectory(dir); File.AppendAllText(Path.Combine(dir, name), line + Environment.NewLine, Encoding.UTF8); return "added a line to files\\" + name; }
                    catch (Exception ex) { return "append_file failed: " + ex.Message; }
                }
            }
            return null;
        }

        static string PressKey(string name)
        {
            name = (name ?? "").Trim(); int vk;
            var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase) { { "MediaPlayPause", 0xB3 }, { "MediaNext", 0xB0 }, { "MediaPrev", 0xB1 }, { "MediaStop", 0xB2 }, { "VolumeUp", 0xAF }, { "VolumeDown", 0xAE }, { "VolumeMute", 0xAD } };
            if (!map.TryGetValue(name, out vk))
            {
                var fm = System.Text.RegularExpressions.Regex.Match(name, @"^F(\d{1,2})$", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                if (fm.Success && int.Parse(fm.Groups[1].Value) >= 1 && int.Parse(fm.Groups[1].Value) <= 24) vk = 0x70 + int.Parse(fm.Groups[1].Value) - 1;
                else if (!int.TryParse(name.StartsWith("0x") ? Convert.ToInt32(name.Substring(2), 16).ToString() : name, out vk) || vk < 1 || vk > 254) return "press_key: unknown key '" + name + "' (use MediaPlayPause, MediaNext, MediaPrev, VolumeUp/Down/Mute, F1-F24 or a virtual-key number)";
            }
            try
            {
                string ps = "Add-Type -MemberDefinition '[DllImport(\"user32.dll\")] public static extern void keybd_event(byte b, byte s, int f, int e);' -Name K -Namespace PgKeys; [PgKeys.K]::keybd_event(" + vk + ",0,0,0); [PgKeys.K]::keybd_event(" + vk + ",0,2,0)";
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("powershell", "-NoProfile -ExecutionPolicy Bypass -Command \"" + ps.Replace("\"", "\\\"") + "\"") { CreateNoWindow = true, UseShellExecute = false });
                return "pressed key " + name;
            }
            catch (Exception ex) { return "press_key failed: " + ex.Message; }
        }

        // ---------------- presets that replace the Streamer.bot actions ----------------
        static JObject Cut(JObject a) { a["cutover"] = true; a["enabled"] = Cutover.On; a["importNotes"] = (string)a["importNotes"] + " [switched on by the Streamer.bot cutover button; until then OFF so nothing answers twice]"; return a; }
        static JObject Act(string id, string name, string note, bool enabled, JArray triggers, params JObject[] steps)
        {
            return new JObject { { "id", id }, { "name", name }, { "group", "Streamer.bot replacement" }, { "enabled", enabled }, { "importNotes", note }, { "triggers", triggers }, { "conditions", new JArray() }, { "steps", new JArray(steps) } };
        }
        static JObject SayStep(string text, string as_ = "core") { return new JObject { { "type", "say" }, { "as", as_ }, { "text", text } }; }
        static JObject Tr(string type, params object[] kv) { var o = new JObject { { "type", type } }; for (int i = 0; i + 1 < kv.Length; i += 2) o[(string)kv[i]] = JToken.FromObject(kv[i + 1]); return o; }
        static JObject Step(string type, params object[] kv) { return Tr(type, kv); }
        static JObject Popup() { return Step("run_action", "name", "Alerts: show Latest Group"); }
        const string BanDir = "C:\\Users\\ivanm\\Documents\\amongusban\\";

        /// <summary>Streamer.bot replacement actions (Docs\STREAMERBOT_REPLACEMENT.md). The ones Ivan asked to be live are created ENABLED, the rest disabled.
        /// Remembered in "seeded", so deleting or editing one sticks.</summary>
        /// <summary>one-time (marker "alertsound1"): the seeded follow/sub/resub/gift/cheer/raid actions saved before the alert_sound step existed get it, placed before the popup step.
        /// Sounds come from alerts_settings.json, so a kind with no file stays silent.</summary>
        static void AddAlertSoundSteps()
        {
            var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray();
            if (seeded.Any(v => (string)v == "alertsound1")) return;
            if (!seeded.Any(v => (string)v == "sbreplace2")) return;   // not seeded yet: the fresh seed already carries the steps
            foreach (var a in ((JArray)doc["actions"]).OfType<JObject>())
            {
                string id = (string)a["id"] ?? ""; var kinds = new Dictionary<string, string> { { "sb-follow", "follow" }, { "sb-sub", "sub" }, { "sb-resub", "resub" }, { "sb-gift", "gift" }, { "sb-cheer", "cheer" }, { "sb-raid", "raid" } };
                string kind; if (!kinds.TryGetValue(id, out kind)) continue;
                var steps = a["steps"] as JArray; if (steps == null || steps.OfType<JObject>().Any(s => (string)s["type"] == "alert_sound")) continue;
                int at = steps.Count; for (int i = 0; i < steps.Count; i++) if ((string)steps[i]["type"] == "run_action") { at = i; break; }
                steps.Insert(at, Step("alert_sound", "kind", kind));
            }
            seeded.Add("alertsound1"); doc["seeded"] = seeded; Save(doc);
        }

        /// <summary>one-time: the "Prepare your emotes" line moves from raid_out (the raid landing) to raid_start (the raid being scheduled). Keeps the enabled flag Ivan chose.</summary>
        internal static void MigrateRaidStart()
        {
            try
            {
                var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray(); if (seeded.Any(v => (string)v == "raidstart1")) return;
                var acts = (JArray)doc["actions"]; var old = acts.OfType<JObject>().FirstOrDefault(o => (string)o["id"] == "sb-raidout");
                if (old != null && !acts.OfType<JObject>().Any(o => (string)o["id"] == "sb-raidstart"))
                {
                    var steps = (JArray)old["steps"]; var say = new JArray(); var rest = new JArray(); bool inSay = true;
                    foreach (JObject st in steps.OfType<JObject>())
                    {
                        if ((string)st["type"] == "delay" && (long?)st["ms"] == 20000) inSay = false;
                        (inSay ? say : rest).Add(st);
                    }
                    if (say.Count > 0)
                    {
                        string disc = Links.Get("discord") ?? "https://discord.gg/fktz5sq4b8";
                        var ns = Act("sb-raidstart", "Raid scheduled", "fires when the raid is SCHEDULED (!confirm raid started the Twitch countdown), not when it lands.", (bool?)old["enabled"] == true, new JArray { Tr("raid_start") });
                        ns["steps"] = say; acts.Add(ns); old["steps"] = rest; old["importNotes"] = "the raid has landed (the emote line moved to 'Raid scheduled'). WARNING: the last step stops the stream 20 s later.";
                    }
                }
                seeded.Add("raidstart1"); doc["seeded"] = seeded; Save(doc);
            }
            catch (Exception ex) { Clog.Warn("automation", "raid start migration failed: " + ex.Message); }
        }

        public static void SeedStreamerBotPresets()
        {
            MigrateRaidStart();
            try { AddAlertSoundSteps(); } catch (Exception ex) { Clog.Warn("automation", "alert sound migration failed: " + ex.Message); }
            try
            {
                var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray();
                if (seeded.Any(v => (string)v == "sbreplace2")) return;
                var acts = (JArray)doc["actions"];
                foreach (var gone in acts.OfType<JObject>().Where(o => ((string)o["id"] ?? "").StartsWith("sb-") && ((string)o["importNotes"] ?? "").StartsWith("preset")).ToList()) acts.Remove(gone);   // an earlier test build's presets
                string disc = Links.Get("discord") ?? "https://discord.gg/fktz5sq4b8";   // the live invite (the old be6bus4GKh one is expired)
                var list = new List<JObject> {
                    Act("sb-latest-popup", "Alerts: show Latest Group", "preset: shows the 'Latest Group' for some seconds after each alert, like the old 'latest' action. Scene, source and seconds: Data\\runtime\\alerts_settings.json.", true, new JArray { Tr("manual") },
                        Step("alert_settings"), Step("obs_source", "scene", "{popup.scene}", "source", "{popup.source}", "visible", "true"), Step("delay", "ms", "{popup.ms}"), Step("obs_source", "scene", "{popup.scene}", "source", "{popup.source}", "visible", "false")),
                    Act("sb-session-cmd", "Command: !session", "new: this stream's numbers (follows, subs, bits, raids). Wording in session_settings.json.", true, new JArray { Tr("command", "names", new JArray("!session", "!streamstats"), "cooldownSec", 20) }, Step("session_say"), SayStep("{session.line}")),
                    Act("sb-goal-cmd", "Command: !goal", "new: progress of the goals in session_settings.json (the OBS bar is /overlay/goal?id=followers).", true, new JArray { Tr("command", "names", new JArray("!goal", "!goals"), "cooldownSec", 20) }, Step("goal_say", "id", "{arg1}"), SayStep("{goal.line}")),
                    Act("sb-recap", "Stream recap", "new: the stream's numbers when you go offline (use instead of or after 'Stream offline').", false, new JArray { Tr("stream_offline") }, Step("session_say"), SayStep("Thanks for tuning in! {session.line}{session.clip}")),
                    Act("sb-follow", "Alert: follow", "from Streamer.bot 'Followed'", true, new JArray { Tr("follow") }, SayStep("innoce108Cool Hello {user} just followed! Welcome to the community! innoce108Hello"), Step("alert_sound", "kind", "follow"), Popup()),
                    Act("sb-sub", "Alert: sub", "from Streamer.bot 'Normal' + 'Super' (Prime looks like tier 1 in Twitch's event)", true, new JArray { Tr("sub") },
                        Step("if", "left", "{tier}", "op", "==", "right", "1", "then", new JArray { SayStep("🐧 Thank you for the sub, {user}! Enjoy the stream!") }, "else", new JArray { SayStep("🐧 Thank you for the super sub, {user}! Enjoy the stream!") }), Step("alert_sound", "kind", "sub"), Popup()),
                    Act("sb-resub", "Alert: resub", "from Streamer.bot 'Resub'", true, new JArray { Tr("resub") }, SayStep("🐧 {user} resubbed with a tier {tier} sub! Thank you. I appreciate you!"), Step("alert_sound", "kind", "resub"), Popup()),
                    Act("sb-gift", "Alert: gifted subs", "from Streamer.bot 'Gifted' (Twitch sends one event per gift bomb)", true, new JArray { Tr("gift") }, SayStep("🎁 {user} gifted {total} sub(s)! innoce108Cool"), Step("alert_sound", "kind", "gift"), Popup()),
                    Act("sb-cheer", "Alert: cheer", "from Streamer.bot 'Cheers'", true, new JArray { Tr("cheer") }, SayStep("{user} cheered {bits} bits!"), Step("alert_sound", "kind", "cheer"), Popup()),
                    Act("sb-raid", "Alert: incoming raid", "from Streamer.bot 'Raided' (it was switched off there): thanks, emotes, welcome, then a queued shoutout.", true, new JArray { Tr("raid") },
                        Step("delay", "ms", 500), SayStep("innoce108Cool {raider} just raided the channel with {viewers} viewers PogChamp"),
                        SayStep("innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid"),
                        Step("delay", "ms", 2500), SayStep("Welcome everyone! innoce108Hello Thank you so much for the raid {raider}!!! innoce108Gift"), Step("alert_sound", "kind", "raid"), Popup(), Step("delay", "ms", 12000), Step("shoutout_queue", "user", "{raider}", "auto", true)),
                    Act("sb-ban", "Alert: ban (Among Us ejected)", "from Streamer.bot 'Add Ban': browser source + eject sound. Needs the ban event (channel:moderate: sign the streamer in again).", true, new JArray { Tr("ban") },
                        Step("obs_request", "request", "SetInputSettings", "data", new JObject { { "inputName", "Ban Alert - Among Us Ejected" }, { "inputSettings", new JObject { { "url", "file:///C:/Users/ivanm/Documents/amongusban/Browser%20Sources/among-uspure-css/index.html?user={user}" } } } }),
                        Step("obs_source", "scene", "Ban Alert", "source", "Ban Alert - Among Us Ejected", "visible", "true"), Step("delay", "ms", 900),
                        Step("sound", "file", BanDir + "Sounds\\eject_amongus.mp3", "volume", 0.9), Step("delay", "ms", 4100),
                        Step("obs_source", "scene", "Ban Alert", "source", "Ban Alert - Among Us Ejected", "visible", "false")),
                    Act("sb-clip", "Command: !clip", "from Streamer.bot 'Clip': says Clipped, 10 s later a Twitch clip (title 'Clip! cmd', 60 s), 15 s later saves the OBS REPLAY BUFFER. The replay buffer must be running in OBS. Needs clips:edit.", true,
                        new JArray { Tr("command", "names", new JArray("!clip"), "cooldownSec", 25) },
                        SayStep("Clipped"), Step("delay", "ms", 10000), Step("create_clip", "title", "Clip! cmd", "duration", 60), Step("delay", "ms", 15000), Step("obs_replay_save")),
                    Act("sb-preroll", "Command: !preroll / !ad", "from Streamer.bot 'Preroll' (PinguinoHelper answers). Needs channel:read:ads.", true, new JArray { Tr("command", "names", new JArray("!preroll", "!ad", "!ads"), "cooldownSec", 20) },
                        Step("ad_schedule"), SayStep("{adPrerollFree} left. Next ad in {adIn}.", "helper")),
                    Act("sb-whyad", "Command: !whyad", "from Streamer.bot 'Whyad' (PinguinoHelper answers)", true, new JArray { Tr("command", "names", new JArray("!whyad", "!whyads"), "cooldownSec", 30) },
                        SayStep("Sorry for the ad! Twitch does not allow affiliates to disable ads so creators have a choice between running ads when you join or during stream. I chose to run 3 minutes during stream so we don't lose any newcomers to ads. Use !preroll to check ad status", "helper")),
                    Act("sb-shout", "Command: !shout", "our own shoutout queue: Twitch card + chat line with last game and pronouns, no repeats within 2 minutes (raids: 60 minutes). Lines in Data\\runtime\\shout_settings.json.", true, new JArray { Tr("command", "names", new JArray("!shout", "!so"), "permission", "mod") },
                        Step("shoutout_queue", "user", "{arg1}", "by", "{user}")),
                    Act("sb-latest-cmd", "Command: !latest", "new: says the newest follower, sub, cheer and raid. The OBS overlay is http://127.0.0.1:8770/overlay/latest.", true, new JArray { Tr("command", "names", new JArray("!latest"), "cooldownSec", 15) },
                        Step("latest_say"), SayStep("{latest.line}")),
                    // off until Ivan reviews them
                    Act("sb-online", "Stream online", "from 'Stream Status (Online)' (the First 5 game restarts by itself)", false, new JArray { Tr("stream_online") }, Step("channel_info"), SayStep("Stream is live! Today we are streaming {game}.")),
                    Act("sb-offline", "Stream offline", "from 'Stream Status (Offline)'", false, new JArray { Tr("stream_offline") }, SayStep("Stream offline. Goodnight everybody. Thanks for tuning in!")),
                    Act("sb-raidstart", "Raid scheduled", "fires when the raid is SCHEDULED (!confirm raid started the Twitch countdown), not when it lands: emotes line, then the Discord invite.", false, new JArray { Tr("raid_start") },
                        SayStep("Raid started! Prepare your emotes! innoce108Arrive innoce108W innoce108Danceydance innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid innoce108Hype innoce108Hello innoce108W"),
                        Step("delay", "ms", 3000), SayStep("Don't forget to join the community Discord! Hang out, chat, share media, receive updates → " + disc)),
                    Act("sb-raidout", "Raid out", "from 'Raid Out Start/End': the raid has landed. WARNING: the last step stops the stream 20 s later, like Streamer.bot did.", false, new JArray { Tr("raid_out") },
                        Step("delay", "ms", 20000), Step("obs_request", "request", "StopStream")),
                    Act("sb-endstream", "Reward: Instantly End Stream", "from the 'Instantly End Stream' reward (2,500,000 points). Needs channel:read:redemptions.", false, new JArray { Tr("redeem", "title", "Instantly End Stream") },
                        SayStep("{user} ended the stream. Goodbye! 🐧"), Step("delay", "ms", 5000), Step("obs_request", "request", "StopStream")),
                    Act("sb-suggest", "Reward: Suggestion Box", "from the 'Suggestion' reward: saves each suggestion to Data\\runtime\\files\\suggestions.txt.", false, new JArray { Tr("redeem", "title", "Suggestion") },
                        Step("inc_var", "name", "suggestions", "by", 1, "persist", true), Step("append_file", "file", "suggestions.txt", "text", "{count} {user} - {input}"), SayStep("Thanks {user}, suggestion saved!")),
                };
                foreach (var a in list) if ((string)a["id"] == "sb-ban") a["conditions"] = new JArray { new JObject { { "left", "{permanent}" }, { "op", "==" }, { "right", "true" } } };   // timeouts (permanent=false) must not play the eject sound
                var dup = new HashSet<string> { "sb-follow", "sb-sub", "sb-resub", "sb-gift", "sb-cheer", "sb-raid", "sb-ban", "sb-clip", "sb-preroll", "sb-whyad" };   // Streamer.bot answers these too: wait for the cutover switch
                foreach (var a in list) if (dup.Contains((string)a["id"])) Cut(a);
                foreach (var a in list) if (!acts.OfType<JObject>().Any(o => (string)o["id"] == (string)a["id"])) acts.Add(a);
                seeded.Add("sbreplace2"); doc["seeded"] = seeded; Save(doc);
            }
            catch (Exception ex) { Clog.Warn("automation", "seeding Streamer.bot replacement presets failed: " + ex.Message); }
        }
    }
}
