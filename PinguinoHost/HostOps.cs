using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>One switch for "Streamer.bot is retired": the Streamer.bot replacement actions that would answer a second time while Streamer.bot still runs
    /// (alerts, !clip, !preroll, !whyad, ban alert, First 5 game ...) are flagged "cutover" and stay OFF until it is switched on, then all go ON at once (and OFF again if switched back).
    /// State: Data\runtime\cutover.json. Page button: Actions &amp; Events > "Streamer.bot cutover". API: GET/POST /api/cutover {"on":true}.</summary>
    public static class Cutover
    {
        static string FilePath { get { return Path.Combine(HostApi.DataDir, "cutover.json"); } }
        public static bool On { get { try { return File.Exists(FilePath) && (bool?)JObject.Parse(File.ReadAllText(FilePath))["on"] == true; } catch (Exception) { return false; } } }
        public static bool StreamerBotRunning()
        {
            int port = int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_SB_PORT"), out int sp) ? sp : 8080;
            try { using (var tc = new TcpClient()) return tc.ConnectAsync("127.0.0.1", port).Wait(500); } catch (Exception) { return false; }
        }
        public static JObject State()
        {
            var flagged = ((JArray)Auto.Doc()["actions"]).OfType<JObject>().Where(a => (bool?)a["cutover"] == true).Select(a => (string)a["name"]).ToList();
            return new JObject { { "ok", true }, { "on", On }, { "firstFiveGameOn", On }, { "streamerBotRunning", StreamerBotRunning() }, { "actions", new JArray(flagged) } };
        }
        public static JObject Set(bool on)
        {
            File.WriteAllText(FilePath, new JObject { { "on", on }, { "at", DateTime.UtcNow.ToString("o") } }.ToString());
            var doc = Auto.Doc(); int n = 0;
            foreach (var a in ((JArray)doc["actions"]).OfType<JObject>().Where(a => (bool?)a["cutover"] == true)) { a["enabled"] = on; n++; }
            string err = Auto.Save(doc); if (err != null) return new JObject { { "ok", false }, { "error", err } };
            bool sb = StreamerBotRunning();
            Clog.Info("cutover", "Streamer.bot cutover " + (on ? "ON" : "OFF") + ": " + n + " actions " + (on ? "enabled" : "disabled") + (on && sb ? " (WARNING: Streamer.bot is still running, expect double answers)" : ""));
            var r = State(); r["changed"] = n; return r;
        }
    }

    /// <summary>how late Twitch's EventSub messages arrive: every message carries its send time, so now minus that is the transport delay (keepalives every ~10 s, real events too).</summary>
    public static class Lag
    {
        static readonly Queue<double> Q = new Queue<double>(); static readonly object L = new object(); static double _lastEvent = -1; static DateTime _lastEventAt = DateTime.MinValue;
        public static void Note(string ts, bool isEvent)
        {
            DateTime t; if (!DateTime.TryParse(ts, null, System.Globalization.DateTimeStyles.RoundtripKind, out t)) return;
            double ms = Math.Max(0, (DateTime.UtcNow - t.ToUniversalTime()).TotalMilliseconds);
            lock (L) { Q.Enqueue(ms); while (Q.Count > 60) Q.Dequeue(); if (isEvent) { _lastEvent = ms; _lastEventAt = DateTime.UtcNow; } }
        }
        public static JObject Stats()
        {
            lock (L)
            {
                if (Q.Count == 0) return new JObject { { "samples", 0 } };
                var a = Q.ToList(); a.Sort();
                return new JObject { { "samples", a.Count }, { "avgMs", (int)a.Average() }, { "medianMs", (int)a[a.Count / 2] }, { "maxMs", (int)a.Last() },
                    { "lastEventMs", _lastEvent < 0 ? (JToken)null : (int)_lastEvent }, { "lastEventAgoSec", _lastEvent < 0 ? (JToken)null : (int)(DateTime.UtcNow - _lastEventAt).TotalSeconds } };
            }
        }
    }

    /// <summary>Optional mirror of the activity feed to innocentpenguin.com (POST /api/bot/events, public names only). Off by default: latest_settings.json
    /// { "ForwardToSite": true, "SiteEventsUrl": "https://innocentpenguin.com/api/bot/events" }. The key is the vault name BOT_API_KEY (or the BOT_API_KEY environment variable).</summary>
    public static class SiteFeed
    {
        static long _sent = -1; static bool _started; static string _lastResult = "off";
        static string StatePath { get { return Path.Combine(HostApi.DataDir, "site_forward.json"); } }
        public static string Status() { return _lastResult; }
        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { while (true) { await Task.Delay(5000); try { Tick(); } catch (Exception ex) { _lastResult = "error: " + ex.Message; } } });
        }
        static string Type(string t) { switch (t) { case "gift": return "giftsub"; case "sub": case "resub": case "cheer": case "follow": case "raid": return t; default: return null; } }
        static void Tick()
        {
            var s = Latest.Settings(); if ((bool?)s["ForwardToSite"] != true) { _lastResult = "off"; return; }
            string key = Vault.Get("BOT_API_KEY"); if (key == "") key = Environment.GetEnvironmentVariable("BOT_API_KEY") ?? "";
            if (key == "") { _lastResult = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            if (_sent < 0) { try { _sent = File.Exists(StatePath) ? (long)JObject.Parse(File.ReadAllText(StatePath))["sent"] : (long)Latest.Activity(0, 1, null)["seq"]; } catch (Exception) { _sent = 0; } }
            var items = ((JArray)Latest.Activity(_sent, 50, null)["items"]).OfType<JObject>().ToList(); if (items.Count == 0) return;
            var events = new JArray();
            foreach (var e in items)
            {
                string ty = Type((string)e["type"]); if (ty == null) continue;
                var o = new JObject { { "id", "host-" + (long)e["ts"] + "-" + (long)e["seq"] }, { "type", ty }, { "user", e["user"] }, { "at", (long)e["ts"] * 1000 } };
                if (e["amount"] != null) o["amount"] = e["amount"]; if (e["tier"] != null) o["tier"] = ((int)e["tier"]).ToString();
                events.Add(o);
            }
            long top = items.Max(e => (long)e["seq"]);
            if (events.Count > 0)
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
                {
                    var rq = new HttpRequestMessage(HttpMethod.Post, (string)s["SiteEventsUrl"] ?? "https://innocentpenguin.com/api/bot/events") { Content = new StringContent(new JObject { { "events", events } }.ToString(), Encoding.UTF8, "application/json") };
                    rq.Headers.Add("Authorization", "Bearer " + key);
                    var r = h.SendAsync(rq).Result;
                    if (!r.IsSuccessStatusCode) { _lastResult = "site answered HTTP " + (int)r.StatusCode; Clog.Warn("site", "events not accepted (HTTP " + (int)r.StatusCode + "), will retry"); return; }
                }
            }
            _sent = top; File.WriteAllText(StatePath, new JObject { { "sent", _sent } }.ToString()); _lastResult = "ok (" + events.Count + " sent, up to #" + _sent + ")";
        }
    }

    /// <summary>"!pg" for mods: quick bot control from chat.</summary>
    public static class PgCommand
    {
        static readonly string[] Roles = { "core", "chat", "helper" };
        public static bool Handle(string user, string text, int role)
        {
            var parts = text.Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0 || !string.Equals(parts[0], "!pg", StringComparison.OrdinalIgnoreCase)) return false;
            if (role < 3) return true;   // only mods and the streamer; others get nothing
            string sub = parts.Length > 1 ? parts[1].ToLowerInvariant() : "help"; string reply;
            try
            {
                switch (sub)
                {
                    case "status": reply = Status(); break;
                    case "on": case "off":
                        reply = "usage: !pg " + sub + " core|chat|helper"; break;
                    case "core": case "chat": case "helper":
                        if (parts.Length < 3 || (parts[2] != "on" && parts[2] != "off")) { reply = "usage: !pg " + sub + " on|off"; break; }
                        { var r = HostApi.SetBotEnabled(sub, parts[2] == "on"); reply = (bool)r["ok"] ? sub + " is now " + parts[2].ToUpperInvariant() : "could not change " + sub + ": " + (string)r["error"]; }
                        break;
                    case "test":
                        foreach (var r in Roles) { string via; bool ok = HostApi.SendAs(r, "test from " + r + " 🐧", out via); Console.WriteLine("[pg] test " + r + ": " + (ok ? "said as " + via : "NOT sent (" + via + ")")); Thread.Sleep(1200); }
                        return true;
                    case "cutover": reply = Cutover.On ? "Streamer.bot cutover is ON" : "Streamer.bot cutover is OFF (replacement alerts/!clip/First 5 are waiting)"; break;
                    default: reply = "!pg status | !pg core|chat|helper on|off | !pg test (each bot says hi) | !pg cutover"; break;
                }
            }
            catch (Exception ex) { reply = "!pg failed: " + ex.Message; }
            string v; if (!HostApi.SendAs("core", reply, out v)) { Console.WriteLine("[pg] " + reply); Clog.Info("pg", reply + " (not sent to chat: " + v + ")"); }
            return true;
        }
        static string Status()
        {
            var bots = HostApi.BotsSnapshot(); var sb = new StringBuilder();
            foreach (JObject b in (JArray)bots["bots"]) sb.Append((string)b["id"]).Append(' ').Append((bool)b["enabled"] ? "on" : "OFF").Append(((bool)b["signedIn"]) ? " (" + (string)b["signedInAs"] + ")" : " (no login)").Append(" | ");
            var lag = Lag.Stats(); var st = HostApi.StatusSnapshot();
            sb.Append("chat ").Append((bool)st["chatConnected"] ? "ok" : "DOWN").Append(", eventsub ").Append((bool)st["eventSubConnected"] ? "ok" + (lag["medianMs"] != null ? " " + (int)lag["medianMs"] + "ms" : "") : "DOWN").Append(", obs ").Append((bool)st["obsConnected"] ? "ok" : "off");
            return sb.ToString();
        }
    }
}
