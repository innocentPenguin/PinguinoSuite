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
            try
            {
                var doc = Doc(); var seeded = doc["seeded"] as JArray ?? new JArray();
                if (!seeded.Any(x => (string)x == "spotify-redeem"))
                {
                    var acts0 = (JArray)doc["actions"];
                    if (!acts0.OfType<JObject>().Any(x => (string)x["id"] == "spotify-redeem"))
                        acts0.Add(new JObject { { "id", "spotify-redeem" }, { "name", "Spotify: channel point song request" }, { "group", "Spotify" }, { "enabled", false }, { "importNotes", "preset: set the reward title, enable when the spotify module runs" },
                            { "triggers", new JArray { new JObject { { "type", "redeem" }, { "title", "Song Request" } } } }, { "conditions", new JArray() },
                            { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", "http://127.0.0.1:8771/api/chat-command" }, { "command", "sr" }, { "redeem", true }, { "as", "core" } } } } });
                    seeded.Add("spotify-redeem"); doc["seeded"] = seeded; Save(doc); doc = Doc(); seeded = doc["seeded"] as JArray ?? new JArray();
                }
                if (seeded.Any(x => (string)x == "spotify")) return;
                const string url = "http://127.0.0.1:8771/api/chat-command";
                Func<string, string, string[], string, int, int, JObject> mk = (id, cmd, names, perm, cd, ucd) => new JObject {
                    { "id", "spotify-" + id }, { "name", "Spotify: !" + names[0].TrimStart('!') }, { "group", "Spotify" }, { "enabled", false }, { "importNotes", "preset: enable when the spotify module runs" },
                    { "triggers", new JArray { new JObject { { "type", "command" }, { "names", new JArray(names) }, { "permission", perm }, { "cooldownSec", cd }, { "userCooldownSec", ucd }, { "consume", true } } } },
                    { "conditions", new JArray() }, { "steps", new JArray { new JObject { { "type", "module_command" }, { "url", url }, { "command", cmd }, { "as", "core" } } } } };
                var acts = (JArray)doc["actions"];
                foreach (var a in new[] {
                    mk("sr", "sr", new[] { "!sr", "!songrequest" }, "everyone", 0, 10), mk("skip", "skip", new[] { "!skip" }, "mod", 0, 0),
                    mk("song", "song", new[] { "!song", "!currentsong", "!np" }, "everyone", 8, 0), mk("queue", "queue", new[] { "!songqueue", "!srqueue" }, "everyone", 15, 0),
                    mk("oops", "oops", new[] { "!oops", "!wrongsong" }, "everyone", 0, 10), mk("block", "blocksong", new[] { "!blocksong" }, "mod", 0, 0), mk("clear", "srclear", new[] { "!srclear" }, "mod", 0, 0) })
                    if (!acts.OfType<JObject>().Any(x => (string)x["id"] == (string)a["id"])) acts.Add(a);
                seeded.Add("spotify"); doc["seeded"] = seeded; Save(doc);
            }
            catch (Exception ex) { Clog.Warn("automation", "seeding presets failed: " + ex.Message); }
        }
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
        public static bool OnChat(string display, string text, int role, bool isSub, bool first, string msgId, string replyTo)
        {
            bool consumed = false;
            string login = (display ?? "").ToLowerInvariant(); text = (text ?? "").Trim(); if (text == "") return false;
            bool firstToday = Roster.FirstToday(login);
            string cmd = text.StartsWith("!") ? text.Split(' ')[0] : ""; string rest = cmd != "" && text.Length > cmd.Length ? text.Substring(cmd.Length).Trim() : "";
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
                    var ctx = BaseCtx(login, display, text, role, isSub, msgId, replyTo); ctx["command"] = cmd; ctx["args"] = rest;
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
                case "TwitchCheer": kind = "cheer"; break; case "TwitchRaid": kind = "raid"; break; case "TwitchRaidOut": kind = "raid_out"; break; case "TwitchPoll": kind = "poll"; break; case "TwitchPrediction": kind = "prediction"; break; case "TwitchHype": kind = "hype"; break; case "TwitchBan": kind = "ban"; break; case "TwitchUnban": kind = "unban"; break; case "TwitchMod": kind = "mod"; break; case "TwitchUnmod": kind = "unmod"; break; case "TwitchRedeem": kind = "redeem"; break; case "StreamOnline": kind = "stream_online"; break; case "StreamOffline": kind = "stream_offline"; break; default: return; }
            var ctx = new Dictionary<string, string>(); foreach (var kv in args) ctx[kv.Key] = Convert.ToString(kv.Value, System.Globalization.CultureInfo.InvariantCulture) ?? "";
            string u = ctx.ContainsKey("userName") ? ctx["userName"] : ""; ctx["user"] = u; ctx["display"] = u; ctx["raider"] = u; ctx["channel"] = Channel(); ctx["event"] = kind;
            if (kind == "stream_online") { try { Program.ResetFirsts(); Session.Begin(); Roster.Reset(); } catch (Exception) { } }
            try { Latest.Record(kind, ctx); } catch (Exception ex) { Clog.Warn("latest", "could not record the event: " + ex.Message); }
            Fire(kind, ctx);
        }

        static void Fire(string kind, Dictionary<string, string> ctx)
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
                    if (kind == "redeem") { string title = (string)t["title"]; if (!string.IsNullOrEmpty(title) && title != "*" && !string.Equals(title, ctx.ContainsKey("title") ? ctx["title"] : "", StringComparison.OrdinalIgnoreCase)) continue; }
                    if (!CooldownOk(a, t, ctx.ContainsKey("userName") ? ctx["userName"] : "", 0)) continue;
                    Run(a, kind, new Dictionary<string, string>(ctx));
                }
        }
        public static void OnStream(bool online) { if (online) Program.ResetFirsts(); Fire(online ? "stream_online" : "stream_offline", new Dictionary<string, string> { { "channel", Channel() } }); }

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

        static void Run(JObject a, string why, Dictionary<string, string> ctx)
        {
            if (!Lease.MayRun || _paused) return;
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
                    case "delay": { int ms; if (!int.TryParse(x("ms"), out ms)) ms = 0; ms = Math.Max(0, Math.Min(600000, ms)); Thread.Sleep(test ? Math.Min(ms, 300) : ms); outp.Add("waited " + ms + " ms"); break; }
                    case "obs_scene": { string s = x("scene"); outp.Add(test ? "(dry run) would switch OBS scene to " + s : Obs(() => Program.ObsScene(s), "scene -> " + s)); break; }
                    case "obs_source": { string sc = x("scene"), so = x("source"), v = ((string)st["visible"] ?? "true").ToLowerInvariant(); outp.Add(test ? "(dry run) would set OBS source " + so + " to " + v : Obs(() => Program.ObsSource(sc, so, v), "source " + so + " -> " + v)); break; }
                    case "obs_request": { string rt = (string)st["request"] ?? ""; var data = st["data"] as JObject; var d2 = data == null ? new JObject() : JObject.Parse(Expand(data.ToString(), ctx)); outp.Add(test ? "(dry run) would send OBS request " + rt : Obs(() => Program.ObsRaw(rt, d2), "OBS " + rt)); break; }
                    case "sound": outp.Add(Sound(x("file"), (double?)st["volume"] ?? 1.0, test)); break;
                    case "http": outp.Add(test ? "(dry run) would call " + x("url") : Http(st, ctx, test)); break;
                    case "module_command": outp.Add(test ? "(dry run) would call module " + x("url") : ModuleCommand(st, ctx, test)); break;
                    case "bot_command": { string t = x("text"); if (!test) Task.Run(() => Program.Dispatch(Channel() == "" ? "streamer" : Channel(), t, "auto-" + Guid.NewGuid().ToString("N"), 4, "", false, null)); outp.Add((test ? "(test) would run " : "ran ") + "bot command: " + t); break; }
                    case "timeout": { string u = x("user"), why = x("reason"); int secs = (int?)st["seconds"] ?? 60; bool r = !test && Program.TimeoutUser(u, secs, why); outp.Add((test ? "(test) would time out " : r ? "timed out " : "could not time out ") + u + " " + secs + " s"); break; }
                    case "set_var": SetVar(x("name"), x("value"), (bool?)st["persist"] == true); outp.Add("var " + x("name") + " = " + x("value")); break;
                    case "inc_var": { double cur; double.TryParse(GetVar(x("name")), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out cur); double by = (double?)st["by"] ?? 1; cur += by; SetVar(x("name"), cur.ToString(System.Globalization.CultureInfo.InvariantCulture), (bool?)st["persist"] == true); ctx["count"] = cur.ToString(System.Globalization.CultureInfo.InvariantCulture); outp.Add("var " + x("name") + " = " + ctx["count"]); break; }
                    case "log": outp.Add("log: " + x("text")); Clog.Info("automation", x("text")); break;
                    case "if": { bool ok = Compare(x("left"), (string)st["op"], x("right")); Exec((ok ? st["then"] : st["else"]) as JArray, ctx, outp, ref budget, test, depth + 1); break; }
                    case "run_action": { var other = FindAction(x("name")); if (other == null) outp.Add("run_action: no action named " + x("name")); else { outp.Add("-> " + (string)other["name"]); Exec(other["steps"] as JArray, ctx, outp, ref budget, test, depth + 1); } break; }
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
        static string Obs(Func<bool> f, string what) { try { return f() ? "OBS " + what : "OBS not connected or refused: " + what; } catch (Exception ex) { return "OBS error: " + ex.Message; } }

        static string Sound(string file, double vol, bool test)
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
        static string ModuleCommand(JObject st, Dictionary<string, string> ctx, bool dry)
        {
            string url = Expand((string)st["url"], ctx); Uri u; if (!Uri.TryCreate(url, UriKind.Absolute, out u) || !UrlAllowed(u)) return "module command blocked: " + url;
            string cmd = (string)st["command"] ?? (ctx.ContainsKey("command") ? ctx["command"].TrimStart('!') : "");
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(8) })
                {
                    var body = new JObject { { "command", cmd }, { "args", ctx.ContainsKey("args") && ctx["args"] != "" ? ctx["args"] : ctx.ContainsKey("input") ? ctx["input"] : "" }, { "redeem", (bool?)st["redeem"] == true }, { "user", ctx.ContainsKey("userName") ? ctx["userName"] : "" }, { "display", ctx.ContainsKey("display") ? ctx["display"] : "" },
                        { "role", ctx.ContainsKey("role") ? ctx["role"] : "1" }, { "isMod", ctx.ContainsKey("isMod") && ctx["isMod"] == "true" }, { "isSub", ctx.ContainsKey("isSub") && ctx["isSub"] == "true" }, { "msgId", ctx.ContainsKey("msgId") ? ctx["msgId"] : "" } };
                    var rq = new HttpRequestMessage(HttpMethod.Post, u) { Content = new StringContent(body.ToString(), Encoding.UTF8, "application/json") };
                    string tok = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? ""; if (tok != "" && ((IPAddress.TryParse(u.Host, out var ip) && IPAddress.IsLoopback(ip)) || u.Host == "localhost")) rq.Headers.Add("Authorization", "Bearer " + tok);
                    var r = h.SendAsync(rq).Result; var j = JObject.Parse(r.Content.ReadAsStringAsync().Result);
                    string say = (string)j["say"] ?? ""; if (say == "" && (bool?)j["ok"] == false) say = (string)j["error"] != null && (bool?)st["sayErrors"] == true ? (string)j["error"] : "";
                    return "module " + cmd + " -> " + (int)r.StatusCode + (say != "" ? " | " + Say((string)st["as"] ?? "core", say, false) : "");
                }
            }
            catch (Exception ex) { return "module command failed: " + ex.Message; }
        }
    }
}
