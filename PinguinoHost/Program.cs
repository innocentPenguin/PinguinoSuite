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
        public static string GetGlobal(string n) { return cph?.GetGlobalVar<string>(n, true); }
        static DateTime _botsAt = DateTime.MinValue;
        /// <summary>the bot logins (known list, bots.json, flagged profiles) as the global "pinguino.botlogins" for the game scripts, which have no access to the Host; at most once a minute</summary>
        public static void PublishBots() { try { if (cph == null || HostApi.DataDir == "" || (DateTime.UtcNow - _botsAt).TotalSeconds < 5) return; _botsAt = DateTime.UtcNow; cph.SetGlobalVar("pinguino.botlogins", "," + string.Join(",", Boards.AllBots()) + ",", false); } catch (Exception) { } }
        public static void SetGlobal(string n, string v) { cph?.SetGlobalVar(n, v, true); }
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
        public static bool? ObsStreamingNow() { try { return cph?.ObsStreaming(); } catch (Exception) { return null; } }   // null = OBS not connected / no answer
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
            Lease.Start(); Lease.StartStreamingReporter(() => cph.ObsStreaming()); if (!sim) Auto.StartTimers(); Links.Start(sim); Auto.SeedDefaults(); Task.Run(async () => { await Task.Delay(sim ? 2500 : 15000); Auto.RecoverHeldOffline(); }); Auto.SeedStreamerBotPresets(); SiteFeed.Start(); WheelEmoji.Start(); SiteTeach.Start(); LobbyPush.Start(); Redeems.Start(); SiteCommands.Start(); EventLog.Start(); Replays.Start(); SiteShop.Start(); Periods.Start(); SiteEconomy.Start(); ModAudit.Start(); StrikeCheckIn.Start(); GiftTags.Start(); SiteActivity.Start(); OverlayChat.Start(); CompatWs.Start(); SpotifyAnnounce.Start(); StartChatTicker(sim); LiveState.Start(cph, sim ? 2 : 20); SubBoard.Start(); SubsImport.Start(); Streaks.Start(); Boards.Start(); Emotes.Start(); Timers.Start(); StreamTimers.Start(); Reminders.Start(); Economy.Start(); ProfileSync.Start();

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
                    string who = ((string)req["login"] ?? "").ToLowerInvariant();
                    if (Boards.IsBot(who) || Boards.AllBots().Contains(who)) { Clog.Warn("firsts", "payout refused: " + who + " is a bot account (" + (string)req["reason"] + ")"); return false; }   // bots never get paid, whatever the game script decided
                    var r = Economy.Grant(new JObject { { "target", "user" }, { "login", (string)req["login"] }, { "amount", req["amount"] }, { "mode", "add" }, { "id", (string)req["id"] }, { "reason", (string)req["reason"] }, { "by", "firsts" } });
                    Clog.Info("firsts", "payout " + (string)req["login"] + ": " + (string)(r["message"] ?? r["error"]));
                    return (bool?)r["ok"] != false;
                }
                catch (Exception ex) { Clog.Warn("firsts", "payout failed: " + ex.Message); return false; }
            };
            PublishBots();
            return ok;
        }

        /// <summary>every few seconds: lets ChattyPinguino run its time-based jobs (pre-stream countdown) even when nobody is chatting.</summary>
        public static void StartChatTicker(bool sim)
        {
            PublishBots(); Task.Run(async () => { await Task.Delay(8000); while (true) { try { PublishBots(); if (Lease.MayRun && (sim || HostApi.IrcConnected)) ChatTick(); } catch (Exception) { } await Task.Delay(sim ? 1000 : 5000); } });
        }
        public static void ChatTick()
        {
            lock (dispatchLock)
            {
                cph.Args.Clear(); cph.Args["pgTick"] = true;
                try { if (cph.Actions.ContainsKey("PinguinoChat")) cph.RunAction("PinguinoChat"); } catch (Exception ex) { Console.WriteLine("ERROR tick: " + ex.Message); }
            }
        }

        /// <summary>chat from another platform (Multi -> POST /api/chat-in). Identity is namespaced ("yt:name") so it can never collide with a Twitch viewer; viewer role only; only the Actions &amp; Events commands run (no economy, points, strikes, firsts, moderation). Replies go back to that platform only (ReplyCtx.Platform).</summary>
        static readonly HashSet<string> ChatPlatforms = new HashSet<string> { "youtube", "tiktok", "kick", "facebook" };
        static string PlatformPrefix(string pf) { return pf == "youtube" ? "yt" : pf == "tiktok" ? "tt" : pf == "kick" ? "kk" : "fb"; }
        public static JObject DispatchExternal(string platform, string user, string userId, string text, string msgId, bool isBot)
        {
            if (!Lease.MayRun) return new JObject { { "ok", false }, { "ignored", "not the master Host" } };
            if (!ChatPlatforms.Contains(platform)) return new JObject { { "ok", false }, { "error", "platform must be one of: " + string.Join(", ", ChatPlatforms) } };
            user = (user ?? "").Trim().TrimStart('@'); text = (text ?? "").Trim();
            if (user == "" || text == "") return new JObject { { "ok", false }, { "error", "user and text required" } };
            if (isBot || HostApi.IsOwnBotName(user)) return new JObject { { "ok", true }, { "ignored", "own bot account" } };   // loop guard: the bots never answer themselves
            string login = PlatformUsers.Key(PlatformPrefix(platform), userId, user);   // the platform's stable id when Multi sends one (names change); the display name is kept beside it
            PlatformUsers.Remember(login, platform, user, userId);
            try
            {
                HostApi.Messages++;
                Console.WriteLine("[chat-in " + platform + "] " + user + ": " + (text.Length > 80 ? text.Substring(0, 80) : text));
                string uid = login;
                Task.Run(() => { try { Dispatch(login, text, msgId, 1, uid, false, null, false, 0, platform); HostApi.FlushForeign(); if (text.StartsWith("!")) { string cmd = text.Split(' ')[0]; if (cmd.Length > 30) cmd = cmd.Substring(0, 30); Clog.Info("chat-in", platform + " " + user + " (" + login + ") " + cmd + " -> " + ReplyCtx.OutSummary()); } if (platform == "tiktok") ReplyCtx.LogSilent(user, text); } catch (Exception ex) { Clog.Warn("chat-in", platform + " chat line failed: " + ex.Message); } finally { ReplyCtx.End(); } });
                return new JObject { { "ok", true } };
            }
            catch (Exception ex) { Clog.Warn("chat-in", platform + " chat line failed: " + ex.Message); return new JObject { { "ok", false }, { "error", "failed" } }; }
        }

        // ---------------- dispatch: exactly the Streamer.bot trigger ownership in Docs\TRIGGERS.md ----------------
        public static void Dispatch(string user, string text, string msgId, int role, string userId, bool firstMsg, string replyTo, bool isSub = false, int subTier = 0, string platform = "twitch", string colorTag = "", string badgeTag = "")
        {
            if (!Lease.MayRun) return;
            bool fx = platform != "twitch";   // chat from YouTube etc. (HostApi /api/chat-in): own namespaced identity, viewer role, answers go to that platform only; Twitch-only machinery below is skipped
            if (fx) ReplyCtx.BeginForeign(platform, msgId, user, true); else ReplyCtx.Begin(msgId, user);   // every reply made while handling this message is a native Twitch reply to it
            bool spamCand = false;
            bool botAcct = false; try { botAcct = BotAccounts.Is(user); } catch (Exception) { }   // a known bot account: counted as chat for logs and the Actions & Events triggers, but never as a viewer (points, welcome, First 5, boards)
            if (!fx) {
            try { if (SpamFirst.OnChat(user, text, role, isSub, subTier, firstMsg, out spamCand)) return; } catch (Exception ex) { Clog.Warn("spam", "first-message check failed: " + ex.Message); }   // link spam in a brand-new chatter's first line: dropped before any bot or bonus (off by default, Data\config\spam_first.json)
            try { if (subTier > 0) { SubBoard.Note(user, subTier); Intro.OnChat(user, subTier); } } catch (Exception ex) { Clog.Warn("intro", "intro check failed: " + ex.Message); }   // not the master Host (or lease lost): never run the bots
            try { if (!botAcct) Roster.Note(user, role, isSub); } catch (Exception) { }
            try { if (!botAcct) Welcome.OnChat(user, firstMsg, s => { if (HostApi.SimMode && !fx) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } }); } catch (Exception ex) { Clog.Warn("welcome", "welcome check failed: " + ex.Message); }   // delayed welcome bonus for a first-ever chatter
            try { if (!botAcct) Economy.OnChat(user, text, s => ChannelLore.Say(s)); } catch (Exception) { }
            try { if (!Control.Synthetic && !botAcct) { Periods.AddBuffered(user, "messages", 1); if (text.TrimStart().StartsWith("!")) Periods.AddBuffered(user, "commands", 1); } } catch (Exception) { }
            try { if (!Control.Synthetic && !botAcct) ChatFeed.Add(user, text, role, isSub, subTier, colorTag, badgeTag, userId); } catch (Exception) { }
            try { EventLog.OnChat(user, text, role); } catch (Exception) { }   // Master View chat panel (last 200 lines in memory)
            try { LiveLog.Record(user, userId, text, (text ?? "").TrimStart().StartsWith("!")); } catch (Exception) { }   // every line, every user, always (Data\chat_logs\live)
            }
            else   // YouTube / TikTok are full citizens: same points, boards, chat feed and logs as Twitch (key = "yt:id", display name beside it)
            {
                bool synth = false; try { synth = Control.Synthetic; } catch (Exception) { }
                string shown = PlatformUsers.Display(user); bool isCmd = (text ?? "").TrimStart().StartsWith("!");
                try { if (!botAcct) { Economy.NoteForeign(user); ChatStats.Note(user, 1); } } catch (Exception) { }
                try { if (PlatformUsers.TakeFresh(user) && !botAcct) Welcome.OnForeign(user, platform, text, s => { string via; HostApi.SendAs("core", s, out via); }); } catch (Exception ex) { Clog.Warn("welcome", "newcomer greeting failed: " + ex.Message); }   // new YouTube viewer: welcome + bonus in the same message as the answer to their line
                try { if (!synth && !botAcct) { Periods.AddBuffered(user, "messages", 1); if (isCmd) Periods.AddBuffered(user, "commands", 1); } } catch (Exception) { }
                try { if (!synth && !botAcct) ChatFeed.Add(user, text, 1, false, 0, "", "", userId, platform, shown); } catch (Exception) { }
                try { EventLog.OnChat(user, text, 1); } catch (Exception) { }
                try { LiveLog.Record(user, userId, text, isCmd, platform, shown); } catch (Exception) { }
            }
            try { if (CmdProfiles.Gate(user, text, role, isSub, subTier)) return; } catch (Exception ex) { Clog.Warn("cmdprofiles", "command gate failed: " + ex.Message); }   // edited tier / disabled / archived / cooldown: silent
            try { bool swallowed; text = CmdFix.Fix(user, text, m => { if (HostApi.SimMode && !fx) Console.WriteLine("[say] " + m); else { string via; HostApi.SendAs("core", m, out via); } }, out swallowed); if (swallowed) return; } catch (Exception ex) { Clog.Warn("cmdfix", "typo check failed: " + ex.Message); }   // "! join", "!jon", "!rejoin" -> !join; near misses answer once
            try { if (FeatureCommands.Handle(user, text, role, s => { if (HostApi.SimMode && !fx) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } })) return; } catch (Exception ex) { Clog.Warn("commands", "leaderboard command failed: " + ex.Message); }
            try { if (!fx && Streaks.Handle(user, text, s => { if (HostApi.SimMode && !fx) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } })) return; } catch (Exception ex) { Clog.Warn("streaks", "streak command failed: " + ex.Message); }
            try { if (!fx && PgCommand.Handle(user, text, role)) return; } catch (Exception ex) { Clog.Warn("pg", "!pg failed: " + ex.Message); }
            try { if (Auto.OnChat(user, text, role, isSub, firstMsg, msgId, replyTo, subTier)) return; } catch (Exception ex) { Clog.Warn("automation", "chat trigger failed: " + ex.Message); }   // an Actions & Events command took it
            try { if (ChannelLore.OnChat(user, text, role, ChannelLore.Say)) return; } catch (Exception ex) { Clog.Warn("lore", "channel lore failed: " + ex.Message); }   // a clear question the channel's own commands answer
            try { if (BotMention.OnChat(user, text, role, s => { if (HostApi.SimMode && !fx) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } })) return; } catch (Exception ex) { Clog.Warn("mention", "mention reply failed: " + ex.Message); }   // @PinguinoB0t about the stream or a moderation situation
            lock (dispatchLock)   // one message at a time: arguments are shared state, so no two chats can mix
            {
                cph.Args.Clear();
                string login = user.ToLowerInvariant();
                cph.Args["user"] = user; cph.Args["userName"] = login; cph.Args["userId"] = userId ?? "";
                cph.Args["message"] = text; cph.Args["rawInput"] = text; cph.Args["msgId"] = msgId ?? Guid.NewGuid().ToString("N");
                cph.Args["role"] = role; cph.Args["isModerator"] = role >= 3; cph.Args["isBroadcaster"] = role >= 4; cph.Args["isVip"] = role == 2;
                cph.Args["firstMessage"] = firstMsg; cph.Args["spamCandidate"] = spamCand; cph.Args["platform"] = platform;
                if (!string.IsNullOrEmpty(replyTo)) { cph.Args["reply.userName"] = replyTo; cph.Args["reply.userLogin"] = replyTo; }
                try
                {
                    string trimmed = text.Trim();
                    string first = trimmed.Split(' ')[0];
                    if (Cutover.On && !botAcct)   // the First 5 game pays points: only once Streamer.bot is retired, or both would pay
                    {
                        if (first.ToLowerInvariant() == "!first" || first.ToLowerInvariant() == "!firsts") { cph.Args["command"] = first.ToLowerInvariant(); cph.RunAction("PinguinoFirsts"); return; }
                        try
                        {
                            int before = cph.GetGlobalVar<int>("firstChatterPlace", true); cph.Args.Remove("command"); cph.RunAction("PinguinoFirsts"); int after = cph.GetGlobalVar<int>("firstChatterPlace", true);
                            if (before >= 1 && after != before) Latest.Record("first5", new Dictionary<string, string> { { "user", PlatformUsers.Shown(user) }, { "place", (after == 0 ? 5 : before).ToString() } });
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

        // Port guard: only the real Host (data = <suite>\Data\runtime or %AppData%\BVQ) may fall back to 8770. A --sim Host without OverlayPort takes a free
        // ephemeral port; any other non-sim Host with its own --data must name its port, or it refuses to start (test Hosts once collided with the live one on 8770).
        internal static int ResolvePort(JObject s, bool sim)
        {
            int? p = s.Value<int?>("OverlayPort");
            if (p.HasValue && p.Value > 0) return p.Value;
            if (sim) { int fp = FreePort(); Console.WriteLine("PORT GUARD: --sim with no OverlayPort, using free port " + fp + " (never 8770)"); return fp; }
            if (IsRealDataDir(dataDir, suite)) return 8770;
            Console.WriteLine("PORT GUARD: refusing to start: --data " + dataDir + " is not the real data folder and host_secrets.json has no OverlayPort. Set OverlayPort explicitly.");
            Environment.Exit(3); return 0;
        }
        internal static bool IsRealDataDir(string dir, string suiteDir)
        {
            string F(string x) => Path.GetFullPath(x).TrimEnd('\\', '/');
            try
            {
                if (string.Equals(F(dir), F(Path.Combine(suiteDir, "Data", "runtime")), StringComparison.OrdinalIgnoreCase)) return true;
                var ad = Environment.GetEnvironmentVariable("APPDATA");
                return !string.IsNullOrEmpty(ad) && string.Equals(F(dir), F(Path.Combine(ad, "BVQ")), StringComparison.OrdinalIgnoreCase);
            }
            catch (Exception) { return false; }
        }
        static int FreePort() { var l = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, 0); l.Start(); int p = ((System.Net.IPEndPoint)l.LocalEndpoint).Port; l.Stop(); return p; }

        // OBS, Twitch events and the overlay web server (what Streamer.bot used to provide).
        static void WireServices(JObject s, bool sim)
        {
            if ((!sim || Environment.GetEnvironmentVariable("PINGUINO_OBS") == "1") && (s.Value<bool?>("ObsEnabled") ?? true))   // sim skips OBS unless a test sets PINGUINO_OBS=1 (mock-obs)
            { cph.Obs = new ObsClient(s.Value<string>("ObsHost") ?? "127.0.0.1", s.Value<int?>("ObsPort") ?? 4455, s.Value<string>("ObsPassword") ?? ""); Task.Run(() => cph.Obs.RunForever()); ObsTree.Start(); }
            if (!sim) CarryOverApiKey();   // never in --sim: a test Host must not copy the real key into its temp data folder
            HostApi.DataDir = dataDir; HostApi.Port = ResolvePort(s, sim); HostApi.SimMode = sim; if (!sim) HostApi.StartPrestreamLoop(); HostApi.ObsConnected = () => cph.ObsIsConnected();
            string overlayDir = null;
            try { var f = Path.Combine(dataDir, "settings.json"); if (File.Exists(f)) overlayDir = JObject.Parse(File.ReadAllText(f)).Value<string>("OverlayDir"); } catch (Exception) { }
            OverlayServer.Start(HostApi.Port, overlayDir, Path.Combine(suite, "PinguinoB0t", "overlays"), dataDir);
            if (!sim || Environment.GetEnvironmentVariable("PINGUINO_EVENTSUB_URL") != null) Task.Run(() => EventSub.RunForever(s, a => DispatchEvent(a)));
        }

        // After a data-folder move the AI key can be blank in the new chat_settings.json while the legacy %AppData%\BVQ copy still has it: copy it across once (never logged).
        static void CarryOverApiKey()
        {
            try
            {
                if (!string.Equals(Path.GetFullPath(dataDir).TrimEnd('\\', '/'), Path.GetFullPath(Path.Combine(suite, "Data", "runtime")).TrimEnd('\\', '/'), StringComparison.OrdinalIgnoreCase)) return;   // only the real runtime folder, never a --data test dir
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
            try { SiteActivity.Note(args); } catch (Exception) { }
            try { Periods.OnEvent(args); } catch (Exception) { }
            try { Control.OnEvent(args); } catch (Exception) { }
            try { StreamTimers.OnEvent(args); } catch (Exception) { }
            try { Announce.OnEvent(args); } catch (Exception) { }
            try { ProfileSync.OnEvent(args); } catch (Exception) { }
            try { if (Convert.ToString(args.ContainsKey("eventType") ? args["eventType"] : "") == "TwitchRedeem") TimeoutReward.OnRedeem(args); } catch (Exception ex) { Clog.Warn("timeout-reward", "redeem failed: " + ex.Message); }
            try { Auto.OnEvent(args); } catch (Exception ex) { Clog.Warn("automation", "event trigger failed: " + ex.Message); }
            object et0; if (args.TryGetValue("eventType", out et0) && !new[] { "TwitchSub", "TwitchReSub", "TwitchGiftBomb", "TwitchCheer", "TwitchRaid", "TwitchFollow", "TwitchHype", "PgGame", "StreamOnline", "StreamOffline" }.Contains(Convert.ToString(et0))) return;   // automation-only events
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
                if (line.StartsWith("@") && line.Contains(" PRIVMSG #")) { HandleIrc(line); continue; }   // sim: a raw IRC PRIVMSG line with its tags (color=, badges=, user-id=)
                if (line.StartsWith("eventsub ")) { var q = line.Split(new[] { ' ' }, 3); try { EventSub.Simulate(q[1], q[2], x => DispatchEvent(x)); } catch (Exception ex) { Console.WriteLine("ERROR eventsub: " + ex.Message); } continue; }
                if (line.StartsWith("timeoutredeem ")) { var q = line.Split(new[] { ' ' }, 3); DispatchEvent(new Dictionary<string, object> { { "eventType", "TwitchRedeem" }, { "userName", q[1] }, { "title", "Timeout" }, { "input", q.Length > 2 ? q[2] : "" }, { "redemptionId", "red-t" }, { "rewardId", "rw-t" } }); continue; }   // sim: timeoutredeem alice marsh
                if (line == "periods-size") { try { Console.WriteLine("[periods] bytes " + Periods.ForSite().ToString(Newtonsoft.Json.Formatting.None).Length); } catch (Exception ex) { Console.WriteLine("[periods] error " + ex); } continue; }
                if (line == "firsts-dry" || line == "firsts-apply") { try { Console.WriteLine("[firsts] " + Firsts.Rebuild(line == "firsts-apply").ToString(Newtonsoft.Json.Formatting.None)); Console.WriteLine("[firstsboard] " + Firsts.Board(10).ToString(Newtonsoft.Json.Formatting.None)); Console.WriteLine("[firstssite] " + Firsts.ForSite().ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception ex) { Console.WriteLine("[firsts] error " + ex); } continue; }
                if (line == "recap-test") { try { Recap.TestClip = (f, t) => new Newtonsoft.Json.Linq.JObject { { "title", "T" }, { "url", "https://clips.twitch.tv/x" }, { "views", 9 } }; Console.WriteLine("[recap] " + Recap.Build(true).ToString(Newtonsoft.Json.Formatting.None)); Recap.TestClip = null; Console.WriteLine("[recap2] " + Recap.Build(true).ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception ex) { Console.WriteLine("[recap] error " + ex); } continue; }
                if (line == "backpay-dry" || line == "backpay-apply") { try { Console.WriteLine("[backpay] " + Economy.BackPay(line == "backpay-apply").ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception ex) { Console.WriteLine("[backpay] error " + ex); } continue; }
                if (line == "pointstest") { try { PointsTest.Run(); } catch (Exception ex) { Console.WriteLine("[pointstest] error " + ex); } continue; }
                if (line == "givelimittest") { try { GiveLimitTest.Run(); } catch (Exception ex) { Console.WriteLine("[givelimittest] error " + ex); } continue; }
                if (line == "replytest") { try { ReplyTest.Run(); } catch (Exception ex) { Console.WriteLine("[replytest] error " + ex); } continue; }
                if (line == "strikechecktest") { try { StrikeCheckInTest.Run(); } catch (Exception ex) { Console.WriteLine("[strikechecktest] error " + ex); } continue; }
                if (line == "alerttest") { try { AlertBridgeTest.Run(); } catch (Exception ex) { Console.WriteLine("[alerttest] error " + ex); } continue; }
                if (line == "scopetest") { try { ScopeTest.Run(); } catch (Exception ex) { Console.WriteLine("[scopetest] error " + ex); } continue; }
                if (line == "ranktest") { try { RankTest.Run(); } catch (Exception ex) { Console.WriteLine("[ranktest] error " + ex); } continue; }
                if (line.StartsWith("emojitest ")) { Console.WriteLine("[emojitest] " + string.Join(" ", WheelEmoji.Interests(line.Substring(10).Trim().ToLowerInvariant()))); continue; }
                if (line.StartsWith("simsay ")) { try { Console.WriteLine("[simsay] " + SimSay.Say(JObject.Parse(line.Substring(7))).ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception ex) { Console.WriteLine("[simsay] error " + ex.Message); } continue; }
                if (line.StartsWith("selfredeem ")) { var q = line.Split(new[] { ' ' }, 3); DispatchEvent(new Dictionary<string, object> { { "eventType", "TwitchRedeem" }, { "userName", q[1] }, { "title", "Self Timeout" }, { "input", q.Length > 2 ? q[2] : "" }, { "redemptionId", "red-s" }, { "rewardId", "rw-s" } }); continue; }   // sim: selfredeem alice 2m
                if (line.StartsWith("raidpick "))   // sim: raidpick target viewers = what the outgoing channel.raid event does (raid pending, then raid_out)
                { var p = line.Split(' '); string tg = p[1]; try { Auto.OnRaidScheduled(tg); } catch (Exception) { } DispatchEvent(new Dictionary<string, object> { { "eventType", "TwitchRaidOut" }, { "userName", tg }, { "target", tg }, { "viewers", p.Length > 2 ? p[2] : "5" } }); continue; }
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
                var resp = http.SendAsync(Req(HttpMethod.Post, HostApi.Helix + "/chat/messages", ReplyCtx.Body(bid, sid, m))).Result;
                if (!resp.IsSuccessStatusCode) Clog.Warn("twitch", "chat send refused by Twitch (HTTP " + (int)resp.StatusCode + (resp.StatusCode == (System.Net.HttpStatusCode)429 ? ", rate limited" : resp.StatusCode == System.Net.HttpStatusCode.Unauthorized ? ", token rejected - sign in again" : "") + ")");
                return resp.IsSuccessStatusCode;
            };
            cph.Timeout = (user, secs, why) =>
            {
                if (ReplyCtx.Platform != "twitch") return false;   // moderation stays Twitch-only
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
            if (Lease.MayRun) { try { Auto.OnChatSignal(m.Groups["nick"].Value, msg); } catch (Exception) { } }   // the raid-picked signal (Sery_Bot's goodbye line)
            string display = T("display-name") != "" ? T("display-name") : m.Groups["nick"].Value;
            string reply = T("reply-parent-user-login");
            Task.Run(() => Dispatch(display, msg, T("id"), role, T("user-id"), T("first-msg") == "1", reply, T("subscriber") == "1", Intro.TierFromBadges(T("badges")), "twitch", T("color"), T("badges")));
        }
    }
}
