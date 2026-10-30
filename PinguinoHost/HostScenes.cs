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

        class W { public string Id, Label, Src, Help; public int Dw, Dh; public bool Takeover, Pinned, Host; public Dictionary<string, int[]> Def; /* profile -> x,y,w,h,z,visible */ }
        static readonly W[] Registry = {
            new W { Id = "players", Label = "Players (teams)", Src = "players.html", Dw = 1920, Dh = 1080, Help = "Team cards of the running match. Full canvas, best in h.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 2, 1 } }, { "v", new[] { 0, 0, 1080, 608, 2, 0 } } } },
            new W { Id = "players_vertical", Label = "Players (vertical)", Src = "players_vertical.html", Dw = 1080, Dh = 250, Help = "Vertical-scene team strip (the page is a 1080x250 strip sized from its height; a full-height box would blow it up into pillars). Default: bottom of the v stage.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 1320, 900, 600, 139, 2, 0 } }, { "v", new[] { 0, 1670, 1080, 250, 2, 1 } } } },
            new W { Id = "queue", Label = "Queue / leaderboards", Src = "queue.html", Dw = 560, Dh = 720, Help = "Queue card, then the idle leaderboards.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 40, 560, 720, 3, 1 } }, { "v", new[] { 260, 1100, 560, 720, 3, 1 } } } },
            new W { Id = "subroll", Label = "Sub roll", Src = "subroll.html", Dw = 1920, Dh = 1080, Help = "Sub roll-call. Full canvas, only visible while a roll runs.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 4, 1 } }, { "v", new[] { 0, 656, 1080, 608, 4, 1 } } } },
            new W { Id = "wheel", Label = "Tournament wheel", Src = "wheel.html", Dw = 1920, Dh = 1080, Takeover = true, Help = "Wheel / team box. Takes over the scene while it has something to show.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 6, 1 } }, { "v", new[] { 0, 656, 1080, 608, 6, 1 } } } },
            new W { Id = "alerts", Label = "Alerts", Src = "http://127.0.0.1:8766/obs/alerts", Dw = 800, Dh = 600, Pinned = true, Help = "The 800x600 alerts overlay (PinguinoMulti, port 8766; it only draws while an alert plays). OFF by default (alerts stay a standalone source that moves per game); when switched on it is always on top (z 100). Its sound plays inside the scene source, so keep audio on for the scene source in OBS, and REMOVE the standalone alerts source while it is framed here or every alert plays twice.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 560, 240, 800, 600, 100, 0 } }, { "v", new[] { 140, 660, 800, 600, 100, 0 } } } },
            // ---- HUD widgets (phase 3): all OFF by default, switch on in the editor ----
            new W { Id = "goal", Label = "Goal bar", Src = "overlay/goal", Host = true, Dw = 900, Dh = 80, Help = "Follower / sub goal bar (Host page /overlay/goal). params: id=followers (the goal id), color, size, font.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 510, 960, 900, 80, 8, 0 } }, { "v", new[] { 90, 1780, 900, 80, 8, 0 } } } },
            new W { Id = "latest", Label = "Latest follower / sub / cheer / raid", Src = "overlay/latest", Host = true, Dw = 600, Dh = 300, Help = "Newest follower, sub, cheer and raid (Host page /overlay/latest).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 1300, 40, 600, 300, 8, 0 } }, { "v", new[] { 240, 60, 600, 300, 8, 0 } } } },
            new W { Id = "subfooter", Label = "Sub footer", Src = "overlay/subfooter", Host = true, Dw = 1920, Dh = 120, Help = "Scrolling sub names strip (Host page /overlay/subfooter).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 960, 1920, 120, 8, 0 } }, { "v", new[] { 0, 1800, 1080, 120, 8, 0 } } } },
            new W { Id = "chat", Label = "Chat feed", Src = "chat.html", Dw = 460, Dh = 520, Help = "Last chat messages (Host /api/chat/recent). params: max=8 (messages shown), fade=0 (seconds before a line fades, 0 = never).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 780, 460, 260, 8, 0 } }, { "v", new[] { 40, 1240, 460, 520, 8, 0 } } } },
            new W { Id = "pm", Label = "PM name", Src = "pm.html", Dw = 420, Dh = 56, Help = "Small \"name: pengXXX\" line for under the Rocket League scoreboard (Host /api/customs/state key pmName). Hidden while no name is set or customs are not running.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 750, 96, 420, 56, 8, 1 } }, { "v", new[] { 330, 150, 420, 56, 8, 1 } } } },
            new W { Id = "customs", Label = "Customs HUD", Src = "customs.html", Dw = 420, Dh = 160, Help = "Customs status: queue open/closed, how many are waiting, mode/format, activity (Host /api/customs/state).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 780, 420, 160, 8, 0 } }, { "v", new[] { 330, 1000, 420, 160, 8, 0 } } } },
            new W { Id = "pushup", Label = "Pushup counter", Src = "pushup.html", Dw = 420, Dh = 80, Help = "Pushup counter (Host /api/pushup, polled every 2 s). Hidden unless the counter is on (!pushup on / off); independent of customs.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 1290, 160, 420, 80, 8, 0 } }, { "v", new[] { 330, 230, 420, 80, 8, 0 } } } },
            new W { Id = "creatorcode", Label = "Creator code banner", Src = "creatorcode.html", Dw = 860, Dh = 340, Help = "Looping PengRL creator-code banner (transparent muted webm, creatorcode.html). OFF by default. Default: bottom right, clear of the scoreboard.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 1040, 620, 860, 340, 8, 0 } }, { "v", new[] { 110, 740, 860, 340, 8, 0 } } } },
            new W { Id = "ranked", Label = "Ranked win/loss", Src = "ranked.html", Dw = 520, Dh = 150, Help = "Ranked session tracker: a row of W/L slots, the net and the \"Game N in progress\" line (Host /api/ranked, polled). Shows only while the Ranked activity runs (!activity ranked / !ranked start, ends with !ranked stop) and shows Break during a break. Runs alongside customs; ending customs does not hide it.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 750, 160, 520, 150, 8, 1 } }, { "v", new[] { 280, 404, 520, 150, 8, 1 } } } },
            new W { Id = "nowplaying", Label = "Now playing", Src = "http://127.0.0.1:8771/overlay", Dw = 640, Dh = 200, Help = "The Spotify module's own now-playing overlay (port 8771, themes via its settings; ?next=0 hides up-next). Blank when the module is not running.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 860, 640, 200, 8, 0 } }, { "v", new[] { 220, 1700, 640, 200, 8, 0 } } } },
            // ---- sub-part widgets (?part= modes of the standalone pages): all OFF by default ----
            new W { Id = "wheel_only", Label = "Wheel only", Src = "wheel.html?part=wheel", Dw = 1080, Dh = 1080, Takeover = true, Help = "Just the wheel and its title (wheel.html?part=wheel), full width, no camera zone. Takes over the scene while it has something to show.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1080, 1080, 6, 0 } }, { "v", new[] { 0, 300, 1080, 1080, 6, 0 } } } },
            new W { Id = "wheel_teams", Label = "Wheel team box", Src = "wheel.html?part=teams", Dw = 700, Dh = 700, Takeover = true, Help = "Just the team box of the wheel: pick text, teams as they fill (wheel.html?part=teams). Takes over the scene while it has something to show.",
                Def = new Dictionary<string, int[]> { { "h", new[] { 1200, 300, 700, 700, 6, 0 } }, { "v", new[] { 190, 1300, 700, 600, 6, 0 } } } },
            new W { Id = "players_teams", Label = "Players: team cards only", Src = "players.html?part=teams", Dw = 1920, Dh = 1080, Help = "The team cards of the running match without the MATCH READY header (players.html?part=teams).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 2, 0 } }, { "v", new[] { 0, 0, 1080, 608, 2, 0 } } } },
            new W { Id = "players_header", Label = "Players: header only", Src = "players.html?part=header", Dw = 1920, Dh = 1080, Help = "Only the MATCH READY title block of the players page (players.html?part=header).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 0, 0, 1920, 1080, 2, 0 } }, { "v", new[] { 0, 0, 1080, 608, 2, 0 } } } },
            new W { Id = "queue_list", Label = "Queue list only", Src = "queue.html?part=list", Dw = 560, Dh = 720, Help = "The queue card only, never the idle leaderboards (queue.html?part=list).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 40, 560, 720, 3, 0 } }, { "v", new[] { 260, 1100, 560, 720, 3, 0 } } } },
            new W { Id = "queue_idle", Label = "Leaderboards only", Src = "queue.html?part=idle", Dw = 560, Dh = 720, Help = "The idle leaderboards / subs cards only, never the queue card (queue.html?part=idle).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 40, 560, 720, 3, 0 } }, { "v", new[] { 260, 1100, 560, 720, 3, 0 } } } },
            new W { Id = "customs_status", Label = "Customs: status only", Src = "customs.html?part=status", Dw = 420, Dh = 160, Help = "Customs card with just the title and QUEUE OPEN/CLOSED (customs.html?part=status).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 780, 420, 160, 8, 0 } }, { "v", new[] { 330, 1000, 420, 160, 8, 0 } } } },
            new W { Id = "customs_info", Label = "Customs: details only", Src = "customs.html?part=info", Dw = 420, Dh = 160, Help = "Customs card with just the title and the waiting / mode / format line (customs.html?part=info).",
                Def = new Dictionary<string, int[]> { { "h", new[] { 40, 780, 420, 160, 8, 0 } }, { "v", new[] { 330, 1000, 420, 160, 8, 0 } } } },
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
            r["scale"] = Clamp(o["scale"], 0.1, 8, 1); r["z"] = reg != null && reg.Pinned ? 100 : (int)Clamp(o["z"], 0, 99, (double)def["z"]);   // alerts are pinned on top, nothing else may reach 100
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
        public static readonly string[] Games = { "Just Chatting", "Rocket League", "Fortnite", "Other" };   // suggestions for the editor; any text up to 40 chars is accepted
        static string Game(string g) { g = Safe(g, 40).Trim(); return g; }
        static JObject CleanLayout(JToken lay, string profile)
        {
            var arr = (lay as JObject)?["widgets"] as JArray; if (arr == null) return null;
            var seen = new HashSet<string>(); var ws = new JArray();
            foreach (var t in arr) { var w = CleanWidget(t, profile); if (w == null || !seen.Add((string)w["id"])) continue; ws.Add(w); if (ws.Count >= 40) break; }
            // registry widgets that the editor did not send keep their defaults, so a layout is always complete
            foreach (var reg in Registry) if (!seen.Contains(reg.Id)) ws.Add(DefaultWidget(reg, profile));
            var res = new JObject { { "widgets", ws }, { "updated", DateTime.UtcNow.ToString("o") } };
            string g = Game((string)(lay as JObject)?["game"]); if (g != "") res["game"] = g;
            return res;
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
                { "widgets", new JArray(Registry.Select(w => new JObject { { "id", w.Id }, { "label", w.Label }, { "src", w.Src }, { "designW", w.Dw }, { "designH", w.Dh }, { "takeover", w.Takeover }, { "available", w.Host || w.Src.StartsWith("http") || File.Exists(Path.Combine(OverlayFiles.Root ?? "", w.Src.Split('?')[0])) }, { "pinned", w.Pinned }, { "help", w.Help } })) },
                { "style", new JArray("radius (px)", "rotate (deg)", "brightness (0-3)", "saturate (0-3)", "hue (deg)", "blur (px)", "shadow (bool)", "bg (css colour)") },
                { "params", "free query-string pairs passed to the widget page, e.g. {\"layout\":\"sprinkled\",\"scale\":\"1.2\"} (same names the standalone page takes)" } };
        }

        /// <summary>Pre-stream check of what the stage would show: per profile the served layout has at least one visible widget, and every visible widget that lives on another local port (alerts 8766, now playing 8771)
        /// has something listening there. A missing layout file is fine (defaults are generated). Used by the prestream list and GET-able via Health().</summary>
        public static JObject Health()
        {
            var problems = new JArray(); var profs = new JObject();
            foreach (var pr in Profiles.Keys)
            {
                var r = Get(pr, null); if ((bool?)r["ok"] != true) { problems.Add(pr + ": layout unreadable"); continue; }
                var ws = (r["layout"]?["widgets"] as JArray ?? new JArray()).OfType<JObject>().Where(w => (bool?)w["visible"] != false).ToList();
                profs[pr] = new JObject { { "layout", r["name"] }, { "visible", ws.Count } };
                if (ws.Count == 0) problems.Add(pr + ": layout '" + (string)r["name"] + "' has no visible widget (the scene would be empty)");
                foreach (var w in ws)
                {
                    var reg = Find((string)w["id"]); string src = (string)w["src"] ?? reg?.Src ?? "";
                    Uri u; if (!src.StartsWith("http", StringComparison.OrdinalIgnoreCase) || !Uri.TryCreate(src, UriKind.Absolute, out u) || u.Port == HostPort()) continue;
                    bool up = false; try { using (var tc = new System.Net.Sockets.TcpClient()) up = tc.ConnectAsync(u.Host, u.Port).Wait(600); } catch (Exception) { }
                    if (!up) problems.Add(pr + ": widget '" + (string)w["id"] + "' is on, but nothing listens on port " + u.Port);
                }
            }
            return new JObject { { "ok", problems.Count == 0 }, { "problems", problems }, { "profiles", profs } };
        }
        static int HostPort() { try { return HostApi.Port; } catch (Exception) { return 8770; } }

        /// <summary>the current game both profiles are on ("" = none set); read by GameWatch</summary>
        public static string CurrentGame()
        {
            lock (L) { var ps = Load()["profiles"] as JObject; var p = ps == null ? null : ps["h"] as JObject; return Game((string)p?["currentGame"] ?? ""); }
        }
        /// <summary>Ending a customs activity hides the customs overlays (players, queue/leaderboards, customs HUD parts); starting one shows them again. Visibility only: the flag lives in scene_layouts.json
        /// and is applied to whatever layout is served, so a layout is never edited. It follows the activity in the Core state (any way it was started or ended), seen on the next read or at once through CustomsSync.</summary>
        static readonly string[] CustomsPages = { "players.html", "players_vertical.html", "queue.html", "customs.html", "pm.html" };   // every page that shows who is in the match / the queue / the customs state, whatever its ?part=
        static bool InCustomsGroup(string id) { var w = Find(id); if (w == null || string.IsNullOrEmpty(w.Src)) return false; string pg = w.Src.Split('?')[0]; return CustomsPages.Contains(pg); }   // the wheel stays: a tournament runs after the customs ended
        /// <summary>the activity, or "queue" when customs run without one (the queue was opened with !queue open: it is open, someone waits or a match is live), else "none"</summary>
        static string ActivityNow()
        {
            try
            {
                var s = CustomsView.State(); var a = (string)s["activity"]; if (!string.IsNullOrEmpty(a) && a != "none") return a;
                bool running = (bool?)s["open"] == true || (s["match"] != null && s["match"].Type != JTokenType.Null) || ((s["queue"] as JArray)?.Count ?? 0) > 0;
                return running ? "queue" : "none";
            }
            catch (Exception) { return "none"; }
        }
        static bool SyncCustoms(JObject all)
        {
            string act = ActivityNow(), last = (string)all["lastActivity"] ?? "none"; bool hid = (bool?)all["customsHidden"] ?? false, nh = act != "none" ? false : last != "none" ? true : hid;
            if (nh != hid || act != last) { all["customsHidden"] = nh; all["lastActivity"] = act; try { Save(all); } catch (Exception) { } }
            return nh;
        }
        public static bool CustomsSync() { lock (L) return SyncCustoms(Load()); }
        public static JObject Get(string profile, string layout)
        {
            GameWatch.EnsureStarted();
            profile = (profile ?? "h").ToLowerInvariant(); if (!Profiles.ContainsKey(profile)) return Err("profile must be h or v");
            lock (L)
            {
                var all = Load(); var p = Prof(all, profile);
                string name = Name(layout); var ls = (JObject)p["layouts"]; string by = "layout"; bool auto = (bool?)p["autoSwitch"] ?? false; string cg = (string)p["currentGame"] ?? "";
                if (name == "" || ls[name] == null)
                {
                    name = (string)p["active"]; by = "active";
                    if (auto && cg != "") { var m = ls.Properties().FirstOrDefault(x => string.Equals((string)x.Value["game"] ?? "", cg, StringComparison.OrdinalIgnoreCase)); if (m != null) { name = m.Name; by = "game"; } }
                }
                var lay = (JObject)ls[name];
                bool chide = SyncCustoms(all);
                if (chide) { lay = (JObject)lay.DeepClone(); foreach (var w in (lay["widgets"] as JArray ?? new JArray()).OfType<JObject>()) if (InCustomsGroup((string)w["id"])) w["visible"] = false; }
                return new JObject { { "ok", true }, { "profile", profile }, { "width", Profiles[profile][0] }, { "height", Profiles[profile][1] }, { "active", (string)p["active"] }, { "name", name },
                    { "names", new JArray(ls.Properties().Select(x => x.Name)) }, { "tags", new JObject(ls.Properties().Select(x => new JProperty(x.Name, (string)x.Value["game"] ?? ""))) }, { "game", (string)lay["game"] ?? "" }, { "autoSwitch", auto }, { "currentGame", cg }, { "resolvedBy", by }, { "games", new JArray(Games) }, { "layout", lay }, { "customsHidden", chide }, { "registry", Widgets()["widgets"] } };
            }
        }

        /// <summary>The current game/activity for both profiles at once (called by whatever sees a category change; with autoSwitch on the layout tagged with it is served).</summary>
        static JObject SetGameAll(JObject b)
        {
            lock (L) { var all = Load(); foreach (var pr in Profiles.Keys) Prof(all, pr)["currentGame"] = Game((string)b["game"]); try { Save(all); } catch (Exception e) { return Err("could not save: " + e.Message); } }
            return new JObject { { "ok", true }, { "currentGame", Game((string)b["game"]) } };
        }
        public static JObject Set(JObject b)
        {
            string action = ((string)b?["action"] ?? "save").ToLowerInvariant(), profile = ((string)b?["profile"] ?? "").ToLowerInvariant();
            if (action == "setgame" && (profile == "*" || profile == "")) return SetGameAll(b);
            if (!Profiles.ContainsKey(profile)) return Err("profile must be h or v");
            lock (L)
            {
                var all = Load(); var p = Prof(all, profile); var ls = (JObject)p["layouts"]; string name = Name((string)b["name"]);
                switch (action)
                {
                    case "save":
                        { if (name == "") return Err("name is required"); var lay = CleanLayout(b["layout"], profile); if (lay == null) return Err("layout.widgets must be an array"); if (ls[name] == null && ls.Count >= 30) return Err("at most 30 layouts per profile"); ls[name] = lay; if (b["activate"] != null && Bool(b["activate"], false)) p["active"] = name; break; }
                    case "tag":
                        { if (ls[name] == null) return Err("no such layout"); string g = Game((string)b["game"]); if (g == "") ((JObject)ls[name]).Remove("game"); else ((JObject)ls[name])["game"] = g; break; }
                    case "settings":
                        { if (b["autoSwitch"] != null) p["autoSwitch"] = Bool(b["autoSwitch"], false); if (b["game"] != null) p["currentGame"] = Game((string)b["game"]); break; }
                    case "setgame":
                        { p["currentGame"] = Game((string)b["game"]); break; }
                    case "clonetogames":
                        {   // one copy of a layout per game: "<from> - <game>", tagged (an existing one is left alone)
                            string from = Name((string)b["from"]); if (ls[from] == null) return Err("no such layout to copy"); var gs = b["games"] as JArray; if (gs == null || gs.Count == 0) return Err("games must be a list");
                            foreach (var gt in gs.Take(20)) { string g = Game((string)gt); if (g == "") continue; string nn = Name(from + " - " + g); if (nn == "" || ls[nn] != null || ls.Count >= 30) continue; var cp = (JObject)ls[from].DeepClone(); cp["game"] = g; cp["updated"] = DateTime.UtcNow.ToString("o"); ls[nn] = cp; }
                            break; }
                    case "activate":
                        { if (ls[name] == null) return Err("no such layout"); p["active"] = name; break; }
                    case "delete":
                        { if (ls[name] == null) return Err("no such layout"); if (ls.Count <= 1) return Err("cannot delete the last layout"); ls.Remove(name); if ((string)p["active"] == name) p["active"] = ls.Properties().First().Name; break; }
                    case "duplicate":
                        { string from = Name((string)b["from"]); if (ls[from] == null) return Err("no such layout to copy"); if (name == "") return Err("name is required"); if (ls[name] != null) return Err("name already used"); var cp = (JObject)ls[from].DeepClone(); cp["updated"] = DateTime.UtcNow.ToString("o"); if (b["game"] != null) { string g = Game((string)b["game"]); if (g == "") cp.Remove("game"); else cp["game"] = g; } ls[name] = cp; break; }
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
