using System;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Vote-skip numbers for the Spotify module: how many votes !skip / !voteskip needs, from the people who chatted lately.
    /// Data\runtime\skipvote.json (all optional): {percent: 40, floor: 2, windowMin: 5}. need = max(floor, ceil(percent/100 * active chatters in the last windowMin minutes)); 6 -> 3, 10 -> 4, 5 -> 2, 3 -> 2.
    /// With nobody counted (the Host just started, chat is empty) nothing is sent and the module uses its own default (skip_votes, 3).</summary>
    public static class SkipVote
    {
        static JObject Cfg() { try { string f = Path.Combine(HostApi.DataDir, "skipvote.json"); return File.Exists(f) ? JObject.Parse(File.ReadAllText(f)) : new JObject(); } catch (Exception) { return new JObject(); } }
        public static int Percent() { return Math.Max(1, Math.Min(100, (int?)Cfg()["percent"] ?? 40)); }
        public static int Floor() { return Math.Max(1, (int?)Cfg()["floor"] ?? 2); }
        public static int WindowMin() { return Math.Max(1, Math.Min(60, (int?)Cfg()["windowMin"] ?? 5)); }
        public static int Need(int active, int percent, int floor) { return Math.Max(floor, (int)Math.Ceiling(active * percent / 100.0 - 1e-9)); }
        /// <summary>distinct people (bots left out) who chatted in the window; 0 = no data</summary>
        public static int Active() { return Roster.ActiveCount(WindowMin() * 60); }
        /// <summary>fills the module request: activeChatters + skipNeed (only when someone was counted)</summary>
        public static void Fill(JObject body)
        {
            int a = Active(); if (a < 1) return;
            body["activeChatters"] = a; body["skipNeed"] = Need(a, Percent(), Floor());
        }
    }
}
