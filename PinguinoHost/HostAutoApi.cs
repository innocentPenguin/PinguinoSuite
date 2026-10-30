using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    public static partial class HostApi
    {
        /// <summary>Say a line in chat as one of the bots (own Twitch login first, then PinguinoB0t, then the rest of its fallback chain, then the shared account).</summary>
        public static bool SendAs(string role, string text, out string via)
        {
            string raw = text; bool reply = ReplyCtx.IsReply; bool ok = SendAsCore(role, text, out via);
            BotSendLog(role, reply, raw, ok ? "ok" : "no: " + via, via); return ok;
        }

        static string _sendLogDay = ""; static long _sendLogBytes; static readonly object _sendLogLock = new object();
        /// <summary>one line per chat send: time, account, reply/plain, result, first 160 chars. Data/../logs/bot-sends-YYYY-MM-DD.log, at most 5 MB a day. No secrets.</summary>
        public static string SendLogDir;   // tests may point this elsewhere
        static void BotSendLog(string role, bool reply, string text, string result, string via)
        {
            try
            {
                string t = System.Text.RegularExpressions.Regex.Replace(text ?? "", "[\u0000-\u001f]+", " "); if (t.Length > 160) t = t.Substring(0, 160) + "...";
                string line = DateTime.UtcNow.ToString("HH:mm:ss.fff") + "Z\t" + role + "\t" + (reply ? "reply" : "plain") + "\t" + (result.Length > 90 ? result.Substring(0, 90) : result) + "\t" + t;
                lock (_sendLogLock)
                {
                    string day = DateTime.UtcNow.ToString("yyyy-MM-dd");
                    string dir = SendLogDir ?? System.IO.Path.Combine(System.IO.Path.GetDirectoryName((DataDir ?? "").TrimEnd((char)92, (char)47)) ?? DataDir, "logs");
                    string f = System.IO.Path.Combine(dir, "bot-sends-" + day + ".log");
                    if (day != _sendLogDay) { _sendLogDay = day; _sendLogBytes = System.IO.File.Exists(f) ? new System.IO.FileInfo(f).Length : 0; }
                    if (System.IO.File.Exists(f) && new System.IO.FileInfo(f).Length > 5L * 1024 * 1024) return;   // real size on disk: the bot copies append to the same file
                    System.IO.Directory.CreateDirectory(dir);
                    System.IO.File.AppendAllText(f, line + Environment.NewLine, new System.Text.UTF8Encoding(false)); _sendLogBytes += line.Length + 2;
                }
            }
            catch (Exception) { }
        }

        static readonly System.Text.RegularExpressions.Regex RxKey = new System.Text.RegularExpressions.Regex(@"(?<![\w:])(yt|tt|kk|fb):[\w\-]+", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        /// <summary>replaces platform keys (yt:..., tt:...) by the remembered display name</summary>
        public static string ShowNames(string text)
        {
            if (string.IsNullOrEmpty(text) || text.IndexOf(':') < 0) return text;
            try { return RxKey.Replace(text, m => { string n = PlatformUsers.Display(m.Value.ToLowerInvariant()); return string.IsNullOrEmpty(n) ? m.Value : n; }); } catch (Exception) { return text; }
        }
        static bool SendAsCore(string role, string text, out string via)
        {
            via = "";
            if (!Lease.MayRun) { via = "this Host is not the master"; return false; }
            text = CleanLine(text, "chat send as " + role);
            if (text == "") { via = "nothing to say (empty line)"; return false; }
            { string pf = ReplyCtx.Platform; if (pf != "twitch") return SendForeign(pf, text, out via); }   // chat from YouTube etc.: the answer goes to that platform only, through Multi, never to Twitch
            text = ShowNames(text);   // Twitch lines never carry a raw "yt:UC..." key: the viewer's display name instead
            if (SaidRecently(text)) { via = "duplicate: the same line was said moments ago"; Clog.Info("chat", "not sent, same line said moments ago: " + (text.Length > 60 ? text.Substring(0, 60) : text)); return true; }
            role = string.IsNullOrWhiteSpace(role) ? "core" : role.Trim().ToLowerInvariant();
            var reg = LoadFile("bots.json"); var sec = BotSecretsV();
            var chain = new List<string> { role }; if (!chain.Contains("core")) chain.Add("core");
            if (reg["Fallback"]?[role] is JArray fb) foreach (var x in fb) if (!chain.Contains((string)x)) chain.Add((string)x);
            foreach (string r in chain)
            {
                var bot = reg["Bots"]?[r]; var s = sec[r] as JObject;
                if (bot == null || (bool?)bot["Enabled"] == false || s == null || ((string)bot["Sender"] ?? "") != "helix") continue;
                string tok = (string)s["UserToken"], cid = (string)s["ClientId"], sid = (string)s["SenderId"], bid = (string)s["BroadcasterId"];
                if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid) || string.IsNullOrEmpty(sid) || string.IsNullOrEmpty(bid)) continue;
                try
                {
                    using (var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
                    {
                        var rq = new HttpRequestMessage(HttpMethod.Post, Helix + "/chat/messages"); rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                        string sentJson = ReplyCtx.Body(bid, sid, text).ToString();   // kept as a string: the request content may be disposed once it was sent
                        rq.Content = new StringContent(sentJson, Encoding.UTF8, "application/json");
                        var resp = http.SendAsync(rq).Result;
                        if (resp.IsSuccessStatusCode) { via = (string)bot["Account"] ?? r; return true; }
                        int code = (int)resp.StatusCode; string why = "";
                        try { why = resp.Content.ReadAsStringAsync().Result ?? ""; if (why.Length > 160) why = why.Substring(0, 160); } catch (Exception) { }
                        Clog.Warn("automation", "chat send as " + r + " refused (HTTP " + code + ")" + (code == 400 ? ": " + why + " | line (" + text.Length + " chars): " + (text.Length > 120 ? text.Substring(0, 120) + "..." : text) : ""));
                        if (code == 400)
                        {
                            // a reply whose parent message was deleted / is too old is refused: say the line ONCE as a plain line (it was refused, so nothing went out); a 400 for the text itself fails here again and stops
                            if (sentJson.Contains("reply_parent_message_id"))
                            {
                                Clog.Warn("automation", "chat send as " + r + ": the reply parent was refused, saying the line once as a plain line");
                                var rq2 = new HttpRequestMessage(HttpMethod.Post, Helix + "/chat/messages"); rq2.Headers.Add("Authorization", "Bearer " + tok); rq2.Headers.Add("Client-Id", cid);
                                rq2.Content = new StringContent(new JObject { { "broadcaster_id", bid }, { "sender_id", sid }, { "message", text } }.ToString(), Encoding.UTF8, "application/json");
                                if (http.SendAsync(rq2).Result.IsSuccessStatusCode) { via = ((string)bot["Account"] ?? r) + " (plain, reply parent refused)"; return true; }
                            }
                            via = "refused by Twitch (HTTP 400): the line itself is not accepted, not tried on other accounts"; return false;   // the same text is refused for every account: do not spray it
                        }
                    }
                }
                catch (Exception ex)
                {
                    Clog.Warn("automation", "chat send as " + r + " failed: " + ex.Message);
                    // a timeout after the request went out may still have been delivered: never try another account for it (that is how a line gets said twice)
                    if (ex is AggregateException || ex is TaskCanceledException || ex is TimeoutException) { via = "timed out (may have gone out, not repeated)"; return true; }
                }
            }
            if (Program.SayShared(text)) { via = "shared account"; return true; }
            via = "no account could send (not signed in, or sim mode)"; return false;
        }

        /// <summary>what Twitch accepts as a chat line: no control characters, one line, at most 500 characters (cut at a sentence / word end). Empty stays empty. The first time a line had to be changed it is logged (once per distinct text).</summary>
        public static string CleanLine(string text, string who)
        {
            string t = text ?? "";
            string c = System.Text.RegularExpressions.Regex.Replace(t, @"[\u0000-\u001F\u007F\u0080-\u009F\u2028\u2029]+", " ");
            c = System.Text.RegularExpressions.Regex.Replace(c, @" {2,}", " ").Trim();
            if (c.Length > 500)
            {
                string head = c.Substring(0, 500); int cut = -1;
                foreach (System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(head, @"[.!?](\s|$)")) cut = m.Index + 1;
                if (cut < 250) cut = head.LastIndexOf(' '); if (cut < 250) cut = 497;
                c = c.Substring(0, cut).TrimEnd();
            }
            if (c != t.Trim() || c == "")
            {
                string key = t.Length > 80 ? t.Substring(0, 80) : t;
                bool first; lock (_cleanLogged) { first = _cleanLogged.Add(key); if (_cleanLogged.Count > 200) _cleanLogged.Clear(); }
                if (first) Clog.Warn("automation", who + ": the line was " + (c == "" ? "empty (dropped)" : t.Trim().Length > 500 ? "over 500 characters (cut)" : "changed (control characters)") + ": " + (t.Length > 120 ? t.Substring(0, 120) + "..." : t).Replace("\r", " ").Replace("\n", " "));
            }
            return c;
        }
        static readonly System.Collections.Generic.HashSet<string> _cleanLogged = new System.Collections.Generic.HashSet<string>();

        // NEVER SAY THE SAME LINE TWICE: every chat send (timers, reminders, commands, shoutouts...) passes here. Same text (case/spacing ignored) inside the window is dropped.
        static readonly System.Collections.Generic.Dictionary<string, DateTime> _said = new System.Collections.Generic.Dictionary<string, DateTime>();
        public static int DupSeconds { get { int n; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_DUP_SECONDS"), out n) ? n : 30; } }
        /// <summary>clip routes: this computer only AND not from a web page (a browser always sends Origin on fetch/POST; bots do not), Host header must be local (no DNS rebinding)</summary>
        static bool ClipLocalOnly(System.Net.HttpListenerContext c)
        {
            if (!System.Net.IPAddress.IsLoopback(c.Request.RemoteEndPoint.Address)) return false;
            if (!string.IsNullOrEmpty(c.Request.Headers["Origin"])) return false;
            string h = c.Request.Headers["Host"] ?? ""; return h.StartsWith("127.0.0.1:") || h.StartsWith("localhost:") || h.StartsWith("[::1]:");
        }
        /// <summary>a reply to chat from another platform: one explicit platform through Multi /api/send (reply_to = that platform's message id), NO Twitch fallback; tiktok is read-only: logged and skipped quietly</summary>
        public static Func<string, JObject, JObject> TestMultiSend;   // test hook (path, body) -> Multi answer
        static readonly System.Text.RegularExpressions.Regex RxTwitchEmote = new System.Text.RegularExpressions.Regex(@"\binnoce108\w*\*?", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        static bool SendForeign(string pf, string text, out string via)
        {
            string parent, login; ReplyCtx.Current(out parent, out login);
            string line = ReplyCtx.Prepare(text, out parent);
            if (login != "" && login.IndexOf(':') > 0) { string shown = PlatformUsers.Display(login); line = System.Text.RegularExpressions.Regex.Replace(line, System.Text.RegularExpressions.Regex.Escape(login), m => shown, System.Text.RegularExpressions.RegexOptions.IgnoreCase); }   // "yt:id" is only our internal key: say the display name
            line = ShowNames(line);   // other viewers named in the line: display names, never keys
            line = RxTwitchEmote.Replace(line, "").Replace("  ", " ").Trim();   // Twitch emote tokens (innoce108*) are plain text on YouTube / TikTok
            if (line == "") { via = "nothing left to say"; return true; }
            if (pf == "tiktok") { via = "tiktok is read-only"; ReplyCtx.NoteSilent(line); return true; }   // no reply anywhere (never Twitch, never Multi); one log line per handled command from ReplyCtx.LogSilent
            // YouTube has no native reply: the answer to a viewer says who it is for
            if (PlatformUsers.IsForeign(login) && !line.StartsWith("@")) line = "@" + PlatformUsers.Display(login) + " " + line;
            if (ReplyCtx.Hold(line)) { via = "held: goes out with the rest of this answer as one message"; return true; }
            return SendOut(pf, line, out via);
        }
        /// <summary>the held lines of one handled chat-in message go out as one message (split only when over YouTube's 200 characters)</summary>
        public static void FlushForeign()
        {
            string pf = ReplyCtx.Platform; var held = ReplyCtx.TakeHeld(); if (held.Count == 0 || pf == "twitch") return;
            string at = held[0].StartsWith("@") && held[0].IndexOf(' ') > 0 ? held[0].Substring(0, held[0].IndexOf(' ') + 1) : "";
            string par0, lg; ReplyCtx.Current(out par0, out lg); if (lg != "" && lg.IndexOf(':') > 0) { string full = "@" + PlatformUsers.Display(lg) + " "; if (held[0].StartsWith(full, StringComparison.OrdinalIgnoreCase)) at = held[0].Substring(0, full.Length); }   // a handle with a space ("@Yt Two") is stripped whole, never cut at its first space
            var sb = new System.Text.StringBuilder(held[0]);
            for (int i = 1; i < held.Count; i++) sb.Append(' ').Append(at != "" && held[i].StartsWith(at, StringComparison.OrdinalIgnoreCase) ? held[i].Substring(at.Length) : held[i]);
            string all = sb.ToString(); int lim = pf == "youtube" ? 195 : 450;
            while (all.Length > 0)
            {
                string part = all; if (part.Length > lim) { int cut = part.LastIndexOf(' ', lim); if (cut < lim / 2) cut = lim; part = part.Substring(0, cut); }
                all = all.Substring(part.Length).TrimStart(); string v; SendOut(pf, part.TrimEnd(), out v);
            }
        }
        /// <summary>a line to the YouTube chat from anywhere (a mod resolving an order in Twitch chat or Master View): same duplicate guard and paced queue as every YouTube send</summary>
        public static void SayYouTube(string line)
        {
            string via; if (SaidRecently("youtube", line)) return;
            if (YtQueueOn) YtEnqueue(line, null, out via); else PostToMulti("youtube", line, null, out via, false);
        }
        static bool SendOut(string pf, string line, out string via)
        {
            string parent, login; ReplyCtx.Current(out parent, out login);
            if (SaidRecently(pf, line)) { via = "duplicate: the same line was said moments ago"; Clog.Info("chat", "not sent to " + pf + ", same line said moments ago"); return true; }
            if (pf == "youtube" && YtQueueOn) { bool q = YtEnqueue(line, parent, out via); ReplyCtx.NoteOut(q, line); return q; }
            return PostToMulti(pf, line, parent, out via, true);
        }
        static bool PostToMulti(string pf, string line, string parent, out string via, bool note)
        {
            var body = new JObject { { "platform", pf }, { "text", line } }; if (!string.IsNullOrEmpty(parent)) body["reply_to"] = parent;
            JObject r = TestMultiSend != null ? TestMultiSend("/api/send", body) : AlertBridge.Post("/api/send", body);
            bool ok = r != null && (bool?)r["ok"] == true;
            via = ok ? "multi:" + pf : "multi refused " + pf + ": " + (((string)r?["text"]) ?? ((string)r?["detail"]) ?? "no answer");
            if (!ok) Clog.Warn("chat", "send to " + pf + " failed (no Twitch fallback): " + via);
            if (ok) ChatInStats.Reply(); else ChatInStats.SendError();
            if (note) ReplyCtx.NoteOut(ok, line);
            return ok;
        }

        // ---- YouTube outbound queue: YouTube answers 403 "posted too many chat messages" when two lines go out within a couple of seconds (10-29: two newcomers 2 s apart, the second welcome died).
        // One FIFO for the platform, minimum spacing between sends, one retry after a 403 (with a backoff, in order), bounded; Twitch sends never wait for it. The same line is never queued twice (SaidRecently ran before).
        // In the sim / tests the spacing is 0 unless PINGUINO_YT_SPACING_MS says otherwise.
        sealed class YtItem { public string Line, Parent; public int Tries; public DateTime Queued = DateTime.UtcNow; }
        static readonly Queue<YtItem> _ytQ = new Queue<YtItem>(); static readonly object _ytL = new object(); static Thread _ytT; static DateTime _ytLast = DateTime.MinValue; static DateTime _ytSlowUntil = DateTime.MinValue;
        public static bool YtQueueOn = true; public const int YtQueueMax = 30;
        static int YtSpacingMs { get { int v; string e = Environment.GetEnvironmentVariable("PINGUINO_YT_SPACING_MS"); if (e != null && int.TryParse(e, out v)) return Math.Max(0, v); int? s = SettingSpacing(); return s ?? (SimMode ? 0 : 6000); } }
        static int? _spacing; static DateTime _spacingAt = DateTime.MinValue;
        /// <summary>YouTubeSendSpacingMs from settings.json (null when not set: default 6000), re-read at most every 5 s; clamped to 1000..60000</summary>
        static int? SettingSpacing()
        {
            if ((DateTime.UtcNow - _spacingAt).TotalSeconds < 5) return _spacing;
            _spacingAt = DateTime.UtcNow;
            try { string f = System.IO.Path.Combine(DataDir, "settings.json"); if (System.IO.File.Exists(f)) { var j = JObject.Parse(System.IO.File.ReadAllText(f).TrimStart((char)0xFEFF)); int? v = (int?)j["YouTubeSendSpacingMs"]; _spacing = v == null ? (int?)null : Math.Max(1000, Math.Min(60000, v.Value)); } else _spacing = null; }
            catch (Exception) { }
            return _spacing;
        }
        static int YtBackoffMs { get { int v; string e = Environment.GetEnvironmentVariable("PINGUINO_YT_BACKOFF_MS"); if (e != null && int.TryParse(e, out v)) return Math.Max(0, v); return SimMode ? 300 : 15000; } }
        public static int YtQueueLength() { lock (_ytL) return _ytQ.Count; }
        static bool YtEnqueue(string line, string parent, out string via)
        {
            lock (_ytL)
            {
                if (_ytQ.Count >= YtQueueMax) { via = "youtube queue full (" + YtQueueMax + "): line dropped"; Clog.Warn("chat", via + ": " + (line.Length > 60 ? line.Substring(0, 60) : line)); ChatInStats.SendError(); return false; }
                _ytQ.Enqueue(new YtItem { Line = line, Parent = parent });
                if (_ytT == null || !_ytT.IsAlive) { _ytT = new Thread(YtLoop) { IsBackground = true, Name = "yt-send" }; _ytT.Start(); }
                Monitor.PulseAll(_ytL);
            }
            via = "queued for youtube"; return true;
        }
        static void YtLoop()
        {
            while (true)
            {
                YtItem it;
                lock (_ytL) { while (_ytQ.Count == 0) { if (!Monitor.Wait(_ytL, 60000) && _ytQ.Count == 0) { _ytT = null; return; } } it = _ytQ.Peek(); }
                int space = YtSpacingMs; if (DateTime.UtcNow < _ytSlowUntil) space = Math.Max(space, SimMode ? 0 : 8000);
                double wait = space - (DateTime.UtcNow - _ytLast).TotalMilliseconds; if (wait > 0) Thread.Sleep((int)wait);
                string via; bool ok;
                try { ok = PostToMulti("youtube", it.Line, it.Parent, out via, false); } catch (Exception ex) { ok = false; via = "exception: " + ex.Message; }
                _ytLast = DateTime.UtcNow;
                bool rate = !ok && (via.IndexOf("too many", StringComparison.OrdinalIgnoreCase) >= 0 || via.IndexOf("403", StringComparison.Ordinal) >= 0 || via.IndexOf("rate", StringComparison.OrdinalIgnoreCase) >= 0);
                if (rate) _ytSlowUntil = DateTime.UtcNow.AddMinutes(2);
                if (!ok && rate && it.Tries == 0) { it.Tries++; Clog.Info("chat", "youtube said too many messages: one retry in " + YtBackoffMs + " ms, the queue waits"); Thread.Sleep(YtBackoffMs); continue; }   // the item stays at the head: order kept
                lock (_ytL) { if (_ytQ.Count > 0) _ytQ.Dequeue(); }
                if (!ok) Clog.Warn("chat", "youtube line dropped after " + (it.Tries + 1) + " try(ies): " + via);
            }
        }
        /// <summary>true when this name is one of our own bot sender accounts or the channel itself (loop guard for chat-in)</summary>
        public static bool IsOwnBotName(string name)
        {
            try
            {
                string n = (name ?? "").Trim().TrimStart('@').ToLowerInvariant(); if (n == "") return false;
                var reg = LoadFile("bots.json");
                if (reg["Bots"] is JObject bots) foreach (var p in bots.Properties()) { if (p.Name.ToLowerInvariant() == n) return true; if (p.Value is JObject o) foreach (var f in new[] { "Account", "Login", "Name" }) if (((string)o[f] ?? "").Trim().TrimStart('@').ToLowerInvariant() == n) return true; }
                foreach (var x in new[] { "pinguinob0t", "pinguinohelper", "chattypinguino" }) if (n == x) return true;
            }
            catch (Exception) { }
            return false;
        }
        public static bool SaidRecently(string text) { return SaidRecently("twitch", text); }
        public static bool SaidRecently(string platform, string text)
        {
            string k = System.Text.RegularExpressions.Regex.Replace((text ?? "").ToLowerInvariant(), "[​‍️]", "");
            k = System.Text.RegularExpressions.Regex.Replace(k, @"\s+", " ").Trim(); int win = DupSeconds; if (!string.IsNullOrEmpty(platform) && platform != "twitch") k = platform + "|" + k;
            if (k == "" || win <= 0) return false;
            lock (_said)
            {
                var now = DateTime.UtcNow; foreach (var old in _said.Where(x => (now - x.Value).TotalSeconds > win).Select(x => x.Key).ToList()) _said.Remove(old);
                if (_said.ContainsKey(k)) return true;
                _said[k] = now; return false;
            }
        }

        static string IntroPage(string name)
        {
            foreach (var d in new[] { Path.Combine(AppContext.BaseDirectory, "web"), Path.Combine(Program.SuiteDir ?? "", "PinguinoHost", "web") })
            { var f = Path.Combine(d, name); if (File.Exists(f)) return f; }
            return null;
        }

        static string AutoPagePath()
        {
            foreach (var d in new[] { Path.Combine(AppContext.BaseDirectory, "web"), Path.Combine(Program.SuiteDir ?? "", "PinguinoHost", "web") })
            { var f = Path.Combine(d, "automations.html"); if (File.Exists(f)) return f; }
            return null;
        }

        // returns true when it answered an automation route
        static bool AutoRoutes(System.Net.HttpListenerContext c, string p)
        {
            string m = c.Request.HttpMethod;
            if (p == "/automations" && m == "GET")
            {
                string f = AutoPagePath();
                if (f == null) { c.Response.StatusCode = 404; return true; }
                Write(c, File.ReadAllText(f, Encoding.UTF8), "text/html; charset=utf-8"); return true;
            }
            if (p == "/api/recap/preview" && m == "GET") { Write(c, Recap.Build(true).ToString(), "application/json"); return true; }   // the recap of the LAST stream, text only, nothing is said (works offline)
            if (p == "/api/recap/test" && m == "POST")   // {post:true} says it in chat once (30 s duplicate guard); without post it only returns the text
            {
                var b = Body(c); var r = Recap.Build(true); bool post = (bool?)b["post"] == true; r["posted"] = false; r["duplicate"] = false;
                if (post) { string via; bool ok = SendAs("core", (string)r["text"], out via); r["posted"] = ok && !via.StartsWith("duplicate"); r["duplicate"] = via.StartsWith("duplicate"); r["via"] = via; if (!ok) r["ok"] = false; }
                Write(c, r.ToString(), "application/json"); return true;
            }
            if (p == "/api/firsts" && m == "GET") { Write(c, Firsts.Board(int.TryParse(c.Request.QueryString["limit"], out int fl) ? Math.Max(1, Math.Min(500, fl)) : 100).ToString(), "application/json"); return true; }   // the First 5 board: rows {login,display,firsts,top3,top5,score,places[5]}
            if (p == "/api/firsts/rebuild" && m == "POST") { var b = Body(c); bool ap = (bool?)b["apply"] == true; var r = Firsts.Rebuild(ap); ChannelControl.Audit("app", "firsts/rebuild", "apply=" + ap); Write(c, r.ToString(), "application/json"); return true; }   // dry run unless {apply:true}; apply backs the five vars up first
            if (p == "/api/raid/prep" && m == "POST")   // Master View "Raid prep": says the "prepare your emotes" line early for a raid started on twitch.tv (once per raid, 3 min window; the later channel.raid event does not repeat it)
            {
                var b = Body(c); string tg = ((string)b["target"] ?? "").Trim().TrimStart('@').ToLowerInvariant(); bool fired = Auto.OnRaidScheduled(tg, (bool?)b["now"] == true);
                ChannelControl.Audit("app", "raid/prep", "target=" + tg + " fired=" + fired); Write(c, new JObject { { "ok", true }, { "fired", fired }, { "duplicate", !fired } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/rewards" && m == "GET") { Write(c, Rewards.List().ToString(), "application/json"); return true; }   // every channel point reward and whether the Host owns it (refunds only work on those)
            if (p == "/api/rewards/use" && m == "POST") { Write(c, Rewards.Use(Body(c)).ToString(), "application/json"); return true; }   // {rewardId, automation?}: point an automation at a reward the Host owns
            if (p == "/api/rewards/takeover" && m == "POST") { Write(c, Rewards.Takeover(Body(c)).ToString(), "application/json"); return true; }   // {rewardId, automation?}: the Host's own copy of another app's reward; old one renamed "(old)" + disabled when Twitch allows
            if (p == "/api/rewards/create" && m == "POST") { Write(c, Rewards.Create(Body(c)).ToString(), "application/json"); return true; }   // {title:"Song Request",cost,prompt,inputRequired,automation:"spotify-redeem"}: makes the Host's OWN reward and points the automation at it
            if (p == "/api/channel/info" && m == "GET") { Write(c, ChannelControl.Info().ToString(), "application/json"); return true; }
            if ((p == "/api/channel/update" || p == "/api/mod/timeout") && m == "POST")   // Speak module: module token required for timeouts; the channel editor in the Suite app passes the same write gate as /api/customs/mod (own origin or the app token). Every call is audit-logged
            {
                if (!(p == "/api/channel/update") && !HostApi.StrictTokenOk(c.Request)) { c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"module token required\"}", "application/json"); return true; }
                var b = Body(c); JObject res; string who = "module:speak";
                if (p == "/api/channel/update") { res = ChannelControl.Update((string)b["title"], (string)b["game"], b["tags"]); ChannelControl.Audit(who, "channel/update", "title=" + (string)b["title"] + " game=" + (string)b["game"] + " tags=" + (b["tags"] == null ? "" : b["tags"].ToString(Newtonsoft.Json.Formatting.None)) + " -> " + (bool?)res["ok"] + " " + (string)res["error"]); }
                else { res = ChannelControl.Timeout((string)b["user"], (int?)b["seconds"] ?? 0, (string)b["reason"]); ChannelControl.Audit(who, "mod/timeout", "user=" + (string)b["user"] + " seconds=" + (int?)b["seconds"] + " reason=" + (string)b["reason"] + " -> " + (bool?)res["ok"] + " " + (string)res["error"]); }
                Write(c, res.ToString(), "application/json"); return true;
            }
            if (p == "/api/chat-in" && m == "POST")   // Multi: one chat line from another platform {platform,user,userId,text,msgId,isBot}. Namespaced, viewer role only, Actions & Events commands only: no economy, no moderation, no points
            {
                if (!HostApi.StrictTokenOk(c.Request)) { ChatInStats.Unauthorized(c.Request.RemoteEndPoint?.Address?.ToString(), ChatInStats.TokenField(c.Request)); c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"module token required\"}", "application/json"); return true; }
                var b = Body(c); string ciPlat = ((string)b["platform"] ?? "").Trim().ToLowerInvariant(), ciText = (string)b["text"] ?? ""; var res = Program.DispatchExternal(((string)b["platform"] ?? "").Trim().ToLowerInvariant(), ((string)b["user"] ?? "").Trim(), ((string)b["userId"] ?? "").Trim(), (string)b["text"] ?? "", (string)b["msgId"] ?? "", ((bool?)b["isBot"] == true || (bool?)b["ownBot"] == true));
                ChatInStats.Result(ciPlat, ciText, res);
                Write(c, res.ToString(), "application/json"); return true;
            }
            if (p == "/api/say" && m == "POST")   // modules (Multi, Speak): say one line in chat through the Host, so the 30 s duplicate guard and the no-retry-on-timeout rule apply
            {
                if (!HostApi.StrictTokenOk(c.Request)) { c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"module token required\"}", "application/json"); return true; }
                var b = Body(c); string text = ((string)b["text"] ?? "").Trim();
                if (text == "" || text.Length > 500) { Write(c, "{\"ok\":false,\"error\":\"text required (max 500 characters)\"}", "application/json"); return true; }
                string via; bool ok; string plat = ((string)b["platform"] ?? "").Trim().ToLowerInvariant();
                if (plat != "" && plat != "twitch") { string who = ((string)b["user"] ?? "").Trim(); ReplyCtx.BeginForeign(plat, (string)b["reply_to"], who == "" ? "" : "x:" + who); try { ok = SendAs((string)b["bot"], text, out via); } finally { ReplyCtx.End(); } }   // Chatty / Helper answering a YouTube viewer: {platform,reply_to,user}
                else ok = SendAs((string)b["bot"], text, out via);
                Write(c, new JObject { { "ok", ok }, { "duplicate", via.StartsWith("duplicate") }, { "via", via } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/obs/status" && m == "GET")
            {
                bool con = ObsConnected(); var rb = ReplayBuf.Status();
                Write(c, new JObject { { "ok", true }, { "connected", con }, { "recording", LiveState.Recording }, { "autoStartReplayBuffer", ReplayBuf.AutoStart }, { "replayBufferEnabled", ReplayBuf.Enabled }, { "replayBuffer", rb } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/obs/tree" && m == "GET") { Write(c, ObsTree.Get(c.Request.QueryString["scene"]).ToString(), "application/json"); return true; }
            if ((p == "/api/obs/scene" || p == "/api/obs/item") && m == "POST")
            {
                var b = Body(c); JObject res;
                if (p == "/api/obs/scene") res = ObsTree.SetScene((string)b["scene"] ?? "");
                else res = ObsTree.SetItem((string)b["scene"] ?? "", (int?)b["itemId"] ?? -1, (bool?)b["enabled"], (bool?)b["toggle"] == true);
                Write(c, res.ToString(), "application/json"); return true;
            }
            if (p == "/api/overlaychat/status" && m == "GET") { Write(c, OverlayChat.Status().ToString(), "application/json"); return true; }
            if ((p == "/api/overlaychat/ask" || p == "/api/overlaychat/apply") && m == "POST")
            {
                var b = Body(c); var res = p.EndsWith("/ask") ? OverlayChat.Ask((string)b["user"], (string)b["text"]) : OverlayChat.Apply((string)b["id"], (string)b["user"]);
                Write(c, res.ToString(), "application/json"); return true;
            }
            if (p == "/api/overlays" && m == "GET") { Write(c, OverlayFiles.List().ToString(), "application/json"); return true; }
            if (p == "/api/overlays/file" && m == "GET") { Write(c, OverlayFiles.Read(c.Request.QueryString["path"]).ToString(), "application/json"); return true; }
            if ((p == "/api/overlays/write" || p == "/api/overlays/delete" || p == "/api/overlays/rename") && m == "POST")
            {
                var b = Body(c); string who = "overlay-api"; JObject res;
                if (p.EndsWith("/write")) res = OverlayFiles.Write((string)b["path"], (string)b["text"], (string)b["base64"], who);
                else if (p.EndsWith("/delete")) res = OverlayFiles.Delete((string)b["path"], who);
                else res = OverlayFiles.Rename((string)b["from"], (string)b["to"], who);
                Write(c, res.ToString(), "application/json"); return true;
            }
            if (p == "/api/offline-mode" && m == "GET") { Write(c, OfflineMode.Api().ToString(), "application/json"); return true; }
            if (p == "/api/offline-mode" && m == "POST") { var b = Body(c); bool? en = (bool?)b["enabled"], ar = (bool?)b["actLiveWhileRecording"]; if (en == null && ar == null) { Write(c, new JObject { { "ok", false }, { "error", "enabled or actLiveWhileRecording (true/false) required" } }.ToString(), "application/json"); return true; } JObject res = null; if (ar != null) res = OfflineMode.SetActLiveWhileRecording(ar.Value, "api"); if (en != null) res = OfflineMode.Set(en.Value, "api"); Write(c, res.ToString(), "application/json"); return true; }
            if (p == "/api/live-state" && m == "GET") { Write(c, Control.LiveState().ToString(), "application/json"); return true; }
            if (p == "/api/activity" && m == "GET")
            {
                long since = long.TryParse(c.Request.QueryString["since"], out long sn) ? sn : 0; int lim = int.TryParse(c.Request.QueryString["limit"], out int ln) ? ln : 100;
                Write(c, Latest.Activity(since, lim, c.Request.QueryString["type"]).ToString(), "application/json"); return true;
            }
            if (p == "/api/vars" && m == "GET") { Write(c, Auto.VarList().ToString(), "application/json"); return true; }
            if (p == "/api/vars" && m == "POST") { var b = Body(c); Write(c, Auto.VarSet((string)b["name"], (string)b["value"], (bool?)b["persist"] != false).ToString(), "application/json"); return true; }
            if (p == "/api/vars/delete" && m == "POST") { Write(c, Auto.VarDelete((string)Body(c)["name"] ?? "").ToString(), "application/json"); return true; }
            if (p == "/api/queues" && m == "GET") { Write(c, Auto.QueueState().ToString(), "application/json"); return true; }
            if (p.StartsWith("/api/queues/") && m == "POST") { Write(c, Auto.QueueControl(p.Substring(12)).ToString(), "application/json"); return true; }
            if (p == "/api/automations/triggers" && m == "GET") { Write(c, Auto.TriggerList().ToString(), "application/json"); return true; }
            if (p == "/api/automations/hotkeys" && m == "GET") { Write(c, Auto.HotkeyList().ToString(), "application/json"); return true; }
            if (p == "/api/automations/export" && m == "GET") { Write(c, Auto.Export().ToString(), "application/json"); return true; }
            if (p == "/api/automations/enable" && m == "POST") { var b = Body(c); Write(c, Auto.Enable((string)b["id"], (string)b["group"], (bool?)b["on"] != false).ToString(), "application/json"); return true; }
            if (p == "/api/endpoints" && m == "GET") { Write(c, Auto.Endpoints().ToString(), "application/json"); return true; }
            if (p == "/api/session" && m == "GET") { Write(c, Session.Api().ToString(), "application/json"); return true; }
            if (p == "/api/goals" && m == "GET") { Write(c, Session.Goals().ToString(), "application/json"); return true; }
            if (p == "/api/credits" && m == "GET") { var cr = Credits.Build(); if (c.Request.QueryString["test"] == "1") Credits.Sample(cr); Write(c, cr.ToString(), "application/json"); return true; }
            if ((p == "/overlay/credits" || p == "/overlay/goal") && m == "GET")
            {
                string f = p == "/overlay/goal" ? Session.PagePath() : Credits.PagePath(); if (f == null) { c.Response.StatusCode = 404; return true; }
                Write(c, File.ReadAllText(f, Encoding.UTF8), "text/html; charset=utf-8"); return true;
            }
            if (p == "/overlay/intro" && m == "GET" || p == "/intro" && m == "GET")
            {
                string f = IntroPage(p == "/intro" ? "intro_controls.html" : "intro.html"); if (f == null) { c.Response.StatusCode = 404; return true; }
                Write(c, File.ReadAllText(f, Encoding.UTF8), "text/html; charset=utf-8"); return true;
            }
            if (p.StartsWith("/intro/media/") && m == "GET")
            {
                string f = Intro.MediaPath(Uri.UnescapeDataString(p.Substring("/intro/media/".Length))); if (f == null) { c.Response.StatusCode = 404; return true; }
                c.Response.ContentType = Intro.Mime(f); c.Response.Headers["Cache-Control"] = "no-store"; var fi = new FileInfo(f); c.Response.ContentLength64 = fi.Length;
                using (var fs = File.OpenRead(f)) fs.CopyTo(c.Response.OutputStream);
                return true;
            }
            if ((p == "/overlay/subfooter" || p == "/subfooter") && m == "GET")
            {
                string f = IntroPage(p == "/subfooter" ? "subfooter_controls.html" : "subfooter.html"); if (f == null) { c.Response.StatusCode = 404; return true; }
                Write(c, File.ReadAllText(f, Encoding.UTF8), "text/html; charset=utf-8"); return true;
            }
            if (p == "/api/commands-doc" && m == "GET") { Write(c, FeatureCommands.Doc().ToString(), "application/json"); return true; }
            if (p == "/helper-review" || p == "/api/helper/review")
            {   // private chat history: this computer only
                if (!System.Net.IPAddress.IsLoopback(c.Request.RemoteEndPoint.Address)) { c.Response.StatusCode = 403; return true; }
                if (p == "/helper-review" && m == "GET")
                {
                    string f = IntroPage("helper-review.html"); if (f == null) { c.Response.StatusCode = 404; return true; }
                    Write(c, File.ReadAllText(f, Encoding.UTF8), "text/html; charset=utf-8"); return true;
                }
                if (p == "/api/helper/review" && m == "GET") { int lim; int.TryParse(c.Request.QueryString["limit"], out lim); Write(c, HelperReview.List(c.Request.QueryString["kind"], c.Request.QueryString["q"], lim).ToString(), "application/json"); return true; }
                if (p == "/api/helper/review" && m == "POST") { var hb = Body(c); Write(c, HelperReview.SetNote((string)hb["id"], (string)hb["note"]).ToString(), "application/json"); return true; }
            }
            if (p == "/api/canned")
            {   // Chatty's canned commands: list / edit / add / test (this computer only)
                if (!System.Net.IPAddress.IsLoopback(c.Request.RemoteEndPoint.Address)) { c.Response.StatusCode = 403; return true; }
                if (m == "GET" && c.Request.QueryString["export"] == "1") { Write(c, CannedEditor.Export().ToString(), "application/json"); return true; }
                if (m == "GET") { Write(c, CannedEditor.List().ToString(), "application/json"); return true; }
                if (m == "POST" && !WriteOk(c.Request)) { c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"token required\"}", "application/json"); return true; }
                if (m == "POST") { Write(c, CannedEditor.Handle(Body(c)).ToString(), "application/json"); return true; }
            }
            if (p == "/api/clips-pick" && m == "GET")
            {   // a clip for a bot to post (own channel: featured, last 2 weeks, not one of the last 3 sent). Read only: the sender calls POST /api/clips-sent after posting.
                if (!ClipLocalOnly(c)) { c.Response.StatusCode = 403; return true; }
                bool rsv = c.Request.QueryString["reserve"] == "1"; var pk = rsv ? ClipPick.PickOwnReserved(c.Request.QueryString["by"]) : ClipPick.PickOwn(); Write(c, new JObject { { "ok", true }, { "clip", pk == null ? null : new JObject { { "id", pk["id"] }, { "url", pk["url"] }, { "title", pk["title"] }, { "views", pk["view_count"] }, { "created_at", pk["created_at"] } } }, { "recent", new JArray(ClipPick.Recent()) } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/clips-sent" && m == "POST")
            {   // a bot posted this clip: remember it in the shared last-clips list (idempotent: marking the clip that was marked last changes nothing)
                if (!ClipLocalOnly(c)) { c.Response.StatusCode = 403; return true; }
                var cb = Body(c); string cu = (string)cb["url"] ?? (string)cb["id"] ?? ""; if (ClipPick.IdOf(cu) == "") { c.Response.StatusCode = 400; Write(c, "{\"ok\":false,\"error\":\"url required\"}", "application/json"); return true; }
                bool rel = (bool?)cb["release"] == true, already = ClipPick.Recent(1).LastOrDefault() == ClipPick.IdOf(cu);
                if (rel) { Write(c, new JObject { { "ok", true }, { "released", ClipPick.Confirm(cu, true) } }.ToString(), "application/json"); return true; }
                if (already) ClipPick.Confirm(cu, false); else ClipPick.Mark(cu, (string)cb["by"] ?? "bot");
                Write(c, new JObject { { "ok", true }, { "already", already } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/clips-dump" && m == "GET") { Write(c, ClipsDump.Run().ToString(), "application/json"); return true; }
            if (p == "/api/helix-ids" && m == "GET")
            {   // reads Data\namehistory\lookups.json {ids:[...]}, asks Helix /users by id (batches of 100) with the Host's own streamer credentials, saves Data\namehistory\helix_ids.json {data:[{id,login}]}; credentials never leave the Host
                try
                {
                    string dd = HostApi.DataDir.TrimEnd('\\', '/'); string root = string.Equals(Path.GetFileName(dd), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(dd) : dd;
                    string dir = Path.Combine(root, "namehistory"); var ids = JObject.Parse(File.ReadAllText(Path.Combine(dir, "lookups.json"), Encoding.UTF8).TrimStart('﻿'))["ids"] as JArray ?? new JArray();
                    var rows = new JArray(); string err = "", lastErr = "";
                    var todo = new Stack<List<string>>(); var all = ids.Select(x => (string)x).Where(x => !string.IsNullOrEmpty(x)).ToList();
                    for (int i = all.Count - (all.Count % 100 == 0 ? 100 : all.Count % 100); i >= 0; i -= 100) todo.Push(all.Skip(i).Take(100).ToList());
                    int bad = 0;
                    while (todo.Count > 0)
                    {   // a batch with an invalid id answers 400: split it until the bad single ids are known and skipped
                        var batch = todo.Pop(); string q = string.Join("&", batch.Select(x => "id=" + Uri.EscapeDataString(x))); JToken data;
                        string code = TwitchApi.Call(HttpMethod.Get, "/users?" + q, null, out data, out err);
                        if (code == "429") { System.Threading.Thread.Sleep(5000); todo.Push(batch); continue; }
                        if (code == "400") { if (batch.Count == 1) bad++; else { int h = batch.Count / 2; todo.Push(batch.Skip(h).ToList()); todo.Push(batch.Take(h).ToList()); } continue; }
                        if (code != "200") { lastErr = err; break; }
                        foreach (var u in (data as JArray) ?? new JArray()) rows.Add(new JObject { { "id", u["id"] }, { "login", u["login"] } });
                    }
                    if (bad > 0) lastErr = lastErr == "" ? "" : lastErr;
                    if (rows.Count > 0) File.WriteAllText(Path.Combine(dir, "helix_ids.json"), new JObject { { "data", rows } }.ToString(), new UTF8Encoding(false));
                    Write(c, new JObject { { "ok", rows.Count > 0 || lastErr == "" }, { "asked", ids.Count }, { "found", rows.Count }, { "invalidIds", bad }, { "error", lastErr } }.ToString(), "application/json");
                }
                catch (Exception ex) { Write(c, new JObject { { "ok", false }, { "error", ex.Message } }.ToString(), "application/json"); }
                return true;
            }
            if (CmdRoutes(c, p, m)) return true;
            if (SimRoutes(c, p, m)) return true;
            if (EventRoutes(c, p, m)) return true;
            if (DiscordRoutes(c, p, m)) return true;
            if (TuneRoutes(c, p, m)) return true;
            if (p == "/api/livelog" && m == "GET") { Write(c, LiveLog.Api().ToString(), "application/json"); return true; }
            if (p == "/api/teach" && m == "GET") { Write(c, Teach.Api(c.Request.QueryString["status"]).ToString(), "application/json"); return true; }
            if (p == "/api/teach" && m == "POST") { Write(c, Teach.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/teach/decide" && m == "POST") { Write(c, Teach.Decide(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/links" && m == "GET") { var lj = Links.Doc(); lj["mismatches"] = Links.Audit(ChannelLore.AllEntries()); Write(c, lj.ToString(), "application/json"); return true; }
            if (p == "/api/links" && m == "POST") { var lb = Body(c); lock (typeof(Links)) { var ld = Links.Doc(); var lk = (JObject)ld["links"]; if (lb["links"] is JObject nl) foreach (var pr in nl.Properties()) lk[pr.Name.ToLowerInvariant()] = pr.Value; System.IO.File.WriteAllText(System.IO.Path.Combine(HostApi.DataDir, "links.json"), ld.ToString(), new UTF8Encoding(false)); } Write(c, "{\"ok\":true}", "application/json"); return true; }
            if ((p == "/api/intro/viewer" || (p == "/api/intro" && c.Request.QueryString["user_id"] != null)) && m == "GET")   // Multi (/api/intro/viewer; plain /api/intro with user_id still works): the approved intro of one viewer, else 404
            { var iq = c.Request.QueryString; var ij = !string.IsNullOrEmpty(iq["user_id"]) ? ViewerIntro.Approved(iq["platform"], iq["user_id"]) : ViewerIntro.ApprovedByLogin(iq["platform"], iq["login"]); if (ij == null) { c.Response.StatusCode = 404; Write(c, "{\"ok\":false,\"error\":\"no approved intro\"}", "application/json"); } else Write(c, ij.ToString(), "application/json"); return true; }
            if (p == "/api/intros" && m == "GET") { var q = c.Request.QueryString; Write(c, (q["user_id"] != null ? ViewerIntro.Mine(q["platform"], q["user_id"]) : ViewerIntro.List(q["status"])).ToString(), "application/json"); return true; }
            if (p == "/api/intros" && m == "POST") { var ib = Body(c); Write(c, ViewerIntro.Act((string)ib["action"], ib).ToString(), "application/json"); return true; }
            if (p == "/api/subtickets") { Write(c, SubTickets.Api(m, m == "POST" ? Body(c) : new JObject()).ToString(), "application/json"); return true; }
            if (p == "/api/giftags") { if (m == "POST") { var gb = Body(c); if ((bool?)gb["backfill"] == true) GiftTags.Backfill(); } Write(c, GiftTags.Report().ToString(), "application/json"); return true; }
            if (p == "/api/modaudit" && m == "GET") { int ml; if (!int.TryParse(c.Request.QueryString["limit"], out ml)) ml = 200; Write(c, ModAudit.Read(ml, c.Request.QueryString["before"]).ToString(), "application/json"); return true; }
            if (p == "/api/sitebridge" && m == "GET") { Write(c, SiteHttp.Status().ToString(), "application/json"); return true; }
            if (p == "/api/lore" && m == "GET") { Write(c, ChannelLore.Api().ToString(), "application/json"); return true; }
            if (p == "/api/lore" && m == "POST") { Write(c, ChannelLore.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/profile-sync" && m == "GET") { Write(c, ProfileSync.Api().ToString(), "application/json"); return true; }
            if (p == "/api/profile-sync" && m == "POST") { Write(c, ProfileSync.Post(Body(c)).ToString(), "application/json"); return true; }
            if ((p == "/api/points" || p == "/api/points/loan" || p.StartsWith("/api/economy/")) && (p == "/api/points" || p == "/api/points/loan" || p == "/api/economy/me" || p == "/api/economy/public" || p == "/api/economy/depreciation" || p == "/api/economy/loan" || p == "/api/economy/stream" || p == "/api/economy/preview" || p == "/api/economy/event" || p == "/api/economy/streams" || p == "/api/economy/points-settings" || p == "/api/economy/backpay")) { var qj = new Newtonsoft.Json.Linq.JObject(); foreach (string qk in c.Request.QueryString.AllKeys) if (qk != null) qj[qk] = c.Request.QueryString[qk]; var r2 = Economy.Phase2Api(p, m, c.Request.QueryString["login"] ?? "", m == "POST" ? Body(c) : qj); if (r2 != null) { Write(c, r2.ToString(), "application/json"); return true; } }
            if (p == "/api/economy" && m == "GET") { Write(c, Economy.Api().ToString(), "application/json"); return true; }
            if (p == "/api/economy/user" && m == "GET") { Write(c, Economy.User(c.Request.QueryString["login"] ?? "").ToString(), "application/json"); return true; }
            if (p == "/api/economy/import" && m == "POST") { Write(c, Economy.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/economy" && m == "POST") { Write(c, Economy.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/stream-timers" && m == "GET") { Write(c, StreamTimers.Api(c.Request.QueryString["id"]).ToString(), "application/json"); return true; }
            if (p == "/api/stream-timers" && m == "POST") { Write(c, StreamTimers.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/reminders" && m == "GET") { Write(c, Reminders.Api(c.Request.QueryString["user"]).ToString(), "application/json"); return true; }
            if (p == "/api/timers" && m == "GET") { Write(c, Timers.Api().ToString(), "application/json"); return true; }
            if (p == "/api/timers" && m == "POST") { Write(c, Timers.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/emotes" && m == "GET") { int lim; int.TryParse(c.Request.QueryString["limit"], out lim); Write(c, Emotes.Api(c.Request.QueryString["q"], c.Request.QueryString["month"], lim).ToString(), "application/json"); return true; }
            if (p == "/api/emotes/refresh" && m == "POST") { Write(c, Emotes.Refresh(true).ToString(), "application/json"); return true; }
            if (p == "/api/boards" && m == "GET" && c.Request.QueryString["metric"] != null) { var q = c.Request.QueryString; int tp; Write(c, Periods.Query(q["metric"], q["period"], q["key"], q["login"] ?? q["me"], int.TryParse(q["top"], out tp) ? tp : 10).ToString(), "application/json"); return true; }
            if (p == "/api/queue-idle" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; if (c.Request.QueryString["js"] != null) Write(c, "window.QUEUE_IDLE=" + QueueIdle.Api().ToString(Newtonsoft.Json.Formatting.None) + ";", "application/javascript; charset=utf-8"); else Write(c, QueueIdle.Api().ToString(), "application/json"); return true; }
            if (p == "/api/scene-widgets" && m == "GET") { Write(c, Scenes.Widgets().ToString(), "application/json"); return true; }
            if (p == "/api/scene-layouts" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = Scenes.Get(c.Request.QueryString["profile"], c.Request.QueryString["layout"]).ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.SCENE_LAYOUT=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/scene-health" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; Write(c, Scenes.Health().ToString(), "application/json"); return true; }
            if (p == "/api/scene-layouts" && m == "POST") { Write(c, Scenes.Set(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/overlay-options/health" && m == "GET") { Write(c, OverlayOptions.Health().ToString(), "application/json"); return true; }
            if (p == "/api/overlay-options/schema" && m == "GET") { Write(c, OverlayOptions.Schema().ToString(), "application/json"); return true; }
            if (p == "/api/overlay-options" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = OverlayOptions.Get(c.Request.QueryString["name"]).ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.OVERLAY_OPTIONS=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/overlay-options" && m == "POST") { Write(c, OverlayOptions.Set(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/subroll" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = SubRoll.Api(c.Request.QueryString["mode"]).ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.SUBROLL=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/subroll/state" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = SubRoll.State().ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.SUBROLL_STATE=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/subroll/start" && m == "POST") { Write(c, SubRoll.Start(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/subroll/stop" && m == "POST") { Write(c, SubRoll.Stop().ToString(), "application/json"); return true; }
            if (p == "/api/boards/twitch-bits" && m == "GET") { int n; if (!int.TryParse(c.Request.QueryString["count"], out n)) n = 100; Write(c, TwitchBits.Get(c.Request.QueryString["period"], n).ToString(), "application/json"); return true; }
            if (p == "/api/boards/reload" && m == "POST") { Write(c, Periods.Reload().ToString(), "application/json"); return true; }
            if (p == "/api/boards/event" && m == "POST") { Write(c, Periods.TestEvent(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/boards" && m == "GET") { Write(c, Boards.Api().ToString(), "application/json"); return true; }
            if (p == "/api/boards/refresh" && m == "POST") { Write(c, Boards.Refresh(true).ToString(), "application/json"); return true; }
            if (p == "/api/streaks" && m == "GET") { Write(c, Streaks.Api().ToString(), "application/json"); return true; }
            if (p == "/api/streaks/backfill" && m == "POST") { Write(c, Streaks.Backfill().ToString(), "application/json"); return true; }
            if (p == "/api/subs" && m == "GET") { Write(c, SubsImport.Api().ToString(), "application/json"); return true; }
            if (p == "/api/subs/import" && m == "POST") { Write(c, SubsImport.ScanAndImport().ToString(), "application/json"); return true; }
            if (p == "/api/subfooter" && m == "GET") { Write(c, SubBoard.Api().ToString(), "application/json"); return true; }
            if (p == "/api/subfooter/settings" && m == "POST") { Write(c, SubBoard.Save(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/subfooter/refresh" && m == "POST") { System.Threading.Tasks.Task.Run(() => SubBoard.Refresh(true)); Write(c, "{\"ok\":true}", "application/json"); return true; }
            if (p == "/api/intro" && m == "GET") { Write(c, Intro.Api().ToString(), "application/json"); return true; }
            if (p == "/api/intro/poll" && m == "GET") { Write(c, Intro.Poll(c.Request.QueryString["slot"]).ToString(), "application/json"); return true; }
            if (p == "/api/intro/done" && m == "GET") { Write(c, Intro.Done(long.TryParse(c.Request.QueryString["id"], out long iid) ? iid : 0).ToString(), "application/json"); return true; }
            if (p == "/api/intro/skip" && m == "POST") { Write(c, Intro.Skip().ToString(), "application/json"); return true; }
            if (p == "/api/intro/clear" && m == "POST") { Write(c, Intro.Clear().ToString(), "application/json"); return true; }
            if (p == "/api/intro/reset" && m == "POST") { Write(c, Intro.ResetPlayed().ToString(), "application/json"); return true; }
            if (p == "/api/intro/test" && m == "POST") { var b = Body(c); Write(c, Intro.Test((string)b["login"], (int?)b["tier"] ?? 1).ToString(), "application/json"); return true; }
            if (p == "/api/intro/settings" && m == "POST") { Write(c, Intro.Save(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/live" && m == "GET") { Write(c, LiveState.Api().ToString(), "application/json"); return true; }
            if (p == "/api/chat-rate" && m == "GET")
            {   // written by ChattyPinguino once a minute while live: chat lines per minute per stream, averages, the limits in force
                string f = Path.Combine(DataDir, "chat_rate_history.json");
                Write(c, File.Exists(f) ? File.ReadAllText(f, Encoding.UTF8) : "{\"stats\":{\"minutes\":0,\"streams\":0},\"streams\":[]}", "application/json"); return true;
            }
            if (p == "/api/spotify-announce" && m == "GET") { Write(c, SpotifyAnnounce.Api().ToString(), "application/json"); return true; }
            if (p == "/api/spotify-announce" && m == "POST") { Write(c, SpotifyAnnounce.Save(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/cutover" && m == "GET") { Write(c, Cutover.State().ToString(), "application/json"); return true; }
            if (p == "/api/cutover" && m == "POST") { var b = Body(c); Write(c, Cutover.Set((bool?)b["on"] == true).ToString(), "application/json"); return true; }
            if (p == "/api/latest" && m == "GET") { Write(c, Latest.Api().ToString(), "application/json"); return true; }
            if ((p == "/overlay/latest" || p == "/overlay/latest.html") && m == "GET")
            {
                string f = Latest.PagePath(); if (f == null) { c.Response.StatusCode = 404; return true; }
                Write(c, File.ReadAllText(f, Encoding.UTF8), "text/html; charset=utf-8"); return true;
            }
            if (p == "/api/shoutouts" && m == "GET") { Write(c, Shout.Status().ToString(), "application/json"); return true; }
            if (p == "/api/shoutouts" && m == "POST")
            {
                var b = Body(c); string r = Shout.Enqueue((string)b["user"] ?? "", (string)b["by"] ?? "api", false);
                Write(c, new JObject { { "ok", true }, { "result", r } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/automations" && m == "GET") { Write(c, new JObject { { "ok", true }, { "doc", Auto.Doc() }, { "master", Lease.MayRun } }.ToString(), "application/json"); return true; }
            if (p == "/api/automations" && m == "POST")
            {
                var b = Body(c); var doc = b["doc"] as JObject ?? b; string err = Auto.Save(doc);
                Write(c, (err == null ? new JObject { { "ok", true } } : new JObject { { "ok", false }, { "error", err } }).ToString(), "application/json"); return true;
            }
            if (p == "/api/automations/test" && m == "POST")
            {
                var b = Body(c); bool dry = (bool?)b["dry"] != false;
                Write(c, Auto.Test((string)b["id"] ?? (string)b["name"] ?? "", b["args"] as JObject, dry).ToString(), "application/json"); return true;
            }
            if (p == "/api/automations/fire" && m == "POST")
            {
                var b = Body(c); string k = (string)b["hotkey"] ?? ""; Write(c, (k == "" ? new JObject { { "ok", false }, { "error", "hotkey required" } } : Auto.Hotkey(k)).ToString(), "application/json"); return true;
            }
            if (p == "/api/automations/log" && m == "GET")
            {
                int n = int.TryParse(c.Request.QueryString["n"], out int nn) ? Math.Max(1, Math.Min(200, nn)) : 50;
                Write(c, new JObject { { "ok", true }, { "runs", Auto.Log(n) } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/automations/import" && m == "POST") { Write(c, AutoImport.Run(Body(c)).ToString(), "application/json"); return true; }
            return false;
        }
    }
}
