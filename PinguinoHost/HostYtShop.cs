using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The YouTube-only shop items: "1v1" (1v1 vs Peng) and "casual" (Casual game with Peng). Only a YouTube viewer (key yt:...) can buy them with `!shop item`; Twitch and TikTok never see them.
    /// A purchase takes the points (one ledger id per order, so a repeat never charges twice), becomes an order in Data\yt_orders.json (the queue: pending / done / cancelled), pings the mods in Twitch chat and is shown
    /// as a card in Master View (GET /api/ytorders, POST /api/ytorders {action:"done"|"cancel", id}). A mod marks it done; cancel refunds the points automatically (ledger id per order, refunded once).
    /// Chat for mods: !ytorders [all], !ytorder done|cancel id. Prices / labels can be overridden in Data\yt_shop.json {"items":{"1v1":{"label":"..","price":150000,"enabled":true}}}.</summary>
    public static class YtShop
    {
        static readonly object L = new object();
        sealed class Item { public string Key, Label; public long Price; public bool On = true; }
        static string OrdersP { get { return Path.Combine(HostApi.DataDir, "yt_orders.json"); } }
        static string CfgP { get { return Path.Combine(HostApi.DataDir, "yt_shop.json"); } }

        static List<Item> Items()
        {
            var l = new List<Item> { new Item { Key = "1v1", Label = "1v1 vs Peng", Price = 150000 }, new Item { Key = "casual", Label = "Casual game with Peng", Price = 300000 } };
            try
            {
                var o = SiteHttp.ReadJ(CfgP)["items"] as JObject;
                if (o != null) foreach (var it in l) { var x = o[it.Key] as JObject; if (x == null) continue; it.Label = ((string)x["label"] ?? it.Label).Trim(); it.Price = Math.Max(1, (long?)x["price"] ?? it.Price); it.On = (bool?)x["enabled"] != false; }
            }
            catch (Exception) { }
            return l.Where(i => i.On).ToList();
        }
        public static string Norm(string k) { k = (k ?? "").Trim().ToLowerInvariant(); return k == "1v1vspeng" || k == "1v1_vs_peng" ? "1v1" : k == "casual_game" ? "casual" : k; }
        public static bool IsItem(string key) { key = Norm(key); return Items().Any(i => i.Key == key); }
        static string Pts(long n) { return n.ToString("N0", CultureInfo.InvariantCulture); }
        static JObject Doc() { var d = SiteHttp.ReadJ(OrdersP); if (!(d["orders"] is JArray)) d["orders"] = new JArray(); if (d["seq"] == null) d["seq"] = 0; return d; }
        static void Save(JObject d) { SiteHttp.WriteJ(OrdersP, d); }
        static int PendingCount(JObject d) { return ((JArray)d["orders"]).OfType<JObject>().Count(o => (string)o["status"] == "pending"); }

        /// <summary>the items for the one-line YouTube !shop list: "1v1 (1v1 vs Peng, 150,000 points) | casual (...)"</summary>
        public static string ShopLine()
        {
            return string.Join(" | ", Items().Select(i => i.Key + " (" + i.Label + ", " + Pts(i.Price) + " " + Economy.CurrencyName + ")"));
        }

        /// <summary>!shop 1v1 or !shop casual from a YouTube viewer (the caller already checked IsItem)</summary>
        public static void Buy(string user, string itemKey, Action<string> say)
        {
            string key = Norm(itemKey); var it = Items().FirstOrDefault(i => i.Key == key);
            string me = (user ?? "").ToLowerInvariant(), cur = Economy.CurrencyName, name = PlatformUsers.Display(me);
            if (it == null || PlatformUsers.PlatformOf(me) != "youtube") { say("@" + name + " that item is for YouTube viewers only."); return; }
            JObject order = null; string msg = null; int place = 0;
            lock (L)
            {
                var d = Doc(); var orders = (JArray)d["orders"];
                if (orders.OfType<JObject>().Any(o => (string)o["login"] == me && (string)o["status"] == "pending")) msg = "you already have an order waiting. A mod will get to it, or ask a mod to cancel it.";
                else if (Economy.Balance(me) < it.Price) msg = "you need " + Pts(it.Price) + " " + cur + " for " + it.Label + " (you have " + Pts(Economy.Balance(me)) + ").";
                else
                {
                    int id = (int)d["seq"] + 1;
                    string err = Economy.Spend("ytorder-" + id + "-" + me, me, it.Price, "shop " + it.Key);
                    if (err != null) msg = err + ".";
                    else
                    {
                        d["seq"] = id;
                        order = new JObject { { "id", id }, { "login", me }, { "display", name }, { "platform", "youtube" }, { "item", it.Key }, { "label", it.Label }, { "price", it.Price }, { "status", "pending" }, { "createdAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "resolvedAt", 0 }, { "by", "" }, { "note", "" } };
                        orders.Add(order); Save(d); place = PendingCount(d);
                    }
                }
            }
            if (order == null) { say("@" + name + " " + msg); return; }
            int oid = (int)order["id"];
            Clog.Info("ytshop", me + " bought " + it.Key + " (order #" + oid + ", " + it.Price + ")");
            say("@" + name + " you bought " + it.Label + " for " + Pts(it.Price) + " " + cur + "! You are #" + place + " in line, a mod will contact you here. Order #" + oid + ".");
            ModPing("YouTube order #" + oid + ": " + name + " bought " + it.Label + " (" + Pts(it.Price) + " " + cur + "). Mods: !ytorder done " + oid + " or !ytorder cancel " + oid + " (refunds).");
        }

        /// <summary>a plain Twitch chat line for the mods, whatever platform the buyer is on</summary>
        static void ModPing(string line)
        {
            if (HostApi.SimMode) { Console.WriteLine("[say] " + line); return; }
            System.Threading.Tasks.Task.Run(() => { try { ReplyCtx.End(); string via; HostApi.SendAs("core", line, out via); } catch (Exception ex) { Clog.Warn("ytshop", "mod ping failed: " + ex.Message); } });
        }

        public static JObject List(bool all)
        {
            lock (L)
            {
                var d = Doc(); var rows = ((JArray)d["orders"]).OfType<JObject>().Where(o => all || (string)o["status"] == "pending").Select(o => (JObject)o.DeepClone()).ToList();
                int pos = 0; foreach (var o in rows) if ((string)o["status"] == "pending") o["place"] = ++pos;
                return new JObject { { "ok", true }, { "pending", PendingCount(d) }, { "orders", new JArray(rows) }, { "items", new JArray(Items().Select(i => new JObject { { "key", i.Key }, { "label", i.Label }, { "price", i.Price } })) } };
            }
        }

        /// <summary>done | cancel (refund) one order. Resolving an order twice is refused; a refund is applied once.</summary>
        public static JObject Resolve(string action, int id, string by, string note = "")
        {
            action = (action ?? "").Trim().ToLowerInvariant(); if (action != "done" && action != "cancel") return new JObject { { "ok", false }, { "error", "action must be done or cancel" } };
            JObject o; string login, label; long price; int pending;
            lock (L)
            {
                var d = Doc(); o = ((JArray)d["orders"]).OfType<JObject>().FirstOrDefault(x => (int?)x["id"] == id);
                if (o == null) return new JObject { { "ok", false }, { "error", "no order #" + id } };
                if ((string)o["status"] != "pending") return new JObject { { "ok", false }, { "error", "order #" + id + " is already " + (string)o["status"] } };
                login = (string)o["login"]; label = (string)o["label"]; price = (long)o["price"];
                if (action == "cancel" && !Economy.Credit("ytorder-refund-" + id + "-" + login, login, price, "shop refund " + (string)o["item"])) return new JObject { { "ok", false }, { "error", "the refund failed, the order stays pending" } };
                o["status"] = action == "done" ? "done" : "cancelled"; o["resolvedAt"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); o["by"] = by ?? ""; o["note"] = note ?? ""; Save(d); pending = PendingCount(d);
            }
            Clog.Info("ytshop", (by ?? "api") + " " + (action == "done" ? "finished" : "cancelled") + " order #" + id + " (" + login + ", " + label + ")");
            string name = PlatformUsers.Display(login);
            HostApi.SayYouTube("@" + name + " " + (action == "done" ? "your order #" + id + " (" + label + ") is done, thank you!" : "your order #" + id + " (" + label + ") was cancelled and " + Pts(price) + " " + Economy.CurrencyName + " were refunded."));
            return new JObject { { "ok", true }, { "order", o }, { "pending", pending } };
        }

        public static JObject Mod(JObject b)
        {
            int id; try { id = (int)Math.Round((double)(b?["id"] ?? 0)); } catch (Exception) { return new JObject { { "ok", false }, { "error", "id must be a number" } }; }
            return Resolve((string)b?["action"], id, (string)b?["by"] ?? "master view", (string)b?["note"] ?? "");
        }

        public static bool IsCommand(string cmd) { return cmd == "!ytorders" || cmd == "!ytorder"; }
        /// <summary>mods only: !ytorders [all] | !ytorder done|cancel id</summary>
        public static void Handle(string user, string cmd, string[] args, Action<string> say)
        {
            string who = "@" + PlatformUsers.Shown(user) + " ";
            if (cmd == "!ytorders")
            {
                var rows = ((JArray)List(args.Length > 0 && args[0].ToLowerInvariant() == "all")["orders"]).OfType<JObject>().ToList();
                if (rows.Count == 0) { say(who + "No YouTube orders waiting."); return; }
                say(who + "YouTube orders: " + string.Join(" | ", rows.Take(6).Select(o => "#" + (int)o["id"] + " " + (string)o["display"] + ": " + (string)o["label"] + ((string)o["status"] == "pending" ? "" : " (" + (string)o["status"] + ")"))) + (rows.Count > 6 ? " ... +" + (rows.Count - 6) + " more" : ""));
                return;
            }
            int id; string act = args.Length > 0 ? args[0].ToLowerInvariant() : "";
            if ((act != "done" && act != "cancel") || args.Length < 2 || !int.TryParse(args[1].TrimStart('#'), out id)) { say(who + "!ytorder done id | !ytorder cancel id (refunds). See !ytorders."); return; }
            var res = Resolve(act, id, PlatformUsers.Shown(user));
            say(who + ((bool?)res["ok"] == true ? "Order #" + id + (act == "done" ? " marked done." : " cancelled and refunded.") : (string)res["error"] + "."));
        }
    }
}
