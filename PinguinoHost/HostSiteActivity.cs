using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The site's activity feed. Every channel event that goes through Program.DispatchEvent (follow, sub, resub, gift subs, bits, raids in/out, hype train end, redemptions) becomes one item in a local window (last 100, Data\runtime\site_activity.json);
    /// the Host PUSHES each new item ONCE to the site's existing POST /api/bot/events (bot key), oldest first, in batches: {events:[{id, type, user, amount?, tier?, months?, msg?, at?, refollow?}]}. The site de-duplicates by id, so a retry is harmless.
    /// Types: follow (refollow:true when that account followed before), sub, resub (months), giftsub (amount), cheer (amount), raid (amount = viewers, raid in), raid_out (staff only; amount = viewers, user = target channel),
    /// hype (amount = level, msg "Hype train level N"), redemption (user = viewer, msg = reward name). (tip and boost are not Twitch events and are not sent from here.)
    /// Ids of what was already accepted are kept in Data\runtime\site_activity_sent.json, so a restart never re-sends. No e-mails or IPs. Simulated events never appear.</summary>
    public static class SiteActivity
    {
        static readonly object L = new object(); static bool _started; static string _result = "not started"; static DateTime _lastPush = DateTime.MinValue; static List<JObject> _items; static HashSet<string> _sent; static HashSet<string> _followers;
        static string P { get { return Path.Combine(HostApi.DataDir, "runtime", "site_activity.json"); } }
        static int Window { get { return 100; } }
        static int EveryMs { get { int v; return int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_ACTIVITY_PUSH_SEC"), out v) && v > 0 ? v * 1000 : 5000; } }

        static List<JObject> Items()
        {
            if (_items != null) return _items;
            _items = new List<JObject>();
            try { if (File.Exists(P)) foreach (var t in JArray.Parse(File.ReadAllText(P, Encoding.UTF8)).OfType<JObject>()) _items.Add(t); } catch (Exception) { }
            return _items;
        }
        static string SentP { get { return Path.Combine(HostApi.DataDir, "runtime", "site_activity_sent.json"); } }
        static string FolP { get { return Path.Combine(HostApi.DataDir, "runtime", "site_activity_followers.json"); } }
        static HashSet<string> Sent()
        {
            if (_sent != null) return _sent; _sent = new HashSet<string>();
            try { if (File.Exists(SentP)) foreach (var t in JArray.Parse(File.ReadAllText(SentP, Encoding.UTF8))) _sent.Add((string)t); } catch (Exception) { }
            return _sent;
        }
        static void SaveSent() { try { var a = Sent().ToList(); if (a.Count > 400) { a = a.Skip(a.Count - 400).ToList(); _sent = new HashSet<string>(a); } Directory.CreateDirectory(Path.GetDirectoryName(SentP)); File.WriteAllText(SentP, new JArray(a).ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); } catch (Exception) { } }
        /// <summary>true when this account followed before (and remembers it)</summary>
        static bool Refollow(string user)
        {
            string k = (user ?? "").ToLowerInvariant();
            if (_followers == null) { _followers = new HashSet<string>(); try { if (File.Exists(FolP)) foreach (var t in JArray.Parse(File.ReadAllText(FolP, Encoding.UTF8))) _followers.Add((string)t); } catch (Exception) { } }
            if (_followers.Contains(k)) return true;
            _followers.Add(k); try { Directory.CreateDirectory(Path.GetDirectoryName(FolP)); File.WriteAllText(FolP, new JArray(_followers).ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); } catch (Exception) { }
            return false;
        }
        public static JObject Status() { lock (L) return new JObject { { "result", _result }, { "items", Items().Count }, { "pending", Items().Count(x => !Sent().Contains((string)x["id"])) } }; }
        public static JArray Window100() { lock (L) return new JArray(Items().Take(Window).Select(x => x.DeepClone())); }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(10000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(EveryMs); } });
        }

        static string S(Dictionary<string, object> a, string k) { object v; return a.TryGetValue(k, out v) && v != null ? Convert.ToString(v, CultureInfo.InvariantCulture) : ""; }
        static long I(Dictionary<string, object> a, string k) { long n; return long.TryParse(S(a, k), NumberStyles.Integer, CultureInfo.InvariantCulture, out n) ? n : 0; }
        static string Tier(string t) { return t == "3" ? "3000" : t == "2" ? "2000" : t == "prime" ? "prime" : "1000"; }
        static string Months(long n) { return n == 1 ? "1 month" : n + " months"; }

        /// <summary>called for every channel event (Program.DispatchEvent). Never throws.</summary>
        public static void Note(Dictionary<string, object> a)
        {
            try
            {
                if (S(a, "sim") != "" && Environment.GetEnvironmentVariable("PINGUINO_ACTIVITY_SIM") != "1") return;   // (the test switch lets simulated events through)
                string et = S(a, "eventType"), user = S(a, "userName"), type = null, label = null, tier = null, extra = null; long amount = -1;
                switch (et)
                {
                    case "TwitchFollow": type = "follow"; label = user + " followed"; break;
                    case "TwitchSub": type = "sub"; tier = Tier(S(a, "tier")); label = user + " subscribed" + (tier == "1000" ? "" : tier == "prime" ? " with Prime" : " (tier " + tier.Substring(0, 1) + ")"); break;
                    case "TwitchReSub": { type = "resub"; tier = Tier(S(a, "tier")); long m = I(a, "months"); label = user + " resubbed" + (m > 0 ? " (" + Months(m) + ")" : ""); if (m > 0) amount = m; break; }
                    case "TwitchGiftBomb": { type = "gift"; tier = Tier(S(a, "tier")); long n = Math.Max(1, I(a, "total")); amount = n; bool anon = S(a, "anonymous") == "true"; user = anon ? "Anonymous" : user; label = user + " gifted " + n + (n == 1 ? " sub" : " subs"); break; }
                    case "TwitchCheer": { type = "bits"; long b = I(a, "bits"); amount = b; label = user + " cheered " + b + " bits"; break; }
                    case "TwitchRaid": { type = "raid_in"; long v = I(a, "viewers"); amount = v; label = user + " raided with " + v + (v == 1 ? " viewer" : " viewers"); break; }
                    case "TwitchRaidOut": { type = "raid_out"; long v = I(a, "viewers"); amount = v; extra = S(a, "target"); label = "Raiding " + extra + (v > 0 ? " with " + v + (v == 1 ? " viewer" : " viewers") : ""); user = extra; break; }
                    case "TwitchHype": { if (S(a, "state") != "end") return; type = "hype"; long lv = I(a, "x.level"); amount = lv; user = "Hype train"; label = "Hype train ended at level " + lv; break; }
                    case "TwitchRedeem": { type = "redemption"; extra = S(a, "title"); long c = I(a, "cost"); if (c > 0) amount = c; label = user + " redeemed " + extra; break; }
                    default: return;
                }
                long at = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                string id = S(a, "eventId"); if (id == "") id = type + ":" + user + ":" + at;
                id = type + ":" + id;
                var it = new JObject { { "id", id }, { "at", at }, { "type", type }, { "user", user }, { "label", label } };
                if (type == "follow") it["refollow"] = Refollow(user);
                if (amount >= 0) it["amount"] = amount; if (tier != null) it["tier"] = tier; if (!string.IsNullOrEmpty(extra)) it["extra"] = extra;
                lock (L)
                {
                    var items = Items(); if (items.Any(x => (string)x["id"] == id)) return;   // EventSub redelivers: one item per event
                    items.Insert(0, it); while (items.Count > Window) items.RemoveAt(items.Count - 1);
                    try { Directory.CreateDirectory(Path.GetDirectoryName(P)); File.WriteAllText(P, new JArray(items).ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); } catch (Exception) { }
                }
            }
            catch (Exception) { }
        }

        /// <summary>one window item as the site's event: {id, type, user, amount?, tier?, months?, msg?, at, refollow?}</summary>
        internal static JObject ToEvent(JObject x)
        {
            string t = (string)x["type"]; long? amt = (long?)x["amount"];
            var e = new JObject { { "id", (string)x["id"] }, { "user", (string)x["user"] }, { "at", (long?)x["at"] ?? 0 } };
            switch (t)
            {
                case "follow": e["type"] = "follow"; if ((bool?)x["refollow"] == true) e["refollow"] = true; break;
                case "sub": e["type"] = "sub"; e["tier"] = x["tier"]; break;
                case "resub": e["type"] = "resub"; e["tier"] = x["tier"]; if (amt.HasValue) e["months"] = amt; break;
                case "gift": e["type"] = "giftsub"; e["tier"] = x["tier"]; if (amt.HasValue) e["amount"] = amt; break;
                case "bits": e["type"] = "cheer"; if (amt.HasValue) e["amount"] = amt; break;
                case "raid_in": e["type"] = "raid"; if (amt.HasValue) e["amount"] = amt; break;
                case "raid_out": e["type"] = "raid_out"; if (amt.HasValue) e["amount"] = amt; break;
                case "hype": e["type"] = "hype"; e["amount"] = amt ?? 0; e["msg"] = "Hype train level " + (amt ?? 0); break;
                case "redemption": e["type"] = "redemption"; e["msg"] = (string)x["extra"] ?? ""; break;
                default: return null;
            }
            return e;
        }

        public static void Tick()
        {
            if (!SiteHttp.Enabled("SiteActivity")) { _result = "off"; return; }
            string key = SiteHttp.Key(); if (key == "") { _result = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            List<JObject> fresh;
            lock (L) fresh = Items().Where(x => !Sent().Contains((string)x["id"])).Reverse().Take(50).Select(x => ToEvent(x)).Where(x => x != null).ToList();   // oldest first
            if (fresh.Count == 0) { if (_result == "not started") _result = "nothing to send yet"; return; }
            JObject r; int code = SiteHttp.Call("POST", "/api/bot/events", new JObject { { "events", new JArray(fresh) } }, key, out r);
            if (code == 200) { lock (L) { foreach (var e in fresh) Sent().Add((string)e["id"]); SaveSent(); } _lastPush = DateTime.UtcNow; _result = "ok (" + fresh.Count + " events sent)"; }
            else if (code == 401) _result = "site refused the key (HTTP 401)";
            else _result = code == 0 ? "site not reachable" : code == 404 ? "site has no events endpoint yet" : "site answered HTTP " + code;
        }
    }
}
