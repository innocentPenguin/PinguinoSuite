using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The channel's own commands and lore (imported from Nightbot): clips, links, facts, people lines, jokes and counters. Data\runtime\channel_lore.json is the editable copy
    /// (seeded from PinguinoB0t\channel_lore_seed.json the first time). Exact !commands answer instantly; natural questions ("what pc does penguin have?") answer through the same entry, rate limited.
    /// Nothing here uses the language model, so it works with Chatty switched off. Mods: !lore list|on|off|count. Edit through GET/POST /api/lore.</summary>
    public static class ChannelLore
    {
        static readonly object L = new object();
        static JObject _doc; static DateTime _mtime = DateTime.MinValue;
        static readonly Dictionary<string, long> LastEntry = new Dictionary<string, long>(), LastUser = new Dictionary<string, long>(); static long LastGlobal;
        static readonly Random Rng = new Random();
        static string PathF { get { return System.IO.Path.Combine(HostApi.DataDir, "channel_lore.json"); } }
        static string SeedF { get { return System.IO.Path.Combine(Program.SuiteDir ?? "", "PinguinoB0t", "channel_lore_seed.json"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        // ---- the document ----
        static JObject Doc()
        {
            lock (L)
            {
                try
                {
                    if (!File.Exists(PathF) && File.Exists(SeedF)) { Directory.CreateDirectory(HostApi.DataDir); File.Copy(SeedF, PathF); }
                    if (File.Exists(PathF)) { var mt = File.GetLastWriteTimeUtc(PathF); if (_doc == null || mt != _mtime) { _doc = JObject.Parse(File.ReadAllText(PathF, Encoding.UTF8)); _mtime = mt; _idx = null; } }
                }
                catch (Exception ex) { Clog.Warn("lore", "channel_lore.json: " + ex.Message); }
                if (_doc == null) _doc = new JObject { { "version", 1 }, { "settings", new JObject() }, { "counters", new JObject() }, { "entries", new JArray() } };
                if (_doc["entries"] == null) _doc["entries"] = new JArray(); if (_doc["counters"] == null) _doc["counters"] = new JObject(); if (_doc["settings"] == null) _doc["settings"] = new JObject();
                return _doc;
            }
        }
        static void Save() { lock (L) { try { string tmp = PathF + ".tmp"; File.WriteAllText(tmp, _doc.ToString(), new UTF8Encoding(false)); if (File.Exists(PathF)) File.Delete(PathF); File.Move(tmp, PathF); _mtime = File.GetLastWriteTimeUtc(PathF); _idx = null; } catch (Exception ex) { Clog.Warn("lore", "could not save: " + ex.Message); } } }
        static JObject Set { get { return (JObject)Doc()["settings"]; } }
        static T S<T>(string k, T d) { try { var t = Set[k]; return t == null ? d : t.ToObject<T>(); } catch (Exception) { return d; } }
        static IEnumerable<JObject> Entries() { return ((JArray)Doc()["entries"]).OfType<JObject>(); }

        static Dictionary<string, JObject> _idx;
        static Dictionary<string, JObject> Index()
        {
            lock (L)
            {
                var d = Doc(); if (_idx != null) return _idx;
                _idx = new Dictionary<string, JObject>(StringComparer.OrdinalIgnoreCase);
                foreach (var e in Entries()) { if ((bool?)e["enabled"] == false) continue; foreach (var t in ((e["triggers"] as JArray) ?? new JArray()).Concat((e["aliases"] as JArray) ?? new JArray())) { string c = ((string)t ?? "").ToLowerInvariant(); if (c.StartsWith("!") && !_idx.ContainsKey(c)) _idx[c] = e; } }
                return _idx;
            }
        }
        public static bool IsCommand(string cmd) { return cmd == "!lore" || Index().ContainsKey(cmd); }

        // ---- rendering: the Nightbot variables ----
        static TimeZoneInfo Central()
        {
            foreach (var id in new[] { "Central Standard Time", "America/Chicago" }) { try { return TimeZoneInfo.FindSystemTimeZoneById(id); } catch (Exception) { } }
            return TimeZoneInfo.Utc;
        }
        static string Touser(string user, string[] args)
        {
            if (args != null && args.Length > 0 && args[0].Trim('@') != "") return "@" + args[0].TrimStart('@');
            try { var pool = ChatStats.ActiveLogins(10).Where(x => !string.Equals(x, user, StringComparison.OrdinalIgnoreCase) && !Boards.IsBot(x)).ToList(); if (pool.Count > 0) return "@" + pool[Rng.Next(pool.Count)]; } catch (Exception) { }
            return "@" + user;
        }
        public static string Render(JObject e, string user, string[] args)
        {
            var vs = (e["variants"] as JArray); string t = (vs != null && vs.Count > 0) ? (string)vs[Rng.Next(vs.Count)] : ((string)e["response"] ?? "");
            string touser = null;
            t = Regex.Replace(t, @"\$\((user|touser|channel|time[^)]*|random[^)]*|count[^)]*)\)", m =>
            {
                string v = m.Groups[1].Value;
                if (v == "user") return user;
                if (v == "touser") return touser ?? (touser = Touser(user, args));
                if (v == "channel") return S("channelName", "InnocentPenguin");
                if (v.StartsWith("time")) { var n = TimeZoneInfo.ConvertTime(DateTime.UtcNow, Central()); return (n.Hour % 12 == 0 ? 12 : n.Hour % 12) + ":" + n.Minute.ToString("D2") + " " + (n.Hour >= 12 ? "PM" : "AM"); }
                if (v.StartsWith("random")) { var p = v.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries); int a = 1, b = 100; if (p.Length > 2) { int.TryParse(p[1], out a); int.TryParse(p[2], out b); } if (b < a) b = a; return Rng.Next(a, b + 1).ToString(); }
                if (v.StartsWith("count")) { var p = v.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries); string name = p.Length > 1 ? p[1] : ((string)e["id"] ?? "count"); lock (L) { var c = (JObject)Doc()["counters"]; long n = ((long?)c[name] ?? 0) + 1; c[name] = n; Save(); return n.ToString("N0"); } }
                return m.Value;
            });
            return Links.Expand(t).Trim();
        }
        static string Full(JObject e, string user, string[] args)
        {
            string r = Render(e, user, args);
            foreach (var id in (e["also"] as JArray) ?? new JArray())
            {
                var o = Entries().FirstOrDefault(x => (string)x["id"] == ((string)id ?? "").TrimStart('!')); if (o == null || (bool?)o["enabled"] == false) continue;
                string more = Render(o, user, args); if (r.Length + more.Length + 3 <= 440) r += " | " + more;
            }
            return r;
        }

        // ---- exact commands ----
        public static void Handle(string user, string cmd, string[] args, bool mod, Action<string> say)
        {
            try
            {
                if (cmd == "!lore") { Admin(args, mod, say); return; }
                JObject e; if (!Index().TryGetValue(cmd, out e)) return;
                string key = (string)e["id"]; long now = Now(), cd = S("commandCooldownSec", 5);
                lock (L) { long last; if (LastEntry.TryGetValue("c|" + key, out last) && now - last < cd) return; LastEntry["c|" + key] = now; }
                say(Full(e, user, args));
            }
            catch (Exception ex) { Clog.Warn("lore", cmd + " failed: " + ex.Message); }
        }

        static void Admin(string[] args, bool mod, Action<string> say)
        {
            if (!mod) return; string sub = args.Length > 0 ? args[0].ToLowerInvariant() : "list";
            if (sub == "list") { int n = Entries().Count(), on = Entries().Count(x => (bool?)x["enabled"] != false), pub = Entries().Count(x => (bool?)x["publicSafe"] != false); say("Channel lore: " + n + " entries (" + on + " on, " + pub + " also answer questions). Edit them in the Suite or /api/lore. !lore off <id> | on <id> | count <name> <n>"); return; }
            if ((sub == "on" || sub == "off") && args.Length > 1)
            {
                lock (L) { var e = Entries().FirstOrDefault(x => string.Equals((string)x["id"], args[1].TrimStart('!'), StringComparison.OrdinalIgnoreCase)); if (e == null) { say("No lore entry " + args[1]); return; } e["enabled"] = sub == "on"; Save(); }
                say("Lore " + args[1].TrimStart('!') + " is " + sub); return;
            }
            if (sub == "count" && args.Length > 2) { long v; if (!long.TryParse(args[2], out v)) { say("Usage: !lore count <name> <number>"); return; } lock (L) { ((JObject)Doc()["counters"])[args[1]] = v; Save(); } say("Counter " + args[1] + " is now " + v.ToString("N0")); return; }
            say("!lore list | on <id> | off <id> | count <name> <number>");
        }

        // ---- natural questions and keyword replies ----
        static readonly Regex QShape = new Regex(@"(\?|^\s*(?:hey |yo |so |uh |um |wait |btw )?(?:what|whats|what's|which|when|where|who|whos|who's|how|is|are|does|do|did|can|could|will|why|anyone know|tell me|link)\b)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
        static readonly Dictionary<string, Regex> Rx = new Dictionary<string, Regex>();
        static Regex R(string p) { lock (Rx) { Regex r; if (!Rx.TryGetValue(p, out r)) { try { r = new Regex(p, RegexOptions.IgnoreCase | RegexOptions.Compiled, TimeSpan.FromMilliseconds(50)); } catch (Exception) { r = null; } Rx[p] = r; } return r; } }
        static bool Hit(Regex r, string t) { try { return r != null && r.IsMatch(t); } catch (RegexMatchTimeoutException) { return false; } }

        /// <summary>The entry a chat line is asking for, or null. Pure (no cooldowns): the tests call this.</summary>
        public static JObject Match(string text)
        {
            if (string.IsNullOrWhiteSpace(text) || text.Length > 220 || text.TrimStart().StartsWith("!")) return null;
            string t = Regex.Replace(text.Trim(), @"\s+", " ");
            if (S("bareWords", true)) { string bare = Regex.Replace(t, @"[\p{P}\s]+$", "").ToLowerInvariant(); foreach (var e in Entries()) if ((bool?)e["enabled"] != false && (string)e["bare"] == bare) return e; }
            if (!S("contextual", true)) return null;
            bool q = QShape.IsMatch(t);
            JObject best = null; int bp = -1;
            foreach (var e in Entries())
            {
                if ((bool?)e["enabled"] == false || (bool?)e["contextual"] != true || (bool?)e["publicSafe"] == false) continue;
                if ((bool?)e["anyShape"] != true && !q) continue;
                string not = (string)e["not"]; if (!string.IsNullOrEmpty(not) && Hit(R(not), t)) continue;
                int pr = (int?)e["priority"] ?? 3; if (pr <= bp) continue;
                foreach (var p in (e["patterns"] as JArray) ?? new JArray()) if (Hit(R((string)p), t)) { best = e; bp = pr; break; }
            }
            return best;
        }

        /// <summary>A chat line that is not a command: answers when it asks for one of the entries. Returns true when it answered (the bots then stay quiet).</summary>
        public static bool OnChat(string user, string text, int role, Action<string> say)
        {
            try
            {
                if (Boards.IsBot(user)) return false;
                var e = Match(text); if (e == null) return false;
                long now = Now(), ecd = S("entryCooldownSec", 90), gcd = S("globalCooldownSec", 20), ucd = S("userCooldownSec", 45); string key = "x|" + (string)e["id"], uk = "u|" + user.ToLowerInvariant();
                lock (L)
                {
                    long last;
                    if (now - LastGlobal < gcd) return false;
                    if (LastEntry.TryGetValue(key, out last) && now - last < ecd) return false;
                    if (LastUser.TryGetValue(uk, out last) && now - last < ucd) return false;
                    LastGlobal = now; LastEntry[key] = now; LastUser[uk] = now;
                }
                string r = Full(e, user, new string[0]); if (r == "") return false;
                bool bare = (string)e["bare"] != null; if (!bare && r.Length < 400) r = "@" + user + " " + r;
                say(r); return true;
            }
            catch (Exception ex) { Clog.Warn("lore", "chat match failed: " + ex.Message); return false; }
        }
        public static void Say(string s) { if (HostApi.SimMode) Console.WriteLine("[say] " + s); else { string via; HostApi.SendAs("core", s, out via); } }

        // ---- the website's /help: the public entries, grouped ----
        static string Group(string kind) { switch (kind) { case "info": return "Info"; case "link": return "Links"; case "clip": return "Clips"; case "person": return "People"; default: return "Fun"; } }
        public static JArray DocRows()
        {
            var rows = new JArray();
            foreach (var e in Entries())
            {
                if ((bool?)e["enabled"] == false || (bool?)e["publicSafe"] == false) continue;
                var trig = ((e["triggers"] as JArray) ?? new JArray()).Select(x => (string)x).ToList(); if (trig.Count == 0) continue;   // keyword replies are not commands
                string resp = ((string)e["response"] ?? ""); string desc = resp.Length > 110 ? resp.Substring(0, 107) + "..." : resp;
                if ((string)e["kind"] == "clip") desc = "A clip from the channel: " + resp.Replace("https://", "").Substring(0, Math.Min(resp.Replace("https://", "").Length, 60));
                rows.Add(new JObject { { "command", trig[0] }, { "aliases", e["aliases"] ?? new JArray() }, { "action", "ChannelLore" }, { "category", "Channel" }, { "group", Group((string)e["kind"]) }, { "who", "everyone" }, { "permission", "everyone" }, { "usage", trig[0] },
                    { "description", desc }, { "examples", new JArray(trig[0]) } });
            }
            return rows;
        }

        // ---- GET/POST /api/lore ----
        public static List<JObject> AllEntries() { return Entries().ToList(); }
        public static JObject Api() { var d = Doc(); return new JObject { { "ok", true }, { "settings", d["settings"] }, { "counters", d["counters"] }, { "entries", d["entries"] }, { "count", ((JArray)d["entries"]).Count } }; }
        public static JObject Post(JObject b)
        {
            string act = ((string)b["action"] ?? "").ToLowerInvariant();
            lock (L)
            {
                var d = Doc(); var arr = (JArray)d["entries"];
                if (act == "upsert" && b["entry"] is JObject)
                {
                    var ne = (JObject)b["entry"].DeepClone(); string id = ((string)ne["id"] ?? "").Trim().ToLowerInvariant(); if (id == "") return new JObject { { "ok", false }, { "error", "entry.id is required" } };
                    ne["id"] = id; if (ne["enabled"] == null) ne["enabled"] = true; if (ne["publicSafe"] == null) ne["publicSafe"] = true; if (ne["response"] == null) ne["response"] = "";
                    var old = arr.OfType<JObject>().FirstOrDefault(x => (string)x["id"] == id); if (old != null) old.Replace(ne); else arr.Add(ne);
                    Save(); return new JObject { { "ok", true }, { "id", id } };
                }
                if (act == "delete") { var old = arr.OfType<JObject>().FirstOrDefault(x => (string)x["id"] == (string)b["id"]); if (old == null) return new JObject { { "ok", false }, { "error", "no such entry" } }; old.Remove(); Save(); return new JObject { { "ok", true } }; }
                if (act == "settings" && b["settings"] is JObject) { foreach (var p in ((JObject)b["settings"]).Properties()) d["settings"][p.Name] = p.Value; Save(); return new JObject { { "ok", true } }; }
                if (act == "counter") { ((JObject)d["counters"])[(string)b["name"]] = (long?)b["value"] ?? 0; Save(); return new JObject { { "ok", true } }; }
                if (act == "test") { var e = Match((string)b["text"]); return new JObject { { "ok", true }, { "match", e == null ? null : e["id"] } }; }
            }
            return new JObject { { "ok", false }, { "error", "action: upsert | delete | settings | counter | test" } };
        }
    }
}
