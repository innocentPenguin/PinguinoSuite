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
    static void Msg(string user, string text, bool mod = false)
    {
        var a = CPHProxy.Args; a.Clear();
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
        File.WriteAllText(p, "{\"LobbyName\":\"peng3\",\"LobbyPassword\":\"\",\"UserCooldownSec\":0,\"InfoCooldownSec\":0" + extra + "}");
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

        Console.WriteLine(fails == 0 ? "ALL " + passes + " HELPER CHECKS PASSED" : fails + " FAILED / " + passes + " passed");
        try { Directory.Delete(dir, true); } catch (Exception) { }
        return fails == 0 ? 0 : 1;
    }
}
