using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

// ══════════════════════════════════════════════════════════════════════════
//  PinguinoHelper: the HELPER part of PinguinoBot (see HelperPinguino\HELPER_DESIGN.md).
//  Reads normal chat so viewers never need to know a command. Answers lobby / join / register questions,
//  and registers / joins / leaves / looks up the queue for the viewer after they say yes.
//  Streamer.bot: new action "PinguinoHelper", trigger Twitch > Chat > Message (no command filter), Execute C# Code.
//  Remove the chat trigger from "PinguinoChat": the helper hands every message it did not handle on to it.
//  Config: %AppData%\BVQ\helper_settings.json (created on first run). READS (never writes): players.json, live_state.json,
//  settings.json and chat_settings.json (AI key). Talks to the game manager only through CPH.RunAction.
//  C# 7.3.
// ══════════════════════════════════════════════════════════════════════════
public class CPHInline
{

    // <<PINGUINO-SHARED-BEGIN>>
    // ══════════════════════════════════════════════════════════════════════════
    //  THE THREE BOTS (shared code). Source of truth: D:\PinguinoSuite\Shared\PinguinoBots.cs.txt; the copy inside each Streamer.bot action is written by
    //  `node Shared\sync-shared.mjs`, so do not edit it in the .cs files. Design: Shared\BOTS_DESIGN.md.
    //    HELPER (HelperPinguino): practical help, answers lobby / join / register questions, does errands for the viewer.
    //    CHAT   (PinguinoChat):   talks to viewers, memory, personality.
    //    CORE   (PinguinoB0t):    game manager + OBS control (queue, teams, matches, scenes).
    //  Names, Twitch accounts, aliases and Streamer.bot action names live in %AppData%\BVQ\bots.json, NOT in the code, so a bot is renamed by editing that file.
    //  A bot that has no Twitch account yet speaks through the next bot of its fallback chain (helper -> chat -> core, chat -> helper -> core, core -> chat -> helper).
    // ══════════════════════════════════════════════════════════════════════════
    class PgBot
    {
        public string Title { get; set; } = "";               // the name viewers see for this bot
        public string Account { get; set; } = "";             // its Twitch login; "" = this bot has no account yet (it speaks through its fallback)
        public List<string> Aliases { get; set; } = new List<string>();   // names viewers call it by (@name or the plain word)
        public string Action { get; set; } = "";              // the Streamer.bot action that runs it
        public bool Enabled { get; set; } = true;
        public string Sender { get; set; } = "streamerbot";   // streamerbot = the Streamer.bot bot account | helix = this bot's own Twitch token (bots_secrets.json) | none
        public string Tag { get; set; } = "";                 // text put in front when this bot has to speak through another bot's account ("" = [Title])
    }

    class PgRegistry
    {
        public Dictionary<string, PgBot> Bots { get; set; } = new Dictionary<string, PgBot>();
        public Dictionary<string, List<string>> Fallback { get; set; } = new Dictionary<string, List<string>>();   // role -> who takes over, in order
        public bool TagWhenShared { get; set; } = false;      // put [Title] in front of a message a bot speaks through another bot's account
        public int HelperContextSeconds { get; set; } = 120;  // how long a viewer stays "in conversation" with the helper after it spoke to them
    }

    static readonly string[] PgRoleList = { "helper", "chat", "core" };
    static PgRegistry _pgReg;
    static DateTime _pgChecked = DateTime.MinValue, _pgStamp = DateTime.MinValue;
    static Func<string, string, string, string> _pgTestHttp;   // tests only: fake POST (url, auth header, body) -> response

