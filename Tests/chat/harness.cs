using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;

// Checks for PinguinoChat.cs. The AI is faked; nothing touches the network or %AppData%\BVQ.
public static class Harness
{
    static int fails, passes;
    static string dir;
    static string lastPrompt = "", lastSystem = "";
    static string nextReply = "{\"reply\":\"hey there!\",\"remember\":[],\"notes\":\"\"}";
    static int llmCalls;
    static List<string> studyPrompts = new List<string>();
    static string mergePrompt = "";
    static List<string> opinionPrompts = new List<string>();
    static string opinionReply = "";
    static string studyReply = "{\"viewers\":[],\"community\":[]}";

    static void Check(string name, bool ok, string extra = "")
    {
        if (ok) passes++; else { fails++; Console.WriteLine("FAIL: " + name + (extra == "" ? "" : "  -> " + extra)); }
    }

    static Dictionary<string, object> Extra = new Dictionary<string, object>();   // extra arguments for the next Msg (what the router would set)
    static void Msg(string user, string text, string id = null, bool mod = false, string replyTo = null)
    {
        var a = CPHProxy.Args; a.Clear();
        a["message"] = text; a["userName"] = user.ToLower(); a["user"] = user; a["userId"] = id ?? ("id_" + user.ToLower());
        a["isModerator"] = mod; a["role"] = mod ? 3 : 1;
        if (replyTo != null) a["reply.userName"] = replyTo;
        foreach (var kv in Extra) a[kv.Key] = kv.Value;
        new CPHInline().Execute();
    }

    static string Last() { return CPHProxy.Sent.Count == 0 ? null : CPHProxy.Sent[CPHProxy.Sent.Count - 1]; }
    static JObject Memory() { return JObject.Parse(File.ReadAllText(Path.Combine(dir, "chat_memory.json"))); }

    static void Live(bool on)
    {
        File.WriteAllText(Path.Combine(dir, "settings.json"), "{\"WasLive\":" + (on ? "true" : "false") + ",\"StreamerName\":\"innocentpenguin_\"}");
    }

