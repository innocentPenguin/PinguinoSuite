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
    /// <summary>The Host's side of the innocentpenguin.com bot API (Bearer BOT_API_KEY, the same key SiteFeed and the boards push use; it is never logged).
    /// Base URL: env PINGUINO_SITE_BASE, else latest_settings.json "SiteBotBase", else https://innocentpenguin.com.</summary>
    public static class SiteHttp
    {
        static readonly HttpClient Http = MakeClient();
        static HttpClient MakeClient() { var h = new HttpClient { Timeout = TimeSpan.FromSeconds(10) }; h.DefaultRequestHeaders.UserAgent.ParseAdd("PinguinoHost/1.0"); return h; }   // Cloudflare answers error 1010 without a User-Agent
        public static string Base()
        {
            string b = Environment.GetEnvironmentVariable("PINGUINO_SITE_BASE");
            if (string.IsNullOrEmpty(b)) { try { b = (string)Latest.Settings()["SiteBotBase"]; } catch (Exception) { } }
            return (string.IsNullOrEmpty(b) ? "https://innocentpenguin.com" : b).TrimEnd('/');
        }
        public static int PollSec { get { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_SITE_POLL_SEC"), out v) && v > 0 ? v : 30; } }
        /// <summary>returns the HTTP status (0 = no answer at all); json is the parsed body or null</summary>
        public static int Call(string method, string path, JObject body, string key, out JObject json)
        {
            json = null;
            try
            {
                var rq = new HttpRequestMessage(new HttpMethod(method), Base() + path);
                rq.Headers.Add("Authorization", "Bearer " + key);
                if (body != null) rq.Content = new StringContent(body.ToString(Newtonsoft.Json.Formatting.None), Encoding.UTF8, "application/json");
                var r = Http.SendAsync(rq).Result; string t = r.Content.ReadAsStringAsync().Result;
                try { json = JObject.Parse(t); } catch (Exception) { }
                return (int)r.StatusCode;
            }
            catch (Exception) { return 0; }
        }
        public static bool Enabled(string setting) { try { return (bool?)Latest.Settings()[setting] != false; } catch (Exception) { return true; } }
        internal static string Key() { return Boards.SiteKey(); }
        internal static JObject ReadJ(string f) { try { if (File.Exists(f)) return JObject.Parse(File.ReadAllText(f, Encoding.UTF8)); } catch (Exception) { } return new JObject(); }
        internal static void WriteJ(string f, JObject d) { try { Directory.CreateDirectory(HostApi.DataDir); string tmp = f + ".tmp"; File.WriteAllText(tmp, d.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); if (File.Exists(f)) File.Delete(f); File.Move(tmp, f); } catch (Exception ex) { Clog.Warn("site", "could not save " + Path.GetFileName(f) + ": " + ex.Message); } }
        public static JObject Status() { return new JObject { { "ok", true }, { "teach", SiteTeach.Status() }, { "shop", SiteShop.Status() } }; }
    }

    /// <summary>Teach bridge: the site's pending teach notes (GET /api/bot/teach?status=pending) go into the normal Teach inbox, once per site id. The Host checks the author itself
    /// (trusted list or the role it has seen in chat), cleans the text again (links and @mentions out) and nothing happens until Ivan approves. His decision is posted back
    /// (POST /api/bot/teach/status), kept in an outbox until the site took it.</summary>
    public static class SiteTeach
    {
        static readonly object L = new object(); static bool _started; static string _result = "not started";
        static string P { get { return Path.Combine(HostApi.DataDir, "site_teach.json"); } }
        static readonly Regex RxId = new Regex("^[A-Za-z0-9_-]{1,64}$");
        static readonly string[] Kinds = { "fact", "lore", "command", "instruction", "correction" }, Targets = { "helper", "chatty", "lore", "b0t" };

        public static JObject Status() { lock (L) { return new JObject { { "result", _result }, { "outbox", ((JArray)Doc()["outbox"]).Count }, { "dropped", Doc()["dropped"] } }; } }
        static JObject Doc() { var d = SiteHttp.ReadJ(P); if (!(d["outbox"] is JArray)) d["outbox"] = new JArray(); if (!(d["dropped"] is JArray)) d["dropped"] = new JArray(); return d; }

        public static void Start()
        {
            if (_started) return; _started = true;
            Teach.Decided += it => { string sid = (string)it["siteId"]; if (sid == null) return; Enqueue(sid, (string)it["status"], (string)it["note"], (string)it["reviewer"]); };
            Task.Run(async () => { await Task.Delay(4000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(SiteHttp.PollSec * 1000); } });
        }

        static void Enqueue(string id, string hostStatus, string note, string reviewer)
        {
            string st = hostStatus == "rejected" ? "rejected" : "approved";   // edited counts as approved for the site
            note = Regex.Replace(note ?? "", @"\s+", " ").Trim(); if (hostStatus == "edited" && note == "") note = "edited by Ivan"; if (note.Length > 200) note = note.Substring(0, 200);
            lock (L)
            {
                var d = Doc(); var ob = (JArray)d["outbox"]; foreach (var x in ob.OfType<JObject>().Where(x => (string)x["id"] == id).ToList()) x.Remove();
                ob.Add(new JObject { { "id", id }, { "status", st }, { "note", note } }); SiteHttp.WriteJ(P, d);
            }
        }

        public static void Tick()
        {
            if (!SiteHttp.Enabled("SiteTeachBridge")) { _result = "off"; return; }
            string key = SiteHttp.Key(); if (key == "") { _result = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            JObject j; int code = SiteHttp.Call("GET", "/api/bot/teach?status=pending", null, key, out j);
            if (code == 401) { _result = "site refused the key (HTTP 401)"; Clog.Warn("site", "teach: the site refused the key (401)"); return; }
            if (code != 200 || j == null) { _result = code == 0 ? "site not reachable" : "site answered HTTP " + code; return; }
            int added = 0;
            foreach (var s in (j["items"] as JArray ?? new JArray()).OfType<JObject>())
            {
                string id = (string)s["id"] ?? ""; if (!RxId.IsMatch(id)) continue;
                var have = Teach.FindSite(id);
                if (have != null)
                {   // already in the inbox. If it is decided but the site still lists it as pending, the answer got lost: send it again.
                    string hs = (string)have["status"]; bool gaveUp; lock (L) gaveUp = ((JArray)Doc()["dropped"]).OfType<JObject>().Any(x => (string)x["id"] == id); if (hs != "pending" && !gaveUp) Enqueue(id, hs, (string)have["note"], (string)have["reviewer"]);
                    continue;
                }
                string from = ((string)s["from"] ?? "").Trim().TrimStart('@').ToLowerInvariant();
                string kind = ((string)s["kind"] ?? "").ToLowerInvariant(), target = ((string)s["target"] ?? "").ToLowerInvariant(), text = (string)s["text"] ?? "";
                if (Targets.Contains(target)) text = target + ": " + text;   // the first prefix wins, anything inside the text stays text
                string why; var it = Teach.Submit(from, Roster.RoleOf(from), text, Kinds.Contains(kind) ? kind : null, "site-bridge", out why, id);
                if (it != null) { added++; continue; }
                if (why == "not allowed") Enqueue(id, "rejected", "author is not on the Host's trusted list", "host");
                else if (why == "empty") Enqueue(id, "rejected", "nothing left after cleaning the text", "host");
                // inbox full / duplicate: try again next round
            }
            int sent = Flush(key); if (_result.StartsWith("site refused")) return;
            _result = "ok (" + added + " new, " + sent + " answers sent)";
        }

        static int Flush(string key)
        {
            List<JObject> todo; lock (L) todo = ((JArray)Doc()["outbox"]).OfType<JObject>().Select(x => (JObject)x.DeepClone()).ToList();
            int sent = 0;
            foreach (var o in todo)
            {
                JObject r; int code = SiteHttp.Call("POST", "/api/bot/teach/status", new JObject { { "id", o["id"] }, { "status", o["status"] }, { "note", o["note"] } }, key, out r);
                if (code == 401) { _result = "site refused the key (HTTP 401)"; return sent; }
                if (code == 0 || code >= 500 || code == 429) { _result = "site busy (HTTP " + code + "), will retry"; continue; }
                lock (L)
                {
                    var d = Doc(); foreach (var x in ((JArray)d["outbox"]).OfType<JObject>().Where(x => (string)x["id"] == (string)o["id"]).ToList()) x.Remove();
                    if (code != 200)
                    {   // 404 unknown id, 400 bad status, 409 the site already has the other decision: nothing more to do, keep a note
                        var dr = (JArray)d["dropped"]; dr.Add(new JObject { { "id", o["id"] }, { "status", o["status"] }, { "http", code }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } }); while (dr.Count > 30) dr.RemoveAt(0);
                        Clog.Warn("site", "teach decision " + (string)o["id"] + " not accepted (HTTP " + code + ")");
                    }
                    else sent++;
                    SiteHttp.WriteJ(P, d);
                }
            }
            return sent;
        }
    }

    /// <summary>The HIDDEN shop. Nothing here is in the nav, help or the commands page until Ivan reveals it. The site queues purchases; the Host validates, takes the pengs,
    /// runs the item and reports back. Every purchase id is handled once (processed ids are saved), so a restart never charges twice.</summary>
    public static class SiteShop
    {
        static readonly object L = new object(); static bool _started; static string _result = "not started"; static string _cfgHash = ""; static DateTime _cfgPushed = DateTime.MinValue;
        static readonly Random Rng = new Random();
        static string P { get { return Path.Combine(HostApi.DataDir, "site_shop.json"); } }
        public static string UnlockPath { get { return Path.Combine(HostApi.DataDir, "chatty_unlock.json"); } }
        static readonly Regex RxId = new Regex("^[A-Za-z0-9_-]{1,64}$"), RxLogin = new Regex("^[a-z0-9_]{2,25}$");

        // ---- settings (defaults; Data\runtime\site_shop_settings.json overrides) ----
        public static JObject Cfg()
        {
            var d = new JObject { { "BuyChattyPrice", 5000 }, { "MinStake", 100 }, { "MaxStake", 2000 }, { "UserCooldownSec", 1800 }, { "GlobalCooldownSec", 600 }, { "GuessSeconds", 300 }, { "MaxGuesses", 3 }, { "HistoryDays", 14 } };
            foreach (var p in SiteHttp.ReadJ(Path.Combine(HostApi.DataDir, "site_shop_settings.json")).Properties()) d[p.Name] = p.Value;
            int u, g; if (int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_SHOP_USER_CD_SEC"), out u)) d["UserCooldownSec"] = u; if (int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_SHOP_GLOBAL_CD_SEC"), out g)) d["GlobalCooldownSec"] = g;
            return d;
        }
        static long I(JObject c, string k) { return (long?)c[k] ?? 0; }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        public static bool ChattyUnlocked() { return (bool?)SiteHttp.ReadJ(UnlockPath)["unlocked"] == true; }

        static JObject Doc()
        {
            var d = SiteHttp.ReadJ(P);
            foreach (var k in new[] { "processed", "userLast" }) if (!(d[k] is JObject)) d[k] = new JObject();
            return d;
        }
        static void Save(JObject d) { SiteHttp.WriteJ(P, d); }
        public static JObject Status() { lock (L) { var d = Doc(); return new JObject { { "result", _result }, { "processed", ((JObject)d["processed"]).Count }, { "game", d["game"] != null && d["game"].Type != JTokenType.Null }, { "chattyUnlocked", ChattyUnlocked() }, { "unposted", ((JObject)d["processed"]).Properties().Count(p => (bool?)p.Value["posted"] != true) } }; } }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(6000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(SiteHttp.PollSec * 1000); } });
        }

        static JObject ConfigBody()
        {
            var c = Cfg();
            return new JObject { { "currency", Economy.CurrencyName }, { "items", new JObject {   // the site's final contract (Docs/SHOP_BRIDGE.md section 5)
                { "guess", new JObject { { "min", I(c, "MinStake") }, { "max", I(c, "MaxStake") }, { "payoutMultiplier", 2 }, { "cooldownUser", I(c, "UserCooldownSec") }, { "cooldownGlobal", I(c, "GlobalCooldownSec") } } },
                { "chatty", new JObject { { "price", I(c, "BuyChattyPrice") } } } } } };
        }

        /// <summary>The site sends its item ids (guess-the-chatter, buy-chatty); the short keys and the old names are accepted too.</summary>
        static string NormItem(string item)
        {
            item = (item ?? "").ToLowerInvariant().Replace('-', '_');
            if (item == "guess" || item == "guess_the_chatter" || item == "guess_chatter") return "guess_chatter";
            if (item == "chatty" || item == "buy_chatty") return "buy_chatty";
            return item;
        }

        public static void Tick()
        {
            if (!SiteHttp.Enabled("SiteShop")) { _result = "off"; return; }
            string key = SiteHttp.Key(); if (key == "") { _result = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            ExpireGame();
            JObject r; int code;
            var cb = ConfigBody(); string h = cb.ToString(Newtonsoft.Json.Formatting.None);
            if (h != _cfgHash || (DateTime.UtcNow - _cfgPushed).TotalMinutes > 60)
            {
                code = SiteHttp.Call("POST", "/api/bot/shop/config", cb, key, out r);
                if (code == 401) { _result = "site refused the key (HTTP 401)"; return; }
                if (code == 200) { _cfgHash = h; _cfgPushed = DateTime.UtcNow; }
            }
            JObject j; code = SiteHttp.Call("GET", "/api/bot/shop?status=pending", null, key, out j);
            if (code == 401) { _result = "site refused the key (HTTP 401)"; Clog.Warn("site", "shop: the site refused the key (401)"); return; }
            if (code != 200 || j == null) { _result = code == 0 ? "site not reachable" : "site answered HTTP " + code; return; }
            int n = 0;
            foreach (var s in ((j["requests"] ?? j["items"]) as JArray ?? new JArray()).OfType<JObject>()) { Process(s); n++; }
            int posted = Flush(key);
            if (!_result.StartsWith("site refused")) _result = "ok (" + n + " seen, " + posted + " answers sent)";
        }

        // ---- one purchase ----
        static void Record(JObject d, string id, string login, string item, string status, long payout, string note, bool resolved)
        {
            note = Regex.Replace(note ?? "", @"\s+", " ").Trim(); if (note.Length > 200) note = note.Substring(0, 200);
            ((JObject)d["processed"])[id] = new JObject { { "login", login }, { "item", item }, { "status", status }, { "payout", payout }, { "note", note }, { "at", Now() }, { "posted", false }, { "final", resolved } };
        }

        static void Process(JObject s)
        {
            string id = (string)s["id"] ?? ""; if (!RxId.IsMatch(id)) return;
            lock (L)
            {
                var d = Doc(); var pr = (JObject)d["processed"];
                if (pr[id] != null) return;   // seen: its answer is (re)sent by Flush, never decided or charged again
                string login = ((string)s["login"] ?? "").Trim().TrimStart('@').ToLowerInvariant(), item = NormItem((string)s["item"]); long stake = (long?)s["stake"] ?? 0;
                string sid = "shop-" + id; var c = Cfg(); long now = Now();
                Action<string> no = why => { Record(d, id, login, item, "rejected", 0, why, true); Save(d); };
                if (!RxLogin.IsMatch(login)) { no("bad user"); return; }
                bool already = Economy.Applied(sid);   // charged before a crash: finish the job, do not validate or charge again
                if (item == "buy_chatty")
                {
                    long price = I(c, "BuyChattyPrice");
                    if (!already)
                    {
                        if (ChattyUnlocked()) { no("ChattyPinguino is already unlocked"); return; }
                        if (Economy.Balance(login) < price) { no("not enough " + Economy.CurrencyName + " (it costs " + price + ")"); return; }
                        string err = Economy.Spend(sid, login, price, "shop buy_chatty"); if (err != null) { no(err); return; }
                    }
                    SiteHttp.WriteJ(UnlockPath, new JObject { { "unlocked", true }, { "by", login }, { "at", now }, { "id", id } });
                    Record(d, id, login, item, "accepted", 0, "ChattyPinguino is unlocked: it can chat on its own now", true); Save(d); return;
                }
                if (item == "guess_chatter")
                {
                    if (stake < I(c, "MinStake") || stake > I(c, "MaxStake")) { no("stake must be " + I(c, "MinStake") + " to " + I(c, "MaxStake")); return; }
                    if (!already)
                    {
                        long ul = (long?)d["userLast"][login] ?? 0; if (now - ul < I(c, "UserCooldownSec")) { no("you played a moment ago, wait a little"); return; }
                        long gl = (long?)d["globalLast"] ?? 0; if (now - gl < I(c, "GlobalCooldownSec")) { no("the game is cooling down, try again soon"); return; }
                        if (d["game"] != null && d["game"].Type != JTokenType.Null) { no("a round is already running"); return; }
                        if (Economy.Balance(login) < stake) { no("not enough " + Economy.CurrencyName); return; }
                    }
                    string who; string line = PickLine(login, out who); if (line == null) { no("no suitable chat line to use right now"); return; }
                    if (!already) { string err = Economy.Spend(sid, login, stake, "shop guess_chatter"); if (err != null) { no(err); return; } }
                    d["userLast"][login] = now; d["globalLast"] = now;
                    d["game"] = new JObject { { "id", id }, { "login", login }, { "stake", stake }, { "line", line }, { "answer", who }, { "at", now }, { "guesses", 0 } };
                    Record(d, id, login, item, "accepted", 0, "Who said this? \"" + (line.Length > 110 ? line.Substring(0, 110) : line) + "\" Answer in chat with !guess <name>, " + I(c, "MaxGuesses") + " tries.", false); Save(d); return;
                }
                no("unknown item");
            }
        }

        // ---- the game ----
        static void ExpireGame()
        {
            lock (L)
            {
                var d = Doc(); var g = d["game"] as JObject; if (g == null) return;
                if (Now() - (long)g["at"] < I(Cfg(), "GuessSeconds")) return;
                Finish(d, g, false, "time ran out, it was " + (string)g["answer"]);
            }
        }
        static void Finish(JObject d, JObject g, bool won, string note)
        {
            string id = (string)g["id"], login = (string)g["login"]; long stake = (long)g["stake"], pay = won ? stake * 2 : 0;
            if (won) Economy.Credit("shop-win-" + id, login, pay, "shop guess_chatter win");
            Record(d, id + "#result", login, "guess_chatter", won ? "won" : "lost", pay, note, true);
            ((JObject)d["processed"])[id + "#result"]["site"] = id;   // the site knows the purchase by its own id
            d["game"] = null; Save(d);
        }
        /// <summary>!guess &lt;name&gt; from chat. Only the player of the running round gets an answer; everyone else gets nothing (the shop is hidden).</summary>
        public static bool HandleGuess(string user, string[] args, Action<string> say)
        {
            string msg = null;
            lock (L)
            {
                var d = Doc(); var g = d["game"] as JObject; string me = (user ?? "").ToLowerInvariant();
                if (g == null || (string)g["login"] != me) return false;
                string guess = string.Join(" ", args ?? new string[0]).Trim().TrimStart('@').ToLowerInvariant(); if (guess == "") return false;
                if (guess == (string)g["answer"]) { long pay = (long)g["stake"] * 2; Finish(d, g, true, "right, it was " + (string)g["answer"]); msg = "@" + user + " Correct! It was " + (string)g["answer"] + ". You win " + pay + " " + Economy.CurrencyName + "!"; }
                else
                {
                    int n = (int)g["guesses"] + 1; g["guesses"] = n; int left = (int)I(Cfg(), "MaxGuesses") - n;
                    if (left <= 0) { Finish(d, g, false, "out of tries, it was " + (string)g["answer"]); msg = "@" + user + " No luck, it was " + (string)g["answer"] + "."; }
                    else { Save(d); msg = "@" + user + " Nope, " + left + " " + (left == 1 ? "try" : "tries") + " left."; }
                }
            }
            if (msg != null) say(msg); return true;
        }

        // ---- the line: old chat, anonymised, never from someone who opted out, never anything heavy ----
        static readonly Regex Sensitive = new Regex(@"\b(kill (my|him|her|your)self|suicid|self[- ]?harm|want to die|end it all|cutting myself|rape|nigg|fagg|retard|kys|nazi|hitler|porn|nsfw|nude|dox|address is|phone number|my (real )?name is|i live in|password|token|cancer|diagnos|funeral|passed away|died|abus|overdose|drugs?|cocaine|weed|trump|biden|election|gaza|israel)\b|\d{3}[-. ]?\d{3}[-. ]?\d{4}|[\w.+-]+@[\w-]+\.\w+", RegexOptions.IgnoreCase);
        static HashSet<string> OptedOut()
        {
            var set = new HashSet<string>();
            try
            {
                foreach (var p in SiteHttp.ReadJ(Path.Combine(HostApi.DataDir, "chat_memory.json")).Properties())
                {
                    var v = p.Value as JObject; if (v == null || string.IsNullOrEmpty((string)v["Privacy"])) continue;
                    set.Add(p.Name); string lg = ((string)v["Login"] ?? "").ToLowerInvariant(); if (lg != "") set.Add(lg);
                    foreach (var a in v["Aliases"] as JArray ?? new JArray()) set.Add(((string)a ?? "").ToLowerInvariant());
                }
            }
            catch (Exception) { }
            return set;
        }
        /// <summary>a random eligible line (anonymised: links, @mentions and the author's own name removed) and its author's login</summary>
        public static string PickLine(string exceptLogin, out string author)
        {
            author = null; var cands = new List<KeyValuePair<string, string>>();
            try
            {
                var out_ = OptedOut(); string dir = LiveLog.LiveDir; if (!Directory.Exists(dir)) return null;
                try { foreach (var hp in (SiteHttp.ReadJ(Path.Combine(Path.GetDirectoryName(dir), "hidden_sources.json"))["users"] as JObject ?? new JObject()).Properties()) out_.Add(hp.Name.ToLowerInvariant()); } catch (Exception) { }   // people who opted out of the public logs are out too
                var files = Directory.GetFiles(dir, "*.jsonl").OrderByDescending(f => f).Take((int)I(Cfg(), "HistoryDays")).ToList();
                foreach (var f in files)
                    foreach (var ln in File.ReadLines(f, Encoding.UTF8))
                    {
                        JObject o; try { o = JObject.Parse(ln.TrimStart('﻿')); } catch (Exception) { continue; }
                        string u = ((string)o["u"] ?? "").ToLowerInvariant(), i = (string)o["i"] ?? "", m = (string)o["m"] ?? "";
                        if ((int?)o["c"] == 1 || u == "" || u == exceptLogin || Boards.IsBot(u) || out_.Contains(u) || out_.Contains(i)) continue;
                        if (m.StartsWith("!") || m.StartsWith("/") || m.IndexOf("pinguinob0t", StringComparison.OrdinalIgnoreCase) >= 0 || Sensitive.IsMatch(m)) continue;
                        bool stripped; string c = Teach.Clean(m, out stripped); if (stripped) continue;   // had a link or an @mention: not used
                        c = Regex.Replace(c, Regex.Escape(u), "someone", RegexOptions.IgnoreCase);
                        if (c.Length < 20 || c.Length > 140 || c.Count(ch => char.IsLetter(ch)) < 12) continue;
                        cands.Add(new KeyValuePair<string, string>(c, u));
                    }
            }
            catch (Exception ex) { Clog.Warn("shop", "reading chat history: " + ex.Message); return null; }
            if (cands.Count == 0) return null;
            var pick = cands[Rng.Next(cands.Count)]; author = pick.Value; return pick.Key;
        }

        // ---- telling the site ----
        static int Flush(string key)
        {
            List<KeyValuePair<string, JObject>> todo;
            lock (L) todo = ((JObject)Doc()["processed"]).Properties().Where(p => (bool?)p.Value["posted"] != true).Select(p => new KeyValuePair<string, JObject>(p.Name, (JObject)p.Value.DeepClone())).ToList();
            int sent = 0;
            foreach (var kv in todo)
            {
                var o = kv.Value; string sid = (string)o["site"] ?? kv.Key.Split('#')[0];
                JObject r; int code = SiteHttp.Call("POST", "/api/bot/shop/status", new JObject { { "id", sid }, { "status", o["status"] }, { "payout", o["payout"] }, { "note", o["note"] } }, key, out r);
                if (code == 401) { _result = "site refused the key (HTTP 401)"; return sent; }
                if (code == 0 || code >= 500 || code == 429) continue;
                lock (L)
                {
                    var d = Doc(); var e = ((JObject)d["processed"])[kv.Key] as JObject; if (e == null) continue;
                    e["posted"] = true; e["http"] = code; Save(d); if (code == 200) sent++; else Clog.Warn("shop", "status for " + sid + " not accepted (HTTP " + code + ")");
                }
            }
            return sent;
        }
    }
}
