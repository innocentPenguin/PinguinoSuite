using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;

// Checks for PinguinoHelper.cs. The AI is faked; nothing touches the network or %AppData%\BVQ.
public static class Harness
{
    static int fails, passes;
    static string dir;
    static int aiCalls;
    static string aiReply = "{\"intent\":\"none\",\"epic\":\"\"}";
    static int stamp;

    static void Check(string name, bool ok, string extra = "")
    {
        if (ok) passes++; else { fails++; Console.WriteLine("FAIL: " + name + (extra == "" ? "" : "  -> " + extra)); }
    }

    static bool Routed;   // behave as if the router started the helper
    static void Msg(string user, string text, bool mod = false, string reply = null)
    {
        var a = CPHProxy.Args; a.Clear(); if (reply != null) a["reply.userName"] = reply;
        a["message"] = text; a["userName"] = user.ToLower(); a["user"] = user; a["userId"] = "id_" + user.ToLower();
        a["isModerator"] = mod; a["role"] = mod ? 3 : 1; a["isBroadcaster"] = false; a["rawInput"] = "orig raw";
        if (Routed) a["pinguinoRouted"] = true;
        CPHProxy.Sent.Clear(); CPHProxy.Runs.Clear(); CPHProxy.Globals.Remove("pinguino.result");
        new CPHInline().Execute();
    }

    static string Last() { return CPHProxy.Sent.Count == 0 ? null : CPHProxy.Sent[CPHProxy.Sent.Count - 1]; }
    static bool Forwarded() { return CPHProxy.Runs.Any(r => (string)r["_action"] == "PinguinoChat"); }
    static Dictionary<string, object> CoreRun() { return CPHProxy.Runs.FirstOrDefault(r => (string)r["_action"] == "PinguinoBot"); }

    static void Settings(string extra = "")
    {
        string p = Path.Combine(dir, "helper_settings.json");
        File.WriteAllText(p, "{\"LobbyName\":\"peng3\",\"LobbyPassword\":\"\",\"UserCooldownSec\":0,\"InfoCooldownSec\":0,\"McCooldownSec\":0,\"McGlobalCooldownSec\":0,\"SameAnswerGapSec\":0,\"JoinGuardSec\":0" + extra + "}");
        File.SetLastWriteTimeUtc(p, DateTime.UtcNow.AddSeconds(++stamp));
        typeof(CPHInline).GetField("_cfgChecked", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, DateTime.MinValue);
    }

