using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
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
                catch (Exception ex) { Clog.Warn("automation", "chat send as " + r + " failed: " + ex.Message); }
            }
            if (Program.SayShared(text)) { via = "shared account"; return true; }
            via = "no account could send (not signed in, or sim mode)"; return false;
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
