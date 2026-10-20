using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>!rank [name] [1s|2s|3s] and mod !setrank: the channel owner's ranked playlists, from a small file (replaces RocketRankBot's !rank, same output shape:
    /// "Ranked 1v1: Champion I Div II (999) | Ranked 2v2: ... | Ranked 3v3: ..."). Data\runtime\rank.json {"1v1","2v2","3v3","peak","updated"}; seeded once from the
    /// last line RocketRankBot posted. Viewer rank lookups (linked accounts) come later and will plug in at Lookup().</summary>
    public static class Rank
    {
        static readonly object L = new object();
        static string FileP { get { return Path.Combine(HostApi.DataDir, "rank.json"); } }
        static readonly string[] Lists = { "1v1", "2v2", "3v3" };
        public static bool IsCommand(string cmd) { return cmd == "!rank" || cmd == "!setrank"; }
        public static bool IsModCommand(string cmd) { return cmd == "!setrank"; }

        static JObject Load()
        {
            try { if (File.Exists(FileP)) return JObject.Parse(File.ReadAllText(FileP, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { }
            var d = new JObject { { "1v1", "Champion I Div II (999)" }, { "2v2", "Grand Champion I Div III (1532)" }, { "3v3", "Champion II Div III (1276)" }, { "peak", "" }, { "updated", "2026-10-19" }, { "source", "seeded from RocketRankBot's last post" } };
            try { File.WriteAllText(FileP, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { }
            return d;
        }

        static string Clean(string s)
        {   // no pings, links or command starts in anything the bot repeats
            s = Regex.Replace(s ?? "", @"https?://\S+|www\.\S+|@\w+", "").Trim(); s = Regex.Replace(s, @"\s+", " ");
            while (s.StartsWith("!") || s.StartsWith("/") || s.StartsWith(".")) s = s.Substring(1).TrimStart();
            return s.Length > 80 ? s.Substring(0, 80) : s;
        }

        static string ListOf(string w)
        {
            w = (w ?? "").ToLowerInvariant().Trim('/', '-', ' ');
            switch (w) { case "1s": case "1v1": case "duel": case "solo": return "1v1"; case "2s": case "2v2": case "doubles": return "2v2"; case "3s": case "3v3": case "standard": case "threes": return "3v3"; }
            return "";
        }

        public static void Handle(string user, string cmd, string[] args, bool mod, Action<string> say)
        {
            if (cmd == "!setrank") { if (mod) Set(args, say); return; }
            string only = ""; string who = "";
            foreach (var a in args) { string l = ListOf(a); if (l != "") only = l; else if (who == "") who = a.TrimStart('@').ToLowerInvariant(); }
            if (who != "" && who != "innocentpenguin_" && who != "innocentpenguin" && who != "ivan" && who != "penguin") { say("I only know Innocentpenguin_'s ranks for now."); return; }   // TODO viewer lookup (linked accounts)
            JObject d; lock (L) d = Load();
            var parts = Lists.Where(k => only == "" || only == k).Select(k => new { k, v = ((string)d[k] ?? "").Trim() }).Where(x => x.v != "").Select(x => "Ranked " + x.k + ": " + x.v).ToList();
            if (parts.Count == 0) { say("No rank saved yet, a mod can set it with !setrank 2v2 Champion I Div II (1400)."); return; }
            string line = string.Join(" | ", parts);
            if (only == "" && !string.IsNullOrEmpty((string)d["peak"])) line += " | Peak: " + (string)d["peak"];
            say(line);
        }

        static void Set(string[] args, Action<string> say)
        {
            string rest = string.Join(" ", args).Trim();
            if (rest == "") { say("Usage: !setrank 2v2 Champion I Div II (1400), or !setrank peak GC2."); return; }
            lock (L)
            {
                var d = Load(); int n = 0;
                var bulk = Regex.Matches(rest, @"Ranked\s+(1v1|2v2|3v3)\s*:\s*(.+?)(?=\s*\|\s*Ranked\s|\s*$)", RegexOptions.IgnoreCase);
                if (bulk.Count > 0) foreach (Match m in bulk) { string v = Clean(m.Groups[2].Value); if (v != "") { d[m.Groups[1].Value.ToLowerInvariant()] = v; n++; } }
                else
                {
                    string key = args[0].ToLowerInvariant() == "peak" ? "peak" : ListOf(args[0]);
                    if (key == "") { say("Which one? Use 1v1, 2v2, 3v3 or peak, like !setrank 2v2 Champion I Div II (1400)."); return; }
                    string v = Clean(string.Join(" ", args.Skip(1)));
                    if (v == "" || v.ToLowerInvariant() == "clear") { d[key] = ""; n = 1; } else { d[key] = v; n = 1; }
                }
                if (n == 0) { say("Could not read that rank."); return; }
                d["updated"] = DateTime.UtcNow.ToString("yyyy-MM-dd"); d["source"] = "!setrank";
                try { File.WriteAllText(FileP, d.ToString(), new UTF8Encoding(false)); } catch (Exception ex) { Clog.Warn("rank", ex.Message); say("Could not save the rank."); return; }
            }
            say("Rank saved, thanks!");
        }
    }
}
