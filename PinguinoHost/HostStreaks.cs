using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>WATCH STREAKS. Twitch only shows a watch streak when the viewer SHARES it (a "viewermilestone" USERNOTICE, category watch-streak, value = how many streams in a row).
    /// So only people who shared are on the board. Data\streaks\streaks.json, keyed by lowercase login:
    ///   { current (latest shared value), best (max ever), bestAt, lastSharedAt, name, history:[{value, at, id?, source, message?}] }.
    /// Idempotent: a live event by its msg-param-id, a backfilled one by login+value+time. Live capture is in Program.HandleIrc; the past is read out of the saved chat logs
    /// ("X watched 45 consecutive streams and sparked a watch streak!"). Every other USERNOTICE is kept too (Data\streaks\usernotices.jsonl, capped), never dropped.
    /// Chat: !streak [user], !topstreak / !topstreaks, !streakrecord [user]. API: GET /api/streaks, POST /api/streaks/backfill.
    /// The values also go into the viewer profiles (roles.watchStreakCurrent / watchStreakBest).</summary>
    public static class Streaks
    {
        static readonly object L = new object();
        static JObject _doc;
        static bool _started;
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(d) : d; } }
        public static string Dir { get { return Path.Combine(Root, "streaks"); } }
        static string StoreP { get { return Path.Combine(Dir, "streaks.json"); } }
        static string NoticeP { get { return Path.Combine(Dir, "usernotices.jsonl"); } }

        static JObject Doc()
        {
            if (_doc != null) return _doc;
            try { if (File.Exists(StoreP)) { _doc = SubsImport.ParseJ(File.ReadAllText(StoreP)); } } catch (Exception ex) { Clog.Warn("streaks", "store unreadable: " + ex.Message); }
            if (_doc == null) _doc = new JObject { { "version", 1 }, { "backfilledAt", "" }, { "users", new JObject() } };
            if (_doc["users"] == null) _doc["users"] = new JObject();
            return _doc;
        }
        static void Save() { Directory.CreateDirectory(Dir); File.WriteAllText(StoreP + ".tmp", Doc().ToString()); if (File.Exists(StoreP)) File.Replace(StoreP + ".tmp", StoreP, null); else File.Move(StoreP + ".tmp", StoreP); }

        /// <summary>start-up: one automatic backfill from the saved chat logs the first time (when the store has never been backfilled).</summary>
        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () =>
            {
                await Task.Delay(15000);
                try { bool first; lock (L) first = string.IsNullOrEmpty((string)Doc()["backfilledAt"]); if (first) Backfill(); } catch (Exception ex) { Clog.Warn("streaks", "backfill failed: " + ex.Message); }
            });
        }

        // ---- recording ----
        /// <summary>true when it was new. at = ISO UTC text. id = Twitch's msg-param-id (live) or "" (backfill).</summary>
        public static bool Record(string login, string name, int value, string at, string id, string source, string message, bool saveNow = true)
        {
            login = (login ?? "").Trim().ToLowerInvariant(); if (login == "" || value <= 0) return false;
            lock (L)
            {
                var users = (JObject)Doc()["users"]; var u = users[login] as JObject;
                if (u == null) { u = new JObject { { "login", login }, { "name", string.IsNullOrEmpty(name) ? login : name }, { "current", 0 }, { "best", 0 }, { "bestAt", "" }, { "lastSharedAt", "" }, { "history", new JArray() } }; users[login] = u; }
                var h = (JArray)u["history"];
                foreach (var e in h) { if (id != "" && (string)e["id"] == id) return false; if ((int?)e["value"] == value && ((string)e["at"] ?? "").Substring(0, Math.Min(19, ((string)e["at"] ?? "").Length)) == at.Substring(0, Math.Min(19, at.Length))) return false; }
                var item = new JObject { { "value", value }, { "at", at }, { "source", source } }; if (id != "") item["id"] = id; if (!string.IsNullOrEmpty(message)) item["message"] = message.Length > 200 ? message.Substring(0, 200) : message;
                h.Add(item);
                var sorted = h.OrderBy(e => (string)e["at"], StringComparer.Ordinal).ToList(); h.Clear(); foreach (var e in sorted) h.Add(e);
                var last = sorted.Last(); u["current"] = (int)last["value"]; u["lastSharedAt"] = (string)last["at"];
                var top = sorted.OrderByDescending(e => (int)e["value"]).ThenBy(e => (string)e["at"], StringComparer.Ordinal).First(); u["best"] = (int)top["value"]; u["bestAt"] = (string)top["at"];
                if (!string.IsNullOrEmpty(name)) u["name"] = name;
                if (saveNow) { Save(); ApplyToProfile(login, u); }
                return true;
            }
        }

        /// <summary>a live IRC USERNOTICE line. Streaks are recorded; everything else is logged so nothing is lost.</summary>
        static readonly Regex Notice = new Regex(@"^@(?<tags>\S+) :\S+ USERNOTICE #\S+(?: :(?<msg>.*))?$", RegexOptions.Compiled);
        public static void OnUserNotice(string line)
        {
            var m = Notice.Match(line); if (!m.Success) return;
            var tags = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var t in m.Groups["tags"].Value.Split(';')) { var a = t.Split(new[] { '=' }, 2); if (a.Length == 2) tags[a[0]] = Unescape(a[1]); }
            Func<string, string> T = k => { string v; return tags.TryGetValue(k, out v) ? v : ""; };
            string msgId = T("msg-id"), login = T("login"), msg = m.Groups["msg"].Success ? m.Groups["msg"].Value : "";
            string at = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
            long ts; if (long.TryParse(T("tmi-sent-ts"), out ts)) at = DateTimeOffset.FromUnixTimeMilliseconds(ts).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ");
            try
            {
                var rec = new JObject { { "at", at }, { "msgId", msgId }, { "login", login }, { "message", msg } };
                foreach (var kv in tags) if (kv.Key.StartsWith("msg-param-") || kv.Key == "system-msg" || kv.Key == "display-name" || kv.Key == "id") rec[kv.Key] = kv.Value;
                Directory.CreateDirectory(Dir);
                if (File.Exists(NoticeP) && new FileInfo(NoticeP).Length > 3_000_000) File.Move(NoticeP, Path.Combine(Dir, "usernotices-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss") + ".jsonl"));
                lock (L) File.AppendAllText(NoticeP, rec.ToString(Newtonsoft.Json.Formatting.None) + "\n");
            }
            catch (Exception ex) { Clog.Warn("streaks", "usernotice log: " + ex.Message); }
            if (msgId == "viewermilestone" && T("msg-param-category") == "watch-streak")
            {
                int v; if (!int.TryParse(T("msg-param-value"), out v)) return;
                if (Record(login, T("display-name"), v, at, T("msg-param-id"), "live", msg)) Clog.Info("streaks", login + " shared a watch streak of " + v);
            }
        }
        static string Unescape(string s) { return s.Replace("\\s", " ").Replace("\\:", ";").Replace("\\r", "\r").Replace("\\n", "\n").Replace("\\\\", "\\"); }

        // ---- backfill out of the saved chat logs ----
        // Oct 2026 files: "[2026-10-13 01:03:49] #innocentpenguin_ cyfirl: CyFiRL watched 10 consecutive streams and sparked a watch streak! 10 stream streak"   (a chat line by the sharer)
        // Feb 2026 files: "[2026-02-18 01:03:30] #innocentpenguin_ * LvLMarshmello watched 15 consecutive streams and sparked a watch streak! - "squad""         (system line, display name only)
        static readonly Regex LogLine = new Regex(@"^\[(?<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\s+(?:#\S+\s+)?(?:(?<star>\*)\s+|(?<who>[^\s:]+):\s+)(?<name>\S+)\s+watched\s+(?<n>\d+)\s+consecutive\s+streams?\s+and\s+sparked\s+a\s+watch\s+streak!?(?<rest>.*)$", RegexOptions.Compiled | RegexOptions.IgnoreCase);

        public static JObject Backfill()
        {
            var roots = new List<string>(); foreach (var r in new[] { Path.Combine(Root, "chat_logs"), Path.Combine(HostApi.DataDir, "chat_logs"), Path.Combine(Root, "backups") }) if (Directory.Exists(r) && !roots.Contains(r)) roots.Add(r);
            int files = 0, lines = 0, added = 0, dup = 0; var people = new HashSet<string>();
            lock (L)
            {
                foreach (var root in roots)
                    foreach (var f in Directory.EnumerateFiles(root, "*.txt", SearchOption.AllDirectories))
                    {
                        if (f.IndexOf("history", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                        files++;
                        try
                        {
                            foreach (var line in File.ReadLines(f))
                            {
                                if (line.IndexOf("watch streak", StringComparison.OrdinalIgnoreCase) < 0) continue;
                                var m = LogLine.Match(line); if (!m.Success) continue; lines++;
                                DateTime t; if (!DateTime.TryParseExact(m.Groups["ts"].Value, "yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out t)) continue;
                                string login = (m.Groups["star"].Success ? m.Groups["name"].Value : m.Groups["who"].Value).ToLowerInvariant();
                                string rest = m.Groups["rest"].Value.Trim(); if (rest.StartsWith("- ")) rest = rest.Substring(2).Trim().Trim('"');
                                if (Record(login, m.Groups["name"].Value, int.Parse(m.Groups["n"].Value), t.ToString("yyyy-MM-ddTHH:mm:ssZ"), "", "chat log", rest, false)) { added++; people.Add(login); } else dup++;
                            }
                        }
                        catch (Exception ex) { Clog.Warn("streaks", f + ": " + ex.Message); }
                    }
                Doc()["backfilledAt"] = DateTime.UtcNow.ToString("o"); Save();
                foreach (var p in ((JObject)Doc()["users"]).Properties()) ApplyToProfile(p.Name, (JObject)p.Value);
            }
            Clog.Info("streaks", "backfill: " + files + " log files, " + lines + " streak lines, " + added + " new (" + dup + " duplicates), " + people.Count + " people");
            return new JObject { { "ok", true }, { "filesScanned", files }, { "streakLines", lines }, { "added", added }, { "duplicates", dup }, { "people", people.Count } };
        }

        // ---- profiles ----
        static void ApplyToProfile(string login, JObject u)
        {
            try
            {
                string f = Path.Combine(Root, "profiles", login + ".json"); if (!File.Exists(f)) return;
                var prof = SubsImport.ParseJ(File.ReadAllText(f)); var roles = prof["roles"] as JObject ?? new JObject();
                int cur = (int?)u["current"] ?? 0, best = (int?)u["best"] ?? 0;
                if ((int?)roles["watchStreakCurrent"] == cur && (int?)roles["watchStreakBest"] == best) return;
                roles["watchStreakCurrent"] = cur; roles["watchStreakBest"] = best; roles["watchStreakAt"] = (string)u["lastSharedAt"]; prof["roles"] = roles; File.WriteAllText(f, prof.ToString());
            }
            catch (Exception ex) { Clog.Warn("streaks", "profile " + login + ": " + ex.Message); }
        }

        // ---- API ----
        public static JObject Api(int top = 0)
        {
            lock (L)
            {
                var users = ((JObject)Doc()["users"]).Properties().Select(p => (JObject)p.Value).ToList();
                var board = users.OrderByDescending(u => (int)u["best"]).ThenBy(u => (string)u["bestAt"], StringComparer.Ordinal).Select(u => new JObject { { "login", u["login"] }, { "name", u["name"] }, { "best", u["best"] }, { "bestAt", u["bestAt"] }, { "current", u["current"] }, { "lastSharedAt", u["lastSharedAt"] }, { "shares", ((JArray)u["history"]).Count } }).ToList();
                return new JObject { { "ok", true }, { "people", users.Count }, { "backfilledAt", Doc()["backfilledAt"] }, { "board", new JArray(top > 0 ? board.Take(top) : board) } };
            }
        }

        // ---- chat commands ----
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();
        static bool Cooling(string key, int sec) { lock (Cool) { DateTime t; if (Cool.TryGetValue(key, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; Cool[key] = DateTime.UtcNow; return false; } }
        static int CoolSec(string env, int d) { int v; return int.TryParse(Environment.GetEnvironmentVariable(env), out v) ? v : d; }
        static string D(string iso) { DateTime t; return DateTime.TryParse(iso, null, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out t) ? t.ToString("MMM d, yyyy", CultureInfo.InvariantCulture) : ""; }

        public static bool Handle(string user, string text, Action<string> say)
        {
            var parts = (text ?? "").Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries); if (parts.Length == 0) return false;
            string cmd = parts[0].ToLowerInvariant();
            if (cmd != "!streak" && cmd != "!topstreak" && cmd != "!topstreaks" && cmd != "!streakrecord") return false;
            string who = parts.Length > 1 ? parts[1].TrimStart('@').ToLowerInvariant() : user.ToLowerInvariant(); bool self = who == user.ToLowerInvariant();
            string group = cmd == "!topstreak" || cmd == "!topstreaks" ? "top" : cmd;
            int cg = CoolSec("PINGUINO_STREAK_COOL_GLOBAL", 8), cu = CoolSec("PINGUINO_STREAK_COOL_USER", 20);
            if (Cooling("g|" + group, cg) || Cooling("u|" + group + "|" + user.ToLowerInvariant(), cu)) return true;   // quiet while cooling down, like the other commands
            JObject u; lock (L) u = ((JObject)Doc()["users"])[who] as JObject;
            string name = u != null ? (string)u["name"] : who;
            if (group == "top")
            {
                var b = (JArray)Api(5)["board"];
                say(b.Count == 0 ? "Nobody has shared a watch streak yet. When Twitch offers it, share yours in chat and it lands on the board!"
                    : "Top watch streaks (best shared): " + string.Join(" | ", b.Select((x, i) => (i + 1) + ". " + (string)x["name"] + " " + (int)x["best"])));
                return true;
            }
            if (u == null)
            {
                say(self ? "@" + user + " I haven't seen you share a watch streak yet. When Twitch offers it, share it in chat and I'll remember it."
                         : "Nobody has shared a watch streak for " + who + " yet.");
                return true;
            }
            int cur = (int)u["current"], best = (int)u["best"];
            if (cmd == "!streakrecord") say((self ? "@" + user + " your" : name + "'s") + " best shared watch streak: " + best + " streams in a row" + (D((string)u["bestAt"]) != "" ? " (shared " + D((string)u["bestAt"]) + ")" : "") + ".");
            else say((self ? "@" + user + " your" : name + "'s") + " last shared watch streak: " + cur + " streams in a row" + (D((string)u["lastSharedAt"]) != "" ? " (" + D((string)u["lastSharedAt"]) + ")" : "") + (best > cur ? ", best " + best : "") + ".");
            return true;
        }
    }
}
