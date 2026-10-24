using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The "checkbook" for the site's Points page: one row per thing that happened to a person's balance, in the order it happened, each with its signed change and the
    /// balance right after it. Built from the economy ledger (every row already stores delta + balance-after). Gambling is folded into one row: the bet and the payout become a
    /// single "Won 500" / "Lost 200" (net of the bet), a duel is one row per player, and watch-time points (which have no ledger row) are shown as gap rows so the running balance never breaks.</summary>
    public static partial class Economy
    {
        /// <summary>peer-to-peer loan money: a ledger row with its own source and a unique id (a retry applies once; a short balance is refused)</summary>
        public static string AwardP2p(string login, long amount, string source, string note, string id) { if (amount == 0) return "nothing to move"; return Apply(id, login, amount, source, note); }
        public static bool HouseDefaulted(string login) { lock (L) { var ln = Loans()[Canon(Boards.AliasMap(), login)] as JObject; return ln != null && (bool?)ln["defaulted"] == true; } }

        // ---- "hide my page" was removed (2026-10-23): every points page is public again. Only the lore opt-out list still keeps a page private. ----
        static string HideP { get { return System.IO.Path.Combine(Dir, "hidden_pages.json"); } }
        /// <summary>one-time clean-up at start: the old per-viewer hidden flags are dated-backed-up and dropped. Returns how many flags were cleared.</summary>
        public static int ClearHiddenFlags()
        {
            try
            {
                if (!System.IO.File.Exists(HideP)) return 0;
                int n = 0; try { n = JArray.Parse(System.IO.File.ReadAllText(HideP, System.Text.Encoding.UTF8)).Count; } catch (Exception) { }
                string bak = HideP + ".before-unhide-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + ".bak";
                System.IO.File.Move(HideP, bak);
                Clog.Info("economy", "hide my page removed: " + n + " hidden flag(s) cleared (backup " + System.IO.Path.GetFileName(bak) + ")");
                return n;
            }
            catch (Exception ex) { Clog.Warn("economy", "could not clear hidden flags: " + ex.Message); return 0; }
        }
        public static bool PageHidden(string login)
        {
            string c = Canon(Boards.AliasMap(), login); try { return SiteShop.OptedOutNow(c); } catch (Exception) { return false; }
        }
        /// <summary>what anyone may see of another person's points page (balance, rank, categories, activity); nothing when they hid it or opted out. No loans, depreciation or limits.</summary>
        public static JObject PublicView(string login)
        {
            string c = Canon(Boards.AliasMap(), login);
            if (PageHidden(c)) return new JObject { { "ok", false }, { "login", c }, { "error", "this page is private" } };
            var v = Me2(c, 30); foreach (var k in new[] { "loans", "p2p", "depreciation", "giveToday", "giveLimit", "ledger", "sub", "tipped" }) v.Remove(k);
            return v;
        }

        static readonly Regex RxVs = new Regex(@"vs ([A-Za-z0-9_]+)", RegexOptions.IgnoreCase);

        /// <summary>`rows` = this person's ledger rows (each with "id"); returns newest first, at most `cap`; `total` = how many there are before the cap.</summary>
        public static JArray Activity(string login, List<JObject> rows, double currentBalance, int cap, out int total)
        {
            var list = new List<JObject>();   // oldest first: {at,type,label,delta,balance,before}
            lock (L)
            {
                var led = Ledger();
                foreach (var x in rows.OrderBy(r => (long)D(r["at"])))
                {
                    string id = (string)x["id"] ?? "", src = (string)x["source"] ?? "other", note = (string)x["note"] ?? "";
                    long at = (long)D(x["at"]), delta = (long)D(x["delta"]); double? bal = x["balance"] == null || x["balance"].Type == JTokenType.Null ? (double?)null : D(x["balance"]);
                    string label = null, type = src; long d = delta;
                    Func<string, JObject> L1 = k => k == null ? null : led[k] as JObject;
                    Func<JObject, bool> mine = o => o != null && string.Equals((string)o["login"], login, StringComparison.OrdinalIgnoreCase);
                    if ((src == "gamble" || src == "slots" || src == "duel") && id.EndsWith("-win"))
                    {
                        string b0 = id.Substring(0, id.Length - 4);
                        bool folded = src == "duel" ? (mine(L1(b0 + "-a")) || mine(L1(b0 + "-b"))) : mine(L1(b0));
                        if (folded) continue;   // shown inside its bet row
                        label = "Won " + delta;
                    }
                    else if ((src == "gamble" || src == "slots") && delta < 0)
                    {
                        var w = L1(id + "-win");
                        if (w != null)
                        {
                            long net = (long)D(w["delta"]) + delta; d = net; if (w["balance"] != null) bal = D(w["balance"]); at = (long)D(w["at"]);
                            label = net > 0 ? "Won " + net : net == 0 ? "Broke even" : "Lost " + (-net);
                        }
                        else label = "Lost " + (-delta);
                    }
                    else if (src == "duel" && delta < 0 && (id.EndsWith("-a") || id.EndsWith("-b")))
                    {
                        string b0 = id.Substring(0, id.Length - 2); var w = L1(b0 + "-win"); var m = RxVs.Match(note); string vs = m.Success ? m.Groups[1].Value : "";
                        string tail = vs != "" ? " (duel vs " + vs + ")" : " (duel)";
                        if (w != null && mine(w)) { long net = (long)D(w["delta"]) + delta; d = net; if (w["balance"] != null) bal = D(w["balance"]); at = (long)D(w["at"]); label = "Won " + net + tail; }
                        else if (w != null) label = "Lost " + (-delta) + tail;
                        else label = "Duel stake" + tail;
                    }
                    else label = Friendly(src, note, delta);
                    list.Add(new JObject { { "at", at }, { "type", type }, { "label", label }, { "delta", d }, { "balance", bal.HasValue ? (JToken)Math.Floor(bal.Value) : JValue.CreateNull() }, { "before", bal.HasValue ? (JToken)Math.Floor(bal.Value - d) : JValue.CreateNull() } });
                }
            }
            // watch-time points have no ledger row: fill the holes so every balance follows from the one before
            var res = new List<JObject>(); double? prev = null;
            foreach (var e in list)
            {
                if (e["before"].Type != JTokenType.Null)
                {
                    double before = (double)e["before"];
                    if (prev == null) { if (before >= 1) res.Add(Gap((long)e["at"], before, before, "Earlier points (watching, imports)")); }
                    else if (before - prev.Value >= 1) res.Add(Gap((long)e["at"], before - prev.Value, before, "Watching the stream"));
                    prev = e["balance"].Type == JTokenType.Null ? (double?)null : (double)e["balance"];
                }
                res.Add(e);
            }
            if (prev != null && Math.Floor(currentBalance) - prev.Value >= 1) res.Add(Gap(HourNow(), Math.Floor(currentBalance) - prev.Value, Math.Floor(currentBalance), "Watching the stream"));
            else if (prev == null && res.Count == 0 && currentBalance >= 1) res.Add(Gap(HourNow(), Math.Floor(currentBalance), Math.Floor(currentBalance), "Watching the stream"));
            total = res.Count; res.Reverse();
            var o = new JArray();
            foreach (var e in res.Take(Math.Max(1, cap))) { e.Remove("before"); o.Add(e); }
            return o;
        }

        /// <summary>now, rounded down to the hour, so an unchanged balance gives an unchanged view (the site push skips identical views)</summary>
        static long HourNow() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds() / 3600 * 3600; }

        static JObject Gap(long at, double delta, double balance, string label)
        {
            return new JObject { { "at", at }, { "type", "watching" }, { "label", label }, { "delta", (long)Math.Floor(delta) }, { "balance", Math.Floor(balance) }, { "before", Math.Floor(balance - delta) } };
        }

        /// <summary>plain words for one ledger row (never "slots bet" style bookkeeping text)</summary>
        static string Friendly(string src, string note, long delta)
        {
            string n = (note ?? "").Trim(); long a = Math.Abs(delta);
            var m = Regex.Match(n, @"^give to (\S+)", RegexOptions.IgnoreCase); if (m.Success) return "Gave " + a + " to " + m.Groups[1].Value;
            m = Regex.Match(n, @"^given by (\S+)", RegexOptions.IgnoreCase); if (m.Success) return "Received " + a + " from " + m.Groups[1].Value;
            if (src == "shop" || n.StartsWith("shop ", StringComparison.OrdinalIgnoreCase))
            {
                if (n.IndexOf("buy_chatty", StringComparison.OrdinalIgnoreCase) >= 0) return "Unlocked ChattyPinguino";
                if (n.IndexOf("guess_chatter", StringComparison.OrdinalIgnoreCase) >= 0) return delta > 0 ? "Guess the Chatter: won " + a : "Guess the Chatter: stake " + a;
                return delta > 0 ? "Shop refund" : "Shop purchase";
            }
            if (src == "p2p_out" || src == "p2p_in" || src == "p2p_repay" || src == "p2p_repaid") return n != "" ? n : Label(src);
            if (src == "loan") return "Loan taken";
            if (src == "loan_repay") return "Loan repaid";
            if (src == "depreciation") return "Depreciation";
            if (src == "grant" || src == "backpay") return n != "" && !n.StartsWith("grant", StringComparison.OrdinalIgnoreCase) ? n : Label(src);
            if (n != "" && Regex.IsMatch(n, @"\b(bet|stake)\b", RegexOptions.IgnoreCase)) return delta > 0 ? "Winnings" : "Bet";
            return n != "" ? char.ToUpperInvariant(n[0]) + n.Substring(1) : Label(src);
        }
    }
}
