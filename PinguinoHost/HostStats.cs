using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Chat activity for the dashboard: messages per minute, active chatters, and the moderators seen lately. Kept in memory only (logins and counts, no text).</summary>
    public static class ChatStats
    {
        class Hit { public DateTime At; public string Login; public int Role; }
        static readonly List<Hit> _hits = new List<Hit>(); static readonly object _l = new object();

        public static void Note(string login, int role)
        {
            lock (_l)
            {
                var now = DateTime.UtcNow; _hits.Add(new Hit { At = now, Login = (login ?? "").ToLowerInvariant(), Role = role });
                if (_hits.Count > 20000) _hits.RemoveRange(0, 5000);
                while (_hits.Count > 0 && (now - _hits[0].At).TotalMinutes > 90) _hits.RemoveAt(0);
            }
        }

        public static JObject Chat()
        {
            lock (_l)
            {
                var now = DateTime.UtcNow;
                Func<int, List<Hit>> within = m => _hits.Where(h => (now - h.At).TotalMinutes <= m).ToList();
                var m1 = within(1); var m5 = within(5); var m60 = within(60);
                return new JObject {
                    { "messagesLastMinute", m1.Count }, { "messagesPerMinute5", Math.Round(m5.Count / 5.0, 1) },
                    { "chatters5", m5.Select(h => h.Login).Distinct().Count() }, { "chatters60", m60.Select(h => h.Login).Distinct().Count() },
                    { "mods", new JArray(within(60).Where(h => h.Role >= 3 && h.Role < 4).Select(h => h.Login).Distinct().OrderBy(x => x)) },
                    { "modsActive30", within(30).Where(h => h.Role >= 3 && h.Role < 4).Select(h => h.Login).Distinct().Count() } };
            }
        }
    }

    public static partial class HostApi
    {
        // One summary for the dashboard strip: chat rate, active mods, bot health, lease, last error.
        static JObject Summary()
        {
            var st = Status(); var bots = Bots(); var health = new JArray(); string worst = "pass";
            var sec = LoadFile("bots_secrets.json");
            foreach (JObject b in (JArray)bots["bots"])
            {
                string id = (string)b["id"]; bool on = (bool)b["enabled"]; bool signed = (bool)b["signedIn"]; string hs = (string)b["health"];
                if (hs == "fail" || (hs == "warn" && worst == "pass")) worst = hs == "fail" ? "fail" : "warn";
                health.Add(new JObject { { "id", id }, { "title", b["title"] }, { "account", b["account"] }, { "enabled", on }, { "signedIn", signed }, { "health", hs }, { "detail", b["healthDetail"] }, { "runs", b["runs"] }, { "lastRunAgoSec", b["lastRunAgoSec"] } });
            }
            int? errAge = Clog.LastErrorAt == DateTime.MinValue ? (int?)null : (int)(DateTime.UtcNow - Clog.LastErrorAt).TotalSeconds;
            return new JObject {
                { "ok", true }, { "ts", DateTime.UtcNow.ToString("o") }, { "module", "host" }, { "uptimeSec", st["uptimeSec"] }, { "channel", st["channel"] },
                { "connections", new JObject { { "chat", st["chatConnected"] }, { "eventSub", st["eventSubConnected"] }, { "obs", st["obsConnected"] }, { "canSend", st["canSend"] } } },
                { "chat", ChatStats.Chat() }, { "bots", health }, { "botHealth", worst },
                { "lease", Lease.State() },
                { "lastError", new JObject { { "agoSec", errAge }, { "text", errAge == null ? "" : Clog.LastErrorText } } } };
        }
    }
}
