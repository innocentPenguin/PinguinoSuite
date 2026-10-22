using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The subscriber roll-call overlay (PinguinoB0t\overlays\subroll.html, an OBS browser source) and the "our T3 / T2 subs" cards of the queue overlay.
    /// GET /api/subroll[?mode=&amp;js=1]  every current subscriber, sorted by mode: alpha, watch, length, tier, gifted, newest, oldest, random, tiergroups (T3 / T2 / T1 groups).
    /// GET /api/subroll/state[?js=1]  {running, mode, style, nonce}: the overlay plays a roll whenever the nonce changes. POST /api/subroll/start {mode?, style?} and /stop (token like the other POSTs); chat: mods type "!subs roll [mode] [style] [layout]" / "!subs roll stop".
    /// Config Data\runtime\subroll.json (written with these defaults when missing): mode, style (roll | pages | spotlight), speed (px per second), perPage, secondsPerPage, secondsPerItem, size, title, thankYou, showMonths, loop, tierColors.
    /// Source: the subscriber master list (Data\subs\subscribers_master.json, not lapsed) plus anyone Twitch's live list (live_subs.json) knows that the master does not yet. Bots and !optmeout viewers are left out, nothing private is read.
    /// Nothing is ever said in chat by this module except the one short confirmation of the mod command.</summary>
    public static class SubRoll
    {
        static readonly object L = new object();
        static List<JObject> _list; static DateTime _at = DateTime.MinValue;
        static JObject _state = new JObject { { "running", false }, { "mode", "tier" }, { "style", "roll" }, { "layout", "flat" }, { "nonce", 0 } };
        static string CfgP { get { return Path.Combine(HostApi.DataDir, "subroll.json"); } }
        static string Root { get { return Boards.RootDir; } }
        public static readonly string[] Modes = { "alpha", "watch", "length", "tier", "gifted", "newest", "oldest", "random", "tiergroups" };
        public static readonly string[] Styles = { "roll", "pages", "spotlight" };
        public static readonly string[] Layouts = { "flat", "separated", "sprinkled" };   // how T2/T3 sit in the list: flat = one sort, separated = T1 block then T2 block then T3 block, sprinkled = T2+T3 spread evenly through the T1 list

        public static JObject DefaultConfig()
        {
            return new JObject { { "mode", "tier" }, { "style", "roll" }, { "layout", "flat" }, { "speed", 70 }, { "perPage", 10 }, { "secondsPerPage", 8 }, { "secondsPerItem", 3 }, { "size", 1.0 }, { "title", "OUR SUBSCRIBERS" },
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

        /// <summary>one viewer's sub facts for the profile: {months (total months subscribed), streak (current consecutive months), tier 1-3, active (subscribed right now)}. Zeros when never subscribed.</summary>
        public static JObject ViewOf(string login)
        {
            login = (login ?? "").Trim().TrimStart('@').ToLowerInvariant(); int months = 0, streak = 0, tier = 0; bool active = false;
            try
            {
                var users = (Read(Path.Combine("subs", "subscribers_master.json"))["users"] as JObject) ?? new JObject();
                var u = users[login] as JObject; if (u != null) { months = (int?)u["tenure"] ?? 0; streak = (int?)u["streak"] ?? 0; tier = Math.Max(1, Math.Min(3, (int?)u["tier"] ?? 1)); active = (bool?)u["lapsed"] != true; }
                var a = Active().FirstOrDefault(x => (string)x["login"] == login);
                if (a != null) { active = true; months = Math.Max(months, (int?)a["tenure"] ?? 0); streak = Math.Max(streak, (int?)a["streak"] ?? 0); tier = Math.Max(1, Math.Min(3, (int?)a["tier"] ?? 1)); }
                else if (u != null) { var live = (Read(Path.Combine("subs", "live_subs.json"))["users"] as JObject); if (live != null && live.Count > 0) active = live[login] != null; }
            }
            catch (Exception) { }
            return new JObject { { "months", months }, { "streak", streak }, { "tier", tier }, { "active", active } };
        }

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
        /// <summary>The "Subs!" card of the queue overlay: ONE list, Tier 1 first (paid or Prime, NOT gifted subs), then Tier 2, then Tier 3; inside a tier by months subscribed, watch time as the tiebreak (and the second column).
        /// Gifted subs: left out of Tier 1 (almost everybody there is a gift, that list would be the whole community); kept in Tier 2 and 3 (someone on a higher tier is rare and worth a thank-you however they got it).
        /// Both are options of the card in queue_idle.json: giftedT1 (default false), giftedT23 (default true). null when there is nobody.</summary>
        /// <summary>T2/T3 members spread evenly through the T1 list (the base order is kept).</summary>
        public static List<JObject> Sprinkle(List<JObject> baseList, List<JObject> specials)
        {
            int n = baseList.Count + specials.Count, k = specials.Count; var slots = new JObject[n];
            for (int j = 0; j < k; j++) slots[(int)Math.Min(n - 1, Math.Floor((j + 0.5) * n / k))] = specials[j];
            int bi = 0; for (int i = 0; i < n; i++) if (slots[i] == null) slots[i] = baseList[bi++];
            return slots.ToList();
        }
        /// <summary>Sub anniversary this week: the subscribe date (month/day) comes round within the next 6 days or was yesterday/today, and at least one year has passed. Returns the years, or 0.</summary>
        public static int Anniversary(string subscribed, DateTime today)
        {
            DateTime d; if (string.IsNullOrEmpty(subscribed) || !DateTime.TryParse(subscribed, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out d)) return 0;
            int years = today.Year - d.Year; if (years < 1) return 0;
            for (int dy = -1; dy <= 1; dy++)
            {
                int m = d.Month, day = d.Day; int y = today.Year + dy; if (m == 2 && day == 29 && !DateTime.IsLeapYear(y)) day = 28;
                var ann = new DateTime(y, m, day); double diff = (ann.Date - today.Date).TotalDays;
                if (diff >= -1 && diff <= 6) { int yrs = y - d.Year; return yrs >= 1 ? yrs : 0; }
            }
            return 0;
        }
        /// <summary>"NEW SUBS" idle card: current subscribers (gifted ones too, they are new faces) who subscribed within the last `days` days, newest first; value = days ago. null when nobody.</summary>
        public static JObject NewSubsCard(int top, int days)
        {
            var now = DateTime.UtcNow; var rows = new JArray(); int rank = 0;
            var list = Active().Select(o => new { o, d = ParseDate((string)o["subscribed"]) }).Where(x => x.d.HasValue && (now - x.d.Value).TotalDays <= days && (now - x.d.Value).TotalDays > -1)
                .OrderByDescending(x => x.d.Value).ThenBy(x => Name(x.o), StringComparer.Ordinal).Take(top);
            foreach (var x in list) rows.Add(new JObject { { "rank", ++rank }, { "name", x.o["name"] }, { "value", Math.Max(0, (int)Math.Floor((now - x.d.Value).TotalDays)) } });
            if (rows.Count == 0) return null;
            return new JObject { { "id", "newsubs|all" }, { "metric", "newsubs" }, { "period", "all" }, { "title", "NEW SUBS · LAST " + days + " DAYS" }, { "unit", "d ago" }, { "rows", rows } };
        }
        static DateTime? ParseDate(string s)
        {
            DateTime d; if (string.IsNullOrEmpty(s) || !DateTime.TryParse(s, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out d)) return null; return d;
        }
        public static JObject SubsCard(int top, bool giftedT1, bool giftedT23, string layout = "separated")
        {
            layout = layout == "sprinkled" ? "sprinkled" : "separated";
            var secs = new Dictionary<int, List<JObject>>(); var tiers = new List<int>();
            foreach (int t in new[] { 1, 2, 3 })
            {
                var sec = Active().Where(o => I(o, "tier") == t && ((string)o["type"] != "gift" || (t == 1 ? giftedT1 : giftedT23)))
                    .OrderByDescending(o => I(o, "tenure")).ThenByDescending(o => Lg(o, "watch")).ThenBy(Name, StringComparer.Ordinal).ToList();
                secs[t] = sec; if (sec.Count > 0) tiers.Add(t);
            }
            List<JObject> all;
            if (layout == "sprinkled") all = Sprinkle(secs[1], secs[3].Concat(secs[2]).ToList());
            else all = secs[1].Concat(secs[2]).Concat(secs[3]).ToList();
            var rows = new JArray(); int rank = 0; var today = DateTime.UtcNow;
            foreach (var o in all)
            {
                if (rank >= top) break; var row = new JObject { { "rank", ++rank }, { "tier", o["tier"] }, { "name", o["name"] }, { "value", o["tenure"] }, { "extra", o["watch"] } };
                int yrs = Anniversary((string)o["subscribed"], today); if (yrs > 0) row["anniv"] = yrs;   // "sub anniversary this week": the overlay highlights the row
                rows.Add(row);
            }
            if (rows.Count == 0) return null;
            return new JObject { { "id", "subs|all" }, { "metric", "subs" }, { "period", "all" }, { "title", "Subs! · by months" }, { "unit", "months" }, { "kind", "subs" }, { "layout", layout }, { "tiers", new JArray(tiers) }, { "rows", rows } };
        }

        public static JObject State() { lock (L) return (JObject)_state.DeepClone(); }
        public static JObject Start(JObject b)
        {
            var cfg = Config(); string mode = ((string)b?["mode"] ?? "").ToLowerInvariant(), style = ((string)b?["style"] ?? "").ToLowerInvariant(), layout = ((string)b?["layout"] ?? "").ToLowerInvariant();
            if (mode == "") mode = (string)cfg["mode"]; if (style == "") style = (string)cfg["style"]; if (layout == "") layout = (string)cfg["layout"] ?? "flat";
            if (!Layouts.Contains(layout)) return new JObject { { "ok", false }, { "error", "layout must be one of " + string.Join(", ", Layouts) } };
            if (!Modes.Contains(mode)) return new JObject { { "ok", false }, { "error", "mode must be one of " + string.Join(", ", Modes) } };
            if (!Styles.Contains(style)) return new JObject { { "ok", false }, { "error", "style must be one of " + string.Join(", ", Styles) } };
            lock (L) { _state = new JObject { { "ok", true }, { "running", true }, { "mode", mode }, { "style", style }, { "layout", layout }, { "nonce", ((int?)_state["nonce"] ?? 0) + 1 } }; return (JObject)_state.DeepClone(); }
        }
        public static JObject Stop() { lock (L) { _state["running"] = false; _state["nonce"] = ((int?)_state["nonce"] ?? 0) + 1; return (JObject)_state.DeepClone(); } }
        /// <summary>mods: "!subs roll [mode] [style]" or "!subs roll stop"; returns the one short line to say (a confirmation, never the list)</summary>
        public static string Chat(string[] a)
        {
            if (a.Length > 0 && a[0].ToLowerInvariant() == "stop") { Stop(); return "Sub roll stopped."; }
            var b = new JObject();
            foreach (var w in a.Select(x => x.ToLowerInvariant())) { if (Modes.Contains(w)) b["mode"] = w; else if (Styles.Contains(w)) b["style"] = w; else if (Layouts.Contains(w)) b["layout"] = w; }
            var r = Start(b); if (r["ok"] != null && !(bool)r["ok"]) return (string)r["error"];
            return "Sub roll started: " + (string)r["mode"] + ", " + (string)r["style"] + ", " + (string)r["layout"] + ". (modes: " + string.Join("/", Modes) + "; styles: " + string.Join("/", Styles) + "; layouts: " + string.Join("/", Layouts) + ")";
        }
    }
}
