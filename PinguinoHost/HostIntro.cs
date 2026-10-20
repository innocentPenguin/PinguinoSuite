using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Sub intro clips: a T1/T2/T3 subscriber's first chat message of each stream plays that person's own clip on the stream (OBS browser sources, one at a time, highest tier first).
    /// Clips live in Data\intros\LOGIN.mp4|webm|gif (vertical ones as LOGIN_v.mp4, T3 only); _default_t1/_t2/_t3 are optional per-tier fallbacks. Nothing is said in chat.</summary>
    public static class Intro
    {
        public class Item { public long Id; public string Login, Display, File, Slot; public int Tier; public long At; public bool Test; }
        static readonly object L = new object();
        static readonly List<Item> Queue = new List<Item>();
        static Item Cur; static long CurStart; static long _seq; static readonly Dictionary<string, long> SlotSeen = new Dictionary<string, long>();
        static HashSet<string> Played = new HashSet<string>(); static bool? LastLive; static bool _loaded;
        static readonly string[] Exts = { ".mp4", ".webm", ".gif", ".mov", ".m4v" };
        static long NowS() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        static string StateP { get { return Path.Combine(HostApi.DataDir, "intro_state.json"); } }
        static string SettingsP { get { return Path.Combine(HostApi.DataDir, "intro_settings.json"); } }

        public static JObject Settings()
        {
            var d = new JObject { { "Enabled", true }, { "OnlyWhileLive", true }, { "Dir", "" }, { "MaxPlaySec", 60 }, { "SkipOfflineSlots", true }, { "UseTierDefaults", true },
                { "T1", true }, { "T2", true }, { "T3", true }, { "Volume", 1.0 }, { "SlotOfflineSec", 15 }, { "GifSec", 6 } };
            try { if (File.Exists(SettingsP)) { foreach (var p in JObject.Parse(File.ReadAllText(SettingsP))) d[p.Key] = p.Value; } else File.WriteAllText(SettingsP, d.ToString()); } catch (Exception) { }
            return d;
        }
        public static JObject Save(JObject b)
        {
            var d = Settings();
            foreach (var k in new[] { "Enabled", "OnlyWhileLive", "Dir", "MaxPlaySec", "SkipOfflineSlots", "UseTierDefaults", "T1", "T2", "T3", "Volume", "SlotOfflineSec", "GifSec" }) if (b[k] != null) d[k] = b[k];
            File.WriteAllText(SettingsP, d.ToString()); return new JObject { { "ok", true }, { "settings", d } };
        }
        public static string Dir()
        {
            string c = ((string)Settings()["Dir"] ?? "").Trim();
            if (c != "") return c;
            try { var parent = Directory.GetParent(HostApi.DataDir.TrimEnd('\\', '/')); if (parent != null) return Path.Combine(parent.FullName, "intros"); } catch (Exception) { }
            return Path.Combine(HostApi.DataDir, "intros");
        }
        static void Load()
        {
            if (_loaded) return; _loaded = true;
            try { if (File.Exists(StateP)) { var j = JObject.Parse(File.ReadAllText(StateP)); LastLive = (bool?)j["live"]; Played = new HashSet<string>((j["played"] as JArray ?? new JArray()).Select(x => (string)x)); } } catch (Exception) { }
        }
        static void SaveState() { try { File.WriteAllText(StateP, new JObject { { "live", LastLive }, { "played", new JArray(Played) } }.ToString()); } catch (Exception) { } }

        /// <summary>tier from the IRC badges: subscriber/3012 = tier 3 (12 months), 2003 = tier 2, anything below 1000 = tier 1. 0 = not a subscriber.</summary>
        public static int TierFromBadges(string badges)
        {
            var m = System.Text.RegularExpressions.Regex.Match(badges ?? "", @"(?:^|,)subscriber/(\d+)");
            if (!m.Success) return 0; int v; int.TryParse(m.Groups[1].Value, out v);
            return v >= 3000 ? 3 : v >= 2000 ? 2 : 1;
        }

        static string FindFile(string name, out bool vertical)
        {
            vertical = false; string dir = Dir(); if (!Directory.Exists(dir)) return null;
            foreach (var e in Exts) { string f = Path.Combine(dir, name + e); if (File.Exists(f)) return Path.GetFileName(f); }
            foreach (var e in Exts) { string f = Path.Combine(dir, name + "_v" + e); if (File.Exists(f)) { vertical = true; return Path.GetFileName(f); } }
            return null;
        }
        static string SlotFor(int tier, bool vertical) { return tier >= 3 ? (vertical ? "t3v" : "t3") : tier == 2 ? "t2" : "t1"; }

        /// <summary>called for every chat line with the sender's sub tier (0 = not a sub). Queues the intro the first time per stream.</summary>
        public static void OnChat(string display, int tier)
        {
            if (tier <= 0) return;
            var s = Settings(); if ((bool?)s["Enabled"] != true || (bool?)s["T" + tier] == false) return;
            string login = (display ?? "").ToLowerInvariant();
            lock (L)
            {
                Load();
                bool? live = LiveState.Live;
                if (live != null && live != LastLive) { if (live == true) Played.Clear(); LastLive = live; SaveState(); }
                if ((bool?)s["OnlyWhileLive"] != false && !LiveState.Active) return;
                if (Played.Contains(login)) return;
                Played.Add(login); SaveState();
                Enqueue(login, display, tier, false);
            }
        }

        /// <summary>false when the person has no clip (and no tier default).</summary>
        static bool Enqueue(string login, string display, int tier, bool test)
        {
            bool vert; string f = FindFile(login, out vert);
            if (f == null && (bool?)Settings()["UseTierDefaults"] != false) f = FindFile("_default_t" + tier, out vert);
            if (f == null) return false;
            if (Cur != null && Cur.Login == login) return false;
            if (Queue.Any(q => q.Login == login)) return false;
            Queue.Add(new Item { Id = ++_seq, Login = login, Display = display, Tier = tier, File = f, Slot = SlotFor(tier, vert && tier >= 3), At = NowS(), Test = test });
            return true;
        }

        static Item PickNext()
        {
            var s = Settings(); long off = (long)((int?)s["SlotOfflineSec"] ?? 15); bool skipOff = (bool?)s["SkipOfflineSlots"] != false;
            while (Queue.Count > 0)
            {
                var n = Queue.OrderByDescending(q => q.Tier).ThenBy(q => q.Id).First(); Queue.Remove(n);
                long seen; if (skipOff && (!SlotSeen.TryGetValue(n.Slot, out seen) || NowS() - seen > off)) { Clog.Info("intro", "no browser source '" + n.Slot + "' is open: skipped the intro for " + n.Display); continue; }
                return n;
            }
            return null;
        }

        /// <summary>what one overlay slot should be playing right now.</summary>
        public static JObject Poll(string slot)
        {
            lock (L)
            {
                slot = (slot ?? "").ToLowerInvariant(); SlotSeen[slot] = NowS();
                long max = Math.Max(5, (long)((int?)Settings()["MaxPlaySec"] ?? 60));
                if (Cur != null && NowS() - CurStart > max + 3) { Clog.Warn("intro", "the intro for " + Cur.Display + " never reported back, moving on"); Cur = null; }
                if (Cur == null) { Cur = PickNext(); if (Cur != null) CurStart = NowS(); }
                if (Cur == null || Cur.Slot != slot) return new JObject { { "play", null } };
                return new JObject { { "play", new JObject { { "id", Cur.Id }, { "url", "/intro/media/" + Uri.EscapeDataString(Cur.File) }, { "user", Cur.Display }, { "tier", Cur.Tier }, { "maxSec", Cur.File.EndsWith(".gif", StringComparison.OrdinalIgnoreCase) ? (long)((int?)Settings()["GifSec"] ?? 6) : max } } }, { "volume", (double?)Settings()["Volume"] ?? 1.0 } };
            }
        }
        public static JObject Done(long id) { lock (L) { if (Cur != null && Cur.Id == id) Cur = null; return new JObject { { "ok", true } }; } }
        public static JObject Skip() { lock (L) { var was = Cur; Cur = null; return new JObject { { "ok", true }, { "skipped", was == null ? null : was.Display } }; } }
        public static JObject Clear() { lock (L) { int n = Queue.Count; Queue.Clear(); Cur = null; return new JObject { { "ok", true }, { "cleared", n } }; } }
        public static JObject ResetPlayed() { lock (L) { Load(); Played.Clear(); SaveState(); return new JObject { { "ok", true } }; } }
        public static JObject Test(string login, int tier)
        {
            login = (login ?? "").Trim().ToLowerInvariant().TrimStart('@'); if (login == "") return new JObject { { "ok", false }, { "error", "login required" } };
            if (tier < 1 || tier > 3) tier = 1;
            lock (L) { bool ok = Enqueue(login, login, tier, true); return new JObject { { "ok", ok }, { "error", ok ? null : "no clip for " + login + " in " + Dir() + " (and no _default_t" + tier + " clip), or already queued/playing" } }; }
        }
        public static JObject Api()
        {
            lock (L)
            {
                Load(); var files = new JArray();
                try { var dir = Dir(); if (Directory.Exists(dir)) foreach (var f in Directory.GetFiles(dir).Where(f => Exts.Contains(Path.GetExtension(f).ToLowerInvariant())).OrderBy(f => f)) files.Add(Path.GetFileName(f)); } catch (Exception) { }
                var slots = new JObject(); foreach (var k in new[] { "t1", "t2", "t3", "t3v" }) { long seen; slots[k] = SlotSeen.TryGetValue(k, out seen) ? (JToken)(NowS() - seen) : null; }
                Func<Item, JObject> o = i => new JObject { { "id", i.Id }, { "login", i.Login }, { "display", i.Display }, { "tier", i.Tier }, { "slot", i.Slot }, { "file", i.File }, { "test", i.Test } };
                return new JObject { { "ok", true }, { "settings", Settings() }, { "dir", Dir() }, { "current", Cur == null ? null : o(Cur) }, { "queue", new JArray(Queue.OrderByDescending(q => q.Tier).ThenBy(q => q.Id).Select(o)) },
                    { "playedThisStream", Played.Count }, { "live", LiveState.Live }, { "files", files }, { "slotsSeenAgoSec", slots },
                    { "urls", new JObject { { "t1", "/overlay/intro?slot=t1" }, { "t2", "/overlay/intro?slot=t2" }, { "t3", "/overlay/intro?slot=t3" }, { "t3v", "/overlay/intro?slot=t3v" } } } };
            }
        }
        /// <summary>safe path of a clip for the media route (a bare file name from the clip folder only).</summary>
        public static string MediaPath(string name)
        {
            if (string.IsNullOrEmpty(name) || name != Path.GetFileName(name)) return null;
            if (!Exts.Contains(Path.GetExtension(name).ToLowerInvariant())) return null;
            string f = Path.Combine(Dir(), name); return File.Exists(f) ? f : null;
        }
        public static string Mime(string name)
        {
            switch (Path.GetExtension(name).ToLowerInvariant()) { case ".webm": return "video/webm"; case ".gif": return "image/gif"; case ".mov": return "video/quicktime"; default: return "video/mp4"; }
        }
    }
}
