using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Full-screen overlay scenes: PinguinoB0t\overlays\scene.html (the "stage", one OBS browser source per profile) shows every overlay as a placeable widget (iframe).
    /// Data\runtime\scene_layouts.json: {"profiles":{"h":{"active":"default","layouts":{"default":{"widgets":[...],"updated":"iso"}}},"v":{...}}}. Profiles: h = 1920x1080, v = 1080x1920.
    /// Widget: {id, src?, x, y, w, h, scale, z, visible, opacity, takeover, params:{query string for the widget page}, style:{radius, rotate, brightness, saturate, hue, blur, shadow, bg}}.
    /// GET  /api/scene-layouts[?profile=h][&amp;layout=name][&amp;js=1]   the active (or named) layout of a profile + the layout names + the widget registry (js=1: window.SCENE_LAYOUT=...;)
    /// POST /api/scene-layouts {action:save|delete|activate|duplicate|rename, profile, name, layout?, from?, to?}   widgets validated and clamped, unknown keys dropped
    /// GET  /api/scene-widgets   the registry (what can be placed, design size, the style/param help)</summary>
    public static class Scenes
    {
        static readonly object L = new object();
        static string P { get { return Path.Combine(HostApi.DataDir, "scene_layouts.json"); } }
        public static readonly Dictionary<string, int[]> Profiles = new Dictionary<string, int[]> { { "h", new[] { 1920, 1080 } }, { "v", new[] { 1080, 1920 } } };

        class W { public string Id, Label, Src, Help; public int Dw, Dh; public bool Takeover; public Dictionary<string, int[]> Def; /* profile -> x,y,w,h,z,visible */ }
        static readonly W[] Registry = {
            new W { Id = "players", Label = "Players (teams)", Src = "players.html", Dw = 1920, Dh = 1080, Help = "Team cards of the running match. Full canvas, best in h.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 2, 1 } }, { "v", new[] { 0, 0, 1080, 608, 2, 0 } } } },
            new W { Id = "players_vertical", Label = "Players (vertical)", Src = "players_vertical.html", Dw = 1080, Dh = 1920, Help = "Vertical team cards. Full canvas, best in v.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 1320, 0, 600, 1080, 2, 0 } }, { "v", new[] { 0, 0, 1080, 1920, 2, 1 } } } },
            new W { Id = "queue", Label = "Queue / leaderboards", Src = "queue.html", Dw = 560, Dh = 720, Help = "Queue card, then the idle leaderboards.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 40, 560, 720, 3, 1 } }, { "v", new[] { 260, 1100, 560, 720, 3, 1 } } } },
            new W { Id = "subroll", Label = "Sub roll", Src = "subroll.html", Dw = 1920, Dh = 1080, Help = "Sub roll-call. Full canvas, only visible while a roll runs.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 4, 1 } }, { "v", new[] { 0, 656, 1080, 608, 4, 1 } } } },
            new W { Id = "wheel", Label = "Tournament wheel", Src = "wheel.html", Dw = 1920, Dh = 1080, Takeover = true, Help = "Wheel / team box. Takes over the scene while it has something to show.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 6, 1 } }, { "v", new[] { 0, 656, 1080, 608, 6, 1 } } } },
            new W { Id = "alerts", Label = "Alerts", Src = "alerts.html", Dw = 800, Dh = 600, Help = "The 800x600 alerts overlay (03). Audio: a browser source's sound goes through the scene source, so level/ducking is set on the scene source in OBS, not on the old alerts source.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 560, 240, 800, 600, 9, 1 } }, { "v", new[] { 140, 660, 800, 600, 9, 1 } } } },
        };
        static W Find(string id) { return Registry.FirstOrDefault(w => w.Id == id); }

        static JObject Load() { try { if (File.Exists(P)) return JObject.Parse(File.ReadAllText(P).TrimStart((char)0xFEFF)); } catch (Exception) { } return new JObject(); }
        static void Save(JObject all) { File.WriteAllText(P, all.ToString()); }
        static string Name(string n) { n = (n ?? "").Trim(); n = new string(n.Where(ch => char.IsLetterOrDigit(ch) || ch == '_' || ch == '-' || ch == ' ').ToArray()).Trim(); return n.Length > 40 ? n.Substring(0, 40) : n; }
        static JObject Err(string e) { return new JObject { { "ok", false }, { "error", e } }; }

        static JObject DefaultWidget(W w, string profile)
        {
            int[] d = w.Def[profile];
            return new JObject { { "id", w.Id }, { "x", d[0] }, { "y", d[1] }, { "w", d[2] }, { "h", d[3] }, { "scale", 1 }, { "z", d[4] }, { "visible", d[5] == 1 }, { "opacity", 1 }, { "takeover", w.Takeover }, { "params", new JObject() }, { "style", new JObject() } };
        }
        static JObject DefaultLayout(string profile) { return new JObject { { "widgets", new JArray(Registry.Select(w => DefaultWidget(w, profile))) }, { "updated", DateTime.UtcNow.ToString("o") } }; }

        static double Clamp(JToken t, double lo, double hi, double def) { double d; if (t == null || t.Type == JTokenType.Null || !double.TryParse(Convert.ToString(t, System.Globalization.CultureInfo.InvariantCulture), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out d) || double.IsNaN(d) || double.IsInfinity(d)) return def; return Math.Max(lo, Math.Min(hi, d)); }
        static bool Bool(JToken t, bool def) { if (t == null || t.Type == JTokenType.Null) return def; if (t.Type == JTokenType.Boolean) return (bool)t; var s = t.ToString().ToLowerInvariant(); return s == "1" || s == "true"; }
        static string Safe(string s, int max) { s = s ?? ""; var sb = new System.Text.StringBuilder(); foreach (char ch in s) if (char.IsLetterOrDigit(ch) || "-_.,:#%()/ ".IndexOf(ch) >= 0) sb.Append(ch); var r = sb.ToString(); return r.Length > max ? r.Substring(0, max) : r; }

        /// <summary>One widget, validated; null when the id is unknown.</summary>
        static JObject CleanWidget(JToken t, string profile)
        {
            var o = t as JObject; if (o == null) return null; string id = ((string)o["id"] ?? "").Trim().ToLowerInvariant();
            var reg = Find(id); var def = reg != null ? DefaultWidget(reg, profile) : null; string src = null;
            if (reg == null)
            {   // a custom widget: id custom-xxx, src is another overlay page of the overlay folder (relative .html) - nothing external
                if (!id.StartsWith("custom-") || id.Length > 40 || id.Any(ch => !(char.IsLetterOrDigit(ch) || ch == '-' || ch == '_'))) return null;
                src = ((string)o["src"] ?? "").Trim(); if (!src.EndsWith(".html", StringComparison.OrdinalIgnoreCase) || src.Contains("..") || src.Contains("/") || src.Contains("\\") || src.Contains(":")) return null;
                def = new JObject { { "x", 0 }, { "y", 0 }, { "w", 400 }, { "h", 300 }, { "z", 5 } };
            }
            var r = new JObject { { "id", id } }; if (src != null) r["src"] = src;
            r["x"] = Clamp(o["x"], -8000, 8000, (double)def["x"]); r["y"] = Clamp(o["y"], -8000, 8000, (double)def["y"]);
            r["w"] = Clamp(o["w"], 20, 8000, (double)def["w"]); r["h"] = Clamp(o["h"], 20, 8000, (double)def["h"]);
            r["scale"] = Clamp(o["scale"], 0.1, 8, 1); r["z"] = (int)Clamp(o["z"], 0, 100, (double)def["z"]);
            r["visible"] = Bool(o["visible"], reg != null ? (bool)def["visible"] : true); r["opacity"] = Clamp(o["opacity"], 0, 1, 1);
            r["takeover"] = Bool(o["takeover"], reg != null && reg.Takeover);
            var pr = new JObject(); var pi = o["params"] as JObject; if (pi != null) foreach (var p in pi.Properties().Take(30)) { string k = Safe(p.Name, 30).Replace(" ", ""); if (k == "") continue; pr[k] = Safe(p.Value.ToString(), 80); }
            r["params"] = pr;
            var st = new JObject(); var si = o["style"] as JObject;
            if (si != null)
            {
                if (si["radius"] != null) st["radius"] = Clamp(si["radius"], 0, 400, 0);
                if (si["rotate"] != null) st["rotate"] = Clamp(si["rotate"], -360, 360, 0);
                if (si["brightness"] != null) st["brightness"] = Clamp(si["brightness"], 0, 3, 1);
                if (si["saturate"] != null) st["saturate"] = Clamp(si["saturate"], 0, 3, 1);
                if (si["hue"] != null) st["hue"] = Clamp(si["hue"], -360, 360, 0);
                if (si["blur"] != null) st["blur"] = Clamp(si["blur"], 0, 40, 0);
                if (si["shadow"] != null) st["shadow"] = Bool(si["shadow"], false);
                string bg = Safe((string)si["bg"], 30); if (bg != "") st["bg"] = bg;   // a css colour (#rrggbb, rgba(...), name)
            }
            r["style"] = st; return r;
        }
        static JObject CleanLayout(JToken lay, string profile)
        {
            var arr = (lay as JObject)?["widgets"] as JArray; if (arr == null) return null;
            var seen = new HashSet<string>(); var ws = new JArray();
            foreach (var t in arr) { var w = CleanWidget(t, profile); if (w == null || !seen.Add((string)w["id"])) continue; ws.Add(w); if (ws.Count >= 40) break; }
            // registry widgets that the editor did not send keep their defaults, so a layout is always complete
            foreach (var reg in Registry) if (!seen.Contains(reg.Id)) ws.Add(DefaultWidget(reg, profile));
            return new JObject { { "widgets", ws }, { "updated", DateTime.UtcNow.ToString("o") } };
        }

        static JObject Prof(JObject all, string profile)
        {
            var ps = all["profiles"] as JObject; if (ps == null) { ps = new JObject(); all["profiles"] = ps; }
            var p = ps[profile] as JObject;
            if (p == null || !(p["layouts"] is JObject) || ((JObject)p["layouts"]).Count == 0)
            { p = new JObject { { "active", "default" }, { "layouts", new JObject { { "default", DefaultLayout(profile) } } } }; ps[profile] = p; }
            if (((JObject)p["layouts"])[(string)p["active"] ?? ""] == null) p["active"] = ((JObject)p["layouts"]).Properties().First().Name;
            return p;
        }

        public static JObject Widgets()
        {
            return new JObject { { "ok", true }, { "profiles", new JObject { { "h", new JArray(1920, 1080) }, { "v", new JArray(1080, 1920) } } },
                { "widgets", new JArray(Registry.Select(w => new JObject { { "id", w.Id }, { "label", w.Label }, { "src", w.Src }, { "designW", w.Dw }, { "designH", w.Dh }, { "takeover", w.Takeover }, { "available", File.Exists(Path.Combine(OverlayFiles.Root ?? "", w.Src)) }, { "help", w.Help } })) },
                { "style", new JArray("radius (px)", "rotate (deg)", "brightness (0-3)", "saturate (0-3)", "hue (deg)", "blur (px)", "shadow (bool)", "bg (css colour)") },
                { "params", "free query-string pairs passed to the widget page, e.g. {\"layout\":\"sprinkled\",\"scale\":\"1.2\"} (same names the standalone page takes)" } };
        }

        public static JObject Get(string profile, string layout)
        {
            profile = (profile ?? "h").ToLowerInvariant(); if (!Profiles.ContainsKey(profile)) return Err("profile must be h or v");
            lock (L)
            {
                var all = Load(); var p = Prof(all, profile);
                string name = Name(layout); var ls = (JObject)p["layouts"]; if (name == "" || ls[name] == null) name = (string)p["active"];
                var lay = (JObject)ls[name];
                return new JObject { { "ok", true }, { "profile", profile }, { "width", Profiles[profile][0] }, { "height", Profiles[profile][1] }, { "active", (string)p["active"] }, { "name", name },
                    { "names", new JArray(ls.Properties().Select(x => x.Name)) }, { "layout", lay }, { "registry", Widgets()["widgets"] } };
            }
        }

        public static JObject Set(JObject b)
        {
            string action = ((string)b?["action"] ?? "save").ToLowerInvariant(), profile = ((string)b?["profile"] ?? "").ToLowerInvariant();
            if (!Profiles.ContainsKey(profile)) return Err("profile must be h or v");
            lock (L)
            {
                var all = Load(); var p = Prof(all, profile); var ls = (JObject)p["layouts"]; string name = Name((string)b["name"]);
                switch (action)
                {
                    case "save":
                        { if (name == "") return Err("name is required"); var lay = CleanLayout(b["layout"], profile); if (lay == null) return Err("layout.widgets must be an array"); if (ls[name] == null && ls.Count >= 30) return Err("at most 30 layouts per profile"); ls[name] = lay; if (b["activate"] != null && Bool(b["activate"], false)) p["active"] = name; break; }
                    case "activate":
                        { if (ls[name] == null) return Err("no such layout"); p["active"] = name; break; }
                    case "delete":
                        { if (ls[name] == null) return Err("no such layout"); if (ls.Count <= 1) return Err("cannot delete the last layout"); ls.Remove(name); if ((string)p["active"] == name) p["active"] = ls.Properties().First().Name; break; }
                    case "duplicate":
                        { string from = Name((string)b["from"]); if (ls[from] == null) return Err("no such layout to copy"); if (name == "") return Err("name is required"); if (ls[name] != null) return Err("name already used"); var cp = (JObject)ls[from].DeepClone(); cp["updated"] = DateTime.UtcNow.ToString("o"); ls[name] = cp; break; }
                    case "rename":
                        { string to = Name((string)b["to"]); if (ls[name] == null) return Err("no such layout"); if (to == "") return Err("to is required"); if (ls[to] != null) return Err("name already used"); var cp = ls[name]; ls.Remove(name); ls[to] = cp; if ((string)p["active"] == name) p["active"] = to; name = to; break; }
                    default: return Err("action must be save, activate, delete, duplicate or rename");
                }
                try { Save(all); } catch (Exception e) { return Err("could not save: " + e.Message); }
                return Get(profile, name);
            }
        }
    }
}
