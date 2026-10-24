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
            var d = new JObject { { "Enabled", false }, { "As", "helper" }, { "Prefix", "" }, { "MaxPerMinute", 4 }, { "Url", "http://127.0.0.1:8771" }, { "PollSec", 5 } };
            try { if (File.Exists(Cfg)) foreach (var p in JObject.Parse(File.ReadAllText(Cfg))) d[p.Key] = p.Value; else File.WriteAllText(Cfg, d.ToString()); } catch (Exception) { }
            d["As"] = "helper";   // Ivan 10-24: music is said by PinguinoHelper, whatever an old file says
            return d;
        }
        public static JObject Save(JObject b)
        {
            var d = Settings();
            foreach (var k in new[] { "Enabled", "As", "Prefix", "MaxPerMinute", "Url", "PollSec" }) if (b[k] != null) d[k] = b[k];
            string a = ((string)d["As"] ?? "helper").ToLowerInvariant(); a = "helper"; d["As"] = a;   // Ivan 10-24: everything about music is said by PinguinoHelper
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
                    string via; HostApi.SendAs("helper", ((string)s["Prefix"] ?? "") + t, out via); _sent.Enqueue(DateTime.UtcNow); sent++;
                }
                _since = Math.Max(_since, top); _last = "on (" + sent + " posted, up to #" + _since + ")";
            }
        }
    }
}

namespace PinguinoHost
{
    /// <summary>Ivan 10-24: everything about music is said by PinguinoHelper. Module-command replies (the Spotify module's commands) never go out as core/chat.</summary>
    public static class SongSender
    {
        public static readonly string[] SongCommands = { "sr", "request", "songrequest", "oops", "blocksong", "srclear", "skip", "voteskip", "song", "queue", "volume", "vol", "last", "pos" };
        /// <summary>the sender for a module-command reply: always helper (song commands only; other module commands keep their configured sender)</summary>
        public static string Role(string cmd, string configured) { return System.Array.IndexOf(SongCommands, (cmd ?? "").ToLowerInvariant()) >= 0 ? "helper" : (configured ?? "core"); }
        /// <summary>sets "as":"helper" on every module_command step of the song presets; returns how many steps changed</summary>
        public static int MoveToHelper(Newtonsoft.Json.Linq.JArray actions)
        {
            int n = 0;
            foreach (var a in actions.OfType<Newtonsoft.Json.Linq.JObject>())
                foreach (var st in ((a["steps"] as Newtonsoft.Json.Linq.JArray) ?? new Newtonsoft.Json.Linq.JArray()).OfType<Newtonsoft.Json.Linq.JObject>())
                    if ((string)st["type"] == "module_command" && System.Array.IndexOf(SongCommands, ((string)st["command"] ?? "").ToLowerInvariant()) >= 0 && ((string)st["as"] ?? "core") != "helper") { st["as"] = "helper"; n++; }
            return n;
        }
    }
}
