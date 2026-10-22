using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Fit options of every OBS overlay (PinguinoB0t\overlays\overlay-options.js reads them). Data\runtime\overlay_options.json:
    /// {"*": {...options for every overlay...}, "queue": {...}, "players": {...}}  (the key is the overlay file name without .html; a name's own options win over "*").
    /// GET /api/overlay-options[?name=queue][&amp;js=1]  the saved options (js=1: window.OVERLAY_OPTIONS=...; so a file:// overlay can load it).
    /// POST /api/overlay-options {"name":"queue","options":{"scale":1.2,"anchor":"tr"}}  merges (a null value removes an option, "options":null clears the overlay). Only known keys, values clamped.
    /// Options: scale (0.2-4) | anchor (tl,tc,tr,cl,c,cr,bl,bc,br: the corner/edge the scaling grows from) | pad (px safe margin, moved away from the anchored edges) | x, y (px nudge)
    ///          | maxw, maxh (px: the picture is scaled down until it fits) | fit (1: scaled down until it fits inside the safe area) | overflow (hidden|visible)</summary>
    public static class OverlayOptions
    {
        static readonly object L = new object();
        static string P { get { return Path.Combine(HostApi.DataDir, "overlay_options.json"); } }
        public static readonly string[] Anchors = { "tl", "tc", "tr", "cl", "c", "cr", "bl", "bc", "br" };

        static JObject Load()
        {
            try { if (File.Exists(P)) { var j = JObject.Parse(File.ReadAllText(P).TrimStart((char)0xFEFF)); return j; } } catch (Exception) { }
            return new JObject();
        }
        public static JObject Get(string name)
        {
            lock (L)
            {
                var all = Load();
                if (string.IsNullOrEmpty(name)) return new JObject { { "ok", true }, { "options", all } };
                var o = new JObject(); foreach (var k in new[] { "*", Clean(name) }) { var s = all[k] as JObject; if (s != null) foreach (var p in s.Properties()) o[p.Name] = p.Value; }
                return new JObject { { "ok", true }, { "name", Clean(name) }, { "options", o } };
            }
        }
        static string Clean(string n) { n = (n ?? "").Trim().ToLowerInvariant(); return n == "*" ? "*" : new string(n.Where(ch => char.IsLetterOrDigit(ch) || ch == '_' || ch == '-').ToArray()); }
        static double? Num(JToken t, double lo, double hi) { double d; if (t == null || t.Type == JTokenType.Null || !double.TryParse(Convert.ToString(t, System.Globalization.CultureInfo.InvariantCulture), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out d) || double.IsNaN(d) || double.IsInfinity(d)) return null; return Math.Max(lo, Math.Min(hi, d)); }
        public static JObject Set(JObject b)
        {
            string name = Clean((string)b?["name"]); if (name == "") return new JObject { { "ok", false }, { "error", "name is required (the overlay file name without .html, or *)" } };
            lock (L)
            {
                var all = Load();
                if (b["options"] == null || b["options"].Type == JTokenType.Null) { all.Remove(name); }
                else
                {
                    var inp = b["options"] as JObject; if (inp == null) return new JObject { { "ok", false }, { "error", "options must be an object" } };
                    var cur = (all[name] as JObject) ?? new JObject();
                    foreach (var p in inp.Properties())
                    {
                        string k = p.Name; JToken v = p.Value;
                        if (v == null || v.Type == JTokenType.Null) { cur.Remove(k); continue; }
                        switch (k)
                        {
                            case "scale": { var d = Num(v, 0.2, 4); if (d == null) return Bad(k); cur[k] = d; break; }
                            case "pad": { var d = Num(v, 0, 600); if (d == null) return Bad(k); cur[k] = d; break; }
                            case "x": case "y": { var d = Num(v, -4000, 4000); if (d == null) return Bad(k); cur[k] = d; break; }
                            case "maxw": case "maxh": { var d = Num(v, 50, 8000); if (d == null) return Bad(k); cur[k] = d; break; }
                            case "fit": cur[k] = (v.ToString() == "1" || v.ToString().ToLowerInvariant() == "true") ? 1 : 0; break;
                            case "anchor": { string a = v.ToString().ToLowerInvariant(); if (!Anchors.Contains(a)) return Bad(k + " (one of " + string.Join(", ", Anchors) + ")"); cur[k] = a; break; }
                            case "preset": { string a = v.ToString().ToLowerInvariant(); if (a != "safe" && a != "tv" && a != "fit-safe") return Bad(k + " (safe, tv or fit-safe)"); cur[k] = a; break; }
                            case "overflow": { string a = v.ToString().ToLowerInvariant(); if (a != "hidden" && a != "visible") return Bad(k + " (hidden or visible)"); cur[k] = a; break; }
                            default: return Bad(k + " (unknown option)");
                        }
                    }
                    if (cur.Count == 0) all.Remove(name); else all[name] = cur;
                }
                try { File.WriteAllText(P, all.ToString()); } catch (Exception e) { return new JObject { { "ok", false }, { "error", "could not save: " + e.Message } }; }
                return Get(name);
            }
        }
        /// <summary>What the Suite needs to draw the sliders page: every option with type, range, step, default and a one-line help. GET /api/overlay-options/schema</summary>
        public static JObject Schema()
        {
            Func<string, string, double, double, double, double, string, JObject> num = (k, label, lo, hi, step, def, help) => new JObject { { "key", k }, { "label", label }, { "type", "number" }, { "min", lo }, { "max", hi }, { "step", step }, { "default", def }, { "help", help } };
            Func<string, string, string[], string, string, JObject> en = (k, label, vals, def, help) => new JObject { { "key", k }, { "label", label }, { "type", "enum" }, { "values", new JArray(vals) }, { "default", def }, { "help", help } };
            return new JObject { { "ok", true }, { "overlays", new JArray("queue", "players", "players_vertical", "wheel", "subroll") }, { "global", "*" },
                { "options", new JArray {
                    num("scale", "Size", 0.2, 4, 0.05, 1, "Size of the whole overlay (1 = as designed)"),
                    en("anchor", "Anchor", Anchors, "tl", "The point of the source the overlay grows/shrinks from"),
                    num("pad", "Safe margin (px)", 0, 600, 5, 0, "Moves the picture away from the anchored edge(s)"),
                    num("x", "Nudge right (px)", -4000, 4000, 5, 0, "Negative = left"), num("y", "Nudge down (px)", -4000, 4000, 5, 0, "Negative = up"),
                    num("maxw", "Max width (px)", 50, 8000, 10, 0, "0/empty = no limit; scaled down until it fits"), num("maxh", "Max height (px)", 50, 8000, 10, 0, "0/empty = no limit"),
                    new JObject { { "key", "fit" }, { "label", "Fit inside safe area" }, { "type", "bool" }, { "default", 0 }, { "help", "Scale down until everything fits inside the source minus the margin" } },
                    en("overflow", "Overflow", new[] { "hidden", "visible" }, "hidden", "Crop or show anything outside the source"),
                    en("preset", "Safe-area preset", new[] { "safe", "tv", "fit-safe" }, "", "safe = 5% margin, tv = 10% margin, fit-safe = 5% + fit (explicit margin/fit win)") } },
                { "api", new JObject { { "get", "GET /api/overlay-options[?name=queue]" }, { "set", "POST /api/overlay-options {name, options:{key:value|null}}" }, { "clearOverlay", "POST /api/overlay-options {name, options:null}" } } },
                { "preview", "Open <overlay>.html?preview=1&guides=1 to see the red source box, green safe area, blue overlay box" } };
        }
        /// <summary>Pre-stream check: every overlay page in the overlay folder carries the overlay-options.js tag (backups and *_backup pages are left out). GET /api/overlay-options/health</summary>
        public static JObject Health()
        {
            string root = OverlayFiles.Root; var pages = new JArray(); var missing = new JArray(); bool js = false;
            if (!string.IsNullOrEmpty(root) && Directory.Exists(root))
            {
                js = File.Exists(Path.Combine(root, "overlay-options.js"));
                foreach (var f in Directory.GetFiles(root, "*.html", SearchOption.TopDirectoryOnly).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
                {
                    string n = Path.GetFileNameWithoutExtension(f); if (n.ToLowerInvariant().Contains("backup") || n.ToLowerInvariant().Contains("bak")) continue;
                    bool has; try { has = File.ReadAllText(f).Contains("overlay-options.js"); } catch (Exception) { has = false; }
                    pages.Add(new JObject { { "page", n }, { "hasOptions", has } }); if (!has) missing.Add(n);
                }
            }
            return new JObject { { "ok", js && missing.Count == 0 }, { "scriptPresent", js }, { "folder", root ?? "" }, { "pages", pages }, { "missing", missing } };
        }
        static JObject Bad(string what) { return new JObject { { "ok", false }, { "error", "bad value for " + what } }; }
    }
}
