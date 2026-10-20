using System;
using System.Net.Http;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The Host's own idea of "is the stream live" (no website key needed): Twitch's streams endpoint, else OBS. Published to the bots as the non-persisted global pinguino.live ("1"/"0").</summary>
    public static class LiveState
    {
        static DateTime? _startedAt; static bool? _live; static string _source = "unknown"; static DateTime _at = DateTime.MinValue; static bool _started;
        public static bool? Live { get { return _live; } }
        /// <summary>!uptime: how long the stream has been live (Twitch start time when known).</summary>
        public static string UptimeLine()
        {
            if (_live != true || _startedAt == null) return "The stream is offline right now.";
            var t = DateTime.UtcNow - _startedAt.Value; if (t < TimeSpan.Zero) t = TimeSpan.Zero;
            string s = t.TotalHours >= 1 ? (int)t.TotalHours + "h " + t.Minutes + "m" : Math.Max(1, t.Minutes) + "m";
            return "The stream has been live for " + s + ".";
        }

        public static JObject Api() { return new JObject { { "ok", true }, { "live", _live }, { "source", _source }, { "checkedAgoSec", _at == DateTime.MinValue ? (int?)null : (int)(DateTime.UtcNow - _at).TotalSeconds } }; }

        public static void Start(HostCPH cph, int periodSec = 20)
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(6000); while (true) { try { Tick(cph); } catch (Exception ex) { Clog.Warn("live", "live check failed: " + ex.Message); } await Task.Delay(periodSec * 1000); } });
        }
        public static void Tick(HostCPH cph)
        {
            string forced = Environment.GetEnvironmentVariable("PINGUINO_LIVE");   // tests / sim only
            bool? v = null; string src = "unknown";
            if (forced == "1" || forced == "0") { v = forced == "1"; src = "forced"; }
            else
            {
                JToken d; string err; string code = TwitchApi.Call(HttpMethod.Get, "/streams?user_id={bid}", null, out d, out err);
                if (code == "200" && d is JArray a) { v = a.Count > 0; src = "twitch"; DateTime st; _startedAt = a.Count > 0 && DateTime.TryParse((string)a[0]["started_at"], null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out st) ? st : (DateTime?)null; }
                else { bool? o = cph.ObsStreaming(); if (o != null) { v = o; src = "obs"; } }
            }
            if (v == null) return;
            if (_live != true && v == true) SubBoard.ResetChat();
            if (_live != v) Clog.Info("live", "stream is " + (v.Value ? "LIVE" : "offline") + " (" + src + ")");
            if (v == true && _startedAt == null) _startedAt = DateTime.UtcNow;   // OBS / forced: since the Host noticed
            if (v == false) _startedAt = null;
            _live = v; _source = src; _at = DateTime.UtcNow;
            cph.SetGlobalVar("pinguino.live", v.Value ? "1" : "0", false);
        }
    }
}
