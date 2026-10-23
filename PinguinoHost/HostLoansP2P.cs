using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Player-to-player loans. A borrower posts a REQUEST (amount, flat interest %, days); lenders send OFFERS (to a request, or straight to a person); the borrower ACCEPTS one,
    /// the points move, and the borrower REPAYS (any amount, any time) until the loan is paid or its due date passes (status "defaulted": interest stops, the borrower cannot borrow
    /// again until it is repaid, nothing is taken automatically). Money moves only through Economy.Award with unique ids (a retry applies once; a short balance is refused, so nobody goes
    /// below zero) and every move is a ledger row for BOTH people (sources p2p_out / p2p_in / p2p_repay / p2p_repaid, kept out of the "earned" periods).
    /// State: Data\economy\p2p_loans.json. Limits: Data\economy\p2p_settings.json (re-read when it changes). House loans (!loan) are a separate system and stay as they are.</summary>
    public static class LoansP2P
    {
        static readonly object L = new object(); static JObject _doc; static JObject _set; static DateTime _setAt = DateTime.MinValue;
        static readonly Regex RxLogin = new Regex("^[a-z0-9_]{1,25}$");
        static string Dir { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); string root = string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d; var dir = Path.Combine(root, "economy"); Directory.CreateDirectory(dir); return dir; } }
        static string P { get { return Path.Combine(Dir, "p2p_loans.json"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        static string Cur { get { return Economy.CurrencyName; } }

        public static JObject Defaults() { return new JObject { { "On", true }, { "MinAmount", 10 }, { "MaxAmount", 100000 }, { "MaxInterestPct", 50 }, { "MinDays", 1 }, { "MaxDays", 30 }, { "MaxOpenRequests", 1 }, { "MaxActiveBorrowed", 3 }, { "MaxOpenOffers", 10 }, { "RequestHours", 72 }, { "OfferHours", 24 } }; }
        public static JObject Settings()
        {
            lock (L)
            {
                string p = Path.Combine(Dir, "p2p_settings.json"); DateTime t = File.Exists(p) ? File.GetLastWriteTimeUtc(p) : DateTime.MinValue;
                if (_set != null && t == _setAt) return _set;
                var d = Defaults(); try { if (File.Exists(p)) foreach (var kv in JObject.Parse(File.ReadAllText(p, Encoding.UTF8).TrimStart((char)0xFEFF))) d[kv.Key] = kv.Value; else File.WriteAllText(p, d.ToString(), new UTF8Encoding(false)); } catch (Exception ex) { Clog.Warn("p2p", "p2p_settings.json unreadable, using defaults: " + ex.Message); }
                _set = d; _setAt = t; return d;
            }
        }
        static double S(string k) { try { return (double)Settings()[k]; } catch (Exception) { return (double)Defaults()[k]; } }
        public static JObject Public() { var s = Settings(); var o = new JObject(); foreach (var p in s.Properties()) o[p.Name] = p.Value; return o; }

        static JObject Doc()
        {
            if (_doc != null) return _doc;
            try { if (File.Exists(P)) _doc = JObject.Parse(File.ReadAllText(P, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception ex) { Clog.Warn("p2p", "p2p_loans.json unreadable: " + ex.Message); if (File.Exists(P)) File.Copy(P, P + ".broken-" + Now(), true); }
            if (_doc == null) _doc = new JObject();
            foreach (var k in new[] { "requests", "offers", "loans" }) if (!(_doc[k] is JObject)) _doc[k] = new JObject();
            return _doc;
        }
        static void Save() { try { string tmp = P + ".tmp"; File.WriteAllText(tmp, Doc().ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); if (File.Exists(P)) File.Delete(P); File.Move(tmp, P); } catch (Exception ex) { Clog.Warn("p2p", "save failed: " + ex.Message); } }
        static JObject Tab(string k) { return (JObject)Doc()[k]; }
        static JObject No(string why) { return new JObject { { "ok", false }, { "error", why } }; }
        static JObject Yes(string msg, JObject data = null) { var o = new JObject { { "ok", true }, { "message", msg } }; if (data != null) o["data"] = data; return o; }
        static string Disp(string login) { try { return Boards.DisplayName(login); } catch (Exception) { return login; } }
        static string Clean(string id) { return Regex.Replace(id ?? "", "[^A-Za-z0-9_-]", ""); }
        static string NewId(string pre, string reqId) { return pre + "-" + (string.IsNullOrEmpty(reqId) ? Guid.NewGuid().ToString("N").Substring(0, 12) : Clean(reqId)); }
        static string Login(string s) { return (s ?? "").Trim().TrimStart('@').ToLowerInvariant(); }
        static long Interest(long principal, double pct) { return (long)Math.Ceiling(principal * pct / 100.0 - 1e-9); }
        static long Owed(JObject ln) { return (long)ln["principal"] + (long)ln["interest"] - (long)ln["repaid"]; }

        /// <summary>true while this person has an overdue loan (to a viewer or from the house)</summary>
        public static bool Defaulted(string login)
        {
            login = Login(login);
            lock (L) if (Tab("loans").Properties().Any(p => (string)p.Value["borrower"] == login && (string)p.Value["status"] == "defaulted")) return true;
            return Economy.HouseDefaulted(login);
        }
        public static IEnumerable<string> Logins() { lock (L) return Tab("loans").Properties().SelectMany(p => new[] { (string)p.Value["borrower"], (string)p.Value["lender"] }).Concat(Tab("requests").Properties().Select(p => (string)p.Value["borrower"])).Concat(Tab("offers").Properties().SelectMany(p => new[] { (string)p.Value["borrower"], (string)p.Value["lender"] })).Where(x => !string.IsNullOrEmpty(x)).Distinct().ToList(); }

        // ---- one entry point for the site's request queue ----
        public static JObject Handle(string login, string act, JObject s, string reqId)
        {
            try
            {
                if ((bool?)Settings()["On"] == false) return No("loans between viewers are closed right now");
                switch (act)
                {
                    case "loan_request": return Request(login, N(s, "amount"), D(s, "interestPct"), (int)N(s, "days"), reqId);
                    case "loan_offer": return Offer(login, (string)s["requestId"], Login((string)s["toLogin"]), N(s, "amount"), D(s, "interestPct"), (int)N(s, "days"), reqId);
                    case "loan_accept": return Accept(login, (string)s["offerId"], reqId);
                    case "loan_decline": return Decline(login, (string)s["offerId"]);
                    case "loan_cancel": return Cancel(login, (string)(s["targetId"] ?? s["id"]));
                    case "loan_repay": return Repay(login, (string)s["loanId"], N(s, "amount"), reqId);
                }
                return No("unknown action");
            }
            catch (Exception ex) { Clog.Warn("p2p", act + " failed: " + ex.Message); return No("something went wrong, nothing was changed"); }
        }
        static long N(JObject s, string k) { try { return (long)Math.Floor((double?)s[k] ?? 0); } catch (Exception) { return 0; } }
        static double D(JObject s, string k) { try { return (double?)s[k] ?? 0; } catch (Exception) { return 0; } }

        static string Terms(long amount, double pct, int days)
        {
            long mn = (long)S("MinAmount"), mx = (long)S("MaxAmount");
            if (amount < mn || amount > mx) return "the amount must be " + mn + " to " + mx + " " + Cur;
            if (pct < 0 || pct > S("MaxInterestPct") || double.IsNaN(pct)) return "interest must be 0 to " + S("MaxInterestPct") + "%";
            if (days < (int)S("MinDays") || days > (int)S("MaxDays")) return "the loan must run " + (int)S("MinDays") + " to " + (int)S("MaxDays") + " days";
            return null;
        }
        static void Expire()
        {
            long now = Now(); bool ch = false;
            foreach (var p in Tab("requests").Properties()) { var r = (JObject)p.Value; if ((string)r["status"] == "open" && (long)r["expiresAt"] < now) { r["status"] = "expired"; ch = true; foreach (var o in Tab("offers").Properties().Select(x => (JObject)x.Value).Where(o => (string)o["requestId"] == p.Name && (string)o["status"] == "open")) o["status"] = "expired"; } }
            foreach (var p in Tab("offers").Properties()) { var o = (JObject)p.Value; if ((string)o["status"] == "open" && (long)o["expiresAt"] < now) { o["status"] = "expired"; ch = true; } }
            foreach (var p in Tab("loans").Properties()) { var ln = (JObject)p.Value; if ((string)ln["status"] == "active" && (long)ln["dueAt"] < now && Owed(ln) > 0) { ln["status"] = "defaulted"; ln["defaultedAt"] = now; ch = true; Clog.Info("p2p", (string)ln["borrower"] + " defaulted on a loan from " + (string)ln["lender"] + " (" + Owed(ln) + " owed)"); } }
            if (ch) Save();
        }
        public static void Tick() { lock (L) Expire(); }

        // ---- borrower: request ----
        public static JObject Request(string borrower, long amount, double pct, int days, string reqId)
        {
            borrower = Login(borrower); if (!RxLogin.IsMatch(borrower) || Boards.IsBot(borrower)) return No("bad user");
            string bad = Terms(amount, pct, days); if (bad != null) return No(bad);
            lock (L)
            {
                Expire(); string id = NewId("rq", reqId); if (Tab("requests")[id] != null) return Yes("request already posted", new JObject { { "requestId", id } });
                if (Defaulted(borrower)) return No("you have an overdue loan: repay it before asking for another");
                if (Tab("requests").Properties().Count(p => (string)p.Value["borrower"] == borrower && (string)p.Value["status"] == "open") >= (int)S("MaxOpenRequests")) return No("you already have an open request: cancel it first");
                if (ActiveBorrowed(borrower) >= (int)S("MaxActiveBorrowed")) return No("you already have " + (int)S("MaxActiveBorrowed") + " active loans");
                long now = Now(); Tab("requests")[id] = new JObject { { "id", id }, { "borrower", borrower }, { "amount", amount }, { "interestPct", pct }, { "days", days }, { "status", "open" }, { "createdAt", now }, { "expiresAt", now + (long)(S("RequestHours") * 3600) } };
                Save(); return Yes("request posted: " + amount + " " + Cur + " at " + pct + "% for " + days + " days", new JObject { { "requestId", id } });
            }
        }
        static int ActiveBorrowed(string b) { return Tab("loans").Properties().Count(p => (string)p.Value["borrower"] == b && ((string)p.Value["status"] == "active" || (string)p.Value["status"] == "defaulted")); }

        // ---- lender: offer ----
        public static JObject Offer(string lender, string requestId, string toLogin, long amount, double pct, int days, string reqId)
        {
            lender = Login(lender); if (!RxLogin.IsMatch(lender) || Boards.IsBot(lender)) return No("bad user");
            string bad = Terms(amount, pct, days); if (bad != null) return No(bad);
            lock (L)
            {
                Expire(); string id = NewId("of", reqId); if (Tab("offers")[id] != null) return Yes("offer already sent", new JObject { { "offerId", id } });
                string borrower; string rq = null;
                if (!string.IsNullOrEmpty(requestId))
                {
                    var r = Tab("requests")[requestId] as JObject; if (r == null) return No("no such request"); if ((string)r["status"] != "open") return No("that request is no longer open");
                    borrower = (string)r["borrower"]; rq = requestId;
                }
                else { borrower = Login(toLogin); if (!RxLogin.IsMatch(borrower) || Boards.IsBot(borrower)) return No("pick someone to lend to"); }
                if (borrower == lender) return No("you cannot lend to yourself");
                if (Defaulted(borrower)) return No(Disp(borrower) + " has an overdue loan and cannot borrow right now");
                if (Economy.Balance(lender) < amount) return No("you only have " + Economy.Balance(lender) + " " + Cur);
                var mine = Tab("offers").Properties().Select(p => (JObject)p.Value).Where(o => (string)o["lender"] == lender && (string)o["status"] == "open").ToList();
                if (mine.Count >= (int)S("MaxOpenOffers")) return No("you have too many open offers: cancel some first");
                if (mine.Any(o => (string)o["borrower"] == borrower && ((string)o["requestId"] ?? "") == (rq ?? ""))) return No("you already have an open offer there: cancel it first");
                long now = Now();
                Tab("offers")[id] = new JObject { { "id", id }, { "requestId", rq }, { "lender", lender }, { "borrower", borrower }, { "amount", amount }, { "interestPct", pct }, { "days", days }, { "status", "open" }, { "createdAt", now }, { "expiresAt", now + (long)(S("OfferHours") * 3600) } };
                Save(); return Yes("offer sent to " + Disp(borrower) + ": " + amount + " " + Cur + " at " + pct + "% for " + days + " days", new JObject { { "offerId", id } });
            }
        }

        // ---- borrower: accept / decline ----
        public static JObject Accept(string borrower, string offerId, string reqId)
        {
            borrower = Login(borrower);
            lock (L)
            {
                Expire(); var o = Tab("offers")[offerId ?? ""] as JObject; if (o == null) return No("no such offer");
                string loanId = "ln-" + Clean(offerId); var existing = Tab("loans")[loanId] as JObject; if (existing != null && (string)o["status"] == "accepted") return Yes("already accepted", new JObject { { "loanId", loanId } });
                if ((string)o["borrower"] != borrower) return No("that offer is not for you");
                if ((string)o["status"] != "open") return No("that offer is no longer open (" + (string)o["status"] + ")");
                string lender = (string)o["lender"]; long amount = (long)o["amount"]; double pct = (double)o["interestPct"]; int days = (int)o["days"];
                if (Defaulted(borrower)) return No("you have an overdue loan: repay it first");
                if (ActiveBorrowed(borrower) >= (int)S("MaxActiveBorrowed")) return No("you already have " + (int)S("MaxActiveBorrowed") + " active loans");
                if (Economy.Balance(lender) < amount) return No(Disp(lender) + " no longer has enough " + Cur);
                string e = Economy.AwardP2p(lender, -amount, "p2p_out", "Loan to " + Disp(borrower), "p2p-" + loanId + "-out"); if (e != null) return No(Disp(lender) + " could not pay: " + e);
                e = Economy.AwardP2p(borrower, amount, "p2p_in", "Loan from " + Disp(lender), "p2p-" + loanId + "-in");
                if (e != null) { Economy.AwardP2p(lender, amount, "p2p_out", "Loan cancelled, returned", "p2p-" + loanId + "-undo"); return No("the loan fell through: " + e); }
                long now = Now(), interest = Interest(amount, pct);
                Tab("loans")[loanId] = new JObject { { "id", loanId }, { "lender", lender }, { "borrower", borrower }, { "principal", amount }, { "interestPct", pct }, { "interest", interest }, { "repaid", 0L }, { "days", days }, { "createdAt", now }, { "dueAt", now + days * 86400L }, { "status", "active" }, { "requestId", o["requestId"] } };
                o["status"] = "accepted"; o["loanId"] = loanId;
                string rq = (string)o["requestId"];
                if (!string.IsNullOrEmpty(rq)) { var r = Tab("requests")[rq] as JObject; if (r != null) { r["status"] = "filled"; r["loanId"] = loanId; } foreach (var s in Tab("offers").Properties().Select(x => (JObject)x.Value).Where(x => (string)x["requestId"] == rq && (string)x["status"] == "open")) s["status"] = "cancelled"; }
                Save(); return Yes("loan started: " + amount + " " + Cur + " from " + Disp(lender) + ", pay back " + (amount + interest) + " within " + days + " days", new JObject { { "loanId", loanId }, { "owed", amount + interest } });
            }
        }
        public static JObject Decline(string borrower, string offerId)
        {
            borrower = Login(borrower);
            lock (L)
            {
                Expire(); var o = Tab("offers")[offerId ?? ""] as JObject; if (o == null) return No("no such offer"); if ((string)o["borrower"] != borrower) return No("that offer is not for you");
                if ((string)o["status"] == "declined") return Yes("already declined"); if ((string)o["status"] != "open") return No("that offer is no longer open (" + (string)o["status"] + ")");
                o["status"] = "declined"; Save(); return Yes("offer declined");
            }
        }
        /// <summary>the borrower cancels their request (its open offers are cancelled too) or the lender cancels their own offer</summary>
        public static JObject Cancel(string login, string id)
        {
            login = Login(login);
            lock (L)
            {
                Expire(); var r = Tab("requests")[id ?? ""] as JObject;
                if (r != null)
                {
                    if ((string)r["borrower"] != login) return No("that request is not yours"); if ((string)r["status"] == "cancelled") return Yes("already cancelled"); if ((string)r["status"] != "open") return No("that request is already " + (string)r["status"]);
                    r["status"] = "cancelled"; foreach (var o in Tab("offers").Properties().Select(x => (JObject)x.Value).Where(x => (string)x["requestId"] == id && (string)x["status"] == "open")) o["status"] = "cancelled";
                    Save(); return Yes("request cancelled");
                }
                var of = Tab("offers")[id ?? ""] as JObject;
                if (of != null)
                {
                    if ((string)of["lender"] != login) return No("that offer is not yours"); if ((string)of["status"] == "cancelled") return Yes("already cancelled"); if ((string)of["status"] != "open") return No("that offer is already " + (string)of["status"]);
                    of["status"] = "cancelled"; Save(); return Yes("offer cancelled");
                }
                return No("nothing with that id");
            }
        }

        // ---- borrower: repay (amount 0 = all) ----
        public static JObject Repay(string borrower, string loanId, long amount, string reqId)
        {
            borrower = Login(borrower);
            lock (L)
            {
                var ln = Tab("loans")[loanId ?? ""] as JObject; if (ln == null) return No("no such loan"); if ((string)ln["borrower"] != borrower) return No("that loan is not yours");
                long owed = Owed(ln); if (owed <= 0 || (string)ln["status"] == "repaid") return No("that loan is already repaid");
                long bal = Economy.Balance(borrower); if (bal < 1) return No("you have no " + Cur);
                long pay = amount <= 0 ? owed : Math.Min(amount, owed); pay = Math.Min(pay, bal);
                string rid = string.IsNullOrEmpty(reqId) ? Guid.NewGuid().ToString("N").Substring(0, 12) : Clean(reqId); string lender = (string)ln["lender"];
                string e = Economy.AwardP2p(borrower, -pay, "p2p_repay", "Repaid " + Disp(lender), "p2p-rep-" + rid + "-out"); if (e != null) return No(e);
                string e2 = Economy.AwardP2p(lender, pay, "p2p_repaid", "Repayment from " + Disp(borrower), "p2p-rep-" + rid + "-in"); if (e2 != null) Clog.Warn("p2p", "lender credit failed: " + e2);
                ln["repaid"] = (long)ln["repaid"] + pay; long left = Owed(ln);
                if (left <= 0) { ln["status"] = "repaid"; ln["repaidAt"] = Now(); }
                Save(); return Yes((left <= 0 ? "loan fully repaid" : "repaid " + pay + " " + Cur + ", " + left + " left"), new JObject { { "loanId", loanId }, { "paid", pay }, { "owed", left } });
            }
        }

        // ---- views for the site ----
        static JObject LoanRow(JObject ln, bool asBorrower)
        {
            string other = (string)ln[asBorrower ? "lender" : "borrower"];
            return new JObject { { "id", ln["id"] }, { asBorrower ? "lender" : "borrower", other }, { asBorrower ? "lenderDisplay" : "borrowerDisplay", Disp(other) }, { "principal", ln["principal"] }, { "interestPct", ln["interestPct"] }, { "interest", ln["interest"] }, { "days", ln["days"] },
                { "createdAt", ln["createdAt"] }, { "dueAt", ln["dueAt"] }, { "repaid", ln["repaid"] }, { "owed", Math.Max(0, Owed(ln)) }, { "status", ln["status"] } };
        }
        static JObject OfferRow(JObject o)
        {
            return new JObject { { "id", o["id"] }, { "requestId", o["requestId"] }, { "lender", o["lender"] }, { "lenderDisplay", Disp((string)o["lender"]) }, { "borrower", o["borrower"] }, { "borrowerDisplay", Disp((string)o["borrower"]) }, { "amount", o["amount"] }, { "interestPct", o["interestPct"] }, { "days", o["days"] }, { "status", o["status"] }, { "createdAt", o["createdAt"] }, { "expiresAt", o["expiresAt"] }, { "loanId", o["loanId"] } };
        }
        static JObject RequestRow(JObject r)
        {
            int offers = Tab("offers").Properties().Count(p => (string)p.Value["requestId"] == (string)r["id"] && (string)p.Value["status"] == "open");
            return new JObject { { "id", r["id"] }, { "borrower", r["borrower"] }, { "borrowerDisplay", Disp((string)r["borrower"]) }, { "amount", r["amount"] }, { "interestPct", r["interestPct"] }, { "days", r["days"] }, { "status", r["status"] }, { "createdAt", r["createdAt"] }, { "expiresAt", r["expiresAt"] }, { "offers", offers }, { "loanId", r["loanId"] } };
        }
        public static JObject ViewOf(string login)
        {
            login = Login(login);
            lock (L)
            {
                Expire();
                var reqs = Tab("requests").Properties().Select(p => (JObject)p.Value).Where(r => (string)r["borrower"] == login).ToList();
                var offs = Tab("offers").Properties().Select(p => (JObject)p.Value).ToList();
                var loans = Tab("loans").Properties().Select(p => (JObject)p.Value).ToList();
                Func<JObject, bool> isOpen = x => (string)x["status"] == "open";
                Func<JObject, bool> live = x => (string)x["status"] == "active" || (string)x["status"] == "defaulted";
                Func<IEnumerable<JObject>, Func<JObject, bool>, int, List<JObject>> sel = (src, test, keep) => { var l = src.OrderByDescending(x => (long)x["createdAt"]).ToList(); return l.Where(test).Concat(l.Where(x => !test(x)).Take(keep)).ToList(); };
                return new JObject {
                    { "myRequests", new JArray(sel(reqs, isOpen, 10).Select(RequestRow)) },
                    { "myOffers", new JArray(sel(offs.Where(o => (string)o["lender"] == login), isOpen, 10).Select(OfferRow)) },
                    { "incoming", new JArray(offs.Where(o => (string)o["borrower"] == login && isOpen(o)).OrderByDescending(o => (long)o["createdAt"]).Select(OfferRow)) },
                    { "loans", new JObject { { "asBorrower", new JArray(sel(loans.Where(l => (string)l["borrower"] == login), live, 10).Select(l => LoanRow(l, true))) }, { "asLender", new JArray(sel(loans.Where(l => (string)l["lender"] == login), live, 10).Select(l => LoanRow(l, false))) } } } };
            }
        }
        public static JArray MarketView()
        {
            lock (L) { Expire(); return new JArray(Tab("requests").Properties().Select(p => (JObject)p.Value).Where(r => (string)r["status"] == "open").OrderByDescending(r => (long)r["createdAt"]).Take(100).Select(RequestRow)); }
        }
    }
}
