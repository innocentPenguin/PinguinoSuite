using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Economy phase 2 (see Docs\ECONOMY_CONTRACT.md and Docs\ECONOMY_EVERYWHERE.md).
    ///  * Economy.Award(login, amount, source, note): the ONE way points move. Every award/spend is a ledger line {id, login, delta, source, note, balance (after), at}; the same id twice applies once.
    ///  * Match awards: every finished PinguinoBot match pays the roster for playing and the winners for winning (customs / competitive / casual, amounts in settings).
    ///  * Depreciation: once per stream, at the end of the stream, a balance over the threshold loses a small percent. Dry run first (logs what it WOULD take), exempt: bots, the streamer, Exclude, DepreciationExempt.
    ///  * Reminder: a one-line personal heads-up to a rich viewer, once per stream, when they chat (only when depreciation is really on).
    ///  * Loans: !loan / !repay / !bank. Interest per stream; a loan unpaid after LoanDefaultStreams streams is "defaulted" (interest stops, no new loans until repaid, nothing else).
    /// A "stream" here is the live->offline transition seen by IsLive(), debounced (StreamEndGraceMin) so a Twitch blip cannot end a stream twice.</summary>
    public static partial class Economy
    {
        static void Phase2Defaults(JObject d)
        {
            d["ActivityAwards"] = true;
            d["CustomsPlay"] = 5; d["CustomsWin"] = 10; d["CompPlay"] = 10; d["CompWin"] = 25; d["CasPlay"] = 5; d["CasWin"] = 15;
            d["DepreciationOn"] = true; d["DepreciationDryRun"] = true; d["DepreciationPct"] = 2.5; d["DepreciationThreshold"] = 100000; d["DepreciationBasis"] = "total";
            d["DepreciationExempt"] = new JArray(); d["DepreciationReminder"] = true; d["StreamEndGraceMin"] = 10;
            d["LoansOn"] = true; d["LoanPerHour"] = 100; d["LoanCap"] = 5000; d["LoanMinWatchHours"] = 1; d["LoanInterestPct"] = 5; d["LoanDefaultStreams"] = 10;
        }

        // ================= the one way points move =================
        static string SourceOf(string reason)
        {
            string r = (reason ?? "").ToLowerInvariant();
            if (r.StartsWith("welcome")) return "welcome";
            if (r.Contains("duel")) return "duel";
            if (r.Contains("slots")) return "slots";
            if (r.Contains("give") || r.Contains("gift")) return "gifts";
            if (r.Contains("shop")) return "shop";
            if (r.Contains("bet") || r.Contains("gamble")) return "gamble";
            return "other";
        }

        /// <summary>Moves points: amount &gt; 0 gives, amount &lt; 0 takes (refused when the balance is too low). `source` groups the ledger (playing, winning, gamble, song, ...), `note` is the human line, `id` (optional) makes a retry apply once.
        /// Returns null on success (also when the id was already applied) or the reason it was refused.</summary>
        public static string Award(string login, long amount, string source, string note = "", string id = null)
        {
            if (amount == 0) return "nothing to award";
            source = Norm(source); if (source == "") source = "other";
            if (Sim.IsSim(login)) return amount > 0 ? (Sim.Credit(login, amount) ? null : "sim refused") : Sim.Spend(login, -amount);   // simulated players keep their own in-memory ledger
            if (amount > 0 && Boards.IsBot(login)) return "bots do not earn " + CurrencyName;
            if (string.IsNullOrEmpty(id)) id = "aw-" + Guid.NewGuid().ToString("N");
            return Apply(id, login, amount, source, note ?? "");
        }

        static string Apply(string id, string login, long delta, string source, string note)
        {
            login = Canon(Boards.AliasMap(), login); if (login == "") return "no user";
            long before = Balance(login);
            if (delta < 0 && before < -delta) return "not enough " + CurrencyName;
            lock (L)
            {
                var led = Ledger(); if (led[id] != null) return null;
                var adj = (JObject)Doc()["adjust"]; adj[login] = D(adj[login]) + delta;
                led[id] = new JObject { { "login", login }, { "delta", delta }, { "reason", note != "" ? note : source }, { "source", source }, { "note", note }, { "balance", before + delta }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } };
                Save();
            }
            if (source != "loan" && source != "loan_repay" && source != "depreciation") Periods.Add(login, delta < 0 ? "points_spent" : (source == "backpay" || source == "grant") ? "points_backpay" : "points", Math.Abs((double)delta), 0, "ap:" + id);
            return null;
        }

        // ================= stream state =================
        static bool? _forceLive; static DateTime _offlineSince = DateTime.MinValue;
        static bool TestHook { get { return Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_TESTHOOK") == "1"; } }
        static int GraceSec { get { int v; if (int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_GRACE_SEC"), out v)) return Math.Max(0, v); return (int)(Math.Max(0, D(Settings()["StreamEndGraceMin"])) * 60); } }
        /// <summary>start/end (unix s) of the most recent real stream in the economy's records; end = 0 while it is still open</summary>
        public static bool LastStreamWindow(out long start, out long end)
        {
            start = 0; end = 0;
            lock (L)
            {
                var s = PStreams().Properties().Select(p => (JObject)p.Value).Where(x => (string)x["id"] != "off" && (string)x["id"] != "backpay" && D(x["start"]) > 1).OrderByDescending(x => D(x["start"])).FirstOrDefault();
                if (s == null) return false; start = (long)D(s["start"]); end = s["end"] == null || s["end"].Type == JTokenType.Null ? 0 : (long)D(s["end"]); return true;
            }
        }
        static JObject StreamDoc() { var d = Doc(); var s = d["stream"] as JObject; if (s == null) d["stream"] = s = new JObject { { "id", "" }, { "open", false } }; return s; }
        static string Streamer() { try { return Norm((string)HostApi.StreamerCreds()["Channel"]); } catch (Exception) { return ""; } }
        static void Back(string text, JObject detail = null, string level = "info") { try { EventLog.Backend("economy", text, detail, level); } catch (Exception) { } }

        /// <summary>the economy's own once-a-minute work (after the earning tick): match awards and the stream start/end transitions</summary>
        static void Phase2Tick()
        {
            if (!Lease.MayRun) return;
            try { AwardMatches(); } catch (Exception ex) { Clog.Warn("economy", "match awards failed: " + ex.Message); }
            bool live = IsLive(); bool open; lock (L) open = (bool?)StreamDoc()["open"] == true;
            if (live) _offlineSince = DateTime.MinValue;
            if (live && !open) StartStream();
            else if (!live && open)
            {
                if (_offlineSince == DateTime.MinValue) _offlineSince = DateTime.UtcNow;
                if ((DateTime.UtcNow - _offlineSince).TotalSeconds >= GraceSec) EndStream();
            }
            else if (live && open) { try { RefreshHolders(); } catch (Exception ex) { Clog.Warn("economy", "holders refresh failed: " + ex.Message); } }
        }

        static void StartStream()
        {
            string sid = "s" + DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            lock (L) { var s = StreamDoc(); s["id"] = sid; s["open"] = true; s["startedAt"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); s["endedAt"] = null; s["reminded"] = new JArray(); Save(); }
            StreamOpened(sid, DateTimeOffset.UtcNow.ToUnixTimeSeconds());
            Clog.Info("economy", "stream started: " + sid); Back("stream " + sid + " started", new JObject { { "stream", sid } });
            try { RefreshHolders(); } catch (Exception) { }
        }

        static void EndStream()
        {
            string sid; lock (L) sid = (string)StreamDoc()["id"] ?? "";
            try { Depreciate(sid); } catch (Exception ex) { Clog.Warn("economy", "depreciation failed: " + ex.Message); Back("depreciation failed: " + ex.Message, null, "error"); }
            try { LoanInterest(sid); } catch (Exception ex) { Clog.Warn("economy", "loan interest failed: " + ex.Message); }
            StreamClosed(sid);
            lock (L) { var s = StreamDoc(); s["open"] = false; s["endedAt"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); Save(); }
            lock (_holders) _holders.Clear();
            Clog.Info("economy", "stream ended: " + sid); Back("stream " + sid + " ended", new JObject { { "stream", sid } });
        }

        // ================= match awards =================
        static string KindOf(string activity)
        {
            string a = (activity ?? "").ToLowerInvariant();
            if (a == "" || a == "competitive") return "Comp";
            if (a == "casual") return "Cas";
            return "Customs";
        }
        static string KindSource(string kind, bool win) { return kind.ToLowerInvariant() + (win ? "_win" : "_play"); }

        static bool Done(JObject m)
        {
            string w = ((string)m["Winner"] ?? "").ToLowerInvariant();
            return (w == "blue" || w == "orange") && (bool?)m["Incomplete"] != true && (bool?)m["Counted"] != false && m["FinishedAt"] != null && m["FinishedAt"].Type != JTokenType.Null;
        }

        /// <summary>pays finished matches that are newer than the watermark. The watermark is the highest finished match at the first run (history is never paid back); every payment has its own ledger id, so re-scanning never pays twice.</summary>
        static int AwardMatches()
        {
            JObject set; lock (L) set = Settings();
            if ((bool?)set["ActivityAwards"] == false) return 0;
            var ms = Replays.Matches().OfType<JObject>().ToList(); if (ms.Count == 0) return 0;
            long from;
            lock (L)
            {
                var aw = Doc()["awards"] as JObject; if (aw == null) Doc()["awards"] = aw = new JObject();
                if (aw["from"] == null)
                {
                    long env; aw["from"] = long.TryParse(Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_AWARD_FROM"), out env) ? env : ms.Where(Done).Select(m => (long?)m["Id"] ?? 0).DefaultIfEmpty(0).Max();
                    Save();
                }
                from = (long)aw["from"];
            }
            string streamer = Streamer(); var ex = new HashSet<string>(((JArray)set["Exclude"]).Select(x => Norm((string)x))); int paid = 0;
            foreach (var m in ms.Where(m => ((long?)m["Id"] ?? 0) > from && Done(m)).OrderBy(m => (long)m["Id"]))
            {
                long mid = (long)m["Id"]; string kind = KindOf((string)m["Activity"]); string winner = ((string)m["Winner"]).ToLowerInvariant();
                long play = (long?)set[kind + "Play"] ?? 0, win = (long?)set[kind + "Win"] ?? 0; bool mv2 = WatchV2;
                string kn = kind == "Comp" ? "competitive" : kind == "Cas" ? "casual" : "customs"; string label = kn + " match #" + mid;
                foreach (var side in new[] { "blue", "orange" })
                    foreach (var p in (m[char.ToUpperInvariant(side[0]) + side.Substring(1)] as JArray ?? new JArray()).OfType<JObject>())
                    {
                        string login = Norm((string)p["Username"]); if (login == "" || login == streamer || ex.Contains(login) || Boards.IsBot(login)) continue;
                        if (mv2) { play = MatchPoints(TierOf(login), false); win = MatchPoints(TierOf(login), true); }   // v2: scaled to the person's own watch rate
                        if (play > 0) { string id = "match:" + mid + ":play:" + login; if (!Applied(id) && Award(login, play, KindSource(kind, false), "Played a " + label, id) == null) { paid++; MatchRow(login, "game", "Played a " + label, play, id); } }
                        if (side == winner) Periods.Add(login, "wins", 1, 0, "win:" + mid + ":" + login);
                        if (win > 0 && side == winner) { string id = "match:" + mid + ":win:" + login; if (!Applied(id) && Award(login, win, KindSource(kind, true), "Won a " + label, id) == null) { paid++; MatchRow(login, "game", "Won a " + label, win, id); } }
                    }
            }
            if (paid > 0) { Clog.Info("economy", "match awards: " + paid + " payments"); Back("match awards: " + paid + " payments", new JObject { { "payments", paid } }); }
            return paid;
        }

        // ================= depreciation =================
        static readonly Dictionary<string, double> _holders = new Dictionary<string, double>();

        static HashSet<string> DepExempt(JObject set)
        {
            var ex = new HashSet<string>(((JArray)set["Exclude"]).Select(x => Norm((string)x)));
            foreach (var x in (set["DepreciationExempt"] as JArray) ?? new JArray()) ex.Add(Norm((string)x));
            string st = Streamer(); if (st != "") ex.Add(st);
            return ex;
        }
        /// <summary>the loss for one balance under the current settings (0 when under the threshold)</summary>
        public static long DepreciationFor(double bal, JObject set = null)
        {
            if (set == null) lock (L) set = Settings();
            double thr = D(set["DepreciationThreshold"]), pct = D(set["DepreciationPct"]); bal = Math.Floor(bal);
            if (pct <= 0 || bal <= thr) return 0;
            double basis = ((string)set["DepreciationBasis"] ?? "total").ToLowerInvariant() == "excess" ? bal - thr : bal;
            long loss = (long)Math.Floor(basis * pct / 100.0); if (loss < 1) loss = 1;
            if (bal - loss < thr && ((string)set["DepreciationBasis"] ?? "total").ToLowerInvariant() == "excess") loss = (long)(bal - thr);
            return Math.Max(0, loss);
        }
        static List<KeyValuePair<string, double>> Holders(JObject set)
        {
            var al = Boards.AliasMap(); var snap = Snapshot(al); var ex = DepExempt(set); double thr = D(set["DepreciationThreshold"]);
            return snap.Users.Where(k => Math.Floor(k.Value.Points) > thr && !ex.Contains(k.Key) && !Boards.IsBot(k.Key)).Select(k => new KeyValuePair<string, double>(k.Key, Math.Floor(k.Value.Points))).OrderByDescending(k => k.Value).ToList();
        }
        static void RefreshHolders()
        {
            JObject set; lock (L) set = Settings(); var h = Holders(set);
            lock (_holders) { _holders.Clear(); foreach (var k in h) _holders[k.Key] = k.Value; }
        }

        /// <summary>end-of-stream depreciation. Mode: off (DepreciationOn false) = nothing; on + DryRun = only logs what it would take; on + not DryRun = takes it (ledger id depr:&lt;stream&gt;:&lt;login&gt;, once per stream).</summary>
        static JObject Depreciate(string sid)
        {
            JObject set; lock (L) set = Settings();
            if ((bool?)set["DepreciationOn"] == false) return new JObject { { "ran", false }, { "why", "off" } };
            bool dry = (bool?)set["DepreciationDryRun"] != false;
            lock (L) { var s = StreamDoc(); if ((string)s["depreciated"] == sid && sid != "") return new JObject { { "ran", false }, { "why", "already done for " + sid } }; }
            var hs = Holders(set); long total = 0; var lines = new JArray(); int taken = 0;
            foreach (var h in hs)
            {
                long loss = DepreciationFor(h.Value, set); if (loss <= 0) continue;
                lines.Add(new JObject { { "login", h.Key }, { "balance", h.Value }, { "loss", loss } });
                if (!dry && Award(h.Key, -loss, "depreciation", "Depreciation " + D(set["DepreciationPct"]).ToString("0.##", CultureInfo.InvariantCulture) + "% over " + Num(D(set["DepreciationThreshold"])), "depr:" + sid + ":" + h.Key) == null) { total += loss; taken++; }
                else if (dry) total += loss;
            }
            string line = DateTime.UtcNow.ToString("o") + "\t" + sid + "\t" + (dry ? "DRYRUN would take" : "took") + " " + total + " from " + lines.Count + " people: " + string.Join(", ", lines.Take(10).Select(x => (string)x["login"] + " -" + (long)x["loss"]));
            try { File.AppendAllText(System.IO.Path.Combine(Dir, "depreciation.log"), line + Environment.NewLine); } catch (Exception) { }
            var res = new JObject { { "ran", true }, { "dryRun", dry }, { "stream", sid }, { "people", lines.Count }, { "total", total }, { "top", new JArray(lines.Take(10)) } };
            lock (L) { var s = StreamDoc(); s["depreciated"] = sid; s["lastDepreciation"] = res; Save(); }
            Clog.Info("economy", "depreciation " + (dry ? "(dry run) would take " : "took ") + total + " from " + lines.Count + " people");
            Back("depreciation " + (dry ? "dry run: would take " : "took ") + Num(total) + " " + CurrencyName + " from " + lines.Count + " people", res);
            return res;
        }

        /// <summary>what depreciation would do right now (nobody is charged)</summary>
        public static JObject DepreciationPreview()
        {
            JObject set; lock (L) set = Settings(); var hs = Holders(set); long total = 0;
            var rows = new JArray(); foreach (var h in hs) { long loss = DepreciationFor(h.Value, set); total += loss; if (rows.Count < 50) rows.Add(new JObject { { "login", h.Key }, { "balance", h.Value }, { "loss", loss } }); }
            JObject st; lock (L) st = (JObject)StreamDoc().DeepClone();
            return new JObject { { "ok", true }, { "on", (bool?)set["DepreciationOn"] != false }, { "dryRun", (bool?)set["DepreciationDryRun"] != false }, { "pct", D(set["DepreciationPct"]) }, { "threshold", D(set["DepreciationThreshold"]) }, { "basis", (string)set["DepreciationBasis"] ?? "total" },
                { "people", hs.Count }, { "total", total }, { "top", rows }, { "stream", st } };
        }

        // ---- the one-line reminder ----
        static DateTime _lastRemind = DateTime.MinValue;
        /// <summary>called for every chat line: a viewer over the threshold hears ONE personal line per stream. Only when depreciation is really on (not a dry run), the stream is open and they did not opt out of being named (Boards.IsAnon).</summary>
        public static void OnChat(string user, string text, Action<string> say)
        {
            try
            {
                if (string.IsNullOrEmpty(user) || (text ?? "").TrimStart().StartsWith("!") || Control.Synthetic) return;
                string login = Norm(user); double bal;
                lock (_holders) { if (_holders.Count == 0 || !_holders.TryGetValue(login, out bal)) return; }
                JObject set; lock (L) set = Settings();
                if ((bool?)set["DepreciationOn"] == false || (bool?)set["DepreciationDryRun"] != false || (bool?)set["DepreciationReminder"] == false) return;
                if (Boards.IsAnon(login) || Boards.IsBot(login) || DepExempt(set).Contains(login)) return;
                lock (L)
                {
                    var s = StreamDoc(); if ((bool?)s["open"] != true) return;
                    var rem = s["reminded"] as JArray; if (rem == null) s["reminded"] = rem = new JArray();
                    if (rem.Any(x => (string)x == login)) return;
                    if ((DateTime.UtcNow - _lastRemind).TotalSeconds < 15) return;   // one reminder at a time in the whole chat
                    rem.Add(login); _lastRemind = DateTime.UtcNow; Save();
                }
                double pct = D(set["DepreciationPct"]); long loss = DepreciationFor(bal, set);
                say("@" + user + " you hold " + Num(bal) + " " + CurrencyName + "; over " + Num(D(set["DepreciationThreshold"])) + " you lose " + pct.ToString("0.##", CultureInfo.InvariantCulture) + "% each stream (about " + Num(loss) + " at the end of this one). Spend, gamble or give some away.");
            }
            catch (Exception ex) { Clog.Warn("economy", "reminder failed: " + ex.Message); }
        }

        // ================= loans =================
        static JObject Loans() { var d = Doc(); var l = d["loans"] as JObject; if (l == null) d["loans"] = l = new JObject(); return l; }
        public static long MaxLoan(string login, JObject set = null, double? minutes = null)
        {
            if (set == null) lock (L) set = Settings();
            double hours = Math.Floor(minutes ?? Me(login).Minutes) / 60.0; if (hours < D(set["LoanMinWatchHours"])) return 0;
            return (long)Math.Min(D(set["LoanCap"]), Math.Floor(hours * D(set["LoanPerHour"])));
        }

        static JObject LoanView(string login, JObject set, double? minutes = null)
        {
            JObject ln; lock (L) ln = Loans()[login] as JObject;
            long max = MaxLoan(login, set, minutes); bool on = (bool?)set["LoansOn"] != false;
            var o = new JObject { { "on", on }, { "maxLoan", max }, { "interestPct", D(set["LoanInterestPct"]) }, { "defaultAfterStreams", D(set["LoanDefaultStreams"]) }, { "owed", ln == null ? 0 : D(ln["owed"]) }, { "principal", ln == null ? 0 : D(ln["principal"]) },
                { "streamsOpen", ln == null ? 0 : (int?)ln["streams"] ?? 0 }, { "defaulted", ln != null && (bool?)ln["defaulted"] == true }, { "takenAt", ln == null ? null : ln["takenAt"] } };
            o["canBorrow"] = on && ln == null && max > 0; o["ratePct"] = D(set["LoanInterestPct"]);
            o["items"] = new JArray(); if (ln != null && D(ln["owed"]) > 0) ((JArray)o["items"]).Add(new JObject { { "id", "loan-" + login }, { "principal", D(ln["principal"]) }, { "owed", Math.Ceiling(D(ln["owed"])) }, { "at", ln["takenAt"] } });
            return o;
        }

        /// <summary>take a loan (chat or site). reqId (site request id) makes a retry apply once.</summary>
        public static JObject LoanTake(string login, long amount, string reqId = null)
        {
            login = Canon(Boards.AliasMap(), login); JObject set; lock (L) set = Settings(); string cur = CurrencyName;
            Func<string, JObject> no = m => new JObject { { "ok", false }, { "error", m } };
            if (login == "" || Boards.IsBot(login)) return no("no user");
            if ((bool?)set["LoansOn"] == false) return no("the bank is closed for loans right now");
            string id = string.IsNullOrEmpty(reqId) ? "loan:" + login + ":" + DateTimeOffset.UtcNow.ToUnixTimeSeconds() : "loan-" + reqId;
            if (Applied(id)) return new JObject { { "ok", true }, { "message", "already applied" } };
            JObject ln; lock (L) ln = Loans()[login] as JObject;
            if (ln != null) return no("you still owe " + Num(D(ln["owed"])) + " " + cur + ((bool?)ln["defaulted"] == true ? " (overdue: no new loans until it is repaid)" : "") + ": use !repay first");
            long max = MaxLoan(login, set);
            if (max <= 0) return no("you need " + D(set["LoanMinWatchHours"]).ToString("0.##", CultureInfo.InvariantCulture) + " hours of watch time before the bank lends to you (your history sets the limit)");
            if (amount <= 0) return no("how much? You can borrow up to " + Num(max) + " " + cur);
            if (amount > max) return no("your limit is " + Num(max) + " " + cur + " for now");
            lock (L) { Loans()[login] = new JObject { { "principal", amount }, { "owed", amount }, { "takenAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "streams", 0 }, { "defaulted", false } }; Save(); }
            string err = Apply(id, login, amount, "loan", "Loan taken"); if (err != null) { lock (L) { Loans().Remove(login); Save(); } return no(err); }
            Back(login + " took a loan of " + amount, new JObject { { "login", login }, { "amount", amount } });
            return new JObject { { "ok", true }, { "message", "borrowed " + Num(amount) + " " + cur + "; interest " + D(set["LoanInterestPct"]).ToString("0.##", CultureInfo.InvariantCulture) + "% each stream. Pay it back with !repay" }, { "owed", amount } };
        }

        /// <summary>repay part (amount &gt; 0) or all (amount 0) of the loan, limited by the balance</summary>
        public static JObject LoanRepay(string login, long amount, string reqId = null)
        {
            login = Canon(Boards.AliasMap(), login); string cur = CurrencyName;
            Func<string, JObject> no = m => new JObject { { "ok", false }, { "error", m } };
            JObject ln; lock (L) ln = Loans()[login] as JObject; if (ln == null) return no("you have no loan");
            string id = string.IsNullOrEmpty(reqId) ? "repay:" + login + ":" + Guid.NewGuid().ToString("N") : "repay-" + reqId;
            if (!string.IsNullOrEmpty(reqId) && Applied(id)) return new JObject { { "ok", true }, { "message", "already applied" } };
            long owed = (long)Math.Ceiling(D(ln["owed"])); long pay = amount > 0 ? Math.Min(amount, owed) : owed; long bal = Balance(login);
            if (bal <= 0) return no("you have no " + cur + " to repay with");
            pay = Math.Min(pay, bal);
            string err = Apply(id, login, -pay, "loan_repay", "Loan repayment"); if (err != null) return no(err);
            long left;
            lock (L) { double o = D(ln["owed"]) - pay; if (o <= 0.5) { Loans().Remove(login); left = 0; } else { ln["owed"] = o; left = (long)Math.Ceiling(o); } Save(); }
            return new JObject { { "ok", true }, { "paid", pay }, { "owed", left }, { "message", left == 0 ? "paid " + Num(pay) + " " + cur + ": the loan is fully repaid. Thank you!" : "paid " + Num(pay) + " " + cur + ", you still owe " + Num(left) + "." } };
        }

        static void LoanInterest(string sid)
        {
            JObject set; lock (L) set = Settings(); if ((bool?)set["LoansOn"] == false) return;
            double pct = D(set["LoanInterestPct"]); int limit = Math.Max(1, (int)D(set["LoanDefaultStreams"])); int n = 0;
            lock (L)
            {
                foreach (var p in Loans().Properties())
                {
                    var ln = p.Value as JObject; if (ln == null || (string)ln["lastInterest"] == sid || (bool?)ln["defaulted"] == true) continue;
                    ln["lastInterest"] = sid; ln["owed"] = D(ln["owed"]) + Math.Max(1, Math.Round(D(ln["principal"]) * pct / 100.0)); ln["streams"] = ((int?)ln["streams"] ?? 0) + 1;
                    if ((int)ln["streams"] >= limit) ln["defaulted"] = true; n++;
                }
                if (n > 0) Save();
            }
            if (n > 0) Back("loan interest added to " + n + " loans", new JObject { { "loans", n } });
        }

        // ================= chat =================
        public static bool IsBankCommand(string c) { return c == "!loan" || c == "!repay" || c == "!bank"; }
        static string Pct(double v) { return v.ToString("0.##", CultureInfo.InvariantCulture); }

        static void HandleBank(string user, string cmd, string[] args, Action<string> say)
        {
            string me = Norm(user); string cur = CurrencyName; string at = "@" + user + " ";
            if (Cooling("bank|" + me, 1)) return;
            JObject set; lock (L) set = Settings();
            if (cmd == "!loan")
            {
                long n; if (args.Length > 0 && long.TryParse(args[0].Replace(",", ""), NumberStyles.Integer, CultureInfo.InvariantCulture, out n)) { var r = LoanTake(me, n); say(at + ((bool?)r["ok"] == true ? (string)r["message"] : (string)r["error"]) + "."); return; }
                var v = LoanView(me, set);
                say(at + ((bool?)v["on"] == false ? "the bank is closed for loans right now." : D(v["owed"]) > 0 ? "you owe " + Num(D(v["owed"])) + " " + cur + ". Pay it with !repay." : (long)v["maxLoan"] > 0 ? "you can borrow up to " + Num((long)v["maxLoan"]) + " " + cur + " at " + Pct(D(set["LoanInterestPct"])) + "% interest per stream: !loan <amount>" : "you need " + Pct(D(set["LoanMinWatchHours"])) + " hours of watch time before you can borrow."));
                return;
            }
            if (cmd == "!repay")
            {
                long n = 0; if (args.Length > 0 && args[0].ToLowerInvariant() != "all" && !long.TryParse(args[0].Replace(",", ""), NumberStyles.Integer, CultureInfo.InvariantCulture, out n)) { say(at + "usage: !repay <amount|all>"); return; }
                var r = LoanRepay(me, n); say(at + ((bool?)r["ok"] == true ? (string)r["message"] : (string)r["error"]) + ((bool?)r["ok"] == true ? "" : "."));
                return;
            }
            var lv = LoanView(me, set); long bal = Balance(me); long dep = DepreciationFor(bal, set); bool deprOn = (bool?)set["DepreciationOn"] != false;
            string loan = D(lv["owed"]) > 0 ? "loan owed " + Num(D(lv["owed"])) + ((bool?)lv["defaulted"] == true ? " (overdue)" : "") : (long)lv["maxLoan"] > 0 ? "can borrow " + Num((long)lv["maxLoan"]) : "no loan";
            string depr = !deprOn ? "" : dep > 0 ? " | next depreciation about " + Num(dep) + (((bool?)set["DepreciationDryRun"] != false) ? " (practice run, nothing is taken yet)" : " at the end of this stream") : " | nothing is lost to depreciation (limit " + Num(D(set["DepreciationThreshold"])) + ")";
            say(at + "you have " + Num(bal) + " " + cur + " | " + loan + depr);
        }

        // ================= per-user view (the site's Points page) =================
        static readonly Dictionary<string, string> Labels = new Dictionary<string, string> {
            { "watching", "Watching the stream" }, { "imported", "Imported balance" }, { "customs_play", "Playing customs" }, { "customs_win", "Winning customs" }, { "comp_play", "Playing competitive" }, { "comp_win", "Winning competitive" },
            { "cas_play", "Playing casual" }, { "cas_win", "Winning casual" }, { "welcome", "Welcome bonus" }, { "gamble", "Gambling" }, { "slots", "Slots" }, { "duel", "Duels" }, { "gifts", "Gifts between viewers" }, { "shop", "Shop" },
            { "loan", "Loans taken" }, { "loan_repay", "Loan repayments" }, { "depreciation", "Depreciation" }, { "grant", "Given by the streamer" }, { "other", "Other" }, { "cheer", "Cheers" }, { "sub", "Subs" }, { "gift", "Gift subs" }, { "tip", "Tips" }, { "follow", "Follow" }, { "raid_in", "Raid arrivals" }, { "raid_out", "Raids led" } };
        static string Label(string s) { string l; return Labels.TryGetValue(s, out l) ? l : s; }

        /// <summary>everything the Points page needs for one person: GET /api/economy/me?login=</summary>
        /// <summary>one read of the whole economy (balances, ranks, ledger per person) so the site push builds thousands of views without rereading it for each</summary>
        public class Ctx { public Dictionary<string, string> Al; public Snap S; public Dictionary<string, int> Rank = new Dictionary<string, int>(); public int Of; public Dictionary<string, List<JObject>> Led = new Dictionary<string, List<JObject>>(); }
        public static Ctx BuildCtx()
        {
            var cx = new Ctx { Al = Boards.AliasMap() }; cx.S = Snapshot(cx.Al);
            var order = cx.S.Users.OrderByDescending(k => k.Value.Points).Where(k => !Boards.IsBot(k.Key)).Select(k => k.Key).ToList(); cx.Of = order.Count;
            for (int i = 0; i < order.Count; i++) cx.Rank[order[i]] = i + 1;
            lock (L)
                foreach (var p in Ledger().Properties())
                {
                    var e = p.Value as JObject; string lg = e == null ? null : (string)e["login"]; if (lg == null || lg == "*") continue;
                    var x = (JObject)e.DeepClone(); x["id"] = p.Name; if (x["source"] == null) x["source"] = SourceOf((string)x["reason"]);
                    List<JObject> l; if (!cx.Led.TryGetValue(lg, out l)) cx.Led[lg] = l = new List<JObject>(); l.Add(x);
                }
            return cx;
        }

        /// <summary>the Points page's "where it came from" list: play/win pairs of one activity folded into one row (points, wins, games)</summary>
        static JArray PageEarned(Dictionary<string, JObject> groups, List<JObject> rows)
        {
            var o = new JArray(); var done = new HashSet<string>();
            foreach (var g in groups.Values.OrderByDescending(g => (double)g["earned"]))
            {
                string src = (string)g["source"]; string act = src.EndsWith("_play") ? src.Substring(0, src.Length - 5) : src.EndsWith("_win") ? src.Substring(0, src.Length - 4) : null;
                if (act != null && (src.EndsWith("_play") || src.EndsWith("_win")) && groups.ContainsKey(act + "_play") | groups.ContainsKey(act + "_win"))
                {
                    if (!done.Add(act)) continue; JObject pl, wn; groups.TryGetValue(act + "_play", out pl); groups.TryGetValue(act + "_win", out wn);
                    string lab = act == "comp" ? "Competitive matches" : act == "cas" ? "Casual matches" : "Customs";
                    o.Add(new JObject { { "source", act }, { "label", lab }, { "points", Math.Floor((pl == null ? 0 : (double)pl["earned"]) + (wn == null ? 0 : (double)wn["earned"])) }, { "wins", wn == null ? 0 : (int)wn["count"] }, { "games", pl == null ? 0 : (int)pl["count"] } });
                }
                else if ((double)g["earned"] > 0) o.Add(new JObject { { "source", src }, { "label", g["label"] }, { "points", Math.Floor((double)g["earned"]) }, { "wins", 0 }, { "games", (int)g["count"] } });
            }
            return o;
        }

        /// <summary>where a ledger source belongs on the site summary</summary>
        static string CategoryOf(string source, double delta)
        {
            if (delta < 0) return "spent";
            switch (source)
            {
                case "watching": case "watch": case "entry": return "watching";
                case "chat": case "activity": return "chat";
                case "customs_play": case "customs_win": case "comp_play": case "comp_win": case "cas_play": case "cas_win": case "game": return "matches";
                case "cheer": return "cheers";
                case "sub": case "resub": case "gift": case "gift_recipient": case "tip": return "subs";
                case "follow": case "raid_in": case "raid_out": case "raid_leader": return "follows";
                case "backpay": return "backpay";
                default: return "other";
            }
        }
        static readonly string[][] CatDefs = { new[] { "watching", "Watching" }, new[] { "chat", "Chat activity" }, new[] { "matches", "Matches" }, new[] { "cheers", "Cheers/Bits" }, new[] { "subs", "Subs/Gifts" }, new[] { "follows", "Follows/Raids" }, new[] { "backpay", "Back-pay" }, new[] { "spent", "Spent" }, new[] { "other", "Other" } };
        /// <summary>the pushed summary: points grouped by category, each with the exact all-time net total, the event count and the newest 50 rows. Internal logs stay per event.</summary>
        static JArray Categories(List<JObject> rows, double watched, double imported, JArray streams)
        {
            var tot = new Dictionary<string, double>(); var cnt = new Dictionary<string, int>(); var rws = new Dictionary<string, List<JObject>>();
            foreach (var d in CatDefs) { tot[d[0]] = 0; cnt[d[0]] = 0; rws[d[0]] = new List<JObject>(); }
            foreach (var x in rows)   // oldest first, so reverse at the end
            {
                double dl = D(x["delta"]); string src = (string)x["source"] ?? "other"; string k = CategoryOf(src, dl);
                string lab = (string)x["note"]; if (string.IsNullOrEmpty(lab)) lab = (string)x["reason"]; if (string.IsNullOrEmpty(lab)) lab = Label(src);
                tot[k] += dl; cnt[k]++; rws[k].Add(new JObject { { "at", x["at"] }, { "label", lab }, { "delta", dl } });
            }
            if (watched >= 1) { tot["watching"] += Math.Floor(watched); }
            if (imported >= 1) { tot["other"] += Math.Floor(imported); cnt["other"]++; rws["other"].Insert(0, new JObject { { "at", 0 }, { "label", "Imported balance" }, { "delta", Math.Floor(imported) } }); }
            if (streams != null)   // watching rows: one per stream (the per-minute accrual is not kept as events)
                foreach (var s in streams.OfType<JObject>().Reverse())
                {
                    double w = 0; int n = 0; long at = 0; foreach (var r in ((JArray)s["rows"]).OfType<JObject>()) if ((string)r["type"] == "watch") { w += D(r["delta"]); n++; at = Math.Max(at, (long)D(r["at"])); }
                    if (n > 0) { cnt["watching"] += n; rws["watching"].Add(new JObject { { "at", at }, { "label", "Watched " + n + "x during " + (string)s["label"] }, { "delta", w } }); }
                }
            var o = new JArray();
            foreach (var d in CatDefs)
            {
                if (cnt[d[0]] == 0 && tot[d[0]] == 0) continue;
                o.Add(new JObject { { "key", d[0] }, { "label", d[1] }, { "total", Math.Floor(tot[d[0]]) }, { "count", cnt[d[0]] }, { "rows", new JArray(rws[d[0]].OrderByDescending(r => D(r["at"])).Take(50)) } });
            }
            return o;
        }

        public static JObject Me2(string login, int ledgerLimit = 50, Ctx cx = null)
        {
            if (cx == null) cx = BuildCtx();
            string c = Canon(cx.Al, login); JObject set; lock (L) set = Settings();
            Row row; cx.S.Users.TryGetValue(c, out row); double bal = row == null ? 0 : Math.Floor(row.Points); double minutes = row == null ? 0 : Math.Floor(row.Minutes); long dep = DepreciationFor(bal, set);
            List<JObject> rows; if (!cx.Led.TryGetValue(c, out rows)) rows = new List<JObject>();
            rows = rows.OrderBy(x => (long)x["at"]).ToList();
            var groups = new Dictionary<string, JObject>();
            Action<string, double, double, int> add = (src, earned, spent, cnt) => { JObject g; if (!groups.TryGetValue(src, out g)) groups[src] = g = new JObject { { "source", src }, { "label", Label(src) }, { "earned", 0.0 }, { "spent", 0.0 }, { "count", 0 } }; g["earned"] = (double)g["earned"] + earned; g["spent"] = (double)g["spent"] + spent; g["count"] = (int)g["count"] + cnt; };
            foreach (var x in rows) { double d = D(x["delta"]); add((string)x["source"], d > 0 ? d : 0, d < 0 ? -d : 0, 1); }
            double watched, imported;
            lock (L) { var d0 = Doc(); watched = D(d0["earned"]?[c]?["points"]); imported = D(d0["baseline"]?["users"]?[c]?["points"]); }
            if (watched >= 1) add("watching", Math.Floor(watched), 0, 0); if (imported >= 1) add("imported", Math.Floor(imported), 0, 0);
            JObject st; lock (L) st = StreamDoc();
            bool open = (bool?)st["open"] == true; bool dry = (bool?)set["DepreciationDryRun"] != false;
            var res = new JObject { { "ok", true }, { "login", c }, { "currency", CurrencyName }, { "balance", Math.Floor(bal) }, { "rank", cx.Rank.ContainsKey(c) ? cx.Rank[c] : 0 }, { "of", cx.Of }, { "minutes", minutes },
                { "depreciation", new JObject { { "on", (bool?)set["DepreciationOn"] != false }, { "dryRun", dry }, { "pct", D(set["DepreciationPct"]) }, { "threshold", D(set["DepreciationThreshold"]) }, { "basis", (string)set["DepreciationBasis"] ?? "total" },
                    { "amount", dep }, { "applies", dep > 0 }, { "when", open ? "end of this stream" : "end of the next stream" }, { "streamOpen", open } } },
                { "loans", LoanView(c, set, minutes) },
                { "earnings", new JArray(groups.Values.OrderByDescending(g => (double)g["earned"] + (double)g["spent"])) },
                { "ledger", new JArray(Enumerable.Reverse(rows).Take(Math.Max(1, Math.Min(500, ledgerLimit))).Select(x => { var y = (JObject)x.DeepClone(); y["label"] = Label((string)y["source"]); return y; })) },
                { "players", cx.Of }, { "earned", PageEarned(groups, rows) }, { "streams", StreamsView(c) }, { "tipped", TippedView(c) }, { "sub", SubRoll.ViewOf(c) } };
            res["categories"] = Categories(rows, watched, imported, (JArray)res["streams"]);
            var dp = (JObject)res["depreciation"]; dp["ratePct"] = dp["pct"]; dp["nextAmount"] = dp["amount"]; dp["nextAt"] = null; dp["nextAtKind"] = open ? "end_of_stream" : "next_stream_start";
            return res;
        }

        // ---- helpers for the site bridge ----
        public static IEnumerable<string> LoanLogins() { lock (L) return Loans().Properties().Select(x => x.Name).ToList(); }
        public static double LoanOwed(string login) { var c = Canon(Boards.AliasMap(), login); lock (L) { var ln = Loans()[c] as JObject; return ln == null ? 0 : Math.Ceiling(D(ln["owed"])); } }
        /// <summary>the knobs the Points page explains to viewers (no secrets in there)</summary>
        public static JObject PublicSettings()
        {
            JObject s; lock (L) s = Settings(); var o = new JObject();
            foreach (var k in new[] { "CurrencyName", "ActivityAwards", "CustomsPlay", "CustomsWin", "CompPlay", "CompWin", "CasPlay", "CasWin", "DepreciationOn", "DepreciationDryRun", "DepreciationPct", "DepreciationThreshold", "DepreciationBasis", "LoansOn", "LoanPerHour", "LoanCap", "LoanMinWatchHours", "LoanInterestPct", "LoanDefaultStreams" }.Concat(PointsKeys)) o[k] = s[k];
            return o;
        }

        // ================= HTTP =================
        /// <summary>/api/economy/* routes that belong to phase 2. Returns null for a path it does not own.</summary>
        public static JObject Phase2Api(string path, string method, string login, JObject body)
        {
            try
            {
                if ((path == "/api/economy/me" || path == "/api/points") && method == "GET") return Me2(login);
                if (path == "/api/points/loan" && method == "POST") { var q = new JObject { { "action", body["action"] }, { "login", body["login"] ?? login }, { "amount", body["amount"] }, { "id", body["id"] } }; return Phase2Api("/api/economy/loan", "POST", login, q); }
                if (path == "/api/economy/preview") return Preview(body);
                if (path == "/api/economy/backpay" && method == "POST") return BackPay(body["apply"] != null && (bool)body["apply"]);
                if (path == "/api/economy/points-settings") return PointsSettingsApi(body, method == "POST");
                if (path == "/api/economy/event" && method == "POST") return EventApi(body);
                if (path == "/api/economy/streams" && method == "GET") return new JObject { { "ok", true }, { "login", Canon(Boards.AliasMap(), login) }, { "streams", StreamsView(login) } };
                if (path == "/api/economy/depreciation" && method == "GET") return DepreciationPreview();
                if (path == "/api/economy/loan" && method == "POST")
                {
                    string act = ((string)body["action"] ?? "").ToLowerInvariant(); string who = (string)body["login"] ?? ""; string rid = (string)body["id"];
                    if (act == "take") return LoanTake(who, (long?)body["amount"] ?? 0, rid);
                    if (act == "repay") return LoanRepay(who, (long?)body["amount"] ?? 0, rid);
                    return new JObject { { "ok", false }, { "error", "action must be take or repay" } };
                }
                if (path == "/api/economy/stream" && method == "POST")
                {
                    if (!TestHook) return new JObject { { "ok", false }, { "error", "test hook is off" } };
                    if (body["live"] != null) _forceLive = (bool)body["live"];
                    Phase2Tick(); return new JObject { { "ok", true }, { "stream", StreamDoc().DeepClone() } };
                }
                if (path == "/api/economy/stream" && method == "GET") { lock (L) return new JObject { { "ok", true }, { "stream", StreamDoc().DeepClone() } }; }
            }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", ex.Message } }; }
            return null;
        }
    }
}
