using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

// ══════════════════════════════════════════════════════════════════════════
//  PinguinoRouter: the front door of the three bots (HelperPinguino, PinguinoChat, PinguinoB0t). See Shared\BOTS_DESIGN.md.
//  Streamer.bot: new action "PinguinoRouter", trigger Twitch > Chat > Message (no command filter), Execute C# Code.
//  REMOVE the chat-message trigger from "PinguinoHelper" and "PinguinoChat" (they are started by the router). Keep PinguinoChat's event triggers
//  (subs, gifts, cheers, raids, follows) and the core's own command triggers as they are.
//  Who gets a message first:
//    - @ing or naming ANY of the bots -> PinguinoChat (it talks), unless the message is about what the helper just said / does (the helper spoke to this
//      viewer a moment ago, a reply to the helper, a yes / no, a short follow-up, a lobby / join / register question) -> the helper first.
//    - ordinary chat -> the helper first (it only answers practical questions), then PinguinoChat (it listens and may join in).
//    - !commands -> the helper (a mistyped !register), then PinguinoChat (it records them). The game manager runs its commands from its own triggers.
//  A bot that is switched off, missing in Streamer.bot, or that passes the message ("not mine") hands it to the next one in the fallback chain
//  (helper -> chat -> core, chat -> helper -> core). The game manager (core) only takes part through its own triggers.
//  Names / accounts / aliases: %AppData%\BVQ\bots.json. C# 7.3.
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
        r.Bots["chat"] = new PgBot { Title = "ChattyPinguino", Account = "chattypinguino", Sender = "none", Action = "PinguinoChat", Aliases = new List<string> { "chattypinguino", "pinguinochatty", "chattypinguin", "pinguinchatty", "chattypenguino", "chattypenguin", "penguinchatty", "chatty pinguino", "pinguino chatty", "chatty penguin", "chatty_pinguino", "pinguino_chatty", "pinguinochat", "pinguinchat", "penguinochat", "penguinchat", "chatpinguino", "chatpinguin", "pinguino chat", "chat pinguino", "pinguinochatbot", "pinguino", "pinguinos", "pinguin", "pinguinio", "pingino", "pinguinoo", "penguino", "penguinos", "penguins", "penguinoo" } };   // "pinguino(s)" / "penguins" (and typos) = the bots; plain "penguin" / "peng" / "peg" = Ivan, NOT a bot name
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
        if (PgSaidRecently(msg)) { CPH.LogInfo("[Bots] not sent, the same line was already said a moment ago: " + (msg.Length > 60 ? msg.Substring(0, 60) : msg)); return; }
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

    // NEVER SEND THE SAME LINE TWICE: every bot checks (and records) its line here before it speaks. The record is a Streamer.bot global, so the router, the helper,
    // the chat bot and the core all see each other's lines. Same text (case, spacing and invisible characters ignored) inside PgDupSeconds is dropped.
    const int PgDupSeconds = 30;
    bool PgSaidRecently(string text)
    {
        try
        {
            string n = System.Text.RegularExpressions.Regex.Replace((text ?? "").ToLowerInvariant(), "[​‍️]", "");
            n = System.Text.RegularExpressions.Regex.Replace(n, @"\s+", " ").Trim();
            if (n == "") return false;
            long now = PgNow(); var keep = new List<string>(); bool dup = false;
            string raw = CPH.GetGlobalVar<string>("pinguino.said.recent", false) ?? "";
            foreach (string row in raw.Split(new[] { '\n' }, StringSplitOptions.RemoveEmptyEntries))
            {
                int bar = row.IndexOf('|'); long t; if (bar < 1 || !long.TryParse(row.Substring(0, bar), out t) || now - t > PgDupSeconds) continue;
                if (row.Substring(bar + 1) == n) dup = true;
                keep.Add(row);
            }
            if (!dup) { keep.Add(now + "|" + n); }
            if (keep.Count > 40) keep.RemoveRange(0, keep.Count - 40);
            CPH.SetGlobalVar("pinguino.said.recent", string.Join("\n", keep), false);
            return dup;
        }
        catch (Exception) { return false; }
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
        catch (System.Net.WebException wex) when (wex.Status == System.Net.WebExceptionStatus.Timeout)
        { CPH.LogWarn("[Bots] sending as " + role + " timed out; it may have gone out, so it is NOT sent again"); return true; }
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
        new System.Text.RegularExpressions.Regex(@"\b(where|what('?s|\s+is))\b.{0,12}\b(am\s+i|my\s+(place|position|spot|pos|turn))\b.{0,18}\b(queue|line|list)?|\b(my\s+)?(position|spot|place)\s+(in\s+)?(the\s+)?(queue|line|list)\b|\bhow\s+(long|far|many)\b.{0,25}\b(until|till|before|to)\b.{0,15}\b(my\s+turn|play|i\s+play|im\s+up|i'?m\s+up)|\bam\s+i\s+(in|on)\s+(the\s+)?(queue|list)\b|\bwhen\s+(do|will|am)\s+(i|we)\b.{0,12}\b(play|up|next|go)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant),
        new System.Text.RegularExpressions.Regex(@"\b(how\s+(many|much)|what('?s|\s+are|\s+is)|how\s+(do|can)\s+(i|you|we)\s+(get|earn|check|see|spend|use)|check)\b.{0,25}\bpoints?\b|\bmy\s+points?\b|\bpoints?\s+(balance|total|leaderboard)\b|\brecycl(e|er|ing)\b|\b(15|fifteen)\s*-?\s*(min(ute)?s?)\b.{0,20}\b(timeout|time\s*out|custom)|\b(custom|customs?)\b.{0,20}\b(15|fifteen)\s*-?\s*min|\b(incomplete|unfinished|abandoned|crashed|didn'?t\s+finish)\b.{0,15}\b(games?|match(es)?)\b|\b(games?|match(es)?)\b.{0,15}\b(incomplete|unfinished|abandoned|didn'?t\s+count)\b|\b(wheel|spin(ning)?\s+the\s+wheel)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant)
    };
    static bool PgHelperTopic(string text)
    {
        if (string.IsNullOrEmpty(text)) return false;
        foreach (var rx in PgHelperTopics) if (rx.IsMatch(text)) return true;
        return false;
    }
    // <<PINGUINO-SHARED-END>>

    static readonly Regex RxYesNo = new Regex(@"^\s*@?\S*\s*(yes|yep|yeah|yea|ya|yup|y|ye|sure|ok|okay|k|please|pls|plz|do\s+it|go\s+ahead|confirm|no|nope|nah|n|cancel|nevermind|never\s*mind|nvm|no\s+thanks)\s*[.!?]*\s*$", RegexOptions.IgnoreCase);
    static readonly Regex RxPractical = new Regex(@"\b(queue|lobby|join|register|code|pass(word)?|play|custom|private|match|epic|game|pm|in\s+line)\b", RegexOptions.IgnoreCase);
    static readonly string[] OtherBots = { "nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "supibot", "botrix", "synchrabot", "soundalerts", "potatbotat", "rocketrankbot" };

    // used by the tests (tests\bots)
    public void PgSetHelperContextPublic(string login) { PgSetHelperContext(login); }
    public void SayPublic(string role, string text) { PgSay(role, text); }
    public string SpeakerPublic(string role) { return PgSpeaker(role); }

    string ArgS(string name) { object o; return CPH.TryGetArg(name, out o) && o != null ? (Convert.ToString(o) ?? "") : ""; }

    public bool Execute()
    {
        try { Route(); }
        catch (Exception ex) { CPH.LogError("[Router] failed: " + ex); }
        return true;
    }

    // Is this message about what the helper does / just said?
    bool RelatedToHelper(string text, List<string> mentioned)
    {
        if (mentioned.Contains("helper")) return true;
        if (RxYesNo.IsMatch(text)) return true;
        if (PgHelperTopic(text)) return true;
        string stripped = Regex.Replace(text, @"@\S+", "").Trim();
        return stripped.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries).Length <= 4;   // a short follow-up ("and then?", "where?")
    }

    static readonly Regex RxHelperKeys = new Regex(@"\bhow\b|\bjoin\b|\bip\b|!discord|\bminecraft\b|\b(lobby|code|pass(word)?|register|queue)\b", RegexOptions.IgnoreCase);

    // The order the bots are asked, for one message. Pure function of the message, the registry and the helper's open conversation.
    public List<string> Order(string text, string login, string replyTo)
    {
        text = text ?? "";
        var mentioned = PgMentionedRoles(text, true);
        string replyRole = PgRoleOfAccount(replyTo);
        bool mention = mentioned.Count > 0 || replyRole != "";
        bool ctx = PgHelperContext(login);
        string primary;
        if (text.StartsWith("!")) primary = "helper";
        else if (replyRole == "helper") primary = "helper";                       // an answer to what the helper said
        else if (replyRole == "chat") primary = "chat";
        else if (ctx && (!mention || RelatedToHelper(text, mentioned))) primary = "helper";
        else if (mention) primary = PgBestMention(text, true) == "helper" ? "helper" : "chat";   // the bot named gets it; PinguinoB0t and a bare "pinguino" go to the chatbot
        else primary = RxHelperKeys.IsMatch(text) ? "helper" : "chat";            // the helper only chimes in unprompted at its key words
        return PgChain(primary).Where(r => r == "helper" || r == "chat").ToList();   // the game manager is not a chat handler: it has its own triggers
    }

    // ---- correlation: one id per chat message, replayed ids are ignored, every decision goes to routing.log ----
    string MsgId(string login, string text)
    {
        string id = ArgS("msgId");
        if (id == "") id = ArgS("messageId");
        if (id == "") id = Math.Abs((login + "|" + text + "|" + (PgNow() / 2)).GetHashCode()).ToString();   // no id from Twitch: same text by the same user within ~2 s counts as a replay
        return Regex.Replace(id, "[^A-Za-z0-9_-]", "");
    }
    bool SeenBefore(string id)
    {
        try
        {
            long now = PgNow();
            string raw = CPH.GetGlobalVar<string>("pinguino.seen", false) ?? "";
            var keep = new List<string>();
            bool seen = false;
            foreach (string e in raw.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries))
            {
                int c = e.LastIndexOf(':'); long ts;
                if (c < 0 || !long.TryParse(e.Substring(c + 1), out ts) || now - ts > 60) continue;
                if (e.Substring(0, c) == id) seen = true;
                keep.Add(e);
            }
            if (!seen) keep.Add(id + ":" + now);
            if (keep.Count > 50) keep = keep.Skip(keep.Count - 50).ToList();
            CPH.SetGlobalVar("pinguino.seen", string.Join(";", keep), false);
            return seen;
        }
        catch (Exception) { return false; }
    }
    void RLog(string id, string role, string outcome, string why, long ms)
    {
        try
        {
            string f = Path.Combine(PgDirPath(), "routing.log");
            try { if (File.Exists(f) && new FileInfo(f).Length > 512 * 1024) File.Move(f, f + ".old"); } catch (Exception) { }
            File.AppendAllText(f, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "	" + id + "	" + role + "	" + outcome + "	" + why + "	" + ms + "ms" + Environment.NewLine);
        }
        catch (Exception) { }
    }

    void Route()
    {
        string text = ArgS("message").Trim();
        string login = (ArgS("userName") != "" ? ArgS("userName") : ArgS("user")).ToLower().Trim();
        string replyTo = ArgS("reply.userName") != "" ? ArgS("reply.userName") : ArgS("reply.userLogin");
        if (login == "") login = ArgS("login").ToLower();
        if (PgIsBotAccount(login)) return;                                          // our own bots' lines never start anything
        string id = MsgId(login, text);
        if (SeenBefore(id)) { RLog(id, "-", "duplicate", "msgId already routed", 0); return; }
        CPH.SetArgument("pinguinoRouted", true);
        CPH.SetArgument("pinguinoMsgId", id);

        List<string> order;
        if (text == "" || OtherBots.Contains(login)) order = new List<string> { "chat" };   // events and other bots' lines: only the chatbot reads them (events, announcements)
        else order = Order(text, login, replyTo);

        var deferred = new List<string>();
        for (int i = 0; i < order.Count; i++)
        {
            string role = order[i];
            var bot = PgBotOf(role);
            if (bot == null || !bot.Enabled) { CPH.LogInfo("[Router] " + PgTitle(role) + " is switched off, next."); RLog(id, role, "skip", "switched off", 0); continue; }
            if (!PgActionExists(bot.Action)) { CPH.LogWarn("[Router] Streamer.bot has no action '" + bot.Action + "' for " + PgTitle(role) + ", next."); RLog(id, role, "skip", "no action " + bot.Action, 0); continue; }
            PgSetResult("");
            var sw = System.Diagnostics.Stopwatch.StartNew();
            CPH.SetArgument("pinguinoRole", role);
            CPH.SetArgument("pinguinoNext", string.Join(",", order.Skip(i + 1)));
            bool ran = false;
            try { ran = CPH.RunAction(bot.Action, true); } catch (Exception ex) { CPH.LogWarn("[Router] " + PgTitle(role) + " failed: " + ex.Message); }
            string r = PgGetResult(); PgDropResult();
            RLog(id, role, !ran ? "failed" : r == "" ? "handled?" : r, !ran ? "RunAction false/threw" : r == "" ? "module reported nothing" : "", sw.ElapsedMilliseconds);
            if (ran && r == "defer") { deferred.Add(role); continue; }               // "this looks like the next bot's job": ask it first
            if (ran && r != "pass") return;                                         // handled (or an older module that does not report: it handled it)
        }
        // nobody took it: the bots that deferred get it back and must answer this time
        foreach (string role in deferred)
        {
            var bot = PgBotOf(role);
            PgSetResult("");
            CPH.SetArgument("pinguinoRole", role);
            CPH.SetArgument("pinguinoNext", "");
            CPH.SetArgument("pinguinoNoDefer", true);
            var sw2 = System.Diagnostics.Stopwatch.StartNew();
            try
            {
                bool ran2 = CPH.RunAction(bot.Action, true);
                string r2 = PgGetResult(); PgDropResult();
                RLog(id, role, !ran2 ? "failed" : "retry:" + (r2 == "" ? "handled?" : r2), "answered after defer", sw2.ElapsedMilliseconds);
                if (ran2 && r2 != "pass") return;
            }
            catch (Exception ex) { CPH.LogWarn("[Router] " + PgTitle(role) + " failed: " + ex.Message); RLog(id, role, "failed", ex.Message, sw2.ElapsedMilliseconds); }
        }
        RLog(id, "-", "unhandled", "no bot took it", 0);
    }
}