    public static int Main()
    {
        dir = Path.Combine(Path.GetTempPath(), "bvq_helper_test_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        Environment.SetEnvironmentVariable("PINGUINO_DATA_DIR", dir);
        File.WriteAllText(Path.Combine(dir, "settings.json"), "{\"WasLive\":true}");
        File.WriteAllText(Path.Combine(dir, "players.json"), "{\"ana\":{\"GameId\":\"AnaEpic\"}}");
        File.WriteAllText(Path.Combine(dir, "live_state.json"), "{\"queueOpen\":true}");
        Settings();
        typeof(CPHInline).GetField("_testLlm", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null,
            (Func<string, string, string>)((s, u) => { aiCalls++; return aiReply; }));

        typeof(CPHInline).GetField("_pgTestRoll", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, (Func<double>)(() => 100.0));   // chimes off unless a test turns them on
        // 1. lobby questions: answered from the config, chatbot kept out
        foreach (var q in new[] { "whats the code", "what's the code?", "name and pass?", "lobby password?", "gimme the pass", "what is the private match name", "whats the lobby name", "pass?", "can someone give me the password" })
        {
            Msg("Newbie", q);
            Check("lobby: " + q, Last() != null && Last().Contains("Name: peng3") && Last().Contains("no password") && !Forwarded(), Last());
        }
        Check("reply names the viewer", Last().StartsWith("@Newbie "));
        Settings(",\"LobbyName\":\"zzz9\",\"LobbyPassword\":\"hunter2\"");
        Msg("Newbie", "whats the code");
        Check("values come from the config file, not code", Last().Contains("zzz9") && Last().Contains("Password: hunter2") && !Last().Contains("peng3"), Last());
        Settings();

        // 2. how to join / register: right example, no brackets
        Msg("Newbie", "how do I join?");
        Check("how join: steps + example", Last().Contains("!register YourEpicName") && Last().Contains("peng3") && !Last().Contains("<"), Last());
        Msg("Newbie", "how do i register");
        Check("how register: example", Last().Contains("!register YourEpicName") && Last().Contains("no < > brackets"), Last());
        Msg("Ana", "how do i join");
        Check("registered viewer skips the register step", Last().Contains("registered as AnaEpic") && !Last().Contains("1) Register"), Last());
        Msg("Ana", "how do i register");
        Check("already registered says so", Last().Contains("already registered as AnaEpic"), Last());

        // 3. normal chatter goes to the chatbot, helper silent
        foreach (var t in new[] { "hello chat", "lol that was insane", "@pinguinob0t how are you", "my cat is playing with the code on my screen", "gg", "i love this game" })
        {
            Msg("Zed", t);
            Check("chatter passes through: " + t, Last() == null && Forwarded(), Last());
        }
        Msg("Zed", "!join");
        Check("commands pass through untouched", Last() == null && Forwarded());
        Msg("Zed", "!register RealName");
        Check("a good typed !register is left to the game manager", Last() == null && Forwarded());

        // 4. bot itself, other bots, offline
        Msg("pinguinob0t", "whats the code"); Check("ignores itself", Last() == null);
        Msg("nightbot", "whats the code"); Check("ignores other bots", Last() == null);
        File.WriteAllText(Path.Combine(dir, "settings.json"), "{\"WasLive\":false}");
        Msg("Newbie", "whats the code"); Check("silent while offline", Last() == null && Forwarded());
        File.WriteAllText(Path.Combine(dir, "settings.json"), "{\"WasLive\":true}");

        // 5. do-actions need a yes
        Msg("Newbie", "register me as Cool Penguin");
        Check("register asks first", Last().Contains("\"Cool Penguin\"") && Last().Contains("yes") && CoreRun() == null && !Forwarded(), Last());
        Msg("Newbie", "yes");
        var run = CoreRun();
        Check("yes runs the core !register with the name", run != null && (string)run["command"] == "!register" && (string)run["rawInput"] == "Cool Penguin", run == null ? "no run" : (string)run["command"] + "|" + (string)run["rawInput"]);
        Check("core call is as the viewer", run != null && (string)run["userName"] == "newbie" && (string)run["user"] == "Newbie");
        Check("core call has no privileges", run != null && (int)run["role"] == 1 && !(bool)run["isModerator"] && !(bool)run["isBroadcaster"]);
        Msg("Newbie", "yes");
        Check("a second yes does nothing", CoreRun() == null && Forwarded());

        Msg("Mod1", "register me as ModName", true);
        Msg("Mod1", "yes", true);
        run = CoreRun();
        Check("a mod's helper call is stripped of mod rights", run != null && (int)run["role"] == 1 && !(bool)run["isModerator"], run == null ? "no run" : run["role"] + "");
        Check("args restored after the core call", CPHProxy.Args.Count > 0 && (int)CPHProxy.Args["role"] == 3 && (bool)CPHProxy.Args["isModerator"] && (string)CPHProxy.Args["rawInput"] == "orig raw" && (string)CPHProxy.Args["command"] == "", string.Join(",", CPHProxy.Args.Select(kv => kv.Key + "=" + kv.Value)));

        Msg("Ana", "add me to the queue");
        Check("join asks first", Last().Contains("Add you to the queue") && CoreRun() == null, Last());
        Msg("Ana", "nah");
        Check("no cancels", Last().Contains("nothing changed"));
        Msg("Ana", "yes"); Check("after no, yes does nothing", CoreRun() == null && Forwarded());
        Msg("Ana", "put me in the queue"); Msg("Ana", "yes please");
        run = CoreRun();
        Check("yes runs !join", run != null && (string)run["command"] == "!join" && (string)run["userName"] == "ana");
        Msg("Ana", "take me out of the queue"); Msg("Ana", "yep");
        run = CoreRun(); Check("leave: !leave after yes", run != null && (string)run["command"] == "!leave");
        Msg("Ana", "where am i in the queue");
        run = CoreRun(); Check("position runs !pos at once (read only)", run != null && (string)run["command"] == "!pos" && !Forwarded());

        Msg("Newbie2", "add me to the queue");
        Check("join before register: explains", Last().Contains("register first") && CoreRun() == null, Last());
        File.WriteAllText(Path.Combine(dir, "live_state.json"), "{\"queueOpen\":false}");
        Msg("Ana", "add me to the queue");
        Check("join with the queue closed: says so, shows lobby", Last().Contains("closed") && CoreRun() == null, Last());
        File.WriteAllText(Path.Combine(dir, "live_state.json"), "{\"queueOpen\":true}");

        // 6. pending expires, unrelated chat keeps it open
        Msg("Ana", "add me to the queue");
        Msg("Ana", "lol ok so");
        Check("other chat while pending is passed on", Last() == null && Forwarded());
        Msg("Ana", "yes"); Check("pending survives other chat", CoreRun() != null);
        Settings(",\"ConfirmSeconds\":0");
        Msg("Ana", "add me to the queue"); System.Threading.Thread.Sleep(1100);
        Msg("Ana", "yes"); Check("expired confirmation does nothing", CoreRun() == null && Forwarded());
        Settings();

        // 7. only the sender's own name; nothing weird registered
        foreach (var bad in new[] { "register me as @someone", "register me as !kick", "register me as ab", "register me as thisnameiswaytoolongforepic", "register me as <name>" })
        {
            Msg("Newbie3", bad);
            Check("refuses bad epic name: " + bad, CoreRun() == null && Last() != null && !Last().Contains("Say yes"), Last());
        }
        Msg("Newbie3", "register me as My_Name-1.x"); Check("accepts normal punctuation", Last().Contains("Say yes"), Last());
        Msg("Newbie3", "register my friend bob as BobEpic"); Check("no 'for a friend' intent", CoreRun() == null && !(Last() ?? "").Contains("Say yes"));

        // 8. mistyped !register (brackets, extra words, placeholder)
        Msg("Brk", "!register <BrkEpic>");
        Check("brackets: tip + confirm", Last().Contains("no brackets") && Last().Contains("\"BrkEpic\"") && CoreRun() == null && !Forwarded(), Last());
        Msg("Brk", "yes"); run = CoreRun(); Check("fixed name registered after yes", run != null && (string)run["rawInput"] == "BrkEpic");
        Msg("Brk2", "!register [Brk Two]"); Check("square brackets", Last().Contains("\"Brk Two\""), Last());
        Msg("Brk3", "!register my epic is Brk Three"); Check("extra words", Last().Contains("\"Brk Three\""), Last());
        Msg("Brk4", "!register <your epic name>"); Check("placeholder: tells them to use their own", Last().Contains("YOUR Epic name") && CoreRun() == null, Last());
        Msg("Brk5", "!register name"); Check("placeholder 'name'", Last().Contains("YOUR Epic name"), Last());
        Msg("Ana", "!register <AnaEpic>"); Check("already registered: leave it to the game manager", Last() == null && Forwarded());

        // 9. AI only when unclear
        aiCalls = 0;
        Msg("Q", "hello chat"); Msg("Q", "lol gg"); Msg("Q", "whats the code");
        Check("no AI call for chatter or pattern hits", aiCalls == 0, aiCalls + "");
        aiReply = "{\"intent\":\"lobby_info\",\"epic\":\"\"}";
        Msg("Q", "yo is there a way for me to hop into the game?");
        Check("unclear but practical: AI used, answer templated", aiCalls == 1 && Last() != null && Last().Contains("peng3") && !Forwarded(), Last());
        aiReply = "{\"intent\":\"none\",\"epic\":\"\"}"; aiCalls = 0;
        Msg("Q", "do you play the game with your cat?");
        Check("AI says none: chatbot gets it", aiCalls == 1 && Last() == null && Forwarded());
        aiReply = "garbage"; aiCalls = 0; Msg("Q", "is the lobby thing broken for everyone?");
        Check("bad AI output = silent, passed on", Last() == null && Forwarded());
        aiReply = "{\"intent\":\"delete_everything\",\"epic\":\"\"}"; Msg("Q", "can the lobby thing be fixed?");
        Check("AI can only pick known intents", Last() == null && CoreRun() == null && Forwarded());
        aiReply = "{\"intent\":\"do_register\",\"epic\":\"@victim\"}"; Msg("Q2", "can u sign the new guy up for the lobby?");
        Check("AI-picked register still needs a valid name + yes", CoreRun() == null && !(Last() ?? "").Contains("Say yes"));
        aiReply = "{\"intent\":\"do_register\",\"epic\":\"GoodName\"}"; Msg("Q3", "can u get the lobby thing going for me with GoodName?");
        Check("AI-picked register asks for confirmation", CoreRun() == null && Last() != null && Last().Contains("\"GoodName\"") && Last().Contains("yes"), Last());
        Settings(",\"MaxAiCallsPerHour\":0"); aiCalls = 0; aiReply = "{\"intent\":\"lobby_info\",\"epic\":\"\"}";
        Msg("Q4", "is the lobby thing up?"); Check("AI hourly cap", aiCalls == 0 && Forwarded());
        Settings(",\"UseAi\":false"); Msg("Q4", "is the lobby thing up?"); Check("UseAi=false", aiCalls == 0 && Forwarded());
        Settings();

        // 10. cooldown, kill switch, hand-over options
        Settings(",\"UserCooldownSec\":60");
        Msg("Cd", "whats the code"); Check("first ask answered", Last() != null);
        Msg("Cd", "whats the code"); Check("repeat inside cooldown: silent and chatbot kept out", Last() == null && !Forwarded());
        Settings(",\"Enabled\":false"); Msg("Zed", "whats the code"); Check("kill switch: passes everything on", Last() == null && Forwarded());
        Settings(",\"ForwardHandled\":true"); Msg("Fh", "whats the code");
        Check("ForwardHandled hands it on flagged", Last() != null && Forwarded() && CPHProxy.Runs.Any(r => r.ContainsKey("helperHandled")));
        Settings(",\"ChatActionName\":\"\""); Msg("Zed", "hi"); Check("no chat action configured: no crash", !Forwarded());
        Settings();

        // 11. first run writes a template config
        File.Delete(Path.Combine(dir, "helper_settings.json"));
        typeof(CPHInline).GetField("_init", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, false);
        Msg("Zed", "hi");
        Check("template config written on first run", File.Exists(Path.Combine(dir, "helper_settings.json")) && File.ReadAllText(Path.Combine(dir, "helper_settings.json")).Contains("peng3"));
        Check("core files untouched", File.ReadAllText(Path.Combine(dir, "players.json")).Contains("AnaEpic") && !File.ReadAllText(Path.Combine(dir, "players.json")).Contains("Cool Penguin"));

        // ── the three bots: the router protocol ──
        string Result() { object r; return CPHProxy.Globals.TryGetValue("pinguino.result", out r) ? (string)r : ""; }
        Settings();
        Routed = true;
        Msg("Routed1", "whats the code");
        Check("routed: a handled message is reported as handled", Result() == "handled", Result());
        Check("routed: the helper does not hand the message on itself", !Forwarded());
        Check("routed: the viewer is now in a conversation with the helper", CPHProxy.Globals.ContainsKey("pinguino.helperctx.routed1"), string.Join(",", CPHProxy.Globals.Keys) + " | " + Last());
        Msg("Routed1", "lol nice weather");
        Check("routed: a message that is not the helper's is passed on", Result() == "pass" && !Forwarded(), Result());
        Check("routed: passing means saying nothing", Last() == null);
        CPHProxy.Missing.Add("PinguinoBot");
        Msg("Ana", "add me to the queue"); Msg("Ana", "yes");
        Check("the game manager is missing: its fallback says so instead of leaving the viewer waiting", Last() != null && Last().Contains("can't reach the game manager") && CoreRun() == null, Last() + " | " + string.Join(",", CPHProxy.Sent) + " | runs=" + CPHProxy.Runs.Count);
        CPHProxy.Missing.Clear();
        Routed = false;
        Msg("Legacy1", "lol nice weather");
        Check("legacy (no router): the helper still hands the message to the chatbot", Forwarded() && Result() == "pass", Result());

        // ── Minecraft: ask Java or Bedrock, answer from the facts, AI words it a few times then the stored wordings repeat ──
        Routed = false; Settings(",\"FactsUrl\":\"\"");
        int ai0 = aiCalls; aiReply = "Java players: add smp.innocentpenguin.com, no port needed!";
        Msg("Mc1", "what's the minecraft ip");
        Check("minecraft ip with no edition: asks Java or Bedrock first, no AI call", Last() != null && Last().Contains("Bedrock") && Last().Contains("Java") && aiCalls == ai0, Last());
        Msg("Mc1", "java");
        Check("java answer: the AI wording is used when it holds the IP", Last() != null && Last().Contains("smp.innocentpenguin.com") && !Last().Contains("19132"), Last());
        aiReply = "just join the server lol";
        Msg("Mc2", "minecraft ip bedrock");
        Check("edition in the first message: no question, bedrock gets IP and port (a wording without the facts is thrown away)", Last() != null && Last().Contains("smp.innocentpenguin.com") && Last().Contains("19132"), Last());
        aiReply = "Bedrock: IP smp.innocentpenguin.com port 19132, hardcore hc.innocentpenguin.com port 9216";
        Settings(",\"FactsUrl\":\"\",\"PhraseBankSize\":2");
        Msg("Mc3", "ip? bedrock"); Msg("Mc4", "ip? bedrock");
        int ai1 = aiCalls; Msg("Mc5", "ip? bedrock"); Msg("Mc6", "ip? bedrock");
        Check("once the bank is full the AI is not called again", aiCalls == ai1 && Last() != null && Last().Contains("19132"), Last());
        Msg("Mc7", "!discord");
        Check("!discord answers with the invite", Last() != null && Last().Contains("discord.gg/"), Last());
        Check("facts file was seeded for 05/Ivan to check", File.Exists(Path.Combine(dir, "helper_facts.json")));

        // the website's /api/faq overrides the seed
        var bf = BindingFlags.NonPublic | BindingFlags.Static; var T = typeof(CPHInline);
        T.GetField("_pgTestHttp", bf).SetValue(null, (Func<string, string, string, string>)((u, a, b) => u.StartsWith("GET ") ? "{\"faq\":[{\"key\":\"minecraft_ip\",\"answer\":\"Community SMP: play.example.net (Bedrock port 11111). Hardcore SMP: hc.example.net (Bedrock port 22222).\"},{\"key\":\"discord\",\"answer\":\"x\",\"url\":\"https://discord.gg/zzz\"}]}" : "{}"));
        T.GetField("_siteAt", bf).SetValue(null, DateTime.MinValue); T.GetField("_factsAt", bf).SetValue(null, DateTime.MinValue);
        Settings(",\"FactsUrl\":\"https://site.test/api/faq\",\"PhraseBankSize\":1"); aiReply = "x";
        Msg("Mc8", "ip? bedrock");
        Check("site facts win: new IP and both ports", Last() != null && Last().Contains("play.example.net") && Last().Contains("11111") && Last().Contains("22222"), Last());
        Msg("Mc9", "!discord");
        Check("site discord link wins", Last() != null && Last().Contains("discord.gg/zzz"), Last());
        T.GetField("_pgTestHttp", bf).SetValue(null, null);

        // viewers' feedback 2026-10-19: no false "Java or Bedrock?", no repeats, mods change the lobby, what's playing, my MMR
        Settings(",\"FactsUrl\":\"\""); aiReply = "x";
        Msg("F1", "Geo Minecraft today"); Check("a statement about minecraft is not a question", Last() == null, Last());
        Msg("F2", "u guys also play minecraft"); Check("'also play minecraft' is not a question either", Last() == null, Last());
        Msg("F3", "just use !ip for the minecraft server"); Check("talk about the !ip command is ignored", Last() == null, Last());
        Msg("F4", "how do I join the minecraft server?"); Check("a real question still gets Java or Bedrock", Last() != null && Last().Contains("Bedrock"), Last());
        Settings(",\"FactsUrl\":\"\",\"McCooldownSec\":120,\"McGlobalCooldownSec\":0,\"SameAnswerGapSec\":0");
        Msg("R1", "what is the minecraft ip"); Check("first ask is answered with the question", Last() != null && Last().Contains("Bedrock"), Last());
        Msg("R1", "minecraft ip?"); Check("asking again is not answered with the same question again", Last() == null, Last());
        Msg("R1", "minecraft"); Check("typing just minecraft does nothing", Last() == null, Last());
        Settings(",\"FactsUrl\":\"\"");
        Msg("L1", "!lobbyname arena7", false); Check("lobby name: non-mods are refused", Last() != null && Last().Contains("Only mods"), Last());
        Msg("L2", "!lobbyname arena7", true); Check("a mod sets the lobby name", Last() != null && Last().Contains("arena7") && File.ReadAllText(Path.Combine(dir, "helper_settings.json")).Contains("arena7"), Last());
        Msg("L2", "!lobbypass hunter2", true); Check("a mod sets the lobby password", Last() != null && Last().Contains("hunter2"), Last());
        Msg("L3", "what's the lobby code"); Check("viewers get the new name and password", Last() != null && Last().Contains("arena7") && Last().Contains("hunter2"), Last());
        Msg("L2", "!lobbypass off", true); Check("password can be cleared", Last() != null && Last().Contains("no password"), Last());
        T.GetField("_pgTestHttp", bf).SetValue(null, (Func<string, string, string, string>)((u, a, b) => u.Contains("8771") ? "{\"title\":\"Song X\",\"artist\":\"Band\",\"requestedBy\":\"\"}" : null));
        Msg("S1", "what song is this?"); Check("what's playing comes from the Spotify module", Last() != null && Last().Contains("Song X") && Last().Contains("Band"), Last());
        T.GetField("_pgTestHttp", bf).SetValue(null, null);
        Msg("M1", "what's my mmr"); Check("MMR question points at !mmr", Last() != null && Last().Contains("!mmr"), Last());

        // context gate (2026-10-19/20 chat log): passing mentions, talk between viewers and already-answered questions get no helper reply
        Settings(",\"FactsUrl\":\"\""); aiReply = "x";
        foreach (var fp in new[] { "i dont know what minecraft is", "Cg5 Minecraft animals and other stuff", "Meet me on Minecraft...", "Are you going to do Minecraft after this?", "hmm u guys also play minecraft interesting <:",
                                    "About Minecraft", "when r we doing Minecraft", "i lwky haven't played Minecraft since 1.21 sooo idk", "why would we need a bot that tells us the Minecraft ip, when there's !ip",
                                    "its still up to the people to know when to play and how to play", "I'm not even trying to join the match", "minecraft", "Minecraft", "rocket league" })
        { Msg("G" + Math.Abs(fp.GetHashCode() % 9999), fp); Check("no helper reply to: " + fp, Last() == null, Last()); }
        Msg("Gr1", "can i join?", false, "someone"); Check("a reply to another viewer is not the helper's business", Last() == null, Last());
        Msg("Gr2", "@yoohoo15 you can join with the ip"); Check("a message addressed to another viewer is left alone", Last() == null, Last());
        Msg("GmodX", "@Gnew1 the minecraft ip is smp.innocentpenguin.com java", true); Msg("Gnew1", "whats the minecraft ip"); Check("someone already answered this person: the helper stays out", Last() == null, Last());
        Msg("Gnew2", "how do i join the minecraft server?"); Check("a real question with nobody answering still gets help", Last() != null && Last().Contains("Bedrock"), Last());
        Msg("Gnew3", "is the minecraft server up?"); Check("'is the minecraft server up?' is a real ask", Last() != null, Last());
        Msg("Gnew4", "i wanna join"); Check("'i wanna join' still gets the welcome help", Last() != null, Last());
        Msg("Gnew5", "whats the code"); Check("'whats the code' still gets the lobby", Last() != null && Last().Contains("peng3"), Last());
        Settings(",\"FactsUrl\":\"\",\"SameAnswerGapSec\":45");
        ((System.Collections.IDictionary)T.GetField("_sameAnswer", bf).GetValue(null)).Clear();
        Msg("Gb1", "whats the minecraft ip?"); Check("burst: the first ask is answered", Last() != null, Last());
        Msg("Gb2", "what's the minecraft ip"); Msg("Gb3", "ip?"); Check("burst: the next askers inside the gap get no second reply", Last() == null, Last());
        Settings(",\"FactsUrl\":\"\"");

        // the questions have a purpose: Java -> just the IP; "it doesn't work" -> real help; Bedrock -> port + Bedrock Connect for console
        Settings(",\"FactsUrl\":\"\""); aiReply = "x";
        Msg("Fl1", "how do i join the minecraft server?"); Msg("Fl1", "java");
        Check("java: just the IP, nothing else", Last() != null && Last().StartsWith("@Fl1 Java IP:") && !Last().Contains("port") && !Last().Contains("Rules") && Last().Length < 120, Last());
        Msg("Fl1", "it doesnt work"); Check("java follow-up 'it doesn't work' gets troubleshooting", Last() != null && Last().Contains("Java not connecting") && Last().Contains("play.example.net"), Last());
        Msg("Fl2", "how do i join the minecraft server?"); Msg("Fl2", "bedrock");
        Check("bedrock: IP + port and a pointer to console help", Last() != null && Last().Contains("11111") && Last().Contains("console"), Last());
        Msg("Fl2", "console"); Check("'console' explains Bedrock Connect (and the BedrockGo2 trick from chat)", Last() != null && Last().Contains("Bedrock Connect") && Last().Contains("BedrockGo2") && Last().Contains("play.example.net"), Last());
        Msg("Fl3", "how do i join the minecraft server?"); Msg("Fl3", "bedrock"); Msg("Fl3", "it says cant connect");
        Check("bedrock follow-up gets the bedrock checklist", Last() != null && Last().Contains("Bedrock not connecting") && Last().Contains("separate boxes"), Last());
        Msg("Fl4", "how do i join the minecraft server?"); Msg("Fl4", "java"); Msg("Fl4", "no bedrock");
        Check("switching edition gives the other answer", Last() != null && Last().Contains("11111"), Last());
        Msg("Fl5", "how do i join the minecraft server?"); Msg("Fl5", "java"); Msg("Fl5", "lol nice");
        Check("unrelated chatter after the answer is left alone", Last() == null, Last());
        Msg("Fl6", "i wanna join"); Msg("Fl6", "how do i play"); Check("how-to-join steps say join once and search the private match", Last() == null || Last().Contains("once is enough") || Last().Contains("search"), Last());

        // ── training: the helper answers real help questions in ONE short line with the right site page, and stays silent otherwise ──
        Settings(",\"FactsUrl\":\"\""); aiReply = "{\"intent\":\"none\",\"epic\":\"\"}";
        var siteCases = new[] { new[] { "what commands are there?", "/help#commands" }, new[] { "is there a list of commands?", "/help#commands" }, new[] { "where can i see the leaderboards?", "/leaderboards" }, new[] { "who has gifted the most subs?", "/leaderboards" },
            new[] { "where do i find my profile?", "/members" }, new[] { "what are the rules?", "/faq" }, new[] { "what are strikes?", "/faq" }, new[] { "which emotes are there? 7tv", "/emotes" } };
        int sc = 0;
        foreach (var c in siteCases)
        {
            Msg("Site" + (++sc), c[0]);
            Check("should answer: " + c[0], Last() != null && Last().Contains("https://innocentpenguin.com" + c[1]), Last());
            Check("short: one line under 160 characters with a link: " + c[0], Last() != null && Last().IndexOf('\n') < 0 && Last().Length < 160 && Last().Contains("https://"), Last());
        }
        foreach (var q in new[] { "lol the commands in this game are crazy", "i love the leaderboards on this site", "gg that was a good round", "ay did you see that clutch", "my commands are broken on my keyboard haha", "the rules of rocket league are weird" })
        {
            Msg("Quiet9", q);
            Check("should stay silent: " + q, Last() == null, Last());
        }
        Msg("Quiet9", "@Someone what commands are there?");
        Check("should stay silent: a question meant for another viewer", Last() == null, Last());

        // ── approved "Taught" notes (Host teach inbox) ──
        {
            string hf = Path.Combine(dir, "helper_facts.json"); var hj = Newtonsoft.Json.Linq.JObject.Parse(File.ReadAllText(hf));
            hj["Taught"] = new Newtonsoft.Json.Linq.JArray(new Newtonsoft.Json.Linq.JObject { { "id", "t1" }, { "text", "The SMP world resets at the start of every season, builds are saved to the map archive." }, { "taughtBy", "modguy" } });
            File.WriteAllText(hf, hj.ToString());
            T.GetField("_factsAt", bf).SetValue(null, DateTime.MinValue);
            Msg("Tch1", "when does the smp world reset?");
            Check("a taught note answers a matching question, short, with the help link", Last() != null && Last().Contains("resets at the start of every season") && Last().Contains("https://innocentpenguin.com/help") && Last().IndexOf('\n') < 0, Last());
            Msg("Tch2", "lol the world reset was funny");
            Check("a statement is left alone", Last() == null, Last());
            Msg("Tch3", "what is the best pizza topping?");
            Check("an unrelated question gets no taught answer", Last() == null, Last());
        }

        // ── random chime (Helper only): rate limited, gated ──
        {
            var roll = T.GetField("_pgTestRoll", bf); var cg = T.GetField("_chimeGlobal", bf);
            roll.SetValue(null, (Func<double>)(() => 0.0)); cg.SetValue(null, 0L);
            Msg("Chm1", "this stream is really chill today honestly");
            Check("a chime lands on an ordinary line when the roll hits", Last() != null && Last().StartsWith("@Chm1 ") && Last().Length < 140, Last());
            Msg("Chm2", "another perfectly ordinary chat line here");
            Check("global gap: no second chime right away", Last() == null, Last());
            cg.SetValue(null, 0L); Msg("Chm1", "still a chill stream here with everyone");
            Check("per-viewer gap: same viewer is not chimed twice", Last() == null, Last());
            cg.SetValue(null, 0L); Msg("Chm3", "@Someone that was a funny moment honestly");
            Check("no chime on a line meant for someone else", Last() == null, Last());
            Msg("Chm3", "!points");
            cg.SetValue(null, 0L); Msg("Chm4", "short");
            Check("no chime on a very short line", Last() == null, Last());
            File.WriteAllText(Path.Combine(dir, "unping.json"), "{\"logins\":[\"chm5\"]}");
            cg.SetValue(null, 0L); Msg("Chm5", "this stream is really chill today honestly");
            Check("an !unping viewer is never chimed", Last() == null, Last());
            File.Delete(Path.Combine(dir, "unping.json"));
            roll.SetValue(null, (Func<double>)(() => 100.0));
        }

        // ── private help-review log ──
        string rv = Path.Combine(dir, "helper", "review.jsonl");
        Check("the review log exists in Data\\helper (private, not pushed)", File.Exists(rv), rv);
        var rows = File.ReadAllLines(rv).Where(l => l.Trim() != "").Select(l => Newtonsoft.Json.Linq.JObject.Parse(l)).ToList();
        var trig = rows.Where(r => (string)r["type"] == "trigger").ToList();
        Check("every answer is logged with its reply and the chat window before it", trig.Any(r => (string)r["kind"] == "answered" && ((string)r["reply"]).Contains("/help#commands") && ((Newtonsoft.Json.Linq.JArray)r["window"]).Count >= 2), "triggers=" + trig.Count);
        Msg("Missy1", "how do i get my points refunded?");
        Msg("Chat1", "later chat line one"); Msg("Chat2", "later chat line two");
        rows = File.ReadAllLines(rv).Where(l => l.Trim() != "").Select(l => Newtonsoft.Json.Linq.JObject.Parse(l)).ToList();
        var missed = rows.Where(r => (string)r["type"] == "trigger" && (string)r["kind"] == "missed").ToList();
        Check("a likely-help question with no answer is logged as missed with the reason", missed.Any(r => (string)r["user"] == "missy1" && ((string)r["reason"]).Length > 3), string.Join(",", missed.Select(r => (string)r["user"] + ":" + (string)r["reason"])));
        Check("plain banter is not logged at all", !rows.Any(r => (string)r["type"] == "trigger" && ((string)r["text"]).Contains("clutch")));
        string mid = (string)missed.First(r => (string)r["user"] == "missy1")["id"];
        var after = rows.Where(r => (string)r["type"] == "after" && (string)r["id"] == mid).Select(r => (string)r["t"]).ToList();
        Check("the chat AFTER the trigger (from all chatters) is kept", after.Contains("later chat line one") && after.Contains("later chat line two"), string.Join("|", after));


        // ── lore proposals: quick facts, negative feedback, lobby correction, double join ──
        Settings(",\"FactsUrl\":\"\"");
        Msg("Q1", "why are there so many ads?"); Check("ads question gets the 3 minute line", Last() != null && Last().Contains("3-minute ads") && Last().Length < 160, Last());
        Msg("Q2", "how do i use tts?"); Check("tts question: sub-only + link", Last() != null && Last().Contains("sub-only") && Last().Contains("https://"), Last());
        Msg("Q3", "where is the roblox link?"); Check("roblox question: Ivan posts it", Last() != null && Last().Contains("Roblox") && Last().Contains("Ivan"), Last());
        Msg("Q4", "lol ads are the worst haha"); Check("a remark about ads is left alone", Last() == null, Last());
        Msg("Neg1", "what commands are there?"); Check("negative setup: helper answered", Last() != null, Last());
        Msg("Neg1", "wasn't talking to you"); Check("negative feedback: no reply", Last() == null, Last());
        Msg("Neg1", "what commands are there?"); Check("negative feedback: silent for that viewer for a while", Last() == null, Last());
        Msg("Neg2", "what are the rules?"); Check("others still get answers", Last() != null, Last());
        string rvn = Path.Combine(dir, "helper", "review.jsonl");
        Check("negative feedback is logged as negative", File.ReadAllLines(rvn).Any(l => l.Contains("\"kind\":\"negative\"") && l.Contains("neg1")), "");
        Msg("Neg3", "wrong context bro"); Check("negative from a viewer the helper never answered is not a trigger", Last() == null, Last());
        Msg("Lob1", "whats the code"); Check("lobby setup", Last() != null && Last().Contains("peng3"), Last());
        Msg("Lob2", "its peng4"); Check("someone says another name: thanks + mod hint, once", Last() != null && Last().Contains("peng4") && Last().Contains("!lobbyname"), Last());
        Msg("Lob3", "its peng4"); Check("not repeated within 5 minutes", Last() == null, Last());
        Settings(",\"FactsUrl\":\"\",\"JoinGuardSec\":120");
        File.WriteAllText(Path.Combine(dir, "players.json"), "{\"ana\":{\"GameId\":\"AnaEpic\"},\"dj\":{\"GameId\":\"DjEpic\"}}");
        Msg("Dj", "add me to the queue"); Msg("Dj", "yes"); var djRun = CoreRun();
        Check("double join setup: first join ran", djRun != null && (string)djRun["command"] == "!join", djRun == null ? "no run" : "x");
        Msg("Dj", "add me to the queue"); Check("a second 'add me' right after is answered without asking or calling the core", CoreRun() == null && Last() != null && Last().Contains("already added"), Last());

        Console.WriteLine(fails == 0 ? "ALL " + passes + " HELPER CHECKS PASSED" : fails + " FAILED / " + passes + " passed");
        try { Directory.Delete(dir, true); } catch (Exception) { }
        return fails == 0 ? 0 : 1;
    }
}
