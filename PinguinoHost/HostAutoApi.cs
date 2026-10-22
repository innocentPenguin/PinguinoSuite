using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    public static partial class HostApi
    {
        /// <summary>Say a line in chat as one of the bots (own Twitch login first, then PinguinoB0t, then the rest of its fallback chain, then the shared account).</summary>
        public static bool SendAs(string role, string text, out string via)
        {
            via = "";
            if (!Lease.MayRun) { via = "this Host is not the master"; return false; }
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
                        rq.Content = new StringContent(new JObject { { "broadcaster_id", bid }, { "sender_id", sid }, { "message", text } }.ToString(), Encoding.UTF8, "application/json");
                        var resp = http.SendAsync(rq).Result;
                        if (resp.IsSuccessStatusCode) { via = (string)bot["Account"] ?? r; return true; }
                        Clog.Warn("automation", "chat send as " + r + " refused (HTTP " + (int)resp.StatusCode + ")");
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

        // NEVER SAY THE SAME LINE TWICE: every chat send (timers, reminders, commands, shoutouts...) passes here. Same text (case/spacing ignored) inside the window is dropped.
        static readonly System.Collections.Generic.Dictionary<string, DateTime> _said = new System.Collections.Generic.Dictionary<string, DateTime>();
        public static int DupSeconds { get { int n; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_DUP_SECONDS"), out n) ? n : 30; } }
        public static bool SaidRecently(string text)
        {
            string k = System.Text.RegularExpressions.Regex.Replace((text ?? "").ToLowerInvariant(), "[​‍️]", "");
            k = System.Text.RegularExpressions.Regex.Replace(k, @"\s+", " ").Trim(); int win = DupSeconds;
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
            if ((p == "/api/channel/update" || p == "/api/mod/timeout") && m == "POST")   // Speak module: module token always required, every call audit-logged
            {
                if (!HostApi.StrictTokenOk(c.Request)) { c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"module token required\"}", "application/json"); return true; }
                var b = Body(c); JObject res; string who = "module:speak";
                if (p == "/api/channel/update") { res = ChannelControl.Update((string)b["title"], (string)b["game"]); ChannelControl.Audit(who, "channel/update", "title=" + (string)b["title"] + " game=" + (string)b["game"] + " -> " + (bool?)res["ok"] + " " + (string)res["error"]); }
                else { res = ChannelControl.Timeout((string)b["user"], (int?)b["seconds"] ?? 0, (string)b["reason"]); ChannelControl.Audit(who, "mod/timeout", "user=" + (string)b["user"] + " seconds=" + (int?)b["seconds"] + " reason=" + (string)b["reason"] + " -> " + (bool?)res["ok"] + " " + (string)res["error"]); }
                Write(c, res.ToString(), "application/json"); return true;
            }
            if (p == "/api/say" && m == "POST")   // modules (Multi, Speak): say one line in chat through the Host, so the 30 s duplicate guard and the no-retry-on-timeout rule apply
            {
                if (!HostApi.StrictTokenOk(c.Request)) { c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"module token required\"}", "application/json"); return true; }
                var b = Body(c); string text = ((string)b["text"] ?? "").Trim();
                if (text == "" || text.Length > 500) { Write(c, "{\"ok\":false,\"error\":\"text required (max 500 characters)\"}", "application/json"); return true; }
                string via; bool ok = SendAs((string)b["bot"], text, out via);
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
                if (m == "GET") { Write(c, CannedEditor.List().ToString(), "application/json"); return true; }
                if (m == "POST") { Write(c, CannedEditor.Handle(Body(c)).ToString(), "application/json"); return true; }
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
            if (TuneRoutes(c, p, m)) return true;
            if (p == "/api/livelog" && m == "GET") { Write(c, LiveLog.Api().ToString(), "application/json"); return true; }
            if (p == "/api/teach" && m == "GET") { Write(c, Teach.Api(c.Request.QueryString["status"]).ToString(), "application/json"); return true; }
            if (p == "/api/teach" && m == "POST") { Write(c, Teach.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/teach/decide" && m == "POST") { Write(c, Teach.Decide(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/links" && m == "GET") { var lj = Links.Doc(); lj["mismatches"] = Links.Audit(ChannelLore.AllEntries()); Write(c, lj.ToString(), "application/json"); return true; }
            if (p == "/api/links" && m == "POST") { var lb = Body(c); lock (typeof(Links)) { var ld = Links.Doc(); var lk = (JObject)ld["links"]; if (lb["links"] is JObject nl) foreach (var pr in nl.Properties()) lk[pr.Name.ToLowerInvariant()] = pr.Value; System.IO.File.WriteAllText(System.IO.Path.Combine(HostApi.DataDir, "links.json"), ld.ToString(), new UTF8Encoding(false)); } Write(c, "{\"ok\":true}", "application/json"); return true; }
            if (p == "/api/sitebridge" && m == "GET") { Write(c, SiteHttp.Status().ToString(), "application/json"); return true; }
            if (p == "/api/lore" && m == "GET") { Write(c, ChannelLore.Api().ToString(), "application/json"); return true; }
            if (p == "/api/lore" && m == "POST") { Write(c, ChannelLore.Post(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/profile-sync" && m == "GET") { Write(c, ProfileSync.Api().ToString(), "application/json"); return true; }
            if (p == "/api/profile-sync" && m == "POST") { Write(c, ProfileSync.Post(Body(c)).ToString(), "application/json"); return true; }
            if ((p == "/api/points" || p == "/api/points/loan" || p.StartsWith("/api/economy/")) && (p == "/api/points" || p == "/api/points/loan" || p == "/api/economy/me" || p == "/api/economy/depreciation" || p == "/api/economy/loan" || p == "/api/economy/stream" || p == "/api/economy/preview" || p == "/api/economy/event" || p == "/api/economy/streams" || p == "/api/economy/points-settings")) { var qj = new Newtonsoft.Json.Linq.JObject(); foreach (string qk in c.Request.QueryString.AllKeys) if (qk != null) qj[qk] = c.Request.QueryString[qk]; var r2 = Economy.Phase2Api(p, m, c.Request.QueryString["login"] ?? "", m == "POST" ? Body(c) : qj); if (r2 != null) { Write(c, r2.ToString(), "application/json"); return true; } }
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
            if (p == "/api/overlay-options/schema" && m == "GET") { Write(c, OverlayOptions.Schema().ToString(), "application/json"); return true; }
            if (p == "/api/overlay-options" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = OverlayOptions.Get(c.Request.QueryString["name"]).ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.OVERLAY_OPTIONS=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/overlay-options" && m == "POST") { Write(c, OverlayOptions.Set(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/subroll" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = SubRoll.Api(c.Request.QueryString["mode"]).ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.SUBROLL=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/subroll/state" && m == "GET") { c.Response.Headers["Cache-Control"] = "no-store"; string j = SubRoll.State().ToString(Newtonsoft.Json.Formatting.None); Write(c, c.Request.QueryString["js"] != null ? "window.SUBROLL_STATE=" + j + ";" : j, c.Request.QueryString["js"] != null ? "application/javascript; charset=utf-8" : "application/json"); return true; }
            if (p == "/api/subroll/start" && m == "POST") { Write(c, SubRoll.Start(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/subroll/stop" && m == "POST") { Write(c, SubRoll.Stop().ToString(), "application/json"); return true; }
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
