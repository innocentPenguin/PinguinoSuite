using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>"Get a sub": Twitch has no API to gift a sub, so buying this spends points and creates a "sub owed" ticket that a mod fulfils by hand (gift the sub on Twitch, then mark it done).
    /// Ticket {id, buyer, at, status pending|fulfilled|refunded, price, by?, doneAt?, note?}. Shipped OFF (enabled=false, price=0). Settings + tickets: Data\economy\sub_tickets.json.
    /// Buy: chat "!shop sub" or the site shop item "get_sub". Mods: "!subowed" (list), "!subdone &lt;user&gt;" (fulfilled), "!subrefund &lt;user&gt;" (cancel + points back); API GET /api/subtickets, POST /api/subtickets {action: fulfil|refund|settings, id|login, by}.
    /// Limits: one pending per buyer, a per-buyer and a global monthly cap, a per-buyer cooldown. Ledger label "Bought: Get a sub" (refund "Refund: Get a sub"). Every purchase and refund uses a unique ledger id, so a retry never charges twice.</summary>
    public static class SubTickets
    {
        static readonly object L = new object();
        static string P { get { return Path.Combine(HostApi.DataDir, "economy", "sub_tickets.json"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        static JObject Defaults() { return new JObject { { "enabled", false }, { "price", 0 }, { "maxPendingPerUser", 1 }, { "monthlyCapUser", 1 }, { "monthlyCapGlobal", 10 }, { "cooldownHours", 72 } }; }
        static JObject Doc()
        {
            var d = SiteHttp.ReadJ(P); var s = Defaults();
            if (d["settings"] is JObject o) foreach (var p in o.Properties()) s[p.Name] = p.Value;
            d["settings"] = s; if (!(d["tickets"] is JArray)) d["tickets"] = new JArray(); return d;
        }
        static void Save(JObject d) { Directory.CreateDirectory(Path.GetDirectoryName(P)); SiteHttp.WriteJ(P, d); }
        static long N(JObject s, string k) { return (long?)s[k] ?? 0; }
        public static bool Enabled() { lock (L) { var s = (JObject)Doc()["settings"]; return (bool?)s["enabled"] == true && N(s, "price") > 0; } }
        public static long Price() { lock (L) return N((JObject)Doc()["settings"], "price"); }
        static string Month(long at) { return DateTimeOffset.FromUnixTimeSeconds(at).ToString("yyyy-MM", CultureInfo.InvariantCulture); }

        /// <summary>buy a ticket. Returns null on success (ticket id in `id`), otherwise the reason (short, safe to say in chat). `reqId` makes a retry idempotent (site request id).</summary>
        public static string Buy(string login, string reqId, out string id)
        {
            login = (login ?? "").Trim().TrimStart('@').ToLowerInvariant(); id = null;
            lock (L)
            {
                var d = Doc(); var s = (JObject)d["settings"]; var tk = (JArray)d["tickets"]; long now = Now(); long price = N(s, "price");
                if (!string.IsNullOrEmpty(reqId)) { var again = tk.OfType<JObject>().FirstOrDefault(t => (string)t["reqId"] == reqId); if (again != null) { id = (string)again["id"]; return null; } }
                if ((bool?)s["enabled"] != true || price <= 0) return "Get a sub is not open right now";
                if (login == "") return "bots cannot buy this";
                var mine = tk.OfType<JObject>().Where(t => (string)t["buyer"] == login && (string)t["status"] != "refunded").ToList();
                if (mine.Count(t => (string)t["status"] == "pending") >= Math.Max(1, N(s, "maxPendingPerUser"))) return "you already have a sub waiting to be gifted";
                string mo = Month(now);
                if (mine.Count(t => Month((long)t["at"]) == mo) >= N(s, "monthlyCapUser")) return "you already got your sub for this month";
                if (tk.OfType<JObject>().Count(t => (string)t["status"] != "refunded" && Month((long)t["at"]) == mo) >= N(s, "monthlyCapGlobal")) return "all subs for this month are taken, try next month";
                long last = mine.Select(t => (long)t["at"]).DefaultIfEmpty(0).Max();
                if (last > 0 && now - last < N(s, "cooldownHours") * 3600) return "you have to wait a bit before buying another one";
                id = "st-" + now + "-" + (tk.Count + 1);
                string err = Economy.Spend("subowed-" + id, login, price, "Bought: Get a sub"); if (err != null) { id = null; return err; }
                tk.Add(new JObject { { "id", id }, { "buyer", login }, { "at", now }, { "status", "pending" }, { "price", price }, { "reqId", reqId ?? "" } });
                Save(d);
            }
            ModAudit.Log(login, "viewer", "get_sub bought", id);
            try { ChannelLore.SayCore("@innocentpenguin_ " + login + " bought a sub with points! It is waiting in the Suite (Economy > Sub tickets) or !subowed, gift it and then !subdone " + login + "."); } catch (Exception) { }
            return null;
        }

        static JObject Find(JArray tk, string idOrLogin, string status)
        {
            idOrLogin = (idOrLogin ?? "").Trim().TrimStart('@').ToLowerInvariant();
            return tk.OfType<JObject>().Where(t => (status == null || (string)t["status"] == status) && ((string)t["id"] == idOrLogin || (string)t["buyer"] == idOrLogin)).OrderBy(t => (long)t["at"]).FirstOrDefault();
        }

        public static JObject Fulfil(string idOrLogin, string by)
        {
            lock (L)
            {
                var d = Doc(); var t = Find((JArray)d["tickets"], idOrLogin, "pending"); if (t == null) return new JObject { { "ok", false }, { "error", "no pending ticket for that" } };
                t["status"] = "fulfilled"; t["by"] = by ?? ""; t["doneAt"] = Now(); Save(d);
                ModAudit.Log(by, "mod", "get_sub fulfilled", (string)t["buyer"] + " " + (string)t["id"]);
                return new JObject { { "ok", true }, { "ticket", t } };
            }
        }

        public static JObject Refund(string idOrLogin, string by, string note)
        {
            lock (L)
            {
                var d = Doc(); var t = Find((JArray)d["tickets"], idOrLogin, "pending"); if (t == null) return new JObject { { "ok", false }, { "error", "no pending ticket for that" } };
                Economy.Credit("subowed-refund-" + (string)t["id"], (string)t["buyer"], (long)t["price"], "Refund: Get a sub");
                t["status"] = "refunded"; t["by"] = by ?? ""; t["doneAt"] = Now(); if (!string.IsNullOrEmpty(note)) t["note"] = note; Save(d);
                ModAudit.Log(by, "mod", "get_sub refunded", (string)t["buyer"] + " " + (string)t["id"]);
                return new JObject { { "ok", true }, { "ticket", t } };
            }
        }

        public static JObject Report()
        {
            lock (L)
            {
                var d = Doc(); var tk = ((JArray)d["tickets"]).OfType<JObject>().OrderByDescending(t => (long)t["at"]).ToList();
                return new JObject { { "ok", true }, { "settings", d["settings"] }, { "pending", tk.Count(t => (string)t["status"] == "pending") }, { "tickets", new JArray(tk.Take(200)) } };
            }
        }

        public static JObject SetSettings(JObject b)
        {
            lock (L)
            {
                var d = Doc(); var s = (JObject)d["settings"];
                foreach (var k in new[] { "enabled", "price", "maxPendingPerUser", "monthlyCapUser", "monthlyCapGlobal", "cooldownHours" })
                    if (b[k] != null) { if (k == "enabled") s[k] = (bool)b[k]; else s[k] = Math.Max(0, (long)b[k]); }
                d["settings"] = s; Save(d); return new JObject { { "ok", true }, { "settings", s } };
            }
        }

        public static JObject Api(string method, JObject body)
        {
            if (method == "GET") return Report();
            string a = ((string)body["action"] ?? "").ToLowerInvariant(), by = (string)body["by"] ?? "suite";
            if (a == "fulfil" || a == "fulfill") return Fulfil((string)body["id"] ?? (string)body["login"], by);
            if (a == "refund") return Refund((string)body["id"] ?? (string)body["login"], by, (string)body["note"]);
            if (a == "settings") return SetSettings(body);
            return new JObject { { "ok", false }, { "error", "action must be fulfil, refund or settings" } };
        }

        // ---- chat ----
        public static bool IsModCommand(string cmd) { return cmd == "!subowed" || cmd == "!subdone" || cmd == "!subrefund"; }
        public static void HandleMod(string user, string cmd, string[] args, Action<string> say)
        {
            if (cmd == "!subowed")
            {
                var pend = (Report()["tickets"] as JArray).OfType<JObject>().Where(t => (string)t["status"] == "pending").Select(t => (string)t["buyer"]).ToList();
                say("@" + user + " subs owed: " + (pend.Count == 0 ? "none." : string.Join(", ", pend) + ". Gift each one on Twitch, then !subdone <name>.")); return;
            }
            if (args.Length == 0) { say("@" + user + " " + cmd + " <name>"); return; }
            var r = cmd == "!subdone" ? Fulfil(args[0], user) : Refund(args[0], user, null);
            say("@" + user + " " + ((bool)r["ok"] ? (cmd == "!subdone" ? "marked as gifted: " : "refunded: ") + (string)r["ticket"]["buyer"] + "." : (string)r["error"] + "."));
        }
        /// <summary>!shop sub</summary>
        public static void HandleBuy(string user, Action<string> say)
        {
            string id; string err = Buy(user, null, out id);
            say("@" + user + " " + (err == null ? "done! " + Economy.CurrencyName + " taken, a mod will gift you a sub on Twitch soon." : err + "."));
        }
        public static string ShopLine()
        {
            if (!Enabled()) return null; long price = Price();
            return "Get a sub (" + price.ToString("N0", CultureInfo.InvariantCulture) + " " + Economy.CurrencyName + ", a mod gifts you a real sub): !shop sub";
        }
    }
}
