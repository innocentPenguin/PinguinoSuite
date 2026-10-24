using System;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The "Latest Group" popup after an alert. One show and one hide per run of alerts: an alert that comes while the popup is up only pushes the end time out
    /// (now + PopupSeconds), so the popup never hides early for the later alert and never flickers hide/show in between.</summary>
    static class PopupHold
    {
        const string ActionName = "Alerts: show Latest Group";
        static readonly object L = new object();
        static DateTime _until = DateTime.MinValue; static bool _up;

        /// <summary>test hook: replaces the clock sleep and the OBS calls (scene, source, visible)</summary>
        internal static Action<string, string, bool> TestVisible;

        static int Ms(JObject al) { double s = (double?)al["PopupSeconds"] ?? 10; return (int)(Math.Max(1, Math.Min(120, s)) * 1000); }

        /// <summary>called before the popup action is started in the background: true = the popup is already up and its end was pushed out, nothing to start</summary>
        internal static bool TryExtend(JObject action)
        {
            if (action == null || (string)action["name"] != ActionName) return false;
            lock (L)
            {
                if (!_up) return false;
                var end = DateTime.UtcNow.AddMilliseconds(Ms(AlertCfg.Settings()));
                if (end > _until) _until = end;
                return true;
            }
        }

        /// <summary>step "popup_hold": shows the source, keeps it up until the (pushed out) end time, hides it. Scene, source and seconds come from alerts_settings.json.</summary>
        internal static string Run(bool test)
        {
            var al = AlertCfg.Settings(); string sc = (string)al["PopupScene"], so = (string)al["PopupSource"]; int ms = Ms(al);
            if (test) return "(dry run) would show " + sc + " / " + so + " for " + ms + " ms";
            lock (L) { _up = true; _until = DateTime.UtcNow.AddMilliseconds(ms); }
            string r = Set(sc, so, true);
            try
            {
                while (true)
                {
                    double left; lock (L) left = (_until - DateTime.UtcNow).TotalMilliseconds;
                    if (left <= 0) break;
                    Thread.Sleep((int)Math.Min(left, 250) + 1);
                }
            }
            finally { lock (L) _up = false; Set(sc, so, false); }
            return r + "; hidden after " + ms + " ms+";
        }

        static string Set(string sc, string so, bool on)
        {
            if (TestVisible != null) { TestVisible(sc, so, on); return "test " + (on ? "show" : "hide"); }
            try { return Program.ObsSource(sc, so, on ? "true" : "false") ? "OBS source " + so + " -> " + on : "OBS not connected or refused: source " + so; }
            catch (Exception ex) { return "OBS error: " + ex.Message; }
        }
    }

    public static partial class Auto
    {
        /// <summary>one-time (marker "popuphold1"): the saved popup action's show / delay / hide steps become one popup_hold step (alert_settings stays in front of it).</summary>
        internal static void MakePopupHold()
        {
            var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray();
            if (seeded.Count > 0 && System.Linq.Enumerable.Any(seeded, v => (string)v == "popuphold1")) return;
            foreach (var a in (JArray)doc["actions"])
            {
                if ((string)a["name"] != "Alerts: show Latest Group") continue;
                var steps = a["steps"] as JArray; if (steps == null || steps.Count != 4) continue;
                if ((string)steps[0]["type"] == "alert_settings" && (string)steps[1]["type"] == "obs_source" && (string)steps[1]["visible"] == "true" && (string)steps[2]["type"] == "delay" && (string)steps[3]["type"] == "obs_source" && (string)steps[3]["visible"] == "false")
                    a["steps"] = new JArray { steps[0], new JObject { { "type", "popup_hold" } } };
            }
            seeded.Add("popuphold1"); doc["seeded"] = seeded; Save(doc);
        }
    }
}
