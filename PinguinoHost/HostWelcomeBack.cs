using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>IDEAS #36: varied welcome-back lines for a chatter who has been away. PURE: no files, no Host state (so Tools/test-welcomeback can compile it alone).
    /// Band by days away (2-6 short, 7-29 week, 30-89 month, 90+ long); closeness from the people graph (core = a chat duo, regular = chat buddies or several ties,
    /// known = a few exchanges or a regular group, "" = nothing known / opted out / bot). Close people get the warmer pool ON TOP of the band pool.
    /// Lines never state numbers, never quote anything a person said, and never say how the bot knows them. Data\lore\welcome_lines.json
    /// ({"short":[...],"week":[...],"month":[...],"long":[...],"warm":[...]} with {u}) is added to the built-ins by the caller via Extra.</summary>
    public static class WelcomeBack
    {
        public static string Band(int days) { return days < 2 ? "" : days < 7 ? "short" : days < 30 ? "week" : days < 90 ? "month" : "long"; }

        static readonly Dictionary<string, string[]> Pools = new Dictionary<string, string[]> {
            { "short", new[] { "welcome back {u}!", "{u} is back, chat got louder.", "oh hey {u}, there you are.", "{u} returns. we kept your seat warm-ish.", "{u} is back, no ban today." } },
            { "week", new[] { "{u}!! been a minute, welcome back.", "look who wandered back in, hi {u}.", "{u} survived the week away. welcome back.", "{u} has entered the chat again, W." } },
            { "month", new[] { "{u}?? it has been ages, welcome back!", "the prodigal chatter {u} returns.", "{u} is back, did we miss anything? (yes, lots).", "long time no see {u}, pull up a chair.", "{u} stepped out for a bit and now we are glazing the return. welcome back." } },
            { "long", new[] { "{u}!!! legend returns, welcome home.", "is that {u}?? the chat history says yes, welcome back.", "{u} came back from the shadow realm. W.", "somebody tell the penguins, {u} is back." } },
            { "warm", new[] { "{u} is back and chat just feels right again.", "finally, {u}. we were getting weird without you.", "{u}!! the usual crowd perks up when you show.", "ok {u} is here, the vibes are fixed." } },
        };

        /// <summary>The closeness label of one person from a people_graph document: "core", "regular", "known" or "". The caller must pass "" for bots and opted-out people.</summary>
        public static string Standing(JObject doc, string login)
        {
            if (doc == null || string.IsNullOrEmpty(login)) return "";
            int ties = 0; long best = 0;
            foreach (var e in (doc["edges"] as JArray ?? new JArray()).OfType<JObject>())
            {
                string x = (string)e["a"], y = (string)e["b"];
                if (x != login && y != login) continue;
                ties++; long m = (long?)e["mutual"] ?? 0; if (m > best) best = m;
            }
            if (best >= 200) return "core";
            if (best >= 30 || ties >= 3) return "regular";
            if (ties >= 1) return "known";
            foreach (var g in (doc["groups"] as JArray ?? new JArray()).OfType<JObject>())
                if ((g["members"] as JArray ?? new JArray()).Any(t => (string)t == login)) return "known";
            return "";
        }

        // Spam / viewbot accounts ("Best viewers with viewers streamboo .org"): never welcomed, never lore. Same rules as Tools/lore-mining/spam.mjs.
        static readonly System.Text.RegularExpressions.Regex DomainLike = new System.Text.RegularExpressions.Regex(@"(https?://|www\.|\b[a-z0-9][a-z0-9-]{2,}\s?\.\s?(org|com|net|xyz|ru|shop|site|club|ly|cc)\b)", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        static readonly System.Text.RegularExpressions.Regex NormalLinks = new System.Text.RegularExpressions.Regex(@"(https?://)?([a-z0-9-]+\.)*(twitch\.tv|youtube\.com|youtu\.be|discord\.gg|discord\.com|spotify\.com)\S*", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        static readonly System.Text.RegularExpressions.Regex PromoWord = new System.Text.RegularExpressions.Regex(@"\b(viewers?|followers?|views|subs|promo|cheap|boost|streamboo|bigfollows)\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        /// <summary>Link/domain-like text that sells viewers or followers (or any link in a first message).</summary>
        public static bool IsSpamText(string text, bool firstMessage = false)
        {
            if (string.IsNullOrWhiteSpace(text)) return false;
            text = new string(text.Normalize(System.Text.NormalizationForm.FormKD).Where(c => System.Globalization.CharUnicodeInfo.GetUnicodeCategory(c) != System.Globalization.UnicodeCategory.NonSpacingMark).ToArray()); // fancy letters fold to plain
            if (text.IndexOf("best viewers with viewers", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            string t = NormalLinks.Replace(text, " "); // twitch / youtube / discord links are normal chat
            bool dom = DomainLike.IsMatch(t);
            return dom && (firstMessage || PromoWord.IsMatch(t));
        }
        /// <summary>Auto-generated viewbot logins: 16+ letters/digits that end in a random-looking tail (6+ consonants in a row, or digit-letter-digit in the last 6 characters).</summary>
        public static bool IsSpamLogin(string login)
        {
            string l = System.Text.RegularExpressions.Regex.Replace((login ?? "").ToLowerInvariant().TrimStart('@'), "[^a-z0-9]", "");
            if (l.Length < 16) return false;
            if (System.Text.RegularExpressions.Regex.IsMatch(l.Substring(l.Length - 6), "[0-9][a-z][0-9]")) return true;
            return System.Text.RegularExpressions.Regex.IsMatch(l, "[bcdfghjklmnpqrstvwxz]{6,}$");
        }

        /// <summary>One welcome-back line, or "" when the person has not been away long enough. seen(line) says whether it was used recently (it is avoided while a fresh one is left).</summary>
        public static string Pick(string name, int daysAway, string standing, Func<string, bool> seen, Random rnd, JObject extra = null)
        {
            string band = Band(daysAway); if (band == "" || string.IsNullOrWhiteSpace(name) || IsSpamLogin(name)) return "";
            var pool = new List<string>(Pools[band]); AddExtra(pool, extra, band);
            if (standing == "core" || standing == "regular") { pool.AddRange(Pools["warm"]); AddExtra(pool, extra, "warm"); }
            var all = pool.Select(t => t.Replace("{u}", name)).Distinct().ToList();
            var fresh = seen == null ? all : all.Where(t => !seen(t)).ToList(); if (fresh.Count == 0) fresh = all;
            return fresh[(rnd ?? new Random()).Next(fresh.Count)];
        }
        static readonly string[] ThanksPool = { "thanks {u}, that is a W.", "{u} with the gift, ggez, thank you!", "thank you {u}, the penguins approve." };
        /// <summary>A short thank-you line for {u} (a gift, raid or follow-style event). Never repeats while a fresh one is left.</summary>
        public static string Thanks(string name, Func<string, bool> seen, Random rnd)
        {
            var all = ThanksPool.Select(t => t.Replace("{u}", name)).ToList();
            var fresh = seen == null ? all : all.Where(t => !seen(t)).ToList(); if (fresh.Count == 0) fresh = all;
            return fresh[(rnd ?? new Random()).Next(fresh.Count)];
        }
        static void AddExtra(List<string> pool, JObject extra, string key)
        {
            var a = extra == null ? null : extra[key] as JArray; if (a == null) return;
            foreach (var t in a) { string s = (string)t; if (!string.IsNullOrWhiteSpace(s) && s.Contains("{u}") && s.Length < 200) pool.Add(s); }
        }
    }
}
