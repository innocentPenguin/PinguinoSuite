using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The Host's line in the Pinguino Console: one JSON object per line appended to Data\runtime\console\host.jsonl as {ts,module,level,source,msg}.
    /// Never carries chat text or secrets (messages are cut at 300 chars; callers pass statuses and error texts only).</summary>
    public static class Clog
    {
        static string _file; static readonly object _lock = new object();
        static readonly Dictionary<string, KeyValuePair<DateTime, int[]>> _seen = new Dictionary<string, KeyValuePair<DateTime, int[]>>(); public static int RepeatWindowMin = 30;
        static string _lastKey = ""; static DateTime _lastAt = DateTime.MinValue;
        public static string LastErrorText = ""; public static DateTime LastErrorAt = DateTime.MinValue;

        public static void Init(string dataDir)
        {
            try { var d = Path.Combine(dataDir, "console"); Directory.CreateDirectory(d); _file = Path.Combine(d, "host.jsonl"); } catch (Exception) { _file = null; }
        }
        public static void Info(string source, string msg) { Write("info", source, msg); }
        public static void Warn(string source, string msg) { Write("warn", source, msg); }
        public static void Error(string source, string msg) { Write("error", source, msg); }

        static void Write(string level, string source, string msg)
        {
            if (level != "info") { LastErrorText = source + ": " + Cut(msg); LastErrorAt = DateTime.UtcNow; }
            if (_file == null) return;
            try
            {
                lock (_lock)
                {
                    string key = level + "|" + source + "|" + msg;                       // the same line again within 30 s is a reconnect loop, not news
                    if (key == _lastKey && (DateTime.UtcNow - _lastAt).TotalSeconds < 30) return;
                    _lastKey = key; _lastAt = DateTime.UtcNow;
                    if (level != "info")
                    {
                        // the same warning/error (counters in the text ignored, HTTP codes kept) is written once per window with a count of the repeats, not once per attempt
                        string rk = level + "|" + source + "|" + System.Text.RegularExpressions.Regex.Replace(msg ?? "", @"(?<!HTTP )\b\d+\b", "#");
                        if (_seen.Count > 500) _seen.Clear();
                        if (_seen.TryGetValue(rk, out var st) && (DateTime.UtcNow - st.Key).TotalMinutes < RepeatWindowMin) { st.Value[0]++; return; }
                        int more = _seen.TryGetValue(rk, out st) ? st.Value[0] : 0; _seen[rk] = new KeyValuePair<DateTime, int[]>(DateTime.UtcNow, new int[1]);
                        if (more > 0) msg = msg + " (" + more + " more since the last time it was logged)";
                    }
                    try { if (File.Exists(_file) && new FileInfo(_file).Length > 2 * 1024 * 1024) File.Move(_file, _file + ".old"); } catch (Exception) { }
                    var o = new JObject { { "ts", DateTime.UtcNow.ToString("o") }, { "module", "host" }, { "level", level }, { "source", source }, { "msg", Cut(msg) } };
                    File.AppendAllText(_file, o.ToString(Newtonsoft.Json.Formatting.None) + Environment.NewLine, new UTF8Encoding(false));
                }
            }
            catch (Exception) { }
        }
        static string Cut(string m) { m = (m ?? "").Replace("\r", " ").Replace("\n", " "); return m.Length > 300 ? m.Substring(0, 300) : m; }
    }
}
