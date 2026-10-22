using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Points rework. Every number is a key in Data\economy\settings.json (hot reloaded, no restart).
    ///  * WATCH: only while live, paid per FULL WatchIntervalMin stretch (a viewer who leaves before the next mark gets nothing for the partial stretch). The rate is picked at the moment of payment (viewer / sub T1 / T2 / T3).
    ///  * EntryBonus once per stream; RaidArrival on top for people who arrive inside a raid window.
    ///  * Cheers (real chat cheers only), subs, gift subs, gift recipients, tips, follows (once ever), raid leader.
    ///  * Every award has a unique event id: the same id twice applies once (EventSub replays, reconnects).
    ///  * Per-stream ledger for the site: doc["pstreams"] -> streams[{id,label,start,end,live,total,rows:[{at,type,label,delta}]}] (newest first, 60 streams x 200 rows per person).</summary>
    public static partial class Economy
    {
        static readonly string[] PointsKeys = { "WatchV2", "WatchIntervalMin", "WatchViewer", "WatchSubT1", "WatchSubT2", "WatchSubT3", "EntryBonus", "CheerLow", "CheerMid", "CheerHigh", "CheerMidFrom", "CheerHighFrom",
            "SubT1", "SubT2", "SubT3", "GiftRecipient", "TipCurve", "TipFloorPerUsd", "FollowBonus", "RaidArrival", "RaidLeader", "RaidLeaderMin", "RaidWindowMin" };

        static void PointsDefaults(JObject d)
        {
            d["WatchV2"] = true; d["WatchIntervalMin"] = 5; d["WatchViewer"] = 10; d["WatchSubT1"] = 15; d["WatchSubT2"] = 20; d["WatchSubT3"] = 30; d["EntryBonus"] = 100;
            d["CheerLow"] = 10; d["CheerMid"] = 11; d["CheerHigh"] = 15; d["CheerMidFrom"] = 500; d["CheerHighFrom"] = 1000;
            d["SubT1"] = 6000; d["SubT2"] = 12000; d["SubT3"] = 30000; d["GiftRecipient"] = 1500;
            d["TipCurve"] = new JArray { new JArray { 1, 1250 }, new JArray { 5, 7000 }, new JArray { 10, 20000 } }; d["TipFloorPerUsd"] = 1250;
            d["FollowBonus"] = 150; d["RaidArrival"] = 150; d["RaidLeader"] = 1000; d["RaidLeaderMin"] = 4; d["RaidWindowMin"] = 10;
        }

        static double PS(string k) { lock (L) return D(Settings()[k]); }
        static bool WatchV2 { get { if (Environment.GetEnvironmentVariable("PINGUINO_ECONOMY_V2") == "0") return false; lock (L) return (bool?)Settings()["WatchV2"] != false; } }   // the env switch lets the old per-minute tests keep running

        // ================= the calculators (pure: settings in, points out) =================
        public static long CheerPoints(long bits)
        {
            if (bits <= 0) return 0;
            double rate = bits >= PS("CheerHighFrom") ? PS("CheerHigh") : bits >= PS("CheerMidFrom") ? PS("CheerMid") : PS("CheerLow");
            return (long)Math.Round(bits * rate);
        }
        public static long SubPoints(int tier) { return (long)Math.Round(PS(tier >= 3 ? "SubT3" : tier == 2 ? "SubT2" : "SubT1")); }
        public static long WatchRate(int tier) { return (long)Math.Round(PS(tier >= 3 ? "WatchSubT3" : tier == 2 ? "WatchSubT2" : tier == 1 ? "WatchSubT1" : "WatchViewer")); }
        public static long TipPoints(double usd)
        {
            if (usd <= 0) return 0;
            JArray curve; double floor = PS("TipFloorPerUsd"); lock (L) curve = (JArray)Settings()["TipCurve"].DeepClone();
            var pts = curve.OfType<JArray>().Where(a => a.Count >= 2).Select(a => new[] { D(a[0]), D(a[1]) }).OrderBy(a => a[0]).ToList();
            double v = usd * floor;
            if (pts.Count > 0)
            {
                if (usd < pts[0][0]) v = usd * floor;
                else if (usd >= pts[pts.Count - 1][0])
                {
                    var last = pts[pts.Count - 1]; double slope = pts.Count > 1 ? (last[1] - pts[pts.Count - 2][1]) / Math.Max(0.0001, last[0] - pts[pts.Count - 2][0]) : floor;
                    v = last[1] + (usd - last[0]) * slope;
                }
                else for (int i = 0; i + 1 < pts.Count; i++)
                    if (usd >= pts[i][0] && usd <= pts[i + 1][0]) { v = pts[i][1] + (usd - pts[i][0]) * (pts[i + 1][1] - pts[i][1]) / Math.Max(0.0001, pts[i + 1][0] - pts[i][0]); break; }
            }
            return (long)Math.Round(Math.Max(v, usd * floor));
        }

        /// <summary>dry-run calculator: GET/POST /api/economy/preview {type, amount, tier}. Nothing is paid.</summary>
        public static JObject Preview(JObject q)
        {
            string type = ((string)q["type"] ?? "").ToLowerInvariant(); double amt = D(q["amount"] ?? q["bits"] ?? q["usd"] ?? q["viewers"]); int tier; int.TryParse(((string)q["tier"] ?? "0").Replace("prime", "1"), out tier);
            long pts; string how;
            switch (type)
            {
                case "watch": pts = WatchRate(tier); how = "per " + PS("WatchIntervalMin") + " min, " + (tier > 0 ? "sub T" + tier : "viewer") + " rate"; break;
                case "entry": pts = (long)PS("EntryBonus"); how = "once per stream"; break;
                case "cheer": pts = CheerPoints((long)amt); how = amt + " bits"; break;
                case "sub": case "resub": pts = SubPoints(tier); how = "tier " + Math.Max(1, tier); break;
                case "gift": pts = SubPoints(tier) * Math.Max(1, (long)Math.Max(1, amt)); how = Math.Max(1, (long)amt) + " sub(s) tier " + Math.Max(1, tier); break;
                case "gift_recipient": pts = (long)PS("GiftRecipient"); how = "gift sub received"; break;
                case "tip": pts = TipPoints(amt); how = "$" + amt.ToString("0.##", CultureInfo.InvariantCulture); break;
                case "follow": pts = (long)PS("FollowBonus"); how = "once per account, ever"; break;
                case "raid_in": case "raid_arrival": pts = (long)PS("RaidArrival"); how = "on top of the entry bonus"; break;
                case "raid_out": case "raid_leader": pts = amt >= PS("RaidLeaderMin") ? (long)PS("RaidLeader") : 0; how = amt + " viewers (needs " + PS("RaidLeaderMin") + "+)"; break;
                default: return new JObject { { "ok", false }, { "error", "type must be watch, entry, cheer, sub, gift, gift_recipient, tip, follow, raid_in or raid_leader" } };
            }
            return new JObject { { "ok", true }, { "type", type }, { "amount", amt }, { "tier", tier }, { "points", pts }, { "detail", how }, { "dryRun", true } };
        }

        // ================= per-stream ledger =================
        static JObject PStreams() { var d = Doc(); var p = d["pstreams"] as JObject; if (p == null) d["pstreams"] = p = new JObject(); return p; }
        static JObject PStream(string sid, long start = 0)
        {
            var ps = PStreams(); var s = ps[sid] as JObject;
            if (s == null)
            {
                if (start == 0) start = sid == "off" ? 0 : DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                string label = sid == "off" ? "Between streams" : "Stream " + DateTimeOffset.FromUnixTimeSeconds(start).ToLocalTime().ToString("MMM d, HH:mm", CultureInfo.InvariantCulture);
                ps[sid] = s = new JObject { { "id", sid }, { "label", label }, { "start", start }, { "end", null }, { "users", new JObject() } };
                var old = ps.Properties().Where(p => p.Name != "off").OrderByDescending(p => D(p.Value["start"])).Skip(60).Select(p => p.Name).ToList(); foreach (var k in old) ps.Remove(k);
            }
            return s;
        }
        static string CurSid() { lock (L) { var st = StreamDoc(); return (bool?)st["open"] == true && !string.IsNullOrEmpty((string)st["id"]) ? (string)st["id"] : "off"; } }

        /// <summary>caller holds L</summary>
        static void PRow(string sid, string login, string type, string label, long delta, string id)
        {
            var s = PStream(sid); var us = (JObject)s["users"]; var u = us[login] as JObject; if (u == null) us[login] = u = new JObject { { "total", 0L }, { "rows", new JArray() } };
            var rows = (JArray)u["rows"]; foreach (var r in rows) if ((string)r["id"] == id && id != null) return;
            u["total"] = (long)D(u["total"]) + delta;
            rows.Add(new JObject { { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "type", type }, { "label", label }, { "delta", delta }, { "id", id } });
            while (rows.Count > 200) rows.RemoveAt(0);
        }

        /// <summary>the `streams` list of one person for the site (newest stream first, rows newest first)</summary>
        public static JArray StreamsView(string login, string curSid = null)
        {
            login = Canon(Boards.AliasMap(), login); var o = new JArray();
            lock (L)
            {
                curSid = curSid ?? CurSid();
                foreach (var s in PStreams().Properties().Select(p => (JObject)p.Value).OrderByDescending(s => D(s["start"]) > 0 ? D(s["start"]) : double.MaxValue).Take(60))
                {
                    var u = s["users"][login] as JObject; if (u == null) continue;
                    var rows = new JArray(((JArray)u["rows"]).Reverse().Select(r => new JObject { { "at", r["at"] }, { "type", r["type"] }, { "label", r["label"] }, { "delta", r["delta"] } }));
                    var e = new JObject { { "id", s["id"] }, { "label", s["label"] }, { "start", s["start"] }, { "end", s["end"] }, { "total", u["total"] }, { "rows", rows } };
                    if ((string)s["id"] == curSid && curSid != "off") e["live"] = true;
                    o.Add(e);
                }
            }
            return o;
        }

        // ================= awards =================
        /// <summary>pays one event once (unique id). Returns null when paid or already paid, else the refusal.</summary>
        static string PayEvent(string sid, string login, long amount, string type, string label, string id)
        {
            login = Canon(Boards.AliasMap(), login); if (login == "" || amount <= 0) return "nothing to pay";
            if (Boards.IsBot(login) || login == Streamer()) return "not paid to bots or the streamer";
            if (!Sim.IsSim(login)) lock (L) if (Ledger()[id] != null) return null;
            string err = Award(login, amount, type, label, id); if (err != null) return err;
            if (!Sim.IsSim(login)) lock (L) { PRow(sid, login, type, label, amount, id); Save(); }
            return null;
        }

        // test hooks
        internal static Func<string, int> TestTier; internal static bool TestNoChatters;
        static int TierOf(string login)
        {
            if (TestTier != null) return TestTier(login);
            var su = SubsImport.UserInfo(login); if (su == null || (bool?)su["lapsed"] == true) return 0; return Math.Max(0, (int?)su["tier"] ?? 0);
        }

        /// <summary>one watch step for everybody present NOW (called by the minute tick while live). Pays each person per full interval; absent for a while = state dropped (partial stretch earns nothing).</summary>
        internal static int WatchStep(long now, IEnumerable<string> present, string sid)
        {
            double intervalMin = Math.Max(0.01, PS("WatchIntervalMin")); long ivSec = (long)Math.Round(intervalMin * 60), slack = Math.Min(5, ivSec / 10), gap = Math.Max(150, ivSec / 2);
            JObject w; lock (L) { var d = Doc(); w = d["watch"] as JObject; if (w == null || (string)w["sid"] != sid) d["watch"] = w = new JObject { { "sid", sid }, { "users", new JObject() } }; }
            var users = (JObject)w["users"]; var here = new HashSet<string>(present); int paidN = 0; long entry = (long)PS("EntryBonus"), arrival = (long)PS("RaidArrival");
            foreach (var c in here)
            {
                JObject st; lock (L) st = users[c] as JObject;
                if (st != null && now - (long)D(st["last"]) > gap) { lock (L) users.Remove(c); st = null; }   // was away: the partial stretch earns nothing
                if (st == null)
                {
                    lock (L) users[c] = new JObject { { "paidTo", now }, { "last", now }, { "n", 0 } };
                    if (entry > 0) PayEvent(sid, c, entry, "other", "Joined the stream", "entry:" + sid + ":" + c);
                    bool inRaid = false; lock (L)
                    {
                        var r = Doc()["raid"] as JObject;
                        if (r != null && (string)r["sid"] == sid && now - (long)D(r["at"]) <= (long)(PS("RaidWindowMin") * 60) && D(r["arrived"]) < D(r["viewers"]) && (string)r["from"] != c) { r["arrived"] = D(r["arrived"]) + 1; inRaid = true; }
                    }
                    if (inRaid && arrival > 0) PayEvent(sid, c, arrival, "raid_in", "Raid arrival", "raidin:" + sid + ":" + c);
                    continue;
                }
                lock (L) st["last"] = now;
                while (now - (long)D(st["paidTo"]) >= ivSec - slack)
                {
                    int tier = TierOf(c); long pts = WatchRate(tier); int n = (int)D(st["n"]) + 1;
                    string label = "Watched " + intervalMin.ToString("0.##", CultureInfo.InvariantCulture) + " min" + (tier > 0 ? " (sub T" + tier + " rate)" : "");
                    lock (L)
                    {
                        string rid = "w:" + sid + ":" + c + ":" + n; st["paidTo"] = (long)D(st["paidTo"]) + ivSec; st["n"] = n;
                        var earned = (JObject)Doc()["earned"]; var e = (JObject)(earned[c] ?? (earned[c] = new JObject { { "points", 0.0 }, { "minutes", 0.0 } }));
                        e["points"] = D(e["points"]) + pts; Periods.AddBuffered(c, "points", pts);
                        var mon = (JObject)Doc()["months"]; string month = DateTime.UtcNow.ToString("yyyy-MM"); var mm = (JObject)(mon[month] ?? (mon[month] = new JObject())); var m = (JObject)(mm[c] ?? (mm[c] = new JObject { { "points", 0.0 }, { "minutes", 0.0 } })); m["points"] = D(m["points"]) + pts;
                        PRow(sid, c, "watch", label, pts, rid);
                    }
                    paidN++;
                }
            }
            lock (L) { foreach (var k in users.Properties().Where(p => !here.Contains(p.Name) && now - (long)D(p.Value["last"]) > gap).Select(p => p.Name).ToList()) users.Remove(k); Save(); }
            return paidN;
        }

        // ================= events (EventSub) =================
        static int TierArg(object t) { int v; string s = Convert.ToString(t, CultureInfo.InvariantCulture) ?? ""; if (s == "3000") return 3; if (s == "2000") return 2; if (s == "1000") return 1; if (int.TryParse(s, out v)) return Math.Max(1, Math.Min(3, v)); return 1; }

        /// <summary>called for every Twitch event after it was recorded. `refollow` comes from the follow history.</summary>
        public static void PointsEvent(Dictionary<string, object> a, bool refollow = false)
        {
            if (!Lease.MayRun) return;
            if (a.ContainsKey("sim") && Convert.ToString(a["sim"]) == "true") return;   // simulated events never pay
            Func<string, string> g = k => { object v; return a.TryGetValue(k, out v) ? Convert.ToString(v, CultureInfo.InvariantCulture) ?? "" : ""; };
            string et = g("eventType"), user = Norm(g("userName")), eid = g("eventId"), sid = CurSid(); int tier = TierArg(g("tier")); long n; long.TryParse(g("bits"), out n);
            if (user == "" || user == "anonymous") { if (et != "TwitchRaid") return; }
            Func<string, string> id = k => k + ":" + (eid != "" ? eid : et + ":" + user + ":" + g("bits") + g("viewers") + g("total") + ":" + DateTime.UtcNow.ToString("yyyyMMddHHmm"));
            try
            {
                switch (et)
                {
                    case "TwitchCheer":
                        { string bt = g("bitsType").ToLowerInvariant(); if (bt == "extension" || bt == "power_up" || bt == "combo") return;   // Bits in Extensions / Power-ups are not chat cheers
                          PayEvent(sid, user, CheerPoints(n), "cheer", "Cheer " + n + " bits", id("cheer")); break; }
                    case "TwitchSub": PayEvent(sid, user, SubPoints(tier), "sub", "Sub T" + tier, id("sub")); break;
                    case "TwitchReSub": PayEvent(sid, user, SubPoints(tier), "sub", "Resub T" + tier, id("sub")); break;
                    case "TwitchGiftBomb": { long total; long.TryParse(g("total"), out total); total = Math.Max(1, total); PayEvent(sid, user, SubPoints(tier) * total, "gift", "Gifted " + total + " sub" + (total == 1 ? "" : "s") + " T" + tier, id("gift")); break; }
                    case "TwitchGiftRecipient": PayEvent(sid, user, (long)PS("GiftRecipient"), "gift", "Received a gift sub", id("giftrx")); break;
                    case "TwitchFollow": if (!refollow) PayEvent(sid, user, (long)PS("FollowBonus"), "follow", "Follow", "follow:" + user); break;   // one id per account for ever
                    case "TwitchRaid":
                        {
                            long v; long.TryParse(g("viewers"), out v); string key = eid != "" ? eid : user + ":" + v + ":" + DateTime.UtcNow.ToString("yyyyMMddHHmm");
                            lock (L) { var d = Doc(); var cur = d["raid"] as JObject; if (cur == null || (string)cur["key"] != key) { d["raid"] = new JObject { { "key", key }, { "sid", sid }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "from", user }, { "viewers", v }, { "arrived", 0 } }; Save(); } }
                            if (user != "" && v >= PS("RaidLeaderMin")) PayEvent(sid, user, (long)PS("RaidLeader"), "raid_out", "Raided with " + v + " viewers", "raidlead:" + key);
                            break;
                        }
                }
            }
            catch (Exception ex) { Clog.Warn("economy", "points event failed: " + ex.Message); }
        }

        /// <summary>POST /api/economy/event {type, login, amount, tier, id, viewers}: tips (no EventSub for them) and manual/test awards. Same rules and ids as the live events.</summary>
        public static JObject EventApi(JObject b)
        {
            string type = ((string)b["type"] ?? "").ToLowerInvariant(), login = Norm((string)b["login"]); string id = (string)b["id"]; if (login == "") return new JObject { { "ok", false }, { "error", "login is required" } };
            if (string.IsNullOrEmpty(id)) return new JObject { { "ok", false }, { "error", "id is required (a unique id per event keeps a retry from paying twice)" } };
            var pv = Preview(b); if (pv["ok"] != null && !(bool)pv["ok"]) return pv; long pts = (long)pv["points"]; string sid = CurSid(); string err = null; double amt = D(b["amount"]);
            if (type == "tip") { err = PayEvent(sid, login, pts, "tip", "Tip $" + amt.ToString("0.##", CultureInfo.InvariantCulture), "tip:" + id); if (err == null) RecordTip(login, amt, id); }
            else
            {
                var a = new Dictionary<string, object> { { "userName", login }, { "eventId", id }, { "tier", (string)b["tier"] ?? "1" }, { "bits", (long)amt }, { "viewers", (long)amt }, { "total", (long)amt }, { "bitsType", (string)b["bitsType"] ?? "" } };
                a["eventType"] = type == "cheer" ? "TwitchCheer" : type == "sub" ? "TwitchSub" : type == "resub" ? "TwitchReSub" : type == "gift" ? "TwitchGiftBomb" : type == "gift_recipient" ? "TwitchGiftRecipient" : type == "follow" ? "TwitchFollow" : type == "raid_out" || type == "raid_leader" ? "TwitchRaid" : "";
                if ((string)a["eventType"] == "") return new JObject { { "ok", false }, { "error", "this type is paid by the stream tick, not by an event" } };
                PointsEvent(a, (bool?)b["refollow"] == true);
            }
            return new JObject { { "ok", err == null }, { "type", type }, { "login", login }, { "points", pts }, { "id", id }, { "error", err } };
        }

        // ---- helpers for the alert bridge ----
        public static string RootDir { get { return Root; } }
        public static double MinutesOf(string login) { login = Canon(Boards.AliasMap(), login); lock (L) { var d = Doc(); return D(d["earned"]?[login]?["minutes"]) + D(d["baseline"]?["users"]?[login]?["minutes"]); } }
        static long ParseUnix(string s) { DateTimeOffset t; return DateTimeOffset.TryParse(s ?? "", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out t) ? t.ToUnixTimeSeconds() : 0; }
        static JObject ProfileSeen(string login) { try { string f = System.IO.Path.Combine(Root, "profiles", Norm(login) + ".json"); if (File.Exists(f)) return SubsImport.ParseJ(File.ReadAllText(f))["seen"] as JObject; } catch (Exception) { } return null; }
        public static long ProfileLastSeen(string login) { var s = ProfileSeen(login); return s == null ? 0 : ParseUnix((string)s["lastSeen"]); }
        public static long ProfileFirstSeen(string login) { var s = ProfileSeen(login); return s == null ? 0 : ParseUnix((string)s["firstSeen"]); }

        /// <summary>!tip &lt;user&gt; &lt;$&gt; [id] (mods): interim tip intake. The id (given, or user+amount+minute) keeps a repeated command from paying twice.</summary>
        static string TipCommand(string by, string[] args)
        {
            double usd; if (args.Length < 2 || !double.TryParse(args[1].TrimStart('$'), NumberStyles.Float, CultureInfo.InvariantCulture, out usd) || usd <= 0) return "Usage: !tipped @user <dollars> [id]";
            string who = Norm(args[0]); string id = args.Length > 2 ? args[2] : who + ":" + usd.ToString("0.##", CultureInfo.InvariantCulture) + ":" + DateTime.UtcNow.ToString("yyyyMMddHHmm");
            var r = EventApi(new JObject { { "type", "tip" }, { "login", who }, { "amount", usd }, { "id", id } });
            if ((bool?)r["ok"] != true) return "Tip not paid: " + (string)r["error"];
            return "Thank you for the $" + usd.ToString("0.##", CultureInfo.InvariantCulture) + " tip, " + Boards.DisplayName(who) + "! +" + Num((long)r["points"]) + " " + CurrencyName + ".";
        }

        /// <summary>lifetime tip totals per person (tipped = {total USD, count, last unix s}); the id list keeps a retry from counting twice. Mirrored into the profile file as `tipped`.</summary>
        static void RecordTip(string login, double usd, string id)
        {
            login = Canon(Boards.AliasMap(), login); if (Sim.IsSim(login)) return; JObject t;
            lock (L)
            {
                var tips = Doc()["tips"] as JObject; if (tips == null) Doc()["tips"] = tips = new JObject();
                var u = tips[login] as JObject; if (u == null) tips[login] = u = new JObject { { "total", 0.0 }, { "count", 0 }, { "last", 0L }, { "ids", new JArray() } };
                var ids = (JArray)u["ids"]; if (ids.Any(x => (string)x == id)) return;
                ids.Add(id); while (ids.Count > 100) ids.RemoveAt(0);
                u["total"] = Math.Round(D(u["total"]) + usd, 2); u["count"] = (int)D(u["count"]) + 1; u["last"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); Save();
                t = new JObject { { "total", u["total"] }, { "count", u["count"] }, { "last", u["last"] } };
            }
            try { string f = System.IO.Path.Combine(Root, "profiles", login + ".json"); if (File.Exists(f)) { var p = SubsImport.ParseJ(File.ReadAllText(f)); p["tipped"] = t; var tmp = f + ".tmp"; File.WriteAllText(tmp, p.ToString()); File.Copy(tmp, f, true); File.Delete(tmp); } } catch (Exception) { }
        }
        /// <summary>{total (USD), count, last (unix s)} - zeros when the person never tipped</summary>
        public static JObject TippedView(string login)
        {
            login = Canon(Boards.AliasMap(), login);
            lock (L) { var u = Doc()["tips"]?[login] as JObject; return u == null ? new JObject { { "total", 0.0 }, { "count", 0 }, { "last", 0L } } : new JObject { { "total", u["total"] }, { "count", u["count"] }, { "last", u["last"] } }; }
        }

        internal static long TBal(string l) { return Balance(l); }
        internal static void TReset() { lock (L) { Doc()["watch"] = null; Doc()["raid"] = null; } }
        static void StreamOpened(string sid, long start) { lock (L) { PStream(sid, start); } }
        static void StreamClosed(string sid) { lock (L) { var s = PStreams()[sid] as JObject; if (s != null) s["end"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); Doc()["watch"] = null; } }
    }
}
namespace PinguinoHost
{
    public static partial class Economy { internal static void TSetMinutes(string login, double min) { lock (L) { var e = (JObject)Doc()["earned"]; e[login] = new JObject { { "points", 0.0 }, { "minutes", min } }; } } }
}
