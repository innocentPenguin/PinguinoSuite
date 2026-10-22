using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The stream recap line: the stream's numbers (follows, subs, bits, raids) and, when Twitch has one, the best clip of that stream (most views in the stream window).
    /// Used by the sb-recap automation (stream offline, off by default) and by the Test button: GET /api/recap/preview (text only) and POST /api/recap/test {post:true} (says it in chat once).
    /// Works offline: the window is the LAST stream (the economy's stream record, else the session start).</summary>
    public static class Recap
    {
        internal static Func<long, long, JObject> TestClip;   // test hook: (from, to) -> {title,url,views}

        /// <summary>start/end (unix s) of the last stream; end = now while it is still running</summary>
        public static void LastWindow(out long start, out long end)
        {
            end = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); start = Session.Start;
            long s, e; if (Economy.LastStreamWindow(out s, out e)) { start = s; end = e > 0 ? e : end; }
            if (start <= 0 || start > end) start = Math.Max(0, end - 8 * 3600);
        }

        /// <summary>the clip with the most views created inside the window (Helix GET /clips), or null</summary>
        public static JObject BestClip(long from, long to)
        {
            if (TestClip != null) return TestClip(from, to);
            try
            {
                string q = "/clips?broadcaster_id={bid}&first=100&started_at=" + Uri.EscapeDataString(DateTimeOffset.FromUnixTimeSeconds(Math.Max(0, from - 60)).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")) + "&ended_at=" + Uri.EscapeDataString(DateTimeOffset.FromUnixTimeSeconds(to + 600).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ"));
                JObject j; string err, code = TwitchApi.CallFull(HttpMethod.Get, q, out j, out err);
                if (code != "200" || j == null) return null;
                var best = (j["data"] as JArray ?? new JArray()).OfType<JObject>().OrderByDescending(c => (long?)c["view_count"] ?? 0).FirstOrDefault();
                if (best == null || string.IsNullOrEmpty((string)best["url"])) return null;
                return new JObject { { "title", (string)best["title"] }, { "url", (string)best["url"] }, { "views", (long?)best["view_count"] ?? 0 } };
            }
            catch (Exception) { return null; }
        }

        /// <summary>{ok, text, line, clip, window:{start,end}}; nothing is posted</summary>
        public static JObject Build(bool withClip = true)
        {
            long s, e; LastWindow(out s, out e);
            string line = Session.LineFor(s, e); JObject clip = withClip ? BestClip(s, e) : null;
            string text = "Thanks for tuning in! " + line + (clip != null ? " Best clip: " + (string)clip["url"] : "");
            if (text.Length > 480) text = text.Substring(0, 480);
            return new JObject { { "ok", true }, { "text", text }, { "line", line }, { "clip", clip }, { "window", new JObject { { "start", s }, { "end", e } } } };
        }
    }
}
