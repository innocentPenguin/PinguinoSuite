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
        /// <summary>true when the stream is live OR Offline mode is on: what timers, chimes, intros and the economy gate on (the real state in Live stays honest).</summary>
        public static bool Active { get { return OfflineMode.Enabled || _live == true || RecordingActsLive; } }
        /// <summary>what the chat bots (Helper/Chatty/B0t) follow: offline mode OR a recording that counts as live. The real Twitch state (pinguino.live) is never faked.</summary>
        public static bool BotsActLive { get { return OfflineMode.Enabled || RecordingActsLive; } }
        static volatile bool _rec; static DateTime _recSince = DateTime.MinValue;
        /// <summary>OBS is recording (paused counts); false when OBS is not connected</summary>
        public static bool Recording { get { return _rec; } }
        /// <summary>a recording counts as live ("Act live while recording" is on)</summary>
        public static bool RecordingActsLive { get { return _rec && OfflineMode.ActLiveWhileRecording; } }
        /// <summary>why the bots behave live right now: live | recording | offline-mode | idle</summary>
        public static string Source { get { return _live == true ? "live" : RecordingActsLive ? "recording" : OfflineMode.Enabled ? "offline-mode" : "idle"; } }
        /// <summary>called by the OBS client on RecordStateChanged / (dis)connect</summary>
        public static void OnRecording(bool on)
        {
            if (_rec == on) return; _rec = on; _recSince = on ? DateTime.UtcNow : DateTime.MinValue;
            Clog.Info("live", "OBS recording " + (on ? "STARTED" : "stopped") + " -> bots act live: " + (Active ? "yes (" + Source + ")" : "no"));
            OfflineMode.Publish();
        }
        /// <summary>!uptime: how long the stream has been live (Twitch start time when known).</summary>
        public static string UptimeLine()
        {
            if (_live != true && RecordingActsLive) { var rt = DateTime.UtcNow - _recSince; if (rt < TimeSpan.Zero) rt = TimeSpan.Zero; return "Not live on Twitch, but recording for " + (rt.TotalHours >= 1 ? (int)rt.TotalHours + "h " + rt.Minutes + "m" : Math.Max(1, rt.Minutes) + "m") + "."; }
            if (_live != true || _startedAt == null) return "The stream is offline right now.";
            var t = DateTime.UtcNow - _startedAt.Value; if (t < TimeSpan.Zero) t = TimeSpan.Zero;
            string s = t.TotalHours >= 1 ? (int)t.TotalHours + "h " + t.Minutes + "m" : Math.Max(1, t.Minutes) + "m";
            return "The stream has been live for " + s + ".";
        }

        // when the stream was last seen live (persisted, refreshed every check while live), so !downtime survives a Host restart
        static string SeenP { get { return System.IO.Path.Combine(HostApi.DataDir, "live_last.json"); } }
        static DateTime? _lastSeen; static bool _seenLoaded;
        static void LoadSeen() { if (_seenLoaded) return; _seenLoaded = true; try { if (System.IO.File.Exists(SeenP)) { DateTime t; if (DateTime.TryParse((string)JObject.Parse(System.IO.File.ReadAllText(SeenP))["lastLiveSeen"], null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out t)) _lastSeen = t; } } catch (Exception) { } }
        static void NoteSeen() { _lastSeen = DateTime.UtcNow; _seenLoaded = true; try { System.IO.File.WriteAllText(SeenP, new JObject { { "lastLiveSeen", _lastSeen.Value.ToString("o") } }.ToString()); } catch (Exception) { } }
        /// <summary>!downtime: how long since the last stream ended (the real state, not Offline mode).</summary>
        public static string DowntimeLine()
        {
            LoadSeen();
            if (_live == true) return "The stream is live right now.";
            if (_lastSeen == null) return "I don't know when the last stream ended yet.";
            var t = DateTime.UtcNow - _lastSeen.Value; if (t < TimeSpan.Zero) t = TimeSpan.Zero;
            string s = t.TotalDays >= 1 ? (int)t.TotalDays + "d " + t.Hours + "h" : t.TotalHours >= 1 ? (int)t.TotalHours + "h " + t.Minutes + "m" : Math.Max(1, t.Minutes) + "m";
            return "The last stream ended " + s + " ago.";
        }

        public static JObject Api() { return new JObject { { "ok", true }, { "live", _live }, { "source", _source }, { "simulation", Sim.On }, { "checkedAgoSec", _at == DateTime.MinValue ? (int?)null : (int)(DateTime.UtcNow - _at).TotalSeconds } }; }

        public static void Start(HostCPH cph, int periodSec = 20)
        {
            if (_started) return; _started = true; OfflineMode.Attach(cph);
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
            try { bool? rc = cph.ObsRecording(); if (rc != null) OnRecording(rc.Value); } catch (Exception) { }
            OfflineMode.Publish();
            if (v == null) return;
            if (_live != true && v == true) SubBoard.ResetChat();
            if (_live != v) Clog.Info("live", "stream is " + (v.Value ? "LIVE" : "offline") + " (" + src + ")");
            if (v == true && _startedAt == null) _startedAt = DateTime.UtcNow;   // OBS / forced: since the Host noticed
            if (v == false) _startedAt = null;
            if (v == true) NoteSeen(); else LoadSeen();
            _live = v; _source = src; _at = DateTime.UtcNow;
            cph.SetGlobalVar("pinguino.live", v.Value ? "1" : "0", false);
        }
    }
}
