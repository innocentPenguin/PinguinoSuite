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
    /// <summary>The mods' activity feed on the site. Every channel event that goes through Program.DispatchEvent (follow, sub, resub, gift subs, bits, raids in/out, hype train end, redemptions) becomes one item;
    /// the Host PUSHES the last ~100, newest first, the whole window each time, to POST /api/bot/activity (bot key) whenever it changed (checked every 5 s) and at least once every 2 minutes.
    /// Item: {id (stable, unique), at (unix s), type: follow|sub|resub|gift|bits|raid_in|raid_out|hype|redemption, user (display name), label ("bob resubbed (14 months)"), amount?, tier? ("1000"|"2000"|"3000"|"prime"), extra?}.
    /// No ids, e-mails or IPs. Simulated events never appear. The window survives a restart (Data\runtime\site_activity.json).</summary>
    public static class SiteActivity
    {
        static readonly object L = new object(); static bool _started; static string _result = "not started"; static string _sentHash = ""; static DateTime _lastPush = DateTime.MinValue; static List<JObject> _items;
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
        public static JObject Status() { lock (L) return new JObject { { "result", _result }, { "items", Items().Count } }; }
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

        static string Hash(string s) { using (var h = SHA1.Create()) return Convert.ToBase64String(h.ComputeHash(Encoding.UTF8.GetBytes(s))); }

        public static void Tick()
        {
            if (!SiteHttp.Enabled("SiteActivity")) { _result = "off"; return; }
            string key = SiteHttp.Key(); if (key == "") { _result = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            var win = Window100(); string h = Hash(win.ToString(Newtonsoft.Json.Formatting.None));
            if (h == _sentHash && (DateTime.UtcNow - _lastPush).TotalSeconds < 120) return;
            if (win.Count == 0 && _sentHash == "") { _result = "nothing to send yet"; return; }
            JObject r; int code = SiteHttp.Call("POST", "/api/bot/activity", new JObject { { "items", win } }, key, out r);
            if (code == 200) { _sentHash = h; _lastPush = DateTime.UtcNow; _result = "ok (" + win.Count + " items)"; }
            else if (code == 401) _result = "site refused the key (HTTP 401)";
            else _result = code == 0 ? "site not reachable" : code == 404 ? "site has no activity endpoint yet" : "site answered HTTP " + code;
        }
    }
}
