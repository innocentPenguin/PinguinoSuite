using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Counts every line POSTed to /api/chat-in (accepted AND rejected, per platform) plus the commands, replies and send errors that followed,
    /// shows them in /api/status ("chatIn") and writes one summary line a minute while anything happened: "chat-in: yt 3, tt 0, commands 2, replies 2, send errors 0".
    /// Until now an accepted line left no trace in host.jsonl at all, so a silent break (bad token, Multi down, wrong platform) could not be seen.</summary>
    public static class ChatInStats
    {
        static readonly object L = new object();
        static readonly Dictionary<string, long> Total = new Dictionary<string, long>(), Win = new Dictionary<string, long>();
        static Timer _t; static DateTime _since = DateTime.UtcNow, _last = DateTime.MinValue; static string _lastReject = "";
        public static Action<string> TestLog;   // test hook: the summary line instead of Clog

        static string P(string platform) { return platform == "youtube" ? "yt" : platform == "tiktok" ? "tt" : platform == "twitch" ? "twitch" : string.IsNullOrEmpty(platform) ? "unknown" : platform; }
        static void Bump(string k)
        {
            lock (L)
            {
                long v; Total.TryGetValue(k, out v); Total[k] = v + 1; Win.TryGetValue(k, out v); Win[k] = v + 1; _last = DateTime.UtcNow;
                if (_t == null) _t = new Timer(_ => { try { Flush(); } catch (Exception) { } }, null, 60000, 60000);
            }
        }
        /// <summary>a line was accepted for this platform (a "!" line also counts as a command)</summary>
        public static void Accepted(string platform, string text) { Bump("accepted." + P(platform)); if ((text ?? "").TrimStart().StartsWith("!")) Bump("commands"); }
        /// <summary>a line was not run: reason = bad token | 401 token | platform | empty | own bot | not master | failed</summary>
        public static void Rejected(string platform, string reason) { lock (L) _lastReject = P(platform) + ": " + reason; Bump("rejected." + reason); Bump("rejected"); }
        static DateTime _lastAuthLog = DateTime.MinValue;
        /// <summary>a 401 on /api/chat-in (bad or missing token): counted as "401 token" and logged to host.jsonl at most once a minute with the caller (remote address + which header carried a token, never its value)</summary>
        public static void Unauthorized(string remote, string headerUsed)
        {
            Rejected("", "401 token");
            bool log; lock (L) { log = (DateTime.UtcNow - _lastAuthLog).TotalSeconds >= 60; if (log) _lastAuthLog = DateTime.UtcNow; }
            if (log) { string m = "401 on /api/chat-in from " + (string.IsNullOrEmpty(remote) ? "?" : remote) + ": " + headerUsed + " (wrong or missing module token; further 401s are only counted for a minute)"; if (TestLog != null) TestLog(m); else Clog.Warn("chat-in", m); }
        }
        /// <summary>which header carried a token: "Authorization Bearer", "X-Pinguino-Token" or "no token header" (the value is never read into a log)</summary>
        public static string TokenField(System.Net.HttpListenerRequest r)
        {
            string h = r.Headers["Authorization"] ?? "";
            if (h.StartsWith("Bearer ") && h.Length > 7) return "Authorization Bearer token sent";
            if (!string.IsNullOrEmpty(r.Headers["X-Pinguino-Token"])) return "X-Pinguino-Token sent";
            return "no token header";
        }
        public static void Reply() { Bump("replies"); }
        public static void SendError() { Bump("sendErrors"); }

        /// <summary>reads the response DispatchExternal gave and counts it</summary>
        public static void Result(string platform, string text, JObject res)
        {
            if (res == null) { Rejected(platform, "failed"); return; }
            if ((bool?)res["ok"] == true) { if (res["ignored"] != null) Rejected(platform, ((string)res["ignored"]).StartsWith("own bot") ? "own bot" : "not master"); else Accepted(platform, text); return; }
            string e = (string)res["error"] ?? (string)res["ignored"] ?? "failed";
            Rejected(platform, e.StartsWith("platform") ? "platform" : e.StartsWith("user and text") ? "empty" : e.StartsWith("module token") ? "401 token" : "failed");
        }
        static long G(Dictionary<string, long> d, string k) { long v; return d.TryGetValue(k, out v) ? v : 0; }
        public static JObject Json()
        {
            lock (L)
            {
                var o = new JObject { { "yt", G(Total, "accepted.yt") }, { "tt", G(Total, "accepted.tt") }, { "twitch", G(Total, "accepted.twitch") }, { "commands", G(Total, "commands") }, { "replies", G(Total, "replies") },
                    { "sendErrors", G(Total, "sendErrors") }, { "rejected", G(Total, "rejected") }, { "since", _since.ToString("o") }, { "lastAgoSec", _last == DateTime.MinValue ? (int?)null : (int)(DateTime.UtcNow - _last).TotalSeconds }, { "lastReject", _lastReject } };
                var rj = new JObject(); foreach (var kv in Total.Where(x => x.Key.StartsWith("rejected.")).OrderBy(x => x.Key)) rj[kv.Key.Substring(9)] = kv.Value; o["rejects"] = rj;
                var other = new JObject(); foreach (var kv in Total.Where(x => x.Key.StartsWith("accepted.") && x.Key != "accepted.yt" && x.Key != "accepted.tt" && x.Key != "accepted.twitch")) other[kv.Key.Substring(9)] = kv.Value; if (other.Count > 0) o["otherPlatforms"] = other;
                return o;
            }
        }
        /// <summary>the minute line (only when something happened since the last one)</summary>
        public static void Flush()
        {
            string line;
            lock (L)
            {
                if (Win.Count == 0) return;
                line = "chat-in: yt " + G(Win, "accepted.yt") + ", tt " + G(Win, "accepted.tt") + ", commands " + G(Win, "commands") + ", replies " + G(Win, "replies") + ", send errors " + G(Win, "sendErrors");
                long rj = G(Win, "rejected"); if (rj > 0) line += ", rejected " + rj + " (" + string.Join(", ", Win.Where(x => x.Key.StartsWith("rejected.")).OrderBy(x => x.Key).Select(x => x.Key.Substring(9) + " " + x.Value)) + ")";
                Win.Clear();
            }
            if (TestLog != null) TestLog(line); else Clog.Info("chat-in", line);
        }
        public static void TestReset() { lock (L) { Total.Clear(); Win.Clear(); _lastReject = ""; _last = DateTime.MinValue; _since = DateTime.UtcNow; } }
    }
}
