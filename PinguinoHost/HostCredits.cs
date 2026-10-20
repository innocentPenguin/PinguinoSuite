using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Who chatted this stream (name, mod/vip/sub flags). Reset when the stream goes online. Feeds the credits roll. File: session_chatters.json.</summary>
    public static class Roster
    {
        class E { public string Name; public int Role; public bool Sub; public int Msgs; public long First; }
        static readonly Dictionary<string, E> D = new Dictionary<string, E>(); static readonly object L = new object(); static bool _loaded; static DateTime _saved = DateTime.MinValue;
        static string P { get { return Path.Combine(HostApi.DataDir, "session_chatters.json"); } }
        static void Load()
        {
            if (_loaded) return; _loaded = true;
            try { if (File.Exists(P)) foreach (var o in JArray.Parse(File.ReadAllText(P)).OfType<JObject>()) D[(string)o["login"]] = new E { Name = (string)o["name"], Role = (int)o["role"], Sub = (bool)o["sub"], Msgs = (int)o["msgs"], First = (long)o["first"] }; } catch (Exception) { }
        }
        static void Save() { try { File.WriteAllText(P, new JArray(D.Select(k => new JObject { { "login", k.Key }, { "name", k.Value.Name }, { "role", k.Value.Role }, { "sub", k.Value.Sub }, { "msgs", k.Value.Msgs }, { "first", k.Value.First } })).ToString()); _saved = DateTime.UtcNow; } catch (Exception) { } }
        public static void Reset() { lock (L) { Load(); D.Clear(); Save(); } }
        public static void Note(string display, int role, bool sub)
        {
            string login = (display ?? "").ToLowerInvariant(); if (login == "") return;
            lock (L)
            {
                Load(); E e; bool isNew = !D.TryGetValue(login, out e);
                if (isNew) D[login] = e = new E { Name = display, First = DateTimeOffset.UtcNow.ToUnixTimeSeconds() };
                e.Msgs++; e.Role = Math.Max(e.Role, role); e.Sub = e.Sub || sub;
                if (isNew || (DateTime.UtcNow - _saved).TotalSeconds > 120) Save();
            }
        }
        public static int RoleOf(string login) { login = (login ?? "").ToLowerInvariant(); lock (L) { Load(); E e; return D.TryGetValue(login, out e) ? e.Role : 0; } }
        public static List<string> Names(Func<int, bool, bool> keep) { lock (L) { Load(); return D.Values.Where(e => keep(e.Role, e.Sub)).OrderBy(e => e.First).Select(e => e.Name).ToList(); } }
        /// <summary>true the first time this login chats today (local date), for the first_today trigger.</summary>
        static readonly HashSet<string> Today = new HashSet<string>(); static string _todayKey = "";
        public static bool FirstToday(string login)
        {
            lock (L) { string k = DateTime.Now.ToString("yyyy-MM-dd"); if (k != _todayKey) { Today.Clear(); _todayKey = k; } return Today.Add((login ?? "").ToLowerInvariant()); }
        }
    }

    /// <summary>The Streamer.bot "credits": GET /api/credits (same sections Streamer.bot sent: events, users, hypeTrain, top) and the roll overlay /overlay/credits.
    /// Bits and channel point totals are kept in ledger.json from now on (Streamer.bot's own history cannot be imported). Look: credits_settings.json.</summary>
    public static class Credits
    {
        static readonly object L = new object();
        static string LedgerPath { get { return Path.Combine(HostApi.DataDir, "ledger.json"); } }
        public static void Add(string kind, string user, long amount)
        {
            if (string.IsNullOrEmpty(user) || amount <= 0) return;
            lock (L)
            {
                JArray a; try { a = File.Exists(LedgerPath) ? JArray.Parse(File.ReadAllText(LedgerPath)) : new JArray(); } catch (Exception) { a = new JArray(); }
                a.Add(new JObject { { "k", kind }, { "u", user }, { "a", amount }, { "ts", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } }); while (a.Count > 20000) a.RemoveAt(0);
                try { File.WriteAllText(LedgerPath, a.ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception) { }
            }
        }
        static JArray Top(string kind, long sinceTs, int n)
        {
            JArray a; lock (L) { try { a = File.Exists(LedgerPath) ? JArray.Parse(File.ReadAllText(LedgerPath)) : new JArray(); } catch (Exception) { a = new JArray(); } }
            var sums = a.OfType<JObject>().Where(o => (string)o["k"] == kind && (long)o["ts"] >= sinceTs).GroupBy(o => (string)o["u"], StringComparer.OrdinalIgnoreCase).Select(g => new { g.Key, T = g.Sum(o => (long)o["a"]) }).OrderByDescending(x => x.T).Take(n);
            return new JArray(sums.Select(x => x.Key));
        }
        public static JObject Settings()
        {
            var d = new JObject { { "Exclude", new JArray("innocentpenguin_", "nightbot", "streamelements", "soundalerts", "rocketrankbot", "pinguinob0t", "pinguinohelper", "chattypinguino") }, { "TopCount", 10 }, { "Sections", "follows,cheers,subs,reSubs,giftSubs,raided,rewardRedemptions,moderators,vips,subscribers,users,allBits,monthBits,weekBits,channelRewards" },
                { "Titles", new JObject { { "follows", "New Followers!" }, { "cheers", "Cheers!" }, { "subs", "New Subscribers!" }, { "reSubs", "Those who Resubscribed!" }, { "giftSubs", "Crazy peeps who gifted subs!" }, { "raided", "Thank you Raiders!" }, { "rewardRedemptions", "Wasted channel points" },
                    { "moderators", "Moderators" }, { "vips", "VIPs!" }, { "subscribers", "Subscribers" }, { "users", "Viewers" }, { "allBits", "All time top Bits!" }, { "monthBits", "Monthly Top Bits" }, { "weekBits", "Weekly Top bits!" }, { "channelRewards", "Biggest point spenders" } } },
                { "Look", new JObject { { "TitleColor", "ffffff" }, { "NameColor", "ff9900" }, { "TitleSize", 85 }, { "NameSize", 72 }, { "Font", "Sour Gummy" }, { "Stroke", 9 }, { "Uppercase", true }, { "SpeedFactor", 120 } } } };
            try { var f = Path.Combine(HostApi.DataDir, "credits_settings.json"); if (File.Exists(f)) { foreach (var p in JObject.Parse(File.ReadAllText(f))) { if ((p.Key == "Titles" || p.Key == "Look") && p.Value is JObject o) foreach (var q in o) d[p.Key][q.Key] = q.Value; else d[p.Key] = p.Value; } } else File.WriteAllText(f, d.ToString()); } catch (Exception) { }
            return d;
        }
        static JArray Names(string type, long since)
        {
            var items = ((JArray)Latest.Activity(0, 100000, null)["items"]).OfType<JObject>().Where(i => (string)i["type"] == type && (long)i["ts"] >= since).Select(i => (string)i["user"]).Where(u => !string.IsNullOrEmpty(u)).Distinct(StringComparer.OrdinalIgnoreCase);
            return new JArray(items);
        }
        /// <summary>the same shape Streamer.bot's GetCredits answered: { id:"credits", events:{...}, users:{...}, hypeTrain:{...}, top:{...} }</summary>
        public static JObject Build()
        {
            long s = Session.Start, now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); int n = (int?)Settings()["TopCount"] ?? 10;
            var events = new JObject { { "follows", Names("follow", s) }, { "cheers", Names("cheer", s) }, { "subs", Names("sub", s) }, { "reSubs", Names("resub", s) }, { "giftSubs", Names("gift", s) }, { "giftBombs", Names("gift", s) },
                { "raided", Names("raid", s) }, { "rewardRedemptions", Names("redeem", s) }, { "goalContributions", new JArray() }, { "pyramids", new JArray() } };
            var users = new JObject { { "editors", new JArray() }, { "moderators", new JArray(Roster.Names((r, sb) => r == 3)) }, { "subscribers", new JArray(Roster.Names((r, sb) => sb)) }, { "vips", new JArray(Roster.Names((r, sb) => r == 2)) }, { "users", new JArray(Roster.Names((r, sb) => true)) } };
            var top = new JObject { { "allBits", Top("bits", 0, n) }, { "monthBits", Top("bits", now - 30 * 86400, n) }, { "weekBits", Top("bits", now - 7 * 86400, n) }, { "channelRewards", Top("points", 0, n) } };
            return new JObject { { "id", "credits" }, { "status", "ok" }, { "events", events }, { "users", users }, { "hypeTrain", new JObject { { "conductors", new JArray() }, { "contributors", new JArray() } } }, { "top", top }, { "settings", Settings() } };
        }
        /// <summary>?test=1: fills empty sections with sample names so the look can be checked without a stream.</summary>
        public static void Sample(JObject cr)
        {
            var names = new[] { "ViewerOne", "ViewerTwo", "ViewerThree", "ViewerFour" };
            foreach (var sec in new[] { "events", "users", "top" }) foreach (var p in ((JObject)cr[sec]).Properties().ToList()) if (p.Value is JArray a && a.Count == 0 && p.Name != "editors" && p.Name != "goalContributions" && p.Name != "pyramids") ((JObject)cr[sec])[p.Name] = new JArray(names);
        }
        public static string PagePath()
        {
            foreach (var d in new[] { Path.Combine(AppContext.BaseDirectory, "web"), Path.Combine(Program.SuiteDir ?? "", "PinguinoHost", "web") })
            { var f = Path.Combine(d, "credits.html"); if (File.Exists(f)) return f; }
            return null;
        }
    }

    /// <summary>Streamer.bot WebSocket compatibility on 127.0.0.1:8080 (only after the cutover, when Streamer.bot has released the port): lets the existing OBS credits page and Stream Deck
    /// buttons keep working unchanged. Requests: GetCredits (the credits JSON), GetActions, DoAction {action:{id|name}, args}, GetInfo, Subscribe (accepted, no events). No password is checked
    /// (it listens on this PC only). Override the port for tests with PINGUINO_COMPAT_WS_PORT.</summary>
    public static class CompatWs
    {
        static bool _started; public static string State = "off";
        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () =>
            {
                int port = int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_COMPAT_WS_PORT"), out int p) ? p : 8080;
                while (true)
                {
                    if (!Cutover.On) { State = "waiting for the cutover"; await Task.Delay(5000); continue; }
                    HttpListener l = null;
                    try { l = new HttpListener(); l.Prefixes.Add("http://127.0.0.1:" + port + "/"); l.Start(); State = "listening on 127.0.0.1:" + port; Clog.Info("compat-ws", "Streamer.bot WebSocket compatibility listening on 127.0.0.1:" + port); }
                    catch (Exception ex) { State = "port " + port + " busy (is Streamer.bot still running?)"; try { l?.Close(); } catch (Exception) { } await Task.Delay(15000); continue; }
                    try { while (Cutover.On) { var ctx = await l.GetContextAsync(); var t = Serve(ctx); } }
                    catch (Exception) { }
                    try { l.Close(); } catch (Exception) { }
                    State = "off";
                }
            });
        }
        static async Task Serve(HttpListenerContext c)
        {
            if (!c.Request.IsWebSocketRequest) { c.Response.StatusCode = 426; c.Response.Close(); return; }
            WebSocket ws; try { ws = (await c.AcceptWebSocketAsync(null)).WebSocket; } catch (Exception) { return; }
            var buf = new byte[65536];
            try
            {
                while (ws.State == WebSocketState.Open)
                {
                    var sb = new StringBuilder(); WebSocketReceiveResult r;
                    do { r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), CancellationToken.None); if (r.MessageType == WebSocketMessageType.Close) { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None); return; } sb.Append(Encoding.UTF8.GetString(buf, 0, r.Count)); } while (!r.EndOfMessage);
                    JObject req; try { req = JObject.Parse(sb.ToString()); } catch (Exception) { continue; }
                    var resp = Handle(req); var bytes = Encoding.UTF8.GetBytes(resp.ToString(Newtonsoft.Json.Formatting.None));
                    await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None);
                }
            }
            catch (Exception) { }
        }
        static JObject Handle(JObject req)
        {
            string id = (string)req["id"] ?? "", rq = (string)req["request"] ?? "";
            try
            {
                switch (rq)
                {
                    case "GetCredits": { var j = Credits.Build(); j["id"] = id == "" ? "credits" : id; return j; }
                    case "GetInfo": return new JObject { { "id", id }, { "status", "ok" }, { "info", new JObject { { "instanceId", "pinguinohost" }, { "name", "PinguinoHost (Streamer.bot compatible)" }, { "version", "1" } } } };
                    case "GetActions":
                    {
                        var doc = Auto.Doc(); var acts = new JArray(((JArray)doc["actions"]).OfType<JObject>().Select(a => new JObject { { "id", a["id"] }, { "name", a["name"] }, { "enabled", (bool?)a["enabled"] != false }, { "group", a["group"] }, { "subaction_count", (a["steps"] as JArray)?.Count ?? 0 } }));
                        return new JObject { { "id", id }, { "status", "ok" }, { "count", acts.Count }, { "actions", acts } };
                    }
                    case "DoAction":
                    {
                        var a = req["action"] as JObject; string key = (string)a?["id"] ?? (string)a?["name"] ?? ""; var args = req["args"] as JObject;
                        if (!Auto.Has(key)) return new JObject { { "id", id }, { "status", "error" }, { "error", "no such action" } };
                        Task.Run(() => { try { Auto.Test(key, args, false); } catch (Exception) { } }); return new JObject { { "id", id }, { "status", "ok" } };   // like Streamer.bot: answers at once, the action runs on
                    }
                    case "Subscribe": return new JObject { { "id", id }, { "status", "ok" }, { "events", new JObject() } };
                    default: return new JObject { { "id", id }, { "status", "error" }, { "error", "request not supported by PinguinoHost: " + rq } };
                }
            }
            catch (Exception ex) { return new JObject { { "id", id }, { "status", "error" }, { "error", ex.Message } }; }
        }
    }
}
