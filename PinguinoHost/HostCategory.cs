using System;
using System.IO;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The current Twitch category, kept in a file the bots read (Ivan 10-24: join answers depend on the game). Data\twitch_category.json {"game":"Fortnite","at":unixSeconds,"ok":true};
    /// ok:false + game:"" when the lookup failed. The master Host asks Helix /channels every 60 s. Readers treat the file as fresh when ok and at is within 300 s, otherwise the category is unknown.
    /// Tests: PINGUINO_TEST_CATEGORY (a name; empty = a failed lookup) makes the poll deterministic and skips Helix.</summary>
    public static class StreamCategory
    {
        static readonly object L = new object(); static bool _started;
        static string P { get { return Path.Combine(HostApi.DataDir, "twitch_category.json"); } }
        public static void EnsureStarted()
        {
            lock (L) { if (_started) return; _started = true; }
            new Thread(() => { Thread.Sleep(3000); while (true) { try { Poll(); } catch (Exception) { } Thread.Sleep(60000); } }) { IsBackground = true, Name = "category" }.Start();
        }
        /// <summary>one lookup + file write; public so a test can drive it</summary>
        public static void Poll()
        {
            string g = ""; bool ok = false;
            string tc = Environment.GetEnvironmentVariable("PINGUINO_TEST_CATEGORY");
            if (tc != null) { g = tc.Trim(); ok = g != ""; }
            else
            {
                if (HostApi.SimMode || !Lease.MayRun) return;
                try { var i = ChannelControl.Info(); if ((bool?)i["ok"] == true) { g = ((string)i["game"] ?? "").Trim(); ok = g != ""; } } catch (Exception) { }
            }
            try { File.WriteAllText(P, new JObject { { "game", ok ? g : "" }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "ok", ok } }.ToString()); } catch (Exception) { }
        }
    }
}
