using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Typo handling for the queue commands (Plan 7 C): "! join", "!jon", "!joi", "!jpin", "!joinm", "!rejoin" -> !join; !unjoin/!quit/!unqueue/!leaveq -> !leave; !list/!q -> !queue.
    /// Any other word one edit away from !join / !leave / !queue / !points that no bot knows answers ONCE per user with "did you mean !join?". NO !pengs/!peng aliases.
    /// Config Data\config\cmdfix.json {"enabled":true,"didYouMean":true,"aliases":{"!jon":"!join"}} (read live, extra aliases are added to the built-in ones).</summary>
    public static class CmdFix
    {
        static readonly Dictionary<string, string> Builtin = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) {
            { "!jon", "!join" }, { "!joi", "!join" }, { "!jpin", "!join" }, { "!joinm", "!join" }, { "!joinn", "!join" }, { "!rejoin", "!join" }, { "!jion", "!join" }, { "!joim", "!join" },
            { "!unjoin", "!leave" }, { "!quit", "!leave" }, { "!unqueue", "!leave" }, { "!leaveq", "!leave" },
            { "!list", "!queue" }, { "!q", "!queue" } };
        static readonly string[] Targets = { "!join", "!leave", "!queue", "!points" };
        static readonly HashSet<string> Told = new HashSet<string>(); static readonly object L = new object();
        static string CfgP { get { return Path.Combine(HostApi.DataDir, "config", "cmdfix.json"); } }
        static JObject Cfg() { try { return JObject.Parse(File.ReadAllText(CfgP).TrimStart((char)0xFEFF)); } catch (Exception) { return new JObject(); } }

        /// <summary>returns the (possibly rewritten) line; didYouMean is set when the line was a near miss that was answered and must not go any further.</summary>
        // join-type commands change the queue (they act on the person or on others): a typo of them is only a question until the person says yes. Info commands (!queue, !points ...) just run.
        static readonly HashSet<string> Asks = new HashSet<string> { "!join", "!leave" };
        static readonly Dictionary<string, KeyValuePair<string, DateTime>> Pending = new Dictionary<string, KeyValuePair<string, DateTime>>();
        static readonly Regex Yes = new Regex(@"^\s*(yes|yep|yeah|ya|y|yea|yup|ye|sure|correct|please|ok|okay)[.!\s]*$", RegexOptions.IgnoreCase);
        static readonly Regex No = new Regex(@"^\s*(no|nope|nah|n|cancel|nevermind|never mind)[.!\s]*$", RegexOptions.IgnoreCase);
        internal static void TestReset() { lock (L) { Pending.Clear(); Told.Clear(); } }

        /// <summary>true when this typo of a join-type command was turned into a question; false = run it as `to`</summary>
        static bool AskFirst(string user, string to, string rest, Action<string> say)
        {
            if (!Asks.Contains(to)) return false;
            string u = user.ToLowerInvariant(); bool ask;
            lock (L) { KeyValuePair<string, DateTime> p; ask = !(Pending.TryGetValue(u, out p) && p.Key == to + rest && (DateTime.UtcNow - p.Value).TotalSeconds < 20); Pending[u] = new KeyValuePair<string, DateTime>(to + rest, ask ? DateTime.UtcNow : Pending[u].Value); }
            if (ask) say("@" + user + " did you mean " + to + "? Say yes to confirm.");
            return true;
        }

        public static string Fix(string user, string text, Action<string> say, out bool swallowed)
        {
            swallowed = false; if (string.IsNullOrEmpty(text)) return text;
            var c = Cfg(); if ((bool?)c["enabled"] == false) return text;
            { KeyValuePair<string, DateTime> p; bool have; string u0 = user.ToLowerInvariant();
              lock (L) { have = Pending.TryGetValue(u0, out p); if (have && (DateTime.UtcNow - p.Value).TotalSeconds > 30) { Pending.Remove(u0); have = false; } }
              if (have) { if (Yes.IsMatch(text)) { lock (L) Pending.Remove(u0); Clog.Info("cmdfix", "confirmed " + p.Key); return p.Key; } if (No.IsMatch(text)) { lock (L) Pending.Remove(u0); swallowed = true; return text; } } }
            string t = text.TrimStart(); if (!t.StartsWith("!")) return text;
            var m = Regex.Match(t, @"^!\s{0,2}([A-Za-z0-9_]{1,20})[.,'`´’""!?]*(?=\s|$)(.*)$", RegexOptions.Singleline); if (!m.Success) return text;
            string cmd = "!" + m.Groups[1].Value.ToLowerInvariant(), rest = m.Groups[2].Value; bool spaced = Regex.IsMatch(t, @"^!\s");
            string to = null; var extra = c["aliases"] as JObject; JToken x;
            if (extra != null && (x = extra[cmd]) != null) to = (string)x; else if (Builtin.ContainsKey(cmd)) to = Builtin[cmd];
            if (to != null) { if (AskFirst(user, to, rest, say)) { swallowed = true; return text; } Clog.Info("cmdfix", cmd + " -> " + to); return to + rest; }
            if (spaced) { if (Targets.Contains(cmd) || IsKnown(cmd)) { Clog.Info("cmdfix", "! " + cmd.Substring(1) + " -> " + cmd); return cmd + rest; } return text; }   // "! join" -> "!join" (only for real commands)
            if (cmd != t.Split(' ')[0].ToLowerInvariant() && (Targets.Contains(cmd) || IsKnown(cmd))) { Clog.Info("cmdfix", "punctuation after " + cmd); return cmd + rest; }   // "!join." / "!join'" -> "!join"
            if ((bool?)c["didYouMean"] == false || cmd.Length < 4 || IsKnown(cmd)) return text;
            string near = Targets.FirstOrDefault(tg => tg != cmd && Dist(tg, cmd) == 1); if (near == null) return text;
            if (AskFirst(user, near, rest, say)) { swallowed = true; return text; }
            Clog.Info("cmdfix", cmd + " -> " + near + " (info command, just runs)"); return near + rest;
        }

        static bool IsKnown(string cmd)
        {
            if (Targets.Contains(cmd)) return true;
            try { if (ChannelLore.IsCommand(cmd) || ChannelLore.ChattyOwns(cmd)) return true; } catch (Exception) { }
            try { var j = SubsImport.ParseJ(File.ReadAllText(Path.Combine(Program.SuiteDir ?? "", "PinguinoB0t", "commands.json"))); foreach (var e in (j["commands"] as JArray) ?? new JArray()) { if (string.Equals((string)e["command"], cmd, StringComparison.OrdinalIgnoreCase)) return true; foreach (var a in (e["aliases"] as JArray) ?? new JArray()) if (string.Equals((string)a, cmd, StringComparison.OrdinalIgnoreCase)) return true; } } catch (Exception) { }
            return false;
        }

        static int Dist(string a, string b)   // Damerau-Levenshtein (a swap counts as 1)
        {
            var d = new int[a.Length + 1, b.Length + 1];
            for (int i = 0; i <= a.Length; i++) d[i, 0] = i; for (int j = 0; j <= b.Length; j++) d[0, j] = j;
            for (int i = 1; i <= a.Length; i++) for (int j = 1; j <= b.Length; j++)
            {
                int cost = a[i - 1] == b[j - 1] ? 0 : 1; d[i, j] = Math.Min(Math.Min(d[i - 1, j] + 1, d[i, j - 1] + 1), d[i - 1, j - 1] + cost);
                if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) d[i, j] = Math.Min(d[i, j], d[i - 2, j - 2] + 1);
            }
            return d[a.Length, b.Length];
        }
    }
}
