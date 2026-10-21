using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;

// Checks for the router and the shared bot code (names, aliases, who goes first, fallbacks, who speaks).
public static class Harness
{
    static int fails, passes;
    static string dir;
    static void Check(string name, bool ok, string extra = "") { if (ok) passes++; else { fails++; Console.WriteLine("FAIL: " + name + (extra == "" ? "" : "  -> " + extra)); } }

    static void Reset()
    {
        CPHProxy.Sent.Clear(); CPHProxy.Runs.Clear(); CPHProxy.Args.Clear(); CPHProxy.Globals.Clear(); CPHProxy.Log.Clear();
        CPHProxy.Existing = new HashSet<string> { "PinguinoHelper", "PinguinoChat", "PinguinoBot" };
        CPHProxy.Behaviors.Clear();
    }
    static void Chat(string user, string text, string replyTo = null)
    {
        CPHProxy.Args.Clear(); CPHProxy.Runs.Clear();
        CPHProxy.Args["message"] = text; CPHProxy.Args["userName"] = user.ToLower(); CPHProxy.Args["user"] = user;
        if (replyTo != null) CPHProxy.Args["reply.userName"] = replyTo;
        new CPHInline().Execute();
    }
    static void ChatId(string id, string user, string text)
    {
        CPHProxy.Args.Clear(); CPHProxy.Runs.Clear();
        CPHProxy.Args["msgId"] = id; CPHProxy.Args["message"] = text; CPHProxy.Args["userName"] = user.ToLower(); CPHProxy.Args["user"] = user;
        new CPHInline().Execute();
    }
    static string Runs() { return string.Join(",", CPHProxy.Runs); }
    static void Registry(string json) { File.WriteAllText(Path.Combine(dir, "bots.json"), json); typeof(CPHInline).GetField("_pgChecked", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, DateTime.MinValue); typeof(CPHInline).GetField("_pgStamp", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, DateTime.MinValue); }
    static void HelperSpoke(string login) { new CPHInline().PgSetHelperContextPublic(login); }

