using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Points + watch time. Replaces StreamElements' loyalty: a ONE-TIME import (dry run first, apply on confirm, backup, re-runnable because the imported BASELINE is kept apart from
    /// what the Host earns afterwards), then our own earning loop (every minute while live, everyone in the chatroom, bots left out, sub/VIP multipliers).
    /// Store: Data\economy\points.json {baseline:{at,source,users}, earned:{login:{points,minutes}}, months:{yyyy-MM:{login:{points,minutes}}}, adjust:{login:n}}. Aliases (Data\boards\aliases.json) fold at read time.
    /// The StreamElements JWT is read from the vault key se_jwt (or PINGUINO_SE_JWT in tests) and is never logged, echoed or stored.
    /// Chat: !points [user] (also !pengs), !watchtime [user], !toppoints [month], !topwatch [month]; mods: !addpoints @user n, !removepoints @user n, !economy status|import|apply &lt;id&gt;.</summary>
    public static class Economy
    {
        static readonly object L = new object();
        static JObject _doc, _set; static bool _started;
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(System.IO.Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (System.IO.Path.GetDirectoryName(d) ?? d) : d; } }
        static string Dir { get { var d = System.IO.Path.Combine(Root, "economy"); Directory.CreateDirectory(d); return d; } }
        static string PointsP { get { return System.IO.Path.Combine(Dir, "points.json"); } }
        static string SetP { get { return System.IO.Path.Combine(Dir, "settings.json"); } }
        static string DryP { get { return System.IO.Path.Combine(Dir, "import_dryrun.json"); } }
        static string SeBase { get { return (Environment.GetEnvironmentVariable("PINGUINO_SE_BASE") ?? "https://api.streamelements.com/kappa/v2").TrimEnd('/'); } }
        static int SeDelayMs { get { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_SE_DELAY_MS"), out v) ? v : 1000; } }
        static int MinuteSec { get { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_MINUTE_SEC"), out v) && v > 0 ? v : 60; } }
        static string _note = "", _chatterNote = ""; static DateTime _lastTick = DateTime.MinValue; static int _lastPaid;

        public static string CurrencyName { get { lock (L) return (string)Settings()["CurrencyName"] ?? "pengs"; } }

        // ---- settings + store ----
        static JObject Settings()
        {
            if (_set != null) return _set;
            var d = new JObject { { "CurrencyName", "pengs" }, { "PointsPerMinute", 1.0 }, { "SubMultiplier", 2.0 }, { "VipMultiplier", 1.5 }, { "ModMultiplier", 1.0 }, { "OnlyWhileLive", true }, { "Earning", true },
                { "FallbackActiveMinutes", 30 }, { "Exclude", new JArray() } };
            try { if (File.Exists(SetP)) foreach (var p in JObject.Parse(File.ReadAllText(SetP, Encoding.UTF8))) d[p.Key] = p.Value; else File.WriteAllText(SetP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            _set = d; return d;
        }
        static JObject Doc()
        {
            if (_doc != null) return _doc;
            try { if (File.Exists(PointsP)) _doc = JObject.Parse(File.ReadAllText(PointsP, Encoding.UTF8)); } catch (Exception ex) { Clog.Warn("economy", "points.json unreadable: " + ex.Message); }
            if (_doc == null) _doc = new JObject();
            foreach (var k in new[] { "earned", "months", "adjust" }) if (_doc[k] == null) _doc[k] = new JObject();
            if (_doc["baseline"] == null) _doc["baseline"] = new JObject { { "at", "" }, { "source", "" }, { "users", new JObject() } };
            _doc["version"] = 1; return _doc;
        }
        static void Save() { try { string tmp = PointsP + ".tmp"; File.WriteAllText(tmp, _doc.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); if (File.Exists(PointsP)) File.Delete(PointsP); File.Move(tmp, PointsP); } catch (Exception ex) { Clog.Warn("economy", "could not save points.json: " + ex.Message); } }
        static string Norm(string l) { return (l ?? "").Trim().TrimStart('@').ToLowerInvariant(); }
        static string Canon(Dictionary<string, string> al, string l) { l = Norm(l); for (int i = 0; i < 6 && al.ContainsKey(l); i++) l = al[l]; return l; }
        static double D(JToken t) { return t == null || t.Type == JTokenType.Null ? 0 : (double?)t ?? 0; }

        // ---- read side: totals per canonical login ----
        public class Row { public double Points, Minutes; }
        public class Snap { public Dictionary<string, Row> Users = new Dictionary<string, Row>(); public Dictionary<string, Dictionary<string, Row>> Months = new Dictionary<string, Dictionary<string, Row>>(); }

        /// <summary>aliases fold into the main login. Pass the alias map in (taken BEFORE this lock) so this never calls back into Boards while holding the lock.</summary>
        public static Snap Snapshot(Dictionary<string, string> al)
        {
            var s = new Snap();
            lock (L)
            {
                var d = Doc();
                Func<Dictionary<string, Row>, string, double, double, Row> add = (dict, login, p, m) => { string c = Canon(al, login); Row r; if (!dict.TryGetValue(c, out r)) dict[c] = r = new Row(); r.Points += p; r.Minutes += m; return r; };
                foreach (var p in ((JObject)d["baseline"]["users"]).Properties()) add(s.Users, p.Name, D(p.Value["points"]), D(p.Value["minutes"]));
                foreach (var p in ((JObject)d["earned"]).Properties()) add(s.Users, p.Name, D(p.Value["points"]), D(p.Value["minutes"]));
                foreach (var p in ((JObject)d["adjust"]).Properties()) add(s.Users, p.Name, D(p.Value), 0);
                foreach (var mo in ((JObject)d["months"]).Properties())
                {
                    var dict = new Dictionary<string, Row>(); s.Months[mo.Name] = dict;
                    foreach (var p in ((JObject)mo.Value).Properties()) add(dict, p.Name, D(p.Value["points"]), D(p.Value["minutes"]));
                }
            }
            return s;
        }
        static Row Me(string login) { var al = Boards.AliasMap(); var s = Snapshot(al); Row r; return s.Users.TryGetValue(Canon(al, login), out r) ? r : new Row(); }

        // ---- StreamElements import ----
        class SeData { public string Channel = ""; public Dictionary<string, double> Points = new Dictionary<string, double>(), Lifetime = new Dictionary<string, double>(), Minutes = new Dictionary<string, double>(); public int PointsRows, LifetimeRows, MinutesRows; public string Fields = ""; }

        static string Jwt() { string e = Environment.GetEnvironmentVariable("PINGUINO_SE_JWT"); return !string.IsNullOrEmpty(e) ? e : Vault.Get("se_jwt"); }

        static JToken SeGet(HttpClient h, string pathAndQuery)
        {
            var r = h.GetAsync(SeBase + pathAndQuery).Result; int code = (int)r.StatusCode;
            if (code == 401 || code == 403) throw new InvalidOperationException("StreamElements refused the token (HTTP " + code + "): paste a fresh JWT in Integrations > API keys");
            if (code == 429) { Thread.Sleep(5000); r = h.GetAsync(SeBase + pathAndQuery).Result; code = (int)r.StatusCode; }
            if (code != 200) throw new InvalidOperationException("StreamElements answered HTTP " + code + " for " + Regex.Replace(pathAndQuery, @"\?.*$", ""));
            return JToken.Parse(r.Content.ReadAsStringAsync().Result);
        }
        static IEnumerable<JObject> Rows(JToken t) { var arr = (t as JArray) ?? (t?["users"] as JArray) ?? (t?["data"] as JArray) ?? new JArray(); return arr.OfType<JObject>(); }
        static string UserOf(JObject u) { foreach (var k in new[] { "username", "name", "user", "displayName", "login" }) { var v = u[k]; if (v != null && v.Type == JTokenType.String && (string)v != "") return Norm((string)v); } return ""; }
        static double NumOf(JObject u, params string[] keys) { foreach (var k in keys) { var v = u[k]; if (v != null && (v.Type == JTokenType.Integer || v.Type == JTokenType.Float)) return (double)v; if (v != null && v.Type == JTokenType.String) { double d; if (double.TryParse((string)v, NumberStyles.Float, CultureInfo.InvariantCulture, out d)) return d; } } return 0; }

        static SeData FetchSe()
        {
            string jwt = Jwt(); if (jwt == "") throw new InvalidOperationException("No StreamElements token yet: paste it in Integrations > API keys (StreamElements JWT)");
            var d = new SeData();
            using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(60) })
            {
                h.DefaultRequestHeaders.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", jwt);
                h.DefaultRequestHeaders.UserAgent.ParseAdd("PinguinoHost/1.0"); h.DefaultRequestHeaders.Accept.ParseAdd("application/json");
                var me = SeGet(h, "/channels/me"); d.Channel = (string)me["_id"] ?? (string)me["id"] ?? ""; if (d.Channel == "") throw new InvalidOperationException("StreamElements /channels/me gave no channel id");
                Action<string, Action<JObject>, string> page = (path, take, label) =>
                {
                    int offset = 0, limit = 500, total = int.MaxValue; bool first = true;
                    for (int guard = 0; guard < 400 && offset < total; guard++)
                    {
                        if (SeDelayMs > 0 && !first) Thread.Sleep(SeDelayMs); first = false;
                        var j = SeGet(h, "/points/" + d.Channel + path + "?limit=" + limit + "&offset=" + offset);
                        int t = (int?)j["_total"] ?? -1; if (t >= 0) total = t;
                        var rows = Rows(j).ToList(); if (rows.Count == 0) break;
                        if (d.Fields == "" ) d.Fields = string.Join(",", rows[0].Properties().Select(p => p.Name));
                        foreach (var u in rows) take(u); offset += rows.Count; if (t < 0 && rows.Count < limit) break;
                    }
                };
                page("/top", u => { string n = UserOf(u); if (n == "") return; d.PointsRows++; d.Points[n] = NumOf(u, "points", "amount", "currentPoints", "value"); }, "balance");
                page("/alltime", u => { string n = UserOf(u); if (n == "") return; d.LifetimeRows++; d.Lifetime[n] = NumOf(u, "points", "alltime", "amount", "value"); }, "alltime");
                page("/watchtime", u => { string n = UserOf(u); if (n == "") return; d.MinutesRows++; d.Minutes[n] = NumOf(u, "minutes", "watchtime", "watchTime", "time", "value"); }, "watchtime");
            }
            return d;
        }

        /// <summary>read SE and build the dry-run report (nothing is changed). The fetched data is kept in Data\economy\import_dryrun.json so "apply" uses exactly what was reviewed.</summary>
        public static JObject ImportDryRun()
        {
            try
            {
                var se = FetchSe(); var al = Boards.AliasMap();
                var names = new HashSet<string>(se.Points.Keys.Concat(se.Minutes.Keys).Concat(se.Lifetime.Keys));
                string pd = System.IO.Path.Combine(Root, "profiles");
                var known = new HashSet<string>(Directory.Exists(pd) ? Directory.EnumerateFiles(pd, "*.json").Select(f => System.IO.Path.GetFileNameWithoutExtension(f).ToLowerInvariant()) : new string[0]);
                var unmatched = names.Where(n => !known.Contains(Canon(al, n)) && !Boards.IsBot(n)).OrderByDescending(n => (se.Points.ContainsKey(n) ? se.Points[n] : 0) + (se.Minutes.ContainsKey(n) ? se.Minutes[n] : 0)).ToList();
                var folded = names.Where(n => Canon(al, n) != n).Select(n => n + " > " + Canon(al, n)).ToList();
                var bots = names.Where(n => Boards.IsBot(n)).ToList();
                var top = se.Points.Where(k => !Boards.IsBot(k.Key)).OrderByDescending(k => k.Value).Take(10).Select(k => new JObject { { "login", Canon(al, k.Key) }, { "points", k.Value }, { "minutes", se.Minutes.ContainsKey(k.Key) ? se.Minutes[k.Key] : 0 } });
                var topw = se.Minutes.Where(k => !Boards.IsBot(k.Key)).OrderByDescending(k => k.Value).Take(10).Select(k => new JObject { { "login", Canon(al, k.Key) }, { "minutes", k.Value }, { "points", se.Points.ContainsKey(k.Key) ? se.Points[k.Key] : 0 } });
                var payload = new JObject { { "channel", se.Channel }, { "points", JObject.FromObject(se.Points) }, { "lifetime", JObject.FromObject(se.Lifetime) }, { "minutes", JObject.FromObject(se.Minutes) } };
                string id = Convert.ToBase64String(SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(payload.ToString(Newtonsoft.Json.Formatting.None)))).Replace("+", "").Replace("/", "").Replace("=", "").Substring(0, 10);
                var rep = new JObject { { "ok", true }, { "id", id }, { "at", DateTime.UtcNow.ToString("o") }, { "usersWithPoints", se.PointsRows }, { "usersWithWatchtime", se.MinutesRows }, { "usersWithLifetime", se.LifetimeRows },
                    { "totalPoints", Math.Round(se.Points.Sum(k => k.Value)) }, { "totalMinutes", Math.Round(se.Minutes.Sum(k => k.Value)) }, { "fieldsSeen", se.Fields },
                    { "top10Points", new JArray(top) }, { "top10Watchtime", new JArray(topw) }, { "unmatchedCount", unmatched.Count }, { "unmatched", new JArray(unmatched.Take(50).Select(n => new JObject { { "name", n }, { "points", se.Points.ContainsKey(n) ? se.Points[n] : 0 }, { "minutes", se.Minutes.ContainsKey(n) ? se.Minutes[n] : 0 } })) },
                    { "aliasFolded", new JArray(folded.Take(50)) }, { "botsSkipped", new JArray(bots.Take(20)) },
                    { "next", "Review this, then apply with POST /api/economy/import {\"mode\":\"apply\",\"confirm\":\"" + id + "\"} or the chat command !economy apply " + id } };
                lock (L) { File.WriteAllText(DryP, new JObject { { "report", rep }, { "data", payload }, { "savedAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } }.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); }
                _note = "dry run " + id + " ready";
                return rep;
            }
            catch (Exception ex) { _note = "import failed: " + ex.Message; Clog.Warn("economy", "import dry run failed: " + ex.Message); return new JObject { { "ok", false }, { "error", ex.Message } }; }
        }

        /// <summary>write the reviewed dry run as the BASELINE (after a backup of points.json). Needs the report id; re-running replaces the baseline and keeps everything earned since.</summary>
        public static JObject ImportApply(string confirm)
        {
            lock (L)
            {
                JObject saved; try { saved = File.Exists(DryP) ? JObject.Parse(File.ReadAllText(DryP, Encoding.UTF8)) : null; } catch (Exception) { saved = null; }
                if (saved == null) return new JObject { { "ok", false }, { "error", "run the dry run first (POST /api/economy/import {\"mode\":\"dryrun\"})" } };
                string id = (string)saved["report"]["id"];
                if (string.IsNullOrEmpty(confirm) || confirm != id) return new JObject { { "ok", false }, { "error", "the confirm id does not match the last dry run (" + id + ")" } };
                if (DateTimeOffset.UtcNow.ToUnixTimeSeconds() - (long)saved["savedAt"] > 6 * 3600) return new JObject { { "ok", false }, { "error", "that dry run is older than 6 hours: run it again" } };
                var d = Doc(); string backup = "";
                try { if (File.Exists(PointsP)) { Directory.CreateDirectory(System.IO.Path.Combine(Dir, "backups")); backup = System.IO.Path.Combine(Dir, "backups", "points-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + ".json"); File.Copy(PointsP, backup, true); } } catch (Exception ex) { return new JObject { { "ok", false }, { "error", "could not back up points.json: " + ex.Message } }; }
                var data = (JObject)saved["data"]; var users = new JObject();
                var pts = (JObject)data["points"]; var min = (JObject)data["minutes"]; var life = (JObject)data["lifetime"];
                foreach (var n in pts.Properties().Select(p => p.Name).Concat(min.Properties().Select(p => p.Name)).Concat(life.Properties().Select(p => p.Name)).Distinct())
                {
                    if (Boards.IsBot(n)) continue;
                    users[n] = new JObject { { "points", D(pts[n]) }, { "minutes", D(min[n]) }, { "lifetime", D(life[n]) } };
                }
                d["baseline"] = new JObject { { "at", DateTime.UtcNow.ToString("o") }, { "source", "streamelements" }, { "channel", data["channel"] }, { "reportId", id }, { "users", users } };
                Save(); _note = "baseline applied from " + id;
                Clog.Info("economy", "StreamElements baseline applied: " + users.Count + " people (backup " + (backup == "" ? "none: first import" : System.IO.Path.GetFileName(backup)) + ")");
                return new JObject { { "ok", true }, { "applied", users.Count }, { "backup", backup == "" ? "" : System.IO.Path.GetFileName(backup) }, { "report", id } };
            }
        }

        // ---- earning loop ----
        public static void Start()
        {
            if (_started) return; _started = true;
            var th = new Thread(() =>
            {
                Thread.Sleep(MinuteSec < 60 ? 500 : 30000);
                while (true)
                {
                    try { Tick(); } catch (Exception ex) { Clog.Warn("economy", "tick failed: " + ex.Message); }
                    Thread.Sleep(MinuteSec * 1000);
                }
            }) { IsBackground = true };
            th.Start();
        }

        static bool IsLive()
        {
            string o = Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_LIVE"); if (o == "1") return true; if (o == "0") return false;
            return LiveState.Live == true;
        }

        static List<string> Chatters()
        {
            var list = new List<string>(); string cursor = ""; bool ok = true;
            for (int guard = 0; guard < 20; guard++)
            {
                JToken dtok; string err;
                string code = TwitchApi.Call(HttpMethod.Get, "/chat/chatters?broadcaster_id={bid}&moderator_id={bid}&first=1000" + (cursor == "" ? "" : "&after=" + Uri.EscapeDataString(cursor)), null, out dtok, out err);
                if (code != "200") { ok = false; _chatterNote = "the chatters list is not available (HTTP " + code + (err != "" ? ": " + Regex.Replace(err, @"\s+", " ").Substring(0, Math.Min(90, Regex.Replace(err, @"\s+", " ").Length)) : "") + "): using people active in chat in the last " + (int)Settings()["FallbackActiveMinutes"] + " min. Sign the streamer in again to add moderator:read:chatters"; break; }
                foreach (var u in dtok as JArray ?? new JArray()) { string l = Norm((string)u["user_login"]); if (l != "") list.Add(l); }
                cursor = ""; break;   // TwitchApi.Call returns only "data"; one page of up to 1000 is plenty for this channel
            }
            if (ok) { _chatterNote = "Helix chatters list"; return list.Distinct().ToList(); }
            return ChatStats.ActiveLogins((int?)Settings()["FallbackActiveMinutes"] ?? 30);
        }

        static void Tick()
        {
            if (!Lease.MayRun) return;
            JObject set; lock (L) set = Settings();
            if ((bool?)set["Earning"] == false) return;
            if ((bool?)set["OnlyWhileLive"] != false && !IsLive()) { _lastTick = DateTime.MinValue; return; }
            var now = DateTime.UtcNow; double minutes = _lastTick == DateTime.MinValue ? 1 : Math.Min(2, Math.Max(0.5, (now - _lastTick).TotalSeconds / MinuteSec)); _lastTick = now;
            var people = Chatters();
            string streamer = Norm((string)HostApi.StreamerCreds()["Channel"]);
            var ex = new HashSet<string>(((JArray)set["Exclude"]).Select(x => Norm((string)x))); if (streamer != "") ex.Add(streamer);
            var al = Boards.AliasMap();
            double rate = D(set["PointsPerMinute"]), subM = D(set["SubMultiplier"]), vipM = D(set["VipMultiplier"]), modM = D(set["ModMultiplier"]);
            var paid = new Dictionary<string, double>();
            foreach (var l in people)
            {
                if (ex.Contains(l) || Boards.IsBot(l)) continue;
                string c = Canon(al, l); if (c == streamer || ex.Contains(c)) continue;
                double mult = 1;
                var su = SubsImport.UserInfo(c); if (su != null && (int?)su["tier"] > 0 && (bool?)su["lapsed"] != true) mult = Math.Max(mult, subM);
                var role = ProfileRole(c); if (role == "vip") mult = Math.Max(mult, vipM); else if (role == "mod") mult = Math.Max(mult, modM);
                double p; paid.TryGetValue(c, out p); paid[c] = Math.Max(p, rate * mult * minutes);
            }
            string month = DateTime.UtcNow.ToString("yyyy-MM");
            lock (L)
            {
                var d = Doc(); var earned = (JObject)d["earned"]; var mon = (JObject)d["months"]; var mm = (JObject)(mon[month] ?? (mon[month] = new JObject()));
                foreach (var kv in paid)
                {
                    var e = (JObject)(earned[kv.Key] ?? (earned[kv.Key] = new JObject { { "points", 0.0 }, { "minutes", 0.0 } }));
                    e["points"] = D(e["points"]) + kv.Value; e["minutes"] = D(e["minutes"]) + minutes;
                    var m = (JObject)(mm[kv.Key] ?? (mm[kv.Key] = new JObject { { "points", 0.0 }, { "minutes", 0.0 } }));
                    m["points"] = D(m["points"]) + kv.Value; m["minutes"] = D(m["minutes"]) + minutes;
                }
                _lastPaid = paid.Count; if (paid.Count > 0) Save();
            }
        }
        static readonly Dictionary<string, KeyValuePair<DateTime, string>> RoleCache = new Dictionary<string, KeyValuePair<DateTime, string>>();
        static string ProfileRole(string login)
        {
            lock (RoleCache) { KeyValuePair<DateTime, string> c; if (RoleCache.TryGetValue(login, out c) && (DateTime.UtcNow - c.Key).TotalMinutes < 30) return c.Value; }
            string role = "";
            try { string f = System.IO.Path.Combine(Root, "profiles", login + ".json"); if (File.Exists(f)) { var r = SubsImport.ParseJ(File.ReadAllText(f))["roles"] as JObject; if (r != null) role = (bool?)r["mod"] == true ? "mod" : (bool?)r["vip"] == true ? "vip" : ""; } } catch (Exception) { }
            lock (RoleCache) { RoleCache[login] = new KeyValuePair<DateTime, string>(DateTime.UtcNow, role); if (RoleCache.Count > 3000) RoleCache.Clear(); }
            return role;
        }

        // ---- mods change balances ----
        public static string Adjust(string login, double delta, string by)
        {
            login = Canon(Boards.AliasMap(), login); if (login == "") return "Which user?";
            lock (L)
            {
                var adj = (JObject)Doc()["adjust"]; double cur = D(adj[login]); adj[login] = cur + delta; Save();
            }
            var me = Me(login);
            Clog.Info("economy", by + " changed " + login + " by " + delta.ToString("0", CultureInfo.InvariantCulture));
            return login + " now has " + Num(me.Points) + " " + CurrencyName + ".";
        }

        // ---- spending (the hidden shop): every change carries an id, so a retry or a restart never applies it twice ----
        /// <summary>whole pengs the user can spend right now</summary>
        public static bool Applied(string id) { lock (L) return Ledger()[id] != null; }
        public static long Balance(string login) { return (long)Math.Floor(Me(login).Points); }
        /// <summary>takes `amount` pengs for good. Returns null on success (also when this id was already applied: nothing is taken twice), otherwise the reason it was refused.</summary>
        public static string Spend(string id, string login, long amount, string reason)
        {
            if (string.IsNullOrEmpty(id) || amount <= 0) return "bad spend";
            login = Canon(Boards.AliasMap(), login); if (login == "") return "no user";
            long bal = Balance(login);
            lock (L)
            {
                var led = Ledger(); if (led[id] != null) return null;
                if (bal < amount) return "not enough " + CurrencyName;
                var adj = (JObject)Doc()["adjust"]; adj[login] = D(adj[login]) - amount;
                led[id] = new JObject { { "login", login }, { "delta", -amount }, { "reason", reason ?? "" }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } }; Save();
            }
            Clog.Info("economy", login + " spent " + amount + " (" + reason + ")"); return null;
        }
        /// <summary>gives `amount` pengs (a prize). Same id twice is applied once.</summary>
        public static bool Credit(string id, string login, long amount, string reason)
        {
            if (string.IsNullOrEmpty(id) || amount <= 0) return false;
            login = Canon(Boards.AliasMap(), login); if (login == "") return false;
            lock (L)
            {
                var led = Ledger(); if (led[id] != null) return true;
                var adj = (JObject)Doc()["adjust"]; adj[login] = D(adj[login]) + amount;
                led[id] = new JObject { { "login", login }, { "delta", amount }, { "reason", reason ?? "" }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } }; Save();
            }
            return true;
        }
        static JObject Ledger() { var d = Doc(); var l = d["ledger"] as JObject; if (l == null) d["ledger"] = l = new JObject(); return l; }

        // ---- API ----
        public static JObject Api()
        {
            var al = Boards.AliasMap(); var s = Snapshot(al);
            lock (L)
            {
                var d = Doc(); var set = Settings();
                return new JObject { { "ok", true }, { "currency", set["CurrencyName"] }, { "settings", set }, { "people", s.Users.Count }, { "totalPoints", Math.Round(s.Users.Values.Sum(r => r.Points)) }, { "totalMinutes", Math.Round(s.Users.Values.Sum(r => r.Minutes)) },
                    { "baseline", new JObject { { "at", d["baseline"]["at"] }, { "source", d["baseline"]["source"] }, { "people", ((JObject)d["baseline"]["users"]).Count } } },
                    { "earning", new JObject { { "on", (bool?)set["Earning"] != false }, { "live", IsLive() }, { "lastPaidPeople", _lastPaid }, { "source", _chatterNote } } },
                    { "seToken", Jwt() != "" ? "set" : "not set" }, { "note", _note } };
            }
        }
        public static JObject User(string login)
        {
            var al = Boards.AliasMap(); var s = Snapshot(al); string c = Canon(al, login); Row r; s.Users.TryGetValue(c, out r);
            var all = s.Users.OrderByDescending(k => k.Value.Points).Where(k => !Boards.IsBot(k.Key)).Select(k => k.Key).ToList();
            var allw = s.Users.OrderByDescending(k => k.Value.Minutes).Where(k => !Boards.IsBot(k.Key)).Select(k => k.Key).ToList();
            return new JObject { { "ok", true }, { "login", c }, { "points", r == null ? 0 : Math.Floor(r.Points) }, { "minutes", r == null ? 0 : Math.Floor(r.Minutes) }, { "pointsRank", all.IndexOf(c) + 1 }, { "watchRank", allw.IndexOf(c) + 1 }, { "of", all.Count } };
        }
        public static JObject Post(JObject b)
        {
            string mode = ((string)b["mode"] ?? "").ToLowerInvariant();
            if (mode == "dryrun") return ImportDryRun();
            if (mode == "apply") return ImportApply((string)b["confirm"]);
            if (b["adjust"] != null) return new JObject { { "ok", true }, { "message", Adjust((string)b["adjust"], D(b["delta"]), (string)b["by"] ?? "api") } };
            if (b["settings"] is JObject st) { lock (L) { var s = Settings(); foreach (var p in st.Properties()) if (s[p.Name] != null) s[p.Name] = p.Value; File.WriteAllText(SetP, s.ToString(), new UTF8Encoding(false)); } return Api(); }
            return new JObject { { "ok", false }, { "error", "mode must be dryrun or apply" } };
        }

        // ---- chat ----
        static string Num(double n) { return Math.Floor(n).ToString("N0", CultureInfo.InvariantCulture); }
        static string Dur(double min) { long m = (long)Math.Floor(min); if (m < 60) return m + "m"; if (m < 1440) return (m / 60) + "h " + (m % 60) + "m"; return (m / 1440) + "d " + ((m % 1440) / 60) + "h"; }
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();
        static bool Cooling(string key, int sec) { lock (Cool) { DateTime t; if (Cool.TryGetValue(key, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; Cool[key] = DateTime.UtcNow; return false; } }
        static int CoolSec(string env, int d) { int v; return int.TryParse(Environment.GetEnvironmentVariable(env), out v) ? v : d; }
        const string Link = "https://innocentpenguin.com/leaderboards";

        public static bool IsViewerCommand(string c) { return c == "!points" || c == "!pengs" || c == "!watchtime" || c == "!toppoints" || c == "!topwatch"; }
        public static bool IsModCommand(string c) { return c == "!addpoints" || c == "!removepoints" || c == "!economy"; }

        public static void Handle(string user, string cmd, string[] args, bool mod, Action<string> say, Func<string, string> parseMonth, Func<string, string> monthLabel)
        {
            string me = user.ToLowerInvariant();
            try
            {
                if (IsViewerCommand(cmd))
                {
                    if (Cooling("g|" + cmd, CoolSec("PINGUINO_STREAK_COOL_GLOBAL", 8)) || Cooling("u|" + cmd + "|" + me, CoolSec("PINGUINO_STREAK_COOL_USER", 20))) return;
                    string cur = CurrencyName;
                    if (cmd == "!toppoints" || cmd == "!topwatch")
                    {
                        bool pts = cmd == "!toppoints"; string month = ""; foreach (var a in args) { month = parseMonth(a); if (month != "") break; }
                        var al = Boards.AliasMap(); var s = Snapshot(al);
                        var src = month == "" ? s.Users : (s.Months.ContainsKey(month) ? s.Months[month] : new Dictionary<string, Row>());
                        string streamer = Norm((string)HostApi.StreamerCreds()["Channel"]);
                        var top = src.Where(k => !Boards.IsBot(k.Key) && k.Key != streamer).OrderByDescending(k => pts ? k.Value.Points : k.Value.Minutes).Take(5).Where(k => (pts ? k.Value.Points : k.Value.Minutes) >= 1).ToList();
                        string when = month == "" ? "all time" : monthLabel(month);
                        if (top.Count == 0) { say("Nobody on the " + (pts ? cur : "watch time") + " board for " + when + " yet. " + Link + (pts ? "#points" : "#watchtime")); return; }
                        say((pts ? "Top " + cur : "Most watch time") + " (" + when + "): " + string.Join(" | ", top.Select((k, i) => (i + 1) + ". " + Boards.DisplayName(k.Key) + " " + (pts ? Num(k.Value.Points) : Dur(k.Value.Minutes)))) + " - full list: " + Link + (pts ? "#points" : "#watchtime"));
                        return;
                    }
                    string target = args.Length > 0 ? args[0].TrimStart('@').ToLowerInvariant() : me; bool self = target == me;
                    var u = User(target); string disp = Boards.DisplayName((string)u["login"]);
                    double p = (double)u["points"], m = (double)u["minutes"];
                    if (cmd == "!watchtime")
                        say(m < 1 ? (self ? "@" + user + " I have no watch time recorded for you yet." : disp + " has no watch time recorded yet.") : (self ? "@" + user + " you have watched " : disp + " has watched ") + Dur(m) + " (#" + (int)u["watchRank"] + " of " + (int)u["of"] + ").");
                    else
                        say(p < 1 && m < 1 ? (self ? "@" + user + " you have 0 " + cur + " yet. You earn them by hanging out while the stream is live." : disp + " has no " + cur + " yet.") : (self ? "@" + user + " you have " : disp + " has ") + Num(p) + " " + cur + " (#" + (int)u["pointsRank"] + " of " + (int)u["of"] + ").");
                    return;
                }
                if (!mod) return;   // the rest is mods only, silent for everyone else
                if (cmd == "!addpoints" || cmd == "!removepoints")
                {
                    double n; if (args.Length < 2 || !double.TryParse(args[1], NumberStyles.Float, CultureInfo.InvariantCulture, out n) || n <= 0) { say("Usage: " + cmd + " @user <amount>"); return; }
                    say(Adjust(args[0], cmd == "!addpoints" ? n : -n, user)); return;
                }
                if (cmd == "!economy")
                {
                    string sub = args.Length > 0 ? args[0].ToLowerInvariant() : "status";
                    if (sub == "status") { var a = Api(); say("Economy: " + (int)a["people"] + " people, " + Num((double)a["totalPoints"]) + " " + CurrencyName + ", baseline " + ((int)a["baseline"]["people"] > 0 ? "from " + (string)a["baseline"]["source"] : "not imported") + ", earning " + ((bool)a["earning"]["on"] ? ((bool)a["earning"]["live"] ? "on (live)" : "on (waits for live)") : "OFF") + ", StreamElements token " + (string)a["seToken"] + "."); return; }
                    if (sub == "import") { say("Reading StreamElements (takes a minute)..."); var r = ImportDryRun(); if ((bool?)r["ok"] == false) { say("Import dry run failed: " + (string)r["error"]); return; } say("Dry run " + (string)r["id"] + ": " + (int)r["usersWithPoints"] + " with points (" + Num((double)r["totalPoints"]) + " total), " + (int)r["usersWithWatchtime"] + " with watch time, " + (int)r["unmatchedCount"] + " unmatched. Apply with: !economy apply " + (string)r["id"]); return; }
                    if (sub == "apply") { var r = ImportApply(args.Length > 1 ? args[1] : ""); say((bool?)r["ok"] == false ? (string)r["error"] : "Imported " + (int)r["applied"] + " people from StreamElements" + ((string)r["backup"] != "" ? " (backup " + (string)r["backup"] + ")" : "") + "."); return; }
                    say("!economy status | import | apply <id>"); return;
                }
            }
            catch (Exception ex) { Clog.Warn("economy", "command failed: " + ex.Message); }
        }
    }
}
