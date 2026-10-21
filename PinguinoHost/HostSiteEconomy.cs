using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The Points page's bridge (Docs\ECONOMY_CONTRACT.md). The Host PUSHES per-user views (balance, rank, next depreciation, loans, earnings by source, recent ledger) to
    /// POST /api/bot/economy/users, only for people whose view changed (hash per user), 100 per request. The site's viewers act through a queue the Host POLLS:
    /// GET /api/bot/economy/requests?status=pending -> [{id, login, action: loan_take|loan_repay, amount}], answered with POST /api/bot/economy/answers {id, status: done|rejected, message, balance, owed}.
    /// Each site request id is decided once (site_economy.json), its answer is retried until the site took it. Same key, same 401 handling as the shop bridge.</summary>
    public static class SiteEconomy
    {
        static readonly object L = new object(); static bool _started; static string _result = "not started";
        static string P { get { return System.IO.Path.Combine(HostApi.DataDir, "site_economy.json"); } }
        static readonly Regex RxId = new Regex("^[A-Za-z0-9_-]{1,64}$"), RxLogin = new Regex("^[a-z0-9_]{1,25}$");
        static readonly Dictionary<string, string> Sent = new Dictionary<string, string>(); static DateTime _lastPush = DateTime.MinValue;
        static int PushSec { get { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_PUSH_SEC"), out v) && v > 0 ? v : 60; } }

        static JObject Doc() { var d = SiteHttp.ReadJ(P); if (!(d["processed"] is JObject)) d["processed"] = new JObject(); return d; }
        public static JObject Status() { lock (L) return new JObject { { "result", _result }, { "processed", ((JObject)Doc()["processed"]).Count }, { "usersKnownToSite", Sent.Count } }; }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(8000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(SiteHttp.PollSec * 1000); } });
        }

        static string Hash(string s) { using (var h = SHA1.Create()) return Convert.ToBase64String(h.ComputeHash(Encoding.UTF8.GetBytes(s))); }

        public static void Tick()
        {
            if (!SiteHttp.Enabled("SiteEconomy")) { _result = "off"; return; }
            string key = SiteHttp.Key(); if (key == "") { _result = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            JObject j; int code = SiteHttp.Call("GET", "/api/bot/economy/requests?status=pending", null, key, out j), n = 0;
            if (code == 401) { _result = "site refused the key (HTTP 401)"; return; }
            if (code != 200 || j == null) { _result = code == 0 ? "site not reachable" : "site answered HTTP " + code; if (code != 404) return; }
            else foreach (var s in ((j["requests"] ?? j["items"]) as JArray ?? new JArray()).OfType<JObject>()) { Process(s); n++; }
            int answered = Flush(key); if (_result.StartsWith("site refused")) return;
            int pushed = 0; if ((DateTime.UtcNow - _lastPush).TotalSeconds >= PushSec || n > 0) { _lastPush = DateTime.UtcNow; pushed = PushUsers(key); }
            if (!_result.StartsWith("site refused")) _result = "ok (" + n + " requests, " + answered + " answers sent, " + pushed + " users pushed)";
        }

        /// <summary>one view per person who has points, a loan or a ledger line; unchanged views are not sent again</summary>
        static int PushUsers(string key)
        {
            var cx = Economy.BuildCtx();
            var logins = cx.S.Users.Where(k => !Boards.IsBot(k.Key) && (k.Value.Points >= 1 || cx.Led.ContainsKey(k.Key))).Select(k => k.Key).Concat(Economy.LoanLogins()).Distinct().ToList();
            var batch = new JArray(); var hashes = new Dictionary<string, string>(); int total = 0;
            Func<bool> flush = () =>
            {
                if (batch.Count == 0) return true;
                JObject r; int code = SiteHttp.Call("POST", "/api/bot/economy/users", new JObject { { "currency", Economy.CurrencyName }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "settings", Economy.PublicSettings() }, { "users", batch } }, key, out r);
                if (code == 401) { _result = "site refused the key (HTTP 401)"; return false; }
                if (code == 200) { total += batch.Count; foreach (var kv in hashes) Sent[kv.Key] = kv.Value; }
                else if (code == 404) return false;   // the site has no Points page yet
                batch = new JArray(); hashes = new Dictionary<string, string>(); return code != 0 && code < 500;
            };
            foreach (var l in logins)
            {
                var v = Economy.Me2(l, 30, cx); v.Remove("ok"); string h = Hash(v.ToString(Newtonsoft.Json.Formatting.None));
                string old; if (Sent.TryGetValue(l, out old) && old == h) continue;
                batch.Add(v); hashes[l] = h;
                if (batch.Count >= 100 && !flush()) return total;
            }
            flush(); return total;
        }

        static void Process(JObject s)
        {
            string id = (string)s["id"] ?? ""; if (!RxId.IsMatch(id)) return;
            string login = ((string)s["login"] ?? "").Trim().TrimStart('@').ToLowerInvariant(), act = ((string)s["action"] ?? "").ToLowerInvariant(); long amount = (long?)s["amount"] ?? 0;
            lock (L)
            {
                var d = Doc(); var pr = (JObject)d["processed"];
                var seen = pr[id] as JObject; if (seen != null) { int again = (int?)seen["again"] ?? 0; if ((bool?)seen["posted"] == true && again < 20) { seen["posted"] = false; seen["again"] = again + 1; SiteHttp.WriteJ(P, d); } return; }   // the site still lists it: say the answer again, never decide again
                JObject r;
                if (!RxLogin.IsMatch(login)) r = new JObject { { "ok", false }, { "error", "bad user" } };
                else if (act == "loan_take") r = Economy.LoanTake(login, amount, "site-" + id);
                else if (act == "loan_repay") r = Economy.LoanRepay(login, amount, "site-" + id);
                else r = new JObject { { "ok", false }, { "error", "unknown action" } };
                bool ok = (bool?)r["ok"] == true; string msg = Regex.Replace((string)(ok ? r["message"] : r["error"]) ?? "", @"\s+", " ").Trim(); if (msg.Length > 200) msg = msg.Substring(0, 200);
                pr[id] = new JObject { { "login", login }, { "action", act }, { "status", ok ? "done" : "rejected" }, { "message", msg }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "posted", false } };
                SiteHttp.WriteJ(P, d);
                Sent.Remove(login);   // their view changed: send it again on the next push
            }
        }

        static int Flush(string key)
        {
            List<KeyValuePair<string, JObject>> todo;
            lock (L) todo = ((JObject)Doc()["processed"]).Properties().Where(p => (bool?)p.Value["posted"] != true).Select(p => new KeyValuePair<string, JObject>(p.Name, (JObject)p.Value.DeepClone())).ToList();
            int sent = 0;
            foreach (var kv in todo)
            {
                var o = kv.Value; string lg = (string)o["login"];
                JObject r; int code = SiteHttp.Call("POST", "/api/bot/economy/answers", new JObject { { "id", kv.Key }, { "status", o["status"] }, { "message", o["message"] }, { "balance", Economy.Balance(lg) }, { "owed", Economy.LoanOwed(lg) } }, key, out r);
                if (code == 401) { _result = "site refused the key (HTTP 401)"; return sent; }
                if (code == 0 || code >= 500 || code == 429) continue;
                lock (L) { var d = Doc(); var e = ((JObject)d["processed"])[kv.Key] as JObject; if (e == null) continue; e["posted"] = true; e["http"] = code; SiteHttp.WriteJ(P, d); if (code == 200) sent++; else Clog.Warn("economy", "answer for " + kv.Key + " not accepted (HTTP " + code + ")"); }
            }
            return sent;
        }
    }
}
