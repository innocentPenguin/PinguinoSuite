using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>ALL-TIME LEADERBOARD TOTALS for the website (Top Gifters, Top Bitters, Biggest Yappers, Top Watch Streak). One record per person:
    ///   gifts   subs gifted. A gift bomb arrives as ONE "N gifted" line plus N one-per-recipient lines, so the recipients lines that belong to a bomb are not counted again.
    ///   bits    bits cheered.
    ///   messages  chat messages in all saved chat logs (read from the viewer profiles, which are rebuilt from the logs).
    ///   streakBest / streakCurrent / streakAt   the watch streak they shared (Streaks).
    /// Gifts and bits are kept in their own permanent ledger (Data\boards\events.json): chat_events.json forgets old events, this one does not. It is filled from chat_events.json
    /// (merged, the same event within 20 s counts once) and from the live Twitch events. Bots, practice players and anonymous gifters are left out.
    /// GET /api/boards, POST /api/boards/refresh. Pushed to the site (POST {SiteBoardsUrl}, default https://innocentpenguin.com/api/bot/boards, Bearer BOT_API_KEY) when
    /// "ForwardToSite" is on, every 5 minutes if something changed.</summary>
    public static class Boards
    {
        static readonly object L = new object();
        static List<JObject> _ledger; static bool _started; static string _lastPushHash = ""; static DateTime _lastPush = DateTime.MinValue; static string _pushNote = "not pushed yet";
        static JObject _cache; static DateTime _cacheAt = DateTime.MinValue;
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(d) : d; } }
        static string LedgerP { get { return Path.Combine(Root, "boards", "events.json"); } }
        static string TotalsP { get { return Path.Combine(Root, "boards", "totals.json"); } }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () =>
            {
                await Task.Delay(20000);
                while (true)
                {
                    try { Refresh(true); } catch (Exception ex) { _pushNote = "error: " + ex.Message; Clog.Warn("boards", ex.Message); }
                    await Task.Delay(300000);
                }
            });
        }

        static List<JObject> Ledger()
        {
            if (_ledger != null) return _ledger;
            _ledger = new List<JObject>();
            try { if (File.Exists(LedgerP)) foreach (var o in SubsImport.ParseJ("{\"a\":" + File.ReadAllText(LedgerP) + "}")["a"].OfType<JObject>()) _ledger.Add(o); } catch (Exception ex) { Clog.Warn("boards", "ledger unreadable: " + ex.Message); }
            return _ledger;
        }
        static bool Has(List<JObject> l, string type, string user, string to, int amount, long at)
        {
            foreach (var x in l) if ((string)x["type"] == type && (string)x["user"] == user && (string)x["to"] == to && (int)x["amount"] == amount && Math.Abs((long)x["at"] - at) < 20) return true;
            return false;
        }
        static bool Add(List<JObject> l, string type, string user, string to, int amount, long at)
        {
            user = (user ?? "").Trim().ToLowerInvariant().TrimStart('@'); to = (to ?? "").Trim().ToLowerInvariant();
            if (user == "" || user == "anonymous" || amount <= 0 || Has(l, type, user, to, amount, at)) return false;
            l.Add(new JObject { { "at", at }, { "type", type }, { "user", user }, { "amount", amount }, { "to", to } }); return true;
        }

        /// <summary>a live Twitch event (called from Program.DispatchEvent): gift bombs and cheers.</summary>
        public static void OnEvent(Dictionary<string, object> a)
        {
            try
            {
                object et; if (!a.TryGetValue("eventType", out et)) return; string t = Convert.ToString(et); object u; a.TryGetValue("userName", out u);
                long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); bool added = false;
                lock (L)
                {
                    if (t == "TwitchGiftBomb") { object n; a.TryGetValue("total", out n); added = Add(Ledger(), "gift", Convert.ToString(u), "", n == null ? 1 : Convert.ToInt32(n), now); }
                    else if (t == "TwitchCheer") { object n; a.TryGetValue("bits", out n); added = Add(Ledger(), "cheer", Convert.ToString(u), "", n == null ? 0 : Convert.ToInt32(n), now); }
                    if (added) SaveLedger();
                }
            }
            catch (Exception ex) { Clog.Warn("boards", "event: " + ex.Message); }
        }
        static void SaveLedger() { Directory.CreateDirectory(Path.GetDirectoryName(LedgerP)); File.WriteAllText(LedgerP, new JArray(Ledger().OrderBy(x => (long)x["at"])).ToString(Newtonsoft.Json.Formatting.None)); }

        static void ImportChatEvents()
        {
            string f = Path.Combine(HostApi.DataDir, "chat_events.json"); if (!File.Exists(f)) return;
            var l = Ledger(); bool changed = false;
            foreach (var e in JArray.Parse(File.ReadAllText(f)).OfType<JObject>())
            {
                string ty = ((string)e["Type"] ?? "").ToLowerInvariant(); if (ty != "gift" && ty != "cheer") continue;
                changed |= Add(l, ty, (string)e["User"], (string)e["To"], (int?)e["Amount"] ?? 0, (long?)e["At"] ?? 0);
            }
            if (changed) SaveLedger();
        }

        // ---- who does not count ----
        static readonly string[] KnownBots = { "nightbot", "streamelements", "soundalerts", "streamlabs", "moobot", "fossabot", "synchrabot", "pinguinob0t", "chattypinguino", "pinguinohelper", "potatbotat", "sery_bot", "wizebot", "commanderroot", "anotherttvviewer" };
        static HashSet<string> ExtraBots()
        {
            var s = new HashSet<string>();
            try { var j = SubsImport.ParseJ(File.ReadAllText(Path.Combine(HostApi.DataDir, "chat_profiles.json")))["users"] as JObject; if (j != null) foreach (var p in j.Properties()) if ((bool?)p.Value["bot"] == true) s.Add(p.Name); } catch (Exception) { }
            try { var b = SubsImport.ParseJ(File.ReadAllText(Path.Combine(HostApi.DataDir, "bots.json")))["Bots"] as JObject; if (b != null) foreach (var p in b.Properties()) { string acc = ((string)p.Value["Account"] ?? "").ToLowerInvariant(); if (acc != "") s.Add(acc); } } catch (Exception) { }
            return s;
        }
        static readonly Regex BotName = new Regex(@"(bot|b0t)$|^practice\d{2,3}$", RegexOptions.Compiled);

        static string Channel()
        {
            try { return ((string)SubsImport.ParseJ(File.ReadAllText(Path.Combine(HostApi.DataDir, "host_secrets.json")))["Channel"] ?? "").ToLowerInvariant(); } catch (Exception) { return ""; }
        }

        /// <summary>recompute every total. cheap enough to run every few minutes (reads the profile files for the message counts).</summary>
        public static JObject Compute()
        {
            lock (L)
            {
                try { ImportChatEvents(); } catch (Exception ex) { Clog.Warn("boards", "chat_events: " + ex.Message); }
                var users = new Dictionary<string, JObject>();
                Func<string, JObject> U = login => { JObject o; if (!users.TryGetValue(login, out o)) { o = new JObject { { "name", login }, { "gifts", 0 }, { "bits", 0 }, { "messages", 0 }, { "streakBest", 0 }, { "streakCurrent", 0 }, { "streakAt", "" } }; users[login] = o; } return o; };
                var led = Ledger();
                // gifts: a bomb line (no recipient) takes up to N recipient lines of the same gifter shortly after it; the rest are single gifts
                foreach (var grp in led.Where(x => (string)x["type"] == "gift").GroupBy(x => (string)x["user"]))
                {
                    var bombs = grp.Where(x => (string)x["to"] == "").OrderBy(x => (long)x["at"]).ToList(); var ind = grp.Where(x => (string)x["to"] != "").OrderBy(x => (long)x["at"]).ToList();
                    var used = new HashSet<int>(); int total = 0;
                    foreach (var b in bombs)
                    {
                        int n = (int)b["amount"]; total += n; long bt = (long)b["at"];
                        for (int i = 0; i < ind.Count && n > 0; i++) if (!used.Contains(i) && (long)ind[i]["at"] >= bt - 5 && (long)ind[i]["at"] <= bt + 180) { used.Add(i); n--; }
                    }
                    total += ind.Count - used.Count;
                    if (total > 0) U(grp.Key)["gifts"] = total;
                }
                foreach (var grp in led.Where(x => (string)x["type"] == "cheer").GroupBy(x => (string)x["user"])) U(grp.Key)["bits"] = grp.Sum(x => (int)x["amount"]);
                // messages (+ display names) from the viewer profiles
                string pd = Path.Combine(Root, "profiles");
                if (Directory.Exists(pd))
                    foreach (var f in Directory.EnumerateFiles(pd, "*.json"))
                    {
                        try
                        {
                            string login = Path.GetFileNameWithoutExtension(f).ToLowerInvariant(); if (login == "index") continue;
                            var p = SubsImport.ParseJ(File.ReadAllText(f)); int msgs = (int?)p["activity"]?["messages"] ?? 0;
                            if (msgs > 0) { var o = U(login); o["messages"] = msgs; string nm = (string)p["name"]; if (!string.IsNullOrEmpty(nm)) o["name"] = nm; }
                        }
                        catch (Exception) { }
                    }
                // watch streaks
                foreach (JObject b in (JArray)Streaks.Api()["board"]) { var o = U((string)b["login"]); o["streakBest"] = (int)b["best"]; o["streakCurrent"] = (int)b["current"]; o["streakAt"] = (string)b["lastSharedAt"]; if (o["name"].ToString() == (string)b["login"] && !string.IsNullOrEmpty((string)b["name"])) o["name"] = (string)b["name"]; }
                // names for gifters / bitters without a profile come from the ledger user itself (already the login)
                var extra = ExtraBots(); string ch = Channel();
                var keep = users.Where(kv => !BotName.IsMatch(kv.Key) && !KnownBots.Contains(kv.Key) && !extra.Contains(kv.Key) && ((int)kv.Value["gifts"] > 0 || (int)kv.Value["bits"] > 0 || (int)kv.Value["messages"] > 0 || (int)kv.Value["streakBest"] > 0)).ToList();
                var map = new JObject(); foreach (var kv in keep.OrderBy(k => k.Key, StringComparer.Ordinal)) { if (ch != "" && kv.Key == ch) kv.Value["streamer"] = true; map[kv.Key] = kv.Value; }
                Func<string, JArray> top = field => new JArray(keep.Where(kv => kv.Key != ch && (int)kv.Value[field] > 0).OrderByDescending(kv => (int)kv.Value[field]).ThenBy(kv => kv.Key, StringComparer.Ordinal).Take(25).Select(kv => new JObject { { "login", kv.Key }, { "name", kv.Value["name"] }, { "value", kv.Value[field] } }));
                var res = new JObject { { "ok", true }, { "updatedAt", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() }, { "streamerLogin", ch }, { "users", map },
                    { "top", new JObject { { "gifts", top("gifts") }, { "bits", top("bits") }, { "messages", top("messages") }, { "streaks", top("streakBest") } } },
                    { "note", "gifts and bits start in mid-Feb 2026 when the logs start; the streamer is flagged streamer:true and left out of the top lists" } };
                _cache = res; _cacheAt = DateTime.UtcNow;
                try { Directory.CreateDirectory(Path.GetDirectoryName(TotalsP)); File.WriteAllText(TotalsP, res.ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception) { }
                return res;
            }
        }

        public static JObject Api() { lock (L) { if (_cache == null || (DateTime.UtcNow - _cacheAt).TotalSeconds > 120) return Compute(); return _cache; } }

        /// <summary>recompute and (when forwarding to the site is on) push if the numbers changed or 30 minutes have passed.</summary>
        public static JObject Refresh(bool push)
        {
            var r = Compute();
            if (push && Lease.MayRun) PushToSite(r);
            return r;
        }
        static void PushToSite(JObject r)
        {
            var s = Latest.Settings(); if ((bool?)s["ForwardToSite"] != true) { _pushNote = "off (ForwardToSite)"; return; }
            string key = Vault.Get("BOT_API_KEY"); if (key == "") key = Environment.GetEnvironmentVariable("BOT_API_KEY") ?? "";
            if (key == "") { _pushNote = "no key (vault name BOT_API_KEY)"; return; }
            var body = new JObject { { "updatedAt", r["updatedAt"] }, { "users", r["users"] } };
            string hash = Convert.ToBase64String(System.Security.Cryptography.SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(r["users"].ToString(Newtonsoft.Json.Formatting.None))));
            if (hash == _lastPushHash && (DateTime.UtcNow - _lastPush).TotalMinutes < 30) return;
            if (!hash.Equals(_lastPushHash) || (DateTime.UtcNow - _lastPush).TotalMinutes >= 30)
            {
                try
                {
                    using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(20) })
                    {
                        var rq = new HttpRequestMessage(HttpMethod.Post, (string)s["SiteBoardsUrl"] ?? "https://innocentpenguin.com/api/bot/boards") { Content = new StringContent(body.ToString(Newtonsoft.Json.Formatting.None), Encoding.UTF8, "application/json") };
                        rq.Headers.Add("Authorization", "Bearer " + key);
                        var resp = h.SendAsync(rq).Result;
                        if (!resp.IsSuccessStatusCode) { _pushNote = "site answered HTTP " + (int)resp.StatusCode; _lastPush = DateTime.UtcNow.AddMinutes(-25); Clog.Warn("boards", "site did not accept the totals (HTTP " + (int)resp.StatusCode + ")"); return; }
                    }
                    _lastPushHash = hash; _lastPush = DateTime.UtcNow; _pushNote = "ok (" + ((JObject)r["users"]).Count + " people)";
                }
                catch (Exception ex) { _pushNote = "error: " + ex.Message; _lastPush = DateTime.UtcNow.AddMinutes(-25); }
            }
        }
        public static string PushNote() { return _pushNote; }
    }
}
