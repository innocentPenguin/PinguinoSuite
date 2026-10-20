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
    /// GET /api/boards, POST /api/boards/refresh. Gifts and bits are pushed to the site (POST {SiteSupportersUrl}, default https://innocentpenguin.com/api/bot/supporters {gifts:{login:n},bits:{login:n}}, Bearer BOT_API_KEY) every 5 minutes if something changed (unless latest_settings.json says ForwardBoards:false).</summary>
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
        static readonly string[] KnownBots = { "nightbot", "streamelements", "soundalerts", "streamlabs", "moobot", "fossabot", "synchrabot", "pinguinob0t", "chattypinguino", "pinguinohelper", "potatbotat", "rocketrankbot", "sery_bot", "wizebot", "commanderroot", "anotherttvviewer" };
        static HashSet<string> ExtraBots()
        {
            var s = new HashSet<string>();
            try { var j = SubsImport.ParseJ(File.ReadAllText(Path.Combine(HostApi.DataDir, "chat_profiles.json")))["users"] as JObject; if (j != null) foreach (var p in j.Properties()) if ((bool?)p.Value["bot"] == true) s.Add(p.Name); } catch (Exception) { }
            try { var b = SubsImport.ParseJ(File.ReadAllText(Path.Combine(HostApi.DataDir, "bots.json")))["Bots"] as JObject; if (b != null) foreach (var p in b.Properties()) { string acc = ((string)p.Value["Account"] ?? "").ToLowerInvariant(); if (acc != "") s.Add(acc); } } catch (Exception) { }
            try { var b = SubsImport.ParseJ(File.ReadAllText(Path.Combine(Root, "boards", "banned_accounts.json")))["accounts"] as JObject; if (b != null) foreach (var p in b.Properties()) s.Add(p.Name.ToLowerInvariant()); } catch (Exception) { }   // banned accounts are never credited
            return s;
        }
        static readonly Regex BotName = new Regex(@"(bot|b0t)$|^practice\d{2,3}$", RegexOptions.Compiled);

        // Twitch's bits (cheer) badge tiers: the highest one at or below the lifetime bits cheered
        static readonly int[] BitTiers = { 1, 100, 1000, 5000, 10000, 25000, 50000, 75000, 100000, 200000, 300000, 400000, 500000, 600000, 700000, 800000, 900000, 1000000, 1250000, 1500000, 1750000, 2000000, 2500000, 3000000, 3500000, 4000000, 4500000, 5000000 };
        public static int BitsBadge(int bits) { int b = 0; foreach (int t in BitTiers) if (bits >= t) b = t; return b; }

        /// <summary>roles.bitsBadge / roles.bitsTotal in the viewer profiles (separate from sub and mod: a mod can carry both). Only touches profiles that exist.</summary>
        static void ApplyBitsToProfiles(Dictionary<string, JObject> users)
        {
            string pd = Path.Combine(Root, "profiles"); if (!Directory.Exists(pd)) return;
            foreach (var kv in users)
            {
                int bits = (int)kv.Value["bits"]; string f = Path.Combine(pd, kv.Key + ".json"); if (!File.Exists(f)) continue;
                try
                {
                    var prof = SubsImport.ParseJ(File.ReadAllText(f)); var roles = prof["roles"] as JObject ?? new JObject(); int badge = BitsBadge(bits);
                    if ((int?)roles["bitsBadge"] == badge && (int?)roles["bitsTotal"] == bits) continue;
                    if (bits == 0 && roles["bitsBadge"] == null) continue;
                    roles["bitsBadge"] = badge; roles["bitsTotal"] = bits; prof["roles"] = roles; File.WriteAllText(f, prof.ToString());
                }
                catch (Exception) { }
            }
        }

        // ---- aliases: one person, several accounts. Data/boards/aliases.json {"aliases":{"sg_yen":"cyfirl"}} folds the first login into the second everywhere on the boards ----
        static string AliasP { get { return Path.Combine(Root, "boards", "aliases.json"); } }
        static Dictionary<string, string> Aliases()
        {
            var m = new Dictionary<string, string>();
            try
            {
                if (!File.Exists(AliasP))
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(AliasP));
                    File.WriteAllText(AliasP, new JObject { { "note", "alias login -> main login. Their gifts, bits, messages and watch streak are combined under the main login (its Twitch display name is kept). Edit and the next refresh applies it." }, { "aliases", new JObject { { "sg_yen", "cyfirl" } } } }.ToString());
                }
                var a = SubsImport.ParseJ(File.ReadAllText(AliasP))["aliases"] as JObject;
                if (a != null) foreach (var p in a.Properties()) { string from = p.Name.Trim().ToLowerInvariant().TrimStart('@'), to = ((string)p.Value ?? "").Trim().ToLowerInvariant().TrimStart('@'); if (from != "" && to != "" && from != to) m[from] = to; }
            }
            catch (Exception ex) { Clog.Warn("boards", "aliases.json: " + ex.Message); }
            return m;
        }
        static string Canon(Dictionary<string, string> al, string login) { string x; for (int i = 0; i < 5 && al.TryGetValue(login, out x); i++) login = x; return login; }

        /// <summary>alias logins, sent as "drop" so the site can delete their stale rows (the site ignores it until it supports it).</summary>
        static JArray DropList() { lock (L) return new JArray(Aliases().Keys.OrderBy(k => k, StringComparer.Ordinal)); }
        /// <summary>every login the site must treat as a bot: the known list, bots.json accounts and chat_profiles bot flags.</summary>
        public static HashSet<string> AllBots() { var s = new HashSet<string>(KnownBots); try { foreach (var x in ExtraBots()) s.Add(x); } catch (Exception) { } return s; }
        public static bool IsBot(string login) { login = (login ?? "").ToLowerInvariant(); return BotName.IsMatch(login) || KnownBots.Contains(login); }
        public static string CanonLogin(string login) { lock (L) return Canon(Aliases(), (login ?? "").Trim().ToLowerInvariant()); }
        public static Dictionary<string, string> AliasMap() { lock (L) return Aliases(); }
        static JObject AliasDoc()
        {
            Aliases();   // creates the file with its note when it is missing
            try { return SubsImport.ParseJ(File.ReadAllText(AliasP)); } catch (Exception) { return new JObject { { "aliases", new JObject() } }; }
        }
        public static string AliasAdd(string old, string main)
        {
            old = (old ?? "").Trim().ToLowerInvariant().TrimStart('@'); main = (main ?? "").Trim().ToLowerInvariant().TrimStart('@');
            if (!Regex.IsMatch(old, "^[a-z0-9_]{2,25}$") || !Regex.IsMatch(main, "^[a-z0-9_]{2,25}$")) return "Logins are letters, numbers and underscores (2-25 characters).";
            lock (L)
            {
                var al = Aliases(); string target = Canon(al, main);
                if (target == old) return old + " is already the main account of " + main + ", so that would loop.";
                var doc = AliasDoc(); var a = (JObject)(doc["aliases"] ?? (doc["aliases"] = new JObject()));
                foreach (var p in a.Properties().Where(p => ((string)p.Value ?? "").ToLowerInvariant() == old).ToList()) p.Value = target;   // whoever pointed at the old login now points at the main one
                a[old] = target; File.WriteAllText(AliasP, doc.ToString()); _cacheAt = DateTime.MinValue;
                return "Alias saved: " + old + " > " + target + ". Their gifts, bits, messages and streak count under " + target + " from the next refresh (!boards refresh).";
            }
        }
        public static string AliasRemove(string old)
        {
            old = (old ?? "").Trim().ToLowerInvariant().TrimStart('@');
            lock (L)
            {
                var doc = AliasDoc(); var a = doc["aliases"] as JObject; if (a == null || a[old] == null) return old + " is not an alias.";
                a.Remove(old); File.WriteAllText(AliasP, doc.ToString()); _cacheAt = DateTime.MinValue; return "Alias removed: " + old + ". It counts as its own person again from the next refresh.";
            }
        }
        /// <summary>forget every learned display name so the next refresh asks Twitch again.</summary>
        public static void NamesReset() { lock (L) { _names = new JObject(); try { if (File.Exists(NamesP)) File.Delete(NamesP); } catch (Exception) { } } }
        public static string DisplayName(string login)
        {
            lock (L) { var e = Names()[login] as JObject; string dn = e == null ? "" : (string)e["name"] ?? ""; if (dn != "") return dn; var u = (_cache?["users"] as JObject)?[login] as JObject; return u != null ? (string)u["name"] : login; }
        }

        // ---- display names: the real Twitch capitalisation. Data/boards/names.json {login:{name,at}} is filled from Twitch (Helix users) for everyone whose stored name is just the lowercase login ----
        static string NamesP { get { return Path.Combine(Root, "boards", "names.json"); } }
        static JObject _names;
        static JObject Names()
        {
            if (_names != null) return _names;
            try { _names = File.Exists(NamesP) ? SubsImport.ParseJ(File.ReadAllText(NamesP)) : new JObject(); } catch (Exception) { _names = new JObject(); }
            return _names;
        }
        /// <summary>ask Twitch for the display names of people whose name is still the lowercase login. true when new names were learned.</summary>
        static bool FetchNames(JObject r)
        {
            var cr = HostApi.StreamerCreds(); string tok = (string)cr["UserToken"] ?? "", cid = (string)cr["ClientId"] ?? ""; if (tok == "" || cid == "") return false;
            JObject names; lock (L) names = Names();
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var todo = ((JObject)r["users"]).Properties().Where(p => (string)p.Value["name"] == p.Name || (string)p.Value["name"] == null).Select(p => p.Name)
                .Where(l => { var e = names[l] as JObject; return e == null || now - ((long?)e["at"] ?? 0) > 60L * 86400; }).Where(l => Regex.IsMatch(l, "^[a-z0-9_]{2,25}$")).ToList();
            if (todo.Count == 0) return false;
            bool learned = false;
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(15) })
                    for (int i = 0; i < todo.Count && i < 1500; i += 100)
                    {
                        var batch = todo.Skip(i).Take(100).ToList();
                        var rq = new HttpRequestMessage(HttpMethod.Get, HostApi.Helix + "/users?" + string.Join("&", batch.Select(l => "login=" + l)));
                        rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                        var resp = h.SendAsync(rq).Result; if (!resp.IsSuccessStatusCode) { Clog.Warn("boards", "display names: Twitch answered HTTP " + (int)resp.StatusCode); break; }
                        var found = new HashSet<string>();
                        foreach (var u in (SubsImport.ParseJ(resp.Content.ReadAsStringAsync().Result)["data"] as JArray) ?? new JArray())
                        { string lg = ((string)u["login"] ?? "").ToLowerInvariant(), dn = (string)u["display_name"] ?? ""; if (lg == "" || dn == "") continue; found.Add(lg); lock (L) names[lg] = new JObject { { "name", dn }, { "at", now } }; if (dn != lg) learned = true; }
                        foreach (var l in batch.Where(l => !found.Contains(l))) lock (L) names[l] = new JObject { { "name", "" }, { "at", now } };   // renamed/banned account: do not ask again for 60 days
                    }
                lock (L) { Directory.CreateDirectory(Path.GetDirectoryName(NamesP)); File.WriteAllText(NamesP, Names().ToString(Newtonsoft.Json.Formatting.None)); }
            }
            catch (Exception ex) { Clog.Warn("boards", "display names: " + ex.Message); }
            return learned;
        }

        /// <summary>profile.displayName (the real Twitch capitalisation, when we know it) and profile.aliasOf (on the alias account's profile). Only touches profiles that exist.</summary>
        static void ApplyProfileMeta(Dictionary<string, JObject> users, Dictionary<string, string> al)
        {
            string pd = Path.Combine(Root, "profiles"); if (!Directory.Exists(pd)) return; var nm = Names();
            Action<string, string, string> write = (login, dn, aliasOf) =>
            {
                string f = Path.Combine(pd, login + ".json"); if (!File.Exists(f)) return;
                try
                {
                    var prof = SubsImport.ParseJ(File.ReadAllText(f)); bool diff = false;
                    if (dn != "" && (string)prof["displayName"] != dn) { prof["displayName"] = dn; diff = true; }
                    if (aliasOf != "" && (string)prof["aliasOf"] != aliasOf) { prof["aliasOf"] = aliasOf; diff = true; }
                    if (diff) File.WriteAllText(f, prof.ToString());
                }
                catch (Exception) { }
            };
            foreach (var kv in users) { var e = nm[kv.Key] as JObject; string dn = e == null ? "" : (string)e["name"] ?? ""; if (dn == "" && (string)kv.Value["name"] != kv.Key) dn = (string)kv.Value["name"]; if (dn != "") write(kv.Key, dn, ""); }
            foreach (var a in al) { var e = nm[a.Key] as JObject; write(a.Key, e == null ? "" : (string)e["name"] ?? "", Canon(al, a.Key)); }
        }

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
                var al = Aliases();
                var mGifts = new Dictionary<string, Dictionary<string, int>>(); var mBits = new Dictionary<string, Dictionary<string, int>>(); var mMsgs = new Dictionary<string, Dictionary<string, int>>(); var mStreak = new Dictionary<string, Dictionary<string, int>>();
                Action<Dictionary<string, Dictionary<string, int>>, string, string, int, bool> addM = (dict, month, login, v, max) =>
                {
                    if (month.Length != 7 || v <= 0) return; login = Canon(al, login);
                    Dictionary<string, int> d; if (!dict.TryGetValue(month, out d)) dict[month] = d = new Dictionary<string, int>();
                    int cur; d.TryGetValue(login, out cur); d[login] = max ? Math.Max(cur, v) : cur + v;
                };
                Func<long, string> monthOf = at => DateTimeOffset.FromUnixTimeSeconds(at).UtcDateTime.ToString("yyyy-MM");
                Func<string, JObject> U = login => { JObject o; if (!users.TryGetValue(login, out o)) { o = new JObject { { "name", login }, { "gifts", 0 }, { "bits", 0 }, { "messages", 0 }, { "streakBest", 0 }, { "streakCurrent", 0 }, { "streakAt", "" }, { "bitsBadge", 0 }, { "points", 0 }, { "watchMinutes", 0 } }; users[login] = o; } return o; };
                var led = Ledger();
                // gifts: a bomb line (no recipient) takes up to N recipient lines of the same gifter shortly after it; the rest are single gifts
                foreach (var grp in led.Where(x => (string)x["type"] == "gift").GroupBy(x => (string)x["user"]))
                {
                    var bombs = grp.Where(x => (string)x["to"] == "").OrderBy(x => (long)x["at"]).ToList(); var ind = grp.Where(x => (string)x["to"] != "").OrderBy(x => (long)x["at"]).ToList();
                    var used = new HashSet<int>(); int total = 0;
                    foreach (var b in bombs)
                    {
                        int n = (int)b["amount"]; total += n; long bt = (long)b["at"]; addM(mGifts, monthOf(bt), grp.Key, n, false);
                        for (int i = 0; i < ind.Count && n > 0; i++) if (!used.Contains(i) && (long)ind[i]["at"] >= bt - 5 && (long)ind[i]["at"] <= bt + 180) { used.Add(i); n--; }
                    }
                    total += ind.Count - used.Count;
                    for (int i = 0; i < ind.Count; i++) if (!used.Contains(i)) addM(mGifts, monthOf((long)ind[i]["at"]), grp.Key, 1, false);
                    if (total > 0) U(grp.Key)["gifts"] = total;
                }
                foreach (var grp in led.Where(x => (string)x["type"] == "cheer").GroupBy(x => (string)x["user"])) { U(grp.Key)["bits"] = grp.Sum(x => (int)x["amount"]); foreach (var x in grp) addM(mBits, monthOf((long)x["at"]), grp.Key, (int)x["amount"], false); }
                // messages (+ display names) from the viewer profiles
                string pd = Path.Combine(Root, "profiles");
                if (Directory.Exists(pd))
                    foreach (var f in Directory.EnumerateFiles(pd, "*.json"))
                    {
                        try
                        {
                            string login = Path.GetFileNameWithoutExtension(f).ToLowerInvariant(); if (login == "index") continue;
                            var p = SubsImport.ParseJ(File.ReadAllText(f)); int msgs = (int?)p["activity"]?["messages"] ?? 0;
                            if (p["activity"]?["perMonth"] is JObject pm) foreach (var mm in pm.Properties()) addM(mMsgs, mm.Name, login, (int?)mm.Value ?? 0, false);
                            if (msgs > 0) { var o = U(login); o["messages"] = msgs; string pn = (string)p["name"]; if (!string.IsNullOrEmpty(pn)) o["name"] = pn; }
                        }
                        catch (Exception) { }
                    }
                // people the public log sites will not serve (opted out): their lines come from our own recording (Data\chat_logs\live), day files untouched
                try
                {
                    LiveLog.BackfillFromChatty();
                    // profiles are built at one moment and can lag behind newer day files: never show less than the day files hold
                    foreach (var sc in LiveLog.SiteCounts())
                    {
                        JObject uo; int have = users.TryGetValue(sc.Key, out uo) ? (int)uo["messages"] : 0; if (sc.Value.Key <= have) continue;
                        var o = U(sc.Key); o["messages"] = sc.Value.Key;
                        foreach (var m in sc.Value.Value) { Dictionary<string, int> mm; int cur = 0; if (mMsgs.TryGetValue(m.Key, out mm)) mm.TryGetValue(sc.Key, out cur); if (m.Value > cur) addM(mMsgs, m.Key, sc.Key, m.Value - cur, false); }
                    }
                    var exm = LiveLog.Extras(); LiveLog.WriteExtras(exm);
                    foreach (var kv in exm) { if (kv.Value.Total <= 0) continue; var o = U(kv.Key); o["messages"] = (int)o["messages"] + kv.Value.Total; foreach (var pm in kv.Value.PerMonth) addM(mMsgs, pm.Key, kv.Key, pm.Value, false); }
                }
                catch (Exception ex) { Clog.Warn("boards", "hidden-source overlay failed: " + ex.Message); }
                // watch streaks
                foreach (var sh in Streaks.AllShares()) { if ((sh.Item3 ?? "").Length >= 7) addM(mStreak, sh.Item3.Substring(0, 7), sh.Item1, sh.Item2, true); }
                foreach (JObject b in (JArray)Streaks.Api()["board"]) { var o = U((string)b["login"]); o["streakBest"] = (int)b["best"]; o["streakCurrent"] = (int)b["current"]; o["streakAt"] = (string)b["lastSharedAt"]; if (o["name"].ToString() == (string)b["login"] && !string.IsNullOrEmpty((string)b["name"])) o["name"] = (string)b["name"]; }
                // points + watch time (StreamElements baseline + what the Host earned since), already folded by aliases
                var mPts = new Dictionary<string, Dictionary<string, int>>(); var mWatch = new Dictionary<string, Dictionary<string, int>>();
                try
                {
                    var eco = Economy.Snapshot(al);
                    foreach (var kv in eco.Users) { if (kv.Value.Points < 1 && kv.Value.Minutes < 1) continue; var o = U(kv.Key); o["points"] = (int)Math.Min(int.MaxValue, Math.Floor(kv.Value.Points)); o["watchMinutes"] = (int)Math.Min(int.MaxValue, Math.Floor(kv.Value.Minutes)); }
                    foreach (var mo in eco.Months) foreach (var kv in mo.Value) { addM(mPts, mo.Key, kv.Key, (int)Math.Floor(kv.Value.Points), false); addM(mWatch, mo.Key, kv.Key, (int)Math.Floor(kv.Value.Minutes), false); }
                }
                catch (Exception ex) { Clog.Warn("boards", "economy: " + ex.Message); }
                // real Twitch display names (from names.json) win over the name the logs happened to show
                var nm = Names(); foreach (var kv in users) { var e = nm[kv.Key] as JObject; string dn = e == null ? "" : (string)e["name"] ?? ""; if (dn != "") kv.Value["name"] = dn; }
                // aliases: fold the extra accounts of one person into the main login
                foreach (var kv in al)
                {
                    string a = kv.Key, c = Canon(al, kv.Key); JObject ao;
                    if (c == a || !users.TryGetValue(a, out ao)) continue;
                    var co = U(c);
                    co["gifts"] = (int)co["gifts"] + (int)ao["gifts"]; co["bits"] = (int)co["bits"] + (int)ao["bits"]; co["messages"] = (int)co["messages"] + (int)ao["messages"]; co["points"] = (int)co["points"] + (int)ao["points"]; co["watchMinutes"] = (int)co["watchMinutes"] + (int)ao["watchMinutes"];
                    co["streakBest"] = Math.Max((int)co["streakBest"], (int)ao["streakBest"]);
                    if (string.CompareOrdinal((string)ao["streakAt"] ?? "", (string)co["streakAt"] ?? "") > 0) { co["streakCurrent"] = ao["streakCurrent"]; co["streakAt"] = ao["streakAt"]; }
                    var aka = co["aka"] as JArray ?? new JArray(); if (!aka.Any(x => (string)x == a)) aka.Add(a); co["aka"] = aka;
                    if ((string)co["name"] == c && (string)ao["name"] != a && nm[c] == null) { /* keep the main account's own name */ }
                    users.Remove(a);
                }
                foreach (var kv in users) kv.Value["bitsBadge"] = BitsBadge((int)kv.Value["bits"]);
                try { ApplyBitsToProfiles(users.Where(kv => !BotName.IsMatch(kv.Key) && !KnownBots.Contains(kv.Key)).ToDictionary(kv => kv.Key, kv => kv.Value)); } catch (Exception ex) { Clog.Warn("boards", "bits roles: " + ex.Message); }
                try { ApplyProfileMeta(users.Where(kv => !BotName.IsMatch(kv.Key) && !KnownBots.Contains(kv.Key)).ToDictionary(kv => kv.Key, kv => kv.Value), al); } catch (Exception ex) { Clog.Warn("boards", "profile names: " + ex.Message); }
                // names for gifters / bitters without a profile come from the ledger user itself (already the login)
                var extra = ExtraBots(); string ch = Channel();
                var keep = users.Where(kv => !BotName.IsMatch(kv.Key) && !KnownBots.Contains(kv.Key) && !extra.Contains(kv.Key) && ((int)kv.Value["gifts"] > 0 || (int)kv.Value["bits"] > 0 || (int)kv.Value["messages"] > 0 || (int)kv.Value["streakBest"] > 0 || (int)kv.Value["points"] > 0 || (int)kv.Value["watchMinutes"] > 0)).ToList();
                var map = new JObject(); foreach (var kv in keep.OrderBy(k => k.Key, StringComparer.Ordinal)) { if (ch != "" && kv.Key == ch) kv.Value["streamer"] = true; map[kv.Key] = kv.Value; }
                Func<string, JArray> top = field => new JArray(keep.Where(kv => kv.Key != ch && (int)kv.Value[field] > 0).OrderByDescending(kv => (int)kv.Value[field]).ThenBy(kv => kv.Key, StringComparer.Ordinal).Take(500).Select(kv => new JObject { { "login", kv.Key }, { "name", kv.Value["name"] }, { "value", kv.Value[field] } }));
                // per-month boards (UTC months, Feb 2026 on): same people rules as the all-time board (no bots, streamer left out, aliases folded)
                var months = new JObject(); var keepSet = new HashSet<string>(keep.Select(k => k.Key));
                var allMonths = mGifts.Keys.Concat(mBits.Keys).Concat(mMsgs.Keys).Concat(mStreak.Keys).Concat(mPts.Keys).Concat(mWatch.Keys).Distinct().Where(m => string.CompareOrdinal(m, "2026-02") >= 0).OrderBy(m => m, StringComparer.Ordinal).ToList();
                Func<Dictionary<string, Dictionary<string, int>>, string, JArray> mtop = (dict, month) =>
                {
                    Dictionary<string, int> d; if (!dict.TryGetValue(month, out d)) return new JArray();
                    return new JArray(d.Where(kv => keepSet.Contains(kv.Key) && kv.Key != ch).OrderByDescending(kv => kv.Value).ThenBy(kv => kv.Key, StringComparer.Ordinal).Take(500)
                        .Select(kv => new JObject { { "login", kv.Key }, { "name", users.ContainsKey(kv.Key) ? users[kv.Key]["name"] : (JToken)kv.Key }, { "value", kv.Value } }));
                };
                foreach (var mo in allMonths) months[mo] = new JObject { { "gifters", mtop(mGifts, mo) }, { "bits", mtop(mBits, mo) }, { "yappers", mtop(mMsgs, mo) }, { "streaks", mtop(mStreak, mo) }, { "points", mtop(mPts, mo) }, { "watchtime", mtop(mWatch, mo) } };
                var res = new JObject { { "ok", true }, { "push", PushStatus() }, { "months", months }, { "updatedAt", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() }, { "streamerLogin", ch }, { "users", map },
                    { "top", new JObject { { "gifts", top("gifts") }, { "bits", top("bits") }, { "messages", top("messages") }, { "streaks", top("streakBest") }, { "points", top("points") }, { "watchtime", top("watchMinutes") } } },
                    { "note", "gifts and bits start in mid-Feb 2026 when the logs start; the streamer is flagged streamer:true and left out of the top lists" } };
                _cache = res; _cacheAt = DateTime.UtcNow;
                try { Directory.CreateDirectory(Path.GetDirectoryName(TotalsP)); File.WriteAllText(TotalsP, res.ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception) { }
                return res;
            }
        }

        public static JObject Api() { lock (L) { var r = (_cache == null || (DateTime.UtcNow - _cacheAt).TotalSeconds > 120) ? Compute() : _cache; r["push"] = PushStatus(); return r; } }

        /// <summary>recompute and (when forwarding to the site is on) push if the numbers changed or 30 minutes have passed.</summary>
        public static JObject Refresh(bool push)
        {
            var r = Compute();
            try { if (FetchNames(r)) r = Compute(); } catch (Exception ex) { Clog.Warn("boards", "names: " + ex.Message); }
            if (push && Lease.MayRun) PushToSite(r);
            return r;
        }
        // The site reads lifetime gifts and bits from its supporter tally: POST /api/bot/supporters {gifts:{login:n}, bits:{login:n}} (each login's number REPLACES the earlier one, max 3000 logins a call).
        // The watch streaks reach the site through the viewer profiles (roles.watchStreakBest / watchStreakCurrent, pushed by Pipeline/push-profiles.mjs).
        // the site key: vault BOT_API_KEY, the BOT_API_KEY environment variable, or the WebSyncKey the bots already use (it is the same key on the site). Never printed.
        internal static string SiteKey()
        {
            string key = Vault.Get("BOT_API_KEY"); if (key == "") key = Environment.GetEnvironmentVariable("BOT_API_KEY") ?? "";
            if (key == "") { try { key = (string)SubsImport.ParseJ(File.ReadAllText(Path.Combine(HostApi.DataDir, "settings.json")))["WebSyncKey"] ?? ""; } catch (Exception) { } }
            return key;
        }
        static string _lastBoardsHash = ""; static DateTime _lastBoards = DateTime.MinValue;
        // The full snapshot for the leaderboards page: POST /api/bot/boards {updatedAt, users:{login:{name,gifts,bits,messages,streakBest,streakCurrent,streakAt}}} (replaces the stored board; the site
        // drops all-zero users and the streamer/bots itself). This carries the watch streaks too, so they do not have to wait for the daily profile push.
        static void PushBoards(JObject r, JObject s, string key)
        {
            var users = new JObject(); string ch = (string)r["streamerLogin"] ?? "";
            foreach (var p in ((JObject)r["users"]).Properties()) { if (p.Name == ch || !Regex.IsMatch(p.Name, "^[a-z0-9_]{2,25}$")) continue; var o = (JObject)p.Value; users[p.Name] = new JObject { { "name", o["name"] }, { "gifts", o["gifts"] }, { "bits", o["bits"] }, { "messages", o["messages"] }, { "streakBest", o["streakBest"] }, { "streakCurrent", o["streakCurrent"] }, { "streakAt", o["streakAt"] }, { "bitsBadge", o["bitsBadge"] }, { "points", o["points"] }, { "watchMinutes", o["watchMinutes"] } }; if (o["aka"] != null) users[p.Name]["aka"] = o["aka"]; }
            string hash = Convert.ToBase64String(System.Security.Cryptography.SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(users.ToString(Newtonsoft.Json.Formatting.None) + r["months"].ToString(Newtonsoft.Json.Formatting.None))));
            if (hash == _lastBoardsHash && (DateTime.UtcNow - _lastBoards).TotalMinutes < 30) return;
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(30) })
                {
                    var rq = new HttpRequestMessage(HttpMethod.Post, (string)s["SiteBoardsUrl"] ?? "https://innocentpenguin.com/api/bot/boards") { Content = new StringContent(new JObject { { "updatedAt", r["updatedAt"] }, { "users", users }, { "months", r["months"] }, { "pointsName", Economy.CurrencyName }, { "drop", DropList() }, { "aliases", JObject.FromObject(AliasMap()) } }.ToString(Newtonsoft.Json.Formatting.None), Encoding.UTF8, "application/json") };
                    rq.Headers.Add("Authorization", "Bearer " + key); rq.Headers.UserAgent.ParseAdd("PinguinoHost/1.0");   // the site is behind Cloudflare, which refuses requests with no User-Agent (error 1010)
                    var resp = h.SendAsync(rq).Result;
                    if (!resp.IsSuccessStatusCode) { _pushNote += "; boards HTTP " + (int)resp.StatusCode; _lastBoards = DateTime.UtcNow.AddMinutes(-25); Clog.Warn("boards", "site did not accept the board (HTTP " + (int)resp.StatusCode + ")"); return; }
                }
                _lastBoardsHash = hash; _lastBoards = DateTime.UtcNow; _pushNote += "; board ok (" + users.Count + " people)"; Clog.Info("boards", "board pushed to the site: HTTP 200, " + users.Count + " people");
            }
            catch (Exception ex) { _pushNote += "; boards error: " + ex.Message; _lastBoards = DateTime.UtcNow.AddMinutes(-25); Clog.Warn("boards", "board push failed: " + ex.Message); }
        }

        static void PushToSite(JObject r)
        {
            var s = Latest.Settings(); if ((bool?)s["ForwardBoards"] == false) { _pushNote = "off (ForwardBoards = false)"; Clog.Info("boards", "push skipped: ForwardBoards is false"); return; }   // on by default: the boards are public data; the events forwarding switch (ForwardToSite) is a different thing
            string key = SiteKey();
            if (key == "") { _pushNote = "no key (vault BOT_API_KEY or settings.json WebSyncKey)"; Clog.Warn("boards", "push skipped: no site key (vault BOT_API_KEY / settings.json WebSyncKey)"); return; }
            string ch = (string)r["streamerLogin"] ?? "";
            var rows = ((JObject)r["users"]).Properties().Where(p => p.Name != ch && ((int)p.Value["gifts"] > 0 || (int)p.Value["bits"] > 0)).OrderBy(p => p.Name, StringComparer.Ordinal).ToList();
            string hash = Convert.ToBase64String(System.Security.Cryptography.SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(string.Join("|", rows.Select(p => p.Name + ":" + (int)p.Value["gifts"] + ":" + (int)p.Value["bits"])))));
            if (hash == _lastPushHash && (DateTime.UtcNow - _lastPush).TotalMinutes < 30) { _pushNote = "supporters unchanged"; PushBoards(r, s, key); return; }
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(20) })
                    for (int i = 0; i < Math.Max(1, rows.Count); i += 2500)
                    {
                        var gifts = new JObject(); var bits = new JObject();
                        foreach (var p in rows.Skip(i).Take(2500)) { if ((int)p.Value["gifts"] > 0) gifts[p.Name] = (int)p.Value["gifts"]; if ((int)p.Value["bits"] > 0) bits[p.Name] = (int)p.Value["bits"]; }
                        var rq = new HttpRequestMessage(HttpMethod.Post, (string)s["SiteSupportersUrl"] ?? "https://innocentpenguin.com/api/bot/supporters") { Content = new StringContent(new JObject { { "gifts", gifts }, { "bits", bits }, { "drop", DropList() } }.ToString(Newtonsoft.Json.Formatting.None), Encoding.UTF8, "application/json") };
                        rq.Headers.Add("Authorization", "Bearer " + key); rq.Headers.UserAgent.ParseAdd("PinguinoHost/1.0");   // the site is behind Cloudflare, which refuses requests with no User-Agent (error 1010)
                        var resp = h.SendAsync(rq).Result;
                        if (!resp.IsSuccessStatusCode) { _pushNote = "supporters: site answered HTTP " + (int)resp.StatusCode; _lastPush = DateTime.UtcNow.AddMinutes(-25); Clog.Warn("boards", "site did not accept the totals (HTTP " + (int)resp.StatusCode + ")"); return; }
                    }
                _lastPushHash = hash; _lastPush = DateTime.UtcNow; _pushNote = "supporters ok (" + rows.Count + " people)"; Clog.Info("boards", "gifts/bits pushed to the site (supporters): " + rows.Count + " people");
            }
            catch (Exception ex) { _pushNote = "error: " + ex.Message; _lastPush = DateTime.UtcNow.AddMinutes(-25); Clog.Warn("boards", "supporters push failed: " + ex.Message); }
            PushBoards(r, s, key);
        }
        public static JObject PushStatus() { return new JObject { { "note", _pushNote }, { "lastSupportersPush", _lastPush == DateTime.MinValue ? "" : _lastPush.ToString("o") }, { "lastBoardPush", _lastBoards == DateTime.MinValue ? "" : _lastBoards.ToString("o") } }; }
        public static string PushNote() { return _pushNote; }
    }
}