    public static int Main()
    {
        dir = Path.Combine(Path.GetTempPath(), "bots_test_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        Environment.SetEnvironmentVariable("PINGUINO_DATA_DIR", dir);
        Reset();

        // ── defaults: bots.json is created, only the core has an account ──
        CPHProxy.Behaviors["PinguinoHelper"] = () => "pass"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "how is everyone");
        Check("bots.json is created on first use", File.Exists(Path.Combine(dir, "bots.json")));
        Check("ordinary chat: helper first, then the chatbot", Runs() == "PinguinoHelper,PinguinoChat", Runs());
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "nice play lol");
        Check("no key word: the helper stays out, only the chatbot is asked", Runs() == "PinguinoChat", Runs());
        foreach (string kw in new[] { "what is the minecraft ip", "ip?", "!discord", "how do I join" })
        { Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; Chat("viewer1", kw); Check("key word '" + kw + "': the helper goes first", Runs() == "PinguinoHelper", Runs()); }
        Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "@pinguinochat how do I join");
        Check("@ing the chatbot takes priority even with a key word", Runs() == "PinguinoChat", Runs());
        Reset(); Chat("viewer1", "how an older module that reports nothing");
        Check("a module that reports nothing counts as handled (nothing is answered twice)", Runs() == "PinguinoHelper", Runs());

        // ── who handles it ──
        Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "what's the lobby password");
        Check("the helper handled it: the chatbot is not asked", Runs() == "PinguinoHelper", Runs());
        Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "pass"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "how nice play lol");
        Check("the helper passes: the chatbot gets it", Runs() == "PinguinoHelper,PinguinoChat", Runs());
        Check("the router marks the message as routed", CPHProxy.Args.ContainsKey("pinguinoRouted"));
        Check("each module is told who is next", CPHProxy.Args.ContainsKey("pinguinoNext"));

        // ── mentions bring up the chatbot ──
        foreach (string alias in new[] { "@pinguinob0t", "@PinguinoB0t", "pinguinobot", "@pinguinochat", "@HelperPinguino" })
        {
            Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
            Chat("viewer1", alias + " hi there how are you");
            Check("@ing " + alias + " brings up " + (alias.ToLower().Contains("helper") ? "the helper" : "the chatbot") + " first", Runs() == (alias.ToLower().Contains("helper") ? "PinguinoHelper" : "PinguinoChat"), Runs());
        }
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "pass"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer1", "@pinguinob0t hey");
        Check("the chatbot passes: the helper takes over (chat falls into helper)", Runs() == "PinguinoChat,PinguinoHelper", Runs());
        // a helper-type question to the chatbot: it defers, the helper answers; if the helper passes, the chatbot gets it back
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "defer"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer1", "@pinguinob0t what's the code");
        Check("deferred to the helper, which handles it", Runs() == "PinguinoChat,PinguinoHelper", Runs());
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "defer"; CPHProxy.Behaviors["PinguinoHelper"] = () => "pass";
        Chat("viewer1", "@pinguinob0t what's the code");
        Check("nobody took it: the deferring chatbot is asked again and must answer", Runs() == "PinguinoChat,PinguinoHelper,PinguinoChat*", Runs());

        // ── what the helper said ──
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        HelperSpoke("viewer2");
        Chat("viewer2", "@pinguinob0t yes");
        Check("@ing a bot with a yes after the helper spoke: the helper first", Runs() == "PinguinoHelper", Runs());
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        HelperSpoke("viewer2");
        Chat("viewer2", "@pinguinob0t did you see that insane save in the last game, it was unreal");
        Check("@ing a bot about something unrelated, even right after the helper: the chatbot", Runs() == "PinguinoChat", Runs());
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        HelperSpoke("viewer2");
        Chat("viewer2", "ok and then");
        Check("a short follow-up without a mention goes to the helper", Runs() == "PinguinoHelper", Runs());
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer3", "how and then");
        Check("without an open helper conversation the helper still goes first for ordinary chat", Runs() == "PinguinoHelper", Runs());

        // ── commands ──
        Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "pass"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "!join");
        Check("!commands: helper (mistyped !register), then the chatbot records them", Runs() == "PinguinoHelper,PinguinoChat", Runs());

        // ── fallbacks when a bot is missing or switched off ──
        Reset(); CPHProxy.Existing.Remove("PinguinoHelper"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        Chat("viewer1", "what's the code");
        Check("helper action missing in Streamer.bot: helper falls into chat", Runs() == "PinguinoChat" && CPHProxy.Log.Any(l => l.Contains("no action")), Runs());
        Reset(); CPHProxy.Existing.Remove("PinguinoChat"); CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer1", "@pinguinob0t hi");
        Check("chat action missing: chat falls into helper", Runs() == "PinguinoHelper", Runs());
        Reset(); CPHProxy.Existing.Clear();
        Chat("viewer1", "@pinguinob0t hi");
        Check("nothing installed: nothing runs, nothing crashes", Runs() == "" && !CPHProxy.Log.Any(l => l.StartsWith("ERR")), string.Join("|", CPHProxy.Log));

        // ── renaming: only bots.json changes ──
        Registry("{\"Bots\":{\"core\":{\"Title\":\"Pingu\",\"Account\":\"pingu_bot\",\"Aliases\":[\"pingu\"]},\"helper\":{\"Title\":\"Penny\",\"Account\":\"penny_helps\",\"Aliases\":[\"penny\"],\"Action\":\"Penny\"},\"chat\":{\"Title\":\"Yappy\",\"Account\":\"yappy_bot\",\"Aliases\":[\"yappy\"]}}}");
        Reset(); CPHProxy.Existing.Add("Penny"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["Penny"] = () => "handled";
        Chat("viewer1", "hey @yappy you there");
        Check("a renamed bot answers to its new name", Runs() == "PinguinoChat", Runs());
        Reset(); CPHProxy.Existing.Add("Penny"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["Penny"] = () => "handled";
        Chat("viewer1", "how world");
        Check("the helper action name comes from bots.json", Runs() == "Penny", Runs());
        Reset(); CPHProxy.Existing.Add("Penny"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["Penny"] = () => "handled";
        Chat("viewer1", "@pinguinob0t how hi");
        Check("the old name is just a word now (no mention)", Runs() == "Penny", Runs());
        Reset(); CPHProxy.Existing.Add("Penny"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        CPHProxy.Behaviors["Penny"] = () => "pass";
        Chat("pingu_bot", "@yappy hi");
        Check("a message from one of our own accounts never starts anything", Runs() == "");
        Reset(); CPHProxy.Existing.Add("Penny"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["Penny"] = () => "handled";
        Chat("viewer1", "yes please", "penny_helps");
        Check("a reply to the helper's account goes to the helper", Runs() == "Penny", Runs());
        Reset(); CPHProxy.Existing.Add("Penny"); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["Penny"] = () => "handled";
        Chat("viewer1", "thanks", "yappy_bot");
        Check("a reply to the chatbot's account goes to the chatbot", Runs() == "PinguinoChat", Runs());

        // ── switched off in bots.json ──
        Registry("{\"Bots\":{\"helper\":{\"Enabled\":false}}}");
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer1", "what's the code");
        Check("a switched-off helper is skipped", Runs() == "PinguinoChat", Runs());
        Registry("{\"Bots\":{\"chat\":{\"Enabled\":false}}}");
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer1", "@pinguinob0t hi");
        Check("a switched-off chatbot is skipped: the helper takes it", Runs() == "PinguinoHelper", Runs());

        // ── who speaks (PgSay) ──
        Registry("{}");   // defaults: only the core has an account
        Reset();
        var c = new CPHInline();
        c.SayPublic("helper", "hello"); c.SayPublic("chat", "hi"); c.SayPublic("core", "queue open");
        Check("with one account everyone speaks through it, text unchanged", CPHProxy.Sent.SequenceEqual(new[] { "hello", "hi", "queue open" }), string.Join("|", CPHProxy.Sent));
        Check("speaker chains: helper -> chat -> core, chat -> helper -> core, core -> chat -> helper", c.SpeakerPublic("helper") == "core" && c.SpeakerPublic("chat") == "core" && c.SpeakerPublic("core") == "core");
        Registry("{\"Bots\":{\"chat\":{\"Account\":\"chat_acc\"}}}");
        Check("a bot with its own account speaks for itself", c.SpeakerPublic("chat") == "chat");
        Check("a bot without its own login is covered by the main account (PinguinoB0t) first", c.SpeakerPublic("helper") == "core");
        Registry("{\"Bots\":{\"helper\":{\"Account\":\"h_acc\"}}}");
        Check("the main account covers the chatbot too", c.SpeakerPublic("chat") == "core");
        Registry("{\"Bots\":{\"core\":{\"Account\":\"\"},\"helper\":{\"Account\":\"h_acc\"}}}");
        Check("the core falls into the chatbot, then the helper", c.SpeakerPublic("core") == "helper");
        Registry("{\"TagWhenShared\":true,\"Bots\":{\"chat\":{\"Title\":\"Yappy\"}}}");
        Reset(); c.SayPublic("chat", "hi"); c.SayPublic("core", "ok");
        Check("with TagWhenShared a borrowed voice is tagged with the bot's name", CPHProxy.Sent.SequenceEqual(new[] { "[Yappy] hi", "ok" }), string.Join("|", CPHProxy.Sent));

        // ── never the same line twice ──
        Registry("{}"); Reset();
        c.SayPublic("helper", "Queue is open!"); c.SayPublic("chat", "queue  is OPEN! "); c.SayPublic("core", "Queue is open!");
        Check("the same line from any bot inside 30 s is said once (case/spacing ignored)", CPHProxy.Sent.Count == 1 && CPHProxy.Sent[0] == "Queue is open!", string.Join("|", CPHProxy.Sent));
        c.SayPublic("core", "Queue is closed!");
        Check("a different line still goes out", CPHProxy.Sent.Count == 2 && CPHProxy.Sent[1] == "Queue is closed!", string.Join("|", CPHProxy.Sent));
        CPHProxy.Globals["pinguino.said.recent"] = "1|queue is open!";   // old record: 30 s long gone
        c.SayPublic("core", "Queue is open!");
        Check("after the window the line may be said again", CPHProxy.Sent.Count == 3, string.Join("|", CPHProxy.Sent));

        // ── a bot's own account via Twitch's API (fake HTTP) ──
        Registry("{\"Bots\":{\"chat\":{\"Account\":\"chat_acc\",\"Sender\":\"helix\"}}}");
        File.WriteAllText(Path.Combine(dir, "bots_secrets.json"), "{\"chat\":{\"ClientId\":\"cid\",\"UserToken\":\"tok\",\"SenderId\":\"123\",\"BroadcasterId\":\"456\"}}");
        var posts = new List<string>();
        typeof(CPHInline).GetField("_pgTestHttp", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, (Func<string, string, string, string>)((url, auth, body) => { posts.Add(url + " " + auth + " " + body); return "{}"; }));
        Reset(); c.SayPublic("chat", "from my own account");
        Check("a helix bot posts through the Twitch API with its own token", posts.Count == 1 && posts[0].Contains("helix/chat/messages") && posts[0].Contains("\"sender_id\":\"123\"") && posts[0].Contains("from my own account") && CPHProxy.Sent.Count == 0, string.Join("|", posts));
        File.Delete(Path.Combine(dir, "bots_secrets.json"));
        Reset(); c.SayPublic("chat", "no token");
        Check("without a token it falls back to the bot account", CPHProxy.Sent.Count == 1 && CPHProxy.Sent[0] == "no token", string.Join("|", CPHProxy.Sent));

        // ── names: every variant reaches the right bot; the main account never takes a chat line ──
        Registry("{}");
        foreach (var nm in new[] { "pinguino", "hey pinguino what's up", "@chattypinguino hi", "chatty pinguino hi", "pinguinochatty hi", "@PinguinoB0t hi", "pinguino bot hi", "@pinguinochat hi" })
        { Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; Chat("viewer1", nm); Check("'" + nm + "' goes to the chatbot", Runs() == "PinguinoChat", Runs()); }
        foreach (var nm in new[] { "@pinguinohelper hi", "pinguino helper hi", "helper pinguino hi", "@HelperPinguino hi", "pinguinhelper hi", "hey pinguino_helper" })
        { Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; Chat("viewer1", nm); Check("'" + nm + "' goes to the helper", Runs() == "PinguinoHelper", Runs()); }
        foreach (var nm in new[] { "PINGUINO!", "pinguinos", "penguins are great", "hey penguinos", "pinguin", "pingino hi" })
        { Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; Chat("viewer1", nm); Check("'" + nm + "' calls a bot", Runs() == "PinguinoChat", Runs()); }
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; Chat("viewer1", "hello there everyone"); string ctl = Runs();
        foreach (var nm in new[] { "penguin", "peng is late", "peg", "pengiun", "pegg", "is peng here", "penguin is late again" })
        { Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; CPHProxy.Behaviors["PinguinoHelper"] = () => "handled"; Chat("viewer1", nm); Check("'" + nm + "' means Ivan: not addressed to the helper or the main bot (same as any unaddressed line)", Runs() == ctl, Runs()); }
        Reset(); CPHProxy.Behaviors["PinguinoChat"] = () => "handled"; Chat("chattypinguino", "hello"); Chat("pinguinohelper", "hello");
        Check("the new bot accounts' own lines start nothing", Runs() == "", Runs());
        // its own login first, the main account only when that fails
        Registry("{\"Bots\":{\"chat\":{\"Account\":\"chattypinguino\",\"Sender\":\"helix\"},\"core\":{\"Account\":\"pinguinob0t\",\"Sender\":\"helix\"}}}");
        File.WriteAllText(Path.Combine(dir, "bots_secrets.json"), "{\"chat\":{\"ClientId\":\"c\",\"UserToken\":\"t1\",\"SenderId\":\"11\",\"BroadcasterId\":\"9\"},\"core\":{\"ClientId\":\"c\",\"UserToken\":\"t2\",\"SenderId\":\"22\",\"BroadcasterId\":\"9\"}}");
        var posts2 = new List<string>(); bool failChat = false;
        typeof(CPHInline).GetField("_pgTestHttp", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, (Func<string, string, string, string>)((url, auth, body) => { posts2.Add(body); if (failChat && body.Contains("\"sender_id\":\"11\"")) throw new Exception("401"); return "{}"; }));
        Reset(); c.SayPublic("chat", "hi there");
        Check("the chatbot speaks from its own login", posts2.Count == 1 && posts2[0].Contains("\"sender_id\":\"11\""), string.Join("|", posts2));
        posts2.Clear(); failChat = true; Reset(); c.SayPublic("chat", "hi again");
        Check("when its own login fails, PinguinoB0t speaks instead", posts2.Count == 2 && posts2[1].Contains("\"sender_id\":\"22\"") && posts2[1].Contains("hi again"), string.Join("|", posts2));
        typeof(CPHInline).GetField("_pgTestHttp", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, null);
        File.Delete(Path.Combine(dir, "bots_secrets.json")); Registry("{}");

        // ── correlation: per-message result, msgId dedupe, routing.log ──
        string rlog = Path.Combine(dir, "routing.log");
        try { File.Delete(rlog); } catch (Exception) { }
        Registry("{}");
        Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "pass"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        ChatId("m-1", "viewer1", "how nice play lol");
        Check("the router tags the message with its id", (string)CPHProxy.Args["pinguinoMsgId"] == "m-1");
        Check("results are stored per message and removed after reading", !CPHProxy.Globals.Keys.Any(k => k.StartsWith("pinguino.result")), string.Join(",", CPHProxy.Globals.Keys));
        Check("a normal message still routes helper then chat", Runs() == "PinguinoHelper,PinguinoChat", Runs());
        // a stale answer left by another message must not leak into this one
        Reset(); CPHProxy.Globals["pinguino.result.m-other"] = "handled"; CPHProxy.Globals["pinguino.result"] = "handled";
        CPHProxy.Behaviors["PinguinoHelper"] = () => "pass"; CPHProxy.Behaviors["PinguinoChat"] = () => "handled";
        ChatId("m-2", "viewer2", "how another line");
        Check("another message's stored result is ignored", Runs() == "PinguinoHelper,PinguinoChat", Runs());
        Check("and left untouched", (string)CPHProxy.Globals["pinguino.result.m-other"] == "handled");
        // replay
        ChatId("m-2", "viewer2", "how another line");
        Check("a replayed msgId is ignored (nobody answers twice)", Runs() == "", Runs());
        ChatId("m-3", "viewer2", "how another line");
        Check("same text with a new msgId is a new message", Runs() == "PinguinoHelper,PinguinoChat", Runs());
        // no msgId from Twitch: same user + text in the same instant is a replay
        Reset(); CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        Chat("viewer3", "how no id here");
        Check("without a msgId a fallback id is made", CPHProxy.Args.ContainsKey("pinguinoMsgId") && (string)CPHProxy.Args["pinguinoMsgId"] != "");
        string first = Runs();
        CPHProxy.Runs.Clear(); CPHProxy.Args["message"] = "how no id here"; CPHProxy.Args["userName"] = "viewer3"; CPHProxy.Args["user"] = "viewer3"; new CPHInline().Execute();
        Check("an immediate identical line without msgId is dropped as a replay", first == "PinguinoHelper" && Runs() == "", first + " / " + Runs());
        // log
        string log = File.Exists(rlog) ? File.ReadAllText(rlog) : "";
        Check("routing.log is written", log != "");
        Check("routing.log names msgId, role and outcome", log.Contains("	m-1	chat	handled	") && log.Contains("	m-1	helper	pass	"), log);
        Check("routing.log records the replay", log.Contains("	m-2	-	duplicate	"), log);
        // dedupe window expires
        Reset(); CPHProxy.Globals["pinguino.seen"] = "old-id:" + (DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 120);
        CPHProxy.Behaviors["PinguinoHelper"] = () => "handled";
        ChatId("old-id", "viewer4", "how hi");
        Check("an id older than the window is accepted again", Runs() == "PinguinoHelper", Runs());
        Check("the seen list stays short", ((string)CPHProxy.Globals["pinguino.seen"]).Split(';').Length <= 50);
        Console.WriteLine(fails == 0 ? "ALL " + passes + " BOT ROUTING CHECKS PASSED" : fails + " FAILED / " + passes + " passed");
        try { Directory.Delete(dir, true); } catch (Exception) { }
        return fails == 0 ? 0 : 1;
    }
}
