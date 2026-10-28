using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Viewers from other platforms (YouTube, TikTok ...) come in through /api/chat-in. Their key everywhere is "yt:&lt;id&gt;" / "tt:&lt;id&gt;" (the platform's own stable id; the lowercase name only when Multi sends no id),
    /// Twitch stays unprefixed. This remembers the display name per key (Data\platform_users.json) so queue, boards and pushes can show a name plus the platform.</summary>
    public static class PlatformUsers
    {
        static readonly object L = new object(); static JObject _m;
        static string P { get { return Path.Combine(HostApi.DataDir, "platform_users.json"); } }
        static readonly Dictionary<string, string> Prefix = new Dictionary<string, string> { { "yt", "youtube" }, { "tt", "tiktok" }, { "kk", "kick" }, { "fb", "facebook" } };
        static JObject Parse(string f) { return JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)); }
        /// <summary>never starts blank over a good file: a file that fails to parse is moved aside (platform_users.json.corrupt-*), the .bak is tried next, and only then it starts empty (the corrupt copy is kept, never overwritten)</summary>
        static JObject M()
        {
            if (_m != null) return _m;
            try { if (File.Exists(P)) { _m = Parse(P); return _m; } }
            catch (Exception ex)
            {
                try { File.Move(P, P + ".corrupt-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss")); } catch (Exception) { }
                Clog.Warn("platform", "platform_users.json could not be read (" + ex.Message + "): kept as .corrupt-*, trying the .bak");
            }
            try { if (File.Exists(P + ".bak")) { _m = Parse(P + ".bak"); Clog.Warn("platform", "restored platform users from platform_users.json.bak"); return _m; } } catch (Exception) { }
            _m = new JObject(); return _m;
        }
        /// <summary>temp file + replace, the previous version kept as .bak</summary>
        static void Save(JObject m)
        {
            try
            {
                string tmp = P + ".tmp"; File.WriteAllText(tmp, m.ToString(), new UTF8Encoding(false));
                if (File.Exists(P)) File.Replace(tmp, P, P + ".bak"); else File.Move(tmp, P);
            }
            catch (Exception ex) { Clog.Warn("platform", "could not save platform_users.json: " + ex.Message); }
        }
        /// <summary>"twitch" for an unprefixed login, else the platform behind the prefix</summary>
        public static string PlatformOf(string login)
        {
            string l = login ?? ""; int c = l.IndexOf(':'); string v; return c > 0 && Prefix.TryGetValue(l.Substring(0, c), out v) ? v : "twitch";
        }
        public static bool IsForeign(string login) { return PlatformOf(login) != "twitch"; }
        /// <summary>key for a viewer: prefix + platform id (letters, digits, _ and - kept, max 40) or, without an id, the lowercase name made safe</summary>
        public static string Key(string prefix, string id, string name)
        {
            string raw = (id ?? "").Trim(); if (raw == "") raw = (name ?? "").Trim().ToLowerInvariant();
            raw = Regex.Replace(raw, @"[^\w\-]", "_"); if (raw.Length > 40) raw = raw.Substring(0, 40); if (raw == "") raw = "unknown";
            return prefix + ":" + raw.ToLowerInvariant();
        }
        public static void Remember(string login, string platform, string display, string id)
        {
            display = (display ?? "").Trim(); if (display.Length > 60) display = display.Substring(0, 60); if (login == "" || display == "") return;
            lock (L)
            {
                var m = M(); var e = m[login] as JObject;
                if (e != null && (string)e["name"] == display && (string)e["platform"] == platform) return;
                m[login] = new JObject { { "platform", platform }, { "name", display }, { "id", id ?? "" }, { "seen", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } };
                Save(m);
                Publish(m);
            }
        }
        /// <summary>the name to show for a key: the remembered display name for other platforms, the Twitch display name otherwise; never empty</summary>
        public static string Display(string login)
        {
            string l = login ?? "";
            if (IsForeign(l)) { lock (L) { var e = M()[l] as JObject; string n = e == null ? "" : (string)e["name"] ?? ""; if (n != "") return n; } return l.Substring(l.IndexOf(':') + 1); }
            string d = ""; try { d = Boards.DisplayName(l); } catch (Exception) { }
            return string.IsNullOrEmpty(d) ? l : d;
        }
        /// <summary>{login, platform, name} for pushes; Twitch logins stay as they were</summary>
        public static void Tag(JObject o, string login)
        {
            o["platform"] = PlatformOf(login); if (o["name"] == null) o["name"] = Display(login);
        }
        /// <summary>the names go to the bots (Core resolves "!kick Tik Toker" to tt:7001): one "login TAB name" line per viewer in the global var pinguino.platform.users</summary>
        static void Publish(JObject m)
        {
            try { var sb = new StringBuilder(); foreach (var p in m.Properties()) { string n = ((string)(p.Value as JObject)?["name"] ?? "").Replace("\t", " ").Replace("\n", " "); if (n != "") sb.Append(p.Name).Append('\t').Append(n).Append('\n'); } Program.SetGlobal("pinguino.platform.users", sb.ToString()); } catch (Exception) { }
        }
        /// <summary>publish what is stored (Host start)</summary>
        public static void PublishAll() { lock (L) { Publish(M()); } }
        public static void TestReset() { lock (L) { _m = null; } }
    }
}
