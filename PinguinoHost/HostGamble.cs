using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Chat games played with points: !gamble &lt;amount|all&gt;, !slots &lt;amount|all&gt;, !duel @user &lt;amount&gt; + !accept, !give @user &lt;amount&gt;.
    /// Every number lives in Data\economy\gambling.json, re-read whenever the file changes (no restart). There is no maximum bet unless "maxBet" is set above 0.
    /// Money moves only through Economy.Spend / Economy.Credit with unique ids, so a retry never pays twice.</summary>
    public static class Gamble
    {
        static readonly object L = new object(); static readonly Random Rng = new Random();
        static JObject _cfg; static DateTime _cfgAt = DateTime.MinValue;
        static string CfgP { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); string root = string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d; var dir = Path.Combine(root, "economy"); Directory.CreateDirectory(dir); return Path.Combine(dir, "gambling.json"); } }
        public static JObject Defaults()
        {
            return new JObject { { "enabled", true }, { "cooldownSec", 15 }, { "minBet", 1 }, { "maxBet", 0 },
                { "gambleWinChance", 0.45 }, { "gamblePayout", 2.0 },
                { "slotsEnabled", true }, { "slotsSymbols", new JArray("🍒", "🐟", "⭐", "⚽", "🐧") }, { "slotsPairPayout", 1.5 }, { "slotsTriplePayout", 5.0 }, { "slotsJackpotSymbol", "🐧" }, { "slotsJackpotPayout", 10.0 },
                { "slotsSymbolPayouts", new JObject { { "🍒", 2.0 }, { "🐟", 3.0 }, { "⭐", 4.0 }, { "⚽", 6.0 }, { "🐧", 11.0 } } },   // three of a kind pays this x the bet, per symbol (Docs/SLOTS_TABLE.md, about 92.8% back); {} = use slotsTriplePayout / slotsJackpotPayout for every symbol
                { "duelEnabled", true }, { "duelTimeoutSec", 60 }, { "duelHouseCutPercent", 0 },
                { "giveEnabled", true }, { "giveMin", 1 }, { "giveDailyPct", 10 }, { "giveDailyMin", 0 }, { "giveDailyMax", 0 } };
        }
        public static JObject Config()
        {
            lock (L)
            {
                string p = CfgP; DateTime t = File.Exists(p) ? File.GetLastWriteTimeUtc(p) : DateTime.MinValue;
                if (_cfg != null && t == _cfgAt) return _cfg;
                var d = Defaults();
                try { if (File.Exists(p)) foreach (var kv in JObject.Parse(File.ReadAllText(p, Encoding.UTF8))) d[kv.Key] = kv.Value; else File.WriteAllText(p, d.ToString(), new UTF8Encoding(false)); } catch (Exception ex) { Clog.Warn("gamble", "gambling.json unreadable, using defaults: " + ex.Message); }
                _cfg = d; _cfgAt = File.Exists(p) ? File.GetLastWriteTimeUtc(p) : DateTime.MinValue; return d;
            }
        }
        public static void SaveConfig(JObject patch)
        {
            lock (L) { var c = Config(); foreach (var kv in patch) if (c[kv.Key] != null) c[kv.Key] = kv.Value; File.WriteAllText(CfgP, c.ToString(), new UTF8Encoding(false)); _cfgAt = File.GetLastWriteTimeUtc(CfgP); }
        }
        static double N(string k, double d) { var t = Config()[k]; try { return t == null ? d : (double)t; } catch (Exception) { return d; } }
        static bool B(string k) { var t = Config()[k]; return t == null || (bool)t; }

        public static bool IsCommand(string c) { return c == "!gamble" || c == "!bet" || c == "!slots" || c == "!duel" || c == "!accept" || c == "!decline" || c == "!give"; }

        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();
        static bool Cooling(string user) { lock (Cool) { DateTime t; double sec = N("cooldownSec", 15); if (Cool.TryGetValue(user, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; Cool[user] = DateTime.UtcNow; return false; } }
        static void Uncool(string user) { lock (Cool) Cool.Remove(user); }

        class Duel { public string From, To; public long Amount; public DateTime At; }
        static readonly Dictionary<string, Duel> Duels = new Dictionary<string, Duel>();   // by challenged login

        // bet text -> amount; null = not understood
        static long? Amount(string a, long bal)
        {
            if (a == null) return null; a = a.Trim().ToLowerInvariant();
            if (a == "all" || a == "allin") return bal;
            if (a.EndsWith("%")) { double pc; if (double.TryParse(a.TrimEnd('%'), NumberStyles.Float, CultureInfo.InvariantCulture, out pc) && pc > 0 && pc <= 100) return (long)Math.Floor(bal * pc / 100); return null; }
            double v; if (double.TryParse(a.Replace(",", ""), NumberStyles.Float, CultureInfo.InvariantCulture, out v) && v >= 1 && v < 1e12) return (long)Math.Floor(v); return null;
        }
        static string Check(string login, long amt, long bal)
        {
            string cur = Economy.CurrencyName; long min = (long)N("minBet", 1), max = (long)N("maxBet", 0);
            if (bal < 1) return "you have no " + cur + ".";
            if (amt < Math.Max(1, min)) return "the minimum is " + Math.Max(1, min) + " " + cur + ".";
            if (max > 0 && amt > max) return "the maximum bet is " + max + " " + cur + ".";
            if (amt > bal) return "you only have " + bal + " " + cur + ".";
            return null;
        }
        static string Id(string kind, string who) { return kind + "-" + who + "-" + Guid.NewGuid().ToString("N").Substring(0, 12); }
        static string Canon(string s) { return (s ?? "").Trim().TrimStart('@').ToLowerInvariant(); }

        // ---- one door for every result line: Chatty speaks it (PgGame event) when it can post, otherwise the plain Host line. Never both. ----
        static long _csStamp = -1; static bool _csOk = true;
        /// <summary>Chatty can post when chat_settings.json has Enabled, ChatReplies and GameVoice on (a missing key means on, as in Chatty).</summary>
        public static bool ChattyCanPost()
        {
            try
            {
                string p = Path.Combine(HostApi.DataDir, "chat_settings.json"); long st = File.Exists(p) ? new FileInfo(p).LastWriteTimeUtc.Ticks : 0;
                lock (L)
                {
                    if (st != _csStamp)
                    {
                        bool ok = true;
                        if (st != 0) { var j = JObject.Parse(File.ReadAllText(p, Encoding.UTF8).TrimStart((char)0xFEFF)); foreach (var k in new[] { "Enabled", "ChatReplies", "GameVoice" }) if (j[k] != null && j[k].Type == JTokenType.Boolean && !(bool)j[k]) ok = false; }
                        _csOk = ok; _csStamp = st;
                    }
                    return _csOk;
                }
            }
            catch (Exception) { return true; }
        }
        public static readonly List<JObject> Sent = new List<JObject>();   // the last PgGame events (for tests and the Suite), newest last
        public static void GameOut(Action<string> say, string plain, string kind, string outcome, string user, long amount = 0, long payout = 0, long balance = 0, string opponent = "", string reel = "", string reason = "", string gameId = "", int timeoutSec = 0, string item = "", int tries = 0)
        {
            Out(say, plain, kind, outcome, user, amount, payout, balance, opponent, reel, reason, gameId, timeoutSec, item, tries);
        }
        static void Out(Action<string> say, string plain, string kind, string outcome, string user, long amount = 0, long payout = 0, long balance = 0, string opponent = "", string reel = "", string reason = "", string gameId = "", int timeoutSec = 0, string item = "", int tries = 0)
        {
            try { AlertBridge.OnGame(kind, outcome, (user ?? "").ToLowerInvariant(), user, amount, payout, opponent, item, gameId); } catch (Exception) { }   // Multi alert (off by EmitHypeTip=false), whatever the chat voice does
            if (!ChattyCanPost()) { say(plain); return; }
            string login = (user ?? "").ToLowerInvariant();
            bool opt = false; try { opt = SiteShop.OptedOutNow(login); } catch (Exception) { }
            var a = new Dictionary<string, object> {
                { "eventType", "PgGame" }, { "kind", kind }, { "outcome", outcome }, { "user", login }, { "display", user ?? "" }, { "amount", amount.ToString(CultureInfo.InvariantCulture) }, { "payout", payout.ToString(CultureInfo.InvariantCulture) },
                { "balance", balance.ToString(CultureInfo.InvariantCulture) }, { "opponent", opponent ?? "" }, { "reel", reel ?? "" }, { "reason", reason ?? "" }, { "currency", Economy.CurrencyName },
                { "timeoutSec", timeoutSec.ToString(CultureInfo.InvariantCulture) }, { "item", item ?? "" }, { "tries", tries.ToString(CultureInfo.InvariantCulture) }, { "optout", opt ? "1" : "" }, { "gameId", string.IsNullOrEmpty(gameId) ? Guid.NewGuid().ToString("N") : gameId } };
            lock (Sent) { var o = new JObject(); foreach (var kv in a) o[kv.Key] = Convert.ToString(kv.Value, CultureInfo.InvariantCulture); Sent.Add(o); if (Sent.Count > 50) Sent.RemoveAt(0); }
            if (HostApi.SimMode) { Console.WriteLine("[pggame] " + Newtonsoft.Json.JsonConvert.SerializeObject(a, Newtonsoft.Json.Formatting.None)); return; }
            System.Threading.Tasks.Task.Run(() => { try { Program.DispatchEvent(a); } catch (Exception ex) { Clog.Warn("gamble", "PgGame event failed, plain line sent: " + ex.Message); try { say(plain); } catch (Exception) { } } });
        }
        static string Reel(string[] r) { return string.Join(" ", r); }

        // ---- !give / site Give: one door, one set of rules ----
        static string GiveP { get { return Path.Combine(HostApi.DataDir, "economy", "give_daily.json"); } }
        static string GiveDay() { return DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture); }
        public static double GivePct() { return Math.Max(0, N("giveDailyPct", 10)); }
        /// <summary>what this person may give per stream: giveDailyPct % of their CURRENT balance (rounded down), at least giveDailyMin, at most giveDailyMax (0 = no cap). Live: it follows the balance, the counter does not shrink.</summary>
        public static long GiveLimit(string login)
        {
            long bal = Economy.Balance(Canon(login)); long lim = (long)Math.Floor(bal * GivePct() / 100.0);
            long min = (long)N("giveDailyMin", 0), max = (long)N("giveDailyMax", 0);
            if (lim < min) lim = min; if (max > 0 && lim > max) lim = max; return lim;
        }
        /// <summary>the counter belongs to a stream: a new stream id clears it; while offline it carries over</summary>
        static JObject GiveDoc()
        {
            JObject d = null; try { if (File.Exists(GiveP)) d = JObject.Parse(File.ReadAllText(GiveP, Encoding.UTF8)); } catch (Exception) { }
            string sid = Economy.StreamId();
            if (d == null || !(d["users"] is JObject) || (sid != "off" && (string)d["sid"] != sid)) d = new JObject { { "sid", sid == "off" ? "" : sid }, { "users", new JObject() } };
            return d;
        }
        public static long GiveToday(string login) { lock (L) { var u = GiveDoc()["users"] as JObject; return (long?)u[(login ?? "").ToLowerInvariant()] ?? 0; } }
        /// <summary>give points to someone: min, no self, no bots, balance, the per-stream cap (giveDailyPct % of the balance, see GiveLimit), unique ids. Returns {ok, error|message, balance, givenToday, limit}.</summary>
        public static JObject Give(string from, string to, long amount, string reqId = null)
        {
            string me = Canon(from), tl = Canon(to), cur = Economy.CurrencyName;
            Func<string, JObject> no = why => new JObject { { "ok", false }, { "error", why }, { "balance", Economy.Balance(me) }, { "givenToday", GiveToday(me) }, { "givenThisStream", GiveToday(me) }, { "limit", GiveLimit(me) }, { "pct", GivePct() } };
            if (!B("enabled") || !B("giveEnabled")) return no("giving points is switched off.");
            if (tl == "" || tl == me) return no("pick someone else to give to.");
            bool bot = false; try { bot = Boards.IsBot(tl); } catch (Exception) { }
            if (bot) return no("bots do not need " + cur + ".");
            if (amount < Math.Max(1, (long)N("giveMin", 1))) return no("the minimum is " + Math.Max(1, (long)N("giveMin", 1)) + " " + cur + ".");
            long bal = Economy.Balance(me); if (amount > bal) return no("you only have " + bal + " " + cur + ".");
            lock (L)
            {
                long lim = GiveLimit(me), given = GiveToday(me);
                if (given + amount > lim) return no(given >= lim ? "you have given " + given.ToString("N0", CultureInfo.InvariantCulture) + " this stream and the limit is " + lim.ToString("N0", CultureInfo.InvariantCulture) + " " + cur + " (" + GivePct().ToString("0.##", CultureInfo.InvariantCulture) + "% of what you have), try again next stream." : "you can give " + lim.ToString("N0", CultureInfo.InvariantCulture) + " " + cur + " per stream (" + GivePct().ToString("0.##", CultureInfo.InvariantCulture) + "% of what you have), you have given " + given.ToString("N0", CultureInfo.InvariantCulture) + " so " + (lim - given).ToString("N0", CultureInfo.InvariantCulture) + " is left.");
                string id = reqId != null ? "give-" + reqId : Id("give", me);
                string err = Economy.Spend(id, me, amount, "give to " + tl); if (err != null) return no(err + ".");
                Economy.Credit(id + "-in", tl, amount, "given by " + me);
                var d = GiveDoc(); var u = (JObject)d["users"]; u[me] = ((long?)u[me] ?? 0) + amount;
                try { Directory.CreateDirectory(Path.GetDirectoryName(GiveP)); File.WriteAllText(GiveP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
                return new JObject { { "ok", true }, { "message", "gave " + amount + " " + cur + " to " + Boards.DisplayName(tl) }, { "balance", Economy.Balance(me) }, { "givenToday", (long)u[me] }, { "givenThisStream", (long)u[me] }, { "limit", lim }, { "pct", GivePct() }, { "id", id } };
            }
        }

        public static void Handle(string user, string cmd, string[] args, Action<string> say)
        {
            try
            {
                string me = user.ToLowerInvariant(), cur = Economy.CurrencyName;
                if (!B("enabled")) return;
                if (cmd == "!bet") cmd = "!gamble";
                string kd = cmd == "!slots" ? "slots" : cmd == "!give" ? "give" : cmd == "!duel" || cmd == "!accept" || cmd == "!decline" ? "duel" : "gamble";
                if (cmd == "!decline") { Duel d; lock (Duels) { if (Duels.TryGetValue(me, out d)) Duels.Remove(me); } if (d != null) Out(say, "@" + d.From + " " + user + " passed on the duel.", "duel", "declined", user, d.Amount, 0, Economy.Balance(me), d.From); return; }
                if (cmd == "!accept") { Accept(user, say); return; }
                if (Cooling(me)) return;
                long bal = Economy.Balance(me);
                Action<string> bad = why => Out(say, "@" + user + " " + why, kd, bal < 1 ? "broke" : "invalid", user, 0, 0, bal, "", "", why);
                if (cmd == "!gamble" || cmd == "!slots")
                {
                    if (cmd == "!slots" && !B("slotsEnabled")) return;
                    var a = Amount(args.Length > 0 ? args[0] : null, bal);
                    if (a == null) { Uncool(me); bad("usage: " + cmd + " <amount|all>"); return; }
                    string why = Check(me, a.Value, bal); if (why != null) { Uncool(me); bad(why); return; }
                    string id = Id(cmd.Substring(1), me); string err = Economy.Spend(id, me, a.Value, cmd.Substring(1) + " bet"); if (err != null) { Uncool(me); bad(err + "."); return; }
                    if (cmd == "!gamble") Gam(user, me, a.Value, id, say); else Slots(user, me, a.Value, id, say);
                    return;
                }
                if (cmd == "!give")
                {
                    if (!B("giveEnabled")) return;
                    if (args.Length < 2) { Uncool(me); bad("usage: !give @user <amount>"); return; }
                    string to = Canon(args[0]); var a = Amount(args[1], bal);
                    if (a == null) { Uncool(me); bad("usage: !give @user <amount>"); return; }
                    var gr = Give(me, to, a.Value);
                    if ((bool?)gr["ok"] != true) { Uncool(me); bad((string)gr["error"]); return; }
                    Out(say, "@" + user + " gave " + a.Value + " " + cur + " to " + Boards.DisplayName(to) + ". Thank you for sharing!", "give", "win", user, a.Value, a.Value, Economy.Balance(me), Boards.DisplayName(to), "", "", (string)gr["id"]); return;
                }
                if (cmd == "!duel")
                {
                    if (!B("duelEnabled")) return;
                    if (args.Length < 2) { Uncool(me); bad("usage: !duel @user <amount>"); return; }
                    string to = Canon(args[0]); var a = Amount(args[1], bal);
                    if (to == "" || to == me) { Uncool(me); bad("pick someone else to duel."); return; }
                    if (a == null) { Uncool(me); bad("usage: !duel @user <amount>"); return; }
                    string why = Check(me, a.Value, bal); if (why != null) { Uncool(me); bad(why); return; }
                    lock (Duels) Duels[to] = new Duel { From = me, To = to, Amount = a.Value, At = DateTime.UtcNow };
                    int tsec = (int)N("duelTimeoutSec", 60);
                    Out(say, "@" + to + " " + user + " challenges you to a duel for " + a.Value + " " + cur + "! Type !accept within " + tsec + "s.", "duel", "challenge", user, a.Value, 0, bal, to, "", "", "", tsec);
                }
            }
            catch (Exception ex) { Clog.Warn("gamble", "command failed: " + ex.Message); }
        }

        static void Gam(string user, string me, long amt, string id, Action<string> say)
        {
            string cur = Economy.CurrencyName; bool win = Rng.NextDouble() < N("gambleWinChance", 0.45); double mult = N("gamblePayout", 2.0);
            if (win) { long pay = (long)Math.Floor(amt * mult); Economy.Credit(id + "-win", me, pay, "gamble win"); long nb = Economy.Balance(me); Out(say, "@" + user + " you won " + (pay - amt) + " " + cur + "! You now have " + nb + ".", "gamble", "win", user, amt, pay, nb, "", "", "", id); }
            else { long nb = Economy.Balance(me); Out(say, "@" + user + " you lost " + amt + " " + cur + ". Now at " + nb + ". Thanks for playing!", "gamble", "lose", user, amt, 0, nb, "", "", "", id); }
        }
        /// <summary>payout multiplier of one spin: three of a kind = that symbol's slotsSymbolPayouts value (else slotsJackpotPayout for the jackpot symbol / slotsTriplePayout), any pair = slotsPairPayout. jackpot = three of the jackpot symbol.</summary>
        public static double SlotMult(string[] r, out bool jackpot)
        {
            jackpot = false; var c = Config();
            if (r[0] == r[1] && r[1] == r[2])
            {
                jackpot = r[0] == ((string)c["slotsJackpotSymbol"] ?? ""); var tb = c["slotsSymbolPayouts"] as JObject; JToken v = tb == null ? null : tb[r[0]];
                if (v != null && (v.Type == JTokenType.Float || v.Type == JTokenType.Integer)) return (double)v;
                return jackpot ? N("slotsJackpotPayout", 10) : N("slotsTriplePayout", 5);
            }
            return r[0] == r[1] || r[1] == r[2] || r[0] == r[2] ? N("slotsPairPayout", 1.5) : 0;
        }
        static void Slots(string user, string me, long amt, string id, Action<string> say)
        {
            string cur = Economy.CurrencyName; var sym = (Config()["slotsSymbols"] as JArray ?? new JArray("a", "b", "c")).Select(x => (string)x).ToList(); if (sym.Count < 2) sym = new List<string> { "a", "b" };
            var r = new[] { sym[Rng.Next(sym.Count)], sym[Rng.Next(sym.Count)], sym[Rng.Next(sym.Count)] };
            bool jackpot; double mult = SlotMult(r, out jackpot);
            string reel = Reel(r);
            if (mult > 0) { long pay = (long)Math.Floor(amt * mult); Economy.Credit(id + "-win", me, pay, "slots win"); long nb = Economy.Balance(me); Out(say, "@" + user + " " + reel + " you won " + pay + " " + cur + "! You now have " + nb + ".", "slots", jackpot ? "jackpot" : "win", user, amt, pay, nb, "", reel, "", id); }
            else { long nb = Economy.Balance(me); Out(say, "@" + user + " " + reel + " no luck, lost " + amt + " " + cur + ". Thanks for playing!", "slots", "lose", user, amt, 0, nb, "", reel, "", id); }
        }
        static void Accept(string user, Action<string> say)
        {
            string me = user.ToLowerInvariant(), cur = Economy.CurrencyName; Duel d;
            lock (Duels) { if (!Duels.TryGetValue(me, out d)) return; Duels.Remove(me); }
            Action<string, string> no = (oc, why) => Out(say, "@" + user + " " + why, "duel", oc, user, d.Amount, 0, Economy.Balance(me), d.From, "", why);
            if ((DateTime.UtcNow - d.At).TotalSeconds > N("duelTimeoutSec", 60)) { no("expired", "that duel expired."); return; }
            string id = Id("duel", d.From);
            if (Economy.Balance(d.From) < d.Amount) { no("invalid", Boards.DisplayName(d.From) + " no longer has enough " + cur + "."); return; }
            if (Economy.Balance(me) < d.Amount) { no(Economy.Balance(me) < 1 ? "broke" : "invalid", "you only have " + Economy.Balance(me) + " " + cur + "."); return; }
            string e1 = Economy.Spend(id + "-a", d.From, d.Amount, "duel stake vs " + me); if (e1 != null) { no("invalid", "the duel fell through."); return; }
            string e2 = Economy.Spend(id + "-b", me, d.Amount, "duel stake vs " + d.From); if (e2 != null) { Economy.Credit(id + "-refund", d.From, d.Amount, "duel refund"); no("invalid", "the duel fell through."); return; }
            bool fromWins = Rng.Next(2) == 0; string win = fromWins ? d.From : me, lose = fromWins ? me : d.From;
            long pot = d.Amount * 2, cut = (long)Math.Floor(pot * N("duelHouseCutPercent", 0) / 100); long pay = pot - cut;
            Economy.Credit(id + "-win", win, pay, "duel win vs " + lose);
            Out(say, Boards.DisplayName(win) + " wins the duel against " + Boards.DisplayName(lose) + " and takes " + pay + " " + cur + "! GG.", "duel", "win", Boards.DisplayName(win), d.Amount, pay, Economy.Balance(win), Boards.DisplayName(lose), "", "", id);
        }

        /// <summary>Test-bet simulator for the Suite: runs `n` bets of `amount` on the current config without touching any balance.</summary>
        public static JObject Simulate(string game, long amount, int n)
        {
            n = Math.Max(1, Math.Min(n, 200000)); long net = 0; int wins = 0; double mult = 0;
            var sym = (Config()["slotsSymbols"] as JArray ?? new JArray("a", "b")).Select(x => (string)x).ToList(); string jp = (string)Config()["slotsJackpotSymbol"] ?? "";
            for (int i = 0; i < n; i++)
            {
                if (game == "slots")
                {
                    var r = new[] { sym[Rng.Next(sym.Count)], sym[Rng.Next(sym.Count)], sym[Rng.Next(sym.Count)] }; mult = 0;
                    bool jk; mult = SlotMult(r, out jk);
                }
                else mult = Rng.NextDouble() < N("gambleWinChance", 0.45) ? N("gamblePayout", 2.0) : 0;
                long pay = (long)Math.Floor(amount * mult); net += pay - amount; if (pay > 0) wins++;
            }
            return new JObject { { "ok", true }, { "game", game }, { "bets", n }, { "amount", amount }, { "wins", wins }, { "winRate", Math.Round((double)wins / n, 4) }, { "netPerBet", Math.Round((double)net / n, 3) }, { "net", net } };
        }
    }
}
