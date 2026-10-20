using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Chat announcements for hype trains and channel goals (EventSub). Settings in Data\runtime\announce.json: HypeOn / GoalsOn (default on), lines with {level} {total} {top} {description} {current} {target}.
    /// Only start and finish are announced (never the progress ticks), each id once; everything goes through HostApi.SendAs, which also drops an identical line said in the last 30 s.</summary>
    public static class Announce
    {
        static readonly object L = new object();
        static readonly HashSet<string> _done = new HashSet<string>();
        static string PathF { get { return Path.Combine(HostApi.DataDir, "announce.json"); } }

        static JObject Settings()
        {
            JObject s = null;
            try { if (File.Exists(PathF)) s = JObject.Parse(File.ReadAllText(PathF, Encoding.UTF8)); } catch (Exception) { }
            if (s == null)
            {
                s = new JObject { { "HypeOn", true }, { "GoalsOn", true },
                    { "HypeBegin", "Hype train started! Everybody in, let's go! innoce108Hello" }, { "HypeEnd", "Hype train finished at level {level}! Thank you {top} and everyone who joined in!" },
                    { "GoalReached", "Channel goal reached: {description}! Thank you all!" }, { "GoalEnded", "The goal {description} has ended at {current}/{target}. Thank you for the support!" } };
                try { File.WriteAllText(PathF, s.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            }
            return s;
        }

        static string A(Dictionary<string, object> a, string k) { object o; return a.TryGetValue(k, out o) && o != null ? Convert.ToString(o) : ""; }

        public static void OnEvent(Dictionary<string, object> a)
        {
            try
            {
                string et = A(a, "eventType"); if (et != "TwitchHype" && et != "TwitchGoal") return;
                string state = A(a, "state"), id = A(a, "x.id"); var s = Settings(); string line = "";
                if (et == "TwitchHype")
                {
                    if ((bool?)s["HypeOn"] == false) return;
                    if (state == "begin") line = (string)s["HypeBegin"];
                    else if (state == "end")
                    {
                        string top = "";
                        try { var tc = JArray.Parse(A(a, "x.topContributions")); var f = tc.OfType<JObject>().OrderByDescending(x => (long?)x["total"] ?? 0).FirstOrDefault(); if (f != null) top = (string)f["user_name"] ?? (string)f["user_login"] ?? ""; } catch (Exception) { }
                        line = ((string)s["HypeEnd"] ?? "").Replace("{level}", A(a, "x.level")).Replace("{total}", A(a, "x.total")).Replace("{top}", top == "" ? "everybody" : "@" + top);
                    }
                }
                else
                {
                    if ((bool?)s["GoalsOn"] == false) return;
                    if (state == "end")
                    {
                        bool ok = A(a, "x.isAchieved").ToLowerInvariant() == "true";
                        line = ((string)(ok ? s["GoalReached"] : s["GoalEnded"]) ?? "").Replace("{description}", A(a, "x.description") == "" ? A(a, "x.type") : A(a, "x.description")).Replace("{current}", A(a, "x.current")).Replace("{target}", A(a, "x.target"));
                    }
                }
                if (string.IsNullOrWhiteSpace(line)) return;
                lock (L) { string key = et + ":" + state + ":" + id; if (id != "" && !_done.Add(key)) return; if (_done.Count > 500) _done.Clear(); }
                string via; HostApi.SendAs("core", line.Trim(), out via);
            }
            catch (Exception ex) { Clog.Warn("announce", "announcement failed: " + ex.Message); }
        }
    }
}
