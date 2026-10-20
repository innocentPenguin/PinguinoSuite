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
}
