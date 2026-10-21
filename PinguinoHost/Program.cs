using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.WebSockets;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>
    /// PinguinoHost - runs PinguinoB0t, PinguinoChat, HelperPinguino and PinguinoRouter without Streamer.bot.
    /// Usage:  PinguinoHost [--sim] [--channel name] [--data dir] [--suite dir] [--no-sync]
    ///   --sim   read "user: text" lines from the keyboard instead of Twitch ("*user:" = mod, "#user:" = broadcaster)
    /// Twitch secrets (never printed) live in  data\host_secrets.json :  {"Channel","ClientId","UserToken","SenderId","BroadcasterId"}
    /// </summary>
    public static class Program
    {
        static HostCPH cph;
        public static bool HasAction(string n) { return cph != null && cph.ActionExists(n); }
        public static bool SayShared(string m) { try { return cph != null && cph.Say != null && cph.Say(m); } catch (Exception) { return false; } }
        static string suite, dataDir;
        public static string SuiteDir { get { return suite; } }
        public static bool ObsScene(string s) { return cph != null && cph.ObsSetScene(s); }
        public static bool ObsRaw(string type, JObject data) { return cph != null && cph.Obs != null && cph.Obs.Request(type, data); }
        public static bool ObsSource(string scene, string source, string v) { if (cph == null) return false; return v == "toggle" ? cph.Obs != null && cph.Obs.Toggle(scene, source) : v == "false" ? cph.ObsHideSource(scene, source) : cph.ObsShowSource(scene, source); }
        /// <summary>a new stream starts the First 5 game again (what Streamer.bot's Stream Status (Online) action did).</summary>
        public static void ResetFirsts()
        {
            if (cph == null) return;
            cph.SetGlobalVar("firstChatterPlace", 1, true); cph.SetGlobalVar("firstChatterClaimedUserIds", "[]", true); cph.SetGlobalVar("firstChatterWinners", "{}", true);
            Clog.Info("firsts", "First 5 game reset for the new stream");
        }
        public static JObject ObsData(string type, JObject data) { try { return cph?.Obs?.Data(type, data); } catch (Exception) { return null; } }
        public static bool TimeoutUser(string user, int secs, string why) { return cph != null && cph.TwitchTimeoutUser(user, secs, why, false); }
        public static List<string> CoreCommandList() { return coreCommands.OrderBy(x => x).ToList(); }
        static HashSet<string> coreCommands = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        static readonly object dispatchLock = new object();
        static readonly Dictionary<string, string> sources = new Dictionary<string, string>
        {
            { "PinguinoBot", @"PinguinoB0t\PinguinoBotCore.cs" }, { "PinguinoChat", @"PinguinoChat\PinguinoChat.cs" },
            { "PinguinoHelper", @"HelperPinguino\PinguinoHelper.cs" }, { "PinguinoRouter", @"Shared\PinguinoRouter.cs" },
            { "PinguinoFirsts", @"PinguinoB0t\PinguinoBotFirsts.cs" },   // the First 5 game (!first, !firsts, and the claim on every chat line)
        };

        public static int Main(string[] argv)
        {
            Console.OutputEncoding = Encoding.UTF8;
            string Opt(string n, string d) { int i = Array.IndexOf(argv, n); return i >= 0 && i + 1 < argv.Length ? argv[i + 1] : d; }
            bool sim = argv.Contains("--sim");
            suite = Opt("--suite", FindSuite());
            dataDir = Opt("--data", Environment.GetEnvironmentVariable("PINGUINO_DATA_DIR") ?? Environment.GetEnvironmentVariable("BVQ_DATA_DIR") ?? Path.Combine(suite, "Data", "runtime"));
            Directory.CreateDirectory(dataDir); Clog.Init(dataDir);
            if (!Lease.TakeMutex(dataDir)) { Console.WriteLine("Another PinguinoHost is already running on this PC for " + dataDir + "; exiting."); Clog.Error("lease", "another Host already runs on this PC; this one exits"); return 3; } Clog.Info("host", "PinguinoHost starting");
            Environment.SetEnvironmentVariable("PINGUINO_DATA_DIR", dataDir); Environment.SetEnvironmentVariable("BVQ_DATA_DIR", dataDir);   // the bots find bots.json, bots_secrets.json, settings.json, routing.log here
            Vault.Refresh();   // the key vault (when the core launched us); plaintext files remain the fallback
            var secrets = LoadSecrets();
            string channel = Opt("--channel", secrets.Value<string>("Channel") ?? "");

            cph = HostCPH.Current = new HostCPH(dataDir);
            Vault.PushToBots(cph); Vault.StartLoop(() => Vault.PushToBots(cph));
            if (!LoadModules()) return 2;
            if (!sim) WireTwitch(secrets);
            WireServices(secrets, sim);
            Lease.Start(); Lease.StartStreamingReporter(() => cph.ObsStreaming()); if (!sim) Auto.StartTimers(); Auto.SeedDefaults(); Auto.SeedStreamerBotPresets(); SiteFeed.Start(); SiteTeach.Start(); LobbyPush.Start(); Redeems.Start(); SiteCommands.Start(); EventLog.Start(); Replays.Start(); SiteShop.Start(); OverlayChat.Start(); CompatWs.Start(); SpotifyAnnounce.Start(); StartChatTicker(sim); LiveState.Start(cph, sim ? 2 : 20); SubBoard.Start(); SubsImport.Start(); Streaks.Start(); Boards.Start(); Emotes.Start(); Timers.Start(); StreamTimers.Start(); Reminders.Start(); Economy.Start(); ProfileSync.Start();

            Console.WriteLine("PinguinoHost ready. data=" + dataDir + (sim ? "  [SIM: type  user: text ]" : "  channel=#" + channel));
            if (!argv.Contains("--no-sync")) StartSyncTimer();
            if (sim) { SimLoop(); return 0; }
            if (channel == "") { Console.WriteLine("No channel yet: open http://127.0.0.1:" + HostApi.Port + "/setup to configure."); Thread.Sleep(Timeout.Infinite); }
            ReadChatForever(channel).GetAwaiter().GetResult();
            return 0;
        }

        static string FindSuite() { var d = new DirectoryInfo(AppContext.BaseDirectory); while (d != null && !File.Exists(Path.Combine(d.FullName, "Shared", "PinguinoRouter.cs"))) d = d.Parent; return d != null ? d.FullName : @"D:\PinguinoSuite"; }
        static JObject LoadSecrets()
        {
            JObject o; try { var f = Path.Combine(dataDir, "host_secrets.json"); o = File.Exists(f) ? JObject.Parse(File.ReadAllText(f)) : new JObject(); } catch (Exception) { o = new JObject(); }
            foreach (var k in new[] { "UserToken", "ObsPassword" }) if (string.IsNullOrEmpty((string)o[k])) { var v = Vault.Get("HOST_SECRETS." + k); if (v != "") o[k] = v; }   // memory only: never saved back
            return o;
        }

        // ---------------- compile each bot file as its own assembly (what Streamer.bot does per action) ----------------
        static bool LoadModules()
        {
            var refs = new List<MetadataReference>();
            foreach (string a in ((string)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")).Split(Path.PathSeparator))
                if (File.Exists(a)) refs.Add(MetadataReference.CreateFromFile(a));
            refs.Add(MetadataReference.CreateFromFile(typeof(Program).Assembly.Location));
            bool ok = true;
            foreach (var kv in sources)
            {
                string path = Path.Combine(suite, kv.Value);
                string code = File.ReadAllText(path, Encoding.UTF8);
                if (kv.Key == "PinguinoBot") foreach (Match m in Regex.Matches(code, "case \"(![a-z0-9]+)\"")) coreCommands.Add(m.Groups[1].Value);
                code = Regex.Replace(code, @"(?m)^public class CPHInline\s*$", "public class CPHInline : PinguinoHost.HostBase");
                var comp = CSharpCompilation.Create("pg_" + kv.Key + "_" + Guid.NewGuid().ToString("N"),
                    new[] { CSharpSyntaxTree.ParseText(code, new CSharpParseOptions(LanguageVersion.Latest)) }, refs,
                    new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, nullableContextOptions: NullableContextOptions.Disable));
                using (var ms = new MemoryStream())
                {
                    var res = comp.Emit(ms);
                    if (!res.Success)
                    {
                        ok = false;
                        Console.WriteLine("COMPILE FAILED: " + kv.Key);
                        foreach (var d in res.Diagnostics.Where(d => d.Severity == DiagnosticSeverity.Error).Take(8)) Console.WriteLine("  " + d);
                        continue;
                    }
                    var asm = Assembly.Load(ms.ToArray());
                    var type = asm.GetType("CPHInline");
                    var inst = Activator.CreateInstance(type);
                    var exec = type.GetMethod("Execute");
                    cph.Actions[kv.Key] = c => (bool)exec.Invoke(inst, null);
                    Console.WriteLine("loaded " + kv.Key + "  (" + kv.Value + ")");
                }
            }
            // Native action for the First 5 payout: the script puts {login, amount, id, reason} in the global "pinguino.grant.request" and runs this. The id makes a retry harmless.
            cph.Actions["PinguinoGrantPoints"] = c =>
            {
                try
                {
                    var req = JObject.Parse(c.GetGlobalVar<string>("pinguino.grant.request", false) ?? "{}");
                    var r = Economy.Grant(new JObject { { "target", "user" }, { "login", (string)req["login"] }, { "amount", req["amount"] }, { "mode", "add" }, { "id", (string)req["id"] }, { "reason", (string)req["reason"] }, { "by", "firsts" } });
                    Clog.Info("firsts", "payout " + (string)req["login"] + ": " + (string)(r["message"] ?? r["error"]));
                    return (bool?)r["ok"] != false;
                }
                catch (Exception ex) { Clog.Warn("firsts", "payout failed: " + ex.Message); return false; }
            };
            return ok;
        }

        /// <summary>every few seconds: lets ChattyPinguino run its time-based jobs (pre-stream countdown) even when nobody is chatting.</summary>
        public static void StartChatTicker(bool sim)
        {
            Task.Run(async () => { await Task.Delay(8000); while (true) { try { if (Lease.MayRun && (sim || HostApi.IrcConnected)) ChatTick(); } catch (Exception) { } await Task.Delay(sim ? 1000 : 5000); } });
        }
        public static void ChatTick()
        {
            lock (dispatchLock)
            {
                cph.Args.Clear(); cph.Args["pgTick"] = true;
                try { if (cph.Actions.ContainsKey("PinguinoChat")) cph.RunAction("PinguinoChat"); } catch (Exception ex) { Console.WriteLine("ERROR tick: " + ex.Message); }
            }
        }

        // ---------------- dispatch: exactly the Streamer.bot trigger ownership in Docs\TRIGGERS.md ----------------
        public static void Dispatch(string user, string text, string msgId, int role, string userId, bool firstMsg, string replyTo, bool isSub = false, int subTier = 0)
        {
            if (!Lease.MayRun) return;
            try { if (subTier > 0) { SubBoard.Note(user, subTier); Intro.OnChat(user, subTier); } } catch (Exception ex) { Clog.Warn("intro", "intro check failed: " + ex.Message); }   // not the master Host (or lease lost): never run the bots
            try { Roster.Note(user, role, isSub); } catch (Exception) { }
            try { Welcome.OnChat(user, firstMsg, s => { if (HostApi.SimMode) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } }); } catch (Exception ex) { Clog.Warn("welcome", "welcome check failed: " + ex.Message); }   // delayed welcome bonus for a first-ever chatter
            try { Economy.OnChat(user, text, s => ChannelLore.Say(s)); } catch (Exception) { }
            try { if (!Control.Synthetic) ChatFeed.Add(user, text, role, isSub, subTier); } catch (Exception) { }
            try { EventLog.OnChat(user, text, role); } catch (Exception) { }   // Master View chat panel (last 200 lines in memory)
            try { LiveLog.Record(user, userId, text, (text ?? "").TrimStart().StartsWith("!")); } catch (Exception) { }   // every line, every user, always (Data\chat_logs\live)
            try { if (CmdProfiles.Gate(user, text, role, isSub, subTier)) return; } catch (Exception ex) { Clog.Warn("cmdprofiles", "command gate failed: " + ex.Message); }   // edited tier / disabled / archived / cooldown: silent
            try { bool swallowed; text = CmdFix.Fix(user, text, m => { if (HostApi.SimMode) Console.WriteLine("[say] " + m); else { string via; HostApi.SendAs("core", m, out via); } }, out swallowed); if (swallowed) return; } catch (Exception ex) { Clog.Warn("cmdfix", "typo check failed: " + ex.Message); }   // "! join", "!jon", "!rejoin" -> !join; near misses answer once
            try { if (FeatureCommands.Handle(user, text, role, s => { if (HostApi.SimMode) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } })) return; } catch (Exception ex) { Clog.Warn("commands", "leaderboard command failed: " + ex.Message); }
            try { if (Streaks.Handle(user, text, s => { if (HostApi.SimMode) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } })) return; } catch (Exception ex) { Clog.Warn("streaks", "streak command failed: " + ex.Message); }
            try { if (PgCommand.Handle(user, text, role)) return; } catch (Exception ex) { Clog.Warn("pg", "!pg failed: " + ex.Message); }
            try { if (Auto.OnChat(user, text, role, isSub, firstMsg, msgId, replyTo, subTier)) return; } catch (Exception ex) { Clog.Warn("automation", "chat trigger failed: " + ex.Message); }   // an Actions & Events command took it
            try { if (ChannelLore.OnChat(user, text, role, ChannelLore.Say)) return; } catch (Exception ex) { Clog.Warn("lore", "channel lore failed: " + ex.Message); }   // a clear question the channel's own commands answer
            try { if (BotMention.OnChat(user, text, role, s => { if (HostApi.SimMode) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } })) return; } catch (Exception ex) { Clog.Warn("mention", "mention reply failed: " + ex.Message); }   // @PinguinoB0t about the stream or a moderation situation
            lock (dispatchLock)   // one message at a time: arguments are shared state, so no two chats can mix
            {
                cph.Args.Clear();
                string login = user.ToLowerInvariant();
                cph.Args["user"] = user; cph.Args["userName"] = login; cph.Args["userId"] = userId ?? "";
                cph.Args["message"] = text; cph.Args["rawInput"] = text; cph.Args["msgId"] = msgId ?? Guid.NewGuid().ToString("N");
                cph.Args["role"] = role; cph.Args["isModerator"] = role >= 3; cph.Args["isBroadcaster"] = role >= 4; cph.Args["isVip"] = role == 2;
                cph.Args["firstMessage"] = firstMsg;
                if (!string.IsNullOrEmpty(replyTo)) { cph.Args["reply.userName"] = replyTo; cph.Args["reply.userLogin"] = replyTo; }
                try
                {
                    string trimmed = text.Trim();
                    string first = trimmed.Split(' ')[0];
                    if (Cutover.On)   // the First 5 game pays points: only once Streamer.bot is retired, or both would pay
                    {
                        if (first.ToLowerInvariant() == "!first" || first.ToLowerInvariant() == "!firsts") { cph.Args["command"] = first.ToLowerInvariant(); cph.RunAction("PinguinoFirsts"); return; }
                        try
                        {
                            int before = cph.GetGlobalVar<int>("firstChatterPlace", true); cph.Args.Remove("command"); cph.RunAction("PinguinoFirsts"); int after = cph.GetGlobalVar<int>("firstChatterPlace", true);
                            if (before >= 1 && after != before) Latest.Record("first5", new Dictionary<string, string> { { "user", user }, { "place", (after == 0 ? 5 : before).ToString() } });
                        }
                        catch (Exception ex) { Clog.Warn("firsts", "First 5 claim failed: " + ex.Message); }
                    }
                    if (first.StartsWith("!") && coreCommands.Contains(first))
                    {
                        cph.Args["command"] = first.ToLowerInvariant();
                        cph.Args["rawInput"] = trimmed.Length > first.Length ? trimmed.Substring(first.Length).Trim() : "";   // Streamer.bot: rawInput = text after the command
                        cph.RunAction("PinguinoBot");
                    }
                    else cph.RunAction("PinguinoRouter");
                }
                catch (Exception ex) { Console.WriteLine("ERROR dispatch: " + ex); }
            }
        }

        // OBS, Twitch events and the overlay web server (what Streamer.bot used to provide).
        static void WireServices(JObject s, bool sim)
        {
            if ((!sim || Environment.GetEnvironmentVariable("PINGUINO_OBS") == "1") && (s.Value<bool?>("ObsEnabled") ?? true))   // sim skips OBS unless a test sets PINGUINO_OBS=1 (mock-obs)
            { cph.Obs = new ObsClient(s.Value<string>("ObsHost") ?? "127.0.0.1", s.Value<int?>("ObsPort") ?? 4455, s.Value<string>("ObsPassword") ?? ""); Task.Run(() => cph.Obs.RunForever()); ObsTree.Start(); }
            CarryOverApiKey();
            HostApi.DataDir = dataDir; HostApi.Port = s.Value<int?>("OverlayPort") ?? 8770; HostApi.SimMode = sim; if (!sim) HostApi.StartPrestreamLoop(); HostApi.ObsConnected = () => cph.ObsIsConnected();
            string overlayDir = null;
            try { var f = Path.Combine(dataDir, "settings.json"); if (File.Exists(f)) overlayDir = JObject.Parse(File.ReadAllText(f)).Value<string>("OverlayDir"); } catch (Exception) { }
            OverlayServer.Start(HostApi.Port, overlayDir, Path.Combine(suite, "PinguinoB0t", "overlays"), dataDir);
            if (!sim) Task.Run(() => EventSub.RunForever(s, a => DispatchEvent(a)));
        }

        // After a data-folder move the AI key can be blank in the new chat_settings.json while the legacy %AppData%\BVQ copy still has it: copy it across once (never logged).
        static void CarryOverApiKey()
        {
            try
            {
                var legacy = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "BVQ", "chat_settings.json");
                var cur = Path.Combine(dataDir, "chat_settings.json");
                if (!File.Exists(legacy) || !File.Exists(cur) || Path.GetFullPath(legacy) == Path.GetFullPath(cur)) return;
                var c = JObject.Parse(File.ReadAllText(cur)); var l = JObject.Parse(File.ReadAllText(legacy));
                if (!string.IsNullOrWhiteSpace((string)c["ApiKey"]) || string.IsNullOrWhiteSpace((string)l["ApiKey"])) return;
                c["ApiKey"] = l["ApiKey"]; if (string.IsNullOrEmpty((string)c["Provider"])) c["Provider"] = l["Provider"];
                var tmp = cur + ".tmp"; File.WriteAllText(tmp, c.ToString()); File.Replace(tmp, cur, null);
                Console.WriteLine("INFO  carried the AI key over from the legacy data folder into chat_settings.json");
            }
            catch (Exception e) { Console.WriteLine("WARN  AI key carry-over failed: " + e.Message); }
        }

        public static void DispatchEvent(Dictionary<string, object> args)
        {
            if (!Lease.MayRun) return;
            try { Boards.OnEvent(args); } catch (Exception) { }
            try { Control.OnEvent(args); } catch (Exception) { }
            try { StreamTimers.OnEvent(args); } catch (Exception) { }
            try { Announce.OnEvent(args); } catch (Exception) { }
            try { ProfileSync.OnEvent(args); } catch (Exception) { }
            try { Auto.OnEvent(args); } catch (Exception ex) { Clog.Warn("automation", "event trigger failed: " + ex.Message); }
            object et0; if (args.TryGetValue("eventType", out et0) && !new[] { "TwitchSub", "TwitchReSub", "TwitchGiftBomb", "TwitchCheer", "TwitchRaid", "TwitchFollow" }.Contains(Convert.ToString(et0))) return;   // automation-only events
            lock (dispatchLock)
            {
                cph.Args.Clear(); foreach (var kv in args) cph.Args[kv.Key] = kv.Value;
                if (args.ContainsKey("userName")) cph.Args["user"] = args["userName"];
                try { cph.RunAction("PinguinoChat"); } catch (Exception ex) { Console.WriteLine("ERROR event: " + ex); }
            }
        }

        static Timer _syncTimer;   // a static field: a local timer is garbage collected and silently stops
        static void StartSyncTimer()   // the "PinguinoBot Web Sync" timed action (every 3 s)
        {
            _syncTimer = new Timer(_ =>
            {
                if (!Monitor.TryEnter(dispatchLock)) return;
                try { cph.Args.Clear(); cph.Args["timerName"] = "PinguinoBot Web Sync"; cph.RunAction("PinguinoBot"); }
                catch (Exception ex) { Clog.Warn("sync", "web sync tick failed: " + ex.Message); }
                finally { Monitor.Exit(dispatchLock); }
            }, null, 3000, 3000);

        }

        // ---------------- simulation (no Twitch, no tokens) ----------------
        static void SimLoop()
        {
            string line; int n = 0;
            while ((line = Console.ReadLine()) != null)
            {
                if (line.StartsWith("@") && line.Contains(" USERNOTICE #")) { Streaks.OnUserNotice(line); continue; }   // sim: a raw IRC USERNOTICE line
                if (line.StartsWith("eventsub ")) { var q = line.Split(new[] { ' ' }, 3); try { EventSub.Simulate(q[1], q[2], x => DispatchEvent(x)); } catch (Exception ex) { Console.WriteLine("ERROR eventsub: " + ex.Message); } continue; }
                if (line.StartsWith("event "))   // sim: event TwitchSub alice 2   (3rd word = tier / bits / viewers)
                { var p = line.Split(' '); string v = p.Length > 3 ? p[3] : "1"; DispatchEvent(new Dictionary<string, object> { { "eventType", p[1] }, { "userName", p.Length > 2 ? p[2] : "x" }, { "tier", v }, { "total", v }, { "bits", v }, { "viewers", v }, { "moderator", p.Length > 4 ? p[4] : "" }, { "title", "Song Request" }, { "input", v }, { "redemptionId", "red-" + v }, { "rewardId", "rw1" } }); continue; }   // TwitchRedeem: 3rd word = the song text
                int c = line.IndexOf(':'); if (c < 1) continue;
                string who = line.Substring(0, c).Trim(); int role = 1;
                if (who.StartsWith("*")) { role = 3; who = who.Substring(1); } else if (who.StartsWith("#")) { role = 4; who = who.Substring(1); } else if (who.StartsWith("%")) { role = 2; who = who.Substring(1); }   // sim: "%alice: hi" = a VIP
                bool simFirst = false; if (who.StartsWith("^")) { simFirst = true; who = who.Substring(1); }   // sim: "^alice: hi" = alice's first message ever (Twitch first-msg flag)
                int simTier = 0; if (who.StartsWith("$") && who.Length > 2 && char.IsDigit(who[1])) { simTier = who[1] - '0'; who = who.Substring(2); }   // sim: "$2alice: hi" = a tier 2 sub
                HostApi.Messages++; HostApi.LastMessage = DateTime.UtcNow;
                ChatStats.Note(who, role);
                Dispatch(who, line.Substring(c + 1).Trim(), "sim-" + (++n), role, "id-" + who.ToLowerInvariant(), simFirst, null, false, simTier);
            }
        }

        // ---------------- Twitch: read chat (anonymous IRC over WebSocket), speak through helix with PinguinoB0t's token ----------------
        static void WireTwitch(JObject s)
        {
            string tok = s.Value<string>("UserToken"), cid = s.Value<string>("ClientId"), sid = s.Value<string>("SenderId"), bid = s.Value<string>("BroadcasterId");
            if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid) || string.IsNullOrEmpty(sid) || string.IsNullOrEmpty(bid)) { Console.WriteLine("(no Twitch send credentials: replies are printed only)"); return; }
            var http = new HttpClient();
            HttpRequestMessage Req(HttpMethod m, string url, JObject body)
            {
                var r = new HttpRequestMessage(m, url);
                r.Headers.Add("Authorization", "Bearer " + tok); r.Headers.Add("Client-Id", cid);
                if (body != null) r.Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json");
                return r;
            }
            cph.Say = m =>
            {
                if (!Lease.MayRun) return false;
                if (HostApi.SaidRecently(m)) return true;   // never the same line twice
                var resp = http.SendAsync(Req(HttpMethod.Post, HostApi.Helix + "/chat/messages", new JObject { { "broadcaster_id", bid }, { "sender_id", sid }, { "message", m } })).Result;
                if (!resp.IsSuccessStatusCode) Clog.Warn("twitch", "chat send refused by Twitch (HTTP " + (int)resp.StatusCode + (resp.StatusCode == (System.Net.HttpStatusCode)429 ? ", rate limited" : resp.StatusCode == System.Net.HttpStatusCode.Unauthorized ? ", token rejected - sign in again" : "") + ")");
                return resp.IsSuccessStatusCode;
            };
            cph.Timeout = (user, secs, why) =>
            {
                var g = http.SendAsync(Req(HttpMethod.Get, HostApi.Helix + "/users?login=" + Uri.EscapeDataString(user), null)).Result;
                var first = (JObject.Parse(g.Content.ReadAsStringAsync().Result)["data"] as JArray)?.FirstOrDefault();
                string uid = first == null ? null : (string)first["id"]; if (uid == null) return false;
                var body = new JObject { { "data", new JObject { { "user_id", uid }, { "duration", secs }, { "reason", why } } } };
                return http.SendAsync(Req(HttpMethod.Post, HostApi.Helix + "/moderation/bans?broadcaster_id=" + bid + "&moderator_id=" + sid, body)).Result.IsSuccessStatusCode;
            };
        }

        static async Task ReadChatForever(string channel)
        {
            int backoff = 2;
            while (true)
            {
                while (!Lease.MayRun) await Task.Delay(1500);
                var lt = Lease.Token;
                try
                {
                    using (var ws = new ClientWebSocket())
                    {
                        await ws.ConnectAsync(new Uri("wss://irc-ws.chat.twitch.tv:443"), lt);
                        async Task Send(string l) { await ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(l + "\r\n")), WebSocketMessageType.Text, true, CancellationToken.None); }
                        await Send("CAP REQ :twitch.tv/tags twitch.tv/commands");
                        await Send("NICK justinfan" + new Random().Next(10000, 99999));
                        await Send("JOIN #" + channel.ToLowerInvariant());
                        Console.WriteLine("connected to #" + channel); Clog.Info("twitch", "chat connected (read)"); backoff = 2; HostApi.IrcConnected = true;
                        var buf = new byte[16384]; var sb = new StringBuilder();
                        while (ws.State == WebSocketState.Open)
                        {
                            var r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), lt);
                            if (r.MessageType == WebSocketMessageType.Close) break;
                            sb.Append(Encoding.UTF8.GetString(buf, 0, r.Count));
                            if (!r.EndOfMessage) continue;
                            foreach (string line in sb.ToString().Split(new[] { "\r\n" }, StringSplitOptions.RemoveEmptyEntries))
                            {
                                if (line.StartsWith("PING")) { await Send("PONG :tmi.twitch.tv"); continue; }
                                HandleIrc(line);
                            }
                            sb.Clear();
                        }
                    }
                }
                catch (Exception ex) { Console.WriteLine("chat connection lost: " + ex.Message); Clog.Warn("twitch", "chat connection lost: " + ex.Message); }
                HostApi.IrcConnected = false;
                Console.WriteLine("reconnecting in " + backoff + "s"); await Task.Delay(backoff * 1000); backoff = Math.Min(backoff * 2, 60);
            }
        }

        static readonly Regex Privmsg = new Regex(@"^@(?<tags>\S+) :(?<nick>[^!]+)![^ ]+ PRIVMSG #\S+ :(?<msg>.*)$", RegexOptions.Compiled);
        static void HandleIrc(string line)
        {
            if (line.Contains(" USERNOTICE #")) { if (Lease.MayRun) Streaks.OnUserNotice(line); return; }   // sub, resub, raid, watch streak ...: kept, never dropped
            var m = Privmsg.Match(line); if (!m.Success) return;
            var tags = m.Groups["tags"].Value.Split(';').Select(t => t.Split(new[] { '=' }, 2)).Where(a => a.Length == 2).ToDictionary(a => a[0], a => a[1], StringComparer.Ordinal);
            string T(string k) { string v; return tags.TryGetValue(k, out v) ? v : ""; }
            HostApi.Messages++; HostApi.LastMessage = DateTime.UtcNow;
            ChatStats.Note(m.Groups["nick"].Value, T("badges").Contains("broadcaster/") ? 4 : T("mod") == "1" ? 3 : T("badges").Contains("vip/") ? 2 : 1);
            string msg = m.Groups["msg"].Value; if (msg.StartsWith("\u0001ACTION ")) msg = msg.Substring(8).TrimEnd('\u0001');
            int role = T("badges").Contains("broadcaster/") ? 4 : T("mod") == "1" ? 3 : T("badges").Contains("vip/") ? 2 : 1;
            string display = T("display-name") != "" ? T("display-name") : m.Groups["nick"].Value;
            string reply = T("reply-parent-user-login");
            Task.Run(() => Dispatch(display, msg, T("id"), role, T("user-id"), T("first-msg") == "1", reply, T("subscriber") == "1", Intro.TierFromBadges(T("badges"))));
        }
    }
}
