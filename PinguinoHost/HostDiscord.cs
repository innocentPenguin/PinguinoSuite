using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Discord go-live announcements (owner: 170 - Discord). One rich webhook message per stream in the announcements channel; optionally edited to "stream ended" when the stream goes offline.
    ///  * Follows LiveState (Twitch /streams, else OBS/forced): a poll loop, not an event, so it is idempotent across Host restarts and Twitch blips.
    ///  * Once per stream: the state file remembers the stream key (Twitch stream id, else the local day) and the posted message id. A restart while live never re-posts.
    ///  * Secret: the webhook URL lives OUTSIDE git: env PINGUINO_DISCORD_WEBHOOK, else Data\runtime\bots_secrets.json {"discord":{"WebhookUrl":...}} (gitignored). Never logged, never in /api output.
    ///  * Settings (not secret): Data\runtime\discord.json {Enabled, DryRun, RoleId, ...}. Enabled=false and DryRun=true are the defaults: nothing reaches Discord until both are flipped.
    ///  * Sim Host: only a loopback webhook (tests) is ever called. DryRun logs the payload to host.jsonl / the console instead of sending.
    ///  * Mods: !discordtest [status|dry|send|end] (audited). API: GET /api/discord, POST /api/discord/settings, POST /api/discord/test {mode}, POST /api/discord/secret {webhook}.</summary>
    public static class DiscordAnnounce
    {
        static readonly object L = new object();
        static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        static bool _started; static DateTime _offlineSince = DateTime.MinValue; static string _lastResult = ""; static DateTime _lastResultAt = DateTime.MinValue;
        public static Func<string, string, JObject, JObject> TestHttp;   // test hook: (method, url, body) -> {code, json}; replaces the network
        public const string WebhookEnv = "PINGUINO_DISCORD_WEBHOOK";

        static string SetP { get { return Path.Combine(HostApi.DataDir, "discord.json"); } }
        static string StateP { get { return Path.Combine(HostApi.DataDir, "discord_state.json"); } }
        static string SecretsP { get { return Path.Combine(HostApi.DataDir, "bots_secrets.json"); } }

        // ================= settings =================
        public static JObject Defaults()
        {
            return new JObject {
                { "note", "Discord go-live announcements. Enabled=false or DryRun=true means nothing is posted (DryRun writes the payload to the log instead). The webhook URL is NOT here: env PINGUINO_DISCORD_WEBHOOK or bots_secrets.json discord.WebhookUrl." },
                { "Enabled", false }, { "DryRun", true },
                { "Login", "innocentpenguin_" }, { "Streamer", "innocentpenguin_" },
                { "RoleId", "" },                                    // a role id to ping, or "everyone" / "here"; empty = no ping
                { "Content", "{ping} {streamer} is LIVE on Twitch!" },  // the plain line above the embed; {ping} = the role mention (or nothing)
                { "Description", "Playing **{game}**\n{link}" },
                { "Color", 16744192 },                               // 0xFF8000 Penguino orange
                { "Thumbnail", "boxart" },                           // boxart | none  (small image, right side)
                { "Image", "preview" },                              // preview | none (big image: the live Twitch preview)
                { "Username", "PinguinoB0t" }, { "AvatarUrl", "" },
                { "EditOnOffline", true }, { "OfflineText", "Stream ended. Thanks for watching, see you next time!" }, { "OfflineGraceSec", 180 },
                { "MinGapMin", 30 },                                 // a new stream key less than this after the last post is a blip: no second post
                { "TestChannelNote", "" } };
        }
        public static JObject Settings()
        {
            var d = Defaults();
            try { if (File.Exists(SetP)) foreach (var p in JObject.Parse(File.ReadAllText(SetP, Encoding.UTF8))) d[p.Key] = p.Value; else File.WriteAllText(SetP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            return d;
        }
        static readonly string[] Editable = { "Enabled", "DryRun", "Login", "Streamer", "RoleId", "Content", "Description", "Color", "Thumbnail", "Image", "Username", "AvatarUrl", "EditOnOffline", "OfflineText", "OfflineGraceSec", "MinGapMin", "TestChannelNote" };
        /// <summary>POST /api/discord/settings: only known keys, types coerced; never the webhook.</summary>
        public static JObject SaveSettings(JObject body)
        {
            var d = Settings(); int n = 0;
            foreach (var p in (body ?? new JObject()).Properties())
            {
                if (!Editable.Contains(p.Name)) continue;
                var cur = d[p.Name];
                if (cur.Type == JTokenType.Boolean) d[p.Name] = p.Value.Type == JTokenType.Boolean ? (bool)p.Value : string.Equals((string)p.Value, "true", StringComparison.OrdinalIgnoreCase);
                else if (cur.Type == JTokenType.Integer) { long v; if (long.TryParse(Convert.ToString(p.Value), out v)) d[p.Name] = v; else continue; }
                else d[p.Name] = ((string)p.Value ?? "").Trim();
                n++;
            }
            string rid = ((string)d["RoleId"] ?? "").Trim().TrimStart('@'); if (rid != "" && rid != "everyone" && rid != "here" && !rid.All(char.IsDigit)) return new JObject { { "ok", false }, { "error", "RoleId must be a numeric role id, everyone, here or empty" } };
            d["RoleId"] = rid;
            try { File.WriteAllText(SetP, d.ToString(), new UTF8Encoding(false)); } catch (Exception ex) { return new JObject { { "ok", false }, { "error", ex.Message } }; }
            Clog.Info("discord", "settings saved (" + n + " keys): enabled " + (bool)d["Enabled"] + ", dry-run " + (bool)d["DryRun"]);
            return Api();
        }

        // ================= secret =================
        /// <summary>the webhook URL (env wins, then bots_secrets.json). Empty = not configured. Never logged.</summary>
        public static string Webhook(out string source)
        {
            source = "none";
            string e = (Environment.GetEnvironmentVariable(WebhookEnv) ?? "").Trim(); if (e != "") { source = "env"; return e; }
            try { if (File.Exists(SecretsP)) { var j = JObject.Parse(File.ReadAllText(SecretsP, Encoding.UTF8)); string w = ((string)(j["discord"] as JObject)?["WebhookUrl"] ?? "").Trim(); if (w != "") { source = "file"; return w; } } } catch (Exception) { }
            return "";
        }
        public static bool ValidWebhook(string url)
        {
            if (string.IsNullOrEmpty(url)) return false;
            if (url.StartsWith("https://discord.com/api/webhooks/") || url.StartsWith("https://discordapp.com/api/webhooks/") || url.StartsWith("https://ptb.discord.com/api/webhooks/") || url.StartsWith("https://canary.discord.com/api/webhooks/")) return true;
            return HostApi.SimMode && url.StartsWith("http://127.0.0.1:");   // tests: a fake webhook on loopback
        }
        /// <summary>POST /api/discord/secret {webhook}: stores it in bots_secrets.json (gitignored). Empty string removes it. The value is never echoed back.</summary>
        public static JObject SetSecret(JObject body)
        {
            string w = ((string)(body ?? new JObject())["webhook"] ?? "").Trim();
            if (w != "" && !ValidWebhook(w)) return new JObject { { "ok", false }, { "error", "that is not a Discord webhook URL (https://discord.com/api/webhooks/...)" } };
            try
            {
                JObject j = new JObject(); if (File.Exists(SecretsP)) { try { j = JObject.Parse(File.ReadAllText(SecretsP, Encoding.UTF8)); } catch (Exception) { j = new JObject(); } }
                var d = j["discord"] as JObject; if (d == null) { d = new JObject(); j["discord"] = d; }
                if (w == "") d.Remove("WebhookUrl"); else d["WebhookUrl"] = w;
                string tmp = SecretsP + ".tmp"; File.WriteAllText(tmp, j.ToString(), new UTF8Encoding(false)); if (File.Exists(SecretsP)) File.Replace(tmp, SecretsP, null); else File.Move(tmp, SecretsP);
            }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", ex.Message } }; }
            Clog.Info("discord", w == "" ? "webhook removed" : "webhook stored in bots_secrets.json");
            return Api();
        }

        // ================= state =================
        static JObject _state;
        static JObject State() { lock (L) { if (_state != null) return _state; try { if (File.Exists(StateP)) _state = JObject.Parse(File.ReadAllText(StateP, Encoding.UTF8)); } catch (Exception) { } if (_state == null) _state = new JObject(); return _state; } }
        static void SaveState() { lock (L) { try { File.WriteAllText(StateP, _state.ToString(), new UTF8Encoding(false)); } catch (Exception) { } } }
        public static void TestResetState() { lock (L) { _state = new JObject(); _offlineSince = DateTime.MinValue; try { if (File.Exists(StateP)) File.Delete(StateP); } catch (Exception) { } } }

        /// <summary>what identifies "this stream": the Twitch stream id when the live check comes from Twitch; else one key per local day (OBS / forced).</summary>
        public static string StreamKey() { string id = LiveState.StreamId; return !string.IsNullOrEmpty(id) ? "twitch:" + id : "day:" + DateTime.Now.ToString("yyyy-MM-dd"); }

        // ================= status =================
        public static string ConfigState()
        {
            string src; string w = Webhook(out src); var s = Settings();
            if (w == "") return "not configured";
            if (!ValidWebhook(w)) return "invalid webhook";
            if (!(bool)s["Enabled"]) return "disabled";
            if ((bool)s["DryRun"]) return "dry-run";
            return "armed";
        }
        public static JObject Api()
        {
            string src; string w = Webhook(out src); var s = Settings(); var st = State();
            var o = new JObject { { "ok", true }, { "state", ConfigState() }, { "webhookConfigured", w != "" }, { "webhookSource", src }, { "webhookValid", w != "" && ValidWebhook(w) },
                { "live", LiveState.Live }, { "streamKey", LiveState.Live == true ? StreamKey() : null },
                { "posted", new JObject { { "streamKey", (string)st["streamKey"] }, { "messageId", (string)st["messageId"] }, { "postedAt", (string)st["postedAt"] }, { "endedAt", (string)st["endedAt"] } } },
                { "lastResult", _lastResult }, { "lastResultAgoSec", _lastResultAt == DateTime.MinValue ? (int?)null : (int)(DateTime.UtcNow - _lastResultAt).TotalSeconds },
                { "settings", new JObject() } };
            foreach (var k in Editable) o["settings"][k] = s[k];
            return o;
        }
        public static string StatusLine()
        {
            var st = State(); string cs = ConfigState();
            string last = string.IsNullOrEmpty((string)st["postedAt"]) ? "nothing posted yet" : "last post " + (string)st["postedAt"] + ((string)st["endedAt"] != null && (string)st["endedAt"] != "" ? " (edited to ended)" : "");
            return "Discord go-live: " + cs + (cs == "not configured" ? " (no webhook URL: env " + WebhookEnv + " or bots_secrets.json discord.WebhookUrl)" : "") + ", stream " + (LiveState.Live == true ? "live" : "offline") + ", " + last + (_lastResult != "" ? ", last result: " + _lastResult : "") + ".";
        }

        // ================= payload =================
        static string Fill(string t, IDictionary<string, string> v) { if (t == null) return ""; foreach (var kv in v) t = t.Replace("{" + kv.Key + "}", kv.Value ?? ""); return t; }
        /// <summary>the webhook body for a live post. stream = the Twitch /streams object (may be null: title/game unknown). Pure.</summary>
        public static JObject BuildLive(JObject stream, JObject s, bool test)
        {
            string login = ((string)s["Login"] ?? "innocentpenguin_").Trim().TrimStart('@'); string link = "https://twitch.tv/" + login;
            string title = (string)stream?["title"] ?? ""; string game = (string)stream?["game_name"] ?? ""; string gameId = (string)stream?["game_id"] ?? ""; string viewers = Convert.ToString(stream?["viewer_count"] ?? "");
            if (title == "") title = "Live on Twitch"; if (game == "") game = "Rocket League";
            string rid = (string)s["RoleId"] ?? ""; string ping = rid == "" ? "" : rid == "everyone" || rid == "here" ? "@" + rid : "<@&" + rid + ">";
            var v = new Dictionary<string, string> { { "ping", ping }, { "streamer", (string)s["Streamer"] ?? login }, { "login", login }, { "link", link }, { "title", title }, { "game", game }, { "viewers", viewers } };
            string content = Fill((string)s["Content"], v).Trim(); if (test) content = "[TEST, ignore] " + content;
            var embed = new JObject { { "title", (test ? "[TEST] " : "") + title }, { "url", link }, { "description", Fill((string)s["Description"], v) }, { "color", (long)(s["Color"] ?? 16744192) },
                { "fields", new JArray { new JObject { { "name", "Game" }, { "value", game }, { "inline", true } }, new JObject { { "name", "Watch" }, { "value", link }, { "inline", true } } } },
                { "footer", new JObject { { "name", "f" } } }, { "timestamp", DateTime.UtcNow.ToString("o") } };
            embed["footer"] = new JObject { { "text", test ? "PinguinoSuite test post" : "PinguinoSuite go-live" } };
            long t = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            if ((string)s["Image"] == "preview") embed["image"] = new JObject { { "url", "https://static-cdn.jtvnw.net/previews-ttv/live_user_" + login.ToLowerInvariant() + "-1280x720.jpg?t=" + t } };
            if ((string)s["Thumbnail"] == "boxart" && gameId != "") embed["thumbnail"] = new JObject { { "url", "https://static-cdn.jtvnw.net/ttv-boxart/" + gameId + "-285x380.jpg" } };
            var allowed = new JObject { { "parse", new JArray() } };
            if (rid == "everyone" || rid == "here") allowed["parse"] = new JArray("everyone"); else if (rid != "") allowed["roles"] = new JArray(rid);
            if (test) allowed = new JObject { { "parse", new JArray() } };   // a test never pings anybody
            var body = new JObject { { "content", content }, { "embeds", new JArray { embed } }, { "allowed_mentions", allowed } };
            string un = (string)s["Username"] ?? ""; if (un != "") body["username"] = un; string av = (string)s["AvatarUrl"] ?? ""; if (av.StartsWith("https://")) body["avatar_url"] = av;
            return body;
        }
        /// <summary>the PATCH body that turns the live post into "stream ended": same embed, no image, grey, no ping.</summary>
        public static JObject BuildEnded(JObject s, JObject liveBody)
        {
            var e = (JObject)((liveBody?["embeds"] as JArray)?.FirstOrDefault()?.DeepClone() ?? new JObject { { "title", "Stream ended" } });
            e.Remove("image"); e["color"] = 6710886; e["description"] = (string)s["OfflineText"] ?? "Stream ended."; e["footer"] = new JObject { { "text", "PinguinoSuite: stream ended " + DateTime.Now.ToString("HH:mm") } };
            string content = ((string)liveBody?["content"] ?? ""); content = System.Text.RegularExpressions.Regex.Replace(content, @"<@&\d+>|@everyone|@here", "").Trim();
            return new JObject { { "content", content == "" ? "Stream ended." : content + " (ended)" }, { "embeds", new JArray { e } }, { "allowed_mentions", new JObject { { "parse", new JArray() } } } };
        }

        // ================= HTTP =================
        /// <summary>POST (new message, ?wait=true so Discord returns the message id) or PATCH (edit). Returns {ok, code, id, error}. Dry run and sim never reach a non-loopback host.</summary>
        static JObject Send(string method, string url, JObject body, bool dry)
        {
            string shown = body.ToString(Newtonsoft.Json.Formatting.None); if (shown.Length > 900) shown = shown.Substring(0, 900) + "...";
            if (dry) { Clog.Info("discord", "DRY RUN " + method + " (webhook not called): " + shown); if (HostApi.SimMode) Console.WriteLine("[discord] dry " + method + " " + shown); return new JObject { { "ok", true }, { "dry", true }, { "code", 0 }, { "id", "" } }; }
            if (TestHttp != null) { var r = TestHttp(method, url, body); return new JObject { { "ok", (int)r["code"] >= 200 && (int)r["code"] < 300 }, { "code", (int)r["code"] }, { "id", (string)r["json"]?["id"] ?? "" }, { "error", (string)r["error"] ?? "" } }; }
            if (HostApi.SimMode && !url.StartsWith("http://127.0.0.1:")) return new JObject { { "ok", false }, { "code", 0 }, { "error", "sim Host: Discord is never called" } };
            for (int attempt = 0; attempt < 2; attempt++)
            {
                try
                {
                    var rq = new HttpRequestMessage(new HttpMethod(method), url) { Content = new StringContent(body.ToString(Newtonsoft.Json.Formatting.None), Encoding.UTF8, "application/json") };
                    var r = Http.SendAsync(rq).Result; int code = (int)r.StatusCode; string txt = r.Content.ReadAsStringAsync().Result;
                    if (code == 429 && attempt == 0) { double wait = 2; try { wait = Math.Min(10, (double)(JObject.Parse(txt)["retry_after"] ?? 2)); } catch (Exception) { } Thread.Sleep((int)(wait * 1000) + 250); continue; }
                    JObject j = null; try { j = JObject.Parse(txt); } catch (Exception) { }
                    string err = r.IsSuccessStatusCode ? "" : code == 404 ? "webhook not found (deleted?)" : code == 401 || code == 403 ? "webhook refused (HTTP " + code + ")" : "HTTP " + code + (j != null && j["message"] != null ? ": " + (string)j["message"] : "");
                    return new JObject { { "ok", r.IsSuccessStatusCode }, { "code", code }, { "id", (string)j?["id"] ?? "" }, { "error", err } };
                }
                catch (Exception ex) { return new JObject { { "ok", false }, { "code", 0 }, { "error", ex.Message.Length > 160 ? ex.Message.Substring(0, 160) : ex.Message } }; }
            }
            return new JObject { { "ok", false }, { "code", 429 }, { "error", "rate limited twice" } };
        }
        static void Result(string r) { _lastResult = r; _lastResultAt = DateTime.UtcNow; }

        // ================= the loop =================
        public static void Start(bool sim)
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(sim ? 3000 : 20000); while (true) { try { Tick(); } catch (Exception ex) { Clog.Warn("discord", "tick failed: " + ex.Message); } await Task.Delay(sim ? 1000 : 10000); } });
        }
        /// <summary>one poll of the live state: post once per stream key when live; after OfflineGraceSec offline, edit the post to "ended" once.</summary>
        public static void Tick()
        {
            bool? live = LiveState.Live; if (live == null) return;
            var s = Settings(); if (!(bool)s["Enabled"]) return;
            string src; string w = Webhook(out src); if (w == "" || !ValidWebhook(w)) return;   // not configured: silent (the status says so)
            var st = State();
            if (live == true)
            {
                _offlineSince = DateTime.MinValue; string key = StreamKey();
                if ((string)st["streamKey"] == key) return;   // this stream is already announced (also after a Host restart)
                DateTime last; if (DateTime.TryParse((string)st["postedAt"], null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out last) && (DateTime.UtcNow - last).TotalMinutes < (double)(long)(s["MinGapMin"] ?? 30))
                { if ((string)st["blipKey"] != key) { st["blipKey"] = key; SaveState(); Clog.Info("discord", "stream key changed within MinGapMin after the last post: treated as a blip, no second announcement"); } return; }
                var body = BuildLive(LiveState.Stream, s, false); bool dry = (bool)s["DryRun"];
                var r = Send("POST", w + (w.Contains("?") ? "&" : "?") + "wait=true", body, dry);
                if (!(bool)r["ok"]) { Result("post failed: " + (string)r["error"]); Clog.Warn("discord", "go-live post failed: " + (string)r["error"]); if ((int)r["code"] == 404 || (int)r["code"] == 401 || (int)r["code"] == 403) { st["streamKey"] = key; SaveState(); } return; }   // a dead webhook: give up for this stream, no retry storm
                lock (L) { st["streamKey"] = key; st["messageId"] = (string)r["id"] ?? ""; st["postedAt"] = DateTime.UtcNow.ToString("o"); st["endedAt"] = ""; st["dry"] = dry; st["liveBody"] = body; st.Remove("blipKey"); }
                SaveState(); Result(dry ? "dry-run post logged" : "posted (message " + (string)r["id"] + ")"); Clog.Info("discord", (dry ? "DRY RUN go-live announcement for " : "go-live announcement posted for ") + key);
                return;
            }
            // offline
            if (string.IsNullOrEmpty((string)st["streamKey"]) || !string.IsNullOrEmpty((string)st["endedAt"])) return;
            if (!(bool)s["EditOnOffline"]) return;
            if (_offlineSince == DateTime.MinValue) { _offlineSince = DateTime.UtcNow; return; }
            if ((DateTime.UtcNow - _offlineSince).TotalSeconds < (double)(long)(s["OfflineGraceSec"] ?? 180)) return;
            string mid = (string)st["messageId"] ?? ""; bool wasDry = (bool?)st["dry"] == true;
            var ended = BuildEnded(s, st["liveBody"] as JObject);
            var er = wasDry || mid == "" ? Send("PATCH", w + "/messages/dry", ended, true) : Send("PATCH", w + "/messages/" + mid, ended, (bool)s["DryRun"]);
            lock (L) { st["endedAt"] = DateTime.UtcNow.ToString("o"); }   // once, even when the edit failed (the message may be gone)
            SaveState(); Result((bool)er["ok"] ? "edited to ended" : "end edit failed: " + (string)er["error"]); Clog.Info("discord", (bool)er["ok"] ? "go-live post edited to 'stream ended'" : "end edit failed: " + (string)er["error"]);
        }

        // ================= tests (mods) =================
        public static bool IsCommand(string cmd) { return cmd == "!discordtest" || cmd == "!discordstatus"; }
        /// <summary>!discordtest [status|dry|send|end]: status (default) | dry = log the payload | send = post a [TEST] message to the real webhook (no ping) | end = edit the last real post to "ended" now.</summary>
        public static string Handle(string user, string cmd, string[] args)
        {
            string mode = cmd == "!discordstatus" ? "status" : args.Length == 0 ? "status" : args[0].ToLowerInvariant();
            return (string)Test(mode)["text"];
        }
        /// <summary>POST /api/discord/test {mode}: the same as the chat command; {ok, text, payload?}</summary>
        public static JObject Test(string mode)
        {
            mode = (mode ?? "status").ToLowerInvariant(); var s = Settings(); string src; string w = Webhook(out src);
            if (mode == "status" || mode == "") return new JObject { { "ok", true }, { "text", StatusLine() } };
            if (mode == "dry" || mode == "payload")
            {
                var body = BuildLive(LiveState.Stream, s, true); Send("POST", w, body, true);
                string t = (string)body["embeds"][0]["title"]; return new JObject { { "ok", true }, { "text", "Discord dry run logged (host.jsonl, source discord): \"" + (string)body["content"] + "\" / " + t + " / " + (string)body["embeds"][0]["fields"][0]["value"] + ". State: " + ConfigState() + "." }, { "payload", body } };
            }
            if (w == "") return new JObject { { "ok", false }, { "text", "Discord go-live: not configured (no webhook URL). Add it with POST /api/discord/secret or bots_secrets.json discord.WebhookUrl, or env " + WebhookEnv + "." } };
            if (!ValidWebhook(w)) return new JObject { { "ok", false }, { "text", "Discord go-live: the stored webhook is not a discord.com/api/webhooks URL." } };
            if (mode == "send" || mode == "post")
            {
                var body = BuildLive(LiveState.Stream, s, true);
                var r = Send("POST", w + (w.Contains("?") ? "&" : "?") + "wait=true", body, false); Result((bool)r["ok"] ? "test post ok" : "test post failed: " + (string)r["error"]);
                Clog.Info("discord", (bool)r["ok"] ? "test post sent (message " + (string)r["id"] + ")" : "test post failed: " + (string)r["error"]);
                return new JObject { { "ok", (bool)r["ok"] }, { "text", (bool)r["ok"] ? "Discord test post sent (marked [TEST], no ping). Delete it in Discord when seen. State: " + ConfigState() + "." : "Discord test post failed: " + (string)r["error"] }, { "id", (string)r["id"] } };
            }
            if (mode == "end" || mode == "ended")
            {
                var st = State(); string mid = (string)st["messageId"] ?? "";
                if (mid == "" || (bool?)st["dry"] == true) return new JObject { { "ok", false }, { "text", "Discord: no real go-live post to edit (" + (mid == "" ? "nothing posted" : "the last post was a dry run") + ")." } };
                if (!string.IsNullOrEmpty((string)st["endedAt"])) return new JObject { { "ok", false }, { "text", "Discord: the last go-live post was already edited to ended." } };
                var r = Send("PATCH", w + "/messages/" + mid, BuildEnded(s, st["liveBody"] as JObject), false);
                if ((bool)r["ok"]) { lock (L) st["endedAt"] = DateTime.UtcNow.ToString("o"); SaveState(); }
                Result((bool)r["ok"] ? "edited to ended (manual)" : "end edit failed: " + (string)r["error"]);
                return new JObject { { "ok", (bool)r["ok"] }, { "text", (bool)r["ok"] ? "Discord go-live post edited to 'stream ended'." : "Discord end edit failed: " + (string)r["error"] } };
            }
            return new JObject { { "ok", false }, { "text", "Usage: !discordtest [status | dry | send | end]" } };
        }
    }
}
