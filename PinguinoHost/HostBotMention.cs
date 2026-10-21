using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>PinguinoB0t answers an @mention (or its name) in ONE short line, but only about the stream (game, title, live/uptime) and moderation situations. General banter and lore stay with Chatty,
    /// help questions with Helper; a line that also names another bot is left to that bot. Rate limited per user and globally; the send path has its own duplicate guard.</summary>
    public static class BotMention
    {
        static readonly string[] Names = { "pinguinob0t", "pinguinb0t", "pinguinobot", "pinguinbot", "pinguino b0t", "pinguino bot", "pinguin b0t", "pinguin bot", "penguinob0t", "penguinb0t", "penguinobot", "penguinbot", "pinguino_bot", "pinguino_b0t", "pinguino", "pinguinos", "penguino", "penguinos", "penguins" };   // Ivan is penguin/peng/peg; the bots are pinguino(s)/penguins (@name only)
        static readonly Regex Others = new Regex(@"@?(chattypinguino|chatty ?pinguino|helperpinguino|helper ?pinguino)", RegexOptions.IgnoreCase);
        static readonly Regex Named = new Regex("@(" + string.Join("|", Names.Select(Regex.Escape)) + @")(?![a-z0-9_])", RegexOptions.IgnoreCase);
        static readonly Regex ModSit = new Regex(@"\b(slur|slurs|racis\w*|toxic\w*|harass\w*|threat\w*|doxx?\w*|spammer|spamming|trolling|troll|should i (report|ban|timeout)|what (should|do) i do|report (him|her|them|this)|unmod|un-mod|ban me|timeout me|ban him|ban her)\b", RegexOptions.IgnoreCase);
        static readonly Regex Game = new Regex(@"\b(what game|which game|playing what|what('s| is| are)? (he|ya|you|we|this|penguin|innocent\w*)?\s*playing|what category|game is this)\b", RegexOptions.IgnoreCase);
        static readonly Regex Title = new Regex(@"\b(stream title|what('s| is) the title|title of the stream)\b", RegexOptions.IgnoreCase);
        static readonly Regex Live = new Regex(@"\b(how long.*(live|stream)|uptime|been live|are (we|you|u) live|is (he|penguin|the stream) live|when .*(stream|live)|stream (start|time|schedule))\b", RegexOptions.IgnoreCase);
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>(); static DateTime _global = DateTime.MinValue; static readonly object L = new object();

        public static bool OnChat(string user, string text, int role, Action<string> say)
        {
            text = (text ?? "").Trim(); if (text == "" || text.StartsWith("!")) return false;
            if (!Named.IsMatch(text) || Others.IsMatch(text)) return false;
            string line = Pick(text); if (line == null) return false;
            int per, glob; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_MENTION_COOL_USER"), out per)) per = 30; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_MENTION_COOL_GLOBAL"), out glob)) glob = 8;
            lock (L)
            {
                var now = DateTime.UtcNow; DateTime t;
                if ((now - _global).TotalSeconds < glob || (Cool.TryGetValue(user.ToLowerInvariant(), out t) && (now - t).TotalSeconds < per)) return true;   // swallowed: still ours, nobody else answers it
                _global = now; Cool[user.ToLowerInvariant()] = now;
            }
            say("@" + user + " " + line); return true;
        }

        static string Pick(string text)
        {
            if (ModSit.IsMatch(text)) return Regex.IsMatch(text, @"unmod|un-mod") ? "I don't decide who is a mod, that's up to Ivan." : "Mods decide: use timeout/ban as needed, or ping a mod.";
            if (Title.IsMatch(text) || Game.IsMatch(text))
            {
                string g, ti; Channel(out g, out ti);
                if (Title.IsMatch(text)) return ti != "" ? "Title: " + ti : "Check the stream title right under the video.";
                return g != "" ? "Right now: " + g + "." : "Check the category under the stream.";
            }
            if (Live.IsMatch(text)) return LiveState.UptimeLine();
            return null;
        }

        static void Channel(out string game, out string title)
        {
            game = ""; title = ""; if (HostApi.SimMode && Environment.GetEnvironmentVariable("PINGUINO_HELIX_BASE") == null) return;
            try { JToken d; string err; TwitchApi.Call(HttpMethod.Get, "/channels?broadcaster_id={bid}", null, out d, out err); var c = (d as JArray)?.FirstOrDefault(); if (c != null) { game = (string)c["game_name"] ?? ""; title = (string)c["title"] ?? ""; } }
            catch (Exception) { }
        }
    }
}