    static string PgEnvDir() { return Environment.GetEnvironmentVariable("PINGUINO_DATA_DIR") ?? Environment.GetEnvironmentVariable("BVQ_DATA_DIR"); }  // BVQ_DATA_DIR = deprecated alias
    static string PgDirPath() { return PgEnvDir() ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "BVQ"); }
    static long PgNow() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

    static PgRegistry PgDefault()
    {
        var r = new PgRegistry();
        r.Bots["core"] = new PgBot { Title = "PinguinoB0t", Account = "pinguinob0t", Action = "PinguinoBot", Aliases = new List<string> { "pinguinob0t", "pinguinb0t", "pinguinobot", "pinguinbot", "pinguino b0t", "pinguino bot", "pinguin b0t", "pinguin bot", "penguinob0t", "penguinb0t", "penguinobot", "penguinbot", "pinguino_bot", "pinguino_b0t" } };
        r.Bots["chat"] = new PgBot { Title = "ChattyPinguino", Account = "chattypinguino", Sender = "none", Action = "PinguinoChat", Aliases = new List<string> { "chattypinguino", "pinguinochatty", "chattypinguin", "pinguinchatty", "chattypenguino", "chattypenguin", "penguinchatty", "chatty pinguino", "pinguino chatty", "chatty penguin", "chatty_pinguino", "pinguino_chatty", "pinguinochat", "pinguinchat", "penguinochat", "penguinchat", "chatpinguino", "chatpinguin", "pinguino chat", "chat pinguino", "pinguinochatbot", "pinguino" } };
        r.Bots["helper"] = new PgBot { Title = "PinguinoHelper", Account = "pinguinohelper", Sender = "none", Action = "PinguinoHelper", Aliases = new List<string> { "pinguinohelper", "pinguinhelper", "penguinohelper", "penguinhelper", "helperpinguino", "helperpinguin", "helperpenguino", "helperpenguin", "pinguino helper", "helper pinguino", "pinguin helper", "penguin helper", "pinguino_helper", "helper_pinguino", "pinguinohelp" } };
        r.Fallback["helper"] = new List<string> { "chat", "core" };
        r.Fallback["chat"] = new List<string> { "helper", "core" };
        r.Fallback["core"] = new List<string> { "chat", "helper" };
        return r;
    }

    // Loads bots.json (created with the defaults on first use, re-read when it changes, checked every 10 s). Missing bots / chains are filled from the defaults.
    PgRegistry PgReg()
    {
        if (_pgReg != null && (DateTime.UtcNow - _pgChecked).TotalSeconds < 10) return _pgReg;
        _pgChecked = DateTime.UtcNow;
        string p = Path.Combine(PgDirPath(), "bots.json");
        try
        {
            Directory.CreateDirectory(PgDirPath());
            if (!File.Exists(p)) File.WriteAllText(p, Newtonsoft.Json.JsonConvert.SerializeObject(PgDefault(), Newtonsoft.Json.Formatting.Indented));
            DateTime stamp = File.GetLastWriteTimeUtc(p);
            if (_pgReg == null || stamp != _pgStamp)
            {
                var r = Newtonsoft.Json.JsonConvert.DeserializeObject<PgRegistry>(File.ReadAllText(p));
                var d = PgDefault();
                if (r == null) r = d;
                foreach (string role in PgRoleList)
                {
                    PgBot b; if (!r.Bots.TryGetValue(role, out b) || b == null) { r.Bots[role] = d.Bots[role]; continue; }
                    if (b.Aliases == null) b.Aliases = new List<string>();
                    if (b.Title == null) b.Title = d.Bots[role].Title;
                    if (b.Account == null) b.Account = "";
                    if (string.IsNullOrEmpty(b.Action)) b.Action = d.Bots[role].Action;
                    if (!r.Fallback.ContainsKey(role) || r.Fallback[role] == null) r.Fallback[role] = d.Fallback[role];
                }
                _pgReg = r; _pgStamp = stamp;
            }
        }
        catch (Exception ex) { if (_pgReg == null) _pgReg = PgDefault(); CPH.LogWarn("[Bots] bots.json problem: " + ex.Message); }
        return _pgReg;
    }

    PgBot PgBotOf(string role) { PgBot b; return PgReg().Bots.TryGetValue(role ?? "", out b) ? b : null; }
    string PgTitle(string role) { var b = PgBotOf(role); return b == null || string.IsNullOrEmpty(b.Title) ? role : b.Title; }
    string PgAccountOf(string role) { var b = PgBotOf(role); return b == null ? "" : (b.Account ?? "").Trim().ToLower(); }

    // the role whose Twitch account this is ("" = nobody's)
    string PgRoleOfAccount(string login)
    {
        login = (login ?? "").Trim().ToLower().TrimStart('@');
        if (login == "") return "";
        foreach (string role in PgRoleList) if (PgAccountOf(role) == login) return role;
        return "";
    }
    bool PgIsBotAccount(string login) { return PgRoleOfAccount(login) != ""; }

    // role -> in order: itself, then who takes over when it is not there (only the three roles, no duplicates)
    List<string> PgChain(string role)
    {
        var list = new List<string> { role };
        List<string> fb; if (PgReg().Fallback.TryGetValue(role, out fb) && fb != null) foreach (string r in fb) if (PgRoleList.Contains(r) && !list.Contains(r)) list.Add(r);
        foreach (string r in PgRoleList) if (!list.Contains(r)) list.Add(r);
        return list;
    }

    // can this bot speak under its own name? (enabled, has an account, and a way to send as that account)
    bool PgHasVoice(string role)
    {
        var b = PgBotOf(role);
        return b != null && b.Enabled && !string.IsNullOrEmpty((b.Account ?? "").Trim()) && !string.Equals(b.Sender, "none", StringComparison.OrdinalIgnoreCase);
    }

    // who really speaks for this bot: itself if it has a voice, otherwise the first bot of its chain that has one
    string PgSpeaker(string role)
    {
        if (PgHasVoice(role)) return role;
        if (role != "core" && PgHasVoice("core")) return "core";               // the main account only speaks for a bot whose own login is missing
        foreach (string r in PgChain(role)) if (PgHasVoice(r)) return r;
        return role;
    }

    // the bot a message is addressed to: the LONGEST name found wins ("pinguino helper" beats the plain word "pinguino"), ties go to the earliest
    string PgBestMention(string text, bool plainWords)
    {
        string t = (text ?? "").ToLower(), best = ""; int bestLen = 0, bestPos = int.MaxValue;
        foreach (string role in PgRoleList)
        {
            var b = PgBotOf(role); if (b == null) continue;
            var names = new List<string>(b.Aliases ?? new List<string>());
            if (!string.IsNullOrEmpty(b.Account)) names.Add(b.Account);
            foreach (string n in names)
            {
                if (string.IsNullOrWhiteSpace(n)) continue;
                string e = System.Text.RegularExpressions.Regex.Escape(n.Trim().ToLower().TrimStart('@'));
                var m = System.Text.RegularExpressions.Regex.Match(t, "@" + e + "(?![a-z0-9_])");
                if (!m.Success && plainWords) m = System.Text.RegularExpressions.Regex.Match(t, "(?<![a-z0-9_])" + e + "(?![a-z0-9_])");
                if (!m.Success) continue;
                int len = m.Value.TrimStart('@').Length;
                if (len > bestLen || (len == bestLen && m.Index < bestPos)) { best = role; bestLen = len; bestPos = m.Index; }
            }
        }
        return best;
    }

    // the roles named in a message: "@HelperPinguino", or the plain word when plainWords is true
    List<string> PgMentionedRoles(string text, bool plainWords)
    {
        var found = new List<string>();
        string t = (text ?? "").ToLower();
        foreach (string role in PgRoleList)
        {
            var b = PgBotOf(role); if (b == null) continue;
            var names = new List<string>(b.Aliases ?? new List<string>());
            if (!string.IsNullOrEmpty(b.Account)) names.Add(b.Account);
            foreach (string n in names)
            {
                if (string.IsNullOrWhiteSpace(n)) continue;
                string e = System.Text.RegularExpressions.Regex.Escape(n.Trim().ToLower().TrimStart('@'));
                if (System.Text.RegularExpressions.Regex.IsMatch(t, "@" + e + "(?![a-z0-9_])") ||
                    (plainWords && System.Text.RegularExpressions.Regex.IsMatch(t, "(?<![a-z0-9_])" + e + "(?![a-z0-9_])"))) { if (!found.Contains(role)) found.Add(role); break; }
            }
        }
        return found;
    }

    // Say something AS a bot. If that bot has no voice yet, its fallback speaks (with [Title] in front when TagWhenShared is on).
    void PgSay(string role, string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        var reg = PgReg();
        string speaker = PgSpeaker(role);
        string msg = text;
        if (speaker != role && reg.TagWhenShared)
        {
            var b = PgBotOf(role);
            string tag = b != null && !string.IsNullOrEmpty(b.Tag) ? b.Tag : "[" + PgTitle(role) + "]";
            msg = tag + " " + text;
        }
        // its own login first; if that fails, the main account (PinguinoB0t), then the rest of the chain
        var tryList = new List<string> { speaker };
        if (!tryList.Contains("core")) tryList.Add("core");
        foreach (string r in PgChain(role)) if (!tryList.Contains(r)) tryList.Add(r);
        foreach (string r in tryList)
        {
            var sp = PgBotOf(r);
            if (sp != null && PgHasVoice(r) && string.Equals(sp.Sender, "helix", StringComparison.OrdinalIgnoreCase) && PgHelixSend(r, msg)) return;
        }
        CPH.SendMessage(msg, true);   // the Streamer.bot bot account
    }

    // Sends as one bot's OWN Twitch account with Twitch's "send chat message" API. Needs bots_secrets.json: { "<role>": { "ClientId", "UserToken", "SenderId", "BroadcasterId" } }
    // (a user access token with user:write:chat for that bot account). Returns false when anything is missing or fails, then the Streamer.bot account is used.
    bool PgHelixSend(string role, string text)
    {
        try
        {
            string p = Path.Combine(PgDirPath(), "bots_secrets.json");
            if (!File.Exists(p)) return false;
            var s = Newtonsoft.Json.Linq.JObject.Parse(File.ReadAllText(p))[role] as Newtonsoft.Json.Linq.JObject;
            if (s == null) return false;
            string cid = (string)s["ClientId"] ?? "", tok = (string)s["UserToken"] ?? "", sid = (string)s["SenderId"] ?? "", bid = (string)s["BroadcasterId"] ?? "";
            if (tok == "") tok = CPH.GetGlobalVar<string>("pinguino.secret.token." + role, false) ?? "";   // the key vault (Host), when bots_secrets.json no longer holds it
            if (cid == "" || tok == "" || sid == "" || bid == "") return false;
            string body = new Newtonsoft.Json.Linq.JObject { ["broadcaster_id"] = bid, ["sender_id"] = sid, ["message"] = text }.ToString(Newtonsoft.Json.Formatting.None);
            if (_pgTestHttp != null) return _pgTestHttp("https://api.twitch.tv/helix/chat/messages", "Bearer " + tok + "|" + cid, body) != null;
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create("https://api.twitch.tv/helix/chat/messages");
            req.Method = "POST"; req.ContentType = "application/json"; req.Timeout = 8000;
            req.Headers["Authorization"] = "Bearer " + tok; req.Headers["Client-Id"] = cid;
            byte[] bytes = System.Text.Encoding.UTF8.GetBytes(body); req.ContentLength = bytes.Length;
            using (var st = req.GetRequestStream()) st.Write(bytes, 0, bytes.Length);
            using (var resp = (System.Net.HttpWebResponse)req.GetResponse()) return (int)resp.StatusCode >= 200 && (int)resp.StatusCode < 300;
        }
        catch (Exception ex) { CPH.LogWarn("[Bots] sending as " + role + " failed, using the bot account: " + ex.Message); return false; }
    }

    // ── what a module tells the router: "handled" (done, or deliberately silent) or "pass" (not mine / can't: next one please) ──
    // The result is stored per chat message ("pinguino.result.<msgId>", the id comes from the router's argument pinguinoMsgId), so two messages
    // being handled at the same time can never read each other's answer. Without that argument (a module run by hand) the old single key is used.
    string PgResultKey() { object o; string id = (CPH.TryGetArg("pinguinoMsgId", out o) && o != null) ? Convert.ToString(o) : ""; return id == "" ? "pinguino.result" : "pinguino.result." + id; }
    void PgSetResult(string result) { try { CPH.SetGlobalVar(PgResultKey(), result, false); } catch (Exception) { } }
    string PgGetResult() { try { return CPH.GetGlobalVar<string>(PgResultKey(), false) ?? ""; } catch (Exception) { return ""; } }
    void PgDropResult() { try { CPH.UnsetGlobalVar(PgResultKey(), false); } catch (Exception) { } }

    // ── the helper's open conversation with a viewer (set when the helper speaks to them) ──
    void PgSetHelperContext(string login)
    {
        if (string.IsNullOrEmpty(login)) return;
        try { CPH.SetGlobalVar("pinguino.helperctx." + login.ToLower(), (PgNow() + Math.Max(10, PgReg().HelperContextSeconds)).ToString(), false); } catch (Exception) { }
    }
    bool PgHelperContext(string login)
    {
        if (string.IsNullOrEmpty(login)) return false;
        try { long until; return long.TryParse(CPH.GetGlobalVar<string>("pinguino.helperctx." + login.ToLower(), false), out until) && until > PgNow(); } catch (Exception) { return false; }
    }

    // roles that come after this one in the router's order (the router sets the argument "pinguinoNext"); a module may only pass when someone is next
    bool PgNextHas(string role)
    {
        object o; if (!CPH.TryGetArg("pinguinoNext", out o) || o == null) return false;
        return ("," + Convert.ToString(o) + ",").Contains("," + role + ",");
    }
    bool PgRouted() { object o; if (!CPH.TryGetArg("pinguinoRouted", out o) || o == null) return false; bool b; return o is bool ? (bool)o : (bool.TryParse(Convert.ToString(o), out b) && b); }

    // does the Streamer.bot action exist? (called by name so an older Streamer.bot without it still compiles; unknown = assume yes)
    bool PgActionExists(string name)
    {
        if (string.IsNullOrWhiteSpace(name)) return false;
        try
        {
            var m = CPH.GetType().GetMethod("ActionExists", new[] { typeof(string) });
            if (m == null) return true;
            object r = m.Invoke(CPH, new object[] { name });
            return !(r is bool) || (bool)r;
        }
        catch (Exception) { return true; }
    }

    // lobby / join / register / queue questions and requests: the helper's kind of message (the same patterns the helper itself uses)
    static readonly System.Text.RegularExpressions.Regex[] PgHelperTopics =
    {
        new System.Text.RegularExpressions.Regex(@"\b(what'?s|whats|what\s+is|wats|gimme|give\s+me|drop|send|tell\s+me|share|need|where'?s|wheres)\b.{0,25}\b(code|pass(word|wd|w)?|pw|lobby|private\s*match|custom\s*(game|match|lobby)?|pm)\b|\b(name\s*(and|&|\+|n|/)\s*(pass|pw|password))\b|\b(lobby|private\s*match|custom)\s*(name|code|pass(word)?|pw)\b|\bpass(word)?\s*(for\s+)?(the\s+)?(lobby|game|match|custom|private)|^\s*(code|pass(word)?|pw|lobby)\s*\??\s*$", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"\bhow\s+(do|can|to|does|would|should)\b.{0,20}\b(join|play|get\s+in|enter|queue|participate|get\s+into|be\s+in)\b|\b(can|could)\s+(i|we|someone|anyone)\s+(play|join)\b|\b(wanna|want\s+to|like\s+to|trying\s+to)\s+(play|join)\b.{0,25}\b(game|customs?|match|lobby|queue|you|stream|viewer|with)\b|\bhow\s+(does|do)\s+(this|it|the\s+(queue|game|lobby))\s+work\b|\bhow\s+(to|do\s+i)\s+(get\s+)?(in\s+)?the\s+(queue|game|lobby)\b|\bviewer\s+games?\b.{0,15}\bhow\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"\bhow\b.{0,25}\b(register|sign\s*up|link)\b|\bwhat('?s|\s+is)\b.{0,12}\bregister\b|\b(register|registration)\b.{0,20}\b(work|how|help|not\s+working|doesn'?t|wont|won'?t|fail|error)|\bhow\b.{0,15}\b(epic|link\s+my)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"^\s*(please\s+|pls\s+|plz\s+)?(register|sign)\s+me\s+(up\s+)?(as|with|under|using)\s+(?<n>.+?)\s*[.!?]*\s*$|\bmy\s+(epic|epic\s+games|epic\s+name|epic\s+id|game\s*id|rl\s+name|username\s+is)\s*(name\s*|id\s*)?(is|=|:)\s*(?<n>.+?)\s*[.!?]*\s*$|^\s*(please\s+)?register\s+me\s*[:\-]\s*(?<n>.+?)\s*$", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"\b(add|put|throw|stick|sign|get|let)\s+(me|us)\s+(in|into|on|to)?\s*(the\s+)?(queue|list|game|lobby|match|custom)|\b(let|lemme|lemme|gonna|wanna|want\s+to|can\s+i|can\s+you)\s+(me\s+)?(join|get\s+in)\b|^\s*(i\s+)?(wanna|want\s+to|would\s+like\s+to|'?d\s+like\s+to)\s+(play|join)\s*[.!?]*\s*$|^\s*(join\s+me|i'?m\s+in|im\s+in|count\s+me\s+in|queue\s+me)\s*[.!?]*\s*$", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"\b(take|remove|get|pull|drop)\s+me\s+(out|off)\b.{0,20}\b(queue|list|game|lobby)?|\b(leave|exit|quit)\s+(the\s+)?(queue|lobby|game|list)\b|\bi\s+(have\s+to|gotta|need\s+to|must)\s+(go|leave)\b.{0,25}\b(queue|game|lobby)\b|\b(cancel|unqueue|dequeue)\s+me\b|\bi'?m\s+out\b.{0,12}\b(queue|game)", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"\b(where|what('?s|\s+is))\b.{0,12}\b(am\s+i|my\s+(place|position|spot|pos|turn))\b.{0,18}\b(queue|line|list)?|\b(my\s+)?(position|spot|place)\s+(in\s+)?(the\s+)?(queue|line|list)\b|\bhow\s+(long|far|many)\b.{0,25}\b(until|till|before|to)\b.{0,15}\b(my\s+turn|play|i\s+play|im\s+up|i'?m\s+up)|\bam\s+i\s+(in|on)\s+(the\s+)?(queue|list)\b|\bwhen\s+(do|will|am)\s+(i|we)\b.{0,12}\b(play|up|next|go)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant)
    };
    static bool PgHelperTopic(string text)
    {
        if (string.IsNullOrEmpty(text)) return false;
        foreach (var rx in PgHelperTopics) if (rx.IsMatch(text)) return true;
        return false;
    }
    // <<PINGUINO-SHARED-END>>

    class HelperSettings
    {
        public bool Enabled { get; set; } = true;
        public string LobbyName { get; set; } = "peng3";
        public string LobbyPassword { get; set; } = "";               // blank = "no password"
        public string CoreActionName { get; set; } = "PinguinoBot";   // the Streamer.bot action that runs PinguinoBotCore.cs
        public string ChatActionName { get; set; } = "PinguinoChat";  // messages the helper does not handle are handed to this action
        public bool ForwardHandled { get; set; } = false;             // also hand handled messages on (needs the helperHandled hook in the chatbot)
        public string BotAccount { get; set; } = "pinguinob0t";
        public bool LiveOnly { get; set; } = true;
        public bool RandomChime { get; set; } = true;                 // the helper (not Chatty) may drop a short helpful / fun tip into a quiet moment
        public double ChimeChancePct { get; set; } = 3;               // chance per ordinary chat line that passes every gate
        public int ChimeGlobalGapSec { get; set; } = 900;             // chat as a whole hears a chime at most this often
        public int ChimeUserGapSec { get; set; } = 3600;              // ...and the same viewer at most this often
        public int ChimeMinChars { get; set; } = 15;
        public int UserCooldownSec { get; set; } = 30;                // the same viewer gets the same kind of answer at most this often
        public int InfoCooldownSec { get; set; } = 8;                 // anti-flood between any two info answers
        public int McCooldownSec { get; set; } = 180;                 // the same viewer gets the Minecraft question / answer at most this often
        public int McGlobalCooldownSec { get; set; } = 45;            // ...and chat as a whole at most this often (a burst of "minecraft" gets ONE reply)
        public bool ContextGate { get; set; } = true;                 // only step in when the viewer is really asking / wanting to join / needing help (reads the recent chat); off = the old pattern-only behaviour
        public int AnsweredWindowSec { get; set; } = 120;             // someone else (a viewer or mod) already answered this person this recently: stay out
        public int SameAnswerGapSec { get; set; } = 45;               // the same kind of info answer is not repeated to anyone within this many seconds
        public int ConfirmSeconds { get; set; } = 60;                 // how long a "say yes" question stays open
        public bool UseAi { get; set; } = true;                       // ask the AI only when the patterns do not understand a practical-sounding message
        public int MaxAiCallsPerHour { get; set; } = 40;
        public string FactsUrl { get; set; } = "https://innocentpenguin.com/api/faq";   // the website's facts (Minecraft IPs, Discord, ...); blank = use helper_facts.json only
        public string SiteBase { get; set; } = "https://innocentpenguin.com";   // where longer explanations live: the helper answers in 1-2 short lines and points here
        public bool ReviewOn { get; set; } = true;                    // private help-review log (Data\helper\review.jsonl): every helper answer and every probably-missed question, with the chat around it
        public int ReviewBefore { get; set; } = 8;                    // chat lines (from all chatters) kept from before the trigger ...
        public int ReviewAfter { get; set; } = 8;                     // ... and after it
        public int ReviewAfterSec { get; set; } = 300;                // the "after" part stops this long after the trigger even if fewer lines came
        public int JoinGuardSec { get; set; } = 120;                  // after the helper added someone to the queue, a second "add me" within this many seconds is answered with "already added" (no core call)
        public int NegativeMuteSec { get; set; } = 300;               // "wasn't talking to you" / "wrong context": silent for that viewer this long, and the review log marks it as negative feedback
        public int PhraseBankSize { get; set; } = 3;                  // the AI words an answer this many times, then the stored wordings repeat with no AI call
    }

    // ── state (static: survives between messages while Streamer.bot stays open) ──
    static readonly object _lock = new object();
    static string _dir;
    static HelperSettings _cfg = new HelperSettings();
    static DateTime _cfgChecked = DateTime.MinValue, _cfgStamp = DateTime.MinValue;
    static bool _init;
    class Pending { public string Intent, Epic; public long Until; }
    static readonly Dictionary<string, Pending> _pending = new Dictionary<string, Pending>();
    static readonly Dictionary<string, long> _userCd = new Dictionary<string, long>();
    static readonly Dictionary<string, long> _mutedUntil = new Dictionary<string, long>(), _saidTo = new Dictionary<string, long>(), _joinedByHelper = new Dictionary<string, long>();
    static long _lobbyToldAt, _lobbyFixGap;
    static long _infoCd, _mcGlobal;
    static string _curLogin = "", _curDisplay = "";   // the viewer being answered (for the helper conversation marker and failure messages)
    static readonly List<long> _aiLog = new List<long>();
    static Func<string, string, string> _testLlm;   // tests only: a fake AI

    static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

    // ══════════════════════════════════════════════════════════════
    //  PATTERNS (the free pass)
    // ══════════════════════════════════════════════════════════════
    const RegexOptions RX = RegexOptions.IgnoreCase | RegexOptions.CultureInvariant;
    static readonly Regex RxLobby = new Regex(@"\b(what'?s|whats|what\s+is|wats|gimme|give\s+me|drop|send|tell\s+me|share|need|where'?s|wheres)\b.{0,25}\b(code|pass(word|wd|w)?|pw|lobby|private\s*match|custom\s*(game|match|lobby)?|pm)\b|\b(name\s*(and|&|\+|n|/)\s*(pass|pw|password))\b|\b(lobby|private\s*match|custom)\s*(name|code|pass(word)?|pw)\b|\bpass(word)?\s*(for\s+)?(the\s+)?(lobby|game|match|custom|private)|^\s*(code|pass(word)?|pw|lobby)\s*\??\s*$", RX);
    static readonly Regex RxHowJoin = new Regex(@"\bhow\s+(do|can|to|does|would|should)\b.{0,20}\b(join|play|get\s+in|enter|queue|participate|get\s+into|be\s+in)\b|\b(can|could)\s+(i|we|someone|anyone)\s+(play|join)\b|\b(wanna|want\s+to|like\s+to|trying\s+to)\s+(play|join)\b.{0,25}\b(game|customs?|match|lobby|queue|you|stream|viewer|with)\b|\bhow\s+(does|do)\s+(this|it|the\s+(queue|game|lobby))\s+work\b|\bhow\s+(to|do\s+i)\s+(get\s+)?(in\s+)?the\s+(queue|game|lobby)\b|\bviewer\s+games?\b.{0,15}\bhow\b", RX);
    static readonly Regex RxHowReg = new Regex(@"\bhow\b.{0,25}\b(register|sign\s*up|link)\b|\bwhat('?s|\s+is)\b.{0,12}\bregister\b|\b(register|registration)\b.{0,20}\b(work|how|help|not\s+working|doesn'?t|wont|won'?t|fail|error)|\bhow\b.{0,15}\b(epic|link\s+my)\b", RX);
    static readonly Regex RxDoReg = new Regex(@"^\s*(please\s+|pls\s+|plz\s+)?(register|sign)\s+me\s+(up\s+)?(as|with|under|using)\s+(?<n>.+?)\s*[.!?]*\s*$|\bmy\s+(epic|epic\s+games|epic\s+name|epic\s+id|game\s*id|rl\s+name|username\s+is)\s*(name\s*|id\s*)?(is|=|:)\s*(?<n>.+?)\s*[.!?]*\s*$|^\s*(please\s+)?register\s+me\s*[:\-]\s*(?<n>.+?)\s*$", RX);
    static readonly Regex RxDoJoin = new Regex(@"\b(add|put|throw|stick|sign|get|let)\s+(me|us)\s+(in|into|on|to)?\s*(the\s+)?(queue|list|game|lobby|match|custom)|\b(let|lemme|lemme|gonna|wanna|want\s+to|can\s+i|can\s+you)\s+(me\s+)?(join|get\s+in)\b|^\s*(i\s+)?(wanna|want\s+to|would\s+like\s+to|'?d\s+like\s+to)\s+(play|join)\s*[.!?]*\s*$|^\s*(join\s+me|i'?m\s+in|im\s+in|count\s+me\s+in|queue\s+me)\s*[.!?]*\s*$", RX);
    static readonly Regex RxDoLeave = new Regex(@"\b(take|remove|get|pull|drop)\s+me\s+(out|off)\b.{0,20}\b(queue|list|game|lobby)?|\b(leave|exit|quit)\s+(the\s+)?(queue|lobby|game|list)\b|\bi\s+(have\s+to|gotta|need\s+to|must)\s+(go|leave)\b.{0,25}\b(queue|game|lobby)\b|\b(cancel|unqueue|dequeue)\s+me\b|\bi'?m\s+out\b.{0,12}\b(queue|game)", RX);
    static readonly Regex RxPos = new Regex(@"\b(where|what('?s|\s+is))\b.{0,12}\b(am\s+i|my\s+(place|position|spot|pos|turn))\b.{0,18}\b(queue|line|list)?|\b(my\s+)?(position|spot|place)\s+(in\s+)?(the\s+)?(queue|line|list)\b|\bhow\s+(long|far|many)\b.{0,25}\b(until|till|before|to)\b.{0,15}\b(my\s+turn|play|i\s+play|im\s+up|i'?m\s+up)|\bam\s+i\s+(in|on)\s+(the\s+)?(queue|list)\b|\bwhen\s+(do|will|am)\s+(i|we)\b.{0,12}\b(play|up|next|go)\b", RX);
    // the viewer is telling the helper it got it wrong ("wasn't talking to you", "wrong context", "i didn't ask", "rustbucket")
    static readonly Regex RxNegFeedback = new Regex(@"\b(wasn'?t|was\s+not|not|weren'?t|isn'?t)\s+(even\s+)?(talking|speaking|asking)\s+(to|with)\s+(you|u|the\s+bot)\b|\bwrong\s+context\b|\bi\s+(didn'?t|did\s+not|never)\s+(ask|call)\b|\bnobody\s+asked\b|\bnot\s+(asking|talking\s+to)\s+you\b|\b(rust\s*bucket|clanker)\b.{0,20}\b(stop|shut|quiet|go\s+away)\b|\b(stop|shut\s+up|be\s+quiet|go\s+away)\b.{0,12}\b(helper|bot|pinguino\w*)\b|\bnot\s+you\b", RX);
    static readonly Regex RxLobbyFix = new Regex(@"\b(it'?s|its|it\s+is|is|now|use|try|should\s+be|changed\s+to|moved\s+to)\s+(?<n>peng\d+)\b|^\s*(?<n>peng\d+)\s*[.!]?\s*$", RX);
    static readonly Regex RxSiteAds = new Regex(@"\b(why|how\s+come|what)\b.{0,25}\b(ads?|commercials?)\b|\b(ads?|commercials?)\b.{0,25}\b(why|how\s+long|so\s+long|again|so\s+many)\b|\bhow\s+long\b.{0,12}\b(are|is)\b.{0,8}\b(the\s+)?ads?\b", RX);
    static readonly Regex RxSiteTts = new Regex(@"\b(tts|text\s*to\s*speech|voices?)\b.{0,30}\b(how|work|use|sub|who\s+can|can\s+i|where|list|which)\b|\b(how|where|can\s+i|who\s+can)\b.{0,30}\b(tts|text\s*to\s*speech|voices)\b", RX);
    static readonly Regex RxSiteRoblox = new Regex(@"\broblox\b.{0,30}\b(link|server|code|join|where|how|private|play)\b|\b(link|server|code|join|where|how)\b.{0,30}\broblox\b", RX);
    static readonly Regex RxYes = new Regex(@"^\s*@?\S*\s*(yes|yep|yeah|yea|ya|yup|y|ye|sure|ok|okay|k|please|pls|plz|do\s+it|go\s+ahead|confirm|yes\s+please|yes\s+pls|sí|si)\s*[.!]*\s*$", RX);
    static readonly Regex RxNo = new Regex(@"^\s*@?\S*\s*(no|nope|nah|n|cancel|nevermind|never\s*mind|stop|dont|don'?t|no\s+thanks|nvm)\s*[.!]*\s*$", RX);
    static readonly Regex RxBadReg = new Regex(@"^\s*!register\s+(?<a>.*)$", RX);
    static readonly Regex RxPractical = new Regex(@"\b(queue|lobby|join|register|code|pass(word)?|play|custom|private|match|epic|game|pm|in\s+line|commands?|leaderboards?|rules|faq|strikes?|emotes?|7tv)\b", RX);
    static readonly Regex RxAsking = new Regex(@"\?|\b(how|where|what|whats|when|can|could|do|does|is|are|will|wanna|want|need|help|pls|please|gimme|give)\b", RX);
    static readonly string[] Placeholders = { "name", "yourname", "your name", "your epic name", "yourepicname", "epicname", "epic name", "epic", "epicid", "epic id", "username", "user", "id", "your epic id", "yourepicid", "your id", "ign", "your name here", "yourusername", "your username", "epic username", "my epic name", "my name" };

    // ══════════════════════════════════════════════════════════════
    //  ENTRY POINT
    // ══════════════════════════════════════════════════════════════
    public bool Execute()
    {
        bool handled = false;
        try
        {
            Init();
            handled = Handle();
        }
        catch (Exception ex) { CPH.LogError("[Helper] failed: " + ex); }
        PgSetResult(handled ? "handled" : "pass");   // tells the router: done, or "not mine, next bot please"
        if (PgRouted()) return true;                 // the router passes the message on itself (Shared\BOTS_DESIGN.md)
        // LEGACY (no router yet): hand the message to the chatbot unless the helper dealt with it (never throws)
        try
        {
            if (!handled || _cfg.ForwardHandled)
            {
                if (handled) CPH.SetArgument("helperHandled", true);
                string chat = _cfg.ChatActionName;
                if (!string.IsNullOrWhiteSpace(chat)) CPH.RunAction(chat, true);
            }
        }
        catch (Exception ex) { CPH.LogError("[Helper] hand-over to the chatbot failed: " + ex.Message); }
        return true;
    }

    void Init()
    {
        lock (_lock)
        {
            if (!_init)
            {
                _dir = PgEnvDir() ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "BVQ");
                Directory.CreateDirectory(_dir);
                string p = Path.Combine(_dir, "helper_settings.json");
                if (!File.Exists(p)) File.WriteAllText(p, JsonConvert.SerializeObject(new HelperSettings(), Formatting.Indented));   // first run: a template to fill in
                _init = true;
                CPH.LogInfo("[Helper] Ready. Config: " + p);
            }
            if ((DateTime.UtcNow - _cfgChecked).TotalSeconds >= 10)
            {
                _cfgChecked = DateTime.UtcNow;
                string p = Path.Combine(_dir, "helper_settings.json");
                try
                {
                    DateTime stamp = File.GetLastWriteTimeUtc(p);
                    if (stamp != _cfgStamp) { var c = JsonConvert.DeserializeObject<HelperSettings>(File.ReadAllText(p)); if (c != null) { _cfg = c; _cfgStamp = stamp; } }
                }
                catch (Exception ex) { CPH.LogWarn("[Helper] helper_settings.json is not valid JSON: " + ex.Message); }
            }
        }
    }

    string ArgS(string name) { object o; return CPH.TryGetArg(name, out o) && o != null ? (Convert.ToString(o) ?? "") : ""; }
    bool ArgB(string name) { object o; if (CPH.TryGetArg(name, out o) && o != null) { bool b; if (o is bool) return (bool)o; if (bool.TryParse(Convert.ToString(o), out b)) return b; } return false; }

    // ══════════════════════════════════════════════════════════════
    //  HELP-REVIEW LOG (private; never pushed anywhere): for every helper answer, and every question that looked like it needed help but got no answer,
    //  Data\helper\review.jsonl keeps the chat window of ALL chatters before and after, what the helper said or why it stayed silent, and room for a note.
    //  The Host browses it at /helper-review (/api/helper/review). Rows: {type:"trigger"...} and later {type:"after", id, at, u, t} lines.
    // ══════════════════════════════════════════════════════════════
    class ReviewOpen { public string Id; public int Left; public long Until; }
    static readonly List<ReviewOpen> _revOpen = new List<ReviewOpen>();
    static readonly List<string> _said = new List<string>();     // what the helper said while handling the current message
    static string _gateWhy = "", _revIntent = ""; static bool _revReady; static int _revSeq;

    string ReviewPath()
    {
        string d = (_dir ?? "").TrimEnd('\\', '/');
        string root = string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d;
        string dir = Path.Combine(root, "helper"); Directory.CreateDirectory(dir); return Path.Combine(dir, "review.jsonl");
    }
    void ReviewAppend(JObject row) { try { File.AppendAllText(ReviewPath(), row.ToString(Formatting.None) + "\n", new UTF8Encoding(false)); } catch (Exception ex) { CPH.LogWarn("[Helper] review log: " + ex.Message); } }

    // every incoming line goes into the "after" part of the reviews that are still open
    void ReviewFollow(string login, string text)
    {
        if (!_cfg.ReviewOn || _revOpen.Count == 0) return;
        long now = Now();
        foreach (var o in _revOpen.ToList())
        {
            if (now > o.Until || o.Left <= 0) { _revOpen.Remove(o); continue; }
            ReviewAppend(new JObject { { "type", "after" }, { "id", o.Id }, { "at", now }, { "u", login }, { "t", text } });
            if (--o.Left <= 0) _revOpen.Remove(o);
        }
    }

    void ReviewAdd(string kind, string intent, string reason)
    {
        if (!_cfg.ReviewOn) return;
        var before = new JArray();
        lock (_recent)
        {
            var win = _recent.Count > 0 ? _recent.Skip(Math.Max(0, _recent.Count - 1 - Math.Max(0, _cfg.ReviewBefore))).Take(Math.Max(0, _cfg.ReviewBefore) + 1).ToList() : new List<Line>();
            foreach (var l in win) before.Add(new JObject { { "at", l.At }, { "u", l.Login }, { "t", l.Text } });   // the last one is the trigger itself
        }
        string id = DateTimeOffset.UtcNow.ToString("yyMMddHHmmss") + "-" + (++_revSeq);
        ReviewAppend(new JObject { { "type", "trigger" }, { "id", id }, { "at", Now() }, { "user", _curLogin }, { "text", _curText }, { "kind", kind }, { "intent", intent ?? "" },
            { "reply", string.Join(" / ", _said) }, { "reason", reason ?? "" }, { "window", before } });
        if (_cfg.ReviewAfter > 0) _revOpen.Add(new ReviewOpen { Id = id, Left = _cfg.ReviewAfter, Until = Now() + Math.Max(10, _cfg.ReviewAfterSec) });
    }

    // looks like somebody needing help (so a silence is worth a look later), without being a command
    static bool LooksLikeHelpAsk(string text)
    {
        if (string.IsNullOrWhiteSpace(text) || text.StartsWith("!") || text.Length > 220) return false;
        if (RxNotAsk.IsMatch(text) || !RxStrongAsk.IsMatch(text)) return false;
        return RxPractical.IsMatch(text) || RxMinecraftWord.IsMatch(text) || RxSiteCmds.IsMatch(text) || Regex.IsMatch(text, @"\b(help|stuck|doesn'?t\s+work|not\s+working|how\s+do\s+i|where\s+(do|can)\s+i|ip|discord)\b", RegexOptions.IgnoreCase);
    }

    // returns true when the helper answered or acted (so the chatbot should stay out of it)
    bool Handle()
    {
        _said.Clear(); _gateWhy = ""; _revIntent = ""; _revReady = false;
        bool handled = HandleCore();
        if (_said.Count > 0 && _curLogin != "") { _saidTo[_curLogin] = Now(); if (_revIntent == "lobby_info") _lobbyToldAt = Now(); }
        try
        {
            if (_revReady)
            {
                if (_said.Count > 0) ReviewAdd("answered", _revIntent, "");
                else if (LooksLikeHelpAsk(_curText)) ReviewAdd("missed", _revIntent, _gateWhy != "" ? _gateWhy : (_revIntent == "" ? "no pattern or AI intent matched" : "stayed silent"));
            }
        }
        catch (Exception ex) { CPH.LogWarn("[Helper] review failed: " + ex.Message); }
        return handled;
    }

    bool HandleCore()
    {
        if (!_cfg.Enabled) return false;
        string text = ArgS("message");
        string login = (ArgS("userName") != "" ? ArgS("userName") : ArgS("user")).ToLower().Trim();
        string display = ArgS("user") != "" ? ArgS("user") : login;
        if (text == "" || login == "") return false;
        if (login == (_cfg.BotAccount ?? "").ToLower() || PgIsBotAccount(login) || IsOtherBot(login)) return false;
        _curLogin = login; _curDisplay = display; _curText = text;
        Remember(login, text, ArgS("reply.userName") != "" ? ArgS("reply.userName") : ArgS("reply.userLogin"));
        try { ReviewFollow(login, text); } catch (Exception) { }
        if (_cfg.LiveOnly && !IsLive()) return false;
        _revReady = true;
        {   // negative feedback: the viewer says the helper was not wanted -> silent for a few minutes, noted for the review
            long nowN = Now(); long mu;
            if (_mutedUntil.TryGetValue(login, out mu) && mu > nowN) { _gateWhy = "muted after negative feedback"; return false; }
            long said;
            if (_saidTo.TryGetValue(login, out said) && nowN - said <= 180 && RxNegFeedback.IsMatch(text))
            {
                _mutedUntil[login] = nowN + Math.Max(30, _cfg.NegativeMuteSec);
                ReviewAdd("negative", "", "the viewer said the helper was not wanted: \"" + text + "\"; silent for " + _cfg.NegativeMuteSec + " s");
                _revReady = false; return false;
            }
        }
        {   // somebody corrects the private match name the helper gave ("it's peng3"): say thanks, flag it, not more than every 5 minutes
            var lf = RxLobbyFix.Match(text); long nowL = Now();
            if (lf.Success && !text.StartsWith("!") && nowL - _lobbyToldAt <= 900 && !string.Equals(lf.Groups["n"].Value, (_cfg.LobbyName ?? "").Trim(), StringComparison.OrdinalIgnoreCase) && nowL - _lobbyFixGap > 300)
            {
                _lobbyFixGap = nowL;
                ReviewAdd("missed", "lobby_fix", "chat says the private match is " + lf.Groups["n"].Value + " but the helper said " + _cfg.LobbyName);
                _revReady = false;
                Say("@" + display + " Thanks, " + lf.Groups["n"].Value + " noted. A mod can set it for good with !lobbyname " + lf.Groups["n"].Value + ".");
                return true;
            }
        }
        text = text.Trim();

        lock (_lock)
        {
            long now = Now();
            // 0. "Java or Bedrock?" was asked: the answer gets the right IP
            long mcUntil;
            if (_mcAsk.TryGetValue(login, out mcUntil))
            {
                if (mcUntil < now) _mcAsk.Remove(login);
                else { string ed = EditionOf(text); if (ed != "") { _mcAsk.Remove(login); return McAnswer(login, display, ed); } }
            }
            // 0b. the Minecraft IP was just given to this person: "it doesn't work" / "console" / the other edition gets real help
            McFollow mfu;
            if (_mcFollow.TryGetValue(login, out mfu))
            {
                if (mfu.Until < now) _mcFollow.Remove(login);
                else if (McFollowUp(login, display, text, mfu)) return true;
            }
            // 1. an open "say yes" question
            Pending pend;
            if (_pending.TryGetValue(login, out pend))
            {
                if (pend.Until < now) _pending.Remove(login);
                else if (RxYes.IsMatch(text)) { _pending.Remove(login); return Do(login, display, pend.Intent, pend.Epic); }
                else if (RxNo.IsMatch(text)) { _pending.Remove(login); Say("@" + display + " No problem, nothing changed."); return true; }
            }

            // 2. a typed !register that will not work (brackets, "my epic is ...", a placeholder)
            if (text.StartsWith("!"))
            {
                var lcm = Regex.Match(text, @"^!(lobbyname|lobbypass|lobbypassword)(?:\s+(?<v>.*))?$", RegexOptions.IgnoreCase);
                if (lcm.Success) return LobbyCommand(lcm.Groups[1].Value.ToLower(), lcm.Groups["v"].Value, display);
                if (RxDiscordCmd.IsMatch(text)) return Respond(login, display, "discord", "");
                var bm = RxBadReg.Match(text);
                if (bm.Success) return BadRegister(login, display, bm.Groups["a"].Value.Trim());
                return false;   // every other command belongs to the game manager (and the chatbot sees it through the hand-over)
            }

            // 3. patterns
            string intent, epic = "";
            Classify(text, out intent, out epic);
            if (intent == "" && RxStrongAsk.IsMatch(text)) { _taughtHit = TaughtMatch(text); if (_taughtHit != null) intent = "site_taught"; }

            // 4. the AI, only when the patterns found nothing but it sounds practical
            if (intent == "" && _cfg.UseAi && RxPractical.IsMatch(text) && RxAsking.IsMatch(text) && text.Length <= 200)
                AskAi(text, out intent, out epic);

            _revIntent = intent;
            if (intent == "") return TryChime(login, display, text);
            if (_cfg.ContextGate && !ContextOk(login, text, intent)) return false;   // passing mention / talk between viewers / already answered: stay out
            return Respond(login, display, intent, epic);
        }
    }

    // ---- random chime: a rate-limited, helpful / fun tip. Never for opted-out or !unping viewers, replies, @mentions, commands, bots, or while someone is muting the helper ----
    static long _chimeGlobal; static readonly Dictionary<string, long> _chimeUser = new Dictionary<string, long>(); static int _chimeNext;
    static Func<double> _pgTestRoll;
    static readonly string[] ChimeTips = {
        "Tip: !points shows your pengs, you earn them just by hanging out.",
        "Fun one: ask !8ball a question and see what the penguin says.",
        "Need a nudge? !remindme 10m stretch and I will ping you.",
        "Did you know !watchtime tells you how long you have been here?",
        "Tip: the website has the leaderboards and the full command list.",
        "Fun one: !streak shows how many streams in a row you showed up." };
    bool OptedOutOfBots(string login)
    {
        try
        {
            var m = ReadJson("chat_memory.json");
            if (m != null) foreach (var p in m.Properties()) { var v = p.Value as JObject; if (v == null || string.IsNullOrEmpty((string)v["Privacy"])) continue; if (string.Equals((string)v["Login"], login, StringComparison.OrdinalIgnoreCase)) return true; }
            var u = ReadJson("unping.json");
            if (u != null) { var arr = u["logins"] as JArray; if (arr != null && arr.Any(x => string.Equals((string)x, login, StringComparison.OrdinalIgnoreCase))) return true; if (u[login] != null && u[login].Type == JTokenType.Boolean && (bool)u[login]) return true; }
        }
        catch (Exception) { }
        return false;
    }
    bool TryChime(string login, string display, string text)
    {
        if (!_cfg.RandomChime || _cfg.ChimeChancePct <= 0) return false;
        if (text.Length < _cfg.ChimeMinChars || text.StartsWith("!") || text.Contains("@") || text.IndexOf("http", StringComparison.OrdinalIgnoreCase) >= 0) return false;
        if (!string.IsNullOrEmpty(ArgS("reply.userName")) || !string.IsNullOrEmpty(ArgS("reply.userLogin"))) return false;
        if (PgIsBotAccount(login) || IsOtherBot(login)) return false;
        long now = Now();
        long m; if (_mutedUntil.TryGetValue(login, out m) && m > now) return false;
        if (now - _chimeGlobal < _cfg.ChimeGlobalGapSec) return false;
        long last; if (_chimeUser.TryGetValue(login, out last) && now - last < _cfg.ChimeUserGapSec) return false;
        double roll = _pgTestRoll != null ? _pgTestRoll() : _rnd.NextDouble() * 100;
        if (roll >= _cfg.ChimeChancePct) return false;
        if (OptedOutOfBots(login)) return false;
        _chimeGlobal = now; _chimeUser[login] = now;
        string tip = ChimeTips[_chimeNext++ % ChimeTips.Length];
        _revIntent = "chime"; Say("@" + display + " " + tip); return true;
    }

    // ---- context gate: the helper only steps in when the viewer is really asking or needing help ----
    class Line { public long At; public string Login, Text, ReplyTo; }
    static readonly List<Line> _recent = new List<Line>();
    static readonly Dictionary<string, long> _sameAnswer = new Dictionary<string, long>();
    void Remember(string login, string text, string replyTo)
    {
        lock (_recent)
        {
            _recent.Add(new Line { At = Now(), Login = login, Text = text, ReplyTo = (replyTo ?? "").ToLower() });
            if (_recent.Count > 60) _recent.RemoveRange(0, _recent.Count - 60);
        }
    }
    // an explicit ask: a question, "how do I", "can I join", "I wanna play", "what's the ip", "is the server up", new here ...
    static readonly Regex RxStrongAsk = new Regex(@"\?|\b(how\s+(do|can|to|does|would|should)\b|can\s+(i|we|someone|anyone|me)\b|could\s+(i|we|someone)\b|where('?s|\s+is|\s+do|\s+can)\b|what'?s\b|whats\b|what\s+is\b|is\s+(the|there|it)\b|i\s+(wanna|want\s+to|need|would\s+like|'?d\s+like)\b|wanna\s+(join|play)\b|let\s+me\b|lemme\b|add\s+me\b|put\s+me\b|gimme\b|give\s+me\b|tell\s+me\b|anyone\b|someone\b|help\b|new\s+here\b|first\s+time\b|how\s+does\b)|\b(pls|plz|please)\b", RegexOptions.IgnoreCase);
    // a statement, a negation or a "why" rant is not a request for help
    static readonly Regex RxNotAsk = new Regex(@"\b(i'?m|im)\s+not\b|\b(not|never|n'?t)\s+(even\s+)?(trying|going|gonna)\b|\bi\s+(don'?t|dont|didn'?t|haven'?t|havent|lwky|literally)\b|\bwhy\s+(would|do|does|did)\b|\bup\s+to\s+the\s+people\b", RegexOptions.IgnoreCase);
    static readonly Regex RxAnswerish = new Regex(@"smp\.innocentpenguin|hc\.innocentpenguin|\bpeng\d\b|lobby\s*(name|code)|\b!(ip|mc|lobby|discord|register|join|queue)\b|\bbedrock\b|\bjava\b|\bport\b|\bpassword\b", RegexOptions.IgnoreCase);

    bool ContextOk(string login, string text, string intent)
    {
        bool info = intent == "mc_info" || intent == "lobby_info" || intent == "how_join" || intent == "how_register" || intent == "do_join" || IsSite(intent);
        if (!info) return true;                                                   // register / leave / position / song / mmr are direct requests
        long now = Now();
        string replyTo = ArgS("reply.userName") != "" ? ArgS("reply.userName") : ArgS("reply.userLogin");
        // 1) meant for somebody else: a reply to another viewer, or starting with their @name (the bots' own names do not count)
        if (!string.IsNullOrEmpty(replyTo) && replyTo.ToLower() != (_cfg.BotAccount ?? "").ToLower() && !PgIsBotAccount(replyTo.ToLower()) && !IsOtherBot(replyTo.ToLower())) { _gateWhy = "a reply to another viewer (" + replyTo + ")"; return false; }
        var at = Regex.Match(text, @"^@(\w+)");
        if (at.Success)
        {
            string tgt = at.Groups[1].Value.ToLower();
            if (tgt != (_cfg.BotAccount ?? "").ToLower() && !PgIsBotAccount(tgt) && !IsOtherBot(tgt) && !tgt.Contains("pinguino")) { _gateWhy = "addressed to @" + tgt; return false; }
        }
        // 2) it has to be a real ask, not a statement or a passing mention
        if (RxNotAsk.IsMatch(text) || !(RxStrongAsk.IsMatch(text) || (intent == "mc_info" && IsMcQuestion(text)))) { _gateWhy = "not a real question (statement or passing mention)"; return false; }
        lock (_recent)
        {
            // 3) somebody else (a viewer or mod) already answered this person a moment ago
            foreach (var l in _recent.Where(x => now - x.At <= _cfg.AnsweredWindowSec && x.Login != login && !PgIsBotAccount(x.Login) && !IsOtherBot(x.Login)))
                if ((l.Text ?? "").ToLower().Contains("@" + login) || l.ReplyTo == login) { if (RxAnswerish.IsMatch(l.Text ?? "") || (l.Text ?? "").Length >= 12) { _gateWhy = "someone else (" + l.Login + ") already answered"; return false; } }
            // 4) the same kind of answer just went out to someone else: do not repeat it to everybody
            long last; if (_sameAnswer.TryGetValue(intent, out last) && now - last < _cfg.SameAnswerGapSec) { _gateWhy = "the same answer just went out to someone else"; return false; }
        }
        lock (_recent) _sameAnswer[intent] = now;
        return true;
    }

    static readonly System.Text.RegularExpressions.Regex RxMcIp = new System.Text.RegularExpressions.Regex(@"\b(minecraft\s+)?(server\s+)?ip\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
    static readonly System.Text.RegularExpressions.Regex RxDiscordCmd = new System.Text.RegularExpressions.Regex(@"^\s*!discord\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    // ══════════════════════════════════════════════════════════════
    //  Minecraft + website facts. The AI words each answer a few times (checked against the facts), then the stored wordings repeat for free.
    // ══════════════════════════════════════════════════════════════
    static readonly Regex RxMinecraftWord = new Regex(@"\b(minecraft|mc|smp)\b", RegexOptions.IgnoreCase);
    static readonly Regex RxJavaWord = new Regex(@"\bjava\b", RegexOptions.IgnoreCase);
    static readonly Regex RxBedrockWord = new Regex(@"\b(bed\s*rock|pe|mobile|phone|console|xbox|playstation|ps[45]|switch|android|iphone|ipad|windows\s*10)\b", RegexOptions.IgnoreCase);
    static readonly Dictionary<string, long> _mcAsk = new Dictionary<string, long>();
    static string _curText = "";
    static JObject _facts; static DateTime _factsAt = DateTime.MinValue, _siteAt = DateTime.MinValue; static JObject _site;
    static readonly Random _rnd = new Random();
    static readonly string[] McAskVariants = { "Are you on Java or Bedrock?", "Java or Bedrock? (Java only needs the IP, Bedrock needs the IP and a port)", "Which version do you play, Java or Bedrock?" };

    static string EditionOf(string text)
    {
        bool j = RxJavaWord.IsMatch(text ?? ""), b = RxBedrockWord.IsMatch(text ?? "");
        return j == b ? "" : j ? "java" : "bedrock";
    }

    // helper_facts.json is the single source of truth for what the helper tells people; it is seeded once (from what the other chatbots said in the chat logs) and
    // then topped up from the website (FactsUrl) so the answers stay current. A site value always wins.
    JObject Facts()
    {
        if (_facts != null && (DateTime.UtcNow - _factsAt).TotalSeconds < 60) return _facts;
        JObject f = ReadJson("helper_facts.json");
        if (f == null)
        {
            f = new JObject {
                { "McSmpIp", "smp.innocentpenguin.com" }, { "McHardcoreIp", "hc.innocentpenguin.com" }, { "McBedrockPort", "19132" }, { "McHardcoreBedrockPort", "9216" }, { "McVersion", "" }, { "McBedrockConnectDns", "" }, { "McConsoleFriend", "BedrockGo2" },
                { "McRules", "No griefing, no killing, no stealing, no cheating, be nice." }, { "Discord", "https://discord.gg/fktz5sq4b8" }, { "Website", "https://innocentpenguin.com" },
                { "Note", "Seeded from the chat logs of 2026-10-16. Check these once; the website (FactsUrl) overrides them when it has the same key." } };
            try { File.WriteAllText(Path.Combine(_dir, "helper_facts.json"), f.ToString()); } catch (Exception) { }
        }
        var merged = (JObject)f.DeepClone();
        var site = SiteFacts();
        if (site != null) foreach (var kv in site) if (!string.IsNullOrWhiteSpace((string)kv.Value)) merged[kv.Key] = kv.Value;
        _facts = merged; _factsAt = DateTime.UtcNow; return merged;
    }
    // {"McSmpIp": "...", ...} or {"faq":[{"key":"McSmpIp","answer":"..."}]} from the website, at most every 10 minutes; any failure just keeps the old copy
    JObject SiteFacts()
    {
        string url = (_cfg.FactsUrl ?? "").Trim();
        if (url == "") return _site;
        if ((DateTime.UtcNow - _siteAt).TotalMinutes < 10) return _site;
        _siteAt = DateTime.UtcNow;
        try
        {
            string body = _pgTestHttp != null ? _pgTestHttp("GET " + url, "", "") : HttpGetText(url);
            var j = JObject.Parse(body); var o = new JObject();
            if (j["faq"] is JArray arr) { foreach (var it in arr) if (it["key"] != null && it["answer"] != null) MapFaq(o, (string)it["key"], (string)it["answer"], (string)it["url"]); }
            else foreach (var kv in j) if (kv.Value.Type == JTokenType.String) o[kv.Key] = kv.Value;
            _site = o;
        }
        catch (Exception) { }
        return _site;
    }
    // innocentpenguin.com/api/faq entries -> the facts above ("minecraft_ip": "Community SMP: smp... (Bedrock port 19132). Hardcore SMP: hc... (Bedrock port 9216).")
    static void MapFaq(JObject o, string key, string answer, string url)
    {
        if (key == "discord") { o["Discord"] = (url ?? "").StartsWith("http") ? url : answer; return; }
        if (key == "minecraft_ip")
        {
            var c = Regex.Match(answer, @"Community[^:]*:\s*(?<h>[A-Za-z0-9.\-]+)\s*\(Bedrock port (?<p>\d+)\)", RegexOptions.IgnoreCase);
            var h = Regex.Match(answer, @"Hardcore[^:]*:\s*(?<h>[A-Za-z0-9.\-]+)\s*\(Bedrock port (?<p>\d+)\)", RegexOptions.IgnoreCase);
            if (c.Success) { o["McSmpIp"] = c.Groups["h"].Value; o["McBedrockPort"] = c.Groups["p"].Value; }
            if (h.Success) { o["McHardcoreIp"] = h.Groups["h"].Value; o["McHardcoreBedrockPort"] = h.Groups["p"].Value; }
            return;
        }
        if (key.StartsWith("Mc") || key == "Discord" || key == "Website") o[key] = answer;   // already in the facts' own names
    }
    string HttpGetText(string url)
    {
        ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
        var req = (HttpWebRequest)WebRequest.Create(url); req.Method = "GET"; req.Timeout = 6000; req.ReadWriteTimeout = 6000;
        using (var resp = (HttpWebResponse)req.GetResponse())
        using (var rd = new StreamReader(resp.GetResponseStream(), Encoding.UTF8)) return rd.ReadToEnd();
    }
    static string F(JObject f, string k) { return ((string)f[k] ?? "").Trim(); }

    // a stored wording per question key; it is dropped when the facts it was written from change
    string Worded(string key, string question, string[] mustContain, string template, JObject facts)
    {
        string hash = Math.Abs(facts.ToString(Formatting.None).GetHashCode()).ToString();
        JObject bank = ReadJson("helper_phrases.json") ?? new JObject();
        var e = bank[key] as JObject;
        if (e == null || (string)e["facts"] != hash) { e = new JObject { { "facts", hash }, { "phrases", new JArray() } }; bank[key] = e; }
        var list = (JArray)e["phrases"];
        if (list.Count >= Math.Max(1, _cfg.PhraseBankSize))
        {
            var all = list.Select(x => (string)x).ToList();
            var others = all.Where(x => x != _lastPhrase).ToList();
            string pick = others.Count > 0 ? others[_rnd.Next(others.Count)] : all[0];
            _lastPhrase = pick; return pick;
        }
        string text = template;
        long now = Now(); _aiLog.RemoveAll(t => t < now - 3600);
        if (_cfg.UseAi && _aiLog.Count < _cfg.MaxAiCallsPerHour)
        {
            _aiLog.Add(now);
            string system = "You are PinguinoHelper, a friendly penguin helper in a Twitch chat. Write ONE short chat reply (under 220 characters, one line, no markdown, at most one emoji) answering the viewer's question. " +
                "Use ONLY these facts and copy every IP, port and link exactly: " + facts.ToString(Formatting.None) + ". Never invent anything that is not in the facts.";
            try
            {
                string r = Ask(system, question);
                r = (r ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
                if (r.Length > 0 && r.Length <= 400 && mustContain.All(m => r.IndexOf(m, StringComparison.OrdinalIgnoreCase) >= 0)) text = r;
            }
            catch (Exception ex) { CPH.LogWarn("[Helper] AI wording failed: " + ex.Message); }
        }
        if (!list.Any(x => (string)x == text)) list.Add(text);
        try { File.WriteAllText(Path.Combine(_dir, "helper_phrases.json"), bank.ToString()); } catch (Exception) { }
        _lastPhrase = text; return text;
    }
    static string _lastPhrase = "";

    bool McInfo(string login, string display)
    {
        var f = Facts();
        if (F(f, "McSmpIp") == "") return false;                                    // nothing known: stay quiet
        string ed = EditionOf(_curText);
        if (ed == "")
        {
            _mcAsk[login] = Now() + Math.Max(30, _cfg.ConfirmSeconds);
            Say("@" + display + " " + McAskVariants[_rnd.Next(McAskVariants.Length)]); return true;
        }
        return McAnswer(login, display, ed);
    }
    bool McAnswer(string login, string display, string ed)
    {
        var f = Facts(); string ip = F(f, "McSmpIp"), hc = F(f, "McHardcoreIp"), port = F(f, "McBedrockPort"), rules = F(f, "McRules");
        string hcPort = F(f, "McHardcoreBedrockPort");
        string hcPart = hc == "" ? "" : " (the stream-only hardcore server is " + hc + ")";
        _mcFollow[login] = new McFollow { Ed = ed, Until = Now() + 240, Last = 0 };   // their next message may be "it doesn't work" / "console": see McFollowUp
        if (ed == "java")
            Say("@" + display + " " + Worded("mc_java", "What is the Minecraft Java server IP?", new[] { ip }, "Java IP: " + ip + (hc == "" ? "" : " (hardcore: " + hc + ")"), f));
        else
        {
            if (port == "") port = "19132";
            string hcB = hc == "" ? "" : " (hardcore: " + hc + ", port " + (hcPort == "" ? port : hcPort) + ")";
            var must = new List<string> { ip, port }; if (hc != "") { must.Add(hc); must.Add(hcPort == "" ? port : hcPort); }
            Say("@" + display + " " + Worded("mc_bedrock", "What is the Minecraft Bedrock server address and port?", must.ToArray(), "Bedrock: IP " + ip + ", port " + port + hcB + ". On console? Say 'console' for the steps.", f));
        }
        return true;
    }

    // ---- follow-up after the IP was given: a short window where "it doesn't work", "console", or the other edition gets real help; anything else is left alone ----
    class McFollow { public string Ed; public long Until, Last; }
    static readonly Dictionary<string, McFollow> _mcFollow = new Dictionary<string, McFollow>();
    static readonly Regex RxConsole = new Regex(@"\b(console|xbox|play\s*station|ps[345]|switch|nintendo)\b", RegexOptions.IgnoreCase);
    static readonly Regex RxMcStuck = new Regex(@"\b(doesn'?t|does\s+not|won'?t|can'?t|cant|cannot|not|didn'?t|unable)\s+(work|working|connect|connecting|join|joining|find|show|load|see)\b|\b(error|failed|timed?\s*out|stuck|help|still|invalid|outdated|unknown host|can'?t\s+reach|nothing|no\s+response|what\s+now|now\s+what|how|where|what\s+do\s+i)\b", RegexOptions.IgnoreCase);
    bool McFollowUp(string login, string display, string text, McFollow fu)
    {
        long now = Now();
        string ed = EditionOf(text);
        if (ed != "" && ed != fu.Ed) return McAnswer(login, display, ed);                   // "no bedrock": give the other edition
        bool console = RxConsole.IsMatch(text);
        if (!console && !RxMcStuck.IsMatch(text)) return false;                               // not about this: leave it to the normal flow
        if (now - fu.Last < 20) return true;                                                  // one follow-up per 20 s
        fu.Last = now; fu.Until = now + 240;
        var f = Facts(); string ip = F(f, "McSmpIp"), port = F(f, "McBedrockPort"); if (port == "") port = "19132";
        string ver = F(f, "McVersion"), dns = F(f, "McBedrockConnectDns"), friend = f["McConsoleFriend"] == null ? "BedrockGo2" : F(f, "McConsoleFriend");   // from the chat: add BedrockGo2 as a friend, join its world, add the server
        string who = "@" + display + " ";
        if (console || fu.Ed == "bedrock" && RxConsole.IsMatch(_curText))
            Say(who + "Consoles (Xbox / PlayStation / Switch) can't type a server IP, so use Bedrock Connect: set your console's DNS to the Bedrock Connect server" + (dns == "" ? " (ask a mod for the current address)" : " (" + dns + ")") +
                ", open Minecraft > Servers, pick the Bedrock Connect entry, then add " + ip + " port " + port + "." + (friend == "" ? "" : " Chat's other trick: add " + friend + " as a friend, join its world, then add the server there."));
        else if (fu.Ed == "java")
            Say(who + "Java not connecting? 1) Type the IP exactly: " + ip + " (no port). 2) Use the server's version" + (ver == "" ? "" : " (" + ver + ")") + ". 3) Turn off a VPN or mods that change the version. Still stuck? Tell me the exact error.");
        else
            Say(who + "Bedrock not connecting? 1) Put the address " + ip + " and the port " + port + " in separate boxes. 2) Update Minecraft to the server's version" + (ver == "" ? "" : " (" + ver + ")") + ". 3) On console, say 'console' for Bedrock Connect. Still stuck? Tell me the exact error.");
        return true;
    }
    bool DiscordInfo(string display)
    {
        var f = Facts(); string link = F(f, "Discord"); if (link == "") return false;
        Say("@" + display + " " + Worded("discord", "Where is the Discord?", new[] { link }, "Join the Discord to hang out, share clips and get updates: " + link, f));
        return true;
    }

    // a REAL question about getting on the Minecraft server: asks (?, how/where/what/can..., please) AND talks about the IP / server / joining.
    // "Geo Minecraft today", "u guys also play minecraft" and talk about the !ip command do not count.
    static readonly Regex RxCmdToken = new Regex(@"(^|\s)!\w+");
    static readonly Regex RxMcAskForm = new Regex(@"\?|^\s*(how|where|what|whats|what's|can|could|is|are|do|does|wanna|want|gimme|give|drop|send|tell|need|anyone|someone)\b|\b(pls|plz|please)\b", RegexOptions.IgnoreCase);
    static readonly Regex RxMcTopic = new Regex(@"\b(ip|address|server|port|join|joining|connect|whitelist|get\s+on|get\s+in|play\s+with)\b", RegexOptions.IgnoreCase);
    static bool IsMcQuestion(string text)
    {
        text = text ?? "";
        if (text.Length > 140 || RxCmdToken.IsMatch(text)) return false;
        bool askForm = RxMcAskForm.IsMatch(text), terse = text.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries).Length <= 6;
        if (RxMcIp.IsMatch(text)) return askForm || terse;   // "minecraft ip" is a request too
        if (!askForm) return false;
        return RxMinecraftWord.IsMatch(text) && RxMcTopic.IsMatch(text);
    }
    static readonly Regex RxSong = new Regex(@"\b(what'?s|whats|what\s+is|which)\b.{0,12}\b(song|track|music)\b.{0,15}\b(this|playing|is\s+it|on)\b|\bwhat'?s\s+playing\b|\b(song|track)\s+(name|id|title)\b|\bwhat\s+song\b|\bname\s+of\s+(this|the)\s+song\b|\bnext\s+song\b", RegexOptions.IgnoreCase);
    static readonly Regex RxMyMmr = new Regex(@"\b(what'?s|whats|what\s+is|check|see|show|tell\s+me)\b.{0,12}\b(my|me)\b.{0,10}\b(mmr|rank|stats|points)\b|\bhow\s+(much|many)\b.{0,12}\b(mmr|points)\b.{0,10}\b(do\s+i|i\s+have|have\s+i)\b", RegexOptions.IgnoreCase);

    static readonly Regex RxSiteCmds = new Regex(@"\b(what|which|any)\b.{0,18}\bcommands?\b|\bcommands?\s*list\b|\blist\s+of\s+(the\s+)?commands\b|\bhow\b.{0,14}\b(use|do)\b.{0,16}\bcommands?\b|\bwhat\s+can\s+(you|the\s+bot|pinguino\w*)\s+do\b|\bwhat'?s\s+the\s+command\s+(for|to)\b|\bis\s+there\s+a\s+command\b", RX);
    static readonly Regex RxSiteBoards = new Regex(@"\b(leader\s*boards?|top\s+(gifters?|bitters?|yappers?|streaks?)|who\s+(has\s+)?(gifted|cheered|yapped)\s+the\s+most|most\s+gifted|watch\s*streak\s+(board|record|leaders?)|where\b.{0,12}\b(see|find|check)\b.{0,12}\b(my\s+)?(rank|ranking))\b", RX);
    static readonly Regex RxSiteProfile = new Regex(@"\b(my\s+profile|members?\s+page|where\b.{0,14}\b(see|find|check)\b.{0,16}\b(profile|my\s+stats|my\s+strikes|my\s+points)|what\s+does\s+(the\s+)?(bot|pinguino\w*)\s+know\s+about\s+me)\b", RX);
    static readonly Regex RxSiteFaq = new Regex(@"\b(the\s+rules|what\s+are\s+the\s+rules|chat\s+rules|faq|what\s+is\s+a\s+strike|what\s+are\s+strikes|how\s+do\s+strikes\s+work)\b", RX);
    static readonly Regex RxSiteEmotes = new Regex(@"\b(7tv|seventv|emote\s+(list|search)|what\s+emotes?\s+(are|does)|which\s+emotes?|where\b.{0,12}\bemotes?)\b", RX);

    // Approved "Taught" notes (helper_facts.json "Taught": [{id,text,taughtBy,...}], written by the Host's teach inbox only after Ivan approved them).
    // A question matches a note when at least two meaningful words overlap; the answer is the note's text, kept short, plus the site help page.
    JObject _taughtHit;
    static readonly HashSet<string> TaughtStop = new HashSet<string>(new[] { "what", "when", "where", "which", "does", "this", "that", "with", "have", "from", "your", "about", "there", "their", "they", "will", "would", "could", "should", "how", "the", "can", "you", "are", "for", "and", "any", "who", "why", "is", "do", "to", "of", "in", "on", "it", "a", "an", "pinguino", "penguin", "stream", "channel", "chat", "guys", "please", "tell", "know" });
    static HashSet<string> TaughtWords(string t)
    {
        var h = new HashSet<string>();
        foreach (Match m in Regex.Matches((t ?? "").ToLowerInvariant(), @"[a-z0-9']{3,}")) { string w = m.Value.Trim((char)39); if (w.Length >= 3 && !TaughtStop.Contains(w)) h.Add(w.Length > 4 && w.EndsWith("s") ? w.Substring(0, w.Length - 1) : w); }
        return h;
    }
    JObject TaughtMatch(string text)
    {
        try
        {
            var arr = Facts()["Taught"] as JArray; if (arr == null || arr.Count == 0) return null;
            var q = TaughtWords(text); if (q.Count < 2) return null;
            JObject best = null; int bs = 0;
            foreach (var it in arr.OfType<JObject>())
            {
                string tx = (string)it["text"] ?? ""; if (tx.Trim() == "") continue;
                int sc = TaughtWords(tx).Count(w => q.Contains(w));
                if (sc > bs) { bs = sc; best = it; }
            }
            return bs >= 2 ? best : null;
        }
        catch (Exception) { return null; }
    }

    static void Classify(string text, out string intent, out string epic)
    {
        intent = ""; epic = "";
        var m = RxDoReg.Match(text);
        if (m.Success) { intent = "do_register"; epic = m.Groups["n"].Value.Trim(); return; }
        if (IsMcQuestion(text)) { intent = "mc_info"; return; }
        if (RxSong.IsMatch(text)) { intent = "song"; return; }
        if (RxMyMmr.IsMatch(text)) { intent = "mmr_info"; return; }
        if (RxDoLeave.IsMatch(text)) { intent = "do_leave"; return; }
        if (RxPos.IsMatch(text)) { intent = "position"; return; }
        if (RxHowReg.IsMatch(text)) { intent = "how_register"; return; }
        if (RxLobby.IsMatch(text)) { intent = "lobby_info"; return; }
        if (RxHowJoin.IsMatch(text)) { intent = "how_join"; return; }
        if (RxDoJoin.IsMatch(text)) { intent = "do_join"; return; }
        if (RxSiteCmds.IsMatch(text)) { intent = "site_commands"; return; }
        if (RxSiteAds.IsMatch(text)) { intent = "site_ads"; return; }
        if (RxSiteTts.IsMatch(text)) { intent = "site_tts"; return; }
        if (RxSiteRoblox.IsMatch(text)) { intent = "site_roblox"; return; }
        if (RxSiteBoards.IsMatch(text)) { intent = "site_leaderboards"; return; }
        if (RxSiteProfile.IsMatch(text)) { intent = "site_profile"; return; }
        if (RxSiteEmotes.IsMatch(text)) { intent = "site_emotes"; return; }
        if (RxSiteFaq.IsMatch(text)) { intent = "site_faq"; return; }
    }

    // ══════════════════════════════════════════════════════════════
    //  AI (only to pick an intent from a fixed list; it never writes the reply)
    // ══════════════════════════════════════════════════════════════
    static readonly string[] Intents = { "lobby_info", "how_join", "how_register", "do_register", "do_join", "do_leave", "position", "site_commands", "site_leaderboards", "site_profile", "site_faq", "site_emotes", "none" };
    static bool IsSite(string i) { return i != null && i.StartsWith("site_"); }

    void AskAi(string text, out string intent, out string epic)
    {
        intent = ""; epic = "";
        long now = Now();
        _aiLog.RemoveAll(t => t < now - 3600);
        if (_aiLog.Count >= _cfg.MaxAiCallsPerHour) return;
        _aiLog.Add(now);
        string system = "You sort Twitch chat messages for a Rocket League viewer-games stream. Reply with ONLY JSON: {\"intent\":\"...\",\"epic\":\"...\"}. intent is one of: " +
            "lobby_info (asks for the private match / lobby name, code or password), how_join (asks how to join or play with the streamer), how_register (asks how to register / link their Epic name), " +
            "do_register (asks to be registered; put the Epic name they gave in epic), do_join (asks to be put in the queue), do_leave (asks to leave the queue), position (asks where they are in the queue), " +
            "site_commands (asks what commands exist / how to use commands), site_leaderboards (asks about the leaderboards, top gifters, rankings), site_profile (asks where to see their profile / stats / what the bot knows about them), site_faq (asks about the rules, strikes, common questions), site_emotes (asks about the 7TV emotes), " +
            "none (anything else: chatting, jokes, talking to someone else, other topics). When unsure, answer none. Never invent an Epic name.";
        string reply;
        try { reply = Ask(system, text); } catch (Exception ex) { CPH.LogWarn("[Helper] AI failed: " + ex.Message); return; }
        if (string.IsNullOrWhiteSpace(reply)) return;
        try
        {
            int a = reply.IndexOf('{'), b = reply.LastIndexOf('}');
            if (a < 0 || b <= a) return;
            var j = JObject.Parse(reply.Substring(a, b - a + 1));
            string i = ((string)j["intent"] ?? "").Trim().ToLower();
            if (!Intents.Contains(i) || i == "none") return;
            intent = i;
            epic = ((string)j["epic"] ?? "").Trim();
        }
        catch (Exception) { intent = ""; epic = ""; }
    }

    string Ask(string system, string user)
    {
        if (_testLlm != null) return _testLlm(system, user);
        JObject c = ReadJson("chat_settings.json");
        c = c ?? new JObject();
        string key = (string)c["ApiKey"] ?? "";
        if (key == "") key = CPH.GetGlobalVar<string>("pinguino.secret.aikey", false) ?? "";   // the key vault (Host)
        if (key == "") return null;
        string prov = (((string)c["Provider"]) ?? "claude").ToLower();
        string model = (string)c["Model"] ?? "", baseUrl = ((string)c["BaseUrl"] ?? "").TrimEnd('/');
        if (prov == "claude" || prov == "anthropic")
        {
            var body = new JObject { ["model"] = model == "" ? "claude-haiku-5-5" : model, ["max_tokens"] = 100, ["system"] = system,
                ["messages"] = new JArray { new JObject { ["role"] = "user", ["content"] = user } } };
            var r = JObject.Parse(HttpPost((baseUrl == "" ? "https://api.anthropic.com" : baseUrl) + "/v1/messages",
                new Dictionary<string, string> { { "x-api-key", key }, { "anthropic-version", "2023-06-01" } }, body.ToString(Formatting.None)));
            var sb = new StringBuilder();
            foreach (var blk in r["content"] as JArray ?? new JArray()) if ((string)blk["type"] == "text") sb.Append((string)blk["text"]);
            return sb.ToString();
        }
        else
        {
            var body = new JObject { ["model"] = model == "" ? "gpt-4o-mini" : model, ["max_tokens"] = 100,
                ["messages"] = new JArray { new JObject { ["role"] = "system", ["content"] = system }, new JObject { ["role"] = "user", ["content"] = user } } };
            var r = JObject.Parse(HttpPost((baseUrl == "" ? "https://api.openai.com/v1" : baseUrl) + "/chat/completions",
                new Dictionary<string, string> { { "Authorization", "Bearer " + key } }, body.ToString(Formatting.None)));
            return (string)r["choices"]?[0]?["message"]?["content"];
        }
    }

    string HttpPost(string url, Dictionary<string, string> headers, string json)
    {
        ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
        var req = (HttpWebRequest)WebRequest.Create(url);
        req.Method = "POST"; req.ContentType = "application/json"; req.Timeout = 15000; req.ReadWriteTimeout = 15000;
        foreach (var kv in headers) req.Headers[kv.Key] = kv.Value;
        byte[] bytes = Encoding.UTF8.GetBytes(json);
        req.ContentLength = bytes.Length;
        using (var s = req.GetRequestStream()) s.Write(bytes, 0, bytes.Length);
        using (var resp = (HttpWebResponse)req.GetResponse())
        using (var rd = new StreamReader(resp.GetResponseStream(), Encoding.UTF8)) return rd.ReadToEnd();
    }

    // ══════════════════════════════════════════════════════════════
    //  ANSWERS AND ACTIONS
    // ══════════════════════════════════════════════════════════════
    bool Respond(string login, string display, string intent, string epic)
    {
        long now = Now();
        if (intent == "mc_info" || intent == "discord")
        {
            string key = login + "|" + intent; long lastInfo;
            int userCd = intent == "mc_info" ? Math.Max(_cfg.UserCooldownSec, _cfg.McCooldownSec) : _cfg.UserCooldownSec;
            if (_userCd.TryGetValue(key, out lastInfo) && now - lastInfo < userCd) return true;
            if (intent == "mc_info")
            {   // already asked "Java or Bedrock?" and waiting for the answer: never ask again; and not more often than the global gap
                long open; if (_mcAsk.TryGetValue(login, out open) && open >= now) return true;
                if (now - _mcGlobal < _cfg.McGlobalCooldownSec) return true;
            }
            if (now - _infoCd < _cfg.InfoCooldownSec) return true;
            bool said = intent == "mc_info" ? McInfo(login, display) : DiscordInfo(display);
            if (said) { _userCd[key] = now; _infoCd = now; if (intent == "mc_info") _mcGlobal = now; }
            return said;
        }
        string cdKey = login + "|" + intent;
        long last;
        bool info = intent == "lobby_info" || intent == "how_join" || intent == "how_register" || intent == "song" || intent == "mmr_info" || IsSite(intent);
        if (_userCd.TryGetValue(cdKey, out last) && now - last < _cfg.UserCooldownSec) { _gateWhy = "cooldown: told this viewer the same a moment ago"; return true; }   // already told them a moment ago: stay quiet, and keep the chatbot out of it
        if (info && now - _infoCd < _cfg.InfoCooldownSec) { _gateWhy = "cooldown: another info answer just went out"; return true; }
        _userCd[cdKey] = now;
        if (info) _infoCd = now;

        JObject me = Player(login);
        string registered = me == null ? "" : ((string)me["GameId"] ?? "");
        string who = "@" + display + " ";

        switch (intent)
        {
            case "lobby_info":
                Say(who + LobbyLine() + QueueHint(registered));
                return true;
            case "how_join":
                Say(who + HowJoinText(registered));
                return true;
            case "how_register":
                Say(who + (registered != ""
                    ? "You're already registered as " + registered + ". Wrong name? Ask a mod to fix it. Next: say 'add me to the queue' when the queue is open."
                    : "2 steps: 1) !register YourEpicName (your exact Epic Games name, no < > brackets), 2) !join when the queue is open. Or tell me \"register me as YourEpicName\" and I'll do it."));
                return true;
            case "do_register":
            {
                string name = CleanEpic(epic);
                if (name == null) { Say(who + "I couldn't read a valid Epic name there. Names are 3-16 letters, numbers, spaces, _ - or . Try: register me as YourEpicName"); return true; }
                if (registered != "") { Say(who + "You're already registered as " + registered + ". Ask a mod if it needs changing."); return true; }
                return AskConfirm(login, display, "register", name, "Register you as \"" + name + "\" (your Epic name)? Say yes to confirm.");
            }
            case "do_join":
                if (registered == "") { Say(who + "You need to register first. Tell me \"register me as YourEpicName\" (your Epic name) and then ask to join."); return true; }
                if (!QueueOpen()) { Say(who + "The queue is closed right now. " + LobbyHint()); return true; }
                { long jb; if (_joinedByHelper.TryGetValue(login, out jb) && now - jb < _cfg.JoinGuardSec) { Say(who + "I already added you a moment ago. Ask \"where am I in the queue\" to check your spot."); return true; } }
                return AskConfirm(login, display, "join", "", "Add you to the queue? Say yes to confirm.");
            case "song": Say(who + SongLine()); return true;
            case "site_taught":
            {
                string tx = _taughtHit == null ? "" : ((string)_taughtHit["text"] ?? "").Trim(); _taughtHit = null;
                if (tx == "") return false;
                if (tx.Length > 200) { int cut = tx.LastIndexOf(' ', 200); tx = tx.Substring(0, cut > 80 ? cut : 200).TrimEnd(' ', ',', ';') + "..."; }
                Say(who + tx + " More: " + SiteUrl("/help")); return true;
            }
            case "site_ads": Say(who + "Ivan runs 3-minute ads during the stream so newcomers are not lost."); return true;
            case "site_tts": Say(who + "TTS voices (!brian, !hank, !ivy, !trump ...) are sub-only. All voices and commands: " + SiteUrl("/help#commands")); return true;
            case "site_roblox": Say(who + "Ivan posts the Roblox private-server link in chat himself. Keep an eye on chat."); return true;
            case "site_commands": Say(who + "Every chat command, with search: " + SiteUrl("/help#commands")); return true;
            case "site_leaderboards": Say(who + "Top gifters, bitters, yappers and watch streaks, all time or by month: " + SiteUrl("/leaderboards")); return true;
            case "site_profile": Say(who + "Your profile, stats and what the bot knows about you: " + SiteUrl("/members")); return true;
            case "site_faq": Say(who + "Rules and answers to common questions: " + SiteUrl("/faq")); return true;
            case "site_emotes": Say(who + "The channel's 7TV emotes, searchable: " + SiteUrl("/emotes")); return true;
            case "mmr_info": Say(who + "Type !mmr to see your MMR, or !stats for your wins and points."); return true;
            case "do_leave":
                return AskConfirm(login, display, "leave", "", "Take you out of the queue? Say yes to confirm.");
            case "position":
                return Do(login, display, "position", "");
        }
        return false;
    }

    string SiteUrl(string path)
    {
        string b = (_cfg.SiteBase ?? "").Trim().TrimEnd('/'); if (b == "") b = F(Facts(), "Website").TrimEnd('/'); if (b == "") b = "https://innocentpenguin.com";
        return b + path;
    }

    bool AskConfirm(string login, string display, string intent, string epic, string question)
    {
        _pending[login] = new Pending { Intent = intent, Epic = epic, Until = Now() + _cfg.ConfirmSeconds };
        Say("@" + display + " " + question);
        return true;
    }

    bool BadRegister(string login, string display, string arg)
    {
        string a = arg;
        if (a == "") return false;   // plain "!register": the game manager already explains it
        string stripped = Regex.Replace(a, @"^[<\[\(]\s*(.*?)\s*[>\]\)]$", "$1");
        bool wrapped = stripped != a;
        bool placeholder = Placeholders.Contains(stripped.ToLower());
        var mm = Regex.Match(a, @"^(my\s+(epic|name|id|epic\s+name|epic\s+id|username)\s+is|i\s+am|i'?m|it'?s|its|name\s*[:=]|epic\s*[:=])\s*(?<n>.+)$", RX);
        string extra = mm.Success ? Regex.Replace(mm.Groups["n"].Value.Trim(), @"^[<\[\(]\s*(.*?)\s*[>\]\)]$", "$1") : null;
        if (!wrapped && !placeholder && extra == null) return false;   // looks like a real name: leave it to the game manager
        if (placeholder) { Say("@" + display + " Replace the example with YOUR Epic name, like: !register YourEpicName (no < > brackets)."); return true; }
        string clean = CleanEpic(extra ?? stripped);
        if (clean == null) { Say("@" + display + " Type it like this: !register YourEpicName (just the name, no brackets or extra words)."); return true; }
        if (Player(login) != null) return false;   // already registered: the game manager says so
        return AskConfirm(login, display, "register", clean, "Tip: the command is just !register YourEpicName, no brackets or extra words. Register you as \"" + clean + "\"? Say yes to confirm.");
    }

    // the confirmed (or read-only) action: always the sender, always the allow-listed core commands, never privileged
    bool Do(string login, string display, string intent, string epic)
    {
        switch (intent)
        {
            case "register": { string n = CleanEpic(epic); if (n == null) return true; return CallCore("!register", n); }
            case "join": { long jb; if (_joinedByHelper.TryGetValue(login, out jb) && Now() - jb < _cfg.JoinGuardSec) return true; _joinedByHelper[login] = Now(); return CallCore("!join", ""); }
            case "leave": return CallCore("!leave", "");
            case "position": return CallCore("!pos", "");
        }
        return false;
    }

    static readonly string[] CoreKeys = { "command", "rawInput", "role", "isModerator", "isBroadcaster" };

    bool CallCore(string command, string input)
    {
        string core = !string.IsNullOrWhiteSpace(_cfg.CoreActionName) ? _cfg.CoreActionName : (PgBotOf("core") != null ? PgBotOf("core").Action : "");
        if (string.IsNullOrWhiteSpace(core)) return false;
        var coreBot = PgBotOf("core");
        if ((coreBot != null && !coreBot.Enabled) || !PgActionExists(core))
        {   // the game manager is not there: its fallback (chat, then helper) says so, the viewer is not left waiting
            PgSay("core", "@" + _curDisplay + " I can't reach the game manager right now. A mod can help with that.");
            return true;
        }
        // command allow-list: nothing else can ever be sent to the game manager
        if (command != "!register" && command != "!join" && command != "!leave" && command != "!pos") return false;
        var saved = new Dictionary<string, object>();
        foreach (var k in CoreKeys) { object o; saved[k] = CPH.TryGetArg(k, out o) ? o : null; }
        try
        {
            CPH.SetArgument("command", command);
            CPH.SetArgument("rawInput", input);
            CPH.SetArgument("role", 1);
            CPH.SetArgument("isModerator", false);
            CPH.SetArgument("isBroadcaster", false);
            CPH.RunAction(core, true);
        }
        finally
        {
            foreach (var k in CoreKeys) CPH.SetArgument(k, saved[k] ?? (k == "command" || k == "rawInput" ? (object)"" : (k == "role" ? (object)1 : false)));
        }
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  TEXT BUILDING
    // ══════════════════════════════════════════════════════════════
    // what is playing right now, from the Spotify module on this PC
    string SongLine()
    {
        try
        {
            string json = _pgTestHttp != null ? _pgTestHttp("GET http://127.0.0.1:8771/api/now", "", "") : HttpGetText("http://127.0.0.1:8771/api/now");
            var j = JObject.Parse(json); string t = (string)j["title"] ?? "", a = (string)j["artist"] ?? "", who = (string)j["requestedBy"] ?? "";
            if (t == "") return "Nothing is playing right now.";
            return "Now playing: " + t + (a == "" ? "" : " - " + a) + (who == "" ? "" : " (requested by " + who + ")") + ".";
        }
        catch (Exception) { return "I can't see what's playing right now."; }
    }
    static Func<string, string> _testHttpGet;   // tests only

    // mods only: !lobbyname NAME / !lobbypass PASS|off  (writes helper_settings.json, so the lobby answers change at once)
    bool LobbyCommand(string cmd, string value, string display)
    {
        int roleN = 0; bool mod = ArgB("isModerator") || ArgB("isBroadcaster") || (int.TryParse(ArgS("role"), out roleN) && roleN >= 3);
        if (!mod) { Say("@" + display + " Only mods can change the lobby."); return true; }
        value = (value ?? "").Trim();
        bool isName = cmd.StartsWith("lobbyname");
        if (value == "") { Say("@" + display + " " + (isName ? "Lobby name: " + (_cfg.LobbyName ?? "").Trim() + ". Change it with !lobbyname NewName" : LobbyHint() + " Change it with !lobbypass NewPass (or !lobbypass off)")); return true; }
        if (value.Length > 32 || Regex.IsMatch(value, @"[@/\\<>]")) { Say("@" + display + " That doesn't look like a valid " + (isName ? "lobby name" : "password") + " (32 characters max, no @ / < >)."); return true; }
        if (isName) _cfg.LobbyName = value;
        else _cfg.LobbyPassword = Regex.IsMatch(value, @"^(off|none|clear|no)$", RegexOptions.IgnoreCase) ? "" : value;
        try
        {
            string p = Path.Combine(_dir, "helper_settings.json");
            File.WriteAllText(p, JsonConvert.SerializeObject(_cfg, Formatting.Indented));
            _cfgStamp = File.GetLastWriteTimeUtc(p);
        }
        catch (Exception ex) { CPH.LogWarn("[Helper] could not save helper_settings.json: " + ex.Message); }
        Say("@" + display + " Done. " + LobbyHint());
        return true;
    }

    string LobbyLine()
    {
        string pass = string.IsNullOrWhiteSpace(_cfg.LobbyPassword) ? "no password" : "Password: " + _cfg.LobbyPassword.Trim();
        return "Private match -> Name: " + (_cfg.LobbyName ?? "").Trim() + ", " + pass + ". ";
    }

    string LobbyHint() { return "Private match name: " + (_cfg.LobbyName ?? "").Trim() + (string.IsNullOrWhiteSpace(_cfg.LobbyPassword) ? " (no password)." : ", password " + _cfg.LobbyPassword.Trim() + "."); }

    string QueueHint(string registered)
    {
        if (registered == "") return "To get a spot: register with !register YourEpicName, or tell me \"register me as YourEpicName\".";
        return QueueOpen() ? "You're registered, say \"add me to the queue\" to join." : "The queue is closed right now.";
    }

    string HowJoinText(string registered)
    {
        string steps = registered == ""
            ? "1) Register once: !register YourEpicName (or tell me \"register me as YourEpicName\"). 2) When the queue is open, say \"add me to the queue\" (or !join), once is enough, in chat or on the site. 3) When you're picked, search the private match name in Rocket League. "
            : "You're registered as " + registered + ". 1) When the queue is open, say \"add me to the queue\" (or !join), once is enough, in chat or on the site. 2) When you're picked, search the private match name in Rocket League. ";
        return steps + LobbyLine().TrimEnd();
    }

    // an Epic name the helper is willing to register: 3-16 letters/digits/space/_ - .
    static string CleanEpic(string raw)
    {
        if (raw == null) return null;
        string n = raw.Trim().Trim('"', '\'', '`', '<', '>', '[', ']', '(', ')').Trim();
        n = Regex.Replace(n, @"\s+", " ");
        if (n.Length < 3 || n.Length > 16) return null;
        if (!Regex.IsMatch(n, @"^[\p{L}\p{N} _\-.]+$")) return null;
        if (Placeholders.Contains(n.ToLower())) return null;
        return n;
    }

    // ══════════════════════════════════════════════════════════════
    //  READING THE GAME MANAGER'S FILES (read only)
    // ══════════════════════════════════════════════════════════════
    JObject ReadJson(string file)
    {
        try { string p = Path.Combine(_dir, file); return File.Exists(p) ? JObject.Parse(File.ReadAllText(p)) : null; }
        catch (Exception) { return null; }
    }

    JObject Player(string login)
    {
        var j = ReadJson("players.json");
        if (j == null) return null;
        foreach (var p in j.Properties()) if (string.Equals(p.Name, login, StringComparison.OrdinalIgnoreCase)) return p.Value as JObject;
        return null;
    }

    bool QueueOpen()
    {
        var j = ReadJson("live_state.json");
        return j != null && j["queueOpen"] != null && (bool)j["queueOpen"];
    }

    bool IsLive()
    {
        var j = ReadJson("settings.json");
        return j != null && j["WasLive"] != null && (bool)j["WasLive"];
    }

    bool IsOtherBot(string login)
    {
        switch (login) { case "nightbot": case "streamelements": case "streamlabs": case "moobot": case "fossabot": case "wizebot": case "supibot": case "botrix": return true; }
        return false;
    }

    // The helper speaks as HelperPinguino (through its fallback while it has no account of its own) and the viewer stays "in conversation" with it for a while.
    void Say(string msg)
    {
        _said.Add(msg);
        PgSay("helper", msg);
        PgSetHelperContext(_curLogin);
    }
}
