using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Alert and welcome sounds. Original tiny chimes are synthesized into Data\runtime\sounds\ the first time they are needed (no recorded or copyrighted audio),
    /// and they are the defaults in alerts_settings.json; every file and volume can be replaced from the Suite page through GET/POST /api/alerts-settings.
    /// Sounds play on this PC, so OBS hears them through its desktop-audio capture. The welcome chime follows the "first message" flag, is gated by Welcome.OnlyWhileLive
    /// (live or Offline mode) and plays at most once per login per Host run. PINGUINO_SOUND_DRYRUN=1 records instead of playing (tests).</summary>
    public static class Sounds
    {
        static readonly object _lk = new object();
        static readonly List<JObject> _recent = new List<JObject>();
        static readonly HashSet<string> _welcomed = new HashSet<string>();
        public static readonly string[] Kinds = { "follow", "sub", "resub", "gift", "cheer", "raid", "ban" };
        static readonly string[] AudioExt = { ".wav", ".mp3", ".ogg", ".wma", ".m4a", ".aac", ".flac" };

        public static string Dir { get { return Path.Combine(HostApi.DataDir, "sounds"); } }
        public static string DefaultFile(string name) { return Path.Combine(Dir, name + ".wav"); }
        public static bool DryRun { get { return Environment.GetEnvironmentVariable("PINGUINO_SOUND_DRYRUN") == "1"; } }

        // note sequences in Hz; each note gets a soft attack and an exponential decay
        static readonly Dictionary<string, double[]> Tunes = new Dictionary<string, double[]> {
            { "welcome", new[] { 523.25, 659.25, 783.99 } },
            { "follow", new[] { 659.25, 880.00 } },
            { "sub", new[] { 523.25, 659.25, 783.99, 1046.50 } },
            { "resub", new[] { 587.33, 739.99, 880.00, 1174.66 } },
            { "gift", new[] { 783.99, 987.77, 1174.66, 1567.98 } },
            { "cheer", new[] { 880.00, 1108.73, 1318.51, 1760.00 } },
            { "raid", new[] { 392.00, 392.00, 587.33, 783.99 } },
            { "ban", new[] { 440.00, 349.23, 293.66 } },
        };

        /// <summary>writes any missing default chime; never overwrites a file (Ivan may have replaced one)</summary>
        public static void EnsureDefaults()
        {
            try
            {
                Directory.CreateDirectory(Dir);
                foreach (var t in Tunes) { string f = DefaultFile(t.Key); if (!File.Exists(f)) File.WriteAllBytes(f, Synth(t.Value)); }
            }
            catch (Exception ex) { Clog.Warn("sounds", "could not write the default sounds: " + ex.Message); }
        }

        static byte[] Synth(double[] notes)
        {
            const int rate = 22050; double noteSec = 0.16, tail = 0.25;
            int per = (int)(rate * noteSec), total = per * (notes.Length - 1) + (int)(rate * (noteSec + tail)); var buf = new double[total];
            for (int n = 0; n < notes.Length; n++)
            {
                int start = n * per, len = (int)(rate * (noteSec + tail));
                for (int i = 0; i < len && start + i < total; i++)
                {
                    double t = i / (double)rate, env = Math.Min(1.0, t / 0.005) * Math.Exp(-t * 9.0);
                    buf[start + i] += env * (Math.Sin(2 * Math.PI * notes[n] * t) + 0.25 * Math.Sin(4 * Math.PI * notes[n] * t));
                }
            }
            double peak = 0; foreach (var v in buf) peak = Math.Max(peak, Math.Abs(v)); if (peak < 1e-9) peak = 1;
            using (var ms = new MemoryStream())
            using (var w = new BinaryWriter(ms))
            {
                int dataLen = total * 2;
                w.Write(new[] { 'R', 'I', 'F', 'F' }); w.Write(36 + dataLen); w.Write(new[] { 'W', 'A', 'V', 'E', 'f', 'm', 't', ' ' }); w.Write(16); w.Write((short)1); w.Write((short)1); w.Write(rate); w.Write(rate * 2); w.Write((short)2); w.Write((short)16);
                w.Write(new[] { 'd', 'a', 't', 'a' }); w.Write(dataLen);
                foreach (var v in buf) w.Write((short)(v / peak * 0.8 * short.MaxValue));
                return ms.ToArray();
            }
        }

        /// <summary>plays a file (or records it when PINGUINO_SOUND_DRYRUN=1). Returns a short status line.</summary>
        public static string Play(string kind, string file, double vol, bool test)
        {
            string res = Auto.Sound(file, vol, test || DryRun);
            lock (_lk) { _recent.Add(new JObject { { "ts", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() }, { "kind", kind }, { "file", Path.GetFileName(file ?? "") }, { "volume", vol }, { "result", res } }); while (_recent.Count > 30) _recent.RemoveAt(0); }
            return res;
        }

        /// <summary>a first-ever chatter's first message: chime once per login (the welcome line itself is Chatty's). Gated by the Welcome block in alerts_settings.json.</summary>
        public static void OnFirstChat(string login)
        {
            try
            {
                var al = AlertCfg.Settings(); if ((bool?)al["MuteSounds"] == true) return;
                var w = al["Welcome"] as JObject; if (w == null || (bool?)w["Enabled"] != true) return;
                if ((bool?)w["OnlyWhileLive"] != false && !LiveState.Active) return;
                lock (_lk) { if (!_welcomed.Add(login)) return; }
                string file = (string)w["File"] ?? ""; if (file == "") return;
                Play("welcome", file, (double?)w["Volume"] ?? 0.6, false);
            }
            catch (Exception ex) { Clog.Warn("sounds", "welcome chime failed: " + ex.Message); }
        }

        public static JObject Api(string method, JObject body)
        {
            try
            {
                if (method == "POST" && body != null && body.Count > 0)
                {
                    if (body["test"] != null)
                    {
                        string k = (string)body["test"]; var al = AlertCfg.Settings(); JToken so = k == "welcome" ? al["Welcome"] : al["Sounds"]?[k];
                        if (so == null) return new JObject { { "ok", false }, { "error", "unknown sound: " + k } };
                        string file = (string)so["File"] ?? ""; if (file == "") return new JObject { { "ok", false }, { "error", "no sound set for " + k } };
                        return new JObject { { "ok", true }, { "result", Play(k, file, (double?)so["Volume"] ?? 0.6, false) } };
                    }
                    string err = Validate(body); if (err != null) return new JObject { { "ok", false }, { "error", err } };
                    AlertCfg.Save(body);
                }
                else if (method != "GET" && method != "POST") return new JObject { { "ok", false }, { "error", "GET or POST" } };
                JArray recent; lock (_lk) recent = new JArray(_recent);
                return new JObject { { "ok", true }, { "settings", AlertCfg.Settings() }, { "kinds", new JArray(Kinds) }, { "dir", Dir }, { "recent", recent } };
            }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", ex.Message } }; }
        }

        static string Validate(JObject b)
        {
            foreach (var p in b)
            {
                if (p.Key == "Sounds" || p.Key == "Welcome")
                {
                    var o = p.Value as JObject; if (o == null) return p.Key + " must be an object";
                    foreach (var q in o)
                    {
                        JObject s = p.Key == "Welcome" ? o : q.Value as JObject; string name = p.Key == "Welcome" ? q.Key : q.Key;
                        if (p.Key == "Sounds") { if (Array.IndexOf(Kinds, q.Key) < 0) return "unknown sound kind: " + q.Key; if (s == null) return q.Key + " must be an object"; foreach (var f in s) { var e = Field(f.Key, f.Value); if (e != null) return q.Key + "." + e; } }
                        else { var e = Field(name, q.Value, true); if (e != null) return "Welcome." + e; }
                    }
                }
                else if (p.Key == "MuteSounds") { if (p.Value.Type != JTokenType.Boolean) return "MuteSounds must be true or false"; }
                else if (p.Key == "PopupSeconds") { double d; if (!double.TryParse((string)p.Value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out d) || d < 1 || d > 120) return "PopupSeconds must be 1 to 120"; }
                else if (p.Key == "PopupScene" || p.Key == "PopupSource") { if (p.Value.Type != JTokenType.String) return p.Key + " must be text"; }
                else return "unknown setting: " + p.Key;
            }
            return null;
        }
        static string Field(string key, JToken v, bool welcome = false)
        {
            switch (key)
            {
                case "File":
                {
                    string f = (string)v ?? ""; if (f == "") return null;
                    if (Array.IndexOf(AudioExt, Path.GetExtension(f).ToLowerInvariant()) < 0) return "File must be a sound file (wav, mp3, ogg, wma, m4a, aac, flac)";
                    if (!File.Exists(f)) return "File not found: " + f; return null;
                }
                case "Volume": { double d; if (!double.TryParse((string)v, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out d) || d < 0 || d > 1) return "Volume must be 0 to 1"; return null; }
                case "Enabled": case "OnlyWhileLive": if (!welcome) return "unknown field: " + key; return v.Type == JTokenType.Boolean ? null : key + " must be true or false";
                default: return "unknown field: " + key;
            }
        }
    }
}
