using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Stream footer that shows the channel's subscribers: T3 first (diamond), then T2 (gold), then T1. Names come from Twitch's subscriber list (needs the channel:read:subscriptions permission the streamer
    /// sign-in already asks for), or from the subs seen chatting this stream (badge tier) when Scope = "chat" or the list is unavailable.</summary>
    public static class SubBoard
    {
        class S { public string Name; public int Tier; public long Seen; }
        static readonly object L = new object();
        static readonly Dictionary<string, S> Chat = new Dictionary<string, S>();
        static List<S> Api_ = new List<S>(); static long ApiAt; static string ApiNote = "not fetched yet"; static bool _started;
        static string SettingsP { get { return Path.Combine(HostApi.DataDir, "subfooter_settings.json"); } }

        public static JObject Settings()
        {
            var d = new JObject { { "Enabled", true }, { "Scope", "all" }, { "Height", 64 }, { "FontSize", 30 }, { "Font", "Segoe UI" }, { "Speed", 70 }, { "Gap", 48 }, { "Opacity", 0.7 }, { "Background", "0a0a0b" },
                { "BorderColor", "ff9900" }, { "T1Color", "f2f0ec" }, { "T2Color", "ffc933" }, { "T3Color", "9be8ff" }, { "ShowT1", true }, { "ShowT2", true }, { "ShowT3", true }, { "MaxNames", 300 },
                { "Title", "SUBS" }, { "TierMarks", true }, { "RefreshMin", 10 }, { "ExcludeBroadcaster", true } };
            try { if (File.Exists(SettingsP)) { foreach (var p in JObject.Parse(File.ReadAllText(SettingsP))) d[p.Key] = p.Value; } else File.WriteAllText(SettingsP, d.ToString()); } catch (Exception) { }
            return d;
        }
        public static JObject Save(JObject b)
        {
            var d = Settings(); foreach (var p in b.Properties()) if (d[p.Name] != null) d[p.Name] = p.Value;
            string sc = ((string)d["Scope"] ?? "all").ToLowerInvariant(); d["Scope"] = sc == "chat" ? "chat" : "all";
            File.WriteAllText(SettingsP, d.ToString()); _apiNow = true; return new JObject { { "ok", true }, { "settings", d } };
        }
        static volatile bool _apiNow;

        /// <summary>every chat line from a subscriber (tier 1-3): the chat list for this stream.</summary>
        public static void Note(string display, int tier)
        {
            if (tier <= 0 || string.IsNullOrEmpty(display)) return;
            lock (L) { Chat[display.ToLowerInvariant()] = new S { Name = display, Tier = tier, Seen = DateTimeOffset.UtcNow.ToUnixTimeSeconds() }; }
        }
        public static void ResetChat() { lock (L) Chat.Clear(); }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () =>
            {
                await Task.Delay(9000);
                while (true)
                {
                    try { Refresh(false); } catch (Exception ex) { ApiNote = "error: " + ex.Message; }
                    for (int i = 0; i < 30 && !_apiNow; i++) await Task.Delay(1000);
                    _apiNow = false;
                }
            });
        }
        /// <summary>fetch Twitch's subscriber list (paged) when it is due; force = now.</summary>
        public static void Refresh(bool force)
        {
            var s = Settings(); if (((string)s["Scope"] ?? "all") != "all") { ApiNote = "chat scope"; return; }
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            if (!force && ApiAt > 0 && now - ApiAt < Math.Max(1, (int?)s["RefreshMin"] ?? 10) * 60 && !_apiNow) return;
            var list = new List<S>(); string after = ""; string err = "";
            var cr = HostApi.StreamerCreds(); string tok = (string)cr["UserToken"] ?? "", cid = (string)cr["ClientId"] ?? "", bid = (string)cr["BroadcasterId"] ?? "";
            if (tok == "" || cid == "" || bid == "") err = "the streamer account is not signed in";
            else using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(10) })
            {
                for (int page = 0; page < 40 && err == ""; page++)
                {
                    try
                    {
                        var rq = new HttpRequestMessage(HttpMethod.Get, HostApi.Helix + "/subscriptions?broadcaster_id=" + bid + "&first=100" + (after == "" ? "" : "&after=" + Uri.EscapeDataString(after)));
                        rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                        var r = h.SendAsync(rq).Result; string txt = r.Content.ReadAsStringAsync().Result;
                        if (!r.IsSuccessStatusCode) { err = (int)r.StatusCode == 401 || (int)r.StatusCode == 403 ? "HTTP " + (int)r.StatusCode + " (the streamer sign-in needs the subscriptions permission: sign in again)" : "HTTP " + (int)r.StatusCode; break; }
                        var j = JObject.Parse(txt);
                        foreach (var x in j["data"] as JArray ?? new JArray())
                        {
                            if ((bool?)s["ExcludeBroadcaster"] != false && ((string)x["user_id"] ?? "") == bid) continue;
                            string t = (string)x["tier"] ?? "1000"; int tier = t == "3000" ? 3 : t == "2000" ? 2 : 1;
                            list.Add(new S { Name = (string)x["user_name"] ?? (string)x["user_login"] ?? "?", Tier = tier });
                        }
                        after = (string)j["pagination"]?["cursor"] ?? ""; if (after == "") break;
                    }
                    catch (Exception ex) { err = ex.Message; }
                }
            }
            lock (L) { if (err == "") { Api_ = list; ApiAt = now; ApiNote = "Twitch list (" + list.Count + " subs)"; } else ApiNote = "Twitch list unavailable: " + err; }
        }

        /// <summary>ordered names for the footer: T3, T2, T1; inside a tier alphabetical.</summary>
        public static JObject Api()
        {
            var s = Settings(); bool all = ((string)s["Scope"] ?? "all") == "all";
            List<S> src; string note;
            lock (L)
            {
                if (all && ApiAt > 0) { src = Api_.ToList(); note = ApiNote; }
                else { src = Chat.Values.ToList(); note = all ? "subs seen chatting this stream (" + ApiNote + ")" : "subs seen chatting this stream"; }
            }
            int max = Math.Max(1, (int?)s["MaxNames"] ?? 300);
            var names = src.Where(x => (bool?)s["ShowT" + x.Tier] != false).OrderByDescending(x => x.Tier).ThenBy(x => x.Name, StringComparer.OrdinalIgnoreCase).Take(max)
                .Select(x => new JObject { { "name", x.Name }, { "tier", x.Tier } });
            return new JObject { { "ok", true }, { "settings", s }, { "names", new JArray(names) }, { "source", note }, { "fetchedAgoSec", ApiAt == 0 ? (int?)null : (int)(DateTimeOffset.UtcNow.ToUnixTimeSeconds() - ApiAt) },
                { "counts", new JObject { { "t1", src.Count(x => x.Tier == 1) }, { "t2", src.Count(x => x.Tier == 2) }, { "t3", src.Count(x => x.Tier == 3) } } } };
        }
    }
}
