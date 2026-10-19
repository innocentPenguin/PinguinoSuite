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
            var reg = LoadFile("bots.json"); var sec = LoadFile("bots_secrets.json");
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
