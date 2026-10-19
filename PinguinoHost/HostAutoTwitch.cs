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
    /// <summary>Twitch Helix calls with the streamer token, for the Actions &amp; Events steps that replace Streamer.bot: set_title, create_clip, ad_schedule, shoutout.
    /// Needs the streamer signed in with channel:manage:broadcast, clips:edit, channel:read:ads and moderator:manage:shoutouts (the sign-in asks for them). Never logs a token.</summary>
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
        public static string BroadcasterId() { return (string)HostApi.StreamerCreds()["BroadcasterId"] ?? ""; }

        public static string Fmt(long sec) { if (sec < 0) sec = 0; return sec >= 60 ? (sec / 60) + ":" + (sec % 60).ToString("D2") : sec + " seconds"; }
        public static string UserId(string login, out string error)
        {
            JToken d; string code = Call(HttpMethod.Get, "/users?login=" + Uri.EscapeDataString(login.TrimStart('@').ToLowerInvariant()), null, out d, out error);
            var first = (d as JArray)?.FirstOrDefault(); if (first == null) { if (error == "") error = "no Twitch user named " + login; return ""; }
            return (string)first["id"] ?? "";
        }
    }

    public static partial class Auto
    {
        static DateTime _lastShoutout = DateTime.MinValue; static readonly object _shoutLock = new object();

        /// <summary>the Streamer.bot replacements. Returns the line for the run log, or null when the step type is not one of these.</summary>
        static string ExtraStep(string type, JObject st, Dictionary<string, string> ctx, bool test, Func<string, string> x)
        {
            JToken d; string err;
            switch (type)
            {
                case "set_title":
                {
                    string title = x("title"), game = x("game");
                    if (title.Length > 140) title = title.Substring(0, 140);
                    if (test) return "(dry run) would set the stream title to: " + title + (game != "" ? " | category: " + game : "");
                    var body = new JObject(); if (title != "") body["title"] = title;
                    string gname = "";
                    if (game != "")
                    {
                        TwitchApi.Call(HttpMethod.Get, "/games?name=" + Uri.EscapeDataString(game), null, out d, out err);
                        var g = (d as JArray)?.FirstOrDefault(); if (g == null) return "set_title: no Twitch category named '" + game + "'" + (err != "" ? " (" + err + ")" : "");
                        body["game_id"] = (string)g["id"]; gname = (string)g["name"];
                    }
                    if (body.Count == 0) return "set_title: nothing to set";
                    string code = TwitchApi.Call(new HttpMethod("PATCH"), "/channels?broadcaster_id={bid}", body, out d, out err);
                    ctx["title"] = title;
                    return code == "204" ? "title set" + (gname != "" ? ", category " + gname : "") : "set_title failed (HTTP " + code + "): " + err;
                }
                case "create_clip":
                {
                    if (test) return "(dry run) would create a clip";
                    string code = TwitchApi.Call(HttpMethod.Post, "/clips?broadcaster_id={bid}", null, out d, out err);
                    var c = (d as JArray)?.FirstOrDefault(); if (c == null || (code != "202" && code != "200")) return "create_clip failed (HTTP " + code + "): " + (err != "" ? err : "the stream may be offline");
                    string id = (string)c["id"]; ctx["clip.id"] = id; ctx["clip.edit"] = (string)c["edit_url"] ?? "";
                    for (int i = 0; i < 6; i++)   // a clip shows up a few seconds after it is requested
                    {
                        Thread.Sleep(3000); TwitchApi.Call(HttpMethod.Get, "/clips?id=" + id, null, out d, out err);
                        var f = (d as JArray)?.FirstOrDefault(); if (f != null) { ctx["clip.url"] = (string)f["url"] ?? ""; return "clip created: " + ctx["clip.url"]; }
                    }
                    ctx["clip.url"] = ctx["clip.edit"]; return "clip requested (link not ready): " + id;
                }
                case "ad_schedule":
                {
                    if (test) { ctx["adPrerollFree"] = "12:34"; ctx["adIn"] = "4:00"; return "(dry run) would read the ad schedule"; }
                    string code = TwitchApi.Call(HttpMethod.Get, "/channels/ads?broadcaster_id={bid}", null, out d, out err);
                    var a = (d as JArray)?.FirstOrDefault(); if (a == null) return "ad_schedule failed (HTTP " + code + "): " + (err != "" ? err : "no data (is the stream live?)");
                    long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), next = (long?)a["next_ad_at"] ?? 0, free = (long?)a["preroll_free_time"] ?? 0;
                    ctx["adPrerollSec"] = free.ToString(); ctx["adPrerollFree"] = TwitchApi.Fmt(free);
                    ctx["adIn"] = next > 0 ? TwitchApi.Fmt(next - now) : "unknown"; ctx["adNextAt"] = next.ToString();
                    ctx["adLengthSec"] = ((int?)a["duration"] ?? 0).ToString(); ctx["adSnoozes"] = ((int?)a["snooze_count"] ?? 0).ToString();
                    return "ads: next in " + ctx["adIn"] + ", preroll-free " + ctx["adPrerollFree"];
                }
                case "shoutout":
                {
                    string who = x("user").TrimStart('@'); if (who == "") return "shoutout: no user given";
                    if (test) { ctx["shoutoutUser"] = who; ctx["shoutoutLogin"] = who.ToLowerInvariant(); ctx["shoutoutGame"] = "their game"; ctx["shoutoutChannel"] = "https://twitch.tv/" + who.ToLowerInvariant(); return "(dry run) would look up " + who + (((bool?)st["native"] ?? false) ? " and send a Twitch shoutout" : ""); }
                    string uid = TwitchApi.UserId(who, out err); if (uid == "") return "shoutout: " + err;
                    TwitchApi.Call(HttpMethod.Get, "/channels?broadcaster_id=" + uid, null, out d, out err);
                    var ch = (d as JArray)?.FirstOrDefault(); string login = ((string)ch?["broadcaster_login"] ?? who).ToLowerInvariant();
                    ctx["shoutoutUser"] = (string)ch?["broadcaster_name"] ?? who; ctx["shoutoutLogin"] = login; ctx["shoutoutGame"] = ((string)ch?["game_name"] ?? "") != "" ? (string)ch["game_name"] : "something fun";
                    ctx["shoutoutChannel"] = "https://twitch.tv/" + login;
                    string extra = "";
                    if ((bool?)st["native"] == true)   // Twitch's own shoutout card; Twitch allows one every 2 minutes, so later ones wait their turn (max 130 s)
                    {
                        lock (_shoutLock)
                        {
                            double wait = 125 - (DateTime.UtcNow - _lastShoutout).TotalSeconds; if (wait > 0) Thread.Sleep((int)Math.Min(wait, 130) * 1000);
                            string code = TwitchApi.Call(HttpMethod.Post, "/chats/shoutouts?from_broadcaster_id={bid}&to_broadcaster_id=" + uid + "&moderator_id=" + TwitchApi.BroadcasterId(), null, out d, out err);
                            _lastShoutout = DateTime.UtcNow; extra = code == "204" ? ", Twitch shoutout sent" : ", Twitch shoutout refused (HTTP " + code + (err != "" ? ": " + err : "") + ")";
                        }
                    }
                    return "shoutout ready for " + ctx["shoutoutUser"] + " (" + ctx["shoutoutGame"] + ")" + extra;
                }
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

        // ---------------- presets that replace the Streamer.bot actions (all created DISABLED, once) ----------------
        static JObject Act(string id, string name, string group, string note, JArray triggers, params JObject[] steps)
        {
            return new JObject { { "id", id }, { "name", name }, { "group", group }, { "enabled", false }, { "importNotes", note }, { "triggers", triggers }, { "conditions", new JArray() }, { "steps", new JArray(steps) } };
        }
        static JObject SayStep(string text) { return new JObject { { "type", "say" }, { "as", "core" }, { "text", text } }; }
        static JObject Tr(string type, params object[] kv) { var o = new JObject { { "type", type } }; for (int i = 0; i + 1 < kv.Length; i += 2) o[(string)kv[i]] = JToken.FromObject(kv[i + 1]); return o; }
        static JObject Step(string type, params object[] kv) { return Tr(type, kv); }
        static JObject Latest() { return Step("run_action", "name", "Alerts: show Latest Group"); }

        /// <summary>Streamer.bot replacement presets (Docs\STREAMERBOT_REPLACEMENT.md). Remembered in "seeded", so deleting one sticks.</summary>
        public static void SeedStreamerBotPresets()
        {
            try
            {
                var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray();
                if (seeded.Any(v => (string)v == "sbreplace1")) return;
                var acts = (JArray)doc["actions"]; const string G = "Streamer.bot replacement";
                string disc = "https://discord.gg/be6bus4GKh";
                var list = new List<JObject> {
                    Act("sb-latest", "Alerts: show Latest Group", G, "preset: shows the 'Latest Group' source in scene 'Alerts' for 10 s (called by the alert actions). Check the scene/source names in OBS.", new JArray { Tr("manual") },
                        Step("obs_source", "scene", "Alerts", "source", "Latest Group", "visible", "true"), Step("delay", "ms", 10000), Step("obs_source", "scene", "Alerts", "source", "Latest Group", "visible", "false")),
                    Act("sb-follow", "Alert: follow", G, "preset from Streamer.bot 'Followed'", new JArray { Tr("follow") }, SayStep("innoce108Cool Hello {user} just followed! Welcome to the community! innoce108Hello"), Latest()),
                    Act("sb-sub", "Alert: sub", G, "preset from Streamer.bot 'Normal/Super/Prime'. Twitch does not say which subs are Prime.", new JArray { Tr("sub") }, SayStep("🐧 Thank you for the sub, {user}! Enjoy the stream!"), Latest()),
                    Act("sb-resub", "Alert: resub", G, "preset from Streamer.bot 'Resub'", new JArray { Tr("resub") }, SayStep("🐧 {user} resubbed with a tier {tier} sub! Thank you. I appreciate you!"), Latest()),
                    Act("sb-gift", "Alert: gifted subs", G, "preset from Streamer.bot 'Gifted' (Twitch sends one event per gift bomb)", new JArray { Tr("gift") }, SayStep("🎁 {user} gifted {total} sub(s)! innoce108Cool"), Latest()),
                    Act("sb-cheer", "Alert: cheer", G, "preset from Streamer.bot 'Cheers'", new JArray { Tr("cheer") }, SayStep("{user} cheered {bits} bits!"), Latest()),
                    Act("sb-title-customs", "Title: customs with viewers", G, "preset from 'RL (customs)'. Day number = variable dayCounter. Edit the text and category.",
                        new JArray { Tr("command", "names", new JArray("!setcustoms"), "permission", "mod") },
                        Step("set_title", "title", "CUSTYs w/ Viewers🎮Day {var:dayCounter}🔥GC2👑DROPS✅Collegiate RL🎮🎵Music !sr🎵!discord !hr @InnocentPenguin_ 🕖5pm CDT DAILY!!", "game", "Rocket League"), SayStep("Title updated.")),
                    Act("sb-title-mc", "Title: Minecraft community server", G, "preset from 'MC Community Server': switch title, wait 7 min, then the Day title.",
                        new JArray { Tr("command", "names", new JArray("!setmcserver"), "permission", "mod") },
                        Step("set_title", "title", "Switching to Minecraft🚨Starting Community Server! Day 1! 🌎 Join the SMP (Java + Bedrock)", "game", "Minecraft"), Step("delay", "ms", 420000),
                        Step("set_title", "title", "Starting Community Server! Day {var:dayCounter}! 🌎 Join the SMP (Java + Bedrock)")),
                    Act("sb-online", "Stream online", G, "preset from 'Stream Status (Online)'. Also restarts the First 5 game.", new JArray { Tr("stream_online") }, SayStep("Stream is live! Let's go! 🐧")),
                    Act("sb-offline", "Stream offline", G, "preset from 'Stream Status (Offline)': goodnight + day counter +1. Set dayCounter first (Actions & Events > variables) so the Day number continues.", new JArray { Tr("stream_offline") },
                        SayStep("Stream offline. Goodnight everybody. Thanks for tuning in!"), Step("inc_var", "name", "dayCounter", "by", 1, "persist", true)),
                    Act("sb-clip", "Command: !clip", G, "preset from 'Clip'. Needs the clips:edit permission (sign the streamer in again).", new JArray { Tr("command", "names", new JArray("!clip"), "cooldownSec", 30) },
                        Step("create_clip"), SayStep("Clipped {clip.url}")),
                    Act("sb-preroll", "Command: !preroll / !ad", G, "preset from 'Preroll'. Needs channel:read:ads (sign the streamer in again).", new JArray { Tr("command", "names", new JArray("!preroll", "!ad", "!ads"), "cooldownSec", 20) },
                        Step("ad_schedule"), SayStep("Next ad in {adIn}. Preroll-free time left: {adPrerollFree}.")),
                    Act("sb-whyad", "Command: !whyad", G, "preset from 'Whyad'", new JArray { Tr("command", "names", new JArray("!whyad", "!whyads"), "cooldownSec", 30) },
                        SayStep("Sorry for the ad! Twitch does not allow affiliates to disable ads, so creators choose between ads when you join or during the stream. I chose to run 3 minutes during the stream so we don't lose any newcomers to ads.")),
                    Act("sb-ban", "Alert: ban (Among Us ejected)", G, "preset from 'Add Ban'. Set the browser source name below to your 'Ban Alert' source. Needs the ban event (re-sign the streamer in).", new JArray { Tr("ban") },
                        Step("obs_request", "request", "SetInputSettings", "data", new JObject { { "inputName", "Ban Alert - Among Us Ejected" }, { "inputSettings", new JObject { { "url", "file://C:\\Users\\ivanm\\Documents\\amongusban\\Browser Sources\\among-uspure-css\\index.html?user={user}" } } } }),
                        Step("obs_source", "scene", "Ban Alert", "source", "Ban Alert - Among Us Ejected", "visible", "true"), Step("delay", "ms", 900),
                        Step("sound", "file", "C:\\Users\\ivanm\\Documents\\amongusban\\Sounds\\eject_amongus.mp3", "volume", 0.9), Step("delay", "ms", 4100),
                        Step("obs_source", "scene", "Ban Alert", "source", "Ban Alert - Among Us Ejected", "visible", "false")),
                    Act("sb-raidout", "Raid out", G, "preset from 'Raid Out Start/End'. WARNING: the last step stops the stream 20 s later, like Streamer.bot did. Delete it if you do not want that.", new JArray { Tr("raid_out") },
                        SayStep("Raid started! Prepare your emotes! innoce108Arrive innoce108W innoce108Danceydance innoce108Pinguinoraid innoce108Pinguinoraid innoce108Pinguinoraid innoce108Hype innoce108Hello innoce108W"),
                        Step("delay", "ms", 3000), SayStep("Don't forget to join the community Discord! Hang out, chat, share media, receive updates → " + disc),
                        Step("delay", "ms", 20000), Step("obs_request", "request", "StopStream")),
                    Act("sb-shout", "Command: !shout", G, "preset from 'Shoutout • Pronoun Support'. Pronouns are not looked up. 'native' also sends Twitch's own shoutout (needs moderator:manage:shoutouts).", new JArray { Tr("command", "names", new JArray("!shout", "!so"), "permission", "mod") },
                        Step("shoutout", "user", "{arg1}", "native", true), SayStep("Go and follow {shoutoutUser}! They were last seen streaming {shoutoutGame}. You can find them at {shoutoutChannel}")),
                    Act("sb-endstream", "Reward: Instantly End Stream", G, "preset from the 'Instantly End Stream' reward (2,500,000 points). Needs channel:read:redemptions.", new JArray { Tr("redeem", "title", "Instantly End Stream") },
                        SayStep("{user} ended the stream. Goodbye! 🐧"), Step("delay", "ms", 5000), Step("obs_request", "request", "StopStream")),
                    Act("sb-suggest", "Reward: Suggestion Box", G, "preset from the 'Suggestion' reward: saves each suggestion to Data\\runtime\\files\\suggestions.txt.", new JArray { Tr("redeem", "title", "Suggestion") },
                        Step("inc_var", "name", "suggestions", "by", 1, "persist", true), Step("append_file", "file", "suggestions.txt", "text", "{count} {user} - {input}"), SayStep("Thanks {user}, suggestion saved!")),
                };
                foreach (var a in list) if (!acts.OfType<JObject>().Any(o => (string)o["id"] == (string)a["id"])) acts.Add(a);
                seeded.Add("sbreplace1"); doc["seeded"] = seeded; Save(doc);
            }
            catch (Exception ex) { Clog.Warn("automation", "seeding Streamer.bot replacement presets failed: " + ex.Message); }
        }
    }
}