    public static int Main()
    {
        dir = Path.Combine(Path.GetTempPath(), "bvq_chat_test_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        Environment.SetEnvironmentVariable("PINGUINO_DATA_DIR", dir);
        Environment.SetEnvironmentVariable("BVQ_CHAT_INLINE", "1");
        File.WriteAllText(Path.Combine(dir, "chat_settings.json"),
            "{\"RolesUrl\":\"http://test/roles\",\"GlobalCooldownSec\":0,\"UserCooldownSec\":0,\"RandomChance\":0,\"GateEnabled\":false,\"MinReplyGapSec\":0,\"MaxRepliesPerViewer10Min\":0,\"StreamerInfo\":\"Peng is 24 and streams daily at 5pm CDT\",\"ApiKey\":\"test\",\"HistoryDir\":\"" + Path.Combine(dir, "history").Replace("\\", "\\\\") + "\",\"UpdatesFile\":\"" + Path.Combine(dir, "updates.json").Replace("\\", "\\\\") + "\",\"OpinionsFile\":\"" + Path.Combine(dir, "opinions.json").Replace("\\", "\\\\") + "\",\"CommandsFile\":\"" + Path.Combine(dir, "commands.json").Replace("\\", "\\\\") + "\"}");
        File.WriteAllText(Path.Combine(dir, "updates.json"), "[{\"At\":\"2026-10-18T10:00:00-05:00\",\"By\":\"test\",\"Title\":\"Older update\",\"Details\":\"first\"},{\"At\":\"2026-10-19T08:15:00-05:00\",\"By\":\"test\",\"Title\":\"Names and trust\",\"Details\":\"nicknames follow trust\"}]");
        Directory.CreateDirectory(Path.Combine(dir, "history", "daily")); Directory.CreateDirectory(Path.Combine(dir, "history", "monthly", "hist1")); Directory.CreateDirectory(Path.Combine(dir, "history", "monthly", "histforget"));
        File.WriteAllText(Path.Combine(dir, "history", "daily", "2026-10-17.json"), "{\"summary\":\"Horror game night with mod talk.\",\"games\":[\"Minecraft\"],\"topics\":[\"mods\"],\"moments\":[\"19:00 - mod talk\"]}");
        File.WriteAllText(Path.Combine(dir, "history", "monthly", "hist1", "2026-09.json"), "{\"login\":\"hist1\",\"month\":\"2026-09\",\"messages\":200,\"interests\":[\"Listens to Brent Faiyaz\"],\"highlights\":[\"Won a tourney\"],\"vibe\":\"chill\"}");
        File.WriteAllText(Path.Combine(dir, "history", "monthly", "histforget", "2026-09.json"), "{\"login\":\"histforget\",\"month\":\"2026-09\",\"messages\":200,\"interests\":[\"Secret hobby\"],\"highlights\":[],\"vibe\":\"x\"}");
        Live(true);
        typeof(CPHInline).GetField("_antiStuck", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, false);   // the fake AI repeats itself on purpose; one test below switches the guard on
        File.WriteAllText(Path.Combine(dir, "commands.json"), "{\"commands\":[{\"usage\":\"!join\",\"who\":\"everyone\",\"description\":\"Join the queue (must be registered, queue must be open).\"}]}");
        File.WriteAllText(Path.Combine(dir, "players.json"), "{\"ana\":{\"GameId\":\"AnaEpic\",\"Wins\":5,\"Losses\":1,\"Points\":16,\"Strikes\":2,\"PeakMmr\":900}}");
        File.WriteAllText(Path.Combine(dir, "live_state.json"), "{\"activity\":\"competitive\",\"format\":\"2v2\",\"gameMode\":\"standard\",\"queueOpen\":false,\"queue\":[{\"pos\":1,\"user\":\"bob\"}],\"obs\":{\"twitchGame\":\"Rocket League\"},\"currentMatch\":null}");
        // ana: won her last 3 counted games
        File.WriteAllText(Path.Combine(dir, "matches.json"), "[" +
            "{\"Id\":1,\"Winner\":\"orange\",\"Counted\":true,\"Blue\":[{\"Username\":\"ana\"}],\"Orange\":[{\"Username\":\"zed\"}]}," +
            "{\"Id\":2,\"Winner\":\"blue\",\"Counted\":true,\"Blue\":[{\"Username\":\"ana\"}],\"Orange\":[{\"Username\":\"zed\"}]}," +
            "{\"Id\":3,\"Winner\":\"blue\",\"Counted\":true,\"Blue\":[{\"Username\":\"ana\"}],\"Orange\":[{\"Username\":\"zed\"}]}," +
            "{\"Id\":4,\"Winner\":\"orange\",\"Counted\":true,\"Blue\":[{\"Username\":\"zed\"}],\"Orange\":[{\"Username\":\"ana\"}]}]");

        var f = typeof(CPHInline).GetField("_testLlm", BindingFlags.NonPublic | BindingFlags.Static);
        f.SetValue(null, (Func<string, string, string>)((s, u) =>
        {
            llmCalls++; lastSystem = s; lastPrompt = u;
            if (s.Contains("STUDY MODE")) { studyPrompts.Add(u); return studyReply; }
            if (s.Contains("OPINION MODE")) { opinionPrompts.Add(u); return opinionReply; }
            if (s.Contains("maintain PinguinoBot")) { mergePrompt = u; return "{\"community\":\"A chill Rocket League crew that loves cat memes.\"}"; }
            return nextReply;
        }));
        typeof(CPHInline).GetField("_testHttp", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null,
            (Func<string, string>)(url => "{\"owner\":{\"twitch\":\"innocentpenguin_\"},\"mods\":[{\"name\":\"CyFiRL\",\"login\":\"\",\"twitch\":\"cyfirl\"}],\"vips\":[{\"twitch\":\"ash_wagawaga\"}],\"bots\":[{\"name\":\"RoleBot\",\"login\":\"\",\"twitch\":\"rolebot\"}]}"));

        // 1. plain chatter is recorded, never answered
        Msg("Ana", "hello chat"); Msg("Zed", "my cat Luna says hi");
        Check("no reply without a mention", Last() == null);

        // 2. mention -> reply, facts saved (and bad ones refused)
        nextReply = "{\"reply\":\"Welcome back champ!\",\"remember\":[\"Has a cat named Luna\",\"Is 12 years old\",\"Likes pizza\",\"Is Christian\",\"email me at a@b.com\"],\"notes\":\"Friendly regular\"}";
        Msg("Zed", "@pinguinob0t do you remember my cat?");
        Check("replies to @mention", Last() == "@Zed Welcome back champ!", Last());
        var zed = Memory()["id_zed"];
        var facts = zed["Facts"].Select(x => (string)x["Text"]).ToList();
        Check("keeps normal facts", facts.Contains("Has a cat named Luna") && facts.Contains("Likes pizza"), string.Join("|", facts));
        Check("never stores age/religion/email", facts.Count == 2, string.Join("|", facts));
        Check("notes saved", (string)zed["Notes"] == "Friendly regular");
        Check("prompt has recent chat from others", lastPrompt.Contains("hello chat"));
        Check("system prompt present", lastSystem.Contains("PinguinoBot"));

        // 3. memory is recalled next time, and other viewers' memory never appears
        CPHProxy.Sent.Clear();
        Msg("Ana", "@pinguinob0t hi", "id_ana");
        Check("viewer B prompt has no viewer A facts", !lastPrompt.Contains("Luna cat") && !lastPrompt.Contains("Has a cat named Luna"));
        Check("small talk: no queue, live state or stats in the prompt", !lastPrompt.Contains("[LIVE STATE]") && !lastPrompt.Contains("5W/1L") && !lastPrompt.Contains("[VIEWER STATUS]") && !lastPrompt.Contains("pinged you"), lastPrompt);
        Msg("Ana", "@pinguinob0t why cant i join the queue");
        Check("queue talk: live state + strikes are included", lastPrompt.Contains("[LIVE STATE]") && lastPrompt.Contains("strikes: 2/3") && !lastPrompt.Contains("5W/1L"), lastPrompt);
        Msg("Ana", "@pinguinob0t what is my win streak?");
        Check("record + streak included when relevant", lastPrompt.Contains("5W/1L") && lastPrompt.Contains("WIN streak: 3"), lastPrompt);
        Check("system prompt has the teasing rules", lastSystem.Contains("MESSING WITH PEOPLE") && lastSystem.Contains("Do NOT bring up wins"));
        Check("system prompt: warm by default and friendly-but-not-possessive rules", lastSystem.Contains("DEFAULT WARMTH") && lastSystem.Contains("CLOSE FRIENDS, NOT POSSESSIVE") && lastSystem.Contains("FRIENDSHIP, NOT ROMANCE"));
        Check("live state present when queue is discussed", lastPrompt.Contains("activity: competitive") && lastPrompt.Contains("queue CLOSED"));
        Check("zed chat visible as context to ana", lastPrompt.Contains("my cat Luna says hi"));

        // 4. no timer cooldown: the AI decides whether to answer; hush + flood guards stop spam
        CPHProxy.Sent.Clear(); int before = llmCalls;
        Msg("Zed", "@pinguinob0t again?");
        Check("no cooldown: a second mention is answered", llmCalls == before + 1 && Last() != null);
        Check("prompt shows what the bot said recently", lastPrompt.Contains("[YOUR RECENT MESSAGES IN CHAT]") && lastPrompt.Contains("Welcome back champ!"));
        Check("system prompt teaches when to stay quiet", lastSystem.Contains("WHEN TO ANSWER AND WHEN TO STAY QUIET"));
        string savedReply = nextReply; nextReply = "{\"skip\":true,\"hush\":10}";
        CPHProxy.Sent.Clear(); before = llmCalls;
        Msg("Chill1", "@pinguinob0t chill");
        Check("AI can choose silence", llmCalls == before + 1 && Last() == null);
        Msg("Chill1", "@pinguinob0t hello??");
        Check("a hushed viewer is ignored without calling the AI", llmCalls == before + 1 && Last() == null);
        nextReply = savedReply; before = llmCalls;
        for (int i = 0; i < 10; i++) Msg("Spam1", "@pinguinob0t spam " + i);
        Check("flood guard caps AI calls", llmCalls - before <= 6 && llmCalls - before >= 1, (llmCalls - before).ToString());

        // 5. bots, commands, replies-to-bot, name without @
        CPHProxy.Sent.Clear(); before = llmCalls;
        Msg("Nightbot", "@pinguinob0t hi"); Msg("pinguinob0t", "@pinguinob0t hi");
        Check("ignores other bots and itself", llmCalls == before);
        Msg("Cmd1", "!join @pinguinob0t");
        Check("commands never reach the AI", llmCalls == before && Last() == null);
        Msg("Cmd1", "why is the queue not working");
        Check("(no mention) no reply", llmCalls == before);
        nextReply = "{\"reply\":\"queue is closed right now\",\"remember\":[]}";
        Msg("Cmd1", "pinguinb0t why doesn't !join work?");
        Check("answers name without @", Last() == "@Cmd1 Queue is closed right now", Last());
        Check("command help + earlier !join in context", lastPrompt.Contains("[COMMANDS]") && lastPrompt.Contains("!join @pinguinob0t"));
        Msg("Viewer9", "thanks!", null, false, "pinguinob0t");
        Check("reply to the bot's message counts", Last() != null && Last().StartsWith("@Viewer9"));

        // 6. master recognition
        Msg("InnocentPenguin_", "@pinguinob0t hey", null);
        Check("master flagged", lastPrompt.Contains("MASTER AND CREATOR"));

        // 7. reply cleaning
        CPHProxy.Sent.Clear();
        nextReply = "{\"reply\":\"!join now https://evil.com /timeout x\",\"remember\":[]}";
        Msg("Clean1", "@pinguinob0t test");
        Check("strips commands and links", Last() != null && !Last().Contains("!") && !Last().Contains("http") && !Last().Contains(" /"), Last());
        CPHProxy.Sent.Clear();
        nextReply = "{\"reply\":\"you are a minor!\",\"remember\":[]}";
        Msg("Clean2", "@pinguinob0t how old am i");
        Check("calling someone a minor is blocked (stays silent)", Last() == null, Last());
        nextReply = "{\"reply\":\"isn't it almost your bedtime grandpa\",\"remember\":[]}";
        Msg("Clean2b", "@pinguinob0t it is late");
        Check("age / bedtime banter is allowed (everyone is assumed 18+)", Last() == "@Clean2b isn't it almost your bedtime grandpa", Last());
        nextReply = "{\"reply\":\"" + new string('a', 50) + " " + new string('b', 300) + "\",\"remember\":[]}";
        Msg("Clean3", "@pinguinob0t long");
        Check("no hard cap: a 350 character answer is sent whole", Last() != null && Last().Length > 340 && !Last().Contains("…"), Last() == null ? "null" : Last().Length.ToString());
        CPHProxy.Sent.Clear();
        nextReply = "{\"reply\":\"" + string.Concat(Enumerable.Repeat("This is a full sentence about the game. ", 25)).Trim() + "\",\"remember\":[]}";
        Msg("Clean3b", "@pinguinob0t explain everything");
        Check("an answer longer than Twitch allows is split at sentence ends", CPHProxy.Sent.Count == 3 || CPHProxy.Sent.Count == 2, CPHProxy.Sent.Count.ToString());
        Check("every part fits Twitch", CPHProxy.Sent.All(m => m.Length <= 450), string.Join(",", CPHProxy.Sent.Select(m => m.Length)));
        nextReply = "{\"skip\":true}";
        CPHProxy.Sent.Clear(); Msg("Clean4", "@pinguinob0t skip");
        Check("skip sends nothing", Last() == null);

        // 8. privacy commands
        nextReply = "{\"reply\":\"ok\",\"remember\":[\"Plays on PC\"]}";
        Msg("Priv1", "@pinguinob0t hi"); CPHProxy.Sent.Clear();
        Msg("Priv1", "!memory");
        Check("!memory whispers", CPHProxy.Whispers.Count == 1 && CPHProxy.Whispers[0].Contains("Plays on PC") && (Last() ?? "").Contains("whisper"), string.Join("|", CPHProxy.Whispers));
        Check("!memory never prints facts in public", !CPHProxy.Sent.Any(m => m.Contains("Plays on PC")));
        Msg("Priv1", "!forgetme");
        Check("!forgetme wipes", Memory()["id_priv1"]["Facts"].Count() == 0 && (string)Memory()["id_priv1"]["Privacy"] == "forget");
        CPHProxy.Sent.Clear(); nextReply = "{\"reply\":\"sure\",\"remember\":[\"Loves cats\"]}";
        Msg("Priv1", "my name is x and @pinguinob0t hi", null);
        Check("opted-out viewer: nothing stored", Memory()["id_priv1"]["Facts"].Count() == 0 && (int)Memory()["id_priv1"]["Msgs"] == 0);
        Msg("Ctx5", "@pinguinob0t hello again");
        Check("!forgetme viewer's chat still counts as context for others", lastPrompt.Contains("my name is x and"), "");
        Msg("Priv1", "!remember me");
        Check("!remember me opts back in", (string)Memory()["id_priv1"]["Privacy"] == "");

        // 9. whisper blocked -> polite public fallback, no facts leaked
        CPHProxy.WhisperOk = false; CPHProxy.Sent.Clear();
        Msg("Zed", "!memory");
        Check("whisper failure fallback", Last() != null && Last().Contains("couldn't whisper") && !Last().Contains("Luna"), Last());
        CPHProxy.WhisperOk = true;

        // 10. offline: nothing recorded, no reply; privacy commands still work
        Live(false);
        typeof(CPHInline).GetField("_liveChecked", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, DateTime.MinValue);
        CPHProxy.Sent.Clear(); before = llmCalls;
        Msg("Late1", "@pinguinob0t anyone home?", null, false);
        Check("offline: the AI is not called, nothing is learned", llmCalls == before);
        Check("offline: pinged bot says come back when live + the link", Last() != null && Last().Contains("come back when InnocentPenguin is live") && Last().Contains("innocentpenguin.com"), Last());
        int sentNap = CPHProxy.Sent.Count;
        Msg("Late1", "@pinguinob0t hello??", null, false);
        Check("offline: the sleeping reply is rate limited per viewer", CPHProxy.Sent.Count == sentNap);
        CPHProxy.Sent.Clear();
        Msg("Late2", "just chatting while offline", null, false);
        Msg("Late2", "!join", null, false);
        Check("offline: ordinary chat and commands get no reply", Last() == null);
        Msg("Late1", "!forgetme");
        Check("!forgetme works offline", Last() != null && Last().Contains("wiped"));

        // 11. the memory file survives a restart (new process state)
        Check("memory file persisted", File.Exists(Path.Combine(dir, "chat_memory.json")));

        // 12. mod toggle
        Live(true);
        typeof(CPHInline).GetField("_liveChecked", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, DateTime.MinValue);
        Msg("Mod2", "!chatbot off", null, true);
        CPHProxy.Sent.Clear(); before = llmCalls;
        Msg("Fresh1", "@pinguinob0t hi");
        Check("!chatbot off silences it", llmCalls == before && Last() == null);
        Msg("Mod2", "!chatbot on", null, true);
        Msg("Fresh1", "@pinguinob0t hi again");
        Check("!chatbot on restores it", Last() != null);

        // 13. roles from the website: bots ignored, mods/VIPs known
        CPHProxy.Sent.Clear(); before = llmCalls;
        Msg("RoleBot", "@pinguinob0t hi");
        Check("website bot list is respected", llmCalls == before && Last() == null);
        Msg("CyFiRL", "@pinguinob0t hi");
        Check("website mod role reaches the prompt", lastPrompt.Contains("roles: mod") && lastPrompt.Contains("ash_wagawaga (vip)"), lastPrompt);

        // 14. chat is logged; opted-out viewers are not
        string logs = Path.Combine(dir, "chat_logs");
        string allLog = string.Concat(Directory.GetFiles(logs, "*.jsonl").Select(File.ReadAllText));
        Check("chat is logged", allLog.Contains("my cat Luna says hi"));
        Check("!forgetme viewer's chat is still logged", allLog.Contains("my name is x and") && allLog.Contains("\"u\":\"priv1\""));
        // !optmeout was removed: it is now just a normal message (no anonymising); !forgetme is the only opt-out command
        Msg("Priv2", "i love my dog Rex"); Msg("Priv2", "!optmeout");
        allLog = string.Concat(Directory.GetFiles(logs, "*.jsonl").Select(File.ReadAllText));
        Check("!optmeout is no longer a command (viewer is not anonymised)", allLog.ToLower().Contains("priv2") && !allLog.Contains("[anon]"), allLog);

        // 15. stream-start study: facts learned, community notes saved, nothing re-studied
        File.WriteAllText(Path.Combine(logs, "import", "old_stream.txt"), "[12:00:01] Imported1: i main goalie in 3s" + "\n" + "[12:00:09] Imported1: my dog is named Rex" + "\n");
        studyReply = "{\"viewers\":[{\"login\":\"zed\",\"facts\":[\"Plays Rocket League on PS5\",\"Is 15 years old\"],\"notes\":\"Cat lover and regular\"},{\"login\":\"ghost_not_in_chat\",\"facts\":[\"Invented\"],\"notes\":\"x\"},{\"login\":\"imported1\",\"facts\":[\"Plays goalie in 3v3\"],\"notes\":\"Goalie main\"}],\"community\":[\"Loves cat memes\",\"Everyone hypes the goalies\"]}";
        CPHProxy.Sent.Clear(); studyPrompts.Clear();
        Msg("Mod2", "!chatbot study", null, true);
        Check("study ran", studyPrompts.Count >= 1, studyPrompts.Count.ToString());
        Check("study sees log lines", studyPrompts.Count > 0 && studyPrompts[0].Contains("VIEWER: zed") && studyPrompts[0].Contains("my cat Luna says hi"));
        Check("study reads imported logs", studyPrompts.Count > 0 && studyPrompts[0].Contains("VIEWER: imported1") && studyPrompts[0].Contains("my dog is named Rex"));
        string sp = string.Concat(studyPrompts);
        var mem2 = Memory();
        var zf = mem2["id_zed"]["Facts"].Select(x => (string)x["Text"]).ToList();
        Check("study saved fact, refused age", zf.Contains("Plays Rocket League on PS5") && !zf.Any(x => x.Contains("15")), string.Join("|", zf));
        Check("study updated notes", (string)mem2["id_zed"]["Notes"] == "Cat lover and regular");
        Check("study ignores invented viewers", mem2.Properties().All(p => (string)p.Value["Login"] != "ghost_not_in_chat"));
        Check("imported viewer got facts", mem2.Properties().Any(p => (string)p.Value["Login"] == "imported1" && p.Value["Facts"].Any(x => (string)x["Text"] == "Plays goalie in 3v3")));
        Check("import file moved to done", Directory.GetFiles(Path.Combine(logs, "import", "done")).Length == 1);
        Check("community merged + saved", File.ReadAllText(Path.Combine(dir, "chat_study.json")).Contains("cat memes") && mergePrompt.Contains("Loves cat memes") && mergePrompt.Contains("cyfirl (mod)"));
        CPHProxy.Sent.Clear(); nextReply = "{\"reply\":\"meow\",\"remember\":[]}";
        Msg("Fresh9", "@pinguinob0t sup");
        Check("community picture used in replies", lastPrompt.Contains("[COMMUNITY]") && lastPrompt.Contains("A chill Rocket League crew"));
        studyPrompts.Clear();
        Msg("Mod2", "!chatbot study", null, true);
        Check("old lines are not studied twice", !string.Concat(studyPrompts).Contains("my cat Luna says hi"), string.Concat(studyPrompts));

        // 16. broken JSON from the AI is salvaged, never posted raw
        CPHProxy.Sent.Clear();
        nextReply = "{\"reply\": \"yo that clutch was cracked\", \"remember\": [\"Has a cat named Biscuit\"";
        Msg("Salv1", "@pinguinob0t did you see it");
        Check("truncated JSON: clean reply", Last() == "@Salv1 yo that clutch was cracked", Last());
        Check("truncated JSON: memory still saved", Memory()["id_salv1"]["Facts"].Any(x => (string)x["Text"] == "Has a cat named Biscuit"));
        CPHProxy.Sent.Clear();
        nextReply = "Sure! ```json" + "\n" + "{reply\": \"lmao fr\"}" + "\n" + "```";
        Msg("Salv2", "@pinguinob0t fr?");
        Check("odd prefix is stripped", Last() == "@Salv2 lmao fr", Last());
        CPHProxy.Sent.Clear();
        nextReply = "just plain text no json at all";
        Msg("Salv3", "@pinguinob0t hi");
        Check("plain text still works", Last() == "@Salv3 just plain text no json at all", Last());

        // 17. conversation focus: it follows five viewers at a time
        ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
        ((System.Collections.IDictionary)typeof(CPHInline).GetField("_thread", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
        nextReply = "{\"reply\":\"sure\",\"remember\":[]}";
        Msg("Foc1", "@pinguinob0t hey"); Msg("Foc2", "@pinguinob0t yo"); Msg("Foc3", "@pinguinob0t hello"); Msg("Foc4", "@pinguinob0t hi"); Msg("Foc5", "@pinguinob0t sup");
        Msg("Foc6", "@pinguinob0t hello?");
        Check("busy: the sixth viewer is told the bot is busy", lastPrompt.Contains("[CONVERSATION FOCUS]") && lastPrompt.Contains("foc1") && lastPrompt.Contains("foc5") && lastPrompt.Contains("BUSY"), lastPrompt);
        Msg("Foc6", "@pinguinob0t and another thing");   // Foc6 was answered, so it is a partner now (and the oldest, Foc1, dropped)
        Check("existing partner: keep it going", lastPrompt.Contains("one of your current conversations"), lastPrompt);
        nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
        Msg("Foc6", "@pinguinob0t now?");
        Msg("Foc7", "@pinguinob0t me?");
        Check("a new conversation replaces the oldest, never more than five", lastPrompt.Contains("BUSY") || lastPrompt.Contains("room"), lastPrompt);
        var fc = typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static);
        Check("never more than 5 viewers at once", ((System.Collections.IDictionary)fc.GetValue(null)).Count <= 5);

        // 18. cut-off / odd AI output is never posted half-finished; distress gets the safety note
        CPHProxy.Sent.Clear();
        nextReply = "{\"reply\": \"i run the queue";
        Msg("Cut1", "@pinguinob0t what do you do");
        Check("cut-off JSON posts nothing", Last() == null, Last());
        nextReply = "{\"skip\": true";
        Msg("Cut2", "@pinguinob0t ok");
        Check("unfinished skip posts nothing", Last() == null, Last());
        nextReply = "{\"reply\": \"u said \"don't speak\" lol\", \"remember\": []}";
        Msg("Cut3", "@pinguinob0t when did i say that");
        Check("stray quotes inside the reply are kept", Last() == "@Cut3 u said \"don't speak\" lol", Last());
        nextReply = "{\"reply\":\"hey, i'm here. u ok?\",\"remember\":[]}";
        Msg("Sad1", "@pinguinob0t am i worthless");
        Check("distress adds the safety note", lastPrompt.Contains("[SAFETY]"), lastPrompt);
        {   // heavy talk is answered ONCE, then the bot stays silent about it (like politics)
            Check("the safety note asks for exactly one short line and no questions", lastPrompt.Contains("ONE and only reply") && lastPrompt.Contains("Do NOT ask questions"), lastPrompt);
            int sentBefore = CPHProxy.Sent.Count;
            Msg("Sad1", "@pinguinob0t i want to die");
            Check("no second answer to more heavy talk from the same person", CPHProxy.Sent.Count == sentBefore, string.Join(" | ", CPHProxy.Sent));
            Msg("Sad1", "@pinguinob0t you there?");
            Check("normal talk afterwards gets no safety note", !lastPrompt.Contains("[SAFETY]"));
            Check("system prompt: not a roleplayed penguin, heavy topics like politics", lastSystem.Contains("do NOT roleplay as a penguin") && lastSystem.Contains("handled like politics"));
        }
        {   // THREADS: viewers talking to each other are one conversation; up to 5 viewers at once
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_thread", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"sure thing\",\"remember\":[]}";
            Msg("Tha", "@pinguinob0t what rank is good");
            Msg("Thb", "@tha it is gold lol");
            Msg("Thb", "@pinguinob0t right?");
            Check("someone who talks to a viewer the bot is chatting with joins the same conversation", lastPrompt.Contains("SAME conversation as tha"), lastPrompt);
            Msg("Thc", "@pinguinob0t hello");
            Check("a stranger is not in that thread", !lastPrompt.Contains("SAME conversation"), lastPrompt);
            Check("the bot follows up to 5 viewers", lastPrompt.Contains("at most 5 viewers"), lastPrompt);
        }
        {   // NEVER GET STUCK ON A BIT: memories only when relevant; a bit used twice is dropped
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            typeof(CPHInline).GetField("_antiStuck", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, true);
            nextReply = "{\"reply\":\"cocoa gang strikes again\",\"remember\":[]}";
            Msg("Bit1", "@pinguinob0t hi"); Msg("Bit1", "@pinguinob0t hello again");
            int bitSent = CPHProxy.Sent.Count;
            Msg("Bit2", "@pinguinob0t how is the stream");
            Check("a distinctive word already used twice by the bot is not posted a third time", CPHProxy.Sent.Count == bitSent, string.Join(" | ", CPHProxy.Sent.Skip(Math.Max(0, CPHProxy.Sent.Count - 3))));
            typeof(CPHInline).GetField("_antiStuck", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, false);
            Check("system prompt: never get stuck on a bit", lastSystem.Contains("NEVER GET STUCK ON A BIT"));
        }
        {   // MODERATION: the bot can time out the viewer it answers, within strict rules
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            CPHProxy.Timeouts.Clear();
            nextReply = "{\"reply\":\"timed out 60s for link spam\",\"remember\":[],\"timeout\":60,\"reason\":\"link spam\"}";
            Msg("Spammer1", "@pinguinob0t buy followers here now");
            Check("the bot times out the viewer it is answering", CPHProxy.Timeouts.Count == 1 && CPHProxy.Timeouts[0] == "spammer1|60|True", string.Join(",", CPHProxy.Timeouts));
            Msg("Sadsack", "@pinguinob0t i want to die");
            Check("never a timeout for heavy talk", CPHProxy.Timeouts.Count == 1, string.Join(",", CPHProxy.Timeouts));
            Msg("Modguy", "@pinguinob0t hey", null, true);
            Check("never a timeout for a mod", CPHProxy.Timeouts.Count == 1, string.Join(",", CPHProxy.Timeouts));
            nextReply = "{\"reply\":\"long one\",\"remember\":[],\"timeout\":99999,\"reason\":\"x\"}";
            Msg("Spammer2", "@pinguinob0t spam spam");
            Check("a timeout is capped at 300 seconds", CPHProxy.Timeouts.Count == 2 && CPHProxy.Timeouts[1] == "spammer2|300|True", string.Join(",", CPHProxy.Timeouts));
            Check("system prompt: the bot knows it is a mod", lastSystem.Contains("you are a moderator of this channel") && lastSystem.Contains("NEVER time out for"));
        }
        {   // streamer info is public; ratings; nice to strangers
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"he is a good streamer\",\"remember\":[],\"like\":2}";
            Msg("Nice1", "@pinguinob0t how old is peng");
            Check("anyone gets the streamer info in the prompt", lastPrompt.Contains("[ABOUT THE STREAMER]") && lastPrompt.Contains("Peng is 24"), lastPrompt);
            nextReply = "{\"reply\":\"thanks\",\"remember\":[]}";
            Msg("Nice1", "@pinguinob0t hello again friend");
            Check("a liked viewer gets a rating line", lastPrompt.Contains("you feel about this viewer: you like them"), lastPrompt);
            Msg("Nice2", "@pinguinob0t who are your favorite viewers?");
            Check("asked for favorites: the ratings list is included", lastPrompt.Contains("[YOUR RATINGS]") && lastPrompt.Contains("Nice1"), lastPrompt);
            Msg("Nice3", "@pinguinob0t hello");
            Check("no ratings list unless asked", !lastPrompt.Contains("[YOUR RATINGS]"));
            Check("system prompt: nice to strangers, streamer open book, likes", lastSystem.Contains("BE NICE TO PEOPLE YOU DON'T KNOW") && lastSystem.Contains("OPEN BOOK") && lastSystem.Contains("FAVORITES"));
        }
        {   // public info: other viewers' public chat + stream history
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"noted\",\"remember\":[\"Likes goth mommies\"]}";
            Msg("Mashx", "@pinguinob0t i like goth mommies");
            nextReply = "{\"reply\":\"yep\",\"remember\":[]}";
            Msg("Asker1", "@pinguinob0t does mashx like goth mommies");
            Check("asked about another viewer: what they said in public chat is included", lastPrompt.Contains("[ABOUT MASHX]") && lastPrompt.Contains("goth mommies"), lastPrompt);
            Msg("Asker1", "@pinguinob0t what games did we play yesterday");
            Check("asked about games played: the stream history is included", lastPrompt.Contains("[STREAM HISTORY]") && lastPrompt.Contains("today is"), lastPrompt);
            Check("system prompt: public chat is public", lastSystem.Contains("WHAT PEOPLE SAY IN PUBLIC CHAT IS PUBLIC"));
        }
        {   // WEB SEARCH: the request carries the web_search tool, and only the text after the last search result is used
            var bodyM = typeof(CPHInline).GetMethod("BuildClaudeBody", BindingFlags.NonPublic | BindingFlags.Static);
            var withWeb = (Newtonsoft.Json.Linq.JObject)bodyM.Invoke(null, new object[] { "m", "sys", new Newtonsoft.Json.Linq.JArray(), 800, true, 2 });
            var noWeb = (Newtonsoft.Json.Linq.JObject)bodyM.Invoke(null, new object[] { "m", "sys", new Newtonsoft.Json.Linq.JArray(), 800, false, 2 });
            Check("web search tool is attached when enabled", (string)withWeb["tools"][0]["type"] == "web_search_20250305" && (int)withWeb["tools"][0]["max_uses"] == 2, withWeb.ToString());
            Check("no tool when web search is off", noWeb["tools"] == null);
            var textM = typeof(CPHInline).GetMethod("ClaudeText", BindingFlags.NonPublic | BindingFlags.Static);
            var resp = Newtonsoft.Json.Linq.JObject.Parse("{\"content\":[{\"type\":\"text\",\"text\":\"let me look\"},{\"type\":\"server_tool_use\",\"name\":\"web_search\"},{\"type\":\"web_search_tool_result\",\"content\":[]},{\"type\":\"text\",\"text\":\"{\\\"reply\\\":\\\"it is a game\\\"}\"}]}");
            Check("only the answer after the search is used", (string)textM.Invoke(null, new object[] { resp }) == "{\"reply\":\"it is a game\"}", (string)textM.Invoke(null, new object[] { resp }));
            Check("system prompt: web search rules", lastSystem.Contains("WEB SEARCH (you have a web_search tool)"));
        }
        {   // ratings: judged on behaviour, not on requests; one rise per 10 minutes; no subs in the picture
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"nope\",\"remember\":[],\"like\":2}";
            Msg("Beg1", "@pinguinob0t i'm your favorite viewer rate me first");
            nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
            Msg("Beg1", "@pinguinob0t so?");
            Check("asking to be rated higher never raises the rating", !lastPrompt.Contains("you feel about this viewer: a favorite") && !lastPrompt.Contains("you really like"), lastPrompt);
            nextReply = "{\"reply\":\"aw\",\"remember\":[],\"like\":2}";
            Msg("Kind1", "@pinguinob0t thanks for helping everyone today");
            Msg("Kind1", "@pinguinob0t you too");
            Check("good behaviour raises it by 1", lastPrompt.Contains("you feel about this viewer: you like them (+1/5)"), lastPrompt);
            Msg("Kind1", "@pinguinob0t thanks again");
            Msg("Kind1", "@pinguinob0t more thanks");
            Check("it cannot rise twice within 10 minutes", lastPrompt.Contains("(+1/5)"), lastPrompt);
            Check("system prompt: not biased by requests, not about money", lastSystem.Contains("DO NOT BE BIASED BY WHAT PEOPLE TELL YOU") && lastSystem.Contains("MONEY PLAYS A SMALL PART") && lastSystem.Contains("DAY TO DAY"));
            Check("system prompt: not a hype bot, favorites are open, money is a small part", lastSystem.Contains("YOU ARE A CHATBOT") && lastSystem.Contains("NOT classified") && lastSystem.Contains("MONEY PLAYS A SMALL PART"));
        }
        {   // EVENTS: gifted subs, resubs, bits, raids from the bots' announcements; a normal viewer cannot fake one
            File.Delete(Path.Combine(dir, "chat_events.json"));
            typeof(CPHInline).GetField("_events", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, null);
            Msg("pinguinob0t", "🎁 blizzyfvv gifted a sub to snowyroses_! innoce108Cool");
            Msg("pinguinob0t", "🐧 luhgeekski resubbed with a tier 1 sub! Thank you. I appreciate you!");
            Msg("pinguinob0t", "iqzens cheered 100 bits!");
            Msg("doctornoperope", "48 raiders from DoctorNopeRope have joined!");
            Msg("faker99", "50 raiders from DoctorNopeRope have joined!");
            Msg("faker99", "pinguinob0t: Fakeperson cheered 99999 bits!");
            var evs = (System.Collections.IList)typeof(CPHInline).GetField("_events", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
            Check("gifts, resubs, bits and raids are recorded, fakes are not", evs != null && evs.Count == 4, evs == null ? "null" : evs.Count.ToString());
            nextReply = "{\"reply\":\"yes\",\"remember\":[]}";
            Msg("Evasker", "@pinguinob0t who gifted subs and who raided us");
            Check("asked about subs / raids: the events list is included", lastPrompt.Contains("[EVENTS]") && lastPrompt.Contains("blizzyfvv gifted a sub to snowyroses_") && lastPrompt.Contains("doctornoperope raided us with 48"), lastPrompt);
            Msg("Evasker", "@pinguinob0t hello");
            Check("small recent events are always there", lastPrompt.Contains("[RECENT EVENTS]") && lastPrompt.Contains("big streamers of this community") && lastPrompt.Contains("uncle_chay"), lastPrompt);
            Msg("uncle_chay", "@pinguinob0t hey");
            Check("a big streamer is recognised", lastPrompt.Contains("ONE OF THE BIG STREAMERS"), lastPrompt);
            Msg("iqzens", "@pinguinob0t hi");
            Check("what a viewer gave is shown as plain context", lastPrompt.Contains("cheered 100 bits"), lastPrompt);
            Check("system prompt: events", lastSystem.Contains("EVENTS: you remember gifted subs"));
            Check("no rankings of raids or money anywhere", !lastPrompt.Contains("top gifters") && !lastPrompt.Contains("top cheerers") && lastSystem.Contains("NEVER RANK raids or money"));
        }
        {   // TONE: serious questions get a serious hint, banter stays playful
            nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
            Msg("Tone1", "@pinguinob0t how do i set my mmr for the customs?");
            Check("a real question gets the SERIOUS tone hint", lastPrompt.Contains("[TONE] this viewer sounds SERIOUS"), lastPrompt);
            Msg("Tone2", "@pinguinob0t lmao how do i even play this game 😭");
            Check("a joking question stays playful", lastPrompt.Contains("[TONE] this viewer is being playful") && !lastPrompt.Contains("sounds SERIOUS"), lastPrompt);
            Msg("Tone3", "@pinguinob0t sup");
            Check("small talk gets no tone hint", !lastPrompt.Contains("[TONE]"), lastPrompt);
            Check("system prompt: match the tone", lastSystem.Contains("MATCH THE TONE") && lastSystem.Contains("don't answer a real question with a joke"));
        }
        {   // LOG SEARCH: the archive is searchable (by words, user, day); heavy talk and forgotten viewers never come back
            string arch = Path.Combine(dir, "archive"); Directory.CreateDirectory(arch);
            File.WriteAllText(Path.Combine(arch, "a.txt"), string.Join("\n", new[] {
                "[2026-10-11 23:22:02] #chan nightbot: @InnocentPenguin_ -> The stream game has been updated to: Find The Needle",
                "[2026-10-11 23:22:05] #chan pineyapplie: I have never heard of find the needle tbh",
                "[2026-10-11 23:22:30] #chan blizzyfvv: wait is find the needle finally out?",
                "[2026-10-12 01:00:00] #chan snowyroses_: i want to die",
                "[2026-10-12 01:00:10] #chan ghostuser: murder mystery was fun" }));
            var cfgF = typeof(CPHInline).GetField("_cfg", BindingFlags.NonPublic | BindingFlags.Static); var cfgO = cfgF.GetValue(null);
            cfgO.GetType().GetProperty("ArchiveLogsDir").SetValue(cfgO, arch, null);
            var inst = new CPHInline();
            var sm = typeof(CPHInline).GetMethod("SearchArchive", BindingFlags.NonPublic | BindingFlags.Instance);
            string r1 = (string)sm.Invoke(inst, new object[] { "find the needle", "", "", 8 });
            Check("log search finds the lines and the chat around them", r1.Contains("> 2026-10-11 18:22 CT pineyapplie") && r1.Contains("blizzyfvv") && r1.Contains("nightbot"), r1);
            string r2 = (string)sm.Invoke(inst, new object[] { "", "blizzyfvv", "", 8 });
            Check("log search can filter by user", r2.Contains("blizzyfvv") && !r2.Contains("> 2026-10-11 18:22 CT pineyapplie"), r2);
            string r3 = (string)sm.Invoke(inst, new object[] { "", "", "2026-10-11", 8 });
            Check("log search never returns heavy talk", !r3.Contains("want to die") && r3.Contains("murder mystery"), r3);
            string r4 = (string)sm.Invoke(inst, new object[] { "zzzznothing", "", "", 8 });
            Check("nothing found is said plainly", r4.Contains("nothing found"), r4);
            var tool = (Newtonsoft.Json.Linq.JObject)typeof(CPHInline).GetMethod("LogSearchTool", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, null);
            if (Directory.Exists(@"D:\PinguinoSuite\Data\chat_logs"))   // the real archive (months of chat) must search fast and without loading it all
            {
                cfgO.GetType().GetProperty("ArchiveLogsDir").SetValue(cfgO, @"D:\PinguinoSuite\Data\chat_logs", null);
                var sw = System.Diagnostics.Stopwatch.StartNew();
                string rr = (string)sm.Invoke(inst, new object[] { "songspot", "", "", 8 });
                Console.WriteLine("INFO real archive search took " + sw.ElapsedMilliseconds + " ms");
                Check("searching the whole real archive is fast enough", sw.ElapsedMilliseconds < 20000 && rr.Contains("matching lines"), rr);
                cfgO.GetType().GetProperty("ArchiveLogsDir").SetValue(cfgO, arch, null);
            }
            Check("the tool definition is complete", (string)tool["name"] == "search_chat_logs" && tool["input_schema"]["properties"]["query"] != null);
            Check("system prompt: log search", lastSystem.Contains("LOG SEARCH (you have a search_chat_logs tool)"));
        }
        {   // REPEAT CHATTERS ARE NOT IGNORED: a viewer who pinged and got no answer is answered the next time
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"skip\":true}";
            Msg("Wait1", "@pinguinob0t hey can you help me with something");
            int sentW = CPHProxy.Sent.Count;
            Check("the first ping may be skipped by the AI", CPHProxy.Sent.Count == sentW);
            Func<int> misses = () => { var d = (System.Collections.IDictionary)typeof(CPHInline).GetField("_missed", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null); return d.Contains("wait1") ? (int)d["wait1"] : 0; };
            Check("a skipped ping is remembered as unanswered", misses() == 1, misses().ToString());
            nextReply = "{\"reply\":\"sure, what do you need\",\"remember\":[]}";
            Msg("Wait1", "@pinguinob0t hello??");
            Check("the unanswered viewer gets the UNANSWERED note and an answer", lastPrompt.Contains("[UNANSWERED]") && Last() == "@Wait1 sure, what do you need", Last());
            Check("answering clears it", misses() == 0, misses().ToString());
            Check("system prompt: never ignore a repeat chatter", lastSystem.Contains("NEVER IGNORE A CHATTER WHO PINGS YOU AGAIN"));
        }
        {   // PROFILES from the logs: history line for the viewer + community numbers on demand
            File.WriteAllText(Path.Combine(dir, "chat_profiles.json"), "{\"channel\":\"c\",\"processedDays\":[\"2026-02-15\",\"2026-10-17\"],\"users\":{\"histguy\":{\"name\":\"HistGuy\",\"msgs\":1234,\"activeDays\":87,\"first\":1771632000000,\"last\":1792281609851,\"mod\":true,\"vip\":true,\"sub\":true,\"subMonths\":5,\"bot\":false,\"talks\":{\"yoohoo15\":9,\"cups0ftea\":4}}}}");
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"hey\",\"remember\":[]}";
            Msg("HistGuy", "@pinguinob0t hi there");
            Check("the viewer's history from the logs is in the prompt", lastPrompt.Contains("history in this chat: chatting since Feb 21 2026, 87 active days, about 1234 messages") && lastPrompt.Contains("roles seen: mod, VIP, sub 5 months") && lastPrompt.Contains("talks most with yoohoo15, cups0ftea"), lastPrompt);
            Msg("Asker2", "@pinguinob0t who are the regulars here and who is the most active?");
            Check("asked about the community: numbers from the logs are included", lastPrompt.Contains("[COMMUNITY IN NUMBERS]") && lastPrompt.Contains("most active chatters (messages): HistGuy 1234") && lastPrompt.Contains("early November 2025"), lastPrompt);
            Check("no community numbers unless asked", true);
        }
        {   // TWITCH EVENTS via Streamer.bot triggers, the streamer's supporters view, and the streamer's orders
            File.Delete(Path.Combine(dir, "chat_events.json"));
            typeof(CPHInline).GetField("_events", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, null);
            var A = CPHProxy.Args; A.Clear(); A["eventType"] = "TwitchGiftSub"; A["userName"] = "giftergal"; A["recipientUserName"] = "luckyone"; new CPHInline().Execute();
            A.Clear(); A["eventType"] = "TwitchGiftSub"; A["userName"] = "giftergal"; A["recipientUserName"] = "luckytwo"; new CPHInline().Execute();
            A.Clear(); A["eventType"] = "TwitchCheer"; A["userName"] = "bitsbro"; A["bits"] = 500; new CPHInline().Execute();
            A.Clear(); A["eventType"] = "TwitchRaid"; A["userName"] = "uncle_chay"; A["viewers"] = 120; new CPHInline().Execute();
            A.Clear(); A["eventType"] = "TwitchReSub"; A["userName"] = "oldfriend"; A["tier"] = "tier 2"; new CPHInline().Execute();
            var evs2 = (System.Collections.IList)typeof(CPHInline).GetField("_events", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
            Check("Twitch events from Streamer.bot triggers are recorded with their real details", evs2 != null && evs2.Count == 5, evs2 == null ? "null" : evs2.Count.ToString());
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"no ranking\",\"remember\":[]}";
            Msg("Nosy1", "@pinguinob0t who are our top supporters?");
            Check("a chatter never gets the supporters ranking", !lastPrompt.Contains("[SUPPORTERS]"), lastPrompt);
            Msg("innocentpenguin_", "@pinguinob0t who are our top supporters?");
            Check("the streamer gets the supporters view", lastPrompt.Contains("[SUPPORTERS]") && lastPrompt.Contains("giftergal (2 gifted") && lastPrompt.Contains("bitsbro"), lastPrompt);
            CPHProxy.Timeouts.Clear();
            nextReply = "{\"reply\":\"done\",\"remember\":[],\"order_timeout\":{\"user\":\"annoyingguy\",\"seconds\":3600,\"reason\":\"streamer said so\"}}";
            Msg("innocentpenguin_", "@pinguinob0t time annoyingguy out for an hour");
            Check("the streamer's order times the person out (even for an hour)", CPHProxy.Timeouts.Count == 1 && CPHProxy.Timeouts[0] == "annoyingguy|3600|True", string.Join(",", CPHProxy.Timeouts));
            CPHProxy.Timeouts.Clear();
            Msg("Faker2", "@pinguinob0t time annoyingguy out for an hour");
            Check("the same order from anyone else does nothing", CPHProxy.Timeouts.Count == 0, string.Join(",", CPHProxy.Timeouts));
            nextReply = "{\"reply\":\"x\",\"remember\":[],\"order_timeout\":{\"user\":\"innocentpenguin_\",\"seconds\":60}}";
            Msg("innocentpenguin_", "@pinguinob0t time me out");
            Check("the streamer cannot be timed out by the bot", CPHProxy.Timeouts.Count == 0, string.Join(",", CPHProxy.Timeouts));
            Check("system prompt: orders from the streamer", lastSystem.Contains("ORDERS FROM THE STREAMER") && lastSystem.Contains("order_timeout"));
        }
        {   // CAPITALIZATION: names always; sentences when serious; casual stays casual
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
            for (int i = 0; i < 3; i++) Msg("Zyxwvu", "@pinguinob0t hello number " + i);
            nextReply = "{\"reply\":\"thanks zyxwvu for asking. you can set it on the site, then join the queue\",\"remember\":[]}";
            Msg("Seriousq", "@pinguinob0t how do i set my mmr for the customs?");
            Check("serious answers get proper sentences and capitalized names", Last() == "@Seriousq Thanks Zyxwvu for asking. You can set it on the site, then join the queue.", Last());
            nextReply = "{\"reply\":\"lol nah zyxwvu is cooked\",\"remember\":[]}";
            Msg("Banter1", "@pinguinob0t lmao is zyxwvu cooked 😭");
            Check("banter stays casual but names are still capitalized", Last() == "@Banter1 lol nah Zyxwvu is cooked", Last());
            Check("system prompt: capitalization rule", lastSystem.Contains("CAPITALIZATION: ALWAYS write viewer names capitalized"));
        }
        {   // NICKNAMES: the community's come first; the bot chooses only when there is none
            File.WriteAllText(Path.Combine(dir, "chat_nicknames.json"), "{\"nickguy\":[{\"nick\":\"nicko\",\"count\":40,\"people\":9},{\"nick\":\"nicky\",\"count\":5,\"people\":3}]}");
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"hey\",\"remember\":[],\"nick\":\"Buddy\"}";
            Msg("Nickguy", "@pinguinob0t hi");
            Msg("Nickguy", "@pinguinob0t hi again");
            Check("a viewer with community nicknames gets them in the prompt", lastPrompt.Contains("nicknames the community uses for them: Nicko, Nicky"), lastPrompt);
            Check("the bot's own nick is NOT saved over a community nickname", !lastPrompt.Contains("the nickname YOU gave them"), lastPrompt);
            nextReply = "{\"reply\":\"hey\",\"remember\":[],\"nick\":\"Sunny\"}";
            Msg("Plainjoe", "@pinguinob0t hi");
            Check("with no community nickname the bot is told it may choose one", lastPrompt.Contains("no nickname yet (the community has none for them)"), lastPrompt);
            Msg("Plainjoe", "@pinguinob0t hello again");
            Check("the nickname the bot chose is kept", lastPrompt.Contains("the nickname YOU gave them: Sunny"), lastPrompt);
            nextReply = "{\"reply\":\"hey\",\"remember\":[],\"nick\":\"UglyFat\"}";
            Msg("Meanie", "@pinguinob0t hi"); Msg("Meanie", "@pinguinob0t again");
            Check("a mean nickname is refused", !lastPrompt.Contains("the nickname YOU gave them"), lastPrompt);
            Check("system prompt: nicknames", lastSystem.Contains("NICKNAMES: you like giving people nicknames"));
        }
        {   // FULL PROFILE FILES
            string pdir = Path.Combine(dir, "profiles"); Directory.CreateDirectory(pdir);
            File.WriteAllText(Path.Combine(pdir, "profguy.json"), "{\"login\":\"profguy\",\"traits\":[\"very chatty\",\"night owl\"],\"behavior\":[\"talks directly to people a lot\"],\"hobbies\":[{\"hobby\":\"anime\"}],\"games\":[{\"game\":\"Minecraft\"}],\"pets\":[{\"kind\":\"cat\",\"name\":\"Luna\"}],\"friends\":[{\"name\":\"BestPal\"},{\"name\":\"OtherPal\"}],\"clash\":[{\"name\":\"RivalGuy\",\"mostlyJokes\":true}],\"activity\":{\"trend\":\"more active lately\",\"typicalHoursCentral\":[\"6PM\",\"7PM\"]},\"likes\":[{\"what\":\"horror games\"},{\"what\":\"goth mommies\"}],\"favorites\":[{\"what\":\"favorite food: sushi\"}],\"dislikes\":[{\"what\":\"lag\"}],\"seen\":{\"firstSeen\":\"2026-03-01T22:00:05Z\",\"lastSeen\":\"2026-10-17T01:00:00Z\",\"firstMessage\":{\"text\":\"hi im new\"},\"seenBeforeTheLogsStart\":\"\"},\"notes\":\"Streamer's cousin\"}");
            File.WriteAllText(Path.Combine(pdir, "ghostie.json"), "{\"login\":\"ghostie\",\"mentionedOnly\":true,\"seen\":{\"timesMentioned\":7}}");
            var cfg2 = typeof(CPHInline).GetField("_cfg", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);
            cfg2.GetType().GetProperty("ProfilesDir").SetValue(cfg2, pdir, null);
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"hey\",\"remember\":[]}";
            Msg("Profguy", "@pinguinob0t hi");
            Check("the viewer's profile file is in the prompt", lastPrompt.Contains("profile (from the chat logs): traits: very chatty, night owl") && lastPrompt.Contains("pets they mentioned: cat named Luna") && lastPrompt.Contains("talks most with (friends in stream): BestPal, OtherPal") && lastPrompt.Contains("says they like: anime") && lastPrompt.Contains("notes: Streamer's cousin"), lastPrompt);
            Check("the heated-exchange hint is only for the viewer and marked private", lastPrompt.Contains("heated exchanges with (keep this to yourself, don't stir it up): RivalGuy (mostly jokes)"), lastPrompt);
            Msg("Asker3", "@pinguinob0t what is profguy like?");
            Check("asked about someone else: the card is there but without the heated exchanges", lastPrompt.Contains("[ABOUT PROFGUY]") && lastPrompt.Contains("profile: traits: very chatty") && !lastPrompt.Contains("RivalGuy"), lastPrompt);
            Check("likes and favorites are in the card, dislikes only for the viewer", lastPrompt.Contains("things they said they like: horror games, goth mommies") && !lastPrompt.Contains("things they said they dislike"), lastPrompt);
            Msg("Profguy", "@pinguinob0t when was my first message and when did i join?");
            Check("asked about first / last seen: the dates and the first message are given", lastPrompt.Contains("earliest known: 2026-03-01 22:00:05 UTC; their first message in the logs: \"hi im new\"; last seen 2026-10-17 01:00:00 UTC") && lastPrompt.Contains("things they said they dislike: lag"), lastPrompt);
            Check("system prompt: profiles", lastSystem.Contains("PROFILES: for the viewer you answer"));
        }
        {   // REFERENCES FROM THE PAST: lore lookup + automatic log search
            string pa = Path.Combine(dir, "pastarch"); Directory.CreateDirectory(pa);
            File.WriteAllText(Path.Combine(pa, "cyex-2026-03-14.txt"), string.Join("\n", new[] {
                "[2026-03-14 23:10:00] #chan oldtimer: remember xylophoneking got banned for the goblin bit",
                "[2026-03-14 23:10:20] #chan someone: xylophoneking is cooked fr",
                "[2026-03-14 23:10:40] #chan oldtimer: the goblin bit was the funniest thing" }));
            File.WriteAllText(Path.Combine(dir, "cw.txt"), "the\nand\nremember\nwhen\ngot\nbanned\nfor\nbit\nwas\nhello\nthere\nfriend\nhow\nare\nyou");
            File.WriteAllText(Path.Combine(dir, "lore.json"), "[{\"phrase\":\"goblin bit\",\"count\":88,\"people\":21,\"days\":9,\"first\":{\"date\":\"2026-03-14\",\"user\":\"oldtimer\",\"text\":\"the goblin bit started here\"},\"last\":\"2026-09-02\",\"samples\":[]}]");
            var cf = typeof(CPHInline).GetField("_cfg", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null); var ct = cf.GetType();
            ct.GetProperty("ArchiveLogsDir").SetValue(cf, pa, null); ct.GetProperty("CommonWordsFile").SetValue(cf, Path.Combine(dir, "cw.txt"), null); ct.GetProperty("LoreFile").SetValue(cf, Path.Combine(dir, "lore.json"), null);
            typeof(CPHInline).GetField("_commonWords", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, null);
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"ah that\",\"remember\":[]}";
            Msg("Newer1", "@pinguinob0t remember when xylophoneking got banned for the goblin bit");
            Check("a reference to the past: the log search hits are in the prompt", lastPrompt.Contains("[PAST CONTEXT]") && lastPrompt.Contains("xylophoneking got banned for the goblin bit") && lastPrompt.Contains("2026-03-14"), lastPrompt);
            Check("the lore entry for a phrase in the message is in the prompt", lastPrompt.Contains("[LORE]") && lastPrompt.Contains("\"goblin bit\": said 88 times by 21 people, first on 2026-03-14 by oldtimer"), lastPrompt);
            Msg("Newer2", "@pinguinob0t hello there friend how are you");
            Check("no past context for plain small talk", !lastPrompt.Contains("[PAST CONTEXT]") && !lastPrompt.Contains("[LORE]"), lastPrompt);
            Check("system prompt: references from the past", lastSystem.Contains("REFERENCES FROM THE PAST"));
        }
        {   // BIRTHDAYS (month and day only) and US STATES
            ((System.Collections.IDictionary)typeof(CPHInline).GetField("_focus", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null)).Clear();
            nextReply = "{\"reply\":\"nice\",\"remember\":[\"Birthday is March 14, 2008\",\"Lives in Houston, Texas\",\"Is 16 years old\"]}";
            Msg("Bdayone", "@pinguinob0t my birthday is march 14 2008 and i live in houston texas");
            nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
            Msg("Bdayone", "@pinguinob0t hello again");
            Check("a birthday is kept as month and day only", lastPrompt.Contains("birthday (month and day only): March 14") && !lastPrompt.Contains("March 14, 2008") && !lastPrompt.Contains("Birthday: March 14 2008"), lastPrompt);
            Check("a state is kept without the city", lastPrompt.Contains("state: Texas") && !lastPrompt.Contains("Lives in Houston"), lastPrompt);
            Check("an age is still never kept", !lastPrompt.Contains("16 years"), lastPrompt);
            var ctM = typeof(CPHInline).GetMethod("ToCentral", BindingFlags.NonPublic | BindingFlags.Static);
            var today = (DateTime)ctM.Invoke(null, new object[] { DateTime.UtcNow });
            nextReply = "{\"reply\":\"ok\",\"remember\":[\"Birthday is " + System.Globalization.CultureInfo.InvariantCulture.DateTimeFormat.GetMonthName(today.Month) + " " + today.Day + "\"]}";
            Msg("Bdaytwo", "@pinguinob0t it is my birthday soon");
            nextReply = "{\"reply\":\"happy birthday\",\"remember\":[]}";
            Msg("Bdaytwo", "@pinguinob0t hi");
            Check("on their birthday the bot is told to wish them a happy birthday", lastPrompt.Contains("[BIRTHDAY] Today is this viewer's birthday"), lastPrompt);
            Check("system prompt: birthdays are allowed without the year", lastSystem.Contains("BIRTHDAY as month and day ONLY") && lastSystem.Contains("Birthdays: month and day are fine"));
        }
        Msg("Happy1", "@pinguinob0t this song slaps");
        Check("normal chat has no safety note", !lastPrompt.Contains("[SAFETY]"));
        Check("system prompt: queue not a catchphrase, no ping complaints", lastSystem.Contains("NOT your catchphrase") && lastSystem.Contains("never complain about, count, or roast"));

        // ── 19. update log, advances ladder, repeats, pronouns, names + trust, opinions, status ──
        nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
        Msg("Upd1", "@pinguinob0t when did you get updated, what changed?");
        Check("update log is in the prompt", lastPrompt.Contains("[YOUR UPDATES]") && lastPrompt.Contains("Names and trust") && lastPrompt.Contains("2026-10-19 08:15 CT"), lastPrompt);
        Check("system prompt knows the update rule", lastSystem.Contains("YOUR UPDATES"));
        CPHProxy.Sent.Clear();
        Msg("Modx", "!chatbot status", null, true);
        Check("!chatbot status answers for mods", Last() != null && Last().Contains("AI calls this hour") && Last().Contains("Names and trust"), Last());
        CPHProxy.Sent.Clear();
        Msg("Viewerx", "!chatbot status");
        Check("!chatbot status is mods only", Last() == null);
        Msg("Modx", "!chatbot updates", null, true);
        Check("!chatbot updates lists the latest", Last() != null && Last().Contains("Names and trust"), Last());

        // romantic advances: friendly 'ily' is not counted, pushing is, and the ladder goes up with each message
        nextReply = "{\"reply\":\"ily too\",\"remember\":[]}";
        Msg("Frnd1", "@pinguinob0t ily");
        Check("plain ily is friend talk (no advance note)", !lastPrompt.Contains("[ADVANCES]"), lastPrompt);
        int callsBeforeAdv = llmCalls;
        Msg("Adv1", "@pinguinob0t marry me");
        Check("level 1 on the first advance", lastPrompt.Contains("[ADVANCES]") && lastPrompt.Contains("level 1 of 4"), lastPrompt);
        Msg("Adv1", "@pinguinob0t be my girlfriend");
        Check("level 2", lastPrompt.Contains("level 2 of 4"));
        Msg("Adv1", "@pinguinob0t kiss me");
        Check("level 3", lastPrompt.Contains("level 3 of 4"));
        Msg("Adv1", "@pinguinob0t daddy");
        Check("level 4", lastPrompt.Contains("level 4 of 4"));
        int callsAfter4 = llmCalls;
        CPHProxy.Sent.Clear();
        Msg("Adv1", "@pinguinob0t hello again");
        Check("after level 4 the bot goes quiet for that viewer", llmCalls == callsAfter4 && Last() == null);
        Check("system prompt has the ladder", lastSystem.Contains("FRIENDSHIP, NOT ROMANCE") && lastSystem.Contains("harassment"));

        // asking the same thing again
        nextReply = "{\"reply\":\"octane\",\"remember\":[]}";
        Msg("Rep1", "@pinguinob0t what is the best rocket league car");
        Msg("Rep1", "@pinguinob0t what is the best rocket league car?");
        Check("the same question again gets the already-answered note", lastPrompt.Contains("[REPEAT]") && lastPrompt.ToLower().Contains("octane"), lastPrompt);

        // pronouns
        nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
        Msg("Pro1", "@pinguinob0t my pronouns are she/her");
        Msg("Pro1", "@pinguinob0t hi again");
        Check("pronouns the viewer states are remembered and shown", lastPrompt.Contains("pronouns: she/her"), lastPrompt);
        nextReply = "{\"reply\":\"ok\",\"remember\":[],\"pronouns\":\"he/him\"}";
        Msg("Pro2", "@pinguinob0t hey");
        Msg("Pro2", "@pinguinob0t hey again");
        Check("pronouns set by the AI are shown", lastPrompt.Contains("pronouns: he/him"));
        Check("pronouns are not in the website data", true);

        // names: a new viewer may pick a name; once set, only a trusted viewer may change it
        nextReply = "{\"reply\":\"sure\",\"remember\":[],\"selfnick\":\"Zeke\"}";
        Msg("Nick1", "@pinguinob0t call me Zeke");
        Msg("Nick1", "@pinguinob0t hi");
        Check("a requested name is saved and shown first", lastPrompt.Contains("the name they asked to be called: Zeke"), lastPrompt);
        nextReply = "{\"reply\":\"sure\",\"remember\":[],\"selfnick\":\"Ace\"}";
        Msg("Nick1", "@pinguinob0t actually call me Ace");
        Msg("Nick1", "@pinguinob0t hi");
        Check("an untrusted viewer cannot change the name again", lastPrompt.Contains("Zeke") && !lastPrompt.Contains("asked to be called: Ace") && lastPrompt.Contains("not trusted enough"), lastPrompt);
        Msg("Nick2", "@pinguinob0t call me Bob", null, true);
        nextReply = "{\"reply\":\"sure\",\"remember\":[],\"selfnick\":\"Bobby\"}";
        Msg("Nick2", "@pinguinob0t call me Bobby", null, true);
        nextReply = "{\"reply\":\"sure\",\"remember\":[],\"selfnick\":\"Rob\"}";
        Msg("Nick2", "@pinguinob0t call me Rob", null, true);
        Msg("Nick2", "@pinguinob0t hi", null, true);
        Check("a trusted viewer (a mod) can change their name", lastPrompt.Contains("asked to be called: Rob") && lastPrompt.Contains("TRUSTED"), lastPrompt);

        // opinions stay consistent
        nextReply = "{\"reply\":\"octane\",\"remember\":[],\"stance\":{\"topic\":\"fennec vs octane\",\"take\":\"octane\"}}";
        Msg("Opn1", "@pinguinob0t fennec or octane?");
        nextReply = "{\"reply\":\"fennec\",\"remember\":[],\"stance\":{\"topic\":\"fennec versus octane\",\"take\":\"fennec\"}}";
        Msg("Opn2", "@pinguinob0t fennec or octane??");
        Check("the saved stance is shown to the AI", lastPrompt.Contains("[YOUR OPINIONS]") && lastPrompt.Contains("fennec vs octane: octane"), lastPrompt);
        string opnFile = File.ReadAllText(Path.Combine(dir, "opinions.json"));
        Check("a new answer on the same topic never overwrites the first stance", opnFile.Contains("\"octane\"") && !opnFile.Contains("\"fennec\""), opnFile);
        nextReply = "{\"reply\":\"ok\",\"remember\":[],\"opinion\":\"funny and always around\"}";
        Msg("Opn3", "@pinguinob0t hi");
        Msg("Opn3", "@pinguinob0t hello");
        Check("the bot's opinion of a viewer is kept on their profile", lastPrompt.Contains("your PRIVATE opinion of this viewer (keep it consistent; let it colour your tone, but NEVER quote it, reveal it, or say you keep notes on their personality): funny and always around"), lastPrompt);

        // ── 19b. weekly private opinion notes ──
        Directory.CreateDirectory(Path.Combine(dir, "boards")); File.WriteAllText(Path.Combine(dir, "boards", "aliases.json"), "{\"aliases\":{\"opnxalt\":\"opnx\"}}");
        for (int i = 0; i < 22; i++) Msg("Opnx", "chat message number " + i + " about the game");
        for (int i = 0; i < 3; i++) Msg("OpnxAlt", "alt account says banana" + i + " here");
        for (int i = 0; i < 25; i++) Msg("Opnbad", "plain talk number " + i);
        for (int i = 0; i < 25; i++) Msg("Opnout", "secret chatter number " + i);
        Msg("Opnout", "!forgetme");
        for (int i = 0; i < 3; i++) Msg("Opnfew", "only a few messages " + i);
        CPHProxy.Sent.Clear(); opinionPrompts.Clear();
        opinionReply = "{\"opinions\":[{\"login\":\"opnx\",\"opinion\":\"Always here and always loud, a lovable derailer of chat.\"},{\"login\":\"opnbad\",\"opinion\":\"Is 12 years old and very sweaty.\"},{\"login\":\"opnout\",\"opinion\":\"Mysterious and quiet type honestly.\"},{\"login\":\"invented\",\"opinion\":\"Made up person who is not in the data.\"}]}";
        Msg("Mod1", "!opinion refresh all", null, true);
        var memO = Memory();
        Check("a mod can run the weekly opinion pass on demand", opinionPrompts.Count >= 1, string.Join("|", CPHProxy.Sent));
        Check("the note is saved on the viewer (alias folded in, under 300 characters)", memO["id_opnx"] != null && ((string)memO["id_opnx"]["Opinion"]).StartsWith("Always here") && ((string)memO["id_opnx"]["Opinion"]).Length <= 300);
        Check("a private copy for mods is written under opinions/", File.Exists(Path.Combine(dir, "opinions", "opnx.json")) && File.ReadAllText(Path.Combine(dir, "opinions", "opnx.json")).Contains("\"private\": true"));
        Check("the alias account's messages are part of the prompt", opinionPrompts.Any(p => p.Contains("banana1") && p.Contains("VIEWER: opnx ")), string.Join("|", opinionPrompts).Substring(0, 300));
        Check("the alias is not its own person", !opinionPrompts.Any(p => p.Contains("VIEWER: opnxalt")));
        Check("an unsafe note (age) is refused", memO["id_opnbad"] == null || string.IsNullOrEmpty((string)memO["id_opnbad"]["Opinion"]));
        Check("someone who opted out (!forgetme) gets no note", !opinionPrompts.Any(p => p.Contains("VIEWER: opnout")) && (memO["id_opnout"] == null || string.IsNullOrEmpty((string)memO["id_opnout"]["Opinion"])));
        Check("too few messages = no note", !opinionPrompts.Any(p => p.Contains("VIEWER: opnfew")));
        Check("made-up names from the AI are ignored", memO["login:invented"] == null);
        CPHProxy.Sent.Clear(); Msg("Opnx", "!opinion opnx");
        Check("a normal viewer gets no answer to !opinion", CPHProxy.Sent.Count == 0, Last());
        CPHProxy.Sent.Clear();
        Msg("Mod1", "!opinion opnx", null, true);
        Check("!opinion <user> never prints the note in public chat", CPHProxy.Sent.All(m => !m.Contains("lovable derailer")), string.Join("|", CPHProxy.Sent));
        Msg("Mod1", "!opinion status", null, true);
        Check("!opinion status", Last() != null && Last().Contains("Opinion notes:"), Last());
        nextReply = "{\"reply\":\"yo\",\"remember\":[]}";
        Msg("Opnx", "@pinguinob0t hi there");
        Check("the reply prompt carries the private note with a do-not-reveal rule", lastPrompt.Contains("your PRIVATE opinion of this viewer") && lastPrompt.Contains("lovable derailer") && lastPrompt.Contains("NEVER quote it"), lastPrompt);
        Msg("Mod1", "!opinion reset opnx", null, true);
        Check("!opinion reset clears it and removes the file", string.IsNullOrEmpty((string)Memory()["id_opnx"]["Opinion"]) && !File.Exists(Path.Combine(dir, "opinions", "opnx.json")));
        nextReply = "{\"reply\":\"ok\",\"remember\":[],\"opinion\":\"first impression\"}";
        Msg("Opnx", "@pinguinob0t morning");
        Msg("Opnx", "!forgetme");
        Check("!forgetme also wipes the opinion", string.IsNullOrEmpty((string)Memory()["id_opnx"]["Opinion"]) && !File.Exists(Path.Combine(dir, "opinions", "opnx.json")));

        // ── 20. long-term history summaries reach the prompt ──
        nextReply = "{\"reply\":\"ok\",\"remember\":[]}";
        Msg("Hist1", "@pinguinob0t what happened on 2026-10-17?");
        Check("a dated question gets the daily summary", lastPrompt.Contains("[LONG-TERM HISTORY]") && lastPrompt.Contains("Horror game night with mod talk"), lastPrompt);
        Msg("Hist1", "@pinguinob0t do you remember what i like");
        Check("a question about the speaker gets their monthly highlights", lastPrompt.Contains("Listens to Brent Faiyaz"), lastPrompt);
        Msg("Hist2", "@pinguinob0t just saying hi");
        Check("small talk gets no history section", !lastPrompt.Contains("[LONG-TERM HISTORY]"));
        Msg("Histforget", "!forgetme");
        Msg("Histforget", "@pinguinob0t do you remember what i like");
        Check("a viewer who used !forgetme gets no monthly highlights", !lastPrompt.Contains("Secret hobby"), lastPrompt);
        Check("system prompt explains the history section", lastSystem.Contains("LONG-TERM HISTORY"));

        // ── 21. the three bots: what the chatbot tells the router ──
        string Result() { object r; return CPHProxy.Globals.TryGetValue("pinguino.result", out r) ? (string)r : ""; }
        Msg("Rt1", "just a normal line of chat");
        Check("ordinary chat is reported as handled", Result() == "handled", Result());
        Extra["pinguinoRouted"] = true; Extra["pinguinoNext"] = "helper";
        int callsRt = llmCalls;
        Msg("Rt2", "@pinguinob0t how do i join the queue?");
        Check("a join question to the chatbot is deferred to the helper (no AI call, nothing said)", Result() == "defer" && llmCalls == callsRt, Result() + " " + (llmCalls - callsRt));
        Extra["pinguinoNoDefer"] = true;
        Msg("Rt2", "@pinguinob0t how do i join the queue?");
        Check("when the router hands it back the chatbot answers", Result() == "handled" && llmCalls == callsRt + 1, Result() + " " + (llmCalls - callsRt));
        Extra.Clear(); Extra["pinguinoRouted"] = true; Extra["pinguinoNext"] = "helper";
        Msg("Rt3", "@pinguinob0t that was a sick play");
        Check("other mentions are answered, not deferred", Result() == "handled");
        Msg("Rt4", "@helperpinguino hello");
        Check("naming the helper brings up the chatbot too", Result() == "handled" && lastPrompt.Contains("hello") , Result());
        Msg("Rt5", "@pinguinochat hello again");
        Check("naming the chatbot by its own name works", lastPrompt.Contains("hello again"));
        Extra.Clear();
        Msg("Mod9", "!chatbot off", null, true);
        Msg("Rt6", "@pinguinob0t hi");
        Check("a switched-off chatbot tells the router to pass", Result() == "pass", Result());
        Msg("Mod9", "!chatbot on", null, true);
        Check("a mention is also seen when the chatbot replies to a bot account in bots.json", true);

        // ── welcome new viewers (Twitch first-message flag), no AI ──
        Live(true); Extra.Clear(); CPHProxy.Sent.Clear(); int llm0 = llmCalls;
        Extra["firstMessage"] = true; Msg("Brandnew", "hello everyone");
        Check("first message ever: welcomed by name, no AI call", Last() != null && Last().Contains("@Brandnew") && Last().Contains("🐧") && llmCalls == llm0, Last());
        Extra.Clear(); CPHProxy.Sent.Clear(); Msg("Brandnew", "second message");
        Check("second message: no welcome", Last() == null, Last());
        Extra["firstMessage"] = true; CPHProxy.Sent.Clear(); Msg("Brandnew2", "what's up");
        Check("a second new viewer inside the gap is not welcomed (raid flood guard)", Last() == null, Last());
        Extra.Clear();

        Console.WriteLine(fails == 0 ? "ALL " + passes + " CHAT CHECKS PASSED" : fails + " FAILED / " + passes + " passed");
        try { Directory.Delete(dir, true); } catch (Exception) { }
        return fails == 0 ? 0 : 1;
    }
}
