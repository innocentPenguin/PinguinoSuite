using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>First-message link spam (design: Docs\SPAM_FIRST_MESSAGE.md). A brand-new chatter (Twitch's first-msg flag, and never welcomed before) whose very first line holds a link, a domain-like
    /// word ("streamboo .org") or a known spam phrase is a spam candidate. Config Data\config\spam_first.json {"enabled":false,"dryRun":true,"timeoutSeconds":600,"phrases":[],"domains":[]}
    /// (read live). enabled=false: nothing changes except that the line is flagged for the bots (argument spamCandidate). enabled + dryRun: only the log says "would timeout".
    /// enabled + dryRun=false: the line is dropped here (no greeting, no welcome points, no bot sees it) and the account gets a ChannelControl.Timeout. Never for the broadcaster, mods, VIPs, subs or bots.
    /// Log: Data\runtime\spam_first.log (DataDir).</summary>
    public static class SpamFirst
    {
        static readonly string[] Tlds = { "com", "org", "net", "io", "gg", "tv", "ly", "xyz", "co", "me", "info", "ru", "su", "top", "site", "online", "live", "shop", "link", "club", "cc", "ws", "app", "dev", "stream", "fun", "vip", "bio", "store", "click", "pro", "biz", "to", "us", "ai" };
        static readonly string[] DefaultPhrases = { "best viewers", "cheap viewers", "buy followers", "buy viewers", "free followers", "streamboo", "viewers and followers", "become famous" };
        static readonly string TldAlt = string.Join("|", Tlds);
        static readonly Regex Url = new Regex(@"(https?://|www\.)\S+", RegexOptions.IgnoreCase | RegexOptions.Compiled);
        static readonly Regex Domain = new Regex(@"(?<![a-z0-9])[a-z0-9][a-z0-9\-]{2,}\s{0,2}\.\s{0,2}(" + TldAlt + @")(?![a-z0-9])", RegexOptions.IgnoreCase | RegexOptions.Compiled);
        static readonly Regex DotWord = new Regex(@"(?<![a-z0-9])[a-z0-9][a-z0-9\-]{2,}\s{0,2}[\(\[]?\s?dot\s?[\)\]]?\s{0,2}(" + TldAlt + @")(?![a-z0-9])", RegexOptions.IgnoreCase | RegexOptions.Compiled);
        static readonly HashSet<string> Done = new HashSet<string>(); static readonly object L = new object();
        static readonly Dictionary<string, DateTime> Flagged = new Dictionary<string, DateTime>();
        internal static void TestReset() { lock (L) { Done.Clear(); Flagged.Clear(); } }

        static JObject Cfg() { try { return JObject.Parse(File.ReadAllText(Path.Combine(HostApi.DataDir, "config", "spam_first.json")).TrimStart((char)0xFEFF)); } catch (Exception) { return new JObject(); } }
        static string LogP { get { return Path.Combine(HostApi.DataDir, "spam_first.log"); } }
        static void Log(string s) { try { File.AppendAllText(LogP, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "\t" + s + "\n"); } catch (Exception) { } Clog.Info("spam", s); }

        static string Clean(string t)
        {
            var sb = new StringBuilder();
            foreach (char c in t ?? "") { var cat = char.GetUnicodeCategory(c); if (cat == System.Globalization.UnicodeCategory.Format || c == '­') continue; sb.Append(c); }
            return sb.ToString().ToLowerInvariant();
        }

        /// <summary>the reason a first message looks like link spam ("link", "domain", "phrase: x"), or "" when it does not. Pure: no state, no exemptions.</summary>
        public static string Looks(string text) { return Looks(text, null); }
        static string Looks(string text, JObject cfg)
        {
            string t = Clean(text); if (t.Trim() == "") return "";
            if (Url.IsMatch(t)) return "link";
            if (Domain.IsMatch(t) || DotWord.IsMatch(t)) return "domain";
            var phrases = new List<string>(DefaultPhrases);
            try { foreach (var p in (cfg?["phrases"] as JArray) ?? new JArray()) { string s = ((string)p ?? "").Trim().ToLowerInvariant(); if (s != "") phrases.Add(s); } } catch (Exception) { }
            foreach (string p in phrases) if (t.Contains(p)) return "phrase: " + p;
            try { foreach (var dm in (cfg?["domains"] as JArray) ?? new JArray()) { string s = ((string)dm ?? "").Trim().ToLowerInvariant(); if (s != "" && t.Replace(" ", "").Contains(s)) return "domain: " + s; } } catch (Exception) { }
            return "";
        }

        /// <summary>true = the line was spam and is dropped here (the caller returns before any bot sees it). candidate = it looks like first-message spam (even when the feature is off), for the bots' greeting.</summary>
        public static bool OnChat(string user, string text, int role, bool isSub, int subTier, bool firstMsg, out bool candidate)
        {
            candidate = false;
            try
            {
                if (!firstMsg || string.IsNullOrEmpty(user) || Control.Synthetic) return false;
                string login = user.Trim().TrimStart('@').ToLowerInvariant();
                if (role >= 2 || isSub || subTier > 0) return false;   // VIP, moderator, broadcaster, subscriber
                if (Sim.IsSim(login) && !HostApi.SimMode) return false;
                if (Boards.IsBot(login) || Boards.AllBots().Contains(login)) return false;
                string ch = ""; try { ch = ((string)HostApi.StreamerCreds()["Channel"] ?? "").ToLowerInvariant(); } catch (Exception) { }
                if (login == ch) return false;
                if (Economy.Applied("welcome:" + login)) return false;   // welcomed before: not a new chatter, whatever the flag says
                var c = Cfg(); string why = Looks(text, c); if (why == "") return false;
                candidate = true;
                if ((bool?)c["enabled"] != true) return false;
                bool dry = (bool?)c["dryRun"] != false; int secs = (int?)c["timeoutSeconds"] ?? 600; if (secs < 1) secs = 600;
                string snip = (text ?? "").Replace("\t", " ").Replace("\n", " "); if (snip.Length > 80) snip = snip.Substring(0, 80);
                lock (L) { Flagged[login] = DateTime.UtcNow; }
                if (dry) { Log("would timeout " + login + " " + secs + "s [" + why + "] \"" + snip + "\""); return false; }
                bool again; lock (L) again = !Done.Add(login);
                if (again) { Log("dropped " + login + " [" + why + "] (already timed out this session) \"" + snip + "\""); return true; }
                string res;
                try { var r = ChannelControl.Timeout(login, secs, "first-message link spam (auto)"); res = (bool?)r["ok"] == true ? "ok" : "refused/failed: " + (string)r["error"]; } catch (Exception ex) { res = "error: " + ex.Message; }
                Log("timeout " + login + " " + secs + "s [" + why + "] -> " + res + " \"" + snip + "\"");
                return true;
            }
            catch (Exception ex) { Clog.Warn("spam", "spam check failed: " + ex.Message); return false; }
        }

        /// <summary>true when this account was banned or timed out just now (used before paying the welcome bonus). Fails open (false) when nothing can be checked.
        /// PINGUINO_TEST_BANNED="a,b" makes tests deterministic; a login the spam rule timed out this session counts too.</summary>
        public static bool BannedNow(string login)
        {
            login = (login ?? "").Trim().ToLowerInvariant(); if (login == "") return false;
            try
            {
                string tb = Environment.GetEnvironmentVariable("PINGUINO_TEST_BANNED");
                if (!string.IsNullOrEmpty(tb)) return tb.Split(',').Select(x => x.Trim().ToLowerInvariant()).Contains(login);
                lock (L) { if (Done.Contains(login)) return true; }
                if (HostApi.SimMode) return false;
                string err; string uid = TwitchApi.UserId(login, out err); if (uid == "") return false;
                JToken d; string code = TwitchApi.Call(HttpMethod.Get, "/moderation/banned?broadcaster_id={bid}&user_id=" + uid, null, out d, out err);
                return code == "200" && (d as JArray)?.Count > 0;
            }
            catch (Exception) { return false; }
        }
    }
}
