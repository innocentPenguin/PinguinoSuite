using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Who gifted each subscriber their sub. Live: the IRC USERNOTICE "subgift" / "anonsubgift" names both the gifter and the recipient (Streaks.OnUserNotice calls Note). Backfill: the old chat logs
    /// ("X gifted a Tier 1 sub to Y!") and the saved USERNOTICE log. Stored per recipient in Data\subs\gift_tags.json (the latest gift wins).
    /// The site reads it as sub:{gifted, gifter (display name or null), gifterAnonymous} in each Points view (SubRoll.ViewOf); a gifted sub whose gifter is not known has gifter null and gifterAnonymous false.
    /// GET /api/giftags lists the tags and the gifted subscribers with no known gifter; POST /api/giftags {"backfill":true} runs the backfill again.</summary>
    public static class GiftTags
    {
        static readonly object L = new object(); static JObject _doc; static bool _started;
        static string P { get { return Path.Combine(HostApi.DataDir, "subs", "gift_tags.json"); } }
        static readonly Regex RxChat = new Regex(@"^\[(?<ts>[0-9-]+ [0-9:]+)\] #\S+ \* (?:(?<anon>An anonymous user)|(?<who>\S+)) gifted a Tier (?<tier>\d) sub to (?<to>\S+?)!", RegexOptions.IgnoreCase | RegexOptions.Compiled);

        static JObject Doc()
        {
            if (_doc != null) return _doc;
            JObject d = null; try { if (File.Exists(P)) d = JObject.Parse(File.ReadAllText(P, Encoding.UTF8)); } catch (Exception) { }
            if (d == null) d = new JObject(); if (!(d["tags"] is JObject)) d["tags"] = new JObject(); return _doc = d;
        }
        static void Save() { try { Directory.CreateDirectory(Path.GetDirectoryName(P)); File.WriteAllText(P, _doc.ToString(Newtonsoft.Json.Formatting.None), new UTF8Encoding(false)); } catch (Exception ex) { Clog.Warn("giftags", "could not save: " + ex.Message); } }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(15000); try { bool done; lock (L) done = Doc()["backfilledAt"] != null; if (!done) Backfill(); } catch (Exception ex) { Clog.Warn("giftags", "backfill failed: " + ex.Message); } });
        }

        /// <summary>one gift: recipient login, gifter login/display (empty + anonymous=true for anonymous), tier 1-3, when (unix seconds)</summary>
        public static bool Note(string recipient, string gifterLogin, string gifterDisplay, bool anonymous, int tier, long at, string source)
        {
            recipient = (recipient ?? "").Trim().TrimStart('@').ToLowerInvariant(); if (recipient == "") return false;
            lock (L)
            {
                var tags = (JObject)Doc()["tags"]; var old = tags[recipient] as JObject;
                if (old != null && ((long?)old["at"] ?? 0) > at) return false;   // keep the newer gift
                string disp = anonymous ? "" : (!string.IsNullOrEmpty(gifterDisplay) ? gifterDisplay : gifterLogin) ?? "";
                tags[recipient] = new JObject { { "gifter", anonymous ? null : (string.IsNullOrEmpty(disp) ? null : disp) }, { "gifterLogin", anonymous ? null : (string.IsNullOrEmpty(gifterLogin) ? disp.ToLowerInvariant() : gifterLogin.ToLowerInvariant()) }, { "anonymous", anonymous }, { "tier", tier }, { "at", at }, { "source", source } };
                Save(); return true;
            }
        }

        /// <summary>live: a USERNOTICE tag set (msg-id subgift | anonsubgift)</summary>
        public static void OnNotice(string msgId, Func<string, string> T)
        {
            if (msgId != "subgift" && msgId != "anonsubgift") return;
            bool anon = msgId == "anonsubgift" || T("login") == "ananonymousgifter" || T("msg-param-sender-count") == "" && T("login") == "";
            int tier = T("msg-param-sub-plan") == "3000" ? 3 : T("msg-param-sub-plan") == "2000" ? 2 : 1;
            long ts; long at = long.TryParse(T("tmi-sent-ts"), out ts) ? ts / 1000 : DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            Note(T("msg-param-recipient-user-name"), T("login"), T("display-name"), anon, tier, at, "live");
        }

        /// <summary>old chat logs + the saved USERNOTICE log. Safe to run again (the newest gift per recipient wins).</summary>
        public static JObject Backfill()
        {
            int seen = 0, applied = 0; var disp = new Dictionary<string, string>();
            string cl = Path.Combine(HostApi.DataDir, "chat_logs");
            try
            {
                if (Directory.Exists(cl))
                    foreach (var f in Directory.GetFiles(cl, "*.txt", SearchOption.AllDirectories))
                    {
                        string[] lines; try { lines = File.ReadAllLines(f, Encoding.UTF8); } catch (Exception) { continue; }
                        foreach (var ln in lines)
                        {
                            if (ln.IndexOf(" gifted a Tier ", StringComparison.OrdinalIgnoreCase) < 0) continue;
                            var m = RxChat.Match(ln); if (!m.Success) continue; seen++;
                            DateTime dt; long at = DateTime.TryParseExact(m.Groups["ts"].Value, "yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out dt) ? new DateTimeOffset(dt).ToUnixTimeSeconds() : 0;
                            if (Note(m.Groups["to"].Value, m.Groups["who"].Value, m.Groups["who"].Value, m.Groups["anon"].Success, int.Parse(m.Groups["tier"].Value), at, "chatlog")) applied++;
                        }
                    }
                string un = Path.Combine(HostApi.DataDir, "streaks");
                if (Directory.Exists(un))
                    foreach (var f in Directory.GetFiles(un, "usernotices*.jsonl"))
                        foreach (var ln in File.ReadAllLines(f, Encoding.UTF8))
                        {
                            JObject j; try { j = JObject.Parse(ln); } catch (Exception) { continue; }
                            string id = (string)j["msgId"]; if (id != "subgift" && id != "anonsubgift") continue; seen++;
                            DateTime dt; long at = DateTime.TryParse((string)j["at"], CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out dt) ? new DateTimeOffset(dt).ToUnixTimeSeconds() : 0;
                            int tier = (string)j["msg-param-sub-plan"] == "3000" ? 3 : (string)j["msg-param-sub-plan"] == "2000" ? 2 : 1;
                            if (Note((string)j["msg-param-recipient-user-name"], (string)j["login"], (string)j["display-name"], id == "anonsubgift", tier, at, "usernotice")) applied++;
                        }
            }
            catch (Exception ex) { Clog.Warn("giftags", "backfill stopped: " + ex.Message); }
            lock (L) { Doc()["backfilledAt"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); Save(); }
            Clog.Info("giftags", "backfill: " + seen + " gift lines read, " + applied + " tags written");
            return new JObject { { "ok", true }, { "linesRead", seen }, { "tagsWritten", applied } };
        }

        public static JObject TagOf(string login)
        {
            login = (login ?? "").Trim().TrimStart('@').ToLowerInvariant();
            lock (L) return (Doc()["tags"] as JObject)?[login] as JObject;
        }

        /// <summary>{gifted, gifter, gifterAnonymous} for the site. gifted = the master list says the sub came as a gift, or a gift was recorded for them.</summary>
        public static JObject ViewOf(string login, string subType)
        {
            var t = TagOf(login); bool gifted = subType == "gift" || (subType == "" && t != null);   // the sub list knows how they subscribe now; an old gift does not make a recurring sub "gifted"
            return new JObject { { "gifted", gifted }, { "gifter", gifted && t != null && (bool?)t["anonymous"] != true ? t["gifter"] : null }, { "gifterAnonymous", gifted && t != null && (bool?)t["anonymous"] == true } };
        }

        /// <summary>GET /api/giftags: counts, and the gifted subscribers whose gifter we do not know</summary>
        public static JObject Report()
        {
            var unknown = new JArray(); int gifted = 0, known = 0, anon = 0;
            try
            {
                string mp = Path.Combine(HostApi.DataDir, "subs", "subscribers_master.json");
                var users = (SubsImport.ParseJ(SubsImport.ReadShared(mp))["users"] as JObject) ?? new JObject();
                foreach (var p in users.Properties())
                {
                    var u = p.Value as JObject; if (u == null || (bool?)u["lapsed"] == true) continue;
                    var t = TagOf(p.Name); bool g = (string)u["subType"] == "gift" || ((string)u["subType"] ?? "") == "" && t != null; if (!g) continue; gifted++;
                    if (t != null && (bool?)t["anonymous"] == true) anon++; else if (t != null && (string)t["gifter"] != null) known++; else unknown.Add(p.Name);
                }
            }
            catch (Exception) { }
            int total; lock (L) total = ((JObject)Doc()["tags"]).Count;
            return new JObject { { "ok", true }, { "tags", total }, { "giftedSubscribers", gifted }, { "gifterKnown", known }, { "gifterAnonymous", anon }, { "gifterUnknown", unknown.Count }, { "unknown", unknown } };
        }
    }
}
