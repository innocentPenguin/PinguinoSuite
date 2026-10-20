// ══════════════════════════════════════════════════════════════════════
//  PinguinoBot Core — Streamer.bot C# action (BVQ matchmaking engine)
//
//  ANNOTATION KEY (for Ivan + Circuit):
//    [FIX]     bug in the previous version, now corrected
//    [NEW]     new feature
//    [CIRCUIT] built to match Circuit's PinguinoBot 2.0 plan
//              (website + OBS read the same live data; "one action,
//               one synchronized result")
//    [NOTE]    design decision / something to know
//
//  Target: Streamer.bot (.NET Framework 4.8, C# 7.3). No new references
//  needed beyond Newtonsoft.Json, which the old version already used.
// ══════════════════════════════════════════════════════════════════════

// CODE MAP (search for the capital region titles / method names)
//   DATA MODELS ......... Player (Modes = per-category stats, Sr = Fortnite rating, Strikes), QueueEntry, MatchRecord, BalanceResult, Settings
//   PERSISTENCE ......... Save*/Load* (everything lives in %AppData%\BVQ)
//   LIVE STATE .......... PublishState -> BuildLiveState / BuildMatchObject (what the website + OBS overlays read; hold = winner animation delay)
//   ENTRY POINT ......... Execute -> Dispatch -> RunCommand (the big switch: ONE place that maps every !command to its Handle... method)
//   WEBSITE BRIDGE ..... HandleWebSync (every 3 s: website commands in, results + state + standings + matches + problems out)
//   QUEUE / TEAMS ....... AddToQueue, PullNextBatch, StartMatch (first KOTH game closes the queue), RecordResult, DoKothRotateAndBalance, HandleFinish
//   ACTIVITIES .......... HandleActivity (!activity [rl|fn] <name>), ActivityCounts / IsFortnite / CategoryFor, HandleKoth
//   OBS + TWITCH GAME ... ObsInvoke (reflection), SwitchObsScene, ObsGameSwitch, SwitchToGame, SetTwitchGame
//   STRIKES / PROBLEMS .. HandleStrike, ApplyLive, ReportProblem (-> red in the website log), HandleCheck
//   CHAT FORMAT ......... Say, SayColored, PostTeams (Blue / Orange as two plain messages)
// RL vs FN: Rocket League is the default game; IsFortnite() is true for boxfights / zonewars / fnviewers (SR instead of MMR, own stats).
// Tests: D:\PinguinoSuite\Tests (harness.cs compiles this file against stub.cs): powershell -ExecutionPolicy Bypass -File Tests\core\run-tests.ps1

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

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
        new System.Text.RegularExpressions.Regex(@"\b(where|what('?s|\s+is))\b.{0,12}\b(am\s+i|my\s+(place|position|spot|pos|turn))\b.{0,18}\b(queue|line|list)?|\b(my\s+)?(position|spot|place)\s+(in\s+)?(the\s+)?(queue|line|list)\b|\bhow\s+(long|far|many)\b.{0,25}\b(until|till|before|to)\b.{0,15}\b(my\s+turn|play|i\s+play|im\s+up|i'?m\s+up)|\bam\s+i\s+(in|on)\s+(the\s+)?(queue|list)\b|\bwhen\s+(do|will|am)\s+(i|we)\b.{0,12}\b(play|up|next|go)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant)
    };
    static bool PgHelperTopic(string text)
    {
        if (string.IsNullOrEmpty(text)) return false;
        foreach (var rx in PgHelperTopics) if (rx.IsMatch(text)) return true;
        return false;
    }
    // <<PINGUINO-SHARED-END>>

    // ══════════════════════════════════════════════════════════════
    //  DATA MODELS
    // ══════════════════════════════════════════════════════════════

    class Player
    {
        public string Username { get; set; }
        public string Platform { get; set; }
        public string GameId { get; set; }
        public string TwitchId { get; set; }   // [NEW] never changes, even when they rename on Twitch
        public int? PeakMmr { get; set; }
        public string MmrSource { get; set; } = "none";
        public long MmrLastUpdated { get; set; }

        // [NEW][CIRCUIT] Community progression (priority #4): wins, losses, points.
        public int Wins { get; set; }
        public int Losses { get; set; }
        public int Points { get; set; }

        // [NEW][WEB] Separate stats per game mode (Penguin League tabs): "2v2", "3v3", "dropshot", "rumble", "boxfights", "zonewars"...
        public Dictionary<string, ModeStat> Modes { get; set; }

        // [NEW][WEB] FORTNITE rating: SR (Skill Rating), our own system (Rocket League keeps MMR). Set with !setsr.
        public int? Sr { get; set; }
        public string SrSource { get; set; }               // "manual" (a mod) | "self" (the player)

        // [NEW][STRIKES] TEMPORARY strikes (orange on the site): a mod gives them (!strike), each one wears off after a day (DecayStrikes). Temporary + permanent is at most 3; 3 = can't join customs.
        public int Strikes { get; set; }
        // PERMANENT strikes (red on the site): !strike @user toxicity|slurs|perma. They never wear off; only !unstrike @user perma removes one.
        public int PermaStrikes { get; set; }
        public string PermaReason { get; set; }
        public long StrikeDecayAt { get; set; }            // unix s: when the oldest temporary strike was given / last wore off (a day after it, one goes)
    }

    class ObsSourceCfg
    {
        public string Label { get; set; }
        public string Scene { get; set; }     // "" = every scene in ObsScenes
        public string Source { get; set; }    // the source's exact name in OBS
    }

    class ModeStat
    {
        public int Wins { get; set; }
        public int Losses { get; set; }
        public int Points { get; set; }
    }

    class QueueEntry
    {
        public string Username { get; set; }
        public int Position { get; set; }
        public string Status { get; set; } = "waiting";   // "waiting" | "active"
        public int GamesPlayedSession { get; set; }
        public long JoinedAt { get; set; }
    }

    class TeamPlayer
    {
        public string Username { get; set; }
        public int Mmr { get; set; }
    }

    class BalanceResult
    {
        public List<TeamPlayer> Blue { get; set; }
        public List<TeamPlayer> Orange { get; set; }
        public int BlueAvgMmr { get; set; }
        public int OrangeAvgMmr { get; set; }
        public int MmrDiff { get; set; }
    }

    class MatchRecord
    {
        public int Id { get; set; }                       // [NEW] stable id the website/OBS can reference
        public string Format { get; set; }
        public string Mode { get; set; }                  // [NEW] balanced | random | picks
        public List<TeamPlayer> Blue { get; set; }
        public List<TeamPlayer> Orange { get; set; }
        public int BlueAvg { get; set; }
        public int OrangeAvg { get; set; }
        public int Diff { get; set; }
        public long CreatedAt { get; set; }
        public string Winner { get; set; }                // [NEW] null until a result is recorded
        public long? FinishedAt { get; set; }
        // [NEW][WEB] Needed to FIX a match later (change the winner / remove it) without breaking the stats:
        public string Activity { get; set; }              // competitive | casual | viewers, when the match was made
        public bool? Counted { get; set; }                // true = its result changed wins/losses/points
        public int? PtsWin { get; set; }                  // points given to the winners
        public int? PtsLoss { get; set; }                 // points given to the losers
        public string Category { get; set; }              // [NEW][WEB] standings tab it counts for: 2v2 | 3v3 | dropshot | rumble (old records: the format)
        public bool Group { get; set; }                   // [NEW][WEB] casual "group" style: shown as one grid, no teams
    }

    class MmrCacheEntry
    {
        public int PeakMmr { get; set; }
        public long FetchedAt { get; set; }
    }

    class BvqSettings
    {
        public string DefaultFormat { get; set; } = "3v3";
        public int DefaultMmr { get; set; } = 800;
        public int DefaultSr { get; set; } = 1000;          // [NEW][WEB] Fortnite SR for players nobody has rated yet
        public bool QueueOpen { get; set; }

        // [FIX] The old version hard-coded a TRN API key here. It was never
        // actually sent with any request, and it was published in the source.
        // Treat that key as leaked: revoke/rotate it on tracker.gg. If you need
        // one later, put it in settings.json on the stream PC only.
        public string TrnApiKey { get; set; } = "";

        // [NEW] Tracker Network blocks automated requests (Cloudflare), and its terms
        // don't allow scraping. Lookups are OFF by default so the bot doesn't stall
        // 2+ s per player on a request that always fails. Set true only if you get
        // official access (see CHANGES.md "Tracker MMR").
        public bool TrackerLookupEnabled { get; set; } = false;

        // [NEW][CIRCUIT] Priority #1: "Random / Streamer Picks" team modes.
        public string TeamMode { get; set; } = "balanced"; // balanced | random | picks

        // [NEW] King-of-the-hill: keep the winning team together as one side
        // (true KOTH) instead of re-mixing everyone (old behaviour = false).
        public bool KothKeepWinnersTogether { get; set; } = false;

        // [NEW] !reroll picks randomly among splits within this many avg MMR
        // of the best split, so rerolls actually produce different teams.
        public int RerollToleranceMmr { get; set; } = 50;

        // [NEW][CIRCUIT] Custom points, adjustable from settings.json (later: website).
        public int PointsWin { get; set; } = 3;
        public int PointsLoss { get; set; } = 1;

        // [NEW][WEB] Website bridge (innocentpenguin.com/customs). Leave WebSyncKey
        // empty to turn the bridge off. WebSyncKey must equal BOT_API_KEY in Railway.
        // [NOTE] It's a password: keep settings.json on the stream PC only.
        public string WebSyncUrl { get; set; } = "https://innocentpenguin.com";
        public string WebSyncKey { get; set; } = "";

        // [NEW][WEB] The streamer always goes to the FRONT of the queue (on !join,
        // and again after every match), so he's in every game while he's queued.
        public string StreamerName { get; set; } = "innocentpenguin_";

        // [NEW][WEB] The streamer PLAYS EVERY MATCH by default, even without typing
        // !join: making teams adds him automatically. "!streamer out" = sitting out
        // (his seat goes to the queue), "!streamer in" = back in. Also the mod-page switch.
        public bool StreamerPlaying { get; set; } = true;

        // [NEW][WEB] ONE activity at a time owns the queue:
        //   competitive = balanced teams + stats/points (the Penguin League)
        //   casual      = random teams, NO stats
        //   viewers     = "Playing with viewers": random teams, NO stats
        //   none        = nothing running, queue closed
        // Changing it (mod command !activity, or "Make active" on the website) clears
        // the queue and opens it for the new activity.
        public string Activity { get; set; } = "competitive";

        // [NEW][WEB] standard = normal Rocket League (counts under the format: 2v2, 3v3...); dropshot / rumble = special
        // game modes with their own Penguin League standings. Set with !gamemode (mods) or Master View.
        public string GameMode { get; set; } = "standard";
        // [NEW][WEB] How CASUAL customs show their players: "group" (one grid, no teams; the default) or "teams" (random Orange vs Blue).
        // Set with !casual group|teams (mods) or the Master View.
        public string CasualStyle { get; set; } = "teams";   // [CHANGE] always "teams" now

        // ── OBS control (through Streamer.bot's OBS connection) [NEW][OBS] ──
        // ObsScenes: label shown on the website / used in !scene  ->  the exact scene name in OBS.
        // ObsSources: switches for the website / !source. Scene "" = apply to every scene in ObsScenes.
        // ObsGameScenes: Twitch category (game) name -> scene label, used by the auto switch.
        // ObsAutoSwitch: when ON the scene follows the game (Twitch category changes, or a mod starts a Fortnite / Rocket League activity).
        public bool ObsEnabled { get; set; } = true;
        public bool ObsAutoSwitch { get; set; } = true;       // ON unless a mod turns it off (!obs auto off / the Master View checkbox)
        // [NEW] "!activity rl <activity>" / "!activity fn <activity>": the game prefix ALSO moves OBS to that game's scene and sets the Twitch category.
        // TwitchGameNames: prefix -> the exact Twitch category name. ActivitySetsGame: turn the category change off by setting this to false.
        public bool ActivitySetsGame { get; set; } = true;
        public Dictionary<string, string> TwitchGameNames { get; set; } = new Dictionary<string, string> { { "rl", "Rocket League" }, { "fn", "Fortnite" } };
        public bool ObsMigrated { get; set; }                  // one-time: old settings files get the new defaults (auto ON, no Starting Soon / Be Right Back)
        public Dictionary<string, string> ObsScenes { get; set; } = new Dictionary<string, string>
            { { "Rocket League", "Rocket League" }, { "Fortnite", "Fortnite" } };
        public List<ObsSourceCfg> ObsSources { get; set; } = new List<ObsSourceCfg>
            { new ObsSourceCfg { Label = "Queue overlay", Scene = "", Source = "PinguinoBot Queue" },
              new ObsSourceCfg { Label = "Players overlay", Scene = "", Source = "PinguinoBot Players" } };
        public Dictionary<string, string> ObsGameScenes { get; set; } = new Dictionary<string, string>
            { { "Rocket League", "Rocket League" }, { "Fortnite", "Fortnite" } };
        public bool ModesBackfilled { get; set; }          // one-time: build per-mode stats from the saved matches

        // [NEW][STRIKES] The stream going live takes one strike off everybody. WasLive/LastLiveSeen survive a bot restart,
        // and a stream that drops and comes back within 30 minutes does NOT count as a new stream.
        public bool WasLive { get; set; }
        public long LastLiveSeen { get; set; }

        // [FIX] Team lines are plain chat messages (🔷 Blue / 🔶 Orange). Twitch dropped /color in chat
        // messages, so the old "/color blue" was posted as text. No announcements (owner's choice).
        // ChatColors / BlueColor / OrangeColor are kept only so old settings.json files still load.
        // [NEW][KOTH] King of the hill. OFF (default): after "Orange wins / Blue wins" (!finish) everyone is out. ON: the winning team stays on.
        // ResultHoldSeconds: the website + OBS overlays keep showing the finished match (the winner animation) this long, the mod page moves on at once.
        public bool Koth { get; set; }
        public Dictionary<string, int> KothWins { get; set; } = new Dictionary<string, int>();   // [NEW][KOTH] the ACTIVITY leaderboard: wins in THIS King of the Hill session (reset when the activity starts)
        public bool KothStarted { get; set; }   // [NEW][KOTH] the King of the Hill ACTIVITY: true once its first game has been picked (that closes the queue)
        public int ResultHoldSeconds { get; set; } = 8;

        public bool ChatColors { get; set; } = true;
        public string BlueColor { get; set; } = "blue";
        public string OrangeColor { get; set; } = "orange";

        public int NextMatchId { get; set; } = 1;
        public long NextEventSeq { get; set; }

        // [NEW][OBS] Folder holding queue.html / players.html; live_state.js is written here.
        public string OverlayDir { get; set; } = @"D:\PinguinoSuite\PinguinoB0t\overlays";
    }

    class LastBalanceData
    {
        public int MatchId { get; set; }
        public List<TeamPlayer> Players { get; set; }
        public string Format { get; set; }
        public BalanceResult Result { get; set; }
        public bool ResultRecorded { get; set; }          // [NEW] prevents double-scoring a match
        public string Winner { get; set; }                // [NEW] "blue" | "orange" once finalized
    }

    class TrnResult
    {
        public bool? ProfileFound { get; set; }  // null = API error, true = found, false = not found
        public int? Mmr { get; set; }
    }

    // [NEW][CIRCUIT] One event = one synchronized output. Every state change
    // bumps Seq; OBS/website poll live_state.json and animate when Seq changes.
    class LiveEvent
    {
        public long Seq { get; set; }
        public string Type { get; set; }   // queue_open | queue_close | queue_update | teams_selected | match_result | ...
        public string Detail { get; set; }
        public long At { get; set; }
    }

    // ══════════════════════════════════════════════════════════════
    //  STATIC STATE
    // ══════════════════════════════════════════════════════════════

    // [FIX] Streamer.bot can run actions concurrently (two people typing !join
    // at once). Every command now runs under this lock so the queue can't corrupt.
    static readonly object _sync = new object();

    static bool _initialized = false;
    static Dictionary<string, Player> _players;
    static List<QueueEntry> _queue;
    static List<MatchRecord> _matches;
    static Dictionary<string, MmrCacheEntry> _mmrCache;
    static BvqSettings _settings;
    static LastBalanceData _lastBalance;
    static List<string> _problems = new List<string>();                  // [NEW][CHECK] things that went wrong, sent to the website log (shown in RED)
    static Dictionary<string, long> _problemSeen = new Dictionary<string, long>();
    static DateTime _lastWebOk = DateTime.MinValue;                      // last time the website answered
    static string _cmdUser = "";    // who is running the current command (for "King of the Hill is starting, picked by ...")
    static object _holdMatch;     // [NEW][KOTH] the finished match the website / OBS keep showing for a few seconds after !finish
    static long _holdUntil;
    static LiveEvent _lastEvent;
    static readonly List<LiveEvent> _recentEvents = new List<LiveEvent>();
    static DateTime _lastTrnRequest = DateTime.MinValue;
    static DateTime _trnPausedUntil = DateTime.MinValue;
    static string _dataDir;
    static readonly Random _rng = new Random();   // [FIX] one shared Random (new Random() per call repeats seeds)

    // ══════════════════════════════════════════════════════════════
    //  CONSTANTS
    // ══════════════════════════════════════════════════════════════

    static readonly string[] ValidFormats = { "1v1", "2v2", "3v3", "4v4" };
    static readonly string[] ValidModes = { "balanced", "random", "picks" };

    static readonly Dictionary<string, int> RankMap = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
    {
        {"bronze", 200}, {"silver", 400}, {"gold", 600}, {"platinum", 800}, {"plat", 800},
        {"diamond", 1000}, {"champ", 1200}, {"champion", 1200},
        {"gc", 1500}, {"grandchamp", 1500}, {"ssl", 1900}, {"supersonic", 1900},
        {"b1", 100}, {"b2", 200}, {"b3", 300},
        {"s1", 300}, {"s2", 400}, {"s3", 500},
        {"g1", 500}, {"g2", 600}, {"g3", 700},
        {"p1", 700}, {"p2", 800}, {"p3", 900},
        {"plat1", 700}, {"plat2", 800}, {"plat3", 900},
        {"d1", 900}, {"d2", 1000}, {"d3", 1100},
        {"diamond1", 900}, {"diamond2", 1000}, {"diamond3", 1100},
        {"c1", 1100}, {"c2", 1300}, {"c3", 1400},
        {"champ1", 1100}, {"champ2", 1300}, {"champ3", 1400},
        {"gc1", 1500}, {"gc2", 1600}, {"gc3", 1700},
    };

    static readonly Dictionary<string, int> FormatTeamSize = new Dictionary<string, int>
    {
        {"1v1", 1}, {"2v2", 2}, {"3v3", 3}, {"4v4", 4}
    };

    // [NEW] Which TRN playlist to read MMR from for each format. The old code
    // always used 2v2. 4v4 has no ranked playlist, so it uses 3v3. If the
    // preferred playlist has no data we fall back to the player's best one.
    static readonly Dictionary<string, string> FormatPlaylist = new Dictionary<string, string>
    {
        {"2v2", "Ranked Doubles 2v2"}, {"3v3", "Ranked Standard 3v3"}, {"4v4", "Ranked Standard 3v3"}
    };

    // ══════════════════════════════════════════════════════════════
    //  PERSISTENCE
    // ══════════════════════════════════════════════════════════════

    void EnsureInitialized()
    {
        if (_initialized) return;

        // PINGUINO_DATA_DIR (alias BVQ_DATA_DIR) is only used by automated tests; normally this is %AppData%\BVQ.
        _dataDir = PgEnvDir() ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "BVQ"
        );
        Directory.CreateDirectory(_dataDir);

        _players = LoadJson<Dictionary<string, Player>>("players.json")
                   ?? new Dictionary<string, Player>();
        _queue = LoadJson<List<QueueEntry>>("queue.json")
                 ?? new List<QueueEntry>();
        _matches = LoadJson<List<MatchRecord>>("matches.json")
                   ?? new List<MatchRecord>();
        _mmrCache = LoadJson<Dictionary<string, MmrCacheEntry>>("mmr_cache.json")
                    ?? new Dictionary<string, MmrCacheEntry>();
        _settings = LoadJson<BvqSettings>("settings.json")
                    ?? new BvqSettings();

        // [FIX] The current lobby used to live only in memory, so a Streamer.bot
        // restart mid-match made !lobby / !reroll / !next blue forget the teams.
        _lastBalance = LoadJson<LastBalanceData>("current_match.json");

        // [NEW] Clean out junk players left by old mistyped commands
        // (e.g. "!register {your epic}" made a player called "{").
        // Real names are letters/numbers/_/- (any language); anything else goes.
        var junk = _players.Keys.Where(k => string.IsNullOrWhiteSpace(k) || System.Text.RegularExpressions.Regex.IsMatch(k, @"^practice\d{2,3}$") ||
                       k.Any(ch => !(char.IsLetterOrDigit(ch) || ch == '_' || ch == '-'))).ToList();
        if (junk.Count > 0)
        {
            foreach (var k in junk) { _players.Remove(k); _queue.RemoveAll(e => e.Username == k); }
            SavePlayers(); SaveQueue();
            CPH.LogInfo("[BVQ] Removed " + junk.Count + " junk player(s): " + string.Join(", ", junk));
        }

        _wheel = LoadJson<WheelSession>("wheel_session.json");   // [NEW][WHEEL]
        if (Environment.GetEnvironmentVariable("BVQ_WHEEL_FAST") == "1") { _wheelStepMs = 1; _wheelLeadMs = 0; _wheelGapMs = 0; _wheelPerTick = 1000; }
        BackfillModes();   // [NEW][WEB] one-time: per-mode stats from saved matches
        MigrateObsDefaults();

        _initialized = true;
        CPH.LogInfo("[BVQ] Initialized. Data dir: " + _dataDir);
    }

    T LoadJson<T>(string filename) where T : class
    {
        string path = Path.Combine(_dataDir, filename);
        if (!File.Exists(path)) return null;
        try
        {
            return JsonConvert.DeserializeObject<T>(File.ReadAllText(path));
        }
        catch (Exception ex)
        {
            CPH.LogWarn("[BVQ] Failed to load " + filename + ": " + ex.Message);
            return null;
        }
    }

    void SaveJson(string filename, object data)
    {
        string path = Path.Combine(_dataDir, filename);
        string tmp = path + ".tmp";
        try
        {
            // [FIX] Write to a temp file then swap, so a crash or the website
            // reading mid-write never sees a half-written (corrupt) JSON file.
            string json = JsonConvert.SerializeObject(data, Formatting.Indented);
            File.WriteAllText(tmp, json);
            try
            {
                if (File.Exists(path)) File.Replace(tmp, path, null);
                else File.Move(tmp, path);
            }
            catch (IOException)
            {
                // [FIX] If OBS/website has the file open, the swap can fail.
                // Fall back to a plain write so the save is never lost on stream.
                File.WriteAllText(path, json);
                try { File.Delete(tmp); } catch { }
            }
        }
        catch (Exception ex)
        {
            CPH.LogWarn("[BVQ] Failed to save " + filename + ": " + ex.Message);
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  PRACTICE MODE  [NEW][PRACTICE]
    //  !practice on [N] | add [N] | off | status   (mods).  Fake players practice01, practice02 ... fill the queue (and the wheel sign-ups while they are open),
    //  so matchmaking, !next, teams, the overlays and the tournament wheel can be rehearsed. They live in memory ONLY:
    //  never in players.json / queue.json / matches.json / current_match.json / wheel_session.json, never in stats, points, King of the Hill wins,
    //  the standings or match history pushed to the website. State/wheel pushes mark them: state.practice, queue[].practice, currentMatch.blue/orange[].Practice,
    //  wheel.practice, wheel.entrants[].practice. A restart (or !practice off) removes them; "off" also restores the real wheel sign-ups.
    // ══════════════════════════════════════════════════════════════
    static readonly HashSet<string> _practice = new HashSet<string>();
    static bool _practiceOn;
    bool IsPractice(string login) { return _practice.Count > 0 && login != null && _practice.Contains(login); }
    bool IsPracticeMatch(MatchRecord m)
    {
        return _practice.Count > 0 && m != null && ((m.Blue ?? new List<TeamPlayer>()).Concat(m.Orange ?? new List<TeamPlayer>()).Any(tp => IsPractice(tp.Username)));
    }
    bool IsPracticeLast()
    {
        return _practice.Count > 0 && _lastBalance != null && _lastBalance.Result != null && _lastBalance.Result.Blue.Concat(_lastBalance.Result.Orange).Any(tp => IsPractice(tp.Username));
    }

    int PracticeAdd(int n)
    {
        int added = 0;
        for (int i = 1; i <= 99 && added < n && _practice.Count < 40; i++)
        {
            string login = "practice" + i.ToString("00");
            if (_practice.Contains(login) || _players.ContainsKey(login)) continue;
            int mmr = 450 + (i * 137) % 1100;
            _players[login] = new Player { Username = login, GameId = login, MmrSource = "manual", PeakMmr = mmr, MmrLastUpdated = Now() };
            _practice.Add(login);
            AddToQueue(login);
            if (_wheel != null && _wheel.Status == "open" && !_wheel.Entrants.Any(e => e.Login == login))
                _wheel.Entrants.Add(new WheelEntrant { Id = "practice-" + i.ToString("00"), Login = login, Name = "Practice" + i.ToString("00"), Epic = login, Mmr = mmr, Practice = true });
            added++;
        }
        return added;
    }

    void PracticeClear()
    {
        bool hadWheel = _wheel != null && _wheel.Entrants.Any(e => e.Practice);
        bool hadMatch = IsPracticeLast();
        foreach (var login in _practice.ToList()) { _players.Remove(login); _queue.RemoveAll(e => e.Username == login); }
        _matches.RemoveAll(IsPracticeMatch);
        _practice.Clear(); _practiceOn = false;
        if (hadMatch) { _lastBalance = LoadJson<LastBalanceData>("current_match.json"); _holdMatch = null; }
        if (hadWheel) { _wheel = LoadJson<WheelSession>("wheel_session.json"); _wheelDirty = true; }   // back to the real sign-ups (practice entrants were never saved)
        _standingsDirty = true; _matchesDirty = true;
        SavePlayers(); SaveQueue(); SaveMatches();
    }

    bool HandlePractice(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can use !practice."); return true; }
        string[] parts = (input ?? "").Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        string sub = parts.Length > 0 ? parts[0].ToLower() : "status";
        int n = 8;
        if (parts.Length > 1) { int v; if (int.TryParse(parts[1], out v)) n = Math.Max(1, Math.Min(40, v)); }
        switch (sub)
        {
            case "on":
            case "add":
            case "start":
            {
                _practiceOn = true;
                int a = PracticeAdd(n);
                SaveQueue(); SavePlayers();
                if (_wheel != null) _wheelDirty = true;
                PublishState("queue_update", "practice players added");
                Say("PRACTICE mode on: " + a + " practice player(s) added (" + _practice.Count + " now" + (_wheel != null && _wheel.Status == "open" ? ", also in the tournament sign-ups" : "") +
                    "). Nothing from practice is saved or counted. !practice off ends it.");
                return true;
            }
            case "off":
            case "clear":
            case "stop":
            {
                int had = _practice.Count;
                PracticeClear();
                PublishState("queue_update", "practice mode off");
                Say("PRACTICE mode off: " + had + " practice player(s) removed" + "; nothing was saved.");
                return true;
            }
            default:
                Say("Practice mode is " + (_practiceOn ? "ON (" + _practice.Count + " practice players)" : "off") + ". !practice on [N] | add [N] | off");
                return true;
        }
    }

    // ══════════════════════════════════════════════════════════════
    //  TOURNAMENT WHEEL  [NEW][WHEEL]
    //  Viewers type !me to sign up; mods run !wheel (or the website's /mod/wheel
    //  page, which queues the same commands). THIS code does the one and only
    //  draw: a seeded Fisher-Yates shuffle (True random) or an MMR balancer
    //  (Balanced, shown as "Rigged / Balanced by MMR"). The result is COMMITTED
    //  (draw id + reveal order + start time); the website and the OBS overlay
    //  only replay it, so a reload never changes it. The whole session is pushed
    //  to POST /api/bot/wheel on every change, so the site keeps showing it when
    //  this PC is off. The seed is never sent to the website.
    //    !me                          join (while sign-ups are open)
    //    !wheel new | open | close | draw | undo | announce | retry | reset | end
    //    !wheel mode random|balanced      !wheel size 1-4
    //    !wheel odd waitlist|trio|partial|hold|mod
    //    !wheel eligibility all|subs
    //    !wheel remove <login>            !wheel mmr <login> <number>
    // ══════════════════════════════════════════════════════════════

    class WheelEntrant
    {
        public string Id;            // Twitch id (the unique key); the login when Twitch gave none
        public string Login;
        public string Name;          // what the overlay shows
        public string Epic;
        public int? Mmr;             // known MMR (mod override or the player's saved one); null = unknown
        public int? MmrOverride;     // set with !wheel mmr
        public bool Flagged;         // unknown MMR: the lobby median was used in Balanced mode
        public bool Wait;            // left over after the draw
        public bool Practice;        // a practice (fake) player: memory only, never saved, flagged for the site
    }
    class WheelTeam
    {
        public int N;
        public List<string> Members = new List<string>();
        public int? Avg;
        public bool Partial;
        public bool Announced;
    }
    class WheelStep { public int Team; public string Name; }
    class WheelDraw
    {
        public string Id;
        public long StartedAt;       // ms since 1970 (UTC): the overlay starts the reveal here
        public int StepMs;
        public List<WheelStep> Steps = new List<WheelStep>();
        public int Revealed;         // manual spin: how many picks the mod has revealed so far (the site sends !wheel spin N)
        public long SpunAt;          // ms since 1970: when Revealed last grew (the overlay spin takes ~8 s)
    }
    class WheelMsg { public string Text; public bool Sent; public int Team; public long Due; }   // Due (ms since 1970): do not send before this (manual spin: after the overlay landed)
    class WheelSession
    {
        public string Id;
        public string Status = "closed";       // closed | open | drawing | drawn
        public string Mode = "random";         // random | balanced
        public int TeamSize = 2;
        public string OddPolicy = "waitlist";  // waitlist | trio | partial | hold | mod
        public string Eligibility = "all";     // all | subs
        public string Seed = "";               // private: never pushed
        public int DrawCount;
        public List<WheelEntrant> Entrants = new List<WheelEntrant>();
        public List<WheelTeam> Teams = new List<WheelTeam>();
        public WheelDraw Draw;
        public List<string> Waitlist = new List<string>();
        public List<WheelMsg> Msgs = new List<WheelMsg>();
        public string AnnState = "idle";       // idle | sending | done | failed
    }

    // splitmix64 over a SHA-256 of the seed: the same seed always gives the same draw.
    class WheelRng
    {
        ulong _s;
        public WheelRng(string seed)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create())
                _s = BitConverter.ToUInt64(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(seed ?? "")), 0);
        }
        public ulong Next()
        {
            unchecked
            {
                _s += 0x9E3779B97F4A7C15UL;
                ulong z = _s;
                z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
                z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
                return z ^ (z >> 31);
            }
        }
        public int Below(int n)   // 0..n-1 without modulo bias
        {
            ulong lim = ulong.MaxValue - (ulong.MaxValue % (ulong)n);
            ulong r;
            do { r = Next(); } while (r >= lim);
            return (int)(r % (ulong)n);
        }
    }

    static WheelSession _wheel;
    static bool _wheelDirty = true;
    static DateTime _lastWheelPush = DateTime.MinValue;
    static string _cmdUserId = "", _cmdDisplay = "";   // who typed the current chat command (Twitch id / display name)
    static bool _cmdSub;                               // ...and whether they are a subscriber
    static readonly Dictionary<string, DateTime> _wheelSaid = new Dictionary<string, DateTime>();
    static int _wheelStepMs = 1500, _wheelLeadMs = 2500, _wheelGapMs = 1200, _wheelPerTick = 3;

    static long NowMs() { return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(); }

    static string WheelNewSeed()
    {
        var b = new byte[16];
        using (var g = System.Security.Cryptography.RandomNumberGenerator.Create()) g.GetBytes(b);
        return BitConverter.ToString(b).Replace("-", "").ToLower();
    }

    static void WheelShuffle<T>(List<T> l, WheelRng rng)   // Fisher-Yates
    {
        for (int i = l.Count - 1; i > 0; i--)
        {
            int j = rng.Below(i + 1);
            T t = l[i]; l[i] = l[j]; l[j] = t;
        }
    }

    static string WheelClean(string s, string fallback)
    {
        var sb = new System.Text.StringBuilder();
        foreach (char c in s ?? "") { if (c == '<' || c == '>' || char.IsControl(c)) continue; sb.Append(c); }
        string r = sb.ToString().Trim();
        if (r.Length > 40) r = r.Substring(0, 40);
        return r.Length == 0 ? fallback : r;
    }

    void WheelSave()
    {
        _wheelDirty = true;
        if (_wheel != null && _wheel.Entrants.Any(e => e.Practice))
        {
            // practice entrants never reach the disk: while sign-ups are open the REAL sign-ups are still saved, after a (practice) draw nothing is
            if (_wheel.Status == "open" && _wheel.Draw == null)
            {
                var real = JObject.FromObject(_wheel);
                var arr = (JArray)real["Entrants"];
                foreach (var t in arr.OfType<JObject>().Where(t => (bool?)t["Practice"] == true).ToList()) t.Remove();
                SaveJson("wheel_session.json", real);
            }
            return;
        }
        SaveJson("wheel_session.json", _wheel);
    }

    // A reply to a viewer, at most once per 30 s each, so a spammed !me can't flood chat.
    void WheelSayOnce(string user, string msg)
    {
        if (_wheelSaid.Count > 2000) _wheelSaid.Clear();
        DateTime t;
        if (_wheelSaid.TryGetValue(user, out t) && (DateTime.UtcNow - t).TotalSeconds < 30) return;
        _wheelSaid[user] = DateTime.UtcNow;
        if (_quiet) { if (_capture != null) _capture.Add(msg); return; }   // a website-only join: the reply goes back to the site, not into chat
        Say(msg);
    }

    // [NEW][STRIKES] Same rule as customs: 3 strikes = no joining (the streamer is exempt). Strikes live in _players.
    bool WheelStruck(string login)
    {
        Player sp;
        return !IsStreamer(login) && _players.TryGetValue(login, out sp) && StrikeTotal(sp) >= MaxStrikes;
    }

    bool HandleMe(string user, bool isPrivileged)
    {
        if (string.IsNullOrEmpty(user)) return true;
        if (_wheel == null || _wheel.Status != "open") { WheelSayOnce(user, "@" + user + " sign-ups for the tournament are closed."); return true; }
        if (_wheel.Eligibility == "subs" && !_cmdSub && !isPrivileged) { WheelSayOnce(user, "@" + user + " tournament sign-ups are for subscribers right now."); return true; }
        if (WheelStruck(user)) { WheelSayOnce(user, "@" + user + " you have " + MaxStrikes + " strikes, so you can't join the tournament right now. A temporary strike wears off after a day; permanent ones stay."); return true; }
        string id = !string.IsNullOrEmpty(_cmdUserId) ? _cmdUserId : user;
        if (_wheel.Entrants.Any(e => e.Id == id || e.Login == user)) { WheelSayOnce(user, "@" + user + " you are already in the tournament."); return true; }
        if (_wheel.Entrants.Count >= 500) { WheelSayOnce(user, "@" + user + " the tournament is full."); return true; }
        var en = new WheelEntrant { Id = id, Login = user, Name = WheelClean(_cmdDisplay, user) };
        Player p;
        if (_players.TryGetValue(user, out p))
        {
            en.Epic = p.GameId ?? "";
            if (p.PeakMmr.HasValue) en.Mmr = p.PeakMmr.Value;
        }
        en.Flagged = !en.Mmr.HasValue;
        _wheel.Entrants.Add(en);
        WheelSave();
        string joined = "@" + user + " you're in the tournament! (" + _wheel.Entrants.Count + " joined)";
        if (_quiet) { if (_capture != null) _capture.Add(joined); } else Say(joined);
        return true;
    }

    bool HandleWheel(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { WheelSayOnce(user, "@" + user + " only mods can run !wheel."); return true; }
        string[] parts = (input ?? "").Trim().Split(new[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
        string sub = parts.Length > 0 ? parts[0].ToLower() : "";
        string arg = parts.Length > 1 ? parts[1].Trim().ToLower() : "";
        var w = _wheel;
        if (w == null && sub != "new" && sub != "open" && sub != "tick")
        {
            Say("There is no tournament wheel session. Type !wheel new.");
            return true;
        }
        bool locked = w != null && (w.Status == "drawing" || w.Status == "drawn");
        switch (sub)
        {
            case "new":
                if (w != null) { Say("A wheel session already exists. Use !wheel end first, or !wheel reset to redo the teams."); return true; }
                _wheel = new WheelSession { Id = "w" + Now(), Seed = WheelNewSeed() };
                WheelSave();
                Say("Tournament wheel ready. Type !wheel open to start sign-ups.");
                return true;
            case "open":
                if (w == null) { _wheel = w = new WheelSession { Id = "w" + Now(), Seed = WheelNewSeed() }; }
                if (w.Status == "open") { Say("Sign-ups are already open."); return true; }
                if (locked) { Say("Teams are already drawn. Use !wheel reset to sign up again."); return true; }
                w.Status = "open";
                WheelSave();
                Say("Tournament sign-ups are OPEN! Type !me to join.");
                return true;
            case "close":
                if (w.Status != "open") { Say("Sign-ups are not open."); return true; }
                w.Status = "closed";
                WheelSave();
                Say("Tournament sign-ups are closed (" + w.Entrants.Count + " joined).");
                return true;
            case "mode":
                if (arg != "random" && arg != "balanced") { Say("Usage: !wheel mode random|balanced"); return true; }
                if (locked) { Say("Teams are already drawn. Use !wheel undo or !wheel reset first."); return true; }
                w.Mode = arg; WheelSave();
                Say(arg == "balanced" ? "Wheel mode: Rigged / Balanced by MMR." : "Wheel mode: True random.");
                return true;
            case "size":
                int sz;
                if (!int.TryParse(arg, out sz) || sz < 1 || sz > 4) { Say("Usage: !wheel size 1-4"); return true; }
                if (locked) { Say("Teams are already drawn. Use !wheel undo or !wheel reset first."); return true; }
                w.TeamSize = sz; WheelSave();
                Say("Team size: " + sz + ".");
                return true;
            case "odd":
                if (new[] { "waitlist", "trio", "partial", "hold", "mod" }.All(x => x != arg)) { Say("Usage: !wheel odd waitlist|trio|partial|hold|mod"); return true; }
                if (locked) { Say("Teams are already drawn. Use !wheel undo or !wheel reset first."); return true; }
                w.OddPolicy = arg; WheelSave();
                Say("Odd player out: " + arg + ".");
                return true;
            case "eligibility":
                if (arg != "all" && arg != "subs") { Say("Usage: !wheel eligibility all|subs"); return true; }
                w.Eligibility = arg; WheelSave();
                Say(arg == "subs" ? "Tournament sign-ups: subscribers only." : "Tournament sign-ups: everyone.");
                return true;
            case "remove":
                {
                    if (locked) { Say("Teams are already drawn. Use !wheel undo or !wheel reset first."); return true; }
                    string who = arg.TrimStart('@');
                    int n = w.Entrants.RemoveAll(e => e.Login == who);
                    if (n == 0) { Say(who + " is not signed up."); return true; }
                    WheelSave();
                    Say("Removed " + who + " from the tournament.");
                    return true;
                }
            case "mmr":
                {
                    if (locked) { Say("Teams are already drawn. Use !wheel undo or !wheel reset first."); return true; }
                    string[] a = arg.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                    int v;
                    if (a.Length != 2 || !int.TryParse(a[1], out v) || v < 0 || v > 5000) { Say("Usage: !wheel mmr <login> <0-5000>"); return true; }
                    string who = a[0].TrimStart('@');
                    var en = w.Entrants.FirstOrDefault(e => e.Login == who);
                    if (en == null) { Say(who + " is not signed up."); return true; }
                    en.MmrOverride = v; en.Mmr = v; en.Flagged = false;
                    WheelSave();
                    Say("Wheel MMR for " + who + " set to " + v + ".");
                    return true;
                }
            case "draw": WheelDoDraw(); return true;
            case "spin": WheelSpin(w, arg); return true;
            case "undo":
                if (!locked) { Say("Nothing to undo."); return true; }
                if (w.Msgs.Any(m => m.Sent)) { Say("The teams were already announced in chat. Use !wheel reset if you really want to redo them."); return true; }
                WheelClearDraw(w);
                Say("Draw undone. Sign-ups are still there.");
                return true;
            case "reset":
                if (!locked) { Say("Nothing to reset."); return true; }
                WheelClearDraw(w);
                Say("Teams reset. Sign-ups are still there.");
                return true;
            case "end":
                _wheel = null;
                WheelSave();
                Say("Tournament wheel session ended.");
                return true;
            case "announce":
                if (w.Status != "drawn" || w.Teams.Count == 0) { Say(w.Status == "drawing" ? "Wait for the reveal to finish, then announce." : "No teams to announce yet."); return true; }
                WheelQueueAnnounce(w);
                WheelPump();
                return true;
            case "retry":
                if (w.AnnState != "failed") { Say("No failed announcement to retry."); return true; }
                w.AnnState = "sending";
                WheelSave();
                WheelPump();
                return true;
            case "tick": WheelPump(); return true;
            default:
                Say("Wheel: !wheel new|open|close|draw|spin [n]|undo|announce|retry|reset|end, mode, size, odd, eligibility, remove <login>, mmr <login> <n>");
                return true;
        }
    }

    void WheelClearDraw(WheelSession w)
    {
        w.Teams.Clear(); w.Waitlist.Clear(); w.Msgs.Clear(); w.Draw = null; w.AnnState = "idle"; w.Status = "closed";
        foreach (var e in w.Entrants) e.Wait = false;
        WheelSave();
    }

    // The ONE draw. Everything random comes from a seed made right now (kept private).
    void WheelDoDraw()
    {
        var w = _wheel;
        if (w.Status == "drawing" || w.Status == "drawn") { Say("The teams are already drawn. Use !wheel undo to draw again."); return; }
        int size = w.TeamSize, total = w.Entrants.Count;
        if (total < size) { Say("Need at least " + size + " player(s) to draw; " + total + " signed up."); return; }
        int r = total % size, k = total / size;
        if (r > 0 && w.OddPolicy == "hold")
        {
            Say("Odd number of players (" + total + "). Need " + (size - r) + " more (or " + r + " fewer), or change it with !wheel odd.");
            return;
        }

        var struck = w.Entrants.Where(e => WheelStruck(e.Login)).ToList();
        if (struck.Count > 0)
        {
            foreach (var e in struck) w.Entrants.Remove(e);
            Say("Removed from the tournament (" + MaxStrikes + " strikes): " + string.Join(", ", struck.Select(e => e.Name)) + ". Run !wheel draw again.");
            WheelSave();
            return;
        }
        w.Seed = WheelNewSeed();
        var rng = new WheelRng(w.Seed);
        w.DrawCount++;
        foreach (var e in w.Entrants) e.Wait = false;

        // 1) Seeded shuffle: it decides the order AND who is left over.
        var order = w.Entrants.ToList();
        WheelShuffle(order, rng);
        var left = new List<WheelEntrant>();
        var pool = order;
        var sizes = new List<int>();
        for (int i = 0; i < k; i++) sizes.Add(size);
        if (r > 0)
        {
            if (w.OddPolicy == "partial") sizes.Add(r);
            else if (w.OddPolicy == "trio" && r <= k) { for (int i = 0; i < r; i++) sizes[i]++; }
            else if (w.OddPolicy == "trio") sizes.Add(r);   // not enough teams to spread the extras
            else { left = order.Skip(order.Count - r).ToList(); pool = order.Take(order.Count - r).ToList(); }   // waitlist | mod
        }

        // 2) Teams.
        var groups = new List<List<WheelEntrant>>();
        Dictionary<WheelEntrant, int> val = null;
        if (w.Mode == "balanced")
        {
            val = WheelMmrValues(pool, size);
            groups = WheelBalance(pool, sizes.ToArray(), val, rng);
            WheelShuffle(groups, rng);   // don't always list the strongest team first
        }
        else
        {
            int at = 0;
            foreach (int s in sizes) { groups.Add(pool.Skip(at).Take(s).ToList()); at += s; }
        }

        w.Teams = new List<WheelTeam>();
        var steps = new List<WheelStep>();
        for (int i = 0; i < groups.Count; i++)
        {
            var t = new WheelTeam { N = i + 1, Partial = groups[i].Count < size };
            foreach (var e in groups[i]) { t.Members.Add(e.Name); steps.Add(new WheelStep { Team = t.N, Name = e.Name }); }
            if (val != null) t.Avg = (int)Math.Round(groups[i].Average(e => (double)val[e]));
            w.Teams.Add(t);
        }
        // Reveal order: random mode shows the shuffle itself; balanced mode shuffles the reveal so the order gives nothing away.
        if (w.Mode == "balanced") WheelShuffle(steps, rng);

        w.Waitlist = left.Select(e => e.Name).ToList();
        foreach (var e in left) e.Wait = true;
        w.Draw = new WheelDraw { Id = w.Id + "-" + w.DrawCount, StartedAt = NowMs() + _wheelLeadMs, StepMs = _wheelStepMs, Steps = steps };
        w.Msgs.Clear(); w.AnnState = "idle";
        w.Status = "drawing";
        WheelSave();
        Say("Drawing the tournament teams! Watch the stream.");
    }

    // MMR per entrant for Balanced mode. Unknown MMR = the lobby median (and the entrant is flagged "?").
    Dictionary<WheelEntrant, int> WheelMmrValues(List<WheelEntrant> pool, int size)
    {
        string fmt = size <= 2 ? "2v2" : "3v3";
        foreach (var e in pool)
        {
            if (e.MmrOverride.HasValue) { e.Mmr = e.MmrOverride; continue; }
            Player p;
            if (_players.TryGetValue(e.Login, out p) && (p.PeakMmr.HasValue || !string.IsNullOrEmpty(p.GameId)))
            {
                try { ResolveMmr(e.Login, fmt); } catch (Exception) { }
                if (p.PeakMmr.HasValue) e.Mmr = p.PeakMmr.Value;
            }
        }
        var known = pool.Where(e => e.Mmr.HasValue).Select(e => e.Mmr.Value).OrderBy(x => x).ToList();
        int med = known.Count == 0 ? _settings.DefaultMmr
                : known.Count % 2 == 1 ? known[known.Count / 2]
                : (known[known.Count / 2 - 1] + known[known.Count / 2]) / 2;
        var val = new Dictionary<WheelEntrant, int>();
        foreach (var e in pool) { e.Flagged = !e.Mmr.HasValue; val[e] = e.Mmr ?? med; }
        return val;
    }

    // Splits the pool into teams with (near) equal average MMR.
    List<List<WheelEntrant>> WheelBalance(List<WheelEntrant> pool, int[] sizes, Dictionary<WheelEntrant, int> val, WheelRng rng)
    {
        int T = sizes.Length;
        var teams = new List<List<WheelEntrant>>();
        for (int i = 0; i < T; i++) teams.Add(new List<WheelEntrant>());

        // Two equal teams: reuse the exact search the queue's !balance uses.
        if (T == 2 && sizes[0] == sizes[1] && sizes[0] <= 4 && pool.Count == sizes[0] * 2)
        {
            var tps = pool.Select(e => new TeamPlayer { Username = e.Login, Mmr = val[e] }).ToList();
            var splits = EnumerateSplits(tps, sizes[0]);
            double best = splits.Min(s => s.Diff);
            var near = splits.Where(s => s.Diff <= best + 1e-9).ToList();
            double bestSpread = near.Min(s => s.Spread);
            near = near.Where(s => s.Spread <= bestSpread + 1e-9).ToList();
            var aSet = new HashSet<int>(near[rng.Below(near.Count)].TeamA);
            for (int i = 0; i < pool.Count; i++) teams[aSet.Contains(i) ? 0 : 1].Add(pool[i]);
            return teams;
        }

        // Otherwise: snake deal from the strongest down, then swap players while that narrows the gap.
        var sorted = pool.OrderByDescending(e => val[e]).ToList();   // stable: ties keep the seeded shuffle order
        int idx = 0, pass = 0;
        while (idx < sorted.Count)
        {
            var seq = Enumerable.Range(0, T).ToList();
            if (pass % 2 == 1) seq.Reverse();
            foreach (int ti in seq)
                if (idx < sorted.Count && teams[ti].Count < sizes[ti]) teams[ti].Add(sorted[idx++]);
            pass++;
        }
        Func<double> gap = () => { var av = teams.Select(t => t.Average(e => (double)val[e])).ToList(); return av.Max() - av.Min(); };
        for (int iter = 0; iter < 200; iter++)
        {
            double cur = gap(), bestGap = cur;
            int ba = -1, bi = -1, bb = -1, bj = -1;
            for (int a = 0; a < T; a++) for (int b = a + 1; b < T; b++)
                for (int i = 0; i < teams[a].Count; i++) for (int j = 0; j < teams[b].Count; j++)
                {
                    var x = teams[a][i]; teams[a][i] = teams[b][j]; teams[b][j] = x;
                    double g = gap();
                    teams[b][j] = teams[a][i]; teams[a][i] = x;
                    if (g < bestGap - 1e-9) { bestGap = g; ba = a; bi = i; bb = b; bj = j; }
                }
            if (ba < 0) break;
            var y = teams[ba][bi]; teams[ba][bi] = teams[bb][bj]; teams[bb][bj] = y;
        }
        return teams;
    }

    // One "Team N: A + B!" line per team, then the whole roster in paragraphs under 450 characters (Twitch allows 500), split at team boundaries.
    List<WheelMsg> WheelBuildMessages(WheelSession w)
    {
        var list = new List<WheelMsg>();
        foreach (var t in w.Teams)
            list.Add(new WheelMsg { Team = t.N, Text = "Team " + t.N + ": " + string.Join(" + ", t.Members) + "!" + (t.Partial ? " (partial team)" : "") });
        Action<IEnumerable<string>, string, string> paragraphs = (items, head, cont) =>
        {
            var sb = new System.Text.StringBuilder(head);
            bool any = false;
            foreach (string p in items)
            {
                if (any && sb.Length + 3 + p.Length > 450) { list.Add(new WheelMsg { Text = sb.ToString() }); sb = new System.Text.StringBuilder(cont); any = false; }
                if (any) sb.Append(" | ");
                sb.Append(p); any = true;
            }
            if (any) list.Add(new WheelMsg { Text = sb.ToString() });
        };
        paragraphs(w.Teams.Select(t => "Team " + t.N + ": " + string.Join(" + ", t.Members)), "TOURNAMENT TEAMS - ", "TOURNAMENT TEAMS (cont.) - ");
        if (w.Waitlist.Count > 0)
        {
            string head = w.OddPolicy == "mod" ? "Waiting for a mod decision - " : "Waitlist - ";
            paragraphs(w.Waitlist, head, head);
        }
        return list;
    }

    // MANUAL SPIN: the draw is committed, the mod reveals one pick per Spin (site button -> "!wheel spin N", or a mod typing "!wheel spin"). Chat lines wait until the overlay has landed (~8.5 s)
    // and never give a pick away early. Safe to repeat: Revealed only grows, each team and the final list are queued once.
    const int WheelSpinLandMs = 8500;
    void WheelSpin(WheelSession w, string arg)
    {
        if (w.Draw == null || w.Draw.Steps.Count == 0) { Say("There is no draw to spin. Type !wheel draw first."); return; }
        int total = w.Draw.Steps.Count, n;
        int target = int.TryParse((arg ?? "").Trim(), out n) ? Math.Min(Math.Max(n, 0), total) : Math.Min(w.Draw.Revealed + 1, total);
        if (target > w.Draw.Revealed) { w.Draw.Revealed = target; w.Draw.SpunAt = NowMs(); }
        if (w.Draw.Revealed == total - 1 && w.Draw.Revealed > 0) w.Draw.Revealed = total;   // the last entrant left needs no spin: it lands with the one before
        long due = w.Draw.SpunAt + WheelSpinLandMs;
        var shown = w.Draw.Steps.Take(w.Draw.Revealed).ToList();
        foreach (var t in w.Teams)
        {
            if (w.Msgs.Any(m => m.Team == t.N)) continue;
            if (shown.Count(x => x.Team == t.N) < t.Members.Count) continue;   // not every member revealed yet
            w.Msgs.Add(new WheelMsg { Team = t.N, Due = due, Text = "Team " + t.N + ": " + string.Join(" & ", t.Members) + "!" + (t.Partial ? " (partial team)" : "") });
        }
        if (w.Draw.Revealed >= total && !w.Msgs.Any(m => m.Team == 0 && (m.Text ?? "").StartsWith("TOURNAMENT TEAMS")))
        {
            Action<IEnumerable<string>, string, string> paragraphs = (items, head, cont) =>
            {
                var sb = new System.Text.StringBuilder(head);
                bool any = false;
                foreach (string p in items)
                {
                    if (any && sb.Length + 3 + p.Length > 450) { w.Msgs.Add(new WheelMsg { Due = due + 500, Text = sb.ToString() }); sb = new System.Text.StringBuilder(cont); any = false; }
                    if (any) sb.Append(" | ");
                    sb.Append(p); any = true;
                }
                if (any) w.Msgs.Add(new WheelMsg { Due = due + 500, Text = sb.ToString() });
            };
            paragraphs(w.Teams.Select(t => string.Join(" & ", t.Members) + (t.Partial ? " (partial team)" : "")), "TOURNAMENT TEAMS - ", "TOURNAMENT TEAMS (cont.) - ");
            if (w.Waitlist.Count > 0)
            {
                string head = w.OddPolicy == "mod" ? "Waiting for a mod decision - " : "Waitlist - ";
                paragraphs(w.Waitlist, head, head);
            }
        }
        if (w.Msgs.Any(m => !m.Sent)) w.AnnState = "sending";
        WheelSave();
        WheelPump();
    }

    void WheelQueueAnnounce(WheelSession w)
    {
        w.Msgs = WheelBuildMessages(w);
        foreach (var t in w.Teams) t.Announced = false;
        w.AnnState = "sending";
        WheelSave();
    }

    // Runs every web sync tick (and after !wheel announce): finishes the reveal, then sends chat messages a few at a time, ~1.2 s apart.
    // Each message has its own "sent" flag, so a retry never repeats one that already went out.
    void WheelPump()
    {
        var w = _wheel;
        if (w == null) return;
        if (w.Status == "drawing" && w.Draw != null && NowMs() >= w.Draw.StartedAt + (long)w.Draw.Steps.Count * w.Draw.StepMs)
        {
            w.Status = "drawn";
            WheelSave();
        }
        if (w.AnnState != "sending") return;
        int sentNow = 0;
        foreach (var m in w.Msgs.Where(x => !x.Sent).ToList())
        {
            if (m.Due > 0 && NowMs() < m.Due) continue;   // manual spin: not before the overlay has landed
            if (sentNow >= _wheelPerTick) return;   // the next tick carries on
            try { PgSay("core", m.Text); }
            catch (Exception ex)
            {
                w.AnnState = "failed";
                ReportProblem("Wheel announcement failed: " + ex.Message);
                WheelSave();
                return;
            }
            m.Sent = true;
            if (m.Team > 0) { var t = w.Teams.FirstOrDefault(x => x.N == m.Team); if (t != null) t.Announced = true; }
            sentNow++;
            WheelSave();
            if (_wheelGapMs > 0 && w.Msgs.Any(x => !x.Sent)) System.Threading.Thread.Sleep(_wheelGapMs);
        }
        bool spinning = w.Draw != null && w.Draw.Revealed > 0 && w.Draw.Revealed < w.Draw.Steps.Count;   // manual spin not finished: more lines will come
        if (w.Msgs.All(x => x.Sent) && !spinning) { w.AnnState = "done"; WheelSave(); }
    }

    // What the website mirrors. Mirrors site worker wheelClean(); the seed is deliberately left out.
    object WheelSnapshot()
    {
        var w = _wheel;
        if (w == null)
            return new { id = "", status = "none", mode = "random", teamSize = 2, oddPolicy = "waitlist", eligibility = "all",
                         entrants = new object[0], teams = new object[0], draw = (object)null, waitlist = new string[0],
                         announce = new { state = "idle", sent = 0, total = 0 }, canUndo = false, drawCount = 0, caps = new { spin = true }, practice = false };
        object draw = w.Draw == null ? null : (object)new
        {
            id = w.Draw.Id, startedAt = w.Draw.StartedAt, stepMs = w.Draw.StepMs,
            steps = w.Draw.Steps.Select(s => new { team = s.Team, name = s.Name }).ToList(),
            revealed = w.Draw.Revealed, spunAt = w.Draw.SpunAt
        };
        return new
        {
            id = w.Id, status = w.Status, mode = w.Mode, teamSize = w.TeamSize, oddPolicy = w.OddPolicy, eligibility = w.Eligibility,
            entrants = w.Entrants.Select(e => new { id = e.Id, login = e.Login, name = e.Name, epic = e.Epic ?? "", mmr = e.Mmr, flagged = e.Flagged, wait = e.Wait, practice = e.Practice }).ToList(),
            teams = w.Teams.Select(t => new { n = t.N, members = t.Members, avg = t.Avg, partial = t.Partial, announced = t.Announced }).ToList(),
            draw = draw, waitlist = w.Waitlist,
            announce = new { state = w.AnnState, sent = w.Msgs.Count(m => m.Sent), total = w.Msgs.Count },
            canUndo = (w.Status == "drawing" || w.Status == "drawn") && !w.Msgs.Any(m => m.Sent),
            drawCount = w.DrawCount, caps = new { spin = true }, practice = w.Entrants.Any(e => e.Practice)
        };
    }

    void SavePlayers() { SaveJson("players.json", _practice.Count == 0 ? _players : _players.Where(kv => !IsPractice(kv.Key)).ToDictionary(kv => kv.Key, kv => kv.Value)); _standingsDirty = true; }   // [NEW][WEB] league table changed (practice players are never saved)
    void SaveQueue() { SaveJson("queue.json", _practice.Count == 0 ? _queue : _queue.Where(e => !IsPractice(e.Username)).ToList()); }
    void SaveMatches() { SaveJson("matches.json", _practice.Count == 0 && !_matches.Any(IsPracticeMatch) ? _matches : _matches.Where(m => !IsPracticeMatch(m)).ToList()); _matchesDirty = true; }   // [NEW][WEB] history changed: send it to the website
    void SaveMmrCache() { SaveJson("mmr_cache.json", _mmrCache); }
    void SaveSettings() { SaveJson("settings.json", _settings); }
    void SaveCurrentMatch() { if (_lastBalance != null && IsPracticeLast()) return; SaveJson("current_match.json", _lastBalance); }   // a practice lobby lives in memory only

    static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

    // ══════════════════════════════════════════════════════════════
    //  LIVE STATE  [NEW][CIRCUIT]
    //  The single snapshot the website and OBS overlays read.
    //  File: %AppData%\BVQ\live_state.json  (serve it, or let OBS read it)
    // ══════════════════════════════════════════════════════════════

    void PublishState(string eventType, string detail)
    {
        // [FIX][CIRCUIT] Seq survives restarts (stored in settings) so overlays never
        // see the counter go backwards, and the last 25 events are kept so an
        // overlay that polls slowly can catch up on anything it missed.
        long seq = ++_settings.NextEventSeq;
        SaveSettings();
        _lastEvent = new LiveEvent { Seq = seq, Type = eventType, Detail = detail, At = Now() };
        _recentEvents.Add(_lastEvent);
        if (_recentEvents.Count > 25) _recentEvents.RemoveAt(0);
        object state = BuildLiveState();
        SaveJson("live_state.json", state);
        WriteOverlayState(state);
        _stateDirty = true;   // [NEW][WEB] the next web sync pushes this to the website
    }

    // [NEW][OBS] OBS browser sources can't fetch a .json file from disk, but they
    // CAN load a .js file. So we also write the state as live_state.js next to the
    // overlay HTML files (settings.json -> OverlayDir). Skipped if that folder doesn't exist.
    void WriteOverlayState(object state)
    {
        if (string.IsNullOrEmpty(_settings.OverlayDir) || !Directory.Exists(_settings.OverlayDir)) return;
        try
        {
            File.WriteAllText(Path.Combine(_settings.OverlayDir, "live_state.js"),
                "window.LIVE_STATE = " + JsonConvert.SerializeObject(state) + ";");
        }
        catch (Exception ex)
        {
            CPH.LogWarn("[BVQ] Overlay write failed: " + ex.Message);
        }
    }

    // [NEW][WEB] The live snapshot, shared by live_state.json (OBS) and the website.
    // [NEW][WEB] A player's registered Epic name ("" if unknown).
    string EpicOf(string username)
    {
        Player p;
        return _players.TryGetValue(username, out p) && p.GameId != null ? p.GameId : "";
    }

    // [NEW][WEB] MMR shown next to names on the site. Stored value only (no Tracker lookups here:
    // BuildLiveState runs on every sync and must never do network calls).
    int? StoredMmr(string username)
    {
        Player p;
        if (!_players.TryGetValue(username, out p)) return null;
        if (IsFortnite()) return p.Sr;                       // Fortnite shows SR
        return p.PeakMmr;
    }
    string MmrSrc(string username)
    {
        Player p;
        if (!_players.TryGetValue(username, out p)) return "default";
        if (IsFortnite()) return !p.Sr.HasValue ? "default" : p.SrSource == "self" ? "self" : "mod";
        if (!p.PeakMmr.HasValue) return "default";
        return p.MmrSource == "api" ? "tracker" : p.MmrSource == "manual" ? "mod" : p.MmrSource == "self" ? "self" : "default";
    }

    // [NEW][KOTH] The match as the website / overlays see it (null when there is none).
    object BuildMatchObject()
    {
        object match = null;
        if (_lastBalance != null && _lastBalance.Result != null)
        {
            match = new
            {
                id = _lastBalance.MatchId,
                winner = _lastBalance.ResultRecorded ? _lastBalance.Winner : null,   // [NEW][KOTH] for the winner animation
                format = _lastBalance.Format,
                status = _lastBalance.ResultRecorded ? "finished" : "live",
                startedAt = _matches.Where(r => r.Id == _lastBalance.MatchId).Select(r => r.CreatedAt).FirstOrDefault(),   // when the teams were made (unix seconds), for the lobby overlay
                // [NEW][WEB] Casual customs: the bot just picks a GROUP (no Orange/Blue teams shown). Internally the group is still
                // split in two (so !next etc. keep working); the website shows one grid.
                group = _matches.Any(r => r.Id == _lastBalance.MatchId && r.Group),
                // [NEW][WEB] epic = registered Epic name, shown on the site as "Platform name | Epic".
                blue = _lastBalance.Result.Blue.Select(p => new { p.Username, p.Mmr, MmrSource = MmrSrc(p.Username), Epic = EpicOf(p.Username), Practice = IsPractice(p.Username) }),
                orange = _lastBalance.Result.Orange.Select(p => new { p.Username, p.Mmr, MmrSource = MmrSrc(p.Username), Epic = EpicOf(p.Username), Practice = IsPractice(p.Username) }),
                practice = IsPracticeLast(),
                blueAvg = _lastBalance.Result.BlueAvgMmr,
                orangeAvg = _lastBalance.Result.OrangeAvgMmr
            };
        }
        return match;
    }

    object BuildLiveState()
    {
        var waiting = GetWaitingQueue();
        // [NEW][KOTH] After !finish the PUBLIC state (website + OBS overlays) keeps showing the finished match for ResultHoldSeconds so the winner animation
        // can play, while liveMatch is what is really going on (the mod page uses that one).
        object live = BuildMatchObject();
        bool hold = _holdMatch != null && Now() < _holdUntil;
        if (!hold) _holdMatch = null;
        object match = hold ? _holdMatch : live;

        return new
        {
            updatedAt = Now(),
            queueOpen = _settings.QueueOpen,
            format = _settings.DefaultFormat,
            gameMode = _settings.GameMode ?? "standard",
            casualStyle = "teams",   // [CHANGE] group style retired
            obs = BuildObsState(),             // [NEW][OBS] the website shows this to mods only (Master View)
            game = IsFortnite() ? "fortnite" : "rocket-league",   // [NEW][WEB] Fortnite shows SR instead of MMR
            mode = _settings.TeamMode,
            streamerPlaying = _settings.StreamerPlaying,   // [NEW][WEB] 5 gold (playing) vs 6 gold (sitting out) on the site
            spotsNeeded = Math.Max(0, GetTotalSlots(_settings.DefaultFormat) - waiting.Count),
            queue = waiting.Select((e, i) => new { pos = i + 1, user = e.Username, epic = EpicOf(e.Username), mmr = StoredMmr(e.Username), mmrSource = MmrSrc(e.Username), practice = IsPractice(e.Username) }),
            activity = _settings.Activity,            currentMatch = match,
            liveMatch = hold ? live : null,   // [NEW][KOTH] only while the public view is being held
            hold = hold,
            board = KothBoard(),   // [NEW][KOTH] who is winning in the King of the Hill activity right now (empty in other activities)
            koth = IsKothMode(),   // the KOTH setting OR the King of the Hill activity
            matchId = _lastBalance != null ? _lastBalance.MatchId : 0,
            practice = _practiceOn || _practice.Count > 0,   // practice mode: the site must not treat anyone flagged practice as a member or keep them
            lastEvent = _lastEvent,
            recentEvents = _recentEvents
        };
    }

    // ══════════════════════════════════════════════════════════════
    //  ENTRY POINT
    // ══════════════════════════════════════════════════════════════

    public bool Execute()
    {
        lock (_sync)   // [FIX] see _sync above
        {
            try
            {
                EnsureInitialized();
                StartWebSyncLoop();   // [NEW][WEB] keeps the website in sync while Streamer.bot is open
                return Dispatch();
            }
            catch (Exception ex)
            {
                // [FIX] An unhandled exception used to kill the action silently.
                CPH.LogError("[BVQ] Command failed: " + ex);
                ReportProblem("Command failed: " + ex.GetType().Name + ": " + ex.Message);
                return true;
            }
        }
    }

    bool Dispatch()
    {
        CPH.TryGetArg("command", out string command);
        CPH.TryGetArg("rawInput", out string rawInput);
        CPH.TryGetArg("user", out string user);
        CPH.TryGetArg("role", out int role);
        CPH.TryGetArg("isModerator", out bool isMod);
        CPH.TryGetArg("isBroadcaster", out bool isBroadcaster);

        // role: 3 = Mod, 4 = Broadcaster
        bool isPrivileged = role >= 3 || isMod || isBroadcaster;

        // [FIX] "user" is the DISPLAY name, which can differ from the Twitch login
        // (e.g. Japanese display names). Use the login (userName) as the player key.
        CPH.TryGetArg("userName", out string login);
        CPH.TryGetArg("userId", out string userId);
        string display = (user ?? "").ToLower().Trim();
        string userLower = (!string.IsNullOrEmpty(login) ? login : user ?? "").ToLower().Trim();
        string input = (rawInput ?? "").Trim();
        if (!string.IsNullOrEmpty(command)) FollowTwitchIdentity(userLower, userId, display);

        // [NEW][WEB] The Streamer.bot Timed Action named "PinguinoBot Web Sync"
        // (every 3 s) runs this same action with no chat command. That tick talks
        // to the website. A chat message can't trigger it: it needs timerName.
        CPH.TryGetArg("timerName", out string timerName);
        if (string.IsNullOrEmpty(command) && string.Equals((timerName ?? "").Trim(), WebSyncTimerName, StringComparison.OrdinalIgnoreCase))
            return HandleWebSync();

        // [NEW][WHEEL] who typed this (for !me): Twitch id, display name, subscriber
        CPH.TryGetArg("isSubscribed", out bool isSub);
        _cmdUserId = userId ?? ""; _cmdDisplay = user ?? ""; _cmdSub = isSub;
        try { return RunCommand(command, input, userLower, isPrivileged); }
        finally { _cmdUserId = ""; _cmdDisplay = ""; _cmdSub = false; }
    }

    // [NEW] TWITCH IDS: names change, ids don't. Every chat command tells us the
    // player's id. If we already know that id under an older name (they renamed),
    // or under their display name (old records), the record, stats and queue spot
    // move to their current login. Players without an id get it filled in.
    void FollowTwitchIdentity(string login, string id, string display)
    {
        if (string.IsNullOrEmpty(login) || string.IsNullOrEmpty(id)) return;
        var byId = _players.Values.FirstOrDefault(x => x.TwitchId == id);
        if (byId != null)
        {
            if (byId.Username != login) RenamePlayer(byId.Username, login);
            return;
        }
        Player p;
        if (_players.TryGetValue(login, out p))
        {
            if (string.IsNullOrEmpty(p.TwitchId)) { p.TwitchId = id; SavePlayers(); }
            return;
        }
        if (!string.IsNullOrEmpty(display) && display != login && _players.TryGetValue(display, out p) && string.IsNullOrEmpty(p.TwitchId))
        {
            RenamePlayer(display, login);
            if (_players.TryGetValue(login, out p)) { p.TwitchId = id; SavePlayers(); }
        }
    }

    void RenamePlayer(string oldName, string newName)
    {
        Player p;
        if (oldName == newName || _players.ContainsKey(newName) || !_players.TryGetValue(oldName, out p)) return;
        _players.Remove(oldName);
        p.Username = newName;
        _players[newName] = p;
        foreach (var e in _queue.Where(e => e.Username == oldName)) e.Username = newName;
        if (_lastBalance != null)
        {
            foreach (var tp in (_lastBalance.Players ?? new List<TeamPlayer>()).Concat(_lastBalance.Result != null ? _lastBalance.Result.Blue.Concat(_lastBalance.Result.Orange) : Enumerable.Empty<TeamPlayer>()))
                if (tp.Username == oldName) tp.Username = newName;
            SaveCurrentMatch();
        }
        SavePlayers(); SaveQueue();
        CPH.LogInfo("[BVQ] Renamed player " + oldName + " -> " + newName);
        PublishState("queue_update", oldName + " is now " + newName);
    }

    // [NEW][WEB] Every command, from chat OR the website, goes through here.
    bool RunCommand(string command, string input, string userLower, bool isPrivileged)
    {
        _cmdUser = userLower ?? "";
        switch (command?.ToLower())
        {
            case "!register": return HandleRegister(userLower, input, isPrivileged);
            case "!join":     return HandleJoin(userLower);
            case "!leave":    return HandleLeave(userLower);
            case "!pos":      return HandlePos(userLower);
            case "!myrank":   return HandleRank(userLower);                        // renamed from !rank (clashed with another bot)
            case "!queue":    return HandleQueue(userLower, input, isPrivileged);
            case "!balance":  return HandleBalance(userLower, isPrivileged);
            case "!next":     return HandleNext(userLower, input, isPrivileged);
            case "!win":      return HandleWin(userLower, input, isPrivileged);    // [NEW]
            case "!reroll":   return HandleReroll(userLower, isPrivileged);
            case "!format":   return HandleFormat(userLower, input, isPrivileged);
            case "!mode":     return HandleMode(userLower, input, isPrivileged);   // [NEW]
            case "!pick":     return HandlePick(userLower, input, isPrivileged);   // [NEW]
            case "!lobby":    return HandleLobby(userLower);
            case "!kick":     return HandleKick(userLower, input, isPrivileged);
            case "!streamer": return HandleStreamer(userLower, input, isPrivileged); // [NEW] in | out
            case "!activity": return HandleActivity(userLower, input, isPrivileged); // [NEW][WEB] competitive | casual | viewers | end
            case "!gamemode": return HandleGameMode(userLower, input, isPrivileged); // [NEW][WEB] standard | dropshot | rumble
            case "!casual":   return HandleCasualStyle(userLower, input, isPrivileged); // [NEW][WEB] group | teams
            case "!scene":    return HandleObsScene(userLower, input, isPrivileged);    // [NEW][OBS] switch the OBS scene
            case "!source":   return HandleObsSource(userLower, input, isPrivileged);   // [NEW][OBS] show / hide an OBS source
            case "!obs":      return HandleObs(userLower, input, isPrivileged);         // [NEW][OBS] !obs auto on|off, !obs status
            case "!matchwin": return HandleMatchWin(userLower, input, isPrivileged); // [NEW][WEB] fix a past match: !matchwin <id> <blue|orange>
            case "!matchdel": return HandleMatchDel(userLower, input, isPrivileged); // [NEW][WEB] remove a past match: !matchdel <id>
            case "!move":     return HandleMove(userLower, input, isPrivileged);     // [NEW][WEB] drag to reorder the queue
            case "!out":      return HandleOut(userLower, input, isPrivileged);      // [NEW][WEB] drag a player out of the match
            case "!in":       return HandleIn(userLower, input, isPrivileged);       // [NEW][WEB] drag a player into a team slot
            case "!match":    return HandleMatch(userLower, input, isPrivileged);    // [NEW][WEB] clear | fill | queue (buttons under the teams)
            case "!mmr":      return HandleMmrLookup(userLower, input, isPrivileged);
            case "!setmmr":   return HandleSetMmr(userLower, input, isPrivileged);
            case "!setsr":    return HandleSetSr(userLower, input, isPrivileged);   // [NEW][WEB] Fortnite skill rating
            case "!problems": return HandleProblems(userLower, input, isPrivileged);       // [NEW][CHECK] open problems / "clear" empties problems.json
            case "!check":    return HandleCheck(userLower, isPrivileged);                 // [NEW][CHECK] self-test; problems go to the website log in red
            case "!finish":   return HandleFinish(userLower, input, isPrivileged);       // [NEW][KOTH] Orange / Blue wins, then everyone out (or winners stay)
            case "!koth":     return HandleKoth(userLower, input, isPrivileged);
            case "!strike":   return HandleStrike(userLower, input, isPrivileged, 1);    // [NEW][STRIKES]
            case "!unstrike": return HandleStrike(userLower, input, isPrivileged, -1);
            case "!strikes":  return HandleStrikes(userLower, input);
            case "!stats":    return HandleStats(userLower, input);                // [NEW]
            case "!topwins":  return HandleTop();                                  // [NEW] (!top was taken by the points bot)
            case "!me":       return HandleMe(userLower, isPrivileged);             // [NEW][WHEEL] join the tournament
            case "!wheel":    return HandleWheel(userLower, input, isPrivileged);   // [NEW][WHEEL] mods run the tournament wheel
            case "!practice": return HandlePractice(userLower, input, isPrivileged);   // [NEW][PRACTICE] fake players to rehearse matchmaking and the wheel
            case "!spin":     return HandleWheel(userLower, ("spin " + input).Trim(), isPrivileged);   // [NEW][WHEEL] alias for !wheel spin
            default:
                CPH.LogWarn("[BVQ] Unknown command: " + command);
                ReportProblem(string.IsNullOrEmpty(command)
                    ? "PinguinoB0t ran without a command (is a Streamer.bot trigger set up wrong?)" + (string.IsNullOrEmpty(userLower) ? "" : " [by " + userLower + "]")
                    : "Unknown command \"" + command + "\"" + (string.IsNullOrEmpty(userLower) ? "" : " from " + userLower) + ": PinguinoB0t does not know it");
                return true;
        }
    }

    void Say(string message)
    {
        // [NEW][WEB] Status updates always reach the stream, even when the change
        // came from the website. For website-only players (no Twitch, IDs like
        // "kick-penguinkick") the "@kick-penguinkick" is swapped for their site
        // display name, e.g. "PenguinKick (web)", so chat isn't confused.
        if (_quiet && !string.IsNullOrEmpty(_webId))
            PgSay("core", message.Replace("@" + _webId, (_webName ?? _webId) + " (web)"));
        else
            PgSay("core", message);
        if (_capture != null) _capture.Add(message);   // [NEW][WEB] reply shown on the website too
    }

    // ══════════════════════════════════════════════════════════════
    //  WEBSITE BRIDGE  [NEW][WEB]
    //  Outgoing HTTPS only (nothing on this PC is opened to the internet):
    //    GET  {WebSyncUrl}/api/bot/commands  -> website requests (Join/Leave, mod buttons)
    //    POST {WebSyncUrl}/api/bot/results   -> what the bot replied to each
    //    POST {WebSyncUrl}/api/bot/state     -> live snapshot (on change, and every 30 s)
    //  Each website request runs through RunCommand() exactly like the chat
    //  command, so chat and website always give the same result.
    //  [NOTE] Runs inside the same lock as chat commands. Every call has a
    //  4-second timeout, so a slow website can delay chat commands by a few
    //  seconds at worst, and never corrupts data.
    // ══════════════════════════════════════════════════════════════

    const string WebSyncTimerName = "PinguinoBot Web Sync";

    // [NEW][WEB] AUTO SYNC: the website no longer depends on a Streamer.bot timer.
    // The first time this action runs (any chat command, or the optional timer),
    // a background loop starts and syncs with the website every 3 s for as long as
    // Streamer.bot stays open. So the site shows PinguinoB0t "online" whenever
    // Streamer.bot is running, live or not.
    // [NOTE] Pressing Compile makes a NEW copy of this code; the old copy's loop
    // would keep running. Each loop registers itself in AppDomain data and stops
    // as soon as a newer loop takes over, so only one ever runs.
    const string SyncOwnerKey = "BVQ.WebSyncOwner";
    static string _loopId;
    void StartWebSyncLoop()
    {
        if (string.IsNullOrEmpty(_settings.WebSyncKey) || string.IsNullOrEmpty(_settings.WebSyncUrl)) return;
        if (_loopId != null && (AppDomain.CurrentDomain.GetData(SyncOwnerKey) as string) == _loopId) return;   // already running
        string id = Guid.NewGuid().ToString("N");
        _loopId = id;
        AppDomain.CurrentDomain.SetData(SyncOwnerKey, id);
        var t = new System.Threading.Thread(() =>
        {
            CPH.LogInfo("[BVQ] Website sync started (every 3 s).");
            while ((AppDomain.CurrentDomain.GetData(SyncOwnerKey) as string) == id)
            {
                try { lock (_sync) { HandleWebSync(); } }
                catch (Exception ex) { CPH.LogVerbose("[BVQ] Web sync error: " + ex.Message); }
                System.Threading.Thread.Sleep(3000);
            }
        });
        t.IsBackground = true;   // never keeps Streamer.bot from closing
        t.Name = "BVQ Web Sync";
        t.Start();
    }
    static List<string> _capture;
    static bool _quiet;   // [NEW][WEB] true while running a website-only player's command
    static string _webId, _webName;   // [NEW][WEB] that player's bot ID and site display name
    static bool _stateDirty = true;
    static bool _standingsDirty = true;                    // [NEW][WEB] send the league table on the next sync
    static bool _matchesDirty = true;                      // [NEW][WEB] send the match history on the next sync
    static DateTime _lastMatchesPush = DateTime.MinValue;
    static DateTime _lastStandingsPush = DateTime.MinValue;
    static DateTime _lastStatePush = DateTime.MinValue;

    class TimeoutWebClient : WebClient
    {
        protected override WebRequest GetWebRequest(Uri address)
        {
            WebRequest r = base.GetWebRequest(address);
            r.Timeout = 4000;
            return r;
        }
    }

    class WebCommand
    {
        public string id { get; set; }
        public string command { get; set; }
        public string input { get; set; }
        public string user { get; set; }
        public bool privileged { get; set; }
        public bool quiet { get; set; }   // website-only player: don't post the reply in Twitch chat
        public string epic { get; set; }
        public string userId { get; set; }   // [NEW][WHEEL] the viewer's Twitch id when the site knows it (a site "Join" for the tournament)
        public bool sub { get; set; }        // [NEW][WHEEL] is a subscriber (tournament eligibility "subs")
        public string name { get; set; }  // [NEW][WEB] site display name, used in chat for website-only players  // [NEW][WEB] Epic name saved in the member's site Settings (sent with !join)
    }

    string WebCall(string method, string path, string body)
    {
        ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
        using (var client = new TimeoutWebClient())
        {
            client.Encoding = System.Text.Encoding.UTF8;
            client.Headers[HttpRequestHeader.Authorization] = "Bearer " + _settings.WebSyncKey;
            string url = _settings.WebSyncUrl.TrimEnd('/') + path;
            string reply;
            if (method == "GET") reply = client.DownloadString(url);
            else
            {
                client.Headers[HttpRequestHeader.ContentType] = "application/json";
                reply = client.UploadString(url, "POST", body);
            }
            _lastWebOk = DateTime.UtcNow;
            return reply;
        }
    }

    bool HandleWebSync()
    {
        HostLive();   // the Host knows by itself whether the stream is live (no website key needed)
        if (string.IsNullOrEmpty(_settings.WebSyncKey) || string.IsNullOrEmpty(_settings.WebSyncUrl))
            return true;   // bridge turned off
        try
        {
            // 1) Website requests -> same code as chat.
            var pending = JObject.Parse(WebCall("GET", "/api/bot/commands", null))["commands"]?.ToObject<List<WebCommand>>()
                          ?? new List<WebCommand>();
            var results = new List<object>();
            foreach (var wc in pending)
            {
                string cmd = (wc.command ?? "").ToLower();
                // [NOTE] Only known commands; the website already limits these too.
                if (!cmd.StartsWith("!")) continue;
                _capture = new List<string>();
                _quiet = wc.quiet;
                _webId = (wc.user ?? "").ToLower().Trim();
                _webName = wc.name;
                try
                {
                    string webUser = (wc.user ?? "").ToLower().Trim();
                    // [NEW][WEB] The website is the source of the Epic name (set once in Settings,
                    // locked by the site). Register/update it first if the bot doesn't match,
                    // then drop that reply so the viewer only sees the !join answer.
                    string epic = (wc.epic ?? "").Trim();
                    Player known;
                    if (epic.Length > 0 && !(_players.TryGetValue(webUser, out known) &&
                        string.Equals(known.GameId, epic, StringComparison.OrdinalIgnoreCase)))
                    {
                        // privileged=true lets it UPDATE an existing name (the site already
                        // requires a mod unlock before a member can change their Epic name).
                        HandleRegister(webUser, epic.StartsWith("@") ? epic.TrimStart('@') : epic, true);
                        _capture.Clear();
                    }
                    // [NEW][WHEEL] a site "Join" for the tournament runs !me with the same rules as chat (open sign-ups, subs-only, dedupe by id or name)
                    _cmdUserId = (wc.userId ?? "").Trim(); _cmdDisplay = string.IsNullOrWhiteSpace(wc.name) ? webUser : wc.name; _cmdSub = wc.sub || string.Equals((wc.input ?? "").Trim(), "sub", StringComparison.OrdinalIgnoreCase);   // the site sends input "sub" for subscribers/staff
                    try { RunCommand(cmd, (wc.input ?? "").Trim(), webUser, wc.privileged); }
                    finally { _cmdUserId = ""; _cmdDisplay = ""; _cmdSub = false; }
                }
                catch (Exception ex) { CPH.LogError("[BVQ] Web command failed: " + ex); ReportProblem("Website command " + cmd + " failed: " + ex.GetType().Name + ": " + ex.Message); _capture.Add("Something went wrong in PinguinoB0t."); }
                results.Add(new { id = wc.id, messages = _capture });
                _capture = null;
                _quiet = false;
                _webId = _webName = null;
            }
            if (results.Count > 0)
                WebCall("POST", "/api/bot/results", JsonConvert.SerializeObject(new { results = results }));

            // [NEW][CHECK] Problems the bot found go to the website's mod log, where they show up in RED.
            if (_problems.Count > 0)
            {
                var batch = _problems.ToList();
                WebCall("POST", "/api/bot/log", JsonConvert.SerializeObject(new { entries = batch.Select(m => new { level = "error", message = m }) }));
                _problems.Clear();
            }
            if (_checkNotes.Count > 0)
            {
                var notes = _checkNotes.ToList();
                WebCall("POST", "/api/bot/log", JsonConvert.SerializeObject(new { entries = notes.Select(m => new { level = "ok", message = m }) }));
                _checkNotes.Clear();
            }

            // [NEW][KOTH] The finished match has been on the website / overlays long enough: show the real state.
            if (_holdMatch != null && Now() >= _holdUntil) { _holdMatch = null; PublishState("hold_end", ""); }

            // 3) [NEW][WEB] Penguin League table: every registered player's
            //    [username, Epic name, wins, losses, points]. Sent when it changed,
            //    and every 5 minutes. The website lists them on /standings and
            //    makes a member profile for each Twitch player automatically.
            if (_standingsDirty || (DateTime.UtcNow - _lastStandingsPush).TotalMinutes >= 5)
            {
                var rows = _players.Values.Where(p => !IsPractice(p.Username)).Select(p => new object[] { p.Username, p.GameId ?? "", p.Wins, p.Losses, p.Points, p.TwitchId ?? "", p.PeakMmr.HasValue ? (object)p.PeakMmr.Value : null, MmrSrc(p.Username), StrikeTotal(p), p.Sr.HasValue ? (object)p.Sr.Value : null, p.PermaStrikes }).ToList();
                // [NEW][WEB] per game mode tables: category -> [username, wins, losses, points]
                var modes = new Dictionary<string, List<object[]>>();
                foreach (var p in _players.Values)
                {
                    if (p.Modes == null || IsPractice(p.Username)) continue;
                    foreach (var kv in p.Modes)
                    {
                        if (kv.Value.Wins + kv.Value.Losses == 0) continue;
                        if (!modes.ContainsKey(kv.Key)) modes[kv.Key] = new List<object[]>();
                        modes[kv.Key].Add(new object[] { p.Username, kv.Value.Wins, kv.Value.Losses, kv.Value.Points });
                    }
                }
                WebCall("POST", "/api/bot/standings", JsonConvert.SerializeObject(new { players = rows, modes = modes }));
                _standingsDirty = false;
                _lastStandingsPush = DateTime.UtcNow;
            }

            // 4) [NEW][WEB] Match history (newest 100) for innocentpenguin.com/matches, so mods can fix a
            //    mistake. Sent when it changed and every 5 minutes.
            if (_matchesDirty || (DateTime.UtcNow - _lastMatchesPush).TotalMinutes >= 5)
            {
                var hist = _matches.Where(m => !IsPracticeMatch(m)).OrderByDescending(m => m.Id).Take(100).Select(m => new
                {
                    id = m.Id, format = m.Format, category = m.Category ?? m.Format, mode = m.Mode, activity = m.Activity ?? "competitive",
                    counted = IsCounted(m), createdAt = m.CreatedAt, finishedAt = m.FinishedAt, winner = m.Winner,
                    blue = (m.Blue ?? new List<TeamPlayer>()).Select(p => new object[] { p.Username, p.Mmr }).ToList(),
                    orange = (m.Orange ?? new List<TeamPlayer>()).Select(p => new object[] { p.Username, p.Mmr }).ToList(),
                    blueAvg = m.BlueAvg, orangeAvg = m.OrangeAvg
                }).ToList();
                WebCall("POST", "/api/bot/matches", JsonConvert.SerializeObject(new { matches = hist }));
                _matchesDirty = false;
                _lastMatchesPush = DateTime.UtcNow;
            }

            // 5) [NEW][OBS] Which game is the Twitch channel set to? (the website looks it up; the scene follows it when the auto switch is on)
            if ((DateTime.UtcNow - _lastGameCheck).TotalSeconds >= 30)
            {
                _lastGameCheck = DateTime.UtcNow;
                try
                {
                    string g = (string)JObject.Parse(WebCall("GET", "/api/game", null))["game"] ?? "";
                    if (g != _twitchGame)
                    {
                        bool first = _twitchGame == "";
                        _twitchGame = g;
                        _stateDirty = true;
                        if (!first && g != "") ObsGameSwitch(g, "Twitch category");
                    }
                }
                catch (Exception) { }
            }

            // 5b) [NEW][STRIKES] Is the stream live? (a new stream takes one strike off everybody)
            if (!_hostLiveGiven && (DateTime.UtcNow - _lastLiveCheck).TotalSeconds >= 30)
            {
                _lastLiveCheck = DateTime.UtcNow;
                try
                {
                    var lv = JObject.Parse(WebCall("GET", "/api/stream-status", null))["live"];
                    if (lv != null && lv.Type == JTokenType.Boolean) ApplyLive((bool)lv);
                }
                catch (Exception) { }
            }

            // [NEW][WHEEL] finish the reveal / send queued announcements, then mirror the session to the website (when changed, and every 30 s).
            try { WheelPump(); } catch (Exception ex) { CPH.LogError("[BVQ] Wheel tick failed: " + ex); }
            if (_wheelDirty || (DateTime.UtcNow - _lastWheelPush).TotalSeconds >= 30)
            {
                WebCall("POST", "/api/bot/wheel", JsonConvert.SerializeObject(WheelSnapshot()));
                _wheelDirty = false;
                _lastWheelPush = DateTime.UtcNow;
            }

            // 2) Live snapshot: when something changed, and every 30 s as a heartbeat.
            if (_stateDirty || (DateTime.UtcNow - _lastStatePush).TotalSeconds >= 30)
            {
                WebCall("POST", "/api/bot/state", JsonConvert.SerializeObject(BuildLiveState()));
                _stateDirty = false;
                _lastStatePush = DateTime.UtcNow;
            }
        }
        catch (WebException ex)
        {
            // Website down / no internet: try again next tick. Kept quiet to avoid log spam.
            CPH.LogVerbose("[BVQ] Web sync skipped: " + ex.Message);
        }
        finally
        {
            _capture = null;
            _quiet = false;
            _webId = _webName = null;
        }
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  QUEUE MANAGEMENT
    // ══════════════════════════════════════════════════════════════

    List<QueueEntry> GetWaitingQueue()
    {
        return _queue.Where(e => e.Status == "waiting").OrderBy(e => e.Position).ToList();
    }

    int GetWaitingCount()
    {
        return _queue.Count(e => e.Status == "waiting");
    }

    QueueEntry GetEntry(string username)
    {
        return _queue.FirstOrDefault(e => e.Username == username);
    }

    bool AddToQueue(string username)
    {
        if (_queue.Any(e => e.Username == username)) return false;

        int maxPos = _queue.Count > 0 ? _queue.Max(e => e.Position) : 0;
        int minPos = _queue.Count > 0 ? _queue.Min(e => e.Position) : 1;
        _queue.Add(new QueueEntry
        {
            Username = username,
            Position = IsStreamer(username) ? minPos - 1 : maxPos + 1,   // [NEW][WEB] streamer jumps to #1
            Status = "waiting",
            JoinedAt = Now()
        });
        CompactPositions();
        return true;
    }

    // [NEW][WEB] Only the competitive activity balances teams and records stats.
    // Boxfights and Zone Wars are the Fortnite "customs": they work exactly like competitive (balanced by SR, wins/points count).
    // [NEW][KOTH] "koth" = the King of the Hill ACTIVITY (Rocket League): balanced teams, winners stay on, its own wins leaderboard (category "koth").
    // WHICH ACTIVITIES COUNT STATS. ACTIVITY KEYS. RL (Rocket League): competitive, casual, koth, viewers | FN (Fortnite): boxfights, zonewars, fnviewers (the FN "viewers"). Keep every copy of this list in sync: grep for "fnviewers". ActivityCounts = competitive + FN customs + koth; casual and the two viewers modes never count.
    static bool ActivityCounts(string a) { return string.IsNullOrEmpty(a) || a == "competitive" || a == "boxfights" || a == "zonewars" || a == "koth"; }
    // The King of the Hill ACTIVITY leaderboard: wins in the current session, best first (up to 100; the site shows the top 10 + the viewer's own place). Empty in every other activity.
    object KothBoard()
    {
        if (_settings.Activity != "koth" || _settings.KothWins == null) return new object[0];
        return _settings.KothWins.OrderByDescending(kv => kv.Value).ThenBy(kv => kv.Key).Take(100)
            .Select(kv => new { user = kv.Key, epic = EpicOf(kv.Key), wins = kv.Value }).ToArray();
    }
    bool IsKothMode() { return _settings.Koth || _settings.Activity == "koth"; }
    // Fortnite and King of the Hill keep their own stats: they never touch the overall Rocket League wins / points.
    bool SeparateStats() { return IsFortnite() || _settings.Activity == "koth"; }
    // FN: true for boxfights / zonewars / fnviewers. Fortnite rates players with SR (Player.Sr, !setsr) instead of MMR, and its stats live in Player.Modes["boxfights"|"zonewars"].
    bool IsFortnite() { var a = _settings.Activity; return a == "boxfights" || a == "zonewars" || a == "fnviewers"; }
    bool IsCompetitive() { return ActivityCounts(_settings.Activity); }
    // [CHANGE] Casual now makes teams exactly like competitive (same team mode). Only viewers modes are always random.
    string ActiveMode() { return IsCompetitive() || _settings.Activity == "casual" ? _settings.TeamMode : "random"; }

    // [NEW][WEB] True for the streamer's own account (settings.json StreamerName).
    bool IsStreamer(string username)
    {
        return !string.IsNullOrEmpty(_settings.StreamerName) &&
               string.Equals(username, _settings.StreamerName, StringComparison.OrdinalIgnoreCase);
    }

    bool RemoveFromQueue(string username)
    {
        if (_queue.RemoveAll(e => e.Username == username) == 0) return false;
        CompactPositions();
        return true;
    }

    List<QueueEntry> PullNextBatch(int count)
    {
        // Entries are references into _queue, so setting Status here updates the list.
        var batch = GetWaitingQueue().Take(count).ToList();
        foreach (var entry in batch) entry.Status = "active";
        SaveQueue();
        return batch;
    }

    // [NEW][WEB] KICKED AFTER PLAYING: when a match is over, everyone who played
    // leaves the queue and has to !join (or press Join on the site) to get back in.
    // (This used to move them to the back of the line.) The streamer is the one
    // exception: he plays every match, so he goes back to the front.
    void SendToBack(IEnumerable<string> usernames)
    {
        var names = new HashSet<string>(usernames);
        var movers = _queue.Where(e => e.Status == "active" && names.Contains(e.Username))
                           .OrderBy(e => e.Position).ToList();
        if (movers.Count == 0) return;

        // [NEW][KOTH] King of the Hill recycles names: everyone who played (the streamer too) goes to the BACK of the waiting line instead of
        // leaving it, so nobody has to !join again and the streamer waits his turn after a loss. (The winners who stay on are made active again by the caller.)
        bool recycle = IsKothMode();
        int frontPos = _queue.Min(e => e.Position) - 1;
        int backPos = _queue.Max(e => e.Position) + 1;
        foreach (var entry in movers)
        {
            if (recycle)
            {
                entry.Status = "waiting";
                entry.Position = backPos++;
                entry.GamesPlayedSession++;
            }
            else if (IsStreamer(entry.Username))
            {
                entry.Status = "waiting";
                entry.Position = frontPos--;
                entry.GamesPlayedSession++;
            }
            else
            {
                _queue.Remove(entry);
            }
        }
        CompactPositions();
    }

    void RotateQueue()
    {
        SendToBack(_queue.Where(e => e.Status == "active").Select(e => e.Username).ToList());
    }

    void CompactPositions()
    {
        var ordered = _queue.OrderBy(e => e.Position).ToList();
        for (int i = 0; i < ordered.Count; i++) ordered[i].Position = i + 1;
        SaveQueue();
    }

    void ClearQueue()
    {
        _queue.Clear();
        _settings.QueueOpen = false;
        _lastBalance = null;            // [FIX] clearing the queue also ends the stale lobby
        SaveQueue();
        SaveSettings();
        SaveCurrentMatch();
    }

    // ══════════════════════════════════════════════════════════════
    //  TEAM BUILDING
    // ══════════════════════════════════════════════════════════════

    int GetTeamSize(string format)
    {
        return FormatTeamSize.ContainsKey(format) ? FormatTeamSize[format] : 3;
    }

    int GetTotalSlots(string format)
    {
        return GetTeamSize(format) * 2;
    }

    class Split
    {
        public int[] TeamA;
        public double Diff;
        public double Spread;
    }

    // Every way to split the players into two teams.
    // [FIX] The old version scored every split twice (A|B and B|A). Fixing
    // player 0 on team A removes the mirrors: 4v4 = 35 splits instead of 70.
    List<Split> EnumerateSplits(List<TeamPlayer> players, int teamSize)
    {
        int n = players.Count;
        int[] rest = Enumerable.Range(1, n - 1).ToArray();
        var splits = new List<Split>();

        foreach (int[] others in GetCombinations(rest, teamSize - 1))
        {
            int[] a = new[] { 0 }.Concat(others).ToArray();
            var aSet = new HashSet<int>(a);
            var aMmr = a.Select(i => (double)players[i].Mmr).ToArray();
            var bMmr = Enumerable.Range(0, n).Where(i => !aSet.Contains(i))
                                 .Select(i => (double)players[i].Mmr).ToArray();

            splits.Add(new Split
            {
                TeamA = a,
                Diff = Math.Abs(aMmr.Average() - bMmr.Average()),
                Spread = Math.Max(aMmr.Max() - aMmr.Min(), bMmr.Max() - bMmr.Min())
            });
        }
        return splits;
    }

    BalanceResult BuildResult(List<TeamPlayer> players, int[] teamA)
    {
        var aSet = new HashSet<int>(teamA);
        var blue = teamA.Select(i => players[i]).ToList();
        var orange = Enumerable.Range(0, players.Count).Where(i => !aSet.Contains(i))
                               .Select(i => players[i]).ToList();

        // [NOTE] Randomly swap sides so the best player isn't always Blue.
        if (_rng.Next(2) == 0) { var t = blue; blue = orange; orange = t; }

        return MakeResult(blue, orange);
    }

    BalanceResult MakeResult(List<TeamPlayer> blue, List<TeamPlayer> orange)
    {
        int blueAvg = (int)Math.Round(blue.Average(p => (double)p.Mmr));
        int orangeAvg = (int)Math.Round(orange.Average(p => (double)p.Mmr));
        return new BalanceResult
        {
            Blue = blue,
            Orange = orange,
            BlueAvgMmr = blueAvg,
            OrangeAvgMmr = orangeAvg,
            MmrDiff = Math.Abs(blueAvg - orangeAvg)
        };
    }

    // [NEW] Single entry point for all team modes.
    //   avoid = the current Blue team usernames; used by !reroll to force a different split.
    BalanceResult MakeTeams(List<TeamPlayer> players, string format, string mode, HashSet<string> avoid)
    {
        int teamSize = GetTeamSize(format);
        if (players.Count != teamSize * 2)
            throw new Exception("Expected " + (teamSize * 2) + " players for " + format + ", got " + players.Count);

        var splits = EnumerateSplits(players, teamSize);

        // Splits that recreate the current teams (either colour) are skipped on reroll.
        Func<Split, bool> isSame = s =>
        {
            if (avoid == null) return false;
            var a = new HashSet<string>(s.TeamA.Select(i => players[i].Username));
            return a.SetEquals(avoid) || !a.Overlaps(avoid);
        };

        if (mode == "random")
        {
            var pool = splits.Where(s => !isSame(s)).ToList();
            if (pool.Count == 0) pool = splits;
            return BuildResult(players, pool[_rng.Next(pool.Count)].TeamA);
        }

        // "balanced" (and "picks", whose auto-fill also balances)
        var best = splits.OrderBy(s => s.Diff).ThenBy(s => s.Spread).First();
        if (avoid == null)
            return BuildResult(players, best.TeamA);

        // [FIX] !reroll used to shuffle and re-run the same deterministic search,
        // which almost always produced the IDENTICAL teams. Now it picks randomly
        // among "fair enough" splits that differ from the current one.
        var fair = splits.Where(s => !isSame(s) && s.Diff <= best.Diff + _settings.RerollToleranceMmr).ToList();
        if (fair.Count == 0)
            fair = splits.Where(s => !isSame(s)).OrderBy(s => s.Diff).Take(1).ToList();
        if (fair.Count == 0)
            fair = new List<Split> { best };
        return BuildResult(players, fair[_rng.Next(fair.Count)].TeamA);
    }

    List<int[]> GetCombinations(int[] arr, int k)
    {
        var result = new List<int[]>();
        CombinationsHelper(arr, k, 0, new List<int>(), result);
        return result;
    }

    void CombinationsHelper(int[] arr, int k, int start, List<int> current, List<int[]> result)
    {
        if (current.Count == k)
        {
            result.Add(current.ToArray());
            return;
        }
        for (int i = start; i <= arr.Length - (k - current.Count); i++)
        {
            current.Add(arr[i]);
            CombinationsHelper(arr, k, i + 1, current, result);
            current.RemoveAt(current.Count - 1);
        }
    }

    List<TeamPlayer> ToTeamPlayers(List<string> usernames)
    {
        string format = _settings.DefaultFormat;
        return usernames.Select(u => new TeamPlayer { Username = u, Mmr = ResolveMmr(u, format) }).ToList();
    }

    // [CIRCUIT] One synchronized "teams selected" result: state, history, chat, overlay.
    void StartMatch(List<TeamPlayer> players, BalanceResult result, string format)
    {
        int id = _settings.NextMatchId++;
        SaveSettings();

        _lastBalance = new LastBalanceData
        {
            MatchId = id,
            Players = players,
            Format = format,
            Result = result
        };
        SaveCurrentMatch();

        _matches.Add(new MatchRecord
        {
            Id = id,
            Format = format,
            Mode = _settings.TeamMode,
            Blue = result.Blue,
            Orange = result.Orange,
            BlueAvg = result.BlueAvgMmr,
            OrangeAvg = result.OrangeAvgMmr,
            Diff = result.MmrDiff,
            CreatedAt = Now(),
            Activity = _settings.Activity,
            Category = CategoryFor(format),
            Group = _settings.Activity == "casual" && false /* casual group style retired: casual = teams, like competitive */
        });
        TrimAndSaveMatches();

        PostTeams(result);

        // [NEW][KOTH] King of the Hill: the FIRST game closes the queue, and the starters are called out by name.
        if (_settings.Activity == "koth" && !_settings.KothStarted)
        {
            _settings.KothStarted = true;
            _settings.QueueOpen = false;
            SaveSettings();
            var starters = result.Blue.Concat(result.Orange).Select(p => "@" + p.Username);
            Say("👑 KING OF THE HILL IS STARTING" + (string.IsNullOrEmpty(_cmdUser) ? "" : " (picked by " + _cmdUser + ")") + "! Starting the game: " + string.Join(" ", starters) +
                ". The queue is now CLOSED. Everyone still waiting stays in line; the winners stay on.");
        }
        PublishState("teams_selected", "match " + id);
    }

    void TrimAndSaveMatches()
    {
        // [NOTE] Capped at 100. Wins/losses live on the Player, so nothing is lost.
        if (_matches.Count > 100)
            _matches = _matches.Skip(_matches.Count - 100).ToList();
        SaveMatches();
    }

    // ══════════════════════════════════════════════════════════════
    //  MMR RESOLUTION
    // ══════════════════════════════════════════════════════════════

    int ResolveMmr(string username, string format)
    {
        Player player;
        // [NEW][WEB] Fortnite customs balance by SR (our own system), never by Rocket League MMR / Tracker.
        if (IsFortnite())
            return _players.TryGetValue(username, out player) && player.Sr.HasValue ? player.Sr.Value : _settings.DefaultSr;
        if (!_players.TryGetValue(username, out player))
            return _settings.DefaultMmr;

        // 1. MMR set by a mod ("manual") or by the player themself ("self") always wins over the tracker.
        if ((player.MmrSource == "manual" || player.MmrSource == "self") && player.PeakMmr.HasValue)
            return player.PeakMmr.Value;

        // [FIX] Crashed with NullReferenceException if a player had no GameId.
        if (string.IsNullOrEmpty(player.GameId))
            return player.PeakMmr ?? _settings.DefaultMmr;

        // 2. Cache (24h). [FIX] Keyed per playlist now, since 2v2 and 3v3 MMR differ.
        string cacheKey = player.GameId.ToLower() + "|" + format;
        MmrCacheEntry cached;
        if (_mmrCache.TryGetValue(cacheKey, out cached) && Now() - cached.FetchedAt < 86400)
            return cached.PeakMmr;

        // 3. Tracker Network (off by default; also paused for 1 h after a block)
        if (!_settings.TrackerLookupEnabled || DateTime.UtcNow < _trnPausedUntil)
            return player.PeakMmr ?? _settings.DefaultMmr;
        TrnResult result = LookupEpicProfile(player.GameId, format);
        if (result.Mmr.HasValue)
        {
            StoreApiMmr(player, cacheKey, result.Mmr.Value);
            return result.Mmr.Value;
        }

        // 4. Previously stored, 5. default
        return player.PeakMmr ?? _settings.DefaultMmr;
    }

    void StoreApiMmr(Player player, string cacheKey, int mmr)
    {
        _mmrCache[cacheKey] = new MmrCacheEntry { PeakMmr = mmr, FetchedAt = Now() };
        if (player.MmrSource != "manual" && player.MmrSource != "self")
        {
            player.PeakMmr = mmr;
            player.MmrSource = "api";
            player.MmrLastUpdated = Now();
        }
        SaveMmrCache();
        SavePlayers();
    }

    TrnResult LookupEpicProfile(string gameId, string format)
    {
        // TRN rate limit: at most one request every 2 seconds
        TimeSpan elapsed = DateTime.UtcNow - _lastTrnRequest;
        if (elapsed.TotalMilliseconds < 2000)
            System.Threading.Thread.Sleep(2000 - (int)elapsed.TotalMilliseconds);
        _lastTrnRequest = DateTime.UtcNow;

        string url = "https://api.tracker.gg/api/v2/rocket-league/standard/profile/epic/"
                     + Uri.EscapeDataString(gameId);

        try
        {
            string body = CurlGet(url);
            if (string.IsNullOrWhiteSpace(body))
                return new TrnResult { ProfileFound = null };

            // [FIX] TRN sometimes returns a Cloudflare HTML page instead of JSON;
            // the old code threw a parse exception. Now it's reported as an API error.
            if (!body.TrimStart().StartsWith("{"))
            {
                CPH.LogWarn("[BVQ] TRN returned non-JSON (likely blocked) for epic:" + gameId + "; pausing lookups for 1 h");
                _trnPausedUntil = DateTime.UtcNow.AddHours(1);
                return new TrnResult { ProfileFound = null };
            }

            var data = JObject.Parse(body);

            if (data["errors"] != null)
            {
                string errMsg = data["errors"]?[0]?["message"]?.ToString() ?? "";
                if (errMsg.IndexOf("not found", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    errMsg.IndexOf("not been found", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    CPH.LogInfo("[BVQ] TRN player not found: epic:" + gameId);
                    return new TrnResult { ProfileFound = false };
                }
                CPH.LogWarn("[BVQ] TRN error for epic:" + gameId + " — " + errMsg);
                return new TrnResult { ProfileFound = null };
            }

            var segments = data["data"]?["segments"];
            if (segments == null)
                return new TrnResult { ProfileFound = true };

            string wanted = FormatPlaylist.ContainsKey(format) ? FormatPlaylist[format] : "Ranked Doubles 2v2";
            int? preferred = null;
            int? bestAny = null;

            foreach (var segment in segments)
            {
                if (segment["type"]?.ToString() != "playlist") continue;
                string name = segment["metadata"]?["name"]?.ToString() ?? "";
                if (!name.StartsWith("Ranked")) continue;

                int? peak = ReadInt(segment["stats"]?["peakRating"]?["value"]);
                int? rating = ReadInt(segment["stats"]?["rating"]?["value"]);
                int? mmr = peak ?? rating;
                if (!mmr.HasValue) continue;

                if (name == wanted) preferred = mmr;
                if (!bestAny.HasValue || mmr > bestAny) bestAny = mmr;
            }

            // [NEW] Use the playlist that matches the format, else best ranked playlist.
            return new TrnResult { ProfileFound = true, Mmr = preferred ?? bestAny };
        }
        catch (Exception ex)
        {
            CPH.LogWarn("[BVQ] TRN error for epic:" + gameId + ": " + ex.Message);
            return new TrnResult { ProfileFound = null };
        }
    }

    // [FIX] (int?)token throws on JSON null or decimals like 1234.0 — this doesn't.
    static int? ReadInt(JToken token)
    {
        if (token == null || token.Type == JTokenType.Null) return null;
        double d;
        if (double.TryParse(token.ToString(), System.Globalization.NumberStyles.Float,
                            System.Globalization.CultureInfo.InvariantCulture, out d))
            return (int)Math.Round(d);
        return null;
    }

    string CurlGet(string url)
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "curl",
                // [FIX] --max-time makes curl itself give up, so the bot can't hang forever.
                Arguments = "-s -L --max-time 12 "
                          + "-H \"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\" "
                          + "-H \"Accept: application/json\" "
                          + "\"" + url + "\"",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using (var proc = Process.Start(psi))
            {
                // [FIX] stderr was redirected but never read; a full stderr buffer can deadlock.
                var stderrTask = proc.StandardError.ReadToEndAsync();
                string output = proc.StandardOutput.ReadToEnd();

                // [FIX] Reading ExitCode on a process that hasn't exited throws.
                if (!proc.WaitForExit(15000))
                {
                    try { proc.Kill(); } catch { }
                    CPH.LogWarn("[BVQ] curl timed out");
                    return null;
                }
                if (proc.ExitCode != 0)
                {
                    CPH.LogWarn("[BVQ] curl exited with code " + proc.ExitCode + ": " + stderrTask.Result);
                    return null;
                }
                return output;
            }
        }
        catch (Exception ex)
        {
            CPH.LogWarn("[BVQ] curl failed: " + ex.Message);
            return null;
        }
    }

    int? ParseRankToMmr(string input)
    {
        if (string.IsNullOrWhiteSpace(input)) return null;
        int v;
        return RankMap.TryGetValue(input.Trim(), out v) ? (int?)v : null;
    }

    // ══════════════════════════════════════════════════════════════
    //  COMMAND HANDLERS — viewers
    // ══════════════════════════════════════════════════════════════

    bool HandleRegister(string user, string input, bool isPrivileged)
    {
        if (string.IsNullOrEmpty(input))
        {
            Say("@" + user + " Usage: !register <EpicID> — Use your Epic Games display name.");
            return true;
        }

        string targetUser = user;
        string gameId;

        // [FIX] Epic names can contain spaces. The old code treated ANY two-word
        // input from a mod as "<username> <EpicID>", so a mod registering
        // themselves as "Cool Penguin" got registered as user "cool" = "Penguin".
        // Mod override now requires the @:  !register @viewer Their Epic Name
        if (isPrivileged && input.StartsWith("@"))
        {
            string[] parts = input.Split(new[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 2)
            {
                Say("@" + user + " Usage: !register @username <EpicID>");
                return true;
            }
            targetUser = parts[0].TrimStart('@').ToLower();
            gameId = parts[1].Trim();
        }
        else
        {
            if (_players.ContainsKey(user) && !isPrivileged)
            {
                Say("@" + user + " You're already registered as " +
                    _players[user].GameId + ". Ask a mod to update your Epic ID if needed.");
                return true;
            }
            gameId = input;
        }

        // Legacy "platform:id" input — strip the prefix
        int colon = gameId.IndexOf(':');
        if (colon > 0)
        {
            string prefix = gameId.Substring(0, colon).ToLower();
            if (prefix == "epic" || prefix == "steam" || prefix == "psn" || prefix == "xbox")
                gameId = gameId.Substring(colon + 1).Trim();
        }

        if (string.IsNullOrEmpty(gameId))
        {
            Say("@" + user + " You need to provide an Epic ID.");
            return true;
        }

        TrnResult result = (_settings.TrackerLookupEnabled && DateTime.UtcNow >= _trnPausedUntil)
            ? LookupEpicProfile(gameId, _settings.DefaultFormat)
            : new TrnResult { ProfileFound = null };
        if (result.ProfileFound == false)
        {
            Say("@" + user + " Could not find \"" + gameId +
                "\" on Tracker Network. Make sure you're using the exact Epic Games display name.");
            return true;
        }
        // [NOTE] If TRN is down (ProfileFound == null) registration still succeeds,
        // same as before, so a TRN outage never blocks stream games.

        Player player;
        if (!_players.TryGetValue(targetUser, out player))
        {
            player = new Player { Username = targetUser, MmrSource = "none" };
            _players[targetUser] = player;
        }
        player.Platform = "epic";
        player.GameId = gameId;

        if (result.Mmr.HasValue)
            StoreApiMmr(player, gameId.ToLower() + "|" + _settings.DefaultFormat, result.Mmr.Value);
        else
            SavePlayers();

        string mmrMsg = result.Mmr.HasValue
            ? " MMR: " + result.Mmr.Value
            : " (no MMR found — a mod can set it with !setmmr)";

        if (targetUser != user)
            Say("@" + user + " Registered " + targetUser + " as " + gameId + "!" + mmrMsg);
        else
            Say("@" + user + " Registered as " + gameId + "!" + mmrMsg);
        return true;
    }

    bool HandleJoin(string user)
    {
        if (!_players.ContainsKey(user))
        {
            Say("@" + user + " Register first: type !register YourEpicName (your exact Epic name, no < >), then !join.");
            return true;
        }

        if (!_settings.QueueOpen)
        {
            Say("@" + user + " The queue is closed right now. It opens when customs start, then type !join.");
            return true;
        }

        if (!IsStreamer(user) && StrikeTotal(_players[user]) >= MaxStrikes)
        {
            Say("@" + user + " You have " + MaxStrikes + " strikes, so you can't play customs right now. A temporary strike wears off after a day; permanent ones stay.");
            return true;
        }

        QueueEntry existing = GetEntry(user);
        if (existing != null)
        {
            int idx = GetWaitingQueue().FindIndex(e => e.Username == user);
            if (idx >= 0)
                Say("@" + user + " You're already in the queue at position #" + (idx + 1) + ".");
            else
                Say("@" + user + " You're in the current match!");
            return true;
        }

        if (IsStreamer(user) && !_settings.StreamerPlaying) { _settings.StreamerPlaying = true; SaveSettings(); }   // [NEW][WEB]
        AddToQueue(user);
        int pos = GetWaitingQueue().FindIndex(e => e.Username == user) + 1;
        Say("@" + user + " You joined the queue at position #" + pos + "!");
        PublishState("queue_update", user + " joined");
        return true;
    }

    bool HandleLeave(string user)
    {
        // [NEW][WEB] The streamer typing !leave = sitting out (otherwise the next !balance re-adds him).
        if (IsStreamer(user) && _settings.StreamerPlaying) { _settings.StreamerPlaying = false; SaveSettings(); }
        if (RemoveFromQueue(user))
        {
            Say("@" + user + " You left the queue.");
            PublishState("queue_update", user + " left");
        }
        else
        {
            Say("@" + user + " You're not in the queue.");
        }
        return true;
    }

    bool HandlePos(string user)
    {
        QueueEntry entry = GetEntry(user);
        if (entry == null)
        {
            Say("@" + user + " You're not in the queue.");
            return true;
        }

        var waiting = GetWaitingQueue();
        int idx = waiting.FindIndex(e => e.Username == user);
        if (idx >= 0)
            Say("@" + user + " You're #" + (idx + 1) + " of " + waiting.Count + " in the queue.");
        else
            Say("@" + user + " You're in the current match!");
        return true;
    }

    bool HandleRank(string user)
    {
        Player player;
        if (!_players.TryGetValue(user, out player))
        {
            Say("@" + user + " You're not registered. Use: !register <EpicID>");
            return true;
        }
        if (!player.PeakMmr.HasValue)
        {
            Say("@" + user + " No MMR on file. A mod can set it with !setmmr, or it will be fetched from Tracker Network.");
            return true;
        }
        Say("@" + user + " Your MMR: " + player.PeakMmr + " (" + SourceLabel(player.MmrSource) + ")");
        return true;
    }

    bool HandleLobby(string user)
    {
        if (_lastBalance == null || _lastBalance.Result == null)
        {
            Say("@" + user + " No active lobby right now.");
            return true;
        }
        PostTeams(_lastBalance.Result);
        return true;
    }

    // [NEW] !stats [user]
    bool HandleStats(string user, string input)
    {
        string target = string.IsNullOrEmpty(input) ? user : input.Split(' ')[0].TrimStart('@').ToLower();
        Player p;
        if (!_players.TryGetValue(target, out p))
        {
            Say("@" + user + " " + target + " is not registered.");
            return true;
        }
        Say("@" + user + " " + target + ": " + p.Wins + "W / " + p.Losses + "L — " + p.Points + " pts");
        return true;
    }

    // [NEW] !topwins — leaderboard by wins (ties: points)
    bool HandleTop()
    {
        var top = _players.Values.Where(p => p.Wins + p.Losses > 0)
                         .OrderByDescending(p => p.Wins).ThenByDescending(p => p.Points)
                         .Take(5).ToList();
        if (top.Count == 0)
        {
            Say("No results recorded yet.");
            return true;
        }
        Say("🏆 Top Wins: " + string.Join(" | ", top.Select((p, i) =>
            (i + 1) + ". " + p.Username + " " + p.Wins + "W-" + p.Losses + "L (" + p.Points + " pts)")));
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  COMMAND HANDLERS — mods
    // ══════════════════════════════════════════════════════════════

    bool HandleQueue(string user, string input, bool isPrivileged)
    {
        string sub = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();

        if ((sub == "open" || sub == "close" || sub == "clear") && !isPrivileged)
        {
            Say("@" + user + " Only mods and the broadcaster can manage the queue.");
            return true;
        }

        switch (sub)
        {
            case "open":
                _settings.QueueOpen = true;
                SaveSettings();
                Say("The queue is now OPEN! Type !join to enter.");
                PublishState("queue_open", null);
                break;

            case "close":
                _settings.QueueOpen = false;
                SaveSettings();
                Say("The queue is now CLOSED. No new joins accepted.");
                PublishState("queue_close", null);
                break;

            case "clear":
                ClearQueue();
                Say("The queue has been cleared and closed.");
                PublishState("queue_close", "cleared");
                break;

            case "list":
            {
                var entries = GetWaitingQueue();
                if (entries.Count == 0)
                {
                    Say("The queue is empty.");
                    return true;
                }

                var lines = entries.Take(10).Select((e, i) =>
                {
                    Player p;
                    _players.TryGetValue(e.Username, out p);
                    string mmrStr = (p != null && p.PeakMmr.HasValue) ? " (" + p.PeakMmr + ")" : "";
                    return (i + 1) + ". " + e.Username + mmrStr;
                });
                string more = entries.Count > 10 ? " (+" + (entries.Count - 10) + " more)" : "";
                Say("Queue (" + entries.Count + "): " + string.Join(" | ", lines) + more);
                PublishState("queue_show", null);   // [NEW][OBS] makes the queue overlay pop up for a few seconds
                break;
            }

            default:
            {
                int count = GetWaitingCount();
                string status = _settings.QueueOpen ? "OPEN" : "CLOSED";
                Say("Queue is " + status + " — " + count + " player" + (count == 1 ? "" : "s") + " waiting.");
                PublishState("queue_show", null);   // [NEW][OBS] makes the queue overlay pop up for a few seconds
                break;
            }
        }
        return true;
    }

    // [NEW][WEB] !streamer in|out  (mods / broadcaster; also the website switch)
    bool HandleStreamer(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change that."); return true; }
        string sub = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        string me = _settings.StreamerName;
        if (sub == "in")
        {
            _settings.StreamerPlaying = true;
            SaveSettings();
            EnsureStreamerQueued();
            // If a match is already running with an empty seat and he isn't in it, he takes the seat right away
            // (the team with fewer players, Blue when level).
            if (_lastBalance != null && _lastBalance.Result != null && !_lastBalance.ResultRecorded)
            {
                var res = _lastBalance.Result;
                int size = GetTeamSize(_lastBalance.Format);
                bool inMatch = res.Blue.Concat(res.Orange).Any(p => p.Username == me);
                if (!inMatch && (res.Blue.Count < size || res.Orange.Count < size))
                {
                    var dest = (res.Blue.Count <= res.Orange.Count && res.Blue.Count < size) || res.Orange.Count >= size ? res.Blue : res.Orange;
                    var entry = _queue.FirstOrDefault(e => e.Username == me && e.Status == "waiting");
                    if (entry != null) { entry.Status = "active"; CompactPositions(); }
                    dest.Add(new TeamPlayer { Username = me, Mmr = ResolveMmr(me, _lastBalance.Format) });
                    RefreshMatch("streamer back in");
                }
            }
            Say(me + " is IN the next matches.");
        }
        else if (sub == "out")
        {
            _settings.StreamerPlaying = false;
            SaveSettings();
            // Leave the waiting line; if he's in the current match he finishes it.
            if (_queue.RemoveAll(e => e.Username == me && e.Status == "waiting") > 0) CompactPositions();
            Say(me + " is sitting out. His seat goes to the next player in the queue.");
        }
        else
        {
            Say("@" + user + " Usage: !streamer <in|out> (now: " + (_settings.StreamerPlaying ? "in" : "out") + ")");
            return true;
        }
        PublishState("settings", "streamer " + sub);
        return true;
    }

    // ── OBS CONTROL  [NEW][OBS] ────────────────────────────────────
    // Streamer.bot is connected to OBS, and this code runs inside Streamer.bot, so it can switch scenes and show / hide sources.
    // The OBS methods are called by NAME (reflection) so this file still compiles on a Streamer.bot version where one of them is missing.
    // They are: ObsIsConnected, ObsSetScene(scene), ObsShowSource(scene, source), ObsHideSource(scene, source).
    static string _obsScene = "";                       // label of the scene we switched to last
    static string _twitchGame = "";                     // the Twitch category, as the website sees it
    static DateTime _lastGameCheck = DateTime.MinValue, _lastObsConnCheck = DateTime.MinValue;
    static bool _obsConnected;
    static readonly Dictionary<string, bool> _obsVis = new Dictionary<string, bool>();

    // One time: a settings.json saved by the first OBS version had the auto switch OFF and the Starting Soon / Be Right Back scenes.
    void MigrateObsDefaults()
    {
        if (_settings.ObsMigrated) return;
        string v;
        if (_settings.ObsScenes.TryGetValue("Starting Soon", out v) && v == "Starting Soon") _settings.ObsScenes.Remove("Starting Soon");
        if (_settings.ObsScenes.TryGetValue("Be Right Back", out v) && v == "BRB") _settings.ObsScenes.Remove("Be Right Back");
        _settings.ObsAutoSwitch = true;
        _settings.ObsMigrated = true;
        SaveSettings();
    }

    DateTime _lastLiveCheck = DateTime.MinValue;

    static string ObsNorm(string s) { return new string((s ?? "").ToLower().Where(char.IsLetterOrDigit).ToArray()); }

    // Finds a label in a list, ignoring case, spaces and punctuation ("rocket league" == "Rocket League").
    static string ObsFindLabel(IEnumerable<string> labels, string wanted)
    {
        string w = ObsNorm(wanted);
        if (w.Length == 0) return null;
        return labels.FirstOrDefault(l => ObsNorm(l) == w);
    }

    bool ObsInvoke(string name, out object result, params object[] args)
    {
        result = null;
        try
        {
            var seen = new List<System.Reflection.MethodInfo>(CPH.GetType().GetMethods());
            foreach (var it in CPH.GetType().GetInterfaces()) seen.AddRange(it.GetMethods());
            foreach (var m in seen)
            {
                if (m.Name != name) continue;
                var ps = m.GetParameters();
                if (ps.Length < args.Length) continue;
                var call = new object[ps.Length];
                bool ok = true;
                for (int i = 0; i < ps.Length; i++)
                {
                    if (i < args.Length) call[i] = args[i];
                    else if (ps[i].IsOptional) call[i] = (ps[i].DefaultValue == null || ps[i].DefaultValue is DBNull || ps[i].DefaultValue == Type.Missing) ? (ps[i].ParameterType == typeof(int) ? (object)0 : null) : ps[i].DefaultValue;
                    else { ok = false; break; }
                }
                if (!ok) continue;
                result = m.Invoke(CPH, call);
                return true;
            }
        }
        catch (Exception ex) { CPH.LogWarn("[BVQ] OBS call " + name + " failed: " + ex.Message); }
        return false;
    }

    bool ObsOk(string name, params object[] args)
    {
        object r;
        if (!ObsInvoke(name, out r, args)) return false;
        return !(r is bool) || (bool)r;
    }

    bool ObsIsConnected()
    {
        if ((DateTime.UtcNow - _lastObsConnCheck).TotalSeconds < 10) return _obsConnected;
        _lastObsConnCheck = DateTime.UtcNow;
        object r;
        _obsConnected = ObsInvoke("ObsIsConnected", out r) && (r is bool ? (bool)r : true);
        return _obsConnected;
    }

    bool SwitchObsScene(string label)
    {
        string scene;
        if (!_settings.ObsEnabled || !_settings.ObsScenes.TryGetValue(label, out scene)) return false;
        if (!ObsOk("ObsSetScene", scene)) return false;
        _obsScene = label;
        PublishState("obs", "scene " + label);
        return true;
    }

    // [NEW] Sets the Twitch category through Streamer.bot (called by name, so a missing method can't break the compile).
    bool SetTwitchGame(string name)
    {
        object r;
        if (ObsInvoke("SetChannelGame", out r, name) || ObsInvoke("TwitchSetChannelGame", out r, name))
        {
            if (r is bool && !(bool)r) return false;
            _twitchGame = name;   // so the 30 s category poll doesn't treat our own change as a new one
            return true;
        }
        return false;
    }

    // [NEW] "!activity rl|fn ...": move to that game's OBS scene (even with the auto switch off) and set the Twitch category.
    void SwitchToGame(string g)
    {
        string name;
        if (!_settings.TwitchGameNames.TryGetValue(g, out name)) name = g == "fn" ? "Fortnite" : "Rocket League";
        string label;
        if (_settings.ObsEnabled && _settings.ObsGameScenes.TryGetValue(name, out label) && _settings.ObsScenes.ContainsKey(label) && _obsScene != label)
        {
            if (!SwitchObsScene(label)) ReportProblem("OBS: could not switch to the " + label + " scene for " + name + " (is OBS connected in Streamer.bot?)");
        }
        if (_settings.ActivitySetsGame && _twitchGame != name)
        {
            if (SetTwitchGame(name)) Say("Twitch category set to " + name + ".");
            else ReportProblem("Could not set the Twitch category to \"" + name + "\" (Streamer.bot needs the SetChannelGame action / Twitch permission)");
        }
        PublishState("obs", "game " + name);
    }

    // Auto switch: the scene follows the game. Called when the Twitch category changes and when a mod starts an activity.
    void ObsGameSwitch(string game, string why)
    {
        if (!_settings.ObsEnabled || !_settings.ObsAutoSwitch) return;
        string label;
        if (!_settings.ObsGameScenes.TryGetValue(game, out label) || !_settings.ObsScenes.ContainsKey(label)) return;
        if (_obsScene == label) return;
        if (SwitchObsScene(label)) CPH.LogInfo("[BVQ] OBS auto switch -> " + label + " (" + why + ")");
    }

    object BuildObsState()
    {
        return new
        {
            enabled = _settings.ObsEnabled,
            connected = _settings.ObsEnabled && ObsIsConnected(),
            auto = _settings.ObsAutoSwitch,
            scene = _obsScene,
            twitchGame = _twitchGame,
            scenes = _settings.ObsScenes.Keys.ToList(),
            sources = _settings.ObsSources.Select(s => new { label = s.Label, visible = _obsVis.ContainsKey(s.Label) ? (bool?)_obsVis[s.Label] : null }).ToList()
        };
    }

    // !scene <label>   (mods)
    bool HandleObsScene(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can switch scenes."); return true; }
        string label = ObsFindLabel(_settings.ObsScenes.Keys, input);
        if (label == null) { Say("@" + user + " Usage: !scene <" + string.Join(" | ", _settings.ObsScenes.Keys) + ">"); return true; }
        if (SwitchObsScene(label)) Say("OBS scene: " + label + ".");
        else { Say("@" + user + " Could not switch OBS to " + label + ". Is OBS connected in Streamer.bot?"); ReportProblem("OBS: could not switch to \"" + label + "\" (is OBS connected in Streamer.bot, and does the scene name match?)"); }
        return true;
    }

    // !source <on|off|toggle> <label>   (mods)
    bool HandleObsSource(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change sources."); return true; }
        string[] parts = (input ?? "").Trim().Split(new[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
        string action = parts.Length > 0 ? parts[0].ToLower() : "";
        ObsSourceCfg cfg = parts.Length > 1 ? _settings.ObsSources.FirstOrDefault(s => ObsNorm(s.Label) == ObsNorm(parts[1])) : null;
        if ((action != "on" && action != "off" && action != "toggle") || cfg == null)
        { Say("@" + user + " Usage: !source <on|off|toggle> <" + string.Join(" | ", _settings.ObsSources.Select(s => s.Label)) + ">"); return true; }
        bool show = action == "on" || (action == "toggle" && !(_obsVis.ContainsKey(cfg.Label) && _obsVis[cfg.Label]));
        var scenes = string.IsNullOrEmpty(cfg.Scene) ? _settings.ObsScenes.Values.Distinct().ToList() : new List<string> { cfg.Scene };
        bool any = false;
        foreach (var sc in scenes) if (ObsOk(show ? "ObsShowSource" : "ObsHideSource", sc, cfg.Source)) any = true;
        if (!any) { Say("@" + user + " Could not change " + cfg.Label + " in OBS. Is OBS connected, and are the scene / source names right (ObsSources in settings.json)?"); return true; }
        _obsVis[cfg.Label] = show;
        Say(cfg.Label + ": " + (show ? "ON" : "OFF") + ".");
        PublishState("obs", "source " + cfg.Label + " " + (show ? "on" : "off"));
        return true;
    }

    // !obs auto on|off  /  !obs status   (mods)
    bool HandleObs(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can use that."); return true; }
        string[] p = (input ?? "").Trim().ToLower().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        if (p.Length >= 2 && p[0] == "auto" && (p[1] == "on" || p[1] == "off"))
        {
            _settings.ObsAutoSwitch = p[1] == "on";
            SaveSettings();
            Say("OBS auto switch is " + (_settings.ObsAutoSwitch ? "ON: the scene follows the game." : "OFF."));
            PublishState("obs", "auto " + p[1]);
            return true;
        }
        Say("OBS: " + (ObsIsConnected() ? "connected" : "NOT connected") + ", scene " + (_obsScene == "" ? "unknown" : _obsScene) + ", auto switch " + (_settings.ObsAutoSwitch ? "ON" : "OFF") + ", Twitch game " + (_twitchGame == "" ? "unknown" : _twitchGame) + ". Usage: !scene <name>, !source <on|off|toggle> <name>, !obs auto <on|off>");
        return true;
    }

    // ── GAME MODES  [NEW][WEB] ─────────────────────────────────────
    // Standings are kept per category: the format for normal games (2v2, 3v3...), or "dropshot" / "rumble".
    // Which stats bucket a result goes into (Player.Modes key / MatchRecord.Category). RL: the format (2v2, 3v3...) or dropshot / rumble | koth | FN: boxfights, zonewars.
    string CategoryFor(string format)
    {
        if (_settings.Activity == "boxfights" || _settings.Activity == "zonewars" || _settings.Activity == "koth") return _settings.Activity;   // Fortnite customs + King of the Hill
        string gm = _settings.GameMode ?? "standard";
        return gm == "dropshot" || gm == "rumble" ? gm : (format ?? "3v3");
    }

    // Fortnite categories do not touch the overall (Rocket League) wins / points.
    static bool IsFnCategory(string cat) { return cat == "boxfights" || cat == "zonewars" || cat == "koth"; }
    static string FnCategoryLabel(string cat)
    {
        return cat == "boxfights" ? "Boxfights" : cat == "koth" ? "King of the Hill" : "Zone Wars";
    }

    void BumpMode(Player p, string category, int dw, int dl, int dp)
    {
        if (string.IsNullOrEmpty(category)) return;
        if (p.Modes == null) p.Modes = new Dictionary<string, ModeStat>();
        ModeStat m;
        if (!p.Modes.TryGetValue(category, out m)) { m = new ModeStat(); p.Modes[category] = m; }
        m.Wins = Math.Max(0, m.Wins + dw); m.Losses = Math.Max(0, m.Losses + dl); m.Points = Math.Max(0, m.Points + dp);
    }

    // One time: older results had no per-mode stats, so rebuild them from the saved matches (newest 100).
    void BackfillModes()
    {
        if (_settings.ModesBackfilled) return;
        foreach (var rec in _matches)
        {
            if (rec.Winner == null || !IsCounted(rec)) continue;
            string cat = rec.Category ?? rec.Format;
            int pw = rec.PtsWin ?? _settings.PointsWin, pl = rec.PtsLoss ?? _settings.PointsLoss;
            foreach (var tp in (rec.Winner == "blue" ? rec.Blue : rec.Orange) ?? new List<TeamPlayer>())
            { Player p; if (_players.TryGetValue(tp.Username, out p)) BumpMode(p, cat, 1, 0, pw); }
            foreach (var tp in (rec.Winner == "blue" ? rec.Orange : rec.Blue) ?? new List<TeamPlayer>())
            { Player p; if (_players.TryGetValue(tp.Username, out p)) BumpMode(p, cat, 0, 1, pl); }
        }
        _settings.ModesBackfilled = true;
        SavePlayers(); SaveSettings();
    }

    // !casual group|teams (mods): casual customs show ONE group grid (default) or random Orange vs Blue teams.
    // [CHANGE] Casual always uses teams now (exactly like competitive), so there's nothing to switch.
    bool HandleCasualStyle(string user, string input, bool isPrivileged)
    {
        _settings.CasualStyle = "teams";
        SaveSettings();
        Say("@" + user + " Casual customs always use teams now, just like competitive (same team mode).");
        return true;
    }

    // !gamemode standard|dropshot|rumble (mods). Dropshot / Rumble have their own standings tabs.
    bool HandleGameMode(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change the game mode."); return true; }
        string gm = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (gm != "standard" && gm != "dropshot" && gm != "rumble")
        { Say("@" + user + " Usage: !gamemode <standard|dropshot|rumble> - Current: " + (_settings.GameMode ?? "standard")); return true; }
        bool changed = gm != (_settings.GameMode ?? "standard");
        _settings.GameMode = gm;
        // Dropshot and Rumble start at 3v3 (change it with !format any time, 1v1 to 4v4 works in every mode).
        if (changed && gm != "standard") _settings.DefaultFormat = "3v3";
        SaveSettings();
        Say("Game mode: " + (gm == "standard" ? "standard (counts as " + _settings.DefaultFormat + ")" : gm + ", " + _settings.DefaultFormat) + ". Takes effect on the next match.");
        PublishState("settings", "gamemode " + gm);
        _standingsDirty = true;
        return true;
    }

    // ── MATCH HISTORY FIXES  [NEW][WEB] ───────────────────────────
    // For a mis-typed result: change who won, or remove the match. Wins, losses and points are
    // reversed and re-applied exactly (using the points that were given at the time).
    bool IsCounted(MatchRecord m)
    {
        // Old records (before Counted existed) counted whenever they had a winner.
        return m.Counted ?? (m.Winner != null && ActivityCounts(m.Activity));
    }

    void ApplyMatchStats(MatchRecord rec, string winner, int sign)
    {
        if (IsPracticeMatch(rec)) return;
        int pw = rec.PtsWin ?? _settings.PointsWin, pl = rec.PtsLoss ?? _settings.PointsLoss;
        var winners = winner == "blue" ? rec.Blue : rec.Orange;
        var losers = winner == "blue" ? rec.Orange : rec.Blue;
        foreach (var tp in winners ?? new List<TeamPlayer>())
        {
            Player p;
            if (_players.TryGetValue(tp.Username, out p)) { if (!IsFnCategory(rec.Category)) { p.Wins = Math.Max(0, p.Wins + sign); p.Points = Math.Max(0, p.Points + sign * pw); } BumpMode(p, rec.Category ?? rec.Format, sign, 0, sign * pw); }
        }
        foreach (var tp in losers ?? new List<TeamPlayer>())
        {
            Player p;
            if (_players.TryGetValue(tp.Username, out p)) { if (!IsFnCategory(rec.Category)) { p.Losses = Math.Max(0, p.Losses + sign); p.Points = Math.Max(0, p.Points + sign * pl); } BumpMode(p, rec.Category ?? rec.Format, 0, sign, sign * pl); }
        }
        SavePlayers();
    }

    // !matchwin <id> <blue|orange>
    bool HandleMatchWin(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can fix matches."); return true; }
        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        int id;
        string team = parts.Length >= 2 ? parts[1].ToLower() : "";
        if (parts.Length < 2 || !int.TryParse(parts[0].TrimStart('#'), out id) || (team != "blue" && team != "orange"))
        { Say("@" + user + " Usage: !matchwin <match id> <blue|orange>"); return true; }
        var rec = _matches.FirstOrDefault(m => m.Id == id);
        if (rec == null) { Say("@" + user + " Match #" + id + " isn't in the history."); return true; }
        if (rec.Winner == team) { Say("@" + user + " Match #" + id + " already shows " + team + " as the winner."); return true; }
        bool counted = rec.Winner != null ? IsCounted(rec) : ActivityCounts(rec.Activity);
        if (rec.Winner != null && counted) ApplyMatchStats(rec, rec.Winner, -1);   // take back the old result
        rec.Winner = team;
        if (!rec.FinishedAt.HasValue) rec.FinishedAt = Now();
        rec.Counted = counted;
        if (!rec.PtsWin.HasValue) rec.PtsWin = _settings.PointsWin;
        if (!rec.PtsLoss.HasValue) rec.PtsLoss = _settings.PointsLoss;
        if (counted) ApplyMatchStats(rec, team, +1);                                  // apply the corrected one
        SaveMatches();
        if (_lastBalance != null && _lastBalance.MatchId == id)
        {
            _lastBalance.ResultRecorded = true; _lastBalance.Winner = team; SaveCurrentMatch();
        }
        Say("Match #" + id + " fixed: " + (team == "blue" ? "🔷 Blue" : "🔶 Orange") + " won." + (counted ? " Wins and points were corrected." : " (no points in this activity)"));
        PublishState("match_result", "fix " + id);
        return true;
    }

    // !matchdel <id>
    bool HandleMatchDel(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can remove matches."); return true; }
        string first = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "";
        int id;
        if (!int.TryParse(first.TrimStart('#'), out id)) { Say("@" + user + " Usage: !matchdel <match id>"); return true; }
        var rec = _matches.FirstOrDefault(m => m.Id == id);
        if (rec == null) { Say("@" + user + " Match #" + id + " isn't in the history."); return true; }
        if (_lastBalance != null && _lastBalance.MatchId == id)
        { Say("@" + user + " Match #" + id + " is the current lobby. Change its winner with !matchwin, or finish it (!next) first."); return true; }
        if (rec.Winner != null && IsCounted(rec)) ApplyMatchStats(rec, rec.Winner, -1);
        _matches.Remove(rec);
        SaveMatches();
        Say("Match #" + id + " was removed from the history" + (rec.Winner != null && IsCounted(rec) ? " and its wins/points were taken back." : "."));
        PublishState("match_result", "removed " + id);
        return true;
    }

    // [NEW][WEB] !activity competitive|casual|viewers|end
    // Only ONE activity owns the queue. Starting one ends the current match (its players
    // leave the queue; people waiting stay) and opens the queue for the new activity;
    // "end" closes and clears everything.
    bool HandleActivity(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change the activity."); return true; }
        // [NEW] Optional game prefix: !activity rl koth / !activity fn boxfights / !activity fn viewers. It keeps names that exist in
        // several games apart AND tells PinguinoB0t which game this is, so it also switches the OBS scene and the Twitch category.
        string[] tok = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.ToLower()).ToArray();
        string game = "";
        if (tok.Length >= 1 && (tok[0] == "rl" || tok[0] == "fn" || tok[0] == "rocketleague" || tok[0] == "fortnite"))
        {
            game = tok[0].StartsWith("r") ? "rl" : "fn";
            tok = tok.Skip(1).ToArray();
        }
        string sub = tok.Length > 0 ? tok[0] : "";
        if (game != "" && sub != "end" && sub != "none")
        {
            if (sub == "comp") sub = "competitive";
            if (game == "fn" && sub == "viewers") sub = "fnviewers";
            bool fnAct = sub == "boxfights" || sub == "zonewars" || sub == "fnviewers";
            bool known = fnAct || sub == "competitive" || sub == "casual" || sub == "koth" || sub == "viewers";
            if (!known || (game == "fn") != fnAct)
            {
                Say("@" + user + " Usage: !activity rl <competitive|casual|koth|viewers>  or  !activity fn <boxfights|zonewars|viewers>  (or !activity end)");
                return true;
            }
        }
        if (sub == "end" || sub == "none")
        {
            ClearQueue();
            _settings.Activity = "none";
            SaveSettings();
            Say("Customs are over. The queue is closed and cleared.");
            PublishState("activity", "none");
            return true;
        }
        string label = sub == "competitive" ? "Competitive Customs" : sub == "casual" ? "Casual Customs" : sub == "viewers" ? "Playing with Viewers"
            : sub == "koth" ? "King of the Hill"
            : sub == "boxfights" ? "Fortnite Boxfights" : sub == "zonewars" ? "Fortnite Zone Wars" : sub == "fnviewers" ? "Fortnite: Playing with Viewers" : null;
        if (label == null) { Say("@" + user + " Usage: !activity [rl|fn] <competitive|casual|koth|viewers|boxfights|zonewars|end> (now: " + _settings.Activity + ")"); return true; }
        // Switching activity removes everyone who was PLAYING (the match ends), but people
        // WAITING in the queue stay in line for the new activity.
        ClearPlaying();
        _settings.Activity = sub;
        _settings.KothStarted = false;     // King of the Hill: the queue stays open until its first game is picked
        _settings.KothWins = new Dictionary<string, int>();   // a new activity starts a fresh leaderboard
        _settings.QueueOpen = true;        // the new activity's queue opens right away
        SaveSettings();
        EnsureStreamerQueued();            // the streamer plays every match unless he's sitting out
        if (sub == "koth")
            Say("👑 NOW PLAYING: KING OF THE HILL! The queue is OPEN to everyone: type !join. It CLOSES as soon as the first game is picked. Winners stay on, losers are out, and the leaderboard counts WINS.");
        else
            Say("NOW PLAYING: " + label + (ActivityCounts(sub) ? " (balanced teams, stats count)" : " (random teams, no stats)") + ". The queue is OPEN! Type !join to enter.");
        if (game != "") SwitchToGame(game);   // [NEW] an explicit game prefix always moves the OBS scene and the Twitch category
        else ObsGameSwitch(IsFortnite() ? "Fortnite" : "Rocket League", "activity " + sub);   // [NEW][OBS] no prefix: only when the auto switch is on
        PublishState("activity", sub);
        return true;
    }

    // [NEW][WEB] Ends the current match for an activity switch: everyone in it leaves the queue,
    // players who were only waiting stay. (The streamer is re-added by EnsureStreamerQueued.)
    void ClearPlaying()
    {
        _queue.RemoveAll(e => e.Status == "active");
        _lastBalance = null;
        _pendingPicks = null;
        SaveCurrentMatch();
        CompactPositions();
    }

    // [NEW][WEB] Recompute averages after a drag changed who is on a team, then publish.
    void RefreshMatch(string detail)
    {
        var r = _lastBalance.Result;
        r.BlueAvgMmr = r.Blue.Count > 0 ? (int)Math.Round(r.Blue.Average(p => (double)p.Mmr)) : 0;
        r.OrangeAvgMmr = r.Orange.Count > 0 ? (int)Math.Round(r.Orange.Average(p => (double)p.Mmr)) : 0;
        r.MmrDiff = Math.Abs(r.BlueAvgMmr - r.OrangeAvgMmr);
        _lastBalance.Players = r.Blue.Concat(r.Orange).ToList();
        SaveCurrentMatch();
        var rec = _matches.FirstOrDefault(m => m.Id == _lastBalance.MatchId);
        if (rec != null)
        {
            rec.Blue = r.Blue; rec.Orange = r.Orange;
            rec.BlueAvg = r.BlueAvgMmr; rec.OrangeAvg = r.OrangeAvgMmr; rec.Diff = r.MmrDiff;
            SaveMatches();
        }
        PublishState("teams_selected", detail);
    }

    bool MatchOpenForEdits(string user)
    {
        if (_lastBalance == null || _lastBalance.Result == null || _lastBalance.ResultRecorded)
        {
            Say("@" + user + " There's no live match to change.");
            return false;
        }
        return true;
    }

    // [NEW][WEB] !move <user> <position>  -> reorder the waiting line (drag & drop).
    bool HandleMove(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can reorder the queue."); return true; }
        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        int pos;
        if (parts.Length < 2 || !int.TryParse(parts[1], out pos)) { Say("@" + user + " Usage: !move <user> <position>"); return true; }
        string target = parts[0].ToLower().TrimStart('@');
        var waiting = GetWaitingQueue();
        var entry = waiting.FirstOrDefault(e => e.Username == target);
        if (entry == null) { Say("@" + user + " " + target + " isn't waiting in the queue."); return true; }
        waiting.Remove(entry);
        pos = Math.Max(1, Math.Min(pos, waiting.Count + 1));
        waiting.Insert(pos - 1, entry);
        int n = 1;
        foreach (var e in _queue.Where(e => e.Status != "waiting").OrderBy(e => e.Position).ToList()) e.Position = n++;
        foreach (var e in waiting) e.Position = n++;
        CompactPositions();
        Say(target + " moved to #" + pos + " in the queue.");
        PublishState("queue_update", target + " moved");
        return true;
    }

    // [NEW][WEB] !out <user>  -> take a player out of the live match. Leaves an EMPTY
    // slot on their team, and they go back to the FRONT of the queue.
    bool HandleOut(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change the match."); return true; }
        string target = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower().TrimStart('@');
        if (!MatchOpenForEdits(user)) return true;
        var r = _lastBalance.Result;
        int removed = r.Blue.RemoveAll(p => p.Username == target) + r.Orange.RemoveAll(p => p.Username == target);
        if (removed == 0) { Say("@" + user + " " + target + " isn't in the match."); return true; }
        var entry = GetEntry(target);
        if (entry != null)
        {
            entry.Status = "waiting";
            entry.Position = _queue.Min(e => e.Position) - 1;
            CompactPositions();
        }
        Say(target + " is out of the match (back to the front of the queue). There's an empty slot.");
        RefreshMatch("out " + target);
        return true;
    }

    // [NEW][WEB] !in <user> <blue|orange>  -> put a queued player into a team's empty
    // slot, or move someone from the other team (drag & drop).
    bool HandleIn(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change the match."); return true; }
        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        string team = parts.Length >= 2 ? parts[1].ToLower() : "";
        if (parts.Length < 2 || (team != "blue" && team != "orange")) { Say("@" + user + " Usage: !in <user> <blue|orange>"); return true; }
        string target = parts[0].ToLower().TrimStart('@');
        if (!MatchOpenForEdits(user)) return true;
        var r = _lastBalance.Result;
        int teamSize = GetTeamSize(_lastBalance.Format);
        var dest = team == "blue" ? r.Blue : r.Orange;
        var other = team == "blue" ? r.Orange : r.Blue;
        if (dest.Any(p => p.Username == target)) { Say("@" + user + " " + target + " is already on " + team + "."); return true; }
        if (dest.Count >= teamSize) { Say("@" + user + " " + team + " has no empty slot. Drag someone out first."); return true; }

        TeamPlayer mover = other.FirstOrDefault(p => p.Username == target);
        if (mover != null)
        {
            other.Remove(mover);              // team -> team: keeps their MMR
            dest.Add(mover);
        }
        else
        {
            var entry = _queue.FirstOrDefault(e => e.Username == target && e.Status == "waiting");
            if (entry == null) { Say("@" + user + " " + target + " isn't waiting in the queue."); return true; }
            entry.Status = "active";
            CompactPositions();
            dest.Add(new TeamPlayer { Username = target, Mmr = ResolveMmr(target, _lastBalance.Format) });
        }
        Say(target + " joined " + team + ".");
        RefreshMatch("in " + target);
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  PROBLEMS + !check  [NEW][CHECK]
    //  Anything that goes wrong (unknown command, an exception, a failed OBS call, a failed self-check) is queued here and sent to the website,
    //  which shows it in RED in the mod log (the Logs pop-out and /mod/log). The same message is not repeated within a minute.
    // ══════════════════════════════════════════════════════════════
    void ReportProblem(string message)
    {
        if (string.IsNullOrEmpty(message)) return;
        if (message.Length > 300) message = message.Substring(0, 300);
        FileProblem(message.StartsWith("Check: ") ? "check" : "problem", message);
        long now = Now(), last;
        if (_problemSeen.TryGetValue(message, out last) && now - last < 60) return;
        _problemSeen[message] = now;
        if (_problems.Count < 20) _problems.Add(message);
        CPH.LogWarn("[BVQ] PROBLEM: " + message);
    }

    // problems.json (in %AppData%\BVQ next to settings.json): EVERY problem and check result, so it can be read, edited and cleared by hand
    // (or by an assistant): [{Id, At, Last, Kind: problem|check|ok, Message, Count, Status: open|fixed}]. "!problems" shows the count, "!problems clear" empties it.
    class ProblemRec { public string Id; public string At; public string Last; public string Kind; public string Message; public int Count; public string Status; }
    static readonly object _problemLock = new object();
    static List<ProblemRec> _problemFile;
    static List<string> _checkNotes = new List<string>();   // "Check passed" lines for the website log (green)
    List<ProblemRec> ProblemFile()
    {
        if (_problemFile == null) _problemFile = LoadJson<List<ProblemRec>>("problems.json") ?? new List<ProblemRec>();
        return _problemFile;
    }
    void FileProblem(string kind, string message)
    {
        try
        {
            lock (_problemLock)
            {
                var list = ProblemFile();
                string nowIso = DateTime.UtcNow.ToString("o");
                var same = list.FirstOrDefault(p => p.Kind == kind && p.Message == message && (kind == "ok" || p.Status == "open"));
                if (same != null && kind != "ok") { same.Count++; same.Last = nowIso; }
                else list.Add(new ProblemRec { Id = Guid.NewGuid().ToString("N").Substring(0, 8), At = nowIso, Last = nowIso, Kind = kind, Message = message, Count = 1, Status = kind == "ok" ? "fixed" : "open" });
                while (list.Count > 300) { var old = list.FirstOrDefault(p => p.Status == "fixed") ?? list[0]; list.Remove(old); }
                SaveJson("problems.json", list);
            }
        }
        catch (Exception ex) { CPH.LogWarn("[BVQ] problems.json: " + ex.Message); }
    }
    bool HandleProblems(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can see the problem list."); return true; }
        if ((input ?? "").Trim().ToLower() == "clear")
        {
            lock (_problemLock) { _problemFile = new List<ProblemRec>(); SaveJson("problems.json", _problemFile); }
            _problemSeen.Clear();
            Say("@" + user + " Problem list cleared.");
            return true;
        }
        int open; lock (_problemLock) open = ProblemFile().Count(p => p.Status == "open" && p.Kind != "ok");
        Say("@" + user + " " + (open == 0 ? "No open problems." : open + " open problem" + (open == 1 ? "" : "s") + " (see the red lines in the website log). !check runs a new check, !problems clear empties the list."));
        return true;
    }

    // !check (mods): looks at everything it can and tells you what is not right (the problems also appear in red in the website log).
    bool HandleCheck(string user, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can run a check."); return true; }
        var issues = new List<string>();
        if (string.IsNullOrEmpty(_settings.WebSyncKey) || string.IsNullOrEmpty(_settings.WebSyncUrl)) issues.Add("the website link is not set up (WebSyncKey / WebSyncUrl)");
        else if ((DateTime.UtcNow - _lastWebOk).TotalSeconds > 90) issues.Add("the website has not answered in the last 90 seconds");
        if (_settings.ObsEnabled && !ObsIsConnected()) issues.Add("OBS is not connected in Streamer.bot");
        if (!string.IsNullOrEmpty(_settings.OverlayDir) && !Directory.Exists(_settings.OverlayDir)) issues.Add("the overlay folder does not exist: " + _settings.OverlayDir);
        foreach (var g in _queue.GroupBy(e => e.Username).Where(g => g.Count() > 1)) issues.Add(g.Key + " is in the queue more than once");
        foreach (var e in _queue.Where(e => !_players.ContainsKey(e.Username))) issues.Add(e.Username + " is in the queue but not registered");
        if (_settings.Activity == "none" && _settings.QueueOpen) issues.Add("the queue is open but no activity is running");
        if (string.IsNullOrEmpty(_settings.StreamerName)) issues.Add("StreamerName is not set");
        // problems.json: earlier "Check:" problems that are no longer found are marked FIXED, and the result of this run is recorded.
        var nowFound = new HashSet<string>(issues.Select(i => "Check: " + i));
        lock (_problemLock)
        {
            foreach (var p in ProblemFile().Where(p => p.Kind == "check" && p.Status == "open" && !nowFound.Contains(p.Message))) { p.Status = "fixed"; p.Last = DateTime.UtcNow.ToString("o"); }
        }
        FileProblem("ok", issues.Count == 0 ? "Check passed: everything looks fine" : "Check found " + issues.Count + " problem" + (issues.Count == 1 ? "" : "s"));
        _checkNotes.Add(issues.Count == 0 ? "Check passed: everything looks fine ✔" : "Check found " + issues.Count + " problem" + (issues.Count == 1 ? "" : "s") + " (listed above in red)");
        if (issues.Count == 0)
            Say("@" + user + " Check: everything looks fine ✔ (website " + (DateTime.UtcNow - _lastWebOk).TotalSeconds.ToString("0") + " s ago, OBS " + (ObsIsConnected() ? "connected" : "off") + ", " + _queue.Count + " in the queue).");
        else
        {
            Say("@" + user + " Check found " + issues.Count + " problem" + (issues.Count == 1 ? "" : "s") + ": " + string.Join("; ", issues) + ".");
            foreach (var i in issues) ReportProblem("Check: " + i);
        }
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  KOTH (king of the hill) + !finish  [NEW][KOTH]
    //  The "Orange wins" / "Blue wins" buttons under the player lists on /mod/master send !finish <team>:
    //    result is recorded (stats, announcement), everyone who played leaves the queue, then
    //    KOTH off (default): the match is cleared ("remove all")
    //    KOTH on:            the winning team stays on and challengers are pulled in for the other side
    //  The mod page shows the new state at once; the website + OBS overlays keep the finished match (winner glow) for ResultHoldSeconds first.
    // ══════════════════════════════════════════════════════════════
    bool HandleFinish(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can finish a match."); return true; }
        string team = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (team != "blue" && team != "orange") { Say("@" + user + " Usage: !finish <blue|orange>"); return true; }
        if (_lastBalance == null || _lastBalance.Result == null) { Say("@" + user + " No active match."); return true; }
        // [FIX] The current game already has a result: pressing the OTHER team corrects the winner
        // (stats are swapped by !matchwin). Same team = nothing to do.
        if (_lastBalance.ResultRecorded)
        {
            if (_lastBalance.Winner == team) { Say("@" + user + " Match #" + _lastBalance.MatchId + " already shows " + team + " as the winner."); return true; }
            return HandleMatchWin(user, _lastBalance.MatchId + " " + team, isPrivileged);
        }

        var winners = (team == "blue" ? _lastBalance.Result.Blue : _lastBalance.Result.Orange).Select(w => w.Username).ToList();
        RecordResult(team);   // stats + announcement; everyone who played leaves the queue
        _holdMatch = BuildMatchObject();   // the finished match, with the winner, for the public view
        _holdUntil = Now() + Math.Max(0, _settings.ResultHoldSeconds);

        if (IsKothMode())
        {
            int need = GetTotalSlots(_settings.DefaultFormat) - winners.Count;
            var ws = new HashSet<string>(winners);
            int avail = _queue.Count(e => e.Status == "waiting" && !ws.Contains(e.Username));
            if (avail < need)
            {
                // Not enough challengers: the winners wait at the FRONT of the line.
                ClearPlaying();
                int front = _queue.Count > 0 ? _queue.Min(e => e.Position) - winners.Count : 1;
                foreach (var w in winners)
                    if (!_queue.Any(e => e.Username == w))
                        _queue.Add(new QueueEntry { Username = w, Position = front++, Status = "waiting", JoinedAt = Now() });
                CompactPositions();
                EnsureStreamerQueued();
                Say("KOTH: " + (team == "blue" ? "🔷 Blue" : "🔶 Orange") + " stays on, but there aren't enough challengers (need " + need + ", have " + avail + "). The winners wait at the front of the queue.");
            }
            else
            {
                bool keep = _settings.KothKeepWinnersTogether;
                _settings.KothKeepWinnersTogether = true;   // KOTH: the winners stay together on their colour
                try { DoKothRotateAndBalance(team); }
                finally { _settings.KothKeepWinnersTogether = keep; }
            }
        }
        else
        {
            ClearPlaying();         // "remove all": nobody stays
            EnsureStreamerQueued();
        }
        PublishState("match_finished", team);
        return true;
    }

    // !koth [on|off|true|false]: king of the hill. Anyone can ask; mods change it.
    bool HandleKoth(string user, string input, bool isPrivileged)
    {
        string v = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (v == "")
        {
            Say("@" + user + " KOTH (king of the hill) is " + (_settings.Koth ? "ON: the winning team stays on." : "OFF: everyone is out after a match."));
            return true;
        }
        if (!isPrivileged) { Say("@" + user + " Only mods can change KOTH."); return true; }
        bool on;
        if (v == "on" || v == "true" || v == "yes") on = true;
        else if (v == "off" || v == "false" || v == "no") on = false;
        else { Say("@" + user + " Usage: !koth <on|off>"); return true; }
        _settings.Koth = on;
        SaveSettings();
        Say("KOTH is now " + (on ? "ON: the winning team stays on." : "OFF: everyone is out after a match."));
        PublishState("koth", on ? "on" : "off");
        return true;
    }

    // [NEW][WEB] !match clear | fill | queue  (the three buttons under the teams on /mod/master)
    //   clear = end the match and REMOVE everyone in it from the queue. Nobody is pulled in.
    //   fill  = no match: make teams from the front of the queue. Match with empty slots: fill them from the queue.
    //   queue = end the match and put everyone in it back at the FRONT of the queue (in team order).
    bool HandleMatch(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can change the match."); return true; }
        string sub = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();

        if (sub == "clear")
        {
            int n = _queue.Count(e => e.Status == "active");
            ClearPlaying();
            EnsureStreamerQueued();        // the streamer stays in line unless he's sitting out
            Say("Match cleared (" + n + " player" + (n == 1 ? "" : "s") + " removed). Press Fill or !match fill for the next one.");
            PublishState("match_cleared", n.ToString());
            return true;
        }

        if (sub == "queue")
        {
            var players = _queue.Where(e => e.Status == "active").OrderBy(e => e.Position).ToList();
            if (players.Count == 0) { Say("@" + user + " Nobody is in the match."); return true; }
            int front = _queue.Min(e => e.Position) - players.Count;
            foreach (var e in players) { e.Status = "waiting"; e.Position = front++; }
            _lastBalance = null;
            _pendingPicks = null;
            SaveCurrentMatch();
            CompactPositions();
            Say("Everyone in the match went back to the front of the queue.");
            PublishState("queue_update", "match back to queue");
            return true;
        }

        if (sub == "fill")
        {
            // No live match (none yet, cleared, or already finished): make a new one from the queue.
            if (_lastBalance == null || _lastBalance.Result == null || _lastBalance.ResultRecorded)
                return DoRotateAndBalance();

            var r = _lastBalance.Result;
            int teamSize = GetTeamSize(_lastBalance.Format);
            int empty = teamSize * 2 - r.Blue.Count - r.Orange.Count;
            if (empty <= 0) { Say("@" + user + " The match is already full."); return true; }
            var fresh = PullNextBatch(Math.Min(empty, GetWaitingCount()));
            if (fresh.Count == 0) { Say("@" + user + " Nobody is waiting in the queue."); return true; }
            foreach (var e in fresh)
            {
                // Put each new player on the team with fewer players (ties: lower average MMR).
                var tp = new TeamPlayer { Username = e.Username, Mmr = ResolveMmr(e.Username, _lastBalance.Format) };
                bool blue = r.Blue.Count < r.Orange.Count ||
                            (r.Blue.Count == r.Orange.Count && (r.Blue.Count == 0 ? 0 : r.Blue.Average(p => p.Mmr)) <= (r.Orange.Count == 0 ? 0 : r.Orange.Average(p => p.Mmr)));
                (blue ? r.Blue : r.Orange).Add(tp);
            }
            Say("Filled " + fresh.Count + " slot" + (fresh.Count == 1 ? "" : "s") + ": " + string.Join(", ", fresh.Select(e => e.Username)) +
                (fresh.Count < empty ? " (still " + (empty - fresh.Count) + " empty)" : "") + ".");
            RefreshMatch("fill");
            return true;
        }

        Say("@" + user + " Usage: !match <clear|fill|queue>");
        return true;
    }

    // [NEW][WEB] While the streamer is playing, make sure he's in the line (at the front).
    void EnsureStreamerQueued()
    {
        string me = _settings.StreamerName;
        if (!_settings.StreamerPlaying || string.IsNullOrEmpty(me)) return;
        if (_queue.Any(e => e.Username == me)) return;
        AddToQueue(me);   // AddToQueue puts the streamer at #1
    }

    bool HandleBalance(string user, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can balance teams.");
            return true;
        }
        return DoRotateAndBalance();
    }

    // !next          -> everyone rotates out, next batch in (no result recorded)
    // !next blue     -> records Blue win, then king-of-the-hill rotation
    bool HandleNext(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {   // viewers asking "who is next?" get a short exact line (read-only); only mods advance the queue
            var nextUp = GetWaitingQueue().Take(3).Select(e => e.Username).ToList();
            Say(nextUp.Count == 0 ? "@" + user + " The queue is empty." : "@" + user + " Next up: " + string.Join(", ", nextUp) + " (" + GetWaitingQueue().Count + " waiting).");
            return true;
        }

        string sub = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (sub == "blue" || sub == "orange")
            return DoKothRotateAndBalance(sub);
        return DoRotateAndBalance();
    }

    // [NEW][CIRCUIT] !win blue|orange — "Orange Wins" button equivalent:
    // records the result, awards points, announces, updates overlay. Players stay put.
    bool HandleWin(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can record results.");
            return true;
        }
        string team = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (team != "blue" && team != "orange")
        {
            Say("@" + user + " Usage: !win <blue|orange>");
            return true;
        }
        if (_lastBalance == null || _lastBalance.Result == null)
        {
            Say("@" + user + " No active match.");
            return true;
        }
        if (_lastBalance.ResultRecorded)
        {
            Say("@" + user + " Match #" + _lastBalance.MatchId + " already has a result. Use !next to continue.");
            return true;
        }
        RecordResult(team);
        return true;
    }

    // [CIRCUIT] One action → one synchronized result: DB (json), points, chat, overlay.
    void RecordResult(string winnerTeam)
    {
        var res = _lastBalance.Result;
        var winners = winnerTeam == "blue" ? res.Blue : res.Orange;
        var losers = winnerTeam == "blue" ? res.Orange : res.Blue;

        // [NEW][WEB] Stats and points only count in the competitive activity.
        bool prac = IsPracticeLast();                      // a practice game changes nobody's stats
        bool counts = IsCompetitive() && !prac;
        bool kothAct = _settings.Activity == "koth";
        int ptsWin = kothAct ? 1 : _settings.PointsWin, ptsLoss = kothAct ? 0 : _settings.PointsLoss;   // King of the Hill ranks by WINS: 1 point per win, none for a loss
        if (kothAct && !prac)
            foreach (var tp in winners)
            {
                int w; _settings.KothWins.TryGetValue(tp.Username, out w);
                _settings.KothWins[tp.Username] = w + 1;
            }
        if (counts)
        {
            foreach (var tp in winners)
            {
                Player p;
                if (_players.TryGetValue(tp.Username, out p)) { if (!SeparateStats()) { p.Wins++; p.Points += _settings.PointsWin; } BumpMode(p, CategoryFor(_lastBalance.Format), 1, 0, ptsWin); }
            }
            foreach (var tp in losers)
            {
                Player p;
                if (_players.TryGetValue(tp.Username, out p)) { if (!SeparateStats()) { p.Losses++; p.Points += _settings.PointsLoss; } BumpMode(p, CategoryFor(_lastBalance.Format), 0, 1, ptsLoss); }
            }
            SavePlayers();
        }

        var rec = _matches.FirstOrDefault(m => m.Id == _lastBalance.MatchId);
        if (rec != null)
        {
            rec.Winner = winnerTeam;
            rec.FinishedAt = Now();
            rec.Counted = counts;                    // [NEW][WEB] remembered so a later fix can reverse exactly what was given
            rec.PtsWin = ptsWin;
            rec.PtsLoss = ptsLoss;
            SaveMatches();
        }

        _lastBalance.ResultRecorded = true;
        _lastBalance.Winner = winnerTeam;
        SaveCurrentMatch();

        // The match is over: everyone who played leaves the queue now (the streamer goes back to the front).
        SendToBack(_queue.Where(e => e.Status == "active").Select(e => e.Username).ToList());

        string label = winnerTeam == "blue" ? "🔷 Blue" : "🔶 Orange";
        Say(label + " wins match #" + _lastBalance.MatchId + "!" + (kothAct
            ? " (+1 win on the King of the Hill leaderboard)"
            : counts
            ? " (+" + _settings.PointsWin + " pts winners, +" + _settings.PointsLoss + " pts losers)"
            : " (casual: no points)"));
        PublishState("match_result", winnerTeam);
    }

    bool DoRotateAndBalance()
    {
        string format = _settings.DefaultFormat;
        int totalSlots = GetTotalSlots(format);

        EnsureStreamerQueued();   // [NEW][WEB] streamer plays unless he's sitting out

        // [FIX] Check BEFORE rotating. Everyone who played is kicked now (they don't
        // rotate back), except the streamer who stays for the next match.
        int available = GetWaitingCount() + (_queue.Any(e => e.Status == "active" && IsStreamer(e.Username)) ? 1 : 0);
        if (available < totalSlots)
        {
            Say("Not enough players for " + format + ". Need " + totalSlots + ", have " + available + ".");
            return true;
        }

        RotateQueue();

        if (ActiveMode() == "picks")
        {
            // [NEW] Streamer Picks: pull the players, but wait for !pick to set teams.
            var picked = PullNextBatch(totalSlots).Select(e => e.Username).ToList();
            BeginPicks(picked, format);
            return true;
        }

        var batch = PullNextBatch(totalSlots);
        var players = ToTeamPlayers(batch.Select(e => e.Username).ToList());
        StartMatch(players, MakeTeams(players, format, ActiveMode(), null), format);
        return true;
    }

    bool DoKothRotateAndBalance(string winnerTeam)
    {
        if (_lastBalance == null || _lastBalance.Result == null)
        {
            Say("No active lobby. Use !balance to start.");
            return true;
        }

        string format = _settings.DefaultFormat;
        int teamSize = GetTeamSize(format);
        EnsureStreamerQueued();   // [NEW][WEB] streamer plays unless he's sitting out

        // [NEW] !next <team> also records the result (once), so stats are always kept. If !win already
        // finalized this match, !next never awards again.
        // [CHANGED] The team named here is the one that STAYS (the website's "Orange stays" / "Blue stays"
        // next-match mode), even if the recorded result was the other team.
        if (!_lastBalance.ResultRecorded)
            RecordResult(winnerTeam);

        var winners = winnerTeam == "blue" ? _lastBalance.Result.Blue : _lastBalance.Result.Orange;
        var losers = winnerTeam == "blue" ? _lastBalance.Result.Orange : _lastBalance.Result.Blue;

        // [CHANGED] "Orange stays" / "Blue stays" is an explicit choice, so that team stays for the next
        // match; everyone else who played is kicked. (A plain !next = "Everyone out": nobody stays.)
        // Everyone who played was already kicked from the queue when the result was recorded, so the
        // staying team is re-added below once we know there are enough players.
        var staying = winners.Select(w => w.Username).ToList();

        // [FIX] If the format shrank (e.g. 3v3 -> 2v2), winners no longer fit on one team.
        if (staying.Count > teamSize)
        {
            Say("Format changed — doing a full rotation instead.");
            return DoRotateAndBalance();
        }

        int slotsNeeded = GetTotalSlots(format) - staying.Count;

        // [FIX] The old code sent losers to the back BEFORE checking there were
        // enough players, leaving a half-rotated queue and a stale lobby on failure.
        // Losers rotating to the back still count — they may get pulled again.
        var stayingSet = new HashSet<string>(staying);
        int availableNew = _queue.Count(e => (e.Status == "waiting" || (e.Status == "active" && IsStreamer(e.Username))) && !stayingSet.Contains(e.Username));
        if (availableNew < slotsNeeded)
        {
            Say("Not enough players in queue. Need " + slotsNeeded + ", have " + availableNew + ".");
            return true;
        }

        // The staying team goes back in the queue as active (they were kicked when the result was recorded).
        foreach (var name in staying)
        {
            AddToQueue(name);
            var se = GetEntry(name);
            if (se != null) se.Status = "active";
        }
        CompactPositions();

        // Anyone active who isn't staying (losers + replaced players) leaves.
        SendToBack(_queue.Where(e => e.Status == "active" && !stayingSet.Contains(e.Username))
                         .Select(e => e.Username).ToList());

        var challengers = PullNextBatch(slotsNeeded).Select(e => e.Username).ToList();

        if (staying.Count > 0)
            Say((winnerTeam == "blue" ? "🔷 Blue" : "🔶 Orange") + " stays on! Rotating in new challengers...");

        if (_settings.KothKeepWinnersTogether && staying.Count == teamSize)
        {
            // [NEW] True king-of-the-hill: winners stay as one team on their colour.
            var champs = ToTeamPlayers(staying);
            var chall = ToTeamPlayers(challengers);
            var result = winnerTeam == "blue" ? MakeResult(champs, chall) : MakeResult(chall, champs);
            StartMatch(champs.Concat(chall).ToList(), result, format);
        }
        else
        {
            var all = ToTeamPlayers(staying.Concat(challengers).ToList());
            StartMatch(all, MakeTeams(all, format, ActiveMode() == "random" ? "random" : "balanced", null), format);
        }
        return true;
    }

    bool HandleReroll(string user, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can reroll teams.");
            return true;
        }
        if (_lastBalance == null || _lastBalance.Players == null)
        {
            Say("@" + user + " No active balance to reroll. Run !balance first.");
            return true;
        }
        if (_lastBalance.ResultRecorded)
        {
            Say("@" + user + " That match is finished. Use !next to start a new one.");
            return true;
        }

        // Players kicked / left since the last balance get replaced from the queue.
        var current = _lastBalance.Players
            .Where(p => _queue.Any(e => e.Username == p.Username && e.Status == "active"))
            .ToList();
        var missing = _lastBalance.Players.Select(p => p.Username)
            .Except(current.Select(p => p.Username)).ToList();

        string format = _lastBalance.Format;
        int needed = GetTotalSlots(format) - current.Count;

        if (needed > 0)
        {
            if (GetWaitingCount() < needed)
            {
                // [FIX] Old code pulled partial replacements (marking them active)
                // and then bailed, stranding them as "active" outside any lobby.
                Say("Missing " + string.Join(", ", missing) + " — need " + needed +
                    " more in queue to refill the lobby.");
                return true;
            }
            var fresh = PullNextBatch(needed).Select(e => e.Username).ToList();
            current.AddRange(ToTeamPlayers(fresh));
            Say("Replaced " + string.Join(", ", missing) + " with " + string.Join(", ", fresh) + ".");
        }

        // Avoid the current split only if the roster is unchanged.
        HashSet<string> avoid = needed == 0
            ? new HashSet<string>(_lastBalance.Result.Blue.Select(p => p.Username))
            : null;
        string mode = ActiveMode() == "random" ? "random" : "balanced";
        var result = MakeTeams(current, format, mode, avoid);

        // [FIX] Reroll used to add a NEW match record every time, inflating history.
        // It now edits the existing match in place.
        _lastBalance.Players = current;
        _lastBalance.Result = result;
        SaveCurrentMatch();

        var rec = _matches.FirstOrDefault(m => m.Id == _lastBalance.MatchId);
        if (rec != null)
        {
            rec.Blue = result.Blue;
            rec.Orange = result.Orange;
            rec.BlueAvg = result.BlueAvgMmr;
            rec.OrangeAvg = result.OrangeAvgMmr;
            rec.Diff = result.MmrDiff;
            SaveMatches();
        }

        if (needed == 0) Say("Rerolled teams!");
        PostTeams(result);
        PublishState("teams_selected", "reroll " + _lastBalance.MatchId);
        return true;
    }

    // ── Streamer Picks  [NEW][CIRCUIT priority #1] ─────────────────
    // !balance in "picks" mode pulls the players and posts them.
    // Then: !pick user1 user2 user3   -> those go Blue, the rest Orange.
    //       !pick auto                 -> balance them automatically instead.
    static List<string> _pendingPicks;
    static string _pendingPicksFormat;

    void BeginPicks(List<string> usernames, string format)
    {
        _pendingPicks = usernames;
        _pendingPicksFormat = format;
        Say("Streamer picks! Players: " + string.Join(", ", usernames) +
            " — use !pick <" + GetTeamSize(format) + " names for Blue> or !pick auto");
        PublishState("picks_pending", string.Join(",", usernames));
    }

    bool HandlePick(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can pick teams.");
            return true;
        }
        if (_pendingPicks == null)
        {
            Say("@" + user + " Nothing to pick. Set !mode picks and run !balance.");
            return true;
        }

        var players = ToTeamPlayers(_pendingPicks);
        string format = _pendingPicksFormat;
        int teamSize = GetTeamSize(format);
        var names = input.Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries)
                         .Select(n => n.TrimStart('@').ToLower()).Distinct().ToList();

        BalanceResult result;
        if (names.Count == 1 && names[0] == "auto")
        {
            result = MakeTeams(players, format, "balanced", null);
        }
        else
        {
            if (names.Count != teamSize || names.Any(n => !_pendingPicks.Contains(n)))
            {
                Say("@" + user + " Pick exactly " + teamSize + " of: " + string.Join(", ", _pendingPicks));
                return true;
            }
            var blue = players.Where(p => names.Contains(p.Username)).ToList();
            var orange = players.Where(p => !names.Contains(p.Username)).ToList();
            result = MakeResult(blue, orange);
        }

        _pendingPicks = null;
        StartMatch(players, result, format);
        return true;
    }

    bool HandleMode(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can change the team mode.");
            return true;
        }
        string mode = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (!ValidModes.Contains(mode))
        {
            Say("@" + user + " Usage: !mode <balanced|random|picks> — Current: " + _settings.TeamMode);
            return true;
        }
        _settings.TeamMode = mode;
        SaveSettings();
        Say("Team mode set to " + mode + ".");
        PublishState("settings", "mode " + mode);
        return true;
    }

    bool HandleFormat(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can change the format.");
            return true;
        }

        string fmt = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower();
        if (!ValidFormats.Contains(fmt))
        {
            Say("@" + user + " Usage: !format <1v1|2v2|3v3|4v4> — Current: " + _settings.DefaultFormat);
            return true;
        }

        _settings.DefaultFormat = fmt;
        SaveSettings();
        Say("Format set to " + fmt + ". Takes effect on the next !balance / !next.");
        PublishState("settings", "format " + fmt);
        return true;
    }

    bool HandleKick(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can kick players.");
            return true;
        }

        string target = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower().TrimStart('@');
        if (string.IsNullOrEmpty(target))
        {
            Say("@" + user + " Usage: !kick <username>");
            return true;
        }

        if (RemoveFromQueue(target))
        {
            bool inLobby = _lastBalance != null && _lastBalance.Players != null &&
                           _lastBalance.Players.Any(p => p.Username == target);
            Say(target + " has been removed from the queue." +
                (inLobby ? " Use !reroll to refill the lobby." : ""));
            PublishState("queue_update", target + " kicked");
        }
        else
        {
            Say("@" + user + " " + target + " is not in the queue.");
        }
        return true;
    }

    bool HandleMmrLookup(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can look up other players' MMR.");
            return true;
        }

        string target = string.IsNullOrEmpty(input) ? "" : input.Split(' ')[0].ToLower().TrimStart('@');
        if (string.IsNullOrEmpty(target))
        {
            Say("@" + user + " Usage: !mmr @username");
            return true;
        }
        if (!_players.ContainsKey(target))
        {
            Say("@" + user + " Player \"" + target + "\" is not registered.");
            return true;
        }

        int mmr = ResolveMmr(target, _settings.DefaultFormat);
        Say("@" + user + " " + target + "'s MMR: " + mmr + " (" + SourceLabel(_players[target].MmrSource) + ")");
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  STRIKES [NEW][STRIKES]
    //  0-3 per player. Rule breakers / people getting in the way of customs get one from a mod; 3 = not allowed to play.
    //  Every time the stream goes live everybody loses one. Shown on the website profile (standings column 9).
    // ══════════════════════════════════════════════════════════════
    const int MaxStrikes = 3;
    static int StrikeTotal(Player p) { return p.Strikes + p.PermaStrikes; }
    static readonly System.Text.RegularExpressions.Regex PermaWords = new System.Text.RegularExpressions.Regex(@"\b(perma|permanent|toxic|toxicity|slur|slurs|racism|racist|hate)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    // temporary strikes wear off: one per full day since the last one went (or since the oldest was given)
    void DecayStrikes(long now)
    {
        int n = 0;
        foreach (var p in _players.Values)
        {
            if (p.Strikes <= 0) { p.StrikeDecayAt = 0; continue; }
            if (p.StrikeDecayAt <= 0) { p.StrikeDecayAt = now; n++; continue; }     // strikes from before this rule: the day starts now
            long days = (now - p.StrikeDecayAt) / 86400;
            if (days <= 0) continue;
            p.Strikes = (int)Math.Max(0, p.Strikes - days); p.StrikeDecayAt = p.Strikes > 0 ? p.StrikeDecayAt + days * 86400 : 0; n++;
        }
        if (n > 0) { SavePlayers(); _standingsDirty = true; _stateDirty = true; CPH.LogInfo("[BVQ] Strike check: temporary strikes updated for " + n + " player(s)."); }
    }

    bool HandleStrike(string user, string input, bool isPrivileged, int delta)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can " + (delta > 0 ? "give" : "remove") + " strikes."); return true; }
        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 1) { Say("@" + user + " Usage: " + (delta > 0 ? "!strike @username [perma|toxicity|slurs]" : "!unstrike @username [perma]")); return true; }
        string target = parts[0].ToLower().TrimStart('@');
        string rest = string.Join(" ", parts.Skip(1));
        bool perma = PermaWords.IsMatch(rest);
        Player p;
        if (!_players.TryGetValue(target, out p)) { Say("@" + user + " Player \"" + target + "\" is not registered."); return true; }
        int before = StrikeTotal(p); string what;
        if (delta > 0)
        {
            if (before >= MaxStrikes) { Say("@" + user + " " + target + " already has the maximum of " + MaxStrikes + " strikes."); return true; }
            if (perma) { p.PermaStrikes++; p.PermaReason = rest.Length > 60 ? rest.Substring(0, 60) : rest; what = "Permanent strike given to "; }
            else { if (p.Strikes == 0) p.StrikeDecayAt = Now(); p.Strikes++; what = "Strike given to "; }
        }
        else
        {
            if (before == 0) { Say("@" + user + " " + target + " already has no strikes."); return true; }
            if (perma) { if (p.PermaStrikes == 0) { Say("@" + user + " " + target + " has no permanent strikes."); return true; } p.PermaStrikes--; what = "Permanent strike removed from "; }
            else if (p.Strikes > 0) { p.Strikes--; what = "Strike removed from "; }
            else { Say("@" + user + " " + target + " only has permanent strikes. Use !unstrike @" + target + " perma to remove one."); return true; }
        }
        SavePlayers();
        _standingsDirty = true;
        string extra = "";
        if (StrikeTotal(p) >= MaxStrikes)
        {
            QueueEntry qe = GetEntry(target);
            if (qe != null && qe.Status == "waiting") { RemoveFromQueue(target); extra = " They were taken out of the queue."; }
            extra = " " + target + " can't play customs until they lose a strike." + extra;
        }
        Say("@" + user + " " + what + target + ": " + StrikeTotal(p) + "/" + MaxStrikes + (p.PermaStrikes > 0 ? " (" + p.PermaStrikes + " permanent)" : "") + "." + extra);
        PublishState("queue_update", target + " strikes");
        return true;
    }

    bool HandleStrikes(string user, string input)
    {
        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        string target = parts.Length >= 1 ? parts[0].ToLower().TrimStart('@') : user;
        Player p;
        if (!_players.TryGetValue(target, out p)) { Say("@" + user + " " + (target == user ? "You aren't" : target + " isn't") + " registered."); return true; }
        int t = StrikeTotal(p);
        Say("@" + user + " " + (target == user ? "You have " : target + " has ") + t + "/" + MaxStrikes + " strikes" + (p.PermaStrikes > 0 ? " (" + p.PermaStrikes + " permanent, " + p.Strikes + " temporary)" : "") + "." + (t >= MaxStrikes ? " (not allowed to play customs)" : ""));
        return true;
    }

    bool _hostLiveGiven; string _hostLiveSeen = "";
    // The PinguinoHost module publishes its own live state as the global "pinguino.live" ("1"/"0"); when present it replaces the website poll.
    void HostLive()
    {
        try
        {
            string hl = CPH.GetGlobalVar<string>("pinguino.live", false);
            _hostLiveGiven = hl == "1" || hl == "0";
            if (_hostLiveGiven && _hostLiveSeen != hl) { _hostLiveSeen = hl; CPH.LogInfo("[BVQ] The Host reports the stream is " + (hl == "1" ? "LIVE" : "offline") + "."); }
            if (_hostLiveGiven) ApplyLive(hl == "1");
        }
        catch (Exception) { _hostLiveGiven = false; }
    }

    // Called every 30 s with what Twitch says. Also where temporary strikes wear off (one per day, see DecayStrikes).
    void ApplyLive(bool live)
    {
        DecayStrikes(Now());
        if (live)
        {
            if (!_settings.WasLive)
            {
                _settings.WasLive = true;
                SaveSettings();
            }
        }
        else if (_settings.WasLive)
        {
            _settings.WasLive = false;
            _settings.LastLiveSeen = Now();
            SaveSettings();
        }
    }

    // [NEW][WEB] !setsr @user <0-5000> [self]: the FORTNITE rating (SR, our own system; Rocket League keeps MMR).
    bool HandleSetSr(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged) { Say("@" + user + " Only mods can set SR."); return true; }
        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        int sr;
        if (parts.Length < 2 || !int.TryParse(parts[1], out sr) || sr < 0 || sr > 5000)
        { Say("@" + user + " Usage: !setsr @username <0-5000>  (Fortnite Skill Rating)"); return true; }
        string target = parts[0].ToLower().TrimStart('@');
        if (!_players.ContainsKey(target)) { Say("@" + user + " Player \"" + target + "\" is not registered."); return true; }
        _players[target].Sr = sr;
        _players[target].SrSource = parts.Length >= 3 && parts[2].ToLower() == "self" ? "self" : "manual";
        SavePlayers();
        Say("@" + user + " Set " + target + "'s SR to " + sr + ".");
        PublishState("queue_update", target + " sr");
        return true;
    }

    bool HandleSetMmr(string user, string input, bool isPrivileged)
    {
        if (!isPrivileged)
        {
            Say("@" + user + " Only mods can set MMR.");
            return true;
        }

        string[] parts = (input ?? "").Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2)
        {
            Say("@" + user + " Usage: !setmmr @username <mmr or rank>");
            return true;
        }

        string target = parts[0].ToLower().TrimStart('@');

        // [NEW] "!setmmr @user auto" clears the manual override so TRN is used again.
        if (parts[1].ToLower() == "auto" && _players.ContainsKey(target))
        {
            _players[target].MmrSource = "none";
            SavePlayers();
            Say("@" + user + " " + target + "'s MMR will be fetched from Tracker Network again.");
            return true;
        }

        // [NEW][WEB] optional 3rd word: "self" = the player set it themself (site Settings); otherwise it's a mod override.
        string newSource = parts.Length >= 3 && parts[2].ToLower() == "self" ? "self" : "manual";
        int mmr;
        int? rankMmr = ParseRankToMmr(parts[1]);
        if (rankMmr.HasValue)
        {
            mmr = rankMmr.Value;
        }
        else if (!int.TryParse(parts[1], out mmr) || mmr < 0 || mmr > 3000)
        {
            Say("@" + user + " Usage: !setmmr @username <mmr or rank> — e.g. !setmmr @user 1200 or !setmmr @user gc1");
            return true;
        }

        if (!_players.ContainsKey(target))
        {
            Say("@" + user + " Player \"" + target + "\" is not registered.");
            return true;
        }

        _players[target].PeakMmr = mmr;
        _players[target].MmrSource = newSource;
        _players[target].MmrLastUpdated = Now();
        SavePlayers();
        Say("@" + user + " Set " + target + "'s MMR to " + mmr + " (" + SourceLabel(newSource) + ").");
        PublishState("queue_update", target + " mmr");
        return true;
    }

    // ══════════════════════════════════════════════════════════════
    //  HELPERS
    // ══════════════════════════════════════════════════════════════

    static string SourceLabel(string source)
    {
        switch (source)
        {
            case "api": return "Tracker Network";
            case "self_report": return "self-reported";
            case "self": return "set by player";
            case "manual": return "set by mod";
            default: return "default";
        }
    }

    void PostTeams(BalanceResult result)
    {
        var blueNames = result.Blue.Select(p => p.Username + "(" + p.Mmr + ")");
        var orangeNames = result.Orange.Select(p => p.Username + "(" + p.Mmr + ")");

        string id = _lastBalance != null ? "#" + _lastBalance.MatchId + " " : "";
        if (_settings.Activity == "casual" && false /* casual group style retired: casual = teams, like competitive */)
        {
            // [NEW][WEB] Casual: announce one group, no teams.
            Say(id + "Casual group (" + (_lastBalance != null ? _lastBalance.Format : _settings.DefaultFormat) + "): " +
                string.Join(", ", result.Blue.Concat(result.Orange).Select(p => p.Username)));
            return;
        }
        // Two plain messages: Blue, then Orange.
        SayColored(_settings.BlueColor, id + "🔷 Blue [avg " + result.BlueAvgMmr + "]: " + string.Join(", ", blueNames));
        SayColored(_settings.OrangeColor, "🔶 Orange [avg " + result.OrangeAvgMmr + "]: " + string.Join(", ", orangeNames) + " | Diff: " + result.MmrDiff);
    }

    void SayColored(string color, string text)
    {
        Say(text);   // plain message; the 🔷 / 🔶 emoji mark the team
    }
}
