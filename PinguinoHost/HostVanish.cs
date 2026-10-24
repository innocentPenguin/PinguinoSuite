using System;
using System.Collections.Generic;

namespace PinguinoHost
{
    /// <summary>!vanish (alias !disappear): the person who typed it is timed out for 1 second with the reason "poof", which clears their messages. Everyone may use it, it costs nothing,
    /// one use per person every 10 s (PINGUINO_VANISH_COOL_SEC in tests), never for mods or the broadcaster (the only reply is "mods can't vanish"). The timeout goes through the existing
    /// Host path (TimeoutReward.Ban: PinguinoB0t's own mod sign-in first, then the streamer account); no token is handled here. In --sim nothing reaches Twitch ([timeout-do] line).</summary>
    public static class Vanish
    {
        static readonly Dictionary<string, DateTime> At = new Dictionary<string, DateTime>();
        public static bool IsCommand(string cmd) { return cmd == "!vanish" || cmd == "!disappear"; }

        public static void Handle(string user, int role, Action<string> say)
        {
            string me = (user ?? "").Trim().TrimStart('@').ToLowerInvariant(); if (me == "" || Control.Synthetic) return;
            int cool = 10; int v; if (int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_VANISH_COOL_SEC"), out v)) cool = v;
            lock (At)
            {
                DateTime t; if (cool > 0 && At.TryGetValue(me, out t) && (DateTime.UtcNow - t).TotalSeconds < cool) return;   // cooling down: no reply at all
                At[me] = DateTime.UtcNow;
                if (At.Count > 2000) { var old = new List<string>(); foreach (var kv in At) if ((DateTime.UtcNow - kv.Value).TotalMinutes > 5) old.Add(kv.Key); foreach (var k in old) At.Remove(k); }
            }
            if (role >= 3 || Roster.RoleOf(me) >= 3) { say("mods can't vanish"); return; }
            if (Boards.IsBot(me) || Boards.AllBots().Contains(me)) return;
            string by = null;
            try { by = TimeoutReward.Ban(new List<string> { "core", "streamer" }, me, 1, "poof"); } catch (Exception ex) { Clog.Warn("vanish", "could not time out " + me + ": " + ex.Message); }
            Clog.Info("vanish", me + (by == null ? " could not vanish (no account could time them out)" : " vanished (timed out by " + by + ")"));
        }
    }
}
