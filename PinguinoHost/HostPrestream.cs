using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Sockets;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    // GET /api/prestream: one non-destructive readiness list for the Suite's prestream checks: [{id,label,status pass|warn|fail,detail}]. No chat message is sent.
    public static partial class HostApi
    {
        static readonly string IdBase = Environment.GetEnvironmentVariable("PINGUINO_ID_BASE") ?? "https://id.twitch.tv";

        static JObject Item(string id, string label, string status, string detail)
        { return new JObject { { "id", id }, { "label", label }, { "status", status }, { "detail", detail ?? "" } }; }

        // id.twitch.tv/oauth2/validate tells login, scopes and seconds left without touching chat
        static JObject Validate(HttpClient http, string tok, string cid)
        {
            try
            {
                var rq = new HttpRequestMessage(HttpMethod.Get, IdBase + "/oauth2/validate"); rq.Headers.Add("Authorization", "OAuth " + tok);
                var r = http.SendAsync(rq).Result;
                if (r.StatusCode == System.Net.HttpStatusCode.Unauthorized) return new JObject { { "ok", false }, { "error", "token rejected or expired - sign in again" } };
                if (!r.IsSuccessStatusCode) return new JObject { { "ok", false }, { "error", "Twitch answered HTTP " + (int)r.StatusCode } };
                var j = JObject.Parse(r.Content.ReadAsStringAsync().Result); j["ok"] = true; return j;
            }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", "could not reach Twitch: " + ex.Message } }; }
        }
        static string Left(JObject v) { int s = (int?)v["expires_in"] ?? 0; return s <= 0 ? "" : s >= 86400 ? (s / 86400) + " d left" : s >= 3600 ? (s / 3600) + " h left" : (s / 60) + " min left"; }

        static JObject Prestream()
        {
            var items = new List<JObject>(); var s = LoadV();
            var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
            string chan = ((string)s["Channel"] ?? "").Trim();

            // 1. live connections
            items.Add(Item("chat", "Chat connected (reading #" + (chan == "" ? "?" : chan) + ")", IrcConnected ? "pass" : "fail", IrcConnected ? "" : "not connected to Twitch chat"));
            bool haveCreds = !string.IsNullOrEmpty((string)s["UserToken"]) && !string.IsNullOrEmpty((string)s["ClientId"]) && !string.IsNullOrEmpty((string)s["BroadcasterId"]);
            items.Add(Item("eventsub", "EventSub connected (follows, subs, raids)", EventSubConnected && EventSubRefused == 0 ? "pass" : haveCreds ? "fail" : "warn", EventSubConnected ? (EventSubRefused == 0 ? "" : EventSubRefused + " event subscriptions refused by Twitch (token or scopes): sign in as streamer again") : haveCreds ? "not connected" : "needs the streamer sign-in"));

            var ls = Lease.State(); string lst = (string)ls["state"];
            if (lst != "none") items.Add(Item("master", "This device is the master (only the master runs the bots)", lst == "master" ? "pass" : "fail", lst == "master" ? "" : "not confirmed as master" + ((string)ls["error"] != "" ? ": " + (string)ls["error"] : "")));

            // 2. accounts: the streamer token and every bot account, all checked with OAuth validate
            var checks = new List<Task<JObject>>(); var names = new List<string>();
            var sec = BotSecretsV(); var reg = LoadFile("bots.json");
            if (!string.IsNullOrEmpty((string)s["UserToken"])) { string t = (string)s["UserToken"], c = (string)s["ClientId"]; names.Add("streamer"); checks.Add(Task.Run(() => Validate(http, t, c))); }
            foreach (string role in BotIds)
            {
                var sr = sec[role] as JObject; string t = (string)sr?["UserToken"]; if (string.IsNullOrEmpty(t)) continue;
                names.Add(role); string c = (string)sr["ClientId"]; checks.Add(Task.Run(() => Validate(http, t, c)));
            }
            Task.WaitAll(checks.ToArray(), 3500);
            var vres = new Dictionary<string, JObject>();
            for (int i = 0; i < names.Count; i++) vres[names[i]] = checks[i].IsCompleted ? checks[i].Result : new JObject { { "ok", false }, { "error", "Twitch did not answer in time" } };

            if (vres.TryGetValue("streamer", out var sv))
                items.Add(sv.Value<bool>("ok") ? Item("streamer", "Streamer account signed in (" + (string)sv["login"] + ")", ((int?)sv["expires_in"] ?? 0) < 4 * 3600 ? "warn" : "pass", Left(sv))
                                               : Item("streamer", "Streamer account signed in", "fail", (string)sv["error"]));
            else items.Add(Item("streamer", "Streamer account signed in", "fail", "not signed in (Host page > Sign in as streamer)"));
            if (vres.TryGetValue("streamer", out var sv0) && sv0.Value<bool>("ok"))
            {
                var have = new HashSet<string>(((sv0["scopes"] as JArray) ?? new JArray()).Select(x => (string)x)); var lack = Scopes.Split(' ').Where(x => !have.Contains(x)).ToList();
                var sci = Item("scopes", "Streamer permissions complete (events, clips, ads, shoutouts)", lack.Count == 0 ? "pass" : "warn", lack.Count == 0 ? "" : "missing: " + string.Join(", ", lack) + " (sign the streamer in again)");
                if (lack.Count > 0) sci["fix"] = new JObject { { "label", "Re-sign Twitch" }, { "route", "accounts" } };
                items.Add(sci);
                var lag = Lag.Stats(); if ((int)lag["samples"] > 5) items.Add(Item("latency", "Twitch events arrive fast", (int)lag["medianMs"] < 1500 ? "pass" : "warn", "median " + (int)lag["medianMs"] + " ms, worst " + (int)lag["maxMs"] + " ms over " + (int)lag["samples"] + " messages"));
            }

            foreach (string role in BotIds)
            {
                string title = (string)reg["Bots"]?[role]?["Title"] ?? role; bool on = (bool?)reg["Bots"]?[role]?["Enabled"] != false;
                if (!on) { items.Add(Item("bot-" + role, title + " switched on", "warn", "switched off")); continue; }
                if (vres.TryGetValue(role, out var bv))
                {
                    if (!bv.Value<bool>("ok")) { items.Add(Item("bot-" + role, title + " can speak as its own account", "fail", (string)bv["error"])); continue; }
                    string scopes = string.Join(" ", ((JArray)bv["scopes"] ?? new JArray()).Select(x => (string)x));
                    bool canSend = scopes.Contains("user:write:chat");
                    string left = Left(bv);
                    items.Add(Item("bot-" + role, title + " speaks as " + (string)bv["login"], !canSend ? "fail" : ((int?)bv["expires_in"] ?? 0) < 4 * 3600 ? "warn" : "pass", !canSend ? "token lacks the user:write:chat scope - sign in again" : left));
                }
                else
                {
                    string acct = (string)reg["Bots"]?[role]?["Account"] ?? "";
                    items.Add(Item("bot-" + role, title + " has its own account", role == "core" ? "fail" : "warn", role == "core" ? "not signed in: it would speak as the shared account" : "no account of its own: speaks through the first bot in its fallback chain that has one"));
                }
            }

            // 3. is the main bot a mod (timeouts need it)? the streamer token can list moderators only with the moderation:read scope
            try
            {
                var core = sec["core"] as JObject; string bid = (string)s["BroadcasterId"], sid = (string)core?["SenderId"], stok = (string)s["UserToken"], cid = (string)s["ClientId"];
                if (!string.IsNullOrEmpty(sid) && !string.IsNullOrEmpty(bid) && !string.IsNullOrEmpty(stok) && sid != bid)
                {
                    var rq = new HttpRequestMessage(HttpMethod.Get, Helix + "/moderation/moderators?broadcaster_id=" + bid + "&user_id=" + sid);
                    rq.Headers.Add("Authorization", "Bearer " + stok); rq.Headers.Add("Client-Id", cid);
                    var r = http.SendAsync(rq).Result;
                    if (r.IsSuccessStatusCode) { bool mod = ((JObject.Parse(r.Content.ReadAsStringAsync().Result)["data"] as JArray)?.Count ?? 0) > 0; items.Add(Item("mod", "PinguinoB0t is a channel mod (needed for timeouts)", mod ? "pass" : "fail", mod ? "" : "not a mod: type /mod pinguinob0t in chat")); }
                    else items.Add(Item("mod", "PinguinoB0t is a channel mod (needed for timeouts)", "warn", "cannot check (streamer token lacks moderation:read); verify in chat with /mods"));
                }
            }
            catch (Exception) { items.Add(Item("mod", "PinguinoB0t is a channel mod", "warn", "cannot check right now")); }

            // 4. bots loaded, OBS, Streamer.bot, AI, website facts
            var missing = new[] { "PinguinoBot", "PinguinoChat", "PinguinoHelper", "PinguinoRouter" }.Where(a => !Program.HasAction(a)).ToList();
            items.Add(Item("modules", "Bot modules loaded (core, chat, helper, router)", missing.Count == 0 ? "pass" : "fail", missing.Count == 0 ? "" : "missing: " + string.Join(", ", missing)));
            bool obsCfg = !string.IsNullOrEmpty((string)s["ObsPassword"]) || !string.IsNullOrEmpty((string)s["ObsHost"]);
            items.Add(Item("obs", "OBS connected", ObsConnected() ? "pass" : obsCfg ? "fail" : "warn", ObsConnected() ? "" : obsCfg ? "OBS WebSocket not reachable (is OBS open, WebSocket on?)" : "OBS is not set up in the Host (overlays/scenes need it)"));
            if (ObsConnected())
            {
                var rb = Program.ObsData("GetReplayBufferStatus", null); bool running = rb != null && ((bool?)rb["outputActive"] ?? false);
                items.Add(Item("replay", "OBS replay buffer running (!clip saves from it)", rb == null ? "warn" : running ? "pass" : "warn", rb == null ? "OBS did not answer" : running ? "" : "not running: start it in OBS (Controls > Start Replay Buffer), or !clip saves nothing"));
            }
            int sbPort = int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_SB_PORT"), out int sp) ? sp : 8080; bool sb = false;
            try { using (var tc = new TcpClient()) sb = tc.ConnectAsync("127.0.0.1", sbPort).Wait(700); } catch (Exception) { }
            items.Add(Item("streamerbot", "Streamer.bot reachable (legacy engine)", sb ? "pass" : "warn", sb ? "running on port " + sbPort : "not running: fine, the Host runs the bots, but old Streamer.bot actions will not fire"));

            var chatCfg = LoadFile("chat_settings.json"); bool key = !string.IsNullOrEmpty((string)chatCfg["ApiKey"]);
            items.Add(Item("ai", "AI key present for chat and helper", key ? "pass" : "fail", key ? ((string)chatCfg["Provider"] ?? "claude") + " / " + (string.IsNullOrEmpty((string)chatCfg["Model"]) ? "default model" : (string)chatCfg["Model"]) : "no ApiKey in chat_settings.json: the AI replies are off"));

            string furl = (string)LoadFile("helper_settings.json")["FactsUrl"] ?? "https://innocentpenguin.com/api/faq";
            if (furl.Trim() == "") items.Add(Item("faq", "Helper facts (innocentpenguin.com/api/faq)", "warn", "FactsUrl is blank: using helper_facts.json only"));
            else
            {
                try
                {
                    var r = http.GetAsync(furl).Result; string body = r.Content.ReadAsStringAsync().Result; int n = (JObject.Parse(body)["faq"] as JArray)?.Count ?? 0;
                    items.Add(Item("faq", "Helper facts (innocentpenguin.com/api/faq)", r.IsSuccessStatusCode && n > 0 ? "pass" : "warn", r.IsSuccessStatusCode ? n + " entries" : "HTTP " + (int)r.StatusCode + ": the helper uses its saved copy"));
                }
                catch (Exception ex) { items.Add(Item("faq", "Helper facts (innocentpenguin.com/api/faq)", "warn", "site not reachable (" + ex.GetType().Name + ": " + ex.Message + "): the helper uses its saved copy")); }
            }

            if (Vault.Enabled)
            {
                bool vr = Vault.Reach == "ok";
                items.Add(Item("vault", "Key vault readable (API keys and tokens)", vr ? "pass" : "warn", vr ? (Vault.Missing.Count == 0 ? "" : Vault.Missing.Count + " of " + Vault.Names.Length + " declared keys not in the vault yet (plaintext files still used)") : Vault.Reach + ": using the plaintext files"));
            }

            // 5. recent trouble
            if (Clog.LastErrorAt == DateTime.MinValue) items.Add(Item("errors", "No warnings or errors since the Host started", "pass", ""));
            else
            {
                int age = (int)(DateTime.UtcNow - Clog.LastErrorAt).TotalSeconds;
                items.Add(Item("errors", "Last warning or error", age < 1800 ? "warn" : "pass", (age < 90 ? age + " s" : age < 5400 ? age / 60 + " min" : age / 3600 + " h") + " ago: " + Clog.LastErrorText));
            }

            string worst = items.Any(i => (string)i["status"] == "fail") ? "fail" : items.Any(i => (string)i["status"] == "warn") ? "warn" : "pass";
            return new JObject { { "ok", true }, { "module", "host" }, { "status", worst }, { "ts", DateTime.UtcNow.ToString("o") }, { "items", new JArray(items) }, { "checks", new JArray(items.Select(i => (JObject)i.DeepClone())) } };
        }

        static JObject _psCache; static DateTime _psAt = DateTime.MinValue; static readonly object _psLock = new object();
        // served from a copy at most 90 s old (the core waits only 5 s); the same report is also written to console\prestream-host.json for the core's file mode
        public static JObject PrestreamCached() { lock (_psLock) { if (_psCache != null && (DateTime.UtcNow - _psAt).TotalSeconds < 90) return _psCache; } return PrestreamRefresh(); }
        static JObject PrestreamRefresh()
        {
            JObject r; try { r = Prestream(); } catch (Exception ex) { r = new JObject { { "ok", false }, { "status", "fail" }, { "items", new JArray { Item("host", "Host readiness check", "fail", ex.Message) } } }; }
            lock (_psLock) { _psCache = r; _psAt = DateTime.UtcNow; }
            try { var d = System.IO.Path.Combine(DataDir, "console"); System.IO.Directory.CreateDirectory(d); var f = System.IO.Path.Combine(d, "prestream-host.json"); var tmp = f + ".tmp"; System.IO.File.WriteAllText(tmp, r.ToString(Newtonsoft.Json.Formatting.None)); if (System.IO.File.Exists(f)) System.IO.File.Replace(tmp, f, null); else System.IO.File.Move(tmp, f); } catch (Exception) { }
            return r;
        }
        public static void StartPrestreamLoop() { Task.Run(async () => { await Task.Delay(4000); while (true) { try { PrestreamRefresh(); } catch (Exception) { } await Task.Delay(120000); } }); }
    }
}
