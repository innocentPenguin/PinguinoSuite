using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The subscriber roll-call overlay (PinguinoB0t\overlays\subroll.html, an OBS browser source) and the "our T3 / T2 subs" cards of the queue overlay.
    /// GET /api/subroll[?mode=&amp;js=1]  every current subscriber, sorted by mode: alpha, watch, length, tier, gifted, newest, oldest, random, tiergroups (T3 / T2 / T1 groups).
    /// GET /api/subroll/state[?js=1]  {running, mode, style, nonce}: the overlay plays a roll whenever the nonce changes. POST /api/subroll/start {mode?, style?} and /stop (token like the other POSTs); chat: mods type "!subs roll [mode] [style]" / "!subs roll stop".
    /// Config Data\runtime\subroll.json (written with these defaults when missing): mode, style (roll | pages | spotlight), speed (px per second), perPage, secondsPerPage, secondsPerItem, size, title, thankYou, showMonths, loop, tierColors.
    /// Source: the subscriber master list (Data\subs\subscribers_master.json, not lapsed) plus anyone Twitch's live list (live_subs.json) knows that the master does not yet. Bots and !optmeout viewers are left out, nothing private is read.
    /// Nothing is ever said in chat by this module except the one short confirmation of the mod command.</summary>
    public static class SubRoll
    {
        static readonly object L = new object();
        static List<JObject> _list; static DateTime _at = DateTime.MinValue;
        static JObject _state = new JObject { { "running", false }, { "mode", "tier" }, { "style", "roll" }, { "nonce", 0 } };
        static string CfgP { get { return Path.Combine(HostApi.DataDir, "subroll.json"); } }
        static string Root { get { return Boards.RootDir; } }
        public static readonly string[] Modes = { "alpha", "watch", "length", "tier", "gifted", "newest", "oldest", "random", "tiergroups" };
        public static readonly string[] Styles = { "roll", "pages", "spotlight" };

        public static JObject DefaultConfig()
        {
            return new JObject { { "mode", "tier" }, { "style", "roll" }, { "speed", 70 }, { "perPage", 10 }, { "secondsPerPage", 8 }, { "secondsPerItem", 3 }, { "size", 1.0 }, { "title", "OUR SUBSCRIBERS" },
                { "thankYou", "Thank you {name}" }, { "showMonths", true }, { "loop", false },
                { "tierColors", new JObject { { "t1", "#f5f2eb" }, { "t2", "#ffb347" }, { "t3", "#ff6a00" } } } };
        }
        public static JObject Config()
        {
            var def = DefaultConfig();
            try
            {
                if (!File.Exists(CfgP)) { File.WriteAllText(CfgP, def.ToString()); return def; }
                var j = JObject.Parse(File.ReadAllText(CfgP).TrimStart((char)0xFEFF));
                foreach (var p in def.Properties()) if (j[p.Name] == null) j[p.Name] = p.Value;
                return j;
            }
            catch (Exception) { return def; }
        }
        static JObject Read(string rel) { try { string p = Path.Combine(Root, rel); return File.Exists(p) ? SubsImport.ParseJ(File.ReadAllText(p).TrimStart((char)0xFEFF)) : new JObject(); } catch (Exception) { return new JObject(); } }

        /// <summary>every current subscriber (cached 60 s): login, name, tier 1-3, tenure (months), streak, type, founder, subscribed, watch (minutes, all time), gifts (all time)</summary>
        public static List<JObject> Active()
        {
            lock (L)
            {
                if (_list != null && (DateTime.UtcNow - _at).TotalSeconds < 60) return _list;
                var users = (Read(Path.Combine("subs", "subscribers_master.json"))["users"] as JObject) ?? new JObject();
                var live = (Read(Path.Combine("subs", "live_subs.json"))["users"] as JObject) ?? new JObject();
                var map = new Dictionary<string, JObject>();
                foreach (var p in users.Properties())
                {
                    var u = p.Value as JObject; if (u == null || (bool?)u["lapsed"] == true) continue;
                    map[p.Name.ToLowerInvariant()] = new JObject { { "tier", (int?)u["tier"] ?? 1 }, { "tenure", (int?)u["tenure"] ?? 0 }, { "streak", (int?)u["streak"] ?? 0 }, { "type", (string)u["subType"] ?? "" }, { "founder", (bool?)u["founder"] ?? false }, { "subscribed", (string)u["subscribed"] ?? "" } };
                }
                foreach (var p in live.Properties())
                {
                    string lg = p.Name.ToLowerInvariant(); var u = p.Value as JObject; if (u == null || map.ContainsKey(lg)) continue;
                    map[lg] = new JObject { { "tier", Math.Max(1, (int?)u["tier"] ?? 1) }, { "tenure", 0 }, { "streak", 0 }, { "type", (bool?)u["prime"] == true ? "prime" : (bool?)u["isGift"] == true ? "gift" : "recurring" }, { "founder", false }, { "subscribed", "" } };
                }
                string ch = (Boards.Channel() ?? "").ToLowerInvariant();
                var list = new List<JObject>();
                foreach (var kv in map)
                {
                    string lg = kv.Key; if (lg == ch || Boards.IsBot(lg) || Boards.IsAnon(lg)) continue;
                    var o = kv.Value; o["login"] = lg; o["name"] = Boards.DisplayName(lg);
                    o["watch"] = (long)Math.Round(Periods.Value(lg, "watchtime", "all")); o["gifts"] = (long)Math.Round(Periods.Value(lg, "gifts", "all"));
                    list.Add(o);
                }
                _list = list; _at = DateTime.UtcNow; return list;
            }
        }
        static int I(JObject o, string k) { return (int?)o[k] ?? 0; }
        static long Lg(JObject o, string k) { return (long?)o[k] ?? 0; }
        static string Name(JObject o) { return ((string)o["name"] ?? "").ToLowerInvariant(); }
        public static List<JObject> Sorted(string mode)
        {
            var l = Active().ToList();
            switch (mode)
            {
                case "alpha": return l.OrderBy(Name, StringComparer.Ordinal).ToList();
                case "watch": return l.OrderByDescending(o => Lg(o, "watch")).ThenBy(Name, StringComparer.Ordinal).ToList();
                case "length": return l.OrderByDescending(o => I(o, "tenure")).ThenByDescending(o => I(o, "streak")).ThenByDescending(o => Lg(o, "watch")).ThenBy(Name, StringComparer.Ordinal).ToList();
                case "gifted": return l.OrderByDescending(o => Lg(o, "gifts")).ThenByDescending(o => Lg(o, "watch")).ThenBy(Name, StringComparer.Ordinal).ToList();
                case "newest": return l.OrderByDescending(o => (string)o["subscribed"] ?? "", StringComparer.Ordinal).ThenBy(Name, StringComparer.Ordinal).ToList();
                case "oldest": return l.Where(o => ((string)o["subscribed"] ?? "") != "").OrderBy(o => (string)o["subscribed"], StringComparer.Ordinal).Concat(l.Where(o => ((string)o["subscribed"] ?? "") == "").OrderBy(Name, StringComparer.Ordinal)).ToList();
                case "random": { var r = new Random(); return l.OrderBy(o => r.Next()).ToList(); }
                default: return l.OrderByDescending(o => I(o, "tier")).ThenByDescending(o => I(o, "tenure")).ThenByDescending(o => Lg(o, "watch")).ThenBy(Name, StringComparer.Ordinal).ToList();   // "tier" and "tiergroups"
            }
        }
        public static JObject Api(string mode)
        {
            mode = (mode ?? "").ToLowerInvariant(); var cfg = Config(); if (!Modes.Contains(mode)) mode = (string)cfg["mode"]; if (!Modes.Contains(mode)) mode = "tier";
            var list = Sorted(mode); var res = new JObject { { "ok", true }, { "mode", mode }, { "total", list.Count }, { "config", cfg }, { "subs", new JArray(list) } };
            if (mode == "tiergroups") res["groups"] = new JArray(new[] { 3, 2, 1 }.Select(t => new JObject { { "tier", t }, { "label", "TIER " + t }, { "subs", new JArray(list.Where(o => I(o, "tier") == t)) } }).Where(g => ((JArray)g["subs"]).Count > 0));
            return res;
        }
        /// <summary>ranked card for the queue overlay: our tier-N subs by months (watch time is the tiebreak and the second column); null when nobody is on that tier</summary>
        public static JObject TierCard(int tier, int top)
        {
            var rows = Active().Where(o => I(o, "tier") == tier).OrderByDescending(o => I(o, "tenure")).ThenByDescending(o => Lg(o, "watch")).ThenBy(Name, StringComparer.Ordinal).Take(top).ToList();
            if (rows.Count == 0) return null;
            int rank = 0;
            return new JObject { { "id", "tier" + tier + "|all" }, { "metric", "tier" + tier }, { "period", "all" }, { "title", "OUR TIER " + tier + " SUBS · BY MONTHS" }, { "unit", "months" },
                { "rows", new JArray(rows.Select(o => new JObject { { "rank", ++rank }, { "name", o["name"] }, { "value", o["tenure"] }, { "extra", o["watch"] } })) } };
        }

        public static JObject State() { lock (L) return (JObject)_state.DeepClone(); }
        public static JObject Start(JObject b)
        {
            var cfg = Config(); string mode = ((string)b?["mode"] ?? "").ToLowerInvariant(), style = ((string)b?["style"] ?? "").ToLowerInvariant();
            if (mode == "") mode = (string)cfg["mode"]; if (style == "") style = (string)cfg["style"];
            if (!Modes.Contains(mode)) return new JObject { { "ok", false }, { "error", "mode must be one of " + string.Join(", ", Modes) } };
            if (!Styles.Contains(style)) return new JObject { { "ok", false }, { "error", "style must be one of " + string.Join(", ", Styles) } };
            lock (L) { _state = new JObject { { "ok", true }, { "running", true }, { "mode", mode }, { "style", style }, { "nonce", ((int?)_state["nonce"] ?? 0) + 1 } }; return (JObject)_state.DeepClone(); }
        }
        public static JObject Stop() { lock (L) { _state["running"] = false; _state["nonce"] = ((int?)_state["nonce"] ?? 0) + 1; return (JObject)_state.DeepClone(); } }
        /// <summary>mods: "!subs roll [mode] [style]" or "!subs roll stop"; returns the one short line to say (a confirmation, never the list)</summary>
        public static string Chat(string[] a)
        {
            if (a.Length > 0 && a[0].ToLowerInvariant() == "stop") { Stop(); return "Sub roll stopped."; }
            var b = new JObject();
            foreach (var w in a.Select(x => x.ToLowerInvariant())) { if (Modes.Contains(w)) b["mode"] = w; else if (Styles.Contains(w)) b["style"] = w; }
            var r = Start(b); if (r["ok"] != null && !(bool)r["ok"]) return (string)r["error"];
            return "Sub roll started: " + (string)r["mode"] + ", " + (string)r["style"] + ". (modes: " + string.Join("/", Modes) + "; styles: " + string.Join("/", Styles) + ")";
        }
    }
}
