using System;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Optional: posts the Spotify module's announcement lines (new track / song request) to chat. Off by default; the Spotify module decides which lines exist, this decides whether and as whom they are posted.</summary>
    public static class SpotifyAnnounce
    {
        static bool _started; static long _since = -1; static string _last = "off";
        static string Cfg { get { return Path.Combine(HostApi.DataDir, "spotify_announce.json"); } }
        public static string Status() { return _last; }

        public static JObject Settings()
        {
            var d = new JObject { { "Enabled", false }, { "As", "core" }, { "Prefix", "" }, { "MaxPerMinute", 4 }, { "Url", "http://127.0.0.1:8771" }, { "PollSec", 5 } };
            try { if (File.Exists(Cfg)) foreach (var p in JObject.Parse(File.ReadAllText(Cfg))) d[p.Key] = p.Value; else File.WriteAllText(Cfg, d.ToString()); } catch (Exception) { }
            return d;
        }
        public static JObject Save(JObject b)
        {
            var d = Settings();
            foreach (var k in new[] { "Enabled", "As", "Prefix", "MaxPerMinute", "Url", "PollSec" }) if (b[k] != null) d[k] = b[k];
            string a = ((string)d["As"] ?? "core").ToLowerInvariant(); if (a != "core" && a != "chat" && a != "helper") a = "core"; d["As"] = a;
            File.WriteAllText(Cfg, d.ToString()); return new JObject { { "ok", true }, { "settings", d }, { "status", _last } };
        }
        public static JObject Api() { return new JObject { { "ok", true }, { "settings", Settings() }, { "status", _last }, { "since", _since } }; }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { while (true) { int sec = 5; try { sec = Math.Max(2, (int?)Settings()["PollSec"] ?? 5); } catch (Exception) { } await Task.Delay(sec * 1000); try { Tick(); } catch (Exception ex) { _last = "error: " + ex.Message; } } });
        }
        static readonly System.Collections.Generic.Queue<DateTime> _sent = new System.Collections.Generic.Queue<DateTime>();
        static void Tick()
        {
            var s = Settings(); if ((bool?)s["Enabled"] != true) { _last = "off"; _since = -1; return; }
            if (!Lease.MayRun) return;
            string url = ((string)s["Url"] ?? "http://127.0.0.1:8771").TrimEnd('/');
            using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(4) })
            {
                string txt; try { txt = h.GetStringAsync(url + "/api/announcements?since=" + Math.Max(_since, 0)).Result; } catch (Exception) { _last = "Spotify module not reachable"; return; }
                var j = JObject.Parse(txt); long top = (long?)j["seq"] ?? 0;
                if (_since < 0) { _since = top; _last = "on (starting after #" + top + ", old lines skipped)"; return; }
                int sent = 0;
                foreach (var l in (j["lines"] as JArray ?? new JArray()).OfType<JObject>().OrderBy(l => (long?)l["seq"] ?? 0))
                {
                    long sq = (long?)l["seq"] ?? 0; if (sq <= _since) continue;
                    string t = ((string)l["text"] ?? "").Trim(); _since = Math.Max(_since, sq); if (t == "") continue;
                    while (_sent.Count > 0 && (DateTime.UtcNow - _sent.Peek()).TotalSeconds > 60) _sent.Dequeue();
                    if (_sent.Count >= Math.Max(1, (int?)s["MaxPerMinute"] ?? 4)) continue;
                    string via; HostApi.SendAs((string)s["As"] ?? "core", ((string)s["Prefix"] ?? "") + t, out via); _sent.Enqueue(DateTime.UtcNow); sent++;
                }
                _since = Math.Max(_since, top); _last = "on (" + sent + " posted, up to #" + _since + ")";
            }
        }
    }
}
