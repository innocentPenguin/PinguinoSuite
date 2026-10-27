using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>What the chat overlay needs to draw a line like Twitch does: the viewer's name colour (IRC tag, else Helix GET /chat/color, cached) and the badge images
    /// (IRC badges tag "subscriber/12,moderator/1" -> [{set_id,version,url?}]; Helix global + channel badge sets cached 1 h, served at GET /api/chat/badges so the overlay needs no token).</summary>
    public static class ChatMeta
    {
        static readonly object L = new object();
        static readonly Dictionary<string, KeyValuePair<string, DateTime>> _colors = new Dictionary<string, KeyValuePair<string, DateTime>>();   // userId -> (colour or "", when)
        static readonly Dictionary<string, Task<string>> _inflight = new Dictionary<string, Task<string>>();
        internal static TimeSpan ColorTtl = TimeSpan.FromHours(6), MissTtl = TimeSpan.FromMinutes(10);
        static JObject _sets; static DateTime _setsAt = DateTime.MinValue;

        public static string CleanColor(string c) { c = (c ?? "").Trim(); return Regex.IsMatch(c, "^#[0-9A-Fa-f]{6}$") ? c.ToUpperInvariant() : ""; }

        /// <summary>"subscriber/12,moderator/1" -> [{set_id:"subscriber", version:"12", url?}]</summary>
        public static JArray BadgeSets(string tag)
        {
            var r = new JArray(); JObject sets = SetsCached();
            foreach (var part in (tag ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var kv = part.Split(new[] { '/' }, 2); string set = kv[0].Trim(), ver = kv.Length > 1 ? kv[1].Trim() : "1"; if (!Regex.IsMatch(set, "^[A-Za-z0-9_\\-]{1,40}$")) continue;
                var o = new JObject { { "set_id", set }, { "version", ver } };
                string u = (string)sets?[set]?[ver]?["2x"]; if (!string.IsNullOrEmpty(u)) o["url"] = u;
                r.Add(o);
            }
            return r;
        }

        /// <summary>the colour for a viewer: the tag when valid, else the cached Helix colour. Waits at most waitMs for a first lookup; a late answer is handed to onLate (the stored line is patched).</summary>
        public static string Color(string tag, string userId, int waitMs, Action<string> onLate)
        {
            string c = CleanColor(tag); if (c != "") { Remember(userId, c); return c; }
            if (!Regex.IsMatch(userId ?? "", "^[0-9]{1,20}$")) return "";
            lock (L) { KeyValuePair<string, DateTime> e; if (_colors.TryGetValue(userId, out e) && DateTime.UtcNow - e.Value < (e.Key == "" ? MissTtl : ColorTtl)) return e.Key; }
            Task<string> t;
            lock (L) { if (!_inflight.TryGetValue(userId, out t)) { t = Task.Run(() => Fetch(userId)); _inflight[userId] = t; } }
            try { if (t.Wait(waitMs)) return t.Result; } catch (Exception) { return ""; }
            if (onLate != null) t.ContinueWith(x => { if (x.Status == TaskStatus.RanToCompletion && x.Result != "") onLate(x.Result); });
            return "";
        }
        static void Remember(string userId, string c) { if (!Regex.IsMatch(userId ?? "", "^[0-9]{1,20}$")) return; lock (L) _colors[userId] = new KeyValuePair<string, DateTime>(c, DateTime.UtcNow); }
        static string Fetch(string userId)
        {
            string c = "";
            try
            {
                JToken d; string err; string code = TwitchApi.Call(HttpMethod.Get, "/chat/color?user_id=" + userId, null, out d, out err);
                if (code == "200" && d is JArray && ((JArray)d).Count > 0) c = CleanColor((string)((JArray)d)[0]["color"]);
                else if (code != "200") Clog.Warn("chatmeta", "chat colour lookup failed (HTTP " + code + (err != "" ? ": " + err : "") + ")");
            }
            catch (Exception ex) { Clog.Warn("chatmeta", "chat colour lookup: " + ex.Message); }
            lock (L) { _colors[userId] = new KeyValuePair<string, DateTime>(c, DateTime.UtcNow); _inflight.Remove(userId); if (_colors.Count > 5000) { foreach (var k in _colors.Where(x => DateTime.UtcNow - x.Value.Value > ColorTtl).Select(x => x.Key).ToList()) _colors.Remove(k); } }
            return c;
        }

        static JObject SetsCached()
        {
            lock (L) { if (_sets != null && DateTime.UtcNow - _setsAt < TimeSpan.FromHours(1)) return _sets; }
            return _sets;   // stale or null: the caller still gets what we have; the refresh runs in the background
        }
        static int _refreshing;
        /// <summary>fills the badge cache in the background (once per hour)</summary>
        public static void WarmBadges()
        {
            lock (L) { if (_sets != null && DateTime.UtcNow - _setsAt < TimeSpan.FromHours(1)) return; }
            if (System.Threading.Interlocked.Exchange(ref _refreshing, 1) == 1) return;
            Task.Run(() => { try { Refresh(); } finally { _refreshing = 0; } });
        }
        static void Refresh()
        {
            var sets = new JObject(); int ok = 0;
            foreach (var path in new[] { "/chat/badges/global", "/chat/badges?broadcaster_id={bid}" })   // channel last: it overrides the global image of the same set/version
            {
                try
                {
                    JToken d; string err; string code = TwitchApi.Call(HttpMethod.Get, path, null, out d, out err);
                    if (code != "200" || !(d is JArray)) { Clog.Warn("chatmeta", "badge sets not loaded (" + path.Split('?')[0] + ": HTTP " + code + (err != "" ? " " + err : "") + ")"); continue; }
                    ok++;
                    foreach (JObject s in ((JArray)d).OfType<JObject>())
                    {
                        string sid = (string)s["set_id"]; if (string.IsNullOrEmpty(sid)) continue; var vs = sets[sid] as JObject; if (vs == null) { vs = new JObject(); sets[sid] = vs; }   // assign only when new: re-assigning a child clones it and later writes go to the detached copy
                        foreach (JObject v in (s["versions"] as JArray ?? new JArray()).OfType<JObject>())
                            vs[(string)v["id"] ?? ""] = new JObject { { "1x", (string)v["image_url_1x"] ?? "" }, { "2x", (string)v["image_url_2x"] ?? "" }, { "4x", (string)v["image_url_4x"] ?? "" } };
                    }
                }
                catch (Exception ex) { Clog.Warn("chatmeta", "badge sets: " + ex.Message); }
            }
            lock (L) { if (ok > 0) { _sets = sets; _setsAt = DateTime.UtcNow; } else _setsAt = DateTime.UtcNow - TimeSpan.FromMinutes(55); }   // all failed: try again in 5 minutes
        }
        /// <summary>GET /api/chat/badges</summary>
        public static JObject Api()
        {
            WarmBadges();
            JObject s; lock (L) s = _sets;
            if (s == null) { for (int i = 0; i < 40 && s == null; i++) { System.Threading.Thread.Sleep(100); lock (L) s = _sets; } }   // first call: wait a moment for the fetch
            return new JObject { { "ok", s != null }, { "sets", s ?? new JObject() }, { "cachedAt", _setsAt == DateTime.MinValue ? "" : _setsAt.ToString("o") } };
        }
    }
}
