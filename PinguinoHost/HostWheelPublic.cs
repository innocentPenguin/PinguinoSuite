using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Adapter for the tournament wheel overlay (PinguinoB0t\overlays\wheel.html, the exact original site overlay): turns Core's wheel_public.json
    /// (one spin = one pick) into the shape that overlay was written for: draw.steps = picks so far, manual {revealed,total,last,spunAt,spinMs}, pool (who can still be
    /// picked, the pick being spun included), teams (only finished ones), teamSizes, names. The join/leave feed fields (signedUp, feed, feedMs, showSignedUp) ride along.</summary>
    public static class WheelPublic
    {
        /// <summary>how the spin ends, set in the Suite (Tune > Tournament wheel): tail 0..100 (how long and slow the last part of the spin is), nearMiss (the pointer lands close to a slice edge). File Data/runtime/wheel_look.json.</summary>
        static string LookP { get { return System.IO.Path.Combine(HostApi.DataDir, "runtime", "wheel_look.json"); } }
        public static JObject Look()
        {
            JObject j = null; try { if (System.IO.File.Exists(LookP)) j = JObject.Parse(System.IO.File.ReadAllText(LookP)); } catch (Exception) { }
            j = j ?? new JObject(); double tail = j["spinTail"] == null ? 50 : Math.Max(0, Math.Min(100, (double)j["spinTail"]));
            return new JObject { { "spinTail", tail }, { "nearMiss", (bool?)j["nearMiss"] ?? true } };
        }
        public static void SetLook(string key, JToken v)
        {
            var j = Look(); j[key] = v; System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(LookP)); System.IO.File.WriteAllText(LookP, j.ToString(), new System.Text.UTF8Encoding(false));
        }
        public static JObject Adapt(JObject j)
        {
            string st = (string)j["status"] ?? "none";
            var picks = j["picks"] as JArray ?? new JArray(); var queue = (j["queue"] as JArray ?? new JArray()).Select(x => (string)x).ToList();
            var spin = j["spin"] as JObject; long now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();   // the file can be older than the last spin: judge "still spinning" by the clock
            int size = Math.Max(1, (int?)j["teamSize"] ?? 2); bool fin = (bool?)j["final"] == true;
            long spunAt = spin == null ? 0 : (long?)spin["at"] ?? 0, spinMs = spin == null ? 8000 : (long?)spin["ms"] ?? 8000;
            var landing = spin == null ? new List<string>() : (spin["landing"] as JArray ?? new JArray()).Select(x => (string)x).ToList();
            bool pending = spunAt > 0 && now < spunAt + spinMs;
            var placed = new HashSet<string>(picks.Select(p => (string)p["name"])); if (!pending) queue = queue.Where(q => !placed.Contains(q)).ToList();
            int R = picks.Count, unplaced = queue.Count - (pending ? queue.Count(q => landing.Contains(q)) : 0), total = fin ? R : R + Math.Max(0, unplaced);
            var steps = new JArray(picks.Select(p => new JObject { { "name", p["name"] }, { "team", p["team"] } }));
            var sizes = new JObject(); var teams = new JArray();
            foreach (var t in j["teams"] as JArray ?? new JArray())
            {
                int n = (int)t["n"]; var mem = t["members"] as JArray ?? new JArray(); bool partial = (bool?)t["partial"] == true;
                sizes[n.ToString()] = fin ? mem.Count : size;
                if (fin || mem.Count >= size) teams.Add(new JObject { { "n", n }, { "members", mem }, { "partial", partial } });
            }
            var names = new List<string>(); foreach (var p in picks) names.Add((string)p["name"]); foreach (var q in queue) if (!names.Contains(q)) names.Add(q);
            var o = new JObject
            {
                { "status", R > 0 ? (fin ? "drawn" : "drawing") : st == "final" ? "closed" : st },
                { "mode", j["mode"] }, { "teamSize", size }, { "names", new JArray(names) }, { "entrantCount", names.Count },
                { "pool", new JArray(queue.OrderBy(x => x, StringComparer.CurrentCultureIgnoreCase)) },
                { "teams", teams }, { "teamSizes", sizes }, { "waitlist", fin ? j["waitlist"] ?? new JArray() : new JArray() },
                { "manual", new JObject { { "on", true }, { "revealed", R }, { "total", total }, { "last", fin }, { "spunAt", spunAt }, { "spinMs", spinMs }, { "tail", Look()["spinTail"] }, { "nearMiss", Look()["nearMiss"] } } },
                { "practice", j["practice"] ?? false }, { "label", (string)j["mode"] == "balanced" ? "Rigged / Balanced by MMR" : "True random" },
                { "serverNow", now }, { "botOnline", true },
                { "signedUp", j["signedUp"] ?? 0 }, { "feed", j["feed"] ?? new JArray() }, { "feedMs", j["feedMs"] ?? 2000 }, { "showSignedUp", j["showSignedUp"] ?? true }
            };
            o["draw"] = R > 0 ? new JObject { { "id", ((string)j["id"] ?? "w") + ":" + ((int?)j["round"] ?? 0) }, { "startedAt", 0 }, { "stepMs", 0 }, { "steps", steps } } : null;
            return o;
        }
    }
}
