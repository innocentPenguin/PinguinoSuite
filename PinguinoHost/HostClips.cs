using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>GET /api/clips-dump (loopback): every clip of the channel from Helix GET /clips, saved to Data\clips\clips.json
    /// [{id,title,url,view_count,created_at,duration,creator_name,game_id,is_featured}]. Helix hands out at most about 1000 clips per time window, so the history is fetched year by year
    /// and any window that comes back full is split in halves until it is not. Uses the Host's own streamer sign-in (read only). Returns {ok,count,requests,error}.</summary>
    public static class ClipsDump
    {
        static readonly object L = new object(); static int _requests; static string _error = "";
        public static JObject Run(DateTime? from = null)
        {
            lock (L)
            {
                _requests = 0; _error = ""; var byId = new Dictionary<string, JObject>(); var start = from ?? new DateTime(2016, 1, 1, 0, 0, 0, DateTimeKind.Utc); var end = DateTime.UtcNow.AddMinutes(1);
                for (var y = start; y < end && _error == ""; y = y.AddYears(1)) Window(y, y.AddYears(1) < end ? y.AddYears(1) : end, byId, 0);
                if (_error != "" && byId.Count == 0) return new JObject { { "ok", false }, { "count", 0 }, { "requests", _requests }, { "error", _error } };
                var rows = new JArray(byId.Values.OrderBy(x => (string)x["created_at"], StringComparer.Ordinal));
                string dir = Path.Combine(ClipsRoot(), "clips"); Directory.CreateDirectory(dir);
                string f = Path.Combine(dir, "clips.json"), tmp = f + ".tmp"; File.WriteAllText(tmp, rows.ToString(Newtonsoft.Json.Formatting.Indented), new UTF8Encoding(false)); if (File.Exists(f)) File.Delete(f); File.Move(tmp, f);
                Clog.Info("clips", "clip dump saved: " + rows.Count + " clips, " + _requests + " requests" + (_error != "" ? " (stopped early: " + _error + ")" : ""));
                return new JObject { { "ok", _error == "" }, { "count", rows.Count }, { "requests", _requests }, { "error", _error } };
            }
        }
        static string ClipsRoot() { string dd = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(dd), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(dd) : dd; }

        // one time window; a window that returns 900+ clips is cut in two (Helix truncates around 1000)
        static void Window(DateTime a, DateTime b, Dictionary<string, JObject> byId, int depth)
        {
            if (_error != "" || _requests > 600) { if (_requests > 600 && _error == "") _error = "stopped after 600 requests"; return; }
            var got = new Dictionary<string, JObject>(); string after = ""; int pages = 0;
            do
            {
                string q = "/clips?broadcaster_id={bid}&first=100&started_at=" + Uri.EscapeDataString(a.ToString("yyyy-MM-ddTHH:mm:ssZ")) + "&ended_at=" + Uri.EscapeDataString(b.ToString("yyyy-MM-ddTHH:mm:ssZ")) + (after != "" ? "&after=" + Uri.EscapeDataString(after) : "");
                JObject j; string err, code = TwitchApi.CallFull(HttpMethod.Get, q, out j, out err); _requests++;
                if (code == "429") { System.Threading.Thread.Sleep(5000); continue; }
                if (code != "200" || j == null) { _error = "HTTP " + code + (err != "" ? ": " + err : ""); return; }
                foreach (var c in (j["data"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    string id = (string)c["id"]; if (string.IsNullOrEmpty(id)) continue;
                    got[id] = new JObject { { "id", id }, { "title", c["title"] }, { "url", c["url"] }, { "view_count", c["view_count"] }, { "created_at", c["created_at"] }, { "duration", c["duration"] }, { "creator_name", c["creator_name"] }, { "game_id", c["game_id"] }, { "is_featured", c["is_featured"] } };
                }
                after = (string)j["pagination"]?["cursor"] ?? ""; pages++;
            } while (after != "" && pages < 12);
            if (got.Count >= 900 && (b - a).TotalHours > 2 && depth < 12) { var mid = a.AddTicks((b - a).Ticks / 2); Window(a, mid, byId, depth + 1); Window(mid, b, byId, depth + 1); }
            foreach (var kv in got) byId[kv.Key] = kv.Value;
        }
    }
    /// <summary>Clip picking rules shared by every bot that posts a clip (Host shoutouts, lore clip lines, Chatty, Helper).
    ///  * Own channel (PickOwn): featured clips from the last 2 weeks only, most viewed first.
    ///  * Someone else's channel (PickFor, shoutouts): their featured clips first, then the most viewed, all time.
    ///  * Never repeat any of the last 3 clips sent: one shared list for all bots in Data\runtime\clips_recent.json [{id,ts,by}], newest last; anyone who posts a clip calls Mark.
    /// Clip ids are Twitch slugs; a clip.twitch.tv URL or a plain id are both accepted.</summary>
    public static class ClipPick
    {
        public const int NoRepeat = 3, OwnDays = 14, Keep = 30;
        static readonly object L = new object();
        public static Func<string, DateTime?, List<JObject>> TestFetch;   // test hook: (broadcaster id, since) -> clips
        static string RecentPath { get { return Path.Combine(HostApi.DataDir, "clips_recent.json"); } }

        public static string IdOf(string urlOrId)
        {
            string s = (urlOrId ?? "").Trim(); int q = s.IndexOfAny(new[] { '?', '#' }); if (q >= 0) s = s.Substring(0, q);
            s = s.TrimEnd('/'); int i = s.LastIndexOf('/'); return (i >= 0 ? s.Substring(i + 1) : s).ToLowerInvariant();
        }
        static JArray LoadRecent()
        {
            try
            {   // a reservation (pending) that nobody confirmed within 2 minutes is dropped: the bot that reserved it never posted
                if (File.Exists(RecentPath)) { long old = DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 120; return new JArray(JArray.Parse(File.ReadAllText(RecentPath, Encoding.UTF8).TrimStart((char)0xFEFF)).Where(x => !((bool?)x["pending"] == true && ((long?)x["ts"] ?? 0) < old))); }
            }
            catch (Exception) { }
            return new JArray();
        }
        /// <summary>ids of the last n clips sent by any bot, newest last</summary>
        public static List<string> Recent(int n = NoRepeat) { lock (L) return LoadRecent().OfType<JObject>().Select(x => (string)x["id"] ?? "").Where(x => x != "").Reverse().Take(n).Reverse().ToList(); }
        /// <summary>true when this clip is one of the last 3 sent (by any bot)</summary>
        public static bool WasRecent(string urlOrId) { string id = IdOf(urlOrId); return id != "" && Recent().Contains(id); }
        /// <summary>record a clip that was just posted (by = which bot / feature)</summary>
        public static void Mark(string urlOrId, string by = "host") { lock (L) MarkLocked(urlOrId, by, false); }
        static void MarkLocked(string urlOrId, string by, bool pending)
        {
            string id = IdOf(urlOrId); if (id == "") return;
            var a = LoadRecent(); var o = new JObject { { "id", id }, { "ts", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "by", by } }; if (pending) o["pending"] = true; a.Add(o);
            while (a.Count > Keep) a.RemoveAt(0);
            Save(a);
        }
        static void Save(JArray a) { try { Directory.CreateDirectory(HostApi.DataDir); File.WriteAllText(RecentPath, a.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); } catch (Exception) { } }
        /// <summary>the sender confirms a reserved clip was posted (pending off) or, with release, gives it back (the post timed out). Returns false when the newest entry is not this clip.</summary>
        public static bool Confirm(string urlOrId, bool release)
        {
            string id = IdOf(urlOrId); lock (L)
            {
                var a = LoadRecent(); var e = a.OfType<JObject>().LastOrDefault(x => (string)x["id"] == id); if (e == null || a.Last != e) return false;
                if (release) { if ((bool?)e["pending"] == true) a.Remove(e); else return false; } else e.Remove("pending");
                Save(a); return true;
            }
        }
        /// <summary>pick an own-channel clip AND reserve it in one step, so two bots asking at the same moment get different clips. Confirm() it once posted, or Confirm(release) if the post failed.</summary>
        public static JObject PickOwnReserved(string by)
        {
            lock (L) { var c = PickOwn(); if (c != null) MarkLocked((string)c["id"], by ?? "bot", true); return c; }
        }
        static readonly Dictionary<string, KeyValuePair<DateTime, List<JObject>>> Cache = new Dictionary<string, KeyValuePair<DateTime, List<JObject>>>();
        /// <summary>Helix clip list cached for 60 s per channel/window, so several bots polling do not hit Helix each time</summary>
        static List<JObject> Cached(string bid, DateTime? since)
        {
            string key = bid + "|" + (since == null ? "all" : since.Value.ToString("yyyyMMddHH"));
            lock (Cache) { KeyValuePair<DateTime, List<JObject>> v; if (Cache.TryGetValue(key, out v) && (DateTime.UtcNow - v.Key).TotalSeconds < 60) return v.Value; }
            var l = Fetch(bid, since); lock (Cache) { Cache[key] = new KeyValuePair<DateTime, List<JObject>>(DateTime.UtcNow, l); if (Cache.Count > 50) Cache.Clear(); }
            return l;
        }
        public static void TestResetCache() { lock (Cache) Cache.Clear(); }
        /// <summary>clips of a channel from Helix, newest window first (since = null: all time). Each row {id,title,url,view_count,created_at,duration,is_featured,thumbnail_url}.</summary>
        public static List<JObject> Fetch(string broadcasterId, DateTime? since = null)
        {
            if (TestFetch != null) return TestFetch(broadcasterId, since);
            var res = new List<JObject>(); string after = ""; int pages = 0;
            do
            {
                string q = "/clips?broadcaster_id=" + Uri.EscapeDataString(broadcasterId) + "&first=100" + (since != null ? "&started_at=" + Uri.EscapeDataString(since.Value.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")) : "") + (after != "" ? "&after=" + Uri.EscapeDataString(after) : "");
                JObject j; string err, code = TwitchApi.CallFull(HttpMethod.Get, q, out j, out err);
                if (code != "200" || j == null) { Clog.Warn("clips", "clip list failed (HTTP " + code + (err != "" ? ": " + err : "") + ")"); break; }
                foreach (var c in (j["data"] as JArray ?? new JArray()).OfType<JObject>()) res.Add(c);
                after = (string)j["pagination"]?["cursor"] ?? ""; pages++;
            } while (after != "" && pages < 3);
            return res;
        }
        /// <summary>the direct video URL Multi can play, from a Helix thumbnail (".../x-preview-480x272.jpg" -> ".../x.mp4"); "" when the thumbnail has no such form</summary>
        public static string MediaUrl(JObject clip)
        {
            string t = (string)clip["media_url"] ?? ""; if (t != "") return t;
            t = (string)clip["thumbnail_url"] ?? ""; int i = t.IndexOf("-preview-", StringComparison.Ordinal);
            return i > 0 && t.StartsWith("https://") ? t.Substring(0, i) + ".mp4" : "";
        }
        static bool Featured(JObject c) { return (bool?)c["is_featured"] == true; }
        static long Views(JObject c) { return (long?)c["view_count"] ?? 0; }
        /// <summary>order for a pick: featured first, then most viewed; clips among the last 3 sent go last (used only when nothing else is left and allowRepeat)</summary>
        public static List<JObject> Rank(IEnumerable<JObject> clips, bool featuredOnly = false)
        {
            return clips.Where(c => !string.IsNullOrEmpty((string)c["id"]) && (!featuredOnly || Featured(c))).OrderByDescending(Featured).ThenByDescending(Views).ToList();
        }
        /// <summary>a clip of THIS channel for a bot to post: featured, made in the last 2 weeks, not one of the last 3 sent. Returns null when there is none (say nothing then). Call Mark(url) after posting.</summary>
        public static JObject PickOwn()
        {
            string bid = TwitchApi.BroadcasterId(); if (bid == "" && TestFetch == null) return null;
            var rec = Recent();
            return Rank(Cached(bid, DateTime.UtcNow.AddDays(-OwnDays)), true).FirstOrDefault(c => !rec.Contains(IdOf((string)c["id"])));
        }
        /// <summary>a clip of another streamer for a shoutout: their featured clips first, then the most viewed (all time), skipping the last 3 sent and clips without a playable video URL. null = no clips.</summary>
        public static JObject PickFor(string broadcasterId, bool needMedia = true)
        {
            var rec = Recent(); var ranked = Rank(Cached(broadcasterId, null)).Where(c => !needMedia || MediaUrl(c) != "").ToList();
            return ranked.FirstOrDefault(c => !rec.Contains(IdOf((string)c["id"]))) ?? ranked.FirstOrDefault();
        }
    }
}
