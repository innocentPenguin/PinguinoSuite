using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>"This stream" numbers and goals, computed from the activity feed. The session starts when the stream goes online (session.json); until then everything since the Host started counts.
    /// Settings (all Ivan's): Data\runtime\session_settings.json { SessionLine, GoalLine, Goals:[{Id,Label,Kind: follow|sub|giftsub|bits|raidviewers|redeem, Target, Offset, Scope: session|all, Color, Visible}] }.
    /// Overlay: /overlay/goal?id=<goal id> (look from the goal; ?color=&amp;size=&amp;font= override). Commands: !session, !goal (presets). API: GET /api/session, GET /api/goals.</summary>
    public static class Session
    {
        static string StartPath { get { return Path.Combine(HostApi.DataDir, "session.json"); } }
        static long _start = -1; static readonly object L = new object();
        public static long Start { get { lock (L) { if (_start < 0) { try { _start = File.Exists(StartPath) ? (long)JObject.Parse(File.ReadAllText(StartPath))["start"] : 0; } catch (Exception) { _start = 0; } } return _start; } } }
        public static void Begin() { lock (L) { _start = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); try { File.WriteAllText(StartPath, new JObject { { "start", _start } }.ToString()); } catch (Exception) { } } }

        public static JObject Settings()
        {
            var d = new JObject {
                { "SessionLine", "This stream: {follows} follows, {subs} subs ({gifts} gifted), {bits} bits, {raids} raids ({raiders} viewers)" },
                { "GoalLine", "{label}: {current}/{target} ({pct}%)" },
                { "Goals", new JArray { new JObject { { "Id", "followers" }, { "Label", "Follower goal" }, { "Kind", "follow" }, { "Target", 50 }, { "Offset", 0 }, { "Scope", "session" }, { "Color", "ff9900" }, { "Visible", true } },
                                        new JObject { { "Id", "subs" }, { "Label", "Sub goal" }, { "Kind", "sub" }, { "Target", 10 }, { "Offset", 0 }, { "Scope", "session" }, { "Color", "9146ff" }, { "Visible", true } } } },
                { "Bar", new JObject { { "Width", 900 }, { "Height", 56 }, { "Font", "bahnschrift" }, { "TextColor", "ffffff" }, { "Background", "000000" }, { "Opacity", 0.55 }, { "Rounded", true } } } };
            try
            {
                var f = Path.Combine(HostApi.DataDir, "session_settings.json");
                if (File.Exists(f)) { foreach (var p in JObject.Parse(File.ReadAllText(f))) d[p.Key] = p.Value; }
                else File.WriteAllText(f, d.ToString());
            }
            catch (Exception) { }
            return d;
        }

        static IEnumerable<JObject> ItemsBetween(long from, long to)
        {
            var all = (JArray)Latest.Activity(0, 100000, null)["items"];
            return all.OfType<JObject>().Where(i => (long)i["ts"] >= from && (long)i["ts"] <= to);
        }
        static JObject CountsOf(List<JObject> it)
        {
            Func<string, int> n = t => it.Count(i => (string)i["type"] == t);
            Func<string, long> sum = t => it.Where(i => (string)i["type"] == t).Sum(i => (long?)i["amount"] ?? 0);
            return new JObject { { "follows", n("follow") }, { "subs", n("sub") + n("resub") }, { "gifts", sum("gift") }, { "bits", sum("cheer") }, { "raids", n("raid") }, { "raiders", sum("raid") }, { "redeems", n("redeem") }, { "bans", n("ban") }, { "clips", n("clip") + n("replay") }, { "shoutouts", n("shoutout") } };
        }
        /// <summary>the SessionLine for any time window (the recap uses the last stream's)</summary>
        public static string LineFor(long from, long to) { return Fill((string)Settings()["SessionLine"], CountsOf(ItemsBetween(from, to).ToList())); }

        static IEnumerable<JObject> Items(bool sessionOnly)
        {
            long s = Start; var all = (JArray)Latest.Activity(0, 100000, null)["items"];
            return all.OfType<JObject>().Where(i => !sessionOnly || (long)i["ts"] >= s);
        }
        public static JObject Counts(bool sessionOnly = true)
        {
            var it = Items(sessionOnly).ToList(); Func<string, int> n = t => it.Count(i => (string)i["type"] == t);
            Func<string, long> sum = t => it.Where(i => (string)i["type"] == t).Sum(i => (long?)i["amount"] ?? 0);
            return new JObject { { "follows", n("follow") }, { "subs", n("sub") + n("resub") }, { "gifts", sum("gift") }, { "bits", sum("cheer") }, { "raids", n("raid") }, { "raiders", sum("raid") }, { "redeems", n("redeem") }, { "bans", n("ban") }, { "clips", n("clip") + n("replay") }, { "shoutouts", n("shoutout") } };
        }
        static string Fill(string t, JObject c) { foreach (var p in c.Properties()) t = t.Replace("{" + p.Name + "}", p.Value.ToString()); return t; }
        public static string Line()
        {
            var c = Counts(true); return Fill((string)Settings()["SessionLine"], c);
        }
        public static JObject Api()
        {
            long s = Start; return new JObject { { "ok", true }, { "startedAt", s == 0 ? (JToken)null : s }, { "minutes", s == 0 ? (JToken)null : (int)((DateTimeOffset.UtcNow.ToUnixTimeSeconds() - s) / 60) }, { "counts", Counts(true) }, { "allTime", Counts(false) }, { "line", Line() } };
        }

        public static long Current(JObject g)
        {
            bool sessionOnly = ((string)g["Scope"] ?? "session") != "all"; var it = Items(sessionOnly).ToList(); string kind = ((string)g["Kind"] ?? "follow").ToLowerInvariant(); long v;
            switch (kind)
            {
                case "sub": v = it.Count(i => (string)i["type"] == "sub" || (string)i["type"] == "resub") + it.Where(i => (string)i["type"] == "gift").Sum(i => (long?)i["amount"] ?? 0); break;
                case "giftsub": v = it.Where(i => (string)i["type"] == "gift").Sum(i => (long?)i["amount"] ?? 0); break;
                case "bits": v = it.Where(i => (string)i["type"] == "cheer").Sum(i => (long?)i["amount"] ?? 0); break;
                case "raidviewers": v = it.Where(i => (string)i["type"] == "raid").Sum(i => (long?)i["amount"] ?? 0); break;
                case "redeem": v = it.Count(i => (string)i["type"] == "redeem"); break;
                default: v = it.Count(i => (string)i["type"] == "follow"); break;
            }
            return v + ((long?)g["Offset"] ?? 0);
        }
        public static JObject Goals()
        {
            var s = Settings(); var rows = new JArray();
            foreach (var g in (s["Goals"] as JArray ?? new JArray()).OfType<JObject>())
            {
                long cur = Current(g), target = Math.Max(1, (long?)g["Target"] ?? 1); int pct = (int)Math.Min(100, cur * 100 / target);
                rows.Add(new JObject { { "id", g["Id"] }, { "label", g["Label"] }, { "kind", g["Kind"] }, { "current", cur }, { "target", target }, { "pct", pct }, { "color", g["Color"] }, { "visible", (bool?)g["Visible"] != false },
                    { "line", Fill((string)s["GoalLine"], new JObject { { "label", g["Label"] }, { "current", cur }, { "target", target }, { "pct", pct } }) } });
            }
            return new JObject { { "ok", true }, { "goals", rows }, { "bar", s["Bar"] } };
        }
        public static string GoalLine(string id)
        {
            var gs = ((JArray)Goals()["goals"]).OfType<JObject>().Where(g => (bool)g["visible"]).ToList();
            if (!string.IsNullOrEmpty(id)) gs = gs.Where(g => string.Equals((string)g["id"], id, StringComparison.OrdinalIgnoreCase)).ToList();
            return gs.Count == 0 ? "No goal is set." : string.Join(" | ", gs.Select(g => (string)g["line"]));
        }
        public static string PagePath()
        {
            foreach (var d in new[] { Path.Combine(AppContext.BaseDirectory, "web"), Path.Combine(Program.SuiteDir ?? "", "PinguinoHost", "web") })
            { var f = Path.Combine(d, "goal.html"); if (File.Exists(f)) return f; }
            return null;
        }
    }

    /// <summary>Ivan's alert look: the OBS popup (scene, source, seconds) and one sound per alert kind. Data\runtime\alerts_settings.json.</summary>
    public static class AlertCfg
    {
        public static JObject Settings()
        {
            var f = Path.Combine(HostApi.DataDir, "alerts_settings.json"); bool fresh = !File.Exists(f); if (fresh) Sounds.EnsureDefaults();   // first run: write the tiny default chimes and use them
            var sounds = new JObject(); foreach (var k in Sounds.Kinds) sounds[k] = new JObject { { "File", fresh ? Sounds.DefaultFile(k) : "" }, { "Volume", 0.6 } };
            var welcome = new JObject { { "Enabled", true }, { "File", fresh ? Sounds.DefaultFile("welcome") : "" }, { "Volume", 0.6 }, { "OnlyWhileLive", true } };
            var d = new JObject { { "PopupScene", "Alerts" }, { "PopupSource", "Latest Group" }, { "PopupSeconds", 10 }, { "MuteSounds", false }, { "Sounds", sounds }, { "Welcome", welcome } };
            try
            {
                if (!fresh) { foreach (var p in JObject.Parse(File.ReadAllText(f))) { if ((p.Key == "Sounds" || p.Key == "Welcome") && p.Value is JObject so) foreach (var q in so) { if (p.Key == "Sounds" && q.Value is JObject qo) { foreach (var r in qo) d["Sounds"][q.Key][r.Key] = r.Value; } else d[p.Key][q.Key] = q.Value; } else d[p.Key] = p.Value; } }
                else File.WriteAllText(f, d.ToString());
            }
            catch (Exception) { }
            return d;
        }
        /// <summary>merges a partial settings object into alerts_settings.json (the caller has validated it)</summary>
        public static void Save(JObject patch)
        {
            lock (typeof(AlertCfg))
            {
                var cur = Settings();
                foreach (var p in patch) { if ((p.Key == "Sounds" || p.Key == "Welcome") && p.Value is JObject so) foreach (var q in so) { if (p.Key == "Sounds" && q.Value is JObject qo) { foreach (var r in qo) cur["Sounds"][q.Key][r.Key] = r.Value; } else cur[p.Key][q.Key] = q.Value; } else cur[p.Key] = p.Value; }
                File.WriteAllText(Path.Combine(HostApi.DataDir, "alerts_settings.json"), cur.ToString());
            }
        }
    }
}
