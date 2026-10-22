using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The channel-point TIMEOUT reward. The redeemer types a name; the closest RECENT chatter (edit distance + substring/token overlap) is timed out.
    /// Mods, the broadcaster, bots (and VIPs when protectVip is on) cannot be timed out by it: the redeemer gets the timeout instead ("You can't do that!") and
    /// ChattyPinguino says one short, freshly generated fail line. Valid flow: wait 1-5 s, timeout with "Sorry! (redeemer) redeemed your timeout! D:", 1-2 s later
    /// Chatty says "(target) has been timed out by (redeemer)". The timeout itself is done by PinguinoHelper, then PinguinoBot, then the streamer account (first that works);
    /// every chat line comes from Chatty and goes through HostApi.SendAs, so the 30 s duplicate guard applies. Settings: Data\runtime\timeout_reward.json (created on first use).</summary>
    public static class TimeoutReward
    {
        static readonly object L = new object();
        static readonly Dictionary<string, DateTime> _cool = new Dictionary<string, DateTime>();
        static readonly List<string> _lines = new List<string>();   // Chatty's recent fail lines (prompt context + no repeats)
        static readonly Random Rnd = new Random();
        public static string LastResult = "";
        static string P { get { return Path.Combine(HostApi.DataDir, "timeout_reward.json"); } }

        public static JObject Config()
        {
            var d = new JObject { { "enabled", true }, { "title", "Timeout" }, { "seconds", 60 }, { "cooldownSec", 0 }, { "userCooldownSec", 0 }, { "recentHours", 6 }, { "minScore", 0.7 },
                { "protectVip", false }, { "refund", true }, { "ai", true }, { "actors", new JArray { "helper", "core", "streamer" } } };
            try
            {
                if (File.Exists(P)) { var u = JObject.Parse(File.ReadAllText(P)); foreach (var kv in u) d[kv.Key] = kv.Value; }
                else File.WriteAllText(P, d.ToString());
            }
            catch (Exception) { }
            return d;
        }

        // ------------------------------------------------------------------ fuzzy matching
        public class Cand { public string Login, Name; public int Role; public bool Sub; public long Last; public double Score; }

        public static string Norm(string s) { return Regex.Replace((s ?? "").ToLowerInvariant().TrimStart('@'), "[^a-z0-9]", ""); }

        /// <summary>Damerau (adjacent swaps count 1) edit distance of q against the best-fitting piece of c (a typo'd part of a longer name).</summary>
        static int Approx(string q, string c)
        {
            int n = q.Length, m = c.Length; if (n == 0) return 0;
            var d = new int[n + 1, m + 1];
            for (int i = 0; i <= n; i++) d[i, 0] = i;
            for (int j = 0; j <= m; j++) d[0, j] = 0;   // free start inside c
            for (int i = 1; i <= n; i++)
                for (int j = 1; j <= m; j++)
                {
                    int cost = q[i - 1] == c[j - 1] ? 0 : 1;
                    int v = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + cost);
                    if (i > 1 && j > 1 && q[i - 1] == c[j - 2] && q[i - 2] == c[j - 1]) v = Math.Min(v, d[i - 2, j - 2] + 1);
                    d[i, j] = v;
                }
            int best = int.MaxValue; for (int j = 0; j <= m; j++) best = Math.Min(best, d[n, j]); return best;
        }
        static int Whole(string a, string b)
        {
            var d = new int[a.Length + 1, b.Length + 1];
            for (int i = 0; i <= a.Length; i++) d[i, 0] = i; for (int j = 0; j <= b.Length; j++) d[0, j] = j;
            for (int i = 1; i <= a.Length; i++)
                for (int j = 1; j <= b.Length; j++)
                {
                    int v = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1));
                    if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) v = Math.Min(v, d[i - 2, j - 2] + 1);
                    d[i, j] = v;
                }
            return d[a.Length, b.Length];
        }
        /// <summary>0..1 how well what the redeemer typed fits one chatter name (login or display name).</summary>
        public static double Score(string typed, string name)
        {
            string q = Norm(typed), c = Norm(name); if (q.Length < 2 || c.Length < 2) return 0;
            if (q == c) return 1.0;
            double best = 0;
            double whole = 1.0 - (double)Whole(q, c) / Math.Max(q.Length, c.Length); best = Math.Max(best, whole * 0.95);   // a typo'd whole name
            if (q.Length >= 3)
            {
                if (c.Contains(q)) best = Math.Max(best, Math.Min(0.95, 0.76 + 0.2 * q.Length / c.Length + (c.StartsWith(q) ? 0.04 : 0)));   // "marsh" in lvlmarshmello
                if (q.Length >= 4 && q.Contains(c) && c.Length >= 4) best = Math.Max(best, 0.8);                                            // typed a bit more than the name
                if (q.Length >= 4)
                {
                    int ed = Approx(q, c);
                    if (ed <= Math.Max(1, q.Length / 4)) best = Math.Max(best, 0.9 * (1.0 - (double)ed / q.Length));                       // "marhsmello" ~ ...marshmello
                }
            }
            return best;
        }
        /// <summary>The best recent chatter for what was typed, or null (nothing above minScore, or two different people tie).</summary>
        public static Cand Match(string typed, IEnumerable<Cand> pool, double minScore, string exclude, out string why)
        {
            why = ""; var list = new List<Cand>();
            foreach (var c in pool)
            {
                if (c.Login == exclude) continue;
                c.Score = Math.Max(Score(typed, c.Login), Score(typed, c.Name));
                if (c.Score >= minScore) list.Add(c);
            }
            if (list.Count == 0) { why = "nobody close enough"; return null; }
            list = list.OrderByDescending(c => c.Score).ThenByDescending(c => c.Last).ToList();
            if (list.Count > 1 && list[0].Score < 1.0 && list[0].Score - list[1].Score < 0.03) { why = "ambiguous: " + list[0].Login + " / " + list[1].Login; return null; }
            return list[0];
        }

        // ------------------------------------------------------------------ the reward
        static bool Sim { get { return HostApi.SimMode; } }
        static int Wait(int minMs, int maxMs) { int ms = Rnd.Next(minMs, maxMs + 1); if (Sim && Environment.GetEnvironmentVariable("PINGUINO_TIMEOUT_FAST") == "1") ms = Math.Max(10, ms / 50); Thread.Sleep(ms); return ms; }
        static void Out(string s) { if (Sim) Console.WriteLine("[timeout-reward] " + s); Clog.Info("timeout-reward", s); }
        static void ChattySay(string text)
        {
            if (Sim) { if (!HostApi.SaidRecently(text)) Console.WriteLine("[say] " + text); return; }
            string via; HostApi.SendAs("chat", text, out via);
        }

        public static void OnRedeem(Dictionary<string, object> args)
        {
            object t; if (!args.TryGetValue("title", out t)) return;
            var cfg = Config(); if ((bool?)cfg["enabled"] == false) return;
            if (!string.Equals((string)t, (string)cfg["title"] ?? "Timeout", StringComparison.OrdinalIgnoreCase)) return;
            string who = Convert.ToString(args.ContainsKey("userName") ? args["userName"] : ""), typed = Convert.ToString(args.ContainsKey("input") ? args["input"] : "");
            string rid = Convert.ToString(args.ContainsKey("redemptionId") ? args["redemptionId"] : ""), rw = Convert.ToString(args.ContainsKey("rewardId") ? args["rewardId"] : "");
            Task.Run(() => { try { Handle(cfg, who, typed, rid, rw); } catch (Exception ex) { Clog.Warn("timeout-reward", "failed: " + ex.Message); } });
        }

        public static string Handle(JObject cfg, string redeemer, string typed, string redemptionId, string rewardId)
        {
            string rlogin = Norm(redeemer); var roster = Roster.Recent((double?)cfg["recentHours"] ?? 6);
            string rname = roster.Where(r => r.Item1 == rlogin).Select(r => r.Item2).FirstOrDefault() ?? redeemer;
            Action refund = () => { if ((bool?)cfg["refund"] != false && !Sim && redemptionId != "") Redeems.Cancel(redemptionId, rewardId); };
            // cooldowns of the reward (global + per user), seconds; a redeem inside one is refunded without a word
            int g = (int?)cfg["cooldownSec"] ?? 0, u = (int?)cfg["userCooldownSec"] ?? 0;
            lock (L)
            {
                var now = DateTime.UtcNow; DateTime d;
                if ((g > 0 && _cool.TryGetValue("*", out d) && (now - d).TotalSeconds < g) || (u > 0 && _cool.TryGetValue(rlogin, out d) && (now - d).TotalSeconds < u))
                { refund(); return Done("cooldown, refunded"); }
                _cool["*"] = now; _cool[rlogin] = now;
            }
            var pool = roster.Select(r => new Cand { Login = r.Item1, Name = r.Item2, Role = r.Item3, Sub = r.Item4, Last = r.Item5 }).ToList();
            string why; var hit = Match(typed, pool, (double?)cfg["minScore"] ?? 0.7, rlogin, out why);
            if (hit == null)
            {
                refund(); ChattySay("@" + rname + " nobody in chat matched \"" + Clip(typed, 24) + "\", so no timeout (points back).");
                return Done("no match (" + why + ") for '" + typed + "', refunded");
            }
            string tname = hit.Name ?? hit.Login;
            int secs = Math.Max(1, Math.Min(1209600, (int?)cfg["seconds"] ?? 60));
            var actors = (cfg["actors"] as JArray ?? new JArray()).Select(a => (string)a).ToList(); if (actors.Count == 0) actors = new List<string> { "helper", "core", "streamer" };
            bool protect = hit.Role >= 3 || Boards.IsBot(hit.Login) || Boards.AllBots().Contains(hit.Login) || ((bool?)cfg["protectVip"] == true && hit.Role >= 2) || IsLiveMod(hit.Login);
            if (protect)
            {
                Out(tname + " cannot be timed out by the reward: timing out " + rname + " instead");
                Thread.Sleep(Sim ? 10 : 1000);
                string by = Ban(actors, rlogin, secs, "You can't do that!");
                ChattySay(FailLine(cfg, rname, tname));
                return Done("protected target " + hit.Login + "; redeemer " + rlogin + " timed out by " + (by ?? "nobody (could not)"));
            }
            Wait(1000, 5000);
            string who2 = Ban(actors, hit.Login, secs, "Sorry! " + redeemer + " redeemed your timeout! D:");
            if (who2 == null) { refund(); ChattySay("@" + rname + " I couldn't time out " + tname + " (no mod rights?), points back."); return Done("could not time out " + hit.Login + ", refunded"); }
            Wait(1000, 2000);
            ChattySay(tname + " has been timed out by " + rname);
            return Done("timed out " + hit.Login + " " + secs + " s via " + who2 + " (score " + hit.Score.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture) + ")");
        }
        static string Done(string s) { LastResult = s; Out(s); return s; }
        static string Clip(string s, int n) { s = Regex.Replace(s ?? "", @"\s+", " ").Trim(); return s.Length > n ? s.Substring(0, n) : s; }

        // ------------------------------------------------------------------ who does the timeout
        /// <summary>Tries each actor in order (helper, core = PinguinoBot, streamer = Ivan) until one succeeds. Returns the actor that did it, or null.</summary>
        public static string Ban(List<string> actors, string login, int secs, string reason)
        {
            foreach (string a in actors)
            {
                bool ok;
                try { ok = Sim ? SimBan(a, login, secs, reason) : RealBan(a, login, secs, reason); } catch (Exception ex) { Clog.Warn("timeout-reward", a + " failed: " + ex.Message); ok = false; }
                if (ok) return a;
                Out(a + " could not time out " + login + ", trying the next");
            }
            return null;
        }
        static bool SimBan(string actor, string login, int secs, string reason)
        {
            var fail = (Environment.GetEnvironmentVariable("PINGUINO_TIMEOUT_FAIL") ?? "").Split(',');
            if (fail.Contains(actor)) return false;
            Console.WriteLine("[timeout-do] actor=" + actor + " user=" + login + " secs=" + secs + " reason=" + reason); return true;
        }
        static bool IsLiveMod(string login)
        {
            if (Sim) return (Environment.GetEnvironmentVariable("PINGUINO_TIMEOUT_MODS") ?? "").Split(',').Contains(login);
            try
            {
                string err; string uid = TwitchApi.UserId(login, out err); if (uid == "") return false;
                JToken d; TwitchApi.Call(HttpMethod.Get, "/moderation/moderators?broadcaster_id={bid}&user_id=" + uid, null, out d, out err);
                return (d as JArray)?.Count > 0;
            }
            catch (Exception) { return false; }
        }
        static bool RealBan(string actor, string login, int secs, string reason)
        {
            string err; string uid = TwitchApi.UserId(login, out err); if (uid == "") { Clog.Warn("timeout-reward", "no Twitch id for " + login + ": " + err); return false; }
            var body = new JObject { { "data", new JObject { { "user_id", uid }, { "duration", secs }, { "reason", reason.Length > 500 ? reason.Substring(0, 500) : reason } } } };
            if (actor == "streamer")
            {
                JToken d; string code = TwitchApi.Call(HttpMethod.Post, "/moderation/bans?broadcaster_id={bid}&moderator_id=" + TwitchApi.BroadcasterId(), body, out d, out err);
                if (code != "200") Clog.Warn("timeout-reward", "streamer account could not time out (HTTP " + code + "): " + err);
                return code == "200";
            }
            return HostApi.BotBan(actor, body);
        }

        // ------------------------------------------------------------------ Chatty's fail line
        static readonly string[] Templates = {
            "{u} blundered! Moderators are off limits.", "{u} tried to time out a mod. Bold. Wrong.", "Oops, {u} picked the wrong penguin!", "{u} just timed out themself. Bravo.",
            "Mods are protected, {u}. Enjoy the nap!", "{u} aimed high and hit themself.", "{u} blundered hard. The mods wave goodbye.", "Nice try {u}, enjoy the timeout!",
            "{u} challenged a mod and lost.", "{u} blundered into a mod-shaped wall.", "That backfired fast, {u}.", "{u} should have checked the badge first." };

        public static string FailLine(JObject cfg, string redeemer, string target)
        {
            string line = null;
            if ((bool?)cfg["ai"] != false && !Sim) { try { line = AiLine(redeemer, target); } catch (Exception ex) { Clog.Warn("timeout-reward", "AI line failed: " + ex.Message); } }
            if (line == null)
            {
                var fresh = Templates.Where(t => !Seen(t.Replace("{u}", redeemer))).ToList(); if (fresh.Count == 0) fresh = Templates.ToList();
                line = fresh[Rnd.Next(fresh.Count)].Replace("{u}", redeemer);
            }
            lock (_lines) { _lines.Add(line); while (_lines.Count > 12) _lines.RemoveAt(0); }
            return line;
        }
        static bool Seen(string l) { string n = Norm(l); lock (_lines) return _lines.Any(x => Norm(x) == n); }
        static int Words(string s) { return Regex.Matches(s ?? "", @"\S+").Count; }
        static string AiLine(string redeemer, string target)
        {
            List<string> recent; lock (_lines) recent = _lines.ToList();
            string sys = "You are ChattyPinguino, a cheeky penguin in a Twitch chat. Write ONE short fail-style line (under 15 words, no quotes, no hashtags, at most one emoji) about a viewer who just blundered. Never reuse wording of these earlier lines: "
                + (recent.Count == 0 ? "(none)" : string.Join(" | ", recent)) + ". Output only the line.";
            string usr = redeemer + " spent channel points to time out " + target + ", but " + target + " is a moderator, so " + redeemer + " got timed out instead. Mention " + redeemer + " by name.";
            for (int i = 0; i < 2; i++)
            {
                string l = Gpt.Ask(sys, usr + (i > 0 ? " (Be different and shorter.)" : "")); if (l == null) return null;
                l = Regex.Replace(l.Trim().Trim('"'), @"\s+", " ");
                if (l == "" || l.Length > 120 || Words(l) >= 15 || !l.ToLowerInvariant().Contains(Norm(redeemer).Length > 0 ? redeemer.ToLowerInvariant() : "") || Seen(l)) continue;
                return l;
            }
            return null;
        }
    }

    /// <summary>One-shot completions with the same provider/key as ChattyPinguino (Data\runtime\chat_settings.json: Provider claude|openai|custom, ApiKey, Model, BaseUrl). The key is never logged.</summary>
    public static class Gpt
    {
        public static string Ask(string system, string user)
        {
            var c = new JObject(); try { c = JObject.Parse(File.ReadAllText(Path.Combine(HostApi.DataDir, "chat_settings.json"))); } catch (Exception) { }
            string key = (string)c["ApiKey"] ?? ""; if (key.Trim() == "") return null;
            string prov = ((string)c["Provider"] ?? "openai").ToLowerInvariant(), model = (string)c["Model"] ?? "", bu = ((string)c["BaseUrl"] ?? "").TrimEnd('/');
            using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(15) })
            {
                HttpRequestMessage rq; Func<JObject, string> pick;
                if (prov == "claude")
                {
                    rq = new HttpRequestMessage(HttpMethod.Post, (bu == "" ? "https://api.anthropic.com" : bu) + "/v1/messages");
                    rq.Headers.Add("x-api-key", key); rq.Headers.Add("anthropic-version", "2023-06-01");
                    rq.Content = new StringContent(new JObject { { "model", model == "" ? "claude-haiku-5-5" : model }, { "max_tokens", 200 }, { "system", system }, { "messages", new JArray { new JObject { { "role", "user" }, { "content", user } } } } }.ToString(), Encoding.UTF8, "application/json");
                    pick = j => string.Concat((j["content"] as JArray ?? new JArray()).Select(b => (string)b["text"]));
                }
                else
                {
                    rq = new HttpRequestMessage(HttpMethod.Post, (bu == "" ? "https://api.openai.com/v1" : bu) + "/chat/completions");
                    rq.Headers.Add("Authorization", "Bearer " + key);
                    rq.Content = new StringContent(new JObject { { "model", model == "" ? "gpt-4o-mini" : model }, { "max_tokens", 200 }, { "messages", new JArray { new JObject { { "role", "system" }, { "content", system } }, new JObject { { "role", "user" }, { "content", user } } } } }.ToString(), Encoding.UTF8, "application/json");
                    pick = j => (string)j["choices"]?[0]?["message"]?["content"];
                }
                var r = h.SendAsync(rq).Result; if (!r.IsSuccessStatusCode) { Clog.Warn("timeout-reward", "AI provider answered HTTP " + (int)r.StatusCode); return null; }
                return pick(JObject.Parse(r.Content.ReadAsStringAsync().Result));
            }
        }
    }

    public static partial class HostApi
    {
        /// <summary>A timeout done by one of the bots' own sign-ins (role helper|core|chat) when that bot is enabled and its token may moderate; false otherwise (the caller tries the next one).</summary>
        public static bool BotBan(string role, JObject body)
        {
            var reg = LoadFile("bots.json"); var sec = BotSecretsV(); var bot = reg["Bots"]?[role]; var s = sec[role] as JObject;
            if (bot == null || (bool?)bot["Enabled"] == false || s == null) return false;
            string tok = (string)s["UserToken"], cid = (string)s["ClientId"], sid = (string)s["SenderId"], bid = (string)s["BroadcasterId"];
            if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid) || string.IsNullOrEmpty(sid) || string.IsNullOrEmpty(bid)) return false;
            using (var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
            {
                var rq = new HttpRequestMessage(HttpMethod.Post, Helix + "/moderation/bans?broadcaster_id=" + bid + "&moderator_id=" + sid); rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                rq.Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json");
                var resp = http.SendAsync(rq).Result; if (!resp.IsSuccessStatusCode) Clog.Warn("timeout-reward", role + " could not time out (HTTP " + (int)resp.StatusCode + ")");
                return resp.IsSuccessStatusCode;
            }
        }
    }
}
