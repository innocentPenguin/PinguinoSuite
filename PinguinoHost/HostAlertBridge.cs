using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The bridge to PinguinoMulti's alert engine (03).
    ///  * !alert (mods / owner): test &lt;type&gt; [user] [amount] [variants...] | testall | stress [n] | profile &lt;name&gt; | skip | clear | pause | resume. Forwards to Multi /api/alerts/test|testall|stress|control and says only Multi's short `text`. Test events never touch credits, stats, points, latest or the event log.
    ///  * Watch celebrations: streak (every watch-streak notification), watchtime (hours boundary crossed), anniversary (years, once), comeback (first presence after a long gap) -> POST /api/alerts/fire with a stable id. Never test or sim items.
    ///  Settings: Data\alert_bridge.json {Url, Token, ComebackDays, WatchHours[], Enabled}. State: Data\alert_bridge_state.json.</summary>
    public static class AlertBridge
    {
        static readonly object L = new object();
        static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(6) };
        static JObject _state; static DateTime _saved = DateTime.MinValue; static bool _dirty;
        public static Func<string, JObject, JObject> TestPost;   // test hook: (path, body) -> response, replaces the network

        static string SetP { get { return Path.Combine(HostApi.DataDir, "alert_bridge.json"); } }
        static string StateP { get { return Path.Combine(HostApi.DataDir, "alert_bridge_state.json"); } }
        public static JObject Settings()
        {
            var d = new JObject { { "Enabled", true }, { "Url", "http://127.0.0.1:8766" }, { "Token", "" }, { "ComebackDays", 30 }, { "WatchHours", new JArray(10, 25, 50, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 3000, 5000) } };
            try { if (File.Exists(SetP)) foreach (var p in JObject.Parse(File.ReadAllText(SetP, Encoding.UTF8))) d[p.Key] = p.Value; else File.WriteAllText(SetP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            return d;
        }
        static JObject State()
        {
            lock (L)
            {
                if (_state != null) return _state;
                try { if (File.Exists(StateP)) _state = JObject.Parse(File.ReadAllText(StateP, Encoding.UTF8)); } catch (Exception) { }
                if (_state == null) _state = new JObject();
                foreach (var k in new[] { "lastSeen", "watch", "anniv", "fired" }) if (_state[k] == null) _state[k] = new JObject();
                return _state;
            }
        }
        static void Dirty() { lock (L) { _dirty = true; if ((DateTime.UtcNow - _saved).TotalSeconds < 30) return; Flush(); } }
        public static void Flush() { lock (L) { if (!_dirty || _state == null) return; try { File.WriteAllText(StateP, _state.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); _dirty = false; _saved = DateTime.UtcNow; } catch (Exception) { } } }

        // ================= HTTP to Multi =================
        static JObject Post(string path, JObject body)
        {
            if (TestPost != null) return TestPost(path, body);
            var set = Settings(); string url = ((string)set["Url"] ?? "http://127.0.0.1:8766").TrimEnd('/');
            var toks = new List<string>(); string t0 = (string)set["Token"] ?? ""; if (t0 != "") toks.Add(t0);
            foreach (var n in new[] { "PINGUINO_MODULE_TOKEN", "PINGUINO_API_TOKEN" }) { string v = Environment.GetEnvironmentVariable(n) ?? ""; if (v != "" && !toks.Contains(v)) toks.Add(v); }
            if (toks.Count == 0) toks.Add("");
            string last = "";
            foreach (var tok in toks)
            {
                try
                {
                    var rq = new HttpRequestMessage(HttpMethod.Post, url + path) { Content = new StringContent(body.ToString(Newtonsoft.Json.Formatting.None), Encoding.UTF8, "application/json") };
                    if (tok != "") { rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("X-Pinguino-Token", tok); }
                    var r = Http.SendAsync(rq).Result; string txt = r.Content.ReadAsStringAsync().Result;
                    if ((int)r.StatusCode == 401 || (int)r.StatusCode == 403) { last = "Multi refused the token (" + (int)r.StatusCode + ")"; continue; }
                    JObject j = null; try { j = JObject.Parse(txt); } catch (Exception) { }
                    if (j == null) return new JObject { { "ok", false }, { "text", "Multi answered " + (int)r.StatusCode } };
                    if (!r.IsSuccessStatusCode && j["text"] == null) j["text"] = (string)j["detail"] ?? ("Multi answered " + (int)r.StatusCode);
                    return j;
                }
                catch (Exception ex) { last = ex.InnerException != null ? ex.InnerException.Message : ex.Message; break; }
            }
            return new JObject { { "ok", false }, { "text", "Multi is not reachable (" + Short(last) + ")" } };
        }
        static string Short(string s) { s = (s ?? "").Replace("\r", " ").Replace("\n", " "); return s.Length > 70 ? s.Substring(0, 70) : s; }

        // ================= !alert =================
        public static bool IsCommand(string cmd) { return cmd == "!alert" || cmd == "!alerts"; }
        static readonly string[] Variants = { "tier1", "tier2", "tier3", "prime", "first", "refollow", "noavatar", "long", "unicode", "msg", "small", "mid", "big", "huge" };
        static readonly Dictionary<string, DateTime> Said = new Dictionary<string, DateTime>();

        /// <summary>mods and the owner only (the caller checks the role); returns what to say (null = nothing)</summary>
        public static string Handle(string user, string[] args)
        {
            string sub = args.Length > 0 ? args[0].ToLowerInvariant() : "";
            JObject r;
            switch (sub)
            {
                case "test":
                    {
                        if (args.Length < 2) return "Usage: !alert test <type> [user] [amount] [variants...]";
                        var body = new JObject { { "type", args[1].ToLowerInvariant() }, { "source", "chat" } };
                        var vars = new JArray(); string who = null; double amt; bool haveAmt = false;
                        foreach (var a in args.Skip(2))
                        {
                            string al = a.ToLowerInvariant();
                            if (Variants.Contains(al)) { vars.Add(al); if (al.StartsWith("tier") && al.Length == 5) body["tier"] = al.Substring(4); if (al == "prime") body["tier"] = "prime"; }
                            else if (!haveAmt && double.TryParse(a, NumberStyles.Float, CultureInfo.InvariantCulture, out amt)) { body["amount"] = amt; haveAmt = true; }
                            else if (who == null) who = a.TrimStart('@');
                        }
                        body["user"] = who ?? user; body["variant"] = vars; r = Post("/api/alerts/test", body); break;
                    }
                case "testall": r = Post("/api/alerts/testall", new JObject()); break;
                case "stress": { int n; r = Post("/api/alerts/stress", new JObject { { "n", args.Length > 1 && int.TryParse(args[1], out n) ? Math.Max(1, Math.Min(200, n)) : 20 } }); break; }
                case "profile": if (args.Length < 2) return "Usage: !alert profile <name>"; r = Post("/api/alerts/control", new JObject { { "action", "profile:" + string.Join(" ", args.Skip(1)) } }); break;
                case "skip": case "clear": case "pause": case "resume": r = Post("/api/alerts/control", new JObject { { "action", sub } }); break;
                default: return "Usage: !alert test <type> [user] [amount] [variants] | testall | stress [n] | profile <name> | skip | clear";
            }
            string text = (string)r["text"] ?? ((bool?)r["ok"] == true ? "done" : "not done");
            return Short2(text);
        }
        static string Short2(string s) { s = (s ?? "").Replace("\r", " ").Replace("\n", " "); return s.Length > 190 ? s.Substring(0, 190) : s; }
        /// <summary>chat reply with the 30 s duplicate guard</summary>
        public static void Reply(string text, Action<string> say)
        {
            if (string.IsNullOrEmpty(text)) return;
            lock (Said) { DateTime t; if (Said.TryGetValue(text, out t) && (DateTime.UtcNow - t).TotalSeconds < 30) return; Said[text] = DateTime.UtcNow; if (Said.Count > 50) Said.Clear(); }
            say(text);
        }

        // ================= fire (real watch celebrations) =================
        public static string AvatarOf(string login)
        {
            try { string f = Path.Combine(Economy.RootDir, "avatars.json"); if (File.Exists(f)) return (string)(JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF))[login]?["url"]) ?? ""; } catch (Exception) { }
            return "";
        }
        /// <summary>posts one real alert; a stable `id` makes Multi (and this bridge) show it once. Never for sim or test items.</summary>
        public static bool Fire(string type, string login, string id, string field, long value, string message = "")
        {
            var set = Settings(); if ((bool?)set["Enabled"] == false || string.IsNullOrEmpty(login) || Sim.IsSim(login)) return false;
            lock (L) { var f = (JObject)State()["fired"]; if (f[id] != null) return false; f[id] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); if (f.Count > 3000) foreach (var k in f.Properties().Take(1000).Select(p => p.Name).ToList()) f.Remove(k); Dirty(); }
            var body = new JObject { { "type", type }, { "user", login }, { "display", Boards.DisplayName(login) }, { "id", id }, { "amount", value }, { field, value } };
            string av = AvatarOf(login); if (av != "") body["avatar"] = av; if (message != "") body["message"] = message;
            var r = Post("/api/alerts/fire", body);
            bool ok = (bool?)r["ok"] == true;
            Clog.Info("alerts", type + " " + login + " " + value + " -> " + (ok ? "queued" : "not queued: " + Short((string)r["text"])));
            return ok;
        }
        public static void FireAsync(string type, string login, string id, string field, long value, string message = "") { ThreadPool.QueueUserWorkItem(_ => { try { Fire(type, login, id, field, value, message); } catch (Exception ex) { Clog.Warn("alerts", "fire failed: " + ex.Message); } }); }

        /// <summary>every watch-streak notification (viewer_milestone): Multi shows it once per id</summary>
        public static void OnStreak(string login, string notifId, long streak) { FireAsync("streak", login, "streak:" + (notifId != "" ? notifId : login + ":" + streak + ":" + DateTime.UtcNow.ToString("yyyyMMddHH")), "streak", streak); }

        /// <summary>called every minute with the people present while live: comeback after a long gap, watch-time boundaries, anniversaries</summary>
        public static void OnPresent(IEnumerable<string> logins, long now = 0)
        {
            if (now == 0) now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var set = Settings(); if ((bool?)set["Enabled"] == false) return;
            long gapSec = (long)(((double?)set["ComebackDays"] ?? 30) * 86400); var bounds = ((JArray)set["WatchHours"]).Select(x => (long)x).OrderBy(x => x).ToList();
            var st = State(); var seen = (JObject)st["lastSeen"]; var wt = (JObject)st["watch"]; var an = (JObject)st["anniv"];
            foreach (var c in logins)
            {
                if (Boards.IsBot(c) || Sim.IsSim(c)) continue;
                try
                {
                    long last; lock (L) last = (long?)seen[c] ?? 0;
                    if (last == 0) last = Economy.ProfileLastSeen(c);
                    if (last > 0 && now - last >= gapSec) { long days = (now - last) / 86400; FireAsync("comeback", c, "comeback:" + c + ":" + last, "days", days, "last seen " + days + " days ago"); }
                    lock (L) { seen[c] = now; _dirty = true; }
                    // watch time: fire when the total crosses a boundary; the first sighting only records where they already are (no flood from history)
                    long hours = (long)(Economy.MinutesOf(c) / 60); long top = bounds.Where(b => b <= hours).DefaultIfEmpty(0).Max(); long known; bool had;
                    lock (L) { had = wt[c] != null; known = (long?)wt[c] ?? 0; }
                    if (!had) { lock (L) wt[c] = top; }
                    else if (top > known) { lock (L) wt[c] = top; FireAsync("watchtime", c, "watchtime:" + c + ":" + top, "hours", top); }
                    // anniversary: years since the first sighting (profile), once per year number
                    long first = Economy.ProfileFirstSeen(c);
                    if (first > 0)
                    {
                        long years = (long)((now - first) / (365.25 * 86400)); bool hadA; long doneA; lock (L) { hadA = an[c] != null; doneA = (long?)an[c] ?? 0; }
                        double sinceAnn = (now - first) - years * 365.25 * 86400;
                        if (!hadA) { long init = years >= 1 && sinceAnn <= 7 * 86400 ? years - 1 : years; lock (L) an[c] = init; doneA = init; }
                        if (years >= 1 && years > doneA) { lock (L) an[c] = years; FireAsync("anniversary", c, "anniversary:" + c + ":" + years, "years", years); }
                    }
                }
                catch (Exception ex) { Clog.Warn("alerts", "presence check failed for " + c + ": " + ex.Message); }
            }
            Dirty();
        }
        internal static void TestReset() { lock (L) { _state = new JObject(); foreach (var k in new[] { "lastSeen", "watch", "anniv", "fired" }) _state[k] = new JObject(); } }
        internal static void TestSeed(string section, string login, long v) { lock (L) ((JObject)State()[section])[login] = v; }
        internal static void TestFire(string type, string login, string id, string field, long v) { Fire(type, login, id, field, v); }
    }
}
