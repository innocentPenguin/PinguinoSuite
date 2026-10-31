using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Actions &amp; Events: Streamer.bot-style automation inside the Host. Triggers (chat command, chat match, first message, follow/sub/resub/gift/cheer/raid/redeem,
    /// timer, stream online/offline, hotkey, manual) run steps (say, delay, OBS, sound, http, module command, variables, if, ...). Stored in Data\runtime\automations.json;
    /// every run is logged to the Console (source "automation") and kept in memory for the page. Format and steps: Docs\ACTIONS.md.</summary>
    public static partial class Auto
    {
        static readonly object L = new object();
        static JObject _doc; static DateTime _docStamp = DateTime.MinValue;
        static readonly Dictionary<string, DateTime> _cool = new Dictionary<string, DateTime>();
        static readonly Dictionary<string, long> _timerLast = new Dictionary<string, long>(); static readonly Dictionary<string, long> _timerMsgs = new Dictionary<string, long>();
        static readonly Dictionary<string, object> _locks = new Dictionary<string, object>();
        static readonly List<JObject> _log = new List<JObject>();
        static JObject _vars; static readonly Random Rnd = new Random();
        public static string DataDir { get { return HostApi.DataDir; } }
        static string FilePath { get { return Path.Combine(DataDir, "automations.json"); } }
        static string VarsPath { get { return Path.Combine(DataDir, "automation_vars.json"); } }
        const int MaxSteps = 300;

        // ---------------- store ----------------
        public static JObject Doc()
        {
            lock (L)
            {
                try
                {
                    DateTime st = File.Exists(FilePath) ? File.GetLastWriteTimeUtc(FilePath) : DateTime.MinValue;
                    if (_doc == null || st != _docStamp) { _doc = File.Exists(FilePath) ? JObject.Parse(File.ReadAllText(FilePath)) : new JObject { { "version", 1 }, { "actions", new JArray() } }; _docStamp = st; }
                }
                catch (Exception ex) { Clog.Error("automation", "automations.json unreadable: " + ex.Message); if (_doc == null) _doc = new JObject { { "version", 1 }, { "actions", new JArray() } }; }
                if (!(_doc["actions"] is JArray)) _doc["actions"] = new JArray();
                return _doc;
            }
        }
        public static string Save(JObject doc)
        {
            var acts = doc["actions"] as JArray; if (acts == null) return "actions must be a list";
            var ids = new HashSet<string>();
            foreach (JObject a in acts.OfType<JObject>())
            {
                if (string.IsNullOrWhiteSpace((string)a["id"])) a["id"] = Guid.NewGuid().ToString("N").Substring(0, 10);
                if (!ids.Add((string)a["id"])) return "duplicate id " + (string)a["id"];
                if (string.IsNullOrWhiteSpace((string)a["name"])) return "every action needs a name";
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                    if (string.Equals((string)t["type"], "chat", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrEmpty((string)t["pattern"]))
                        try { new Regex((string)t["pattern"]); } catch (Exception) { return a["name"] + ": invalid chat pattern"; }
            }
            doc["version"] = 1;
            lock (L)
            {
                var tmp = FilePath + ".tmp"; File.WriteAllText(tmp, doc.ToString());
                if (File.Exists(FilePath)) File.Replace(tmp, FilePath, null); else File.Move(tmp, FilePath);
                _doc = null;
            }
            Clog.Info("automation", "saved " + acts.Count + " actions");
            return null;
        }
        /// <summary>First start only (remembered in the file, so deleting one sticks): the Spotify song-request commands, created DISABLED. They forward to the spotify module
        /// (POST /api/chat-command on port 8771); enable them on the page when that module is running and Nightbot/StreamElements stop answering !sr.</summary>
        public static void SeedDefaults()
        {
            try { StreamCategory.EnsureStarted(); } catch (Exception) { }
            try
            {
                var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray();
                if (!seeded.Any(x => (string)x == "speak"))
                {
                    // !speak (viewer text-to-speech through the Speak module): created DISABLED. Speak's own switch (tts.enabled) is OFF too, so nothing is spoken until both are on.
                    // Typed in chat: mods only. Channel-point redeem (reward title below; Ivan creates it on Twitch, 100 points): anyone, the points were the price (redeem:true).
                    var acts1 = (JArray)doc["actions"]; const string vurl = "http://127.0.0.1:8772/api/chat-command";
                    if (!acts1.OfType<JObject>().Any(x => (string)x["id"] == "speak-chat"))
                        acts1.Add(new JObject { { "id", "speak-chat" }, { "name", "Speak: !speak (mods)" }, { "group", "Speak" }, { "enabled", false }, { "importNotes", "preset: also switch on tts.enabled in the Speak module; the module checks the role again" },
                            { "triggers", new JArray { new JObject { { "type", "command" }, { "names", new JArray("!speak", "!tts") }, { "permission", "mod" }, { "cooldownSec", 0 }, { "userCooldownSec", 20 }, { "consume", true } } } }, { "conditions", new JArray() },
                            { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", vurl }, { "command", "speak" }, { "as", "core" } } } } });
                    if (!acts1.OfType<JObject>().Any(x => (string)x["id"] == "speak-redeem"))
                        acts1.Add(new JObject { { "id", "speak-redeem" }, { "name", "Speak: channel point !speak" }, { "group", "Speak" }, { "enabled", false }, { "importNotes", "preset: create a 100-point reward called Speak on Twitch (text required), then enable; also switch on tts.enabled in the Speak module" },
                            { "triggers", new JArray { new JObject { { "type", "redeem" }, { "title", "Speak" } } } }, { "conditions", new JArray() },
                            { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", vurl }, { "command", "speak" }, { "redeem", true }, { "as", "core" } } } } });
                    seeded.Add("speak"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (!seeded.Any(x => (string)x == "spotify-redeem"))
                {
                    var acts0 = (JArray)doc["actions"];
                    if (!acts0.OfType<JObject>().Any(x => (string)x["id"] == "spotify-redeem"))
                        acts0.Add(new JObject { { "id", "spotify-redeem" }, { "name", "Spotify: channel point song request" }, { "group", "Spotify" }, { "enabled", false }, { "importNotes", "preset: set the reward title, enable when the spotify module runs" },
                            { "triggers", new JArray { new JObject { { "type", "redeem" }, { "title", "Song Request" } } } }, { "conditions", new JArray() },
                            { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", "http://127.0.0.1:8771/api/chat-command" }, { "command", "sr" }, { "redeem", true }, { "as", "helper" } } } } });
                    seeded.Add("spotify-redeem"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (seeded.Any(x => (string)x == "spotify") && !seeded.Any(x => (string)x == "spotify2"))
                {
                    // one-time: !skip and !voteskip are one vote command for everyone (the module counts the votes); !vol / !volume read out (mods set) the volume. Enabled flags stay as they are.
                    var acts2 = (JArray)doc["actions"]; var sk = acts2.OfType<JObject>().FirstOrDefault(x => (string)x["id"] == "spotify-skip");
                    if (sk != null) foreach (var t in ((JArray)sk["triggers"]).OfType<JObject>()) { t["names"] = new JArray("!skip", "!voteskip"); t["permission"] = "everyone"; }
                    if (!acts2.OfType<JObject>().Any(x => (string)x["id"] == "spotify-vol"))
                    {
                        var v = new JObject { { "id", "spotify-vol" }, { "name", "Spotify: !vol" }, { "group", "Spotify" }, { "enabled", sk != null && (bool?)sk["enabled"] == true }, { "importNotes", "preset: !vol shows the volume, mods can set it (!vol 60 or !vol60)" },
                            { "triggers", new JArray { new JObject { { "type", "command" }, { "names", new JArray("!vol", "!volume") }, { "permission", "everyone" }, { "cooldownSec", 5 }, { "userCooldownSec", 0 }, { "consume", true } } } }, { "conditions", new JArray() },
                            { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", "http://127.0.0.1:8771/api/chat-command" }, { "command", "volume" }, { "as", "helper" } } } } };
                        acts2.Add(v);
                    }
                    seeded.Add("spotify2"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (seeded.Any(x => (string)x == "spotify") && !seeded.Any(x => (string)x == "musicoff1"))
                {
                    // one-time (Ivan 10-24): the Helper owns the music replies (!song, !songqueue, !vol, !skip/!voteskip), so the Host presets for them go (dated backup first); !sr, !oops, !blocksong, !srclear stay
                    try { File.Copy(Path.Combine(HostApi.DataDir, "automations.json"), Path.Combine(HostApi.DataDir, "automations.json.before-musicoff-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".bak"), true); } catch (Exception) { }
                    var acts4 = (JArray)doc["actions"]; int gone = 0;
                    foreach (var x in acts4.OfType<JObject>().Where(x => MusicOff.Contains((string)x["id"])).ToList()) { acts4.Remove(x); gone++; }
                    if (gone > 0) Clog.Info("automation", "music presets removed (the Helper answers them): " + gone);
                    seeded.Add("musicoff1"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (seeded.Any(x => (string)x == "spotify") && !seeded.Any(x => (string)x == "songhelper1"))
                {
                    // one-time (Ivan 10-24): every song reply is said by PinguinoHelper: !sr, !blocksong, !srclear presets move to helper (dated backup first), and the "Skip Song" channel-point reward gets its preset
                    try { File.Copy(Path.Combine(HostApi.DataDir, "automations.json"), Path.Combine(HostApi.DataDir, "automations.json.before-songhelper-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".bak"), true); } catch (Exception) { }
                    var acts5 = (JArray)doc["actions"]; int moved = SongSender.MoveToHelper(acts5);
                    if (!acts5.OfType<JObject>().Any(x => (string)x["id"] == "spotify-skip-redeem"))
                        acts5.Add(new JObject { { "id", "spotify-skip-redeem" }, { "name", "Spotify: channel point skip song" }, { "group", "Spotify" }, { "enabled", true }, { "importNotes", "preset: the Skip Song reward skips the song now (the points were the price); the Helper says it" },
                            { "triggers", new JArray { new JObject { { "type", "redeem" }, { "title", "Skip Song" } } } }, { "conditions", new JArray() },
                            { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", "http://127.0.0.1:8771/api/chat-command" }, { "command", "skip" }, { "redeem", true }, { "as", "helper" } } } } });
                    Clog.Info("automation", "song presets now say as helper: " + moved);
                    seeded.Add("songhelper1"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (!seeded.Any(x => (string)x == "raidshort1"))
                {
                    // one-time (Ivan 10-27): the raid emote line was 188 characters, now four emotes (under 100); dated backup first
                    try { File.Copy(Path.Combine(HostApi.DataDir, "automations.json"), Path.Combine(HostApi.DataDir, "automations.json.before-raidshort-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".bak"), true); } catch (Exception) { }
                    int cut = 0;
                    foreach (var act in ((JArray)doc["actions"]).OfType<JObject>())
                        foreach (var st in (act["steps"] as JArray ?? new JArray()).OfType<JObject>())
                        { string tx = (string)st["text"] ?? ""; if (tx.StartsWith("Raid started! Prepare your emotes!") && tx.Length > 100) { st["text"] = "Raid started! Prepare your emotes! innoce108Arrive innoce108W innoce108Pinguinoraid innoce108Hype"; cut++; } }
                    if (cut > 0) Clog.Info("automation", "raid emote line shortened in " + cut + " step(s)");
                    seeded.Add("raidshort1"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (seeded.Any(x => (string)x == "spotify")) return;
                const string url = "http://127.0.0.1:8771/api/chat-command";
                Func<string, string, string[], string, int, int, JObject> mk = (id, cmd, names, perm, cd, ucd) => new JObject {
                    { "id", "spotify-" + id }, { "name", "Spotify: !" + names[0].TrimStart('!') }, { "group", "Spotify" }, { "enabled", false }, { "importNotes", "preset: enable when the spotify module runs" },
                    { "triggers", new JArray { new JObject { { "type", "command" }, { "names", new JArray(names) }, { "permission", perm }, { "cooldownSec", cd }, { "userCooldownSec", ucd }, { "consume", true } } } },
                    { "conditions", new JArray() }, { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", url }, { "command", cmd }, { "as", "helper" } } } } };
                var acts = (JArray)doc["actions"];
                foreach (var a in new[] {
                    mk("sr", "sr", new[] { "!sr", "!songrequest" }, "everyone", 0, 10), 
                    mk("oops", "oops", new[] { "!oops", "!wrongsong" }, "everyone", 0, 10), mk("block", "blocksong", new[] { "!blocksong" }, "mod", 0, 0), mk("clear", "srclear", new[] { "!srclear" }, "mod", 0, 0) })
                    if (!acts.OfType<JObject>().Any(x => (string)x["id"] == (string)a["id"])) acts.Add(a);
                seeded.Add("spotify"); seeded.Add("spotify2"); seeded.Add("musicoff1"); doc["seeded"] = seeded; Save(doc);   // spotify2 / musicoff1 marked too: the skip/vol/song/queue presets are never added
            }
            catch (Exception ex) { Clog.Warn("automation", "seeding presets failed: " + ex.Message); }
        }
        static readonly string[] MusicOff = { "spotify-song", "spotify-queue", "spotify-vol", "spotify-skip" };
        static List<JObject> Actions() { return ((JArray)Doc()["actions"]).OfType<JObject>().Where(a => (bool?)a["enabled"] != false).ToList(); }
        static JObject FindAction(string idOrName) { return ((JArray)Doc()["actions"]).OfType<JObject>().FirstOrDefault(a => (string)a["id"] == idOrName || string.Equals((string)a["name"], idOrName, StringComparison.OrdinalIgnoreCase)); }

        // ---------------- variables ----------------
        static JObject Vars() { lock (L) { if (_vars == null) { try { _vars = File.Exists(VarsPath) ? JObject.Parse(File.ReadAllText(VarsPath)) : new JObject(); } catch (Exception) { _vars = new JObject(); } } return _vars; } }
        static string GetVar(string n) { lock (L) { var v = Vars()[n]; return v == null ? "" : (string)v; } }
        static void SetVar(string n, string v, bool persist) { lock (L) { Vars()[n] = v; if (persist) try { File.WriteAllText(VarsPath, Vars().ToString()); } catch (Exception) { } } }

        // ---------------- templates and conditions ----------------
        static readonly Regex RxTpl = new Regex(@"\{([A-Za-z0-9_.:\-]+)\}", RegexOptions.Compiled);
        public static string Expand(string t, Dictionary<string, string> ctx)
        {
            if (string.IsNullOrEmpty(t)) return "";
            return RxTpl.Replace(t, m =>
            {
                string k = m.Groups[1].Value; string v;
                if (k.StartsWith("var:")) return GetVar(k.Substring(4));
                if (k.StartsWith("redeem.")) return RedeemCounts.Var(k.Substring(7));   // {redeem.pushups}: baseline + live redemptions of the group
                if (k.StartsWith("link:")) return Links.Get(k.Substring(5)) ?? "";   // {link:discord}: the site's canonical links (see Links)
                if (k == "discord" && !ctx.ContainsKey("discord")) return Links.Get("discord") ?? "";
                if (k.StartsWith("random:")) { var mm = Regex.Match(k, @"^random:(-?\d+)-(-?\d+)$"); if (mm.Success) { int a = int.Parse(mm.Groups[1].Value), b = int.Parse(mm.Groups[2].Value); if (b < a) { var x = a; a = b; b = x; } return Rnd.Next(a, b + 1).ToString(); } return m.Value; }
                if (k.StartsWith("now:")) { try { return DateTime.Now.ToString(k.Substring(4)); } catch (Exception) { return ""; } }
                if (ctx.TryGetValue(k, out v)) return v ?? "";
                return "";
            });
        }
        static bool Compare(string l, string op, string r)
        {
            op = (op ?? "==").Trim().ToLowerInvariant(); l = l ?? ""; r = r ?? "";
            var inv = System.Globalization.CultureInfo.InvariantCulture; double a, b;
            bool num = double.TryParse(l, System.Globalization.NumberStyles.Float, inv, out a) && double.TryParse(r, System.Globalization.NumberStyles.Float, inv, out b);
            if (!num) { a = 0; b = 0; } else double.TryParse(r, System.Globalization.NumberStyles.Float, inv, out b);
            switch (op)
            {
                case "==": case "equals": return num ? a == b : string.Equals(l, r, StringComparison.OrdinalIgnoreCase);
                case "!=": case "notequals": return num ? a != b : !string.Equals(l, r, StringComparison.OrdinalIgnoreCase);
                case ">": return num && a > b; case ">=": return num && a >= b; case "<": return num && a < b; case "<=": return num && a <= b;
                case "contains": return l.IndexOf(r, StringComparison.OrdinalIgnoreCase) >= 0;
                case "startswith": return l.StartsWith(r, StringComparison.OrdinalIgnoreCase);
                case "matches": try { return Regex.IsMatch(l, r, RegexOptions.IgnoreCase); } catch (Exception) { return false; }
                case "empty": return l == "";
                case "notempty": return l != "";
                case "true": return l.ToLowerInvariant() == "true"; case "false": return l.ToLowerInvariant() != "true";
            }
            return false;
        }
        static bool CondOk(JToken c, Dictionary<string, string> ctx)
        {
            var o = c as JObject; if (o == null) return true;
            return Compare(Expand((string)o["left"], ctx), (string)o["op"], Expand((string)o["right"], ctx));
        }

        // ---------------- triggers ----------------
        static int PermRank(string p) { switch ((p ?? "everyone").ToLowerInvariant()) { case "sub": return 1; case "vip": return 2; case "mod": return 3; case "broadcaster": return 4; default: return 0; } }
        static int UserRank(int role, bool sub) { return role >= 4 ? 4 : role >= 3 ? 3 : role == 2 ? 2 : sub ? 1 : 0; }

        /// <summary>chat line: returns true when a command trigger consumed it (the bots should not also answer it).</summary>
        public static bool OnChat(string display, string text, int role, bool isSub, bool first, string msgId, string replyTo, int subTier = 0)
        {
            bool consumed = false;
            string login = (display ?? "").ToLowerInvariant(); text = (text ?? "").Trim(); if (text == "") return false;
            bool firstToday = Roster.FirstToday(login);
            string cmd = text.StartsWith("!") ? text.Split(' ')[0] : ""; string rest = cmd != "" && text.Length > cmd.Length ? text.Substring(cmd.Length).Trim() : "";
            var volm = Regex.Match(cmd, @"^!(vol|volume)(\d{1,3})$", RegexOptions.IgnoreCase); if (volm.Success) { cmd = "!" + volm.Groups[1].Value; rest = (volm.Groups[2].Value + " " + rest).Trim(); }   // "!vol60" = "!vol 60"
            foreach (var a in Actions())
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    string type = ((string)t["type"] ?? "").ToLowerInvariant(); bool hit = false;
                    if (type == "command" && cmd != "") hit = (t["names"] as JArray ?? new JArray()).Any(n => string.Equals((string)n, cmd, StringComparison.OrdinalIgnoreCase) || string.Equals((string)n, cmd.TrimStart('!'), StringComparison.OrdinalIgnoreCase));
                    else if (type == "chat") { string pat = (string)t["pattern"]; try { hit = !string.IsNullOrEmpty(pat) && Regex.IsMatch(text, pat, RegexOptions.IgnoreCase); } catch (Exception) { } }
                    else if (type == "first_message") hit = first;
                    else if (type == "first_today") hit = firstToday;
                    if (!hit) continue;
                    if (UserRank(role, isSub) < PermRank((string)t["permission"])) continue;
                    var ctx = BaseCtx(login, display, text, role, isSub, msgId, replyTo); ctx["subTier"] = (isSub ? Math.Max(1, subTier >= 1000 ? subTier / 1000 : subTier) : 0).ToString(); ctx["command"] = cmd; ctx["args"] = rest;
                    var parts = rest.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries); for (int i = 0; i < parts.Length && i < 9; i++) ctx["arg" + (i + 1)] = parts[i];
                    ctx["input"] = rest;
                    if (!CooldownOk(a, t, login, role)) continue;
                    Run(a, "chat:" + (cmd != "" ? cmd : type), ctx);
                    if (type == "command" && (bool?)t["consume"] != false) consumed = true;
                }
            return consumed;
        }

        static Dictionary<string, string> BaseCtx(string login, string display, string text, int role, bool sub, string msgId, string replyTo)
        {
            return new Dictionary<string, string> {
                { "user", display ?? login }, { "userName", login }, { "display", display ?? login }, { "message", text }, { "role", role.ToString() },
                { "isMod", (role >= 3).ToString().ToLowerInvariant() }, { "isSub", sub.ToString().ToLowerInvariant() }, { "isVip", (role == 2).ToString().ToLowerInvariant() },
                { "isBroadcaster", (role >= 4).ToString().ToLowerInvariant() }, { "msgId", msgId ?? "" }, { "replyTo", replyTo ?? "" }, { "channel", Channel() }, { "args", "" } };
        }
        static string Channel() { try { return (string)LoadSecrets()["Channel"] ?? ""; } catch (Exception) { return ""; } }
        static JObject LoadSecrets() { try { var f = Path.Combine(DataDir, "host_secrets.json"); return File.Exists(f) ? JObject.Parse(File.ReadAllText(f)) : new JObject(); } catch (Exception) { return new JObject(); } }

        static bool CooldownOk(JObject a, JObject t, string login, int role)
        {
            int g = (int?)t["cooldownSec"] ?? 0, u = (int?)t["userCooldownSec"] ?? 0; if (g <= 0 && u <= 0) return true;
            if (role >= 4 && (bool?)t["streamerBypass"] != false) return true;
            lock (L)
            {
                var now = DateTime.UtcNow; string kg = (string)a["id"] + "|g|" + (t.Path), ku = (string)a["id"] + "|u|" + t.Path + "|" + login; DateTime d;
                if (g > 0 && _cool.TryGetValue(kg, out d) && (now - d).TotalSeconds < g) return false;
                if (u > 0 && _cool.TryGetValue(ku, out d) && (now - d).TotalSeconds < u) return false;
                if (g > 0) _cool[kg] = now; if (u > 0) _cool[ku] = now; return true;
            }
        }

        /// <summary>Twitch events (EventSub): args = the dictionary the bots get (eventType, userName, tier, bits, viewers ...).</summary>
        public static void OnEvent(Dictionary<string, object> args)
        {
            object et; if (!args.TryGetValue("eventType", out et)) return; string kind;
            switch ((string)et) { case "TwitchFollow": kind = "follow"; break; case "TwitchSub": kind = "sub"; break; case "TwitchReSub": kind = "resub"; break; case "TwitchGiftBomb": kind = "gift"; break;
                case "TwitchCheer": kind = "cheer"; break; case "TwitchRaid": kind = "raid"; break; case "TwitchRaidOut": kind = "raid_out"; break; case "TwitchRaidStart": kind = "raid_start"; break; case "TwitchPoll": kind = "poll"; break; case "TwitchPrediction": kind = "prediction"; break; case "TwitchHype": kind = "hype"; break; case "TwitchBan": kind = "ban"; break; case "TwitchUnban": kind = "unban"; break; case "TwitchMod": kind = "mod"; break; case "TwitchUnmod": kind = "unmod"; break; case "TwitchRedeem": kind = "redeem"; break; case "StreamOnline": kind = "stream_online"; break; case "StreamOffline": kind = "stream_offline"; break; default: return; }
            var ctx = new Dictionary<string, string>(); foreach (var kv in args) ctx[kv.Key] = Convert.ToString(kv.Value, System.Globalization.CultureInfo.InvariantCulture) ?? "";
            string u = ctx.ContainsKey("userName") ? ctx["userName"] : ""; ctx["user"] = u; ctx["display"] = u; ctx["raider"] = u; ctx["channel"] = Channel(); ctx["event"] = kind;
            if (kind == "stream_online" || kind == "stream_offline") SpotifyLive(kind == "stream_online");
            if (kind == "stream_online") { try { Program.ResetFirsts(); Session.Begin(); Roster.Reset(); } catch (Exception) { } }
            try { Latest.Record(kind, ctx); } catch (Exception ex) { Clog.Warn("latest", "could not record the event: " + ex.Message); }
            try { Economy.PointsEvent(args, kind == "follow" && Latest.LastRefollow); } catch (Exception) { }
            if (kind == "stream_online") { lock (typeof(Auto)) _landedAt = DateTime.MinValue; try { SetVar("raid.target", "", true); } catch (Exception) { } }   // !leftbehind works from the raid until the next stream starts
            if (kind == "stream_offline" && JustLanded()) { Clog.Info("automation", "stream offline after the raid landing: the goodnight was already said"); return; }
            if (kind == "stream_offline") { if (HoldOffline(ctx)) return; OfflineFires++; }   // a raid is on its way: the goodnight waits for it (see HoldOffline)
            if (kind == "raid_out") { ScheduleRaidOut(ctx); return; }   // Twitch sends this when the countdown starts: the landing (goodnight, then StopStream) happens when the chat empties or the countdown runs out
            Fire(kind, ctx);
        }
        static int RaidDelaySec() { return RaidDelayOverrideSec >= 0 ? RaidDelayOverrideSec : (int)Math.Max(0, Math.Min(88, (int?)Latest.Settings()["RaidStartDelaySec"] ?? 80)); }
        static System.Threading.Timer _raidOutTimer, _watchTimer; static DateTime _raidOutAt = DateTime.MinValue, _landedAt = DateTime.MinValue; internal static int RaidOutFires; internal static int ChatWatchSec = 4; internal static int RaidLandGraceSec = 3;
        /// <summary>chatters in the channel right now (Helix), null = not known.</summary>
        internal static Func<int?> ChatterCount = () =>
        {
            try
            {
                JToken dtok; string err; string code = TwitchApi.Call(HttpMethod.Get, "/chat/chatters?broadcaster_id={bid}&moderator_id={bid}&first=1000", null, out dtok, out err);
                return code == "200" && dtok is JArray ? ((JArray)dtok).Count : (int?)null;
            }
            catch (Exception) { return null; }
        };
        /// <summary>login of the channel we raided, "" before a raid / after the next stream started (!leftbehind)</summary>
        public static string RaidTargetNow() { return GetVar("raid.target"); }
        static bool JustLanded() { lock (typeof(Auto)) return _landedAt != DateTime.MinValue && (DateTime.UtcNow - _landedAt).TotalMinutes < 10; }
        /// <summary>raid_out arrives with the countdown: the raid lands (goodnight, then StopStream) the moment the chat empties (Raid Now clicked), or when Twitch's 90 s countdown runs out, once per raid</summary>
        static void ScheduleRaidOut(Dictionary<string, string> ctx)
        {
            lock (typeof(Auto)) { if ((DateTime.UtcNow - _raidOutAt).TotalMinutes < 3) return; _raidOutAt = DateTime.UtcNow; _landedAt = DateTime.MinValue; }
            // 10-28: Twitch sends channel.raid when the raid EXECUTES (Raid Now / countdown over), 48-137 s after the raid was picked; the stream goes offline ~20 s later. So the event IS the landing:
            // by default the goodnight + StopStream go out a few seconds after it (after the emotes + Discord lines). RaidStartDelaySec in latest_settings.json (or the test override) keeps the old chat-watch / countdown timing.
            if (RaidDelayOverrideSec < 0 && Latest.Settings()["RaidStartDelaySec"] == null)
            {
                double since; lock (typeof(Auto)) since = (DateTime.UtcNow - _raidStartAt).TotalSeconds;
                int wait = (int)Math.Max(1, Math.Ceiling(RaidLandGraceSec - since));
                lock (typeof(Auto)) { if (_raidOutTimer != null) _raidOutTimer.Dispose(); _raidOutTimer = new System.Threading.Timer(_ => LandRaid(ctx, "the raid event: Twitch moved the viewers"), null, wait * 1000, System.Threading.Timeout.Infinite); }
                return;
            }
            int delay = RaidDelaySec() + (RaidDelayOverrideSec >= 0 ? 0 : 10); if (delay == 0) { LandRaid(ctx, "no delay"); return; }
            lock (typeof(Auto)) { if (_raidOutTimer != null) _raidOutTimer.Dispose(); _raidOutTimer = new System.Threading.Timer(_ => LandRaid(ctx, "Twitch's countdown ran out"), null, delay * 1000, System.Threading.Timeout.Infinite); }
            StartChatWatch(ctx, delay);
        }
        /// <summary>best effort: Raid Now empties the chat; two polls in a row at at or under 20% of the crowd seen before = landed. If Twitch gives no list, the countdown timer above does it.</summary>
        static void StartChatWatch(Dictionary<string, string> ctx, int maxSec)
        {
            int peak = 0, low = 0; DateTime t0 = DateTime.UtcNow; bool busy = false;
            lock (typeof(Auto)) { if (_watchTimer != null) _watchTimer.Dispose(); }
            System.Threading.Timer tm = null;
            tm = new System.Threading.Timer(_ =>
            {
                if (busy) return; busy = true;
                try
                {
                    if ((DateTime.UtcNow - t0).TotalSeconds > maxSec) { tm.Dispose(); return; }
                    int? n = ChatterCount(); if (n == null) return;
                    if (n.Value > peak) peak = n.Value;
                    if (peak >= 3 && n.Value * 5 <= peak && (DateTime.UtcNow - t0).TotalSeconds >= 6) low++; else low = 0;
                    if (low >= 2) { tm.Dispose(); LandRaid(ctx, "the chat emptied (" + n.Value + " of " + peak + ")"); }
                }
                catch (Exception ex) { Clog.Warn("automation", "raid chat watch: " + ex.Message); }
                finally { busy = false; }
            }, null, 0, ChatWatchSec * 1000);   // the first poll is at once: it is the pre-raid crowd
            lock (typeof(Auto)) _watchTimer = tm;
        }
        static bool RaidOutStops() { return Actions().Any(a => (bool?)a["enabled"] != false && (a["triggers"] as JArray ?? new JArray()).OfType<JObject>().Any(tr => (string)tr["type"] == "raid_out") && (a["steps"] as JArray ?? new JArray()).OfType<JObject>().Any(s => (string)s["type"] == "obs_request" && string.Equals((string)s["request"], "StopStream", StringComparison.OrdinalIgnoreCase))); }
        /// <summary>the raid landed: the goodnight first (the held one when Ivan already ended the stream by hand, else a fresh one), THEN raid_out (StopStream), once. The StopStream is checked: OBS must say the stream is off, one retry, a failure is logged loudly.</summary>
        internal static void LandRaid(Dictionary<string, string> ctx, string why)
        {
            Dictionary<string, string> held;
            lock (typeof(Auto))
            {
                if (JustLanded()) return; _landedAt = DateTime.UtcNow;
                if (_raidOutTimer != null) { _raidOutTimer.Dispose(); _raidOutTimer = null; }
                if (_watchTimer != null) { _watchTimer.Dispose(); _watchTimer = null; }
                _raidPendingAt = DateTime.MinValue; held = _heldOffline; _heldOffline = null; if (_heldTimer != null) { _heldTimer.Dispose(); _heldTimer = null; }
            }
            try { if (File.Exists(HeldP)) File.Delete(HeldP); } catch (Exception) { }
            Clog.Info("automation", "raid landed (" + why + "): goodnight, then StopStream");
            var gc = new Dictionary<string, string>(held ?? ctx); gc["event"] = "stream_offline";
            _runInline = true;
            try { OfflineFires++; Fire("stream_offline", gc); RaidOutFires++; Fire("raid_out", ctx); } finally { _runInline = false; }
            if (RaidOutStops()) VerifyStopped();
        }
        static void VerifyStopped()
        {
            for (int attempt = 0; attempt < 2; attempt++)
            {
                bool? on = null; for (int i = 0; i < 6; i++) { on = Program.ObsStreamingNow(); if (on != true) break; System.Threading.Thread.Sleep(1000); }
                if (on == false) { Clog.Info("obs", "StopStream checked: OBS reports the stream is off"); return; }
                if (on == null) { Clog.Error("obs", "RAID LANDED BUT THE STREAM WAS NOT STOPPED BY THE HOST: OBS is not connected (or did not answer) - end the stream by hand"); return; }
                if (attempt == 0) { bool r = false; try { r = Program.ObsRaw("StopStream", new JObject()); } catch (Exception) { } Clog.Warn("obs", "OBS still streaming after StopStream: sent it again (" + (r ? "accepted" : "refused") + ")"); }
            }
            Clog.Error("obs", "RAID LANDED BUT OBS IS STILL STREAMING after two StopStream requests - end the stream by hand");
        }

        static void Fire(string kind, Dictionary<string, string> ctx)
        {
            using (ReplyCtx.Plain()) FireCore(kind, ctx);   // an event's lines are never replies to the last chat message this thread handled (a stale parent is refused by Twitch)
        }
        static void FireCore(string kind, Dictionary<string, string> ctx)
        {
            int num(string k) { int v; return ctx.ContainsKey(k) && int.TryParse(ctx[k], out v) ? v : 0; }
            foreach (var a in Actions())
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    if (!string.Equals((string)t["type"], kind, StringComparison.OrdinalIgnoreCase)) continue;
                    int amount = kind == "cheer" ? num("bits") : kind == "raid" ? num("viewers") : kind == "gift" ? Math.Max(1, num("total")) : 0;
                    int min = (int?)t["min"] ?? -1, max = (int?)t["max"] ?? -1;
                    if (min >= 0 && amount < min) continue; if (max >= 0 && amount > max) continue;
                    string tier = (string)t["tier"]; if (!string.IsNullOrEmpty(tier) && tier != "any" && ctx.ContainsKey("tier") && ctx["tier"] != tier) continue;
                    if (kind == "redeem") { string title = (string)t["title"], rwId = (string)t["rewardId"]; if (!string.IsNullOrEmpty(rwId)) { if (rwId != (ctx.ContainsKey("rewardId") ? ctx["rewardId"] : "")) continue; } else if (!string.IsNullOrEmpty(title) && title != "*" && !string.Equals(title, ctx.ContainsKey("title") ? ctx["title"] : "", StringComparison.OrdinalIgnoreCase)) continue; }
                    if (!CooldownOk(a, t, ctx.ContainsKey("userName") ? ctx["userName"] : "", 0)) continue;
                    if (kind == "redeem" && (string)a["id"] == "spotify-redeem" && SongifyOwns()) { Clog.Info("automation", "song request redeem left to Songify (the module reports songify:true)"); continue; }
                    Run(a, kind, new Dictionary<string, string>(ctx));
                }
        }
        /// <summary>the raid was scheduled (the Twitch countdown began): fires the raid_start automations; the raid landing is raid_out</summary>
        static DateTime _raidStartAt = DateTime.MinValue;
        /// <summary>Fires raid_start ("prepare your emotes") once per raid: !confirm raid (the countdown began), the Master View Raid prep button, or the outgoing channel.raid event when the raid was started on twitch.tv (Twitch only tells us when it goes). Returns false when it already fired in the last 3 minutes.</summary>
        public static bool OnRaidScheduled(string target, bool now = false)
        {
            if (Regex.IsMatch(target ?? "", "^[A-Za-z0-9_]{1,25}$")) { try { SetVar("raid.target", target.ToLowerInvariant(), true); } catch (Exception) { } }   // also when the line already went out (Sery's signal has no target; the channel.raid event brings it)
            lock (typeof(Auto)) { if ((DateTime.UtcNow - _raidStartAt).TotalMinutes < 3) return false; _raidStartAt = DateTime.UtcNow; }
            // Ivan, like Streamer.bot had it: the moment the raid is picked (Twitch's countdown starts) the shoutout, the emotes line and the Discord line go out at once; no hold any more
            lock (typeof(Auto)) { _raidPendingAt = DateTime.UtcNow; }
            FireRaidStart(target); return true;
        }
        /// <summary>Sery_Bot says its goodbye line the moment a raid is picked (48-137 s before Twitch's channel.raid event, which only comes when the raid executes): that line is our earliest signal.
        /// Settings (latest_settings.json): RaidSignalBot (default sery_bot), RaidSignalText (default "Have a great rest of your day"); "" in either turns this off.</summary>
        public static bool OnChatSignal(string nick, string text)
        {
            var st = Latest.Settings(); string bot = ((string)st["RaidSignalBot"] ?? "sery_bot").Trim().ToLowerInvariant(), key = ((string)st["RaidSignalText"] ?? "Have a great rest of your day").Trim();
            if (bot == "" || key == "" || (nick ?? "").ToLowerInvariant() != bot || (text ?? "").IndexOf(key, StringComparison.OrdinalIgnoreCase) < 0) return false;
            if (LiveState.Live == false) return false;   // not streaming: a goodbye line is not a raid
            bool fired = OnRaidScheduled("");
            if (fired) Clog.Info("automation", "raid start signal: " + bot + " said its goodbye line");
            return fired;
        }
        static System.Threading.Timer _raidTimer; internal static int RaidDelayOverrideSec = -1; internal static int RaidStartFires;
        /// <summary>!unraid or the stream going offline before the line was due: nothing is said and a new raid can start the line again</summary>
        public static void CancelRaidStart() { ClearPending(); ReleaseOffline(); lock (typeof(Auto)) { if (_raidTimer != null) { _raidTimer.Dispose(); _raidTimer = null; _raidStartAt = DateTime.MinValue; } if (_raidOutTimer != null) { _raidOutTimer.Dispose(); _raidOutTimer = null; _raidOutAt = DateTime.MinValue; } if (_watchTimer != null) { _watchTimer.Dispose(); _watchTimer = null; } } }
        internal static void ResetRaidStart() { ClearPending(); _heldOffline = null; lock (typeof(Auto)) { _raidStartAt = DateTime.MinValue; _raidOutAt = DateTime.MinValue; _landedAt = DateTime.MinValue; if (_watchTimer != null) { _watchTimer.Dispose(); _watchTimer = null; } if (_raidTimer != null) { _raidTimer.Dispose(); _raidTimer = null; } if (_raidOutTimer != null) { _raidOutTimer.Dispose(); _raidOutTimer = null; } } }
        // ---- a goodnight must not be said while the raid is still on its way ----
        static DateTime _raidPendingAt = DateTime.MinValue; static Dictionary<string, string> _heldOffline; static System.Threading.Timer _heldTimer; internal static int HoldMaxSec = 180; internal static int OfflineFires;
        static void ClearPending() { lock (typeof(Auto)) _raidPendingAt = DateTime.MinValue; }
        static bool RaidPending() { lock (typeof(Auto)) return _raidPendingAt != DateTime.MinValue && (DateTime.UtcNow - _raidPendingAt).TotalSeconds < HoldMaxSec; }
        /// <summary>stream_offline while a raid is pending (raid_start seen, raid_out / cancel not yet): hold it, at most HoldMaxSec (~3 min). true = held (the caller must not fire it).</summary>
        static bool HoldOffline(Dictionary<string, string> ctx)
        {
            lock (typeof(Auto))
            {
                if (!RaidPending()) return false;
                _heldOffline = ctx; if (_heldTimer != null) _heldTimer.Dispose();
                int left = (int)Math.Max(1, HoldMaxSec - (DateTime.UtcNow - _raidPendingAt).TotalSeconds);
                _heldTimer = new System.Threading.Timer(_ => { ClearPending(); ReleaseOffline(); }, null, left * 1000, System.Threading.Timeout.Infinite);
            }
            try { File.WriteAllText(HeldP, new JObject { { "at", DateTime.UtcNow.ToString("o") }, { "ctx", JObject.FromObject(ctx) } }.ToString()); } catch (Exception) { }   // survives a crash / restart during the hold
            Clog.Info("automation", "stream offline held: a raid is on its way"); return true;
        }
        /// <summary>the raid landed or was cancelled (or the hold ran out): the held goodnight runs now</summary>
        static void ReleaseOffline()
        {
            Dictionary<string, string> c; lock (typeof(Auto)) { _raidPendingAt = DateTime.MinValue; c = _heldOffline; _heldOffline = null; if (_heldTimer != null) { _heldTimer.Dispose(); _heldTimer = null; } }
            try { if (File.Exists(HeldP)) File.Delete(HeldP); } catch (Exception) { }
            if (c != null) { OfflineFires++; Fire("stream_offline", c); }
        }
        static string HeldP { get { return Path.Combine(HostApi.DataDir, "held_offline.json"); } }
        /// <summary>at Host start: a goodnight that was held when the Host stopped (crash / restart during a raid) is not lost: it runs now when it is under 15 minutes old. Returns whether it ran.</summary>
        public static bool RecoverHeldOffline()
        {
            try
            {
                if (_heldOffline != null) return false;   // this run already holds one: the marker is its own, not a leftover
                if (!File.Exists(HeldP)) return false;
                JObject j; using (var rd = new Newtonsoft.Json.JsonTextReader(new StringReader(File.ReadAllText(HeldP))) { DateParseHandling = Newtonsoft.Json.DateParseHandling.None }) j = JObject.Load(rd); File.Delete(HeldP);
                DateTime at; if (!DateTime.TryParse((string)j["at"], System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.RoundtripKind, out at) || (DateTime.UtcNow - at.ToUniversalTime()).TotalMinutes > 15) return false;
                var c = new Dictionary<string, string>(); foreach (var pr in ((JObject)j["ctx"]).Properties()) c[pr.Name] = (string)pr.Value ?? "";
                Clog.Info("automation", "held goodnight recovered after a restart"); OfflineFires++; Fire("stream_offline", c); return true;
            }
            catch (Exception ex) { Clog.Warn("automation", "held goodnight not recovered: " + ex.Message); return false; }
        }
        static void FireRaidStart(string target) { RaidStartFires++; Fire("raid_start", new Dictionary<string, string> { { "channel", Channel() }, { "target", target ?? "" }, { "event", "raid_start" } }); }
        /// <summary>customs queue went from closed to open (HostEventLog sees the edge once per opening; a Host restart with the queue already open is no edge). Runs the "queue_open" trigger actions, e.g. the !rules line.</summary>
        public static void OnQueueOpen() { Fire("queue_open", new Dictionary<string, string> { { "channel", Channel() }, { "event", "queue_open" } }); }
        public static void OnStream(bool online) { if (!online) CancelRaidStart(); if (online) Program.ResetFirsts(); Fire(online ? "stream_online" : "stream_offline", new Dictionary<string, string> { { "channel", Channel() } }); }

        public static JObject Hotkey(string key)
        {
            int n = 0;
            foreach (var a in Actions())
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                    if (string.Equals((string)t["type"], "hotkey", StringComparison.OrdinalIgnoreCase) && string.Equals((string)t["key"], key, StringComparison.OrdinalIgnoreCase)) { n++; Run(a, "hotkey:" + key, new Dictionary<string, string> { { "channel", Channel() }, { "hotkey", key } }); break; }
            return new JObject { { "ok", true }, { "ran", n } };
        }

        /// <summary>checks timers every 5 s: every N seconds, and optionally only if at least M chat messages arrived since the last run.</summary>
        public static void StartTimers()
        {
            Task.Run(async () =>
            {
                await Task.Delay(8000);
                while (true)
                {
                    try
                    {
                        if (Lease.MayRun && HostApi.IrcConnected)
                        {
                            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                            foreach (var a in Actions())
                                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                                {
                                    if (!string.Equals((string)t["type"], "timer", StringComparison.OrdinalIgnoreCase)) continue;
                                    int every = Math.Max(10, (int?)t["everySec"] ?? 600); string key = (string)a["id"] + "|" + t.Path; long last;
                                    if (!_timerLast.TryGetValue(key, out last)) { _timerLast[key] = now; _timerMsgs[key] = HostApi.Messages; continue; }
                                    if (now - last < every) continue;
                                    long since = HostApi.Messages - (_timerMsgs.ContainsKey(key) ? _timerMsgs[key] : 0);
                                    if (since < ((int?)t["minChatMessages"] ?? 0)) continue;
                                    _timerLast[key] = now; _timerMsgs[key] = HostApi.Messages;
                                    Run(a, "timer", new Dictionary<string, string> { { "channel", Channel() } });
                                }
                        }
                    }
                    catch (Exception ex) { Clog.Warn("automation", "timer loop: " + ex.Message); }
                    await Task.Delay(5000);
                }
            });
        }

        // ---------------- run ----------------
        public static JObject Test(string idOrName, JObject args, bool dry)
        {
            var a = FindAction(idOrName); if (a == null) return new JObject { { "ok", false }, { "error", "no such action" } };
            var ctx = BaseCtx("tester", "Tester", "!test", 4, true, "test", ""); ctx["command"] = "!test"; ctx["viewers"] = "42"; ctx["bits"] = "100"; ctx["tier"] = "1"; ctx["raider"] = "Tester";
            if (args != null) foreach (var kv in args) ctx[kv.Key] = (string)kv.Value ?? "";
            var entry = RunNow(a, dry ? "manual test (dry run)" : "manual run", ctx, dry);
            return new JObject { { "ok", (bool)entry["ok"] }, { "run", entry } };
        }

        [ThreadStatic] static bool _runInline;   // set only while the raid_out timer fires its automations: they run on that thread, so the caller can wait for them
        static void Run(JObject a, string why, Dictionary<string, string> ctx)
        {
            if (!Lease.MayRun || _paused) return;
            if (_runInline) { try { RunNow(a, why, ctx, false); } catch (Exception ex) { Clog.Error("automation", (string)a["name"] + ": " + ex.Message); } return; }
            Task.Run(() => { try { RunNow(a, why, ctx, false); } catch (Exception ex) { Clog.Error("automation", (string)a["name"] + ": " + ex.Message); } });
        }

        static JObject RunNow(JObject a, string why, Dictionary<string, string> ctx, bool test)
        {
            string id = (string)a["id"]; object lk; lock (L) { if (!_locks.TryGetValue(id, out lk)) _locks[id] = lk = new object(); }
            var outp = new JArray(); var sw = Stopwatch.StartNew(); bool ok = true; string err = "";
            System.Threading.Interlocked.Increment(ref _waiting);
            lock (lk)
            {
                System.Threading.Interlocked.Decrement(ref _waiting); lock (L) _running[id] = (string)a["name"];
                try
                {
                    foreach (var c in (a["conditions"] as JArray ?? new JArray())) if (!CondOk(c, ctx)) { outp.Add("condition not met: skipped"); goto done; }
                    int budget = MaxSteps; Exec(a["steps"] as JArray, ctx, outp, ref budget, test, 0);
                }
                catch (StopAction) { }
                catch (Exception ex) { ok = false; err = ex.Message; }
                finally { lock (L) _running.Remove(id); }
            }
            done:
            if (!test) NoteFire(id);
            var e = new JObject { { "ts", DateTime.UtcNow.ToString("o") }, { "action", a["name"] }, { "id", id }, { "trigger", why }, { "ok", ok }, { "ms", sw.ElapsedMilliseconds }, { "error", err }, { "output", outp }, { "test", test } };
            lock (L) { _log.Add(e); if (_log.Count > 200) _log.RemoveAt(0); }
            if (ok) Clog.Info("automation", "ran '" + (string)a["name"] + "' (" + why + ", " + sw.ElapsedMilliseconds + " ms)"); else Clog.Warn("automation", "'" + (string)a["name"] + "' failed: " + err);
            return e;
        }
        class StopAction : Exception { }
        public static JArray Log(int n) { lock (L) return new JArray(_log.Skip(Math.Max(0, _log.Count - n)).Reverse()); }

        static void Exec(JArray steps, Dictionary<string, string> ctx, JArray outp, ref int budget, bool test, int depth)
        {
            if (steps == null) return; if (depth > 8) throw new Exception("steps nested too deeply");
            foreach (var st in steps.OfType<JObject>())
            {
                if (--budget < 0) throw new Exception("too many steps (" + MaxSteps + ")");
                if ((bool?)st["enabled"] == false) continue;
                string type = ((string)st["type"] ?? "").ToLowerInvariant(); string x(string k) { return Expand((string)st[k], ctx); }
                switch (type)
                {
                    case "say": { string t = x("text"); if (t != "") outp.Add(Say((string)st["as"] ?? "core", t, test)); break; }
                    case "random_say": { var arr = (st["texts"] as JArray ?? new JArray()).Select(v => Expand((string)v, ctx)).Where(v => v != "").ToList(); if (arr.Count > 0) outp.Add(Say((string)st["as"] ?? "core", arr[Rnd.Next(arr.Count)], test)); break; }
                    case "delay": { int ms; if (!int.TryParse(x("ms"), out ms)) ms = 0; int rvs; if ((bool?)st["skipSmallRaid"] == true && ctx.ContainsKey("viewers") && int.TryParse(ctx["viewers"], out rvs) && rvs < ((int?)Latest.Settings()["RaidMinViewers"] ?? 3)) { outp.Add("no wait: this raid is too small for a shoutout"); break; } ms = Math.Max(0, Math.Min(600000, ms)); Thread.Sleep(test ? Math.Min(ms, 300) : ms); outp.Add("waited " + ms + " ms"); break; }   // the wait before the auto shoutout is pointless when no shoutout follows
                    case "obs_scene": { string s = x("scene"); outp.Add(test ? "(dry run) would switch OBS scene to " + s : Obs(() => Program.ObsScene(s), "scene -> " + s)); break; }
                    case "obs_source": { string sc = x("scene"), so = x("source"), v = ((string)st["visible"] ?? "true").ToLowerInvariant(); outp.Add(test ? "(dry run) would set OBS source " + so + " to " + v : Obs(() => Program.ObsSource(sc, so, v), "source " + so + " -> " + v)); break; }
                    case "obs_request": { string rt = (string)st["request"] ?? ""; var data = st["data"] as JObject; var d2 = data == null ? new JObject() : JObject.Parse(Expand(data.ToString(), ctx)); outp.Add(test ? "(dry run) would send OBS request " + rt : rt == "StopStream" && Program.ObsStreamingNow() == false ? StopSkipped() : Obs(() => Program.ObsRaw(rt, d2), "OBS " + rt)); break; }
                    case "sound": outp.Add(Sound(x("file"), (double?)st["volume"] ?? 1.0, test)); break;
                    case "http": outp.Add(test ? "(dry run) would call " + x("url") : Http(st, ctx, test)); break;
                    case "module_command": outp.Add(test ? "(dry run) would call module " + x("url") : ModuleCommand(st, ctx, test)); break;
                    case "bot_command": { string t = x("text"); if (!test && ReplyCtx.Platform != "twitch") { outp.Add("bot command skipped: chat from " + ReplyCtx.Platform + " never runs Twitch bot commands"); break; } if (!test) Task.Run(() => Program.Dispatch(Channel() == "" ? "streamer" : Channel(), t, "auto-" + Guid.NewGuid().ToString("N"), 4, "", false, null)); outp.Add((test ? "(test) would run " : "ran ") + "bot command: " + t); break; }
                    case "timeout": { string u = x("user"), why = x("reason"); int secs = (int?)st["seconds"] ?? 60; bool r = !test && Program.TimeoutUser(u, secs, why); outp.Add((test ? "(test) would time out " : r ? "timed out " : "could not time out ") + u + " " + secs + " s"); break; }
                    case "set_var": SetVar(x("name"), x("value"), (bool?)st["persist"] == true); outp.Add("var " + x("name") + " = " + x("value")); break;
                    case "inc_var": { double cur; double.TryParse(GetVar(x("name")), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out cur); double by = (double?)st["by"] ?? 1; cur += by; SetVar(x("name"), cur.ToString(System.Globalization.CultureInfo.InvariantCulture), (bool?)st["persist"] == true); ctx["count"] = cur.ToString(System.Globalization.CultureInfo.InvariantCulture); outp.Add("var " + x("name") + " = " + ctx["count"]); break; }
                    case "log": outp.Add("log: " + x("text")); Clog.Info("automation", x("text")); break;
                    case "if": { bool ok = Compare(x("left"), (string)st["op"], x("right")); Exec((ok ? st["then"] : st["else"]) as JArray, ctx, outp, ref budget, test, depth + 1); break; }
                    case "run_action": { var other = FindAction(x("name")); if (other == null) outp.Add("run_action: no action named " + x("name")); else if ((bool?)st["wait"] == false && !test && PopupHold.TryExtend(other)) outp.Add("-> " + (string)other["name"] + " (already up: its end was pushed out)");
                        else if ((bool?)st["wait"] == false && !test) { outp.Add("-> " + (string)other["name"] + " (in the background)"); var oc = new Dictionary<string, string>(ctx); var oa = other; Task.Run(() => { try { RunNow(oa, "run_action from " + "another action", oc, false); } catch (Exception ex) { Clog.Error("automation", (string)oa["name"] + ": " + ex.Message); } }); } else { outp.Add("-> " + (string)other["name"]); Exec(other["steps"] as JArray, ctx, outp, ref budget, test, depth + 1); } break; }
                    case "comment": break;
                    case "stop": throw new StopAction();
                    default: { string extra = ExtraStep(type, st, ctx, test, x); outp.Add(extra ?? "unknown step '" + type + "' skipped"); break; }
                }
            }
        }

        static string Say(string role, string text, bool dry)
        {
            if (dry) return "(dry run) would say as " + role + ": " + text;
            string via; bool ok = HostApi.SendAs(role, text, out via);
            return (ok ? "said as " + via + ": " : "NOT sent (" + via + "): ") + text;
        }
        static string StopSkipped() { Clog.Info("obs", "StopStream skipped: OBS says the stream is already off"); return "OBS stream already off: StopStream skipped"; }
        static string Obs(Func<bool> f, string what) { try { if (f()) return "OBS " + what; Clog.Warn("obs", "automation OBS step failed (not connected or refused): " + what); return "OBS not connected or refused: " + what; } catch (Exception ex) { Clog.Warn("obs", "automation OBS step error: " + what + ": " + ex.Message); return "OBS error: " + ex.Message; } }

        internal static string Sound(string file, double vol, bool test)
        {
            if (string.IsNullOrWhiteSpace(file) || !File.Exists(file)) return "sound file not found: " + file;
            if (test) return "(test) would play " + Path.GetFileName(file);
            try
            {
                string ps = "Add-Type -AssemblyName presentationCore; $p=New-Object System.Windows.Media.MediaPlayer; $p.Open([uri]'" + file.Replace("'", "''") + "'); $p.Volume=" + Math.Max(0, Math.Min(1, vol)).ToString(System.Globalization.CultureInfo.InvariantCulture) + "; $p.Play(); Start-Sleep -Milliseconds 800; $d=0; while($p.NaturalDuration.HasTimeSpan -eq $false -and $d -lt 20){Start-Sleep -Milliseconds 200;$d++}; if($p.NaturalDuration.HasTimeSpan){Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds)}";
                Process.Start(new ProcessStartInfo("powershell", "-NoProfile -ExecutionPolicy Bypass -Command \"" + ps.Replace("\"", "\\\"") + "\"") { CreateNoWindow = true, UseShellExecute = false });
                return "playing " + Path.GetFileName(file);
            }
            catch (Exception ex) { return "sound failed: " + ex.Message; }
        }

        // module and website calls: loopback, private LAN, tailnet (100.64/10) and innocentpenguin.com only
        static bool UrlAllowed(Uri u)
        {
            if (u.Scheme != "http" && u.Scheme != "https") return false;
            string h = u.Host.ToLowerInvariant(); if (h == "localhost" || h == "innocentpenguin.com" || h.EndsWith(".innocentpenguin.com")) return true;
            IPAddress ip; if (!IPAddress.TryParse(h, out ip)) return h.EndsWith(".ts.net");
            if (IPAddress.IsLoopback(ip)) return true; var b = ip.GetAddressBytes(); if (b.Length != 4) return false;
            return b[0] == 10 || (b[0] == 192 && b[1] == 168) || (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 100 && b[1] >= 64 && b[1] <= 127);
        }
        static string Http(JObject st, Dictionary<string, string> ctx, bool dry)
        {
            string url = Expand((string)st["url"], ctx); Uri u; if (!Uri.TryCreate(url, UriKind.Absolute, out u) || !UrlAllowed(u)) return "http blocked (only this PC, the LAN, the tailnet and innocentpenguin.com): " + url;
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
                {
                    var rq = new HttpRequestMessage(new HttpMethod(((string)st["method"] ?? "GET").ToUpperInvariant()), u);
                    string body = Expand((string)st["body"], ctx); if (body != "") rq.Content = new StringContent(body, Encoding.UTF8, "application/json");
                    var r = h.SendAsync(rq).Result; string txt = r.Content.ReadAsStringAsync().Result;
                    ctx["http.status"] = ((int)r.StatusCode).ToString(); ctx["http.text"] = txt.Length > 500 ? txt.Substring(0, 500) : txt;
                    try { var j = JObject.Parse(txt); foreach (var p in j.Properties()) if (p.Value.Type != JTokenType.Object && p.Value.Type != JTokenType.Array) ctx["http." + p.Name] = (string)p.Value; } catch (Exception) { }
                    string extra = ""; if ((bool?)st["say"] == true && ctx.ContainsKey("http.say") && ctx["http.say"] != "") extra = " | " + Say((string)st["as"] ?? "core", ctx["http.say"], false);
                    return "http " + (string)st["method"] + " " + u.Host + " -> " + (int)r.StatusCode + extra;
                }
            }
            catch (Exception ex) { return "http failed: " + ex.Message; }
        }
        // POST {command,args,user,display,role,isMod,isSub,msgId} to a module's /api/chat-command; it answers {ok, say}; Host says it (the module token goes only to loopback)
        /// <summary>The Spotify module reopens song requests at go-live (/api/live/auto, only when its own offline close closed them) and closes them when the stream ends (/api/live/stop). Fire and forget, loopback only, module token from PINGUINO_API_TOKEN (never logged). Never from a sim Host.</summary>
        /// <summary>Songify owns the song-request redeems while the Spotify module's GET /api/state says "songify": true: the Host does nothing for them (no module call, no refund, no reply). Cached 10 s; a failed call or a missing key = false (as before). Loopback only, never from a sim Host.</summary>
        internal static Func<bool?> SongifyTest; static bool _sgVal; static DateTime _sgAt = DateTime.MinValue;
        static bool SongifyOwns()
        {
            if (SongifyTest != null) return SongifyTest() == true;
            if (HostApi.SimMode) return false;
            lock (typeof(Auto)) { if ((DateTime.UtcNow - _sgAt).TotalSeconds < 10) return _sgVal; _sgAt = DateTime.UtcNow; _sgVal = false; }
            bool v = false;
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(3) })
                {
                    var rq = new HttpRequestMessage(HttpMethod.Get, "http://127.0.0.1:8771/api/state");
                    string tok = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? ""; if (tok != "") { rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("X-Pinguino-Token", tok); }
                    var r = h.SendAsync(rq).Result; if (r.IsSuccessStatusCode) v = (bool?)JObject.Parse(r.Content.ReadAsStringAsync().Result)["songify"] == true;
                }
            }
            catch (Exception) { v = false; }
            lock (typeof(Auto)) _sgVal = v; return v;
        }
        static string _scLast = "";
        /// <summary>At go-live: ask the Spotify module's /api/selfcheck and name a red "api" item once (log line, same reason never repeated) so song redemptions don't fail silently.</summary>
        internal static string SpotifySelfcheckReason(string json)
        {
            try
            {
                foreach (var c in (JArray)JObject.Parse(json)["checks"])
                    if ((string)c["id"] == "api" && (bool?)c["ok"] == false) return (string)c["reason"] ?? "not answering";
            }
            catch (Exception) { }
            return "";
        }
        static void SpotifySelfcheck(HttpClient h)
        {
            try
            {
                string why = SpotifySelfcheckReason(h.GetStringAsync("http://127.0.0.1:8771/api/selfcheck").Result);
                lock (typeof(Auto)) { if (why == _scLast) return; _scLast = why; }
                if (why != "") Clog.Warn("automation", "go-live: Spotify is not answering (" + why + ") - song requests will be refused until it is");
            }
            catch (Exception ex) { Clog.Warn("automation", "go-live: Spotify selfcheck not reached: " + (ex.InnerException != null ? ex.InnerException.Message : ex.Message)); }
        }
        /// <summary>every reply to a viewer starts with @name (the module has a few lines without one, e.g. "Nothing is playing.")</summary>
        internal static string AtName(string user, string say)
        {
            if (string.IsNullOrEmpty(user) || string.IsNullOrEmpty(say) || say.StartsWith("@")) return say;
            return "@" + user.TrimStart('@') + " " + say;
        }
        static readonly Dictionary<string, List<DateTime>> _spDown = new Dictionary<string, List<DateTime>>();
        /// <summary>Spotify is down and the same viewer keeps redeeming: the points are refunded every time, but the chat hears it from the module twice, then once from us ("requests are paused"), then nothing for that viewer until 5 quiet minutes pass.</summary>
        internal static string SpotifyDownQuiet(string user, string say, DateTime now)
        {
            int n;
            lock (_spDown)
            {
                List<DateTime> l; string k = (user ?? "").ToLowerInvariant();
                if (!_spDown.TryGetValue(k, out l)) _spDown[k] = l = new List<DateTime>();
                l.RemoveAll(t => (now - t).TotalMinutes >= 5); l.Add(now); n = l.Count;
            }
            if (n <= 2) return say;
            if (n == 3) return "@" + (user ?? "").TrimStart('@') + " Spotify is down right now, so song requests are paused. Your points are refunded each time; I will stay quiet about it for a few minutes.";
            return "";
        }
        internal static Action<string> ModuleLiveTest;
        static void SpotifyLive(bool online)
        {
            string path = online ? "/api/live/auto" : "/api/live/stop";
            if (ModuleLiveTest != null) { ModuleLiveTest(path); return; }
            if (HostApi.SimMode || !Lease.MayRun) return;
            Task.Run(() =>
            {
                try
                {
                    using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
                    {
                        var rq = new HttpRequestMessage(HttpMethod.Post, "http://127.0.0.1:8771" + path) { Content = new StringContent("{}", Encoding.UTF8, "application/json") };
                        string tok = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? ""; if (tok != "") { rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("X-Pinguino-Token", tok); }
                        var r = h.SendAsync(rq).Result; Clog.Info("automation", "spotify module " + path + " -> " + (int)r.StatusCode);
                        if (online) SpotifySelfcheck(h);
                    }
                }
                catch (Exception ex) { Clog.Warn("automation", "spotify module " + path + " not reached: " + (ex.InnerException != null ? ex.InnerException.Message : ex.Message)); }
            });
        }
        static string ModuleCommand(JObject st, Dictionary<string, string> ctx, bool dry)
        {
            string url = Expand((string)st["url"], ctx); Uri u; if (!Uri.TryCreate(url, UriKind.Absolute, out u) || !UrlAllowed(u)) return "module command blocked: " + url;
            string cmd = (string)st["command"] ?? (ctx.ContainsKey("command") ? ctx["command"].TrimStart('!') : "");
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
                {
                    var body = new JObject { { "command", cmd }, { "args", ctx.ContainsKey("args") && ctx["args"] != "" ? ctx["args"] : ctx.ContainsKey("input") ? ctx["input"] : "" }, { "redeem", (bool?)st["redeem"] == true }, { "user", ctx.ContainsKey("userName") ? ctx["userName"] : "" }, { "display", ctx.ContainsKey("display") ? ctx["display"] : "" },
                        { "role", ctx.ContainsKey("role") ? ctx["role"] : "1" }, { "isMod", ctx.ContainsKey("isMod") && ctx["isMod"] == "true" }, { "isSub", ctx.ContainsKey("isSub") && ctx["isSub"] == "true" }, { "isVip", ctx.ContainsKey("isVip") && ctx["isVip"] == "true" }, { "subTier", ctx.ContainsKey("subTier") && int.TryParse(ctx["subTier"], out var stv) ? stv : 0 }, { "msgId", ctx.ContainsKey("msgId") ? ctx["msgId"] : "" } };
                    if ((cmd == "skip" || cmd == "voteskip") && (bool?)st["redeem"] != true) { body["role"] = "1"; body["isMod"] = false; try { SkipVote.Fill(body); } catch (Exception) { } }   // !skip = !voteskip for EVERYONE: one vote with the threshold from the people chatting lately (the Skip Song reward is not a vote: redeem=true skips)
                    var rq = new HttpRequestMessage(HttpMethod.Post, u) { Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json") };
                    string tok = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? ""; if (tok != "" && ((IPAddress.TryParse(u.Host, out var ip) && IPAddress.IsLoopback(ip)) || u.Host == "localhost")) rq.Headers.Add("Authorization", "Bearer " + tok);
                    var r = h.SendAsync(rq).Result; var j = JObject.Parse(r.Content.ReadAsStringAsync().Result);
                    if ((bool?)st["redeem"] == true && ctx.ContainsKey("redemptionId") && ctx["redemptionId"] != "")
                    {
                        string rid = ctx["redemptionId"], rw = ctx.ContainsKey("rewardId") ? ctx["rewardId"] : "";
                        if ((bool?)j["refund"] == true) Redeems.Cancel(rid, rw, ctx.ContainsKey("display") && ctx["display"] != "" ? ctx["display"] : ctx.ContainsKey("userName") ? ctx["userName"] : "");   // the module turned the song down: give the points back
                        else if ((bool?)j["ok"] != false) Redeems.Record(ctx.ContainsKey("userName") ? ctx["userName"] : "", rid, rw, ctx.ContainsKey("title") ? ctx["title"] : "");
                    }
                    string say = (string)j["say"] ?? ""; string disp = ctx.ContainsKey("display") && ctx["display"] != "" ? ctx["display"] : ctx.ContainsKey("userName") ? ctx["userName"] : ""; if (say == "" && (bool?)j["ok"] == false) say = (string)j["error"] != null && (bool?)st["sayErrors"] == true ? (string)j["error"] : "";
                    if (say != "" && (bool?)j["refund"] == true && ((string)j["code"] == "lookup" || (string)j["code"] == "offline")) say = SpotifyDownQuiet(disp, say, DateTime.UtcNow);
                    say = AtName(disp, say);
                    return "module " + cmd + " -> " + (int)r.StatusCode + (say != "" ? " | " + Say(SongSender.Role((string)cmd, (string)st["as"]), say, false) : "");
                }
            }
            catch (Exception ex) { return "module command failed: " + ex.Message; }
        }
    }
}
