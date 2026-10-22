using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Feeds the Core's wheel team-line emojis: Data\wheel_emoji.json {login:{i:[emoji],g:"emoji"}}.
    /// i = emojis derived from known interests (private lore cards). Only a SAFE allowlist of topics maps to an emoji and ONLY the emoji is stored, never the text.
    /// People who typed !optmeout / !forgetme get no interests. g = a GPT guess from the public username alone (nothing private is sent). Cached, short timeout.</summary>
    public static class WheelEmoji
    {
        static readonly string[][] Topics = {
            new[]{"rocket league|rl|spike rush|tourney|tourneys","🚀"}, new[]{"minecraft","⛏️"}, new[]{"fortnite","🪂"}, new[]{"valorant","🎯"}, new[]{"zelda","🗡️"}, new[]{"pokemon","⚡"}, new[]{"mario","🍄"},
            new[]{"ksp|kerbal|space","🛰️"}, new[]{"music|noah kahan|brent|sea shanties|shanties|guitar|piano|band|rap|song","🎵"}, new[]{"curry","🍛"}, new[]{"pizza","🍕"}, new[]{"sushi","🍣"}, new[]{"burger","🍔"},
            new[]{"coffee","☕"}, new[]{"tea","🍵"}, new[]{"cookie","🍪"}, new[]{"cake|dessert","🍰"}, new[]{"taco","🌮"}, new[]{"ramen|noodle","🍜"}, new[]{"cat|cats|kitty","🐱"}, new[]{"dog|dogs|puppy","🐶"}, new[]{"penguin","🐧"},
            new[]{"fish|fishing","🎣"}, new[]{"speed build|building|builds","🧱"}, new[]{"art|drawing|draw","🎨"}, new[]{"anime","🍥"}, new[]{"movie|film","🎬"}, new[]{"gym|lifting","🏋️"}, new[]{"hiking|camping","🏕️"},
            new[]{"soccer|football","⚽"}, new[]{"basketball","🏀"}, new[]{"chess","♟️"}, new[]{"cars|car|racing","🏎️"}, new[]{"plants|garden","🪴"}, new[]{"sea|ocean|beach","🌊"}, new[]{"snow|winter","❄️"}, new[]{"neural|ai|robot","🤖"}
        };
        // never turned into anything: personal or sensitive subjects
        static readonly Regex Skip = new Regex(@"health|sick|ill|disease|mental|therap|depress|anxiet|family|mom|dad|mother|father|brother|sister|wife|husband|girlfriend|boyfriend|kid|child|baby|home|address|city|country|state|school|job|work|money|religio|politic|sex|booty|latina|drug|alcohol|beer|vape|smok", RegexOptions.IgnoreCase);
        static readonly object L = new object();
        static DateTime _last = DateTime.MinValue;
        static string F { get { return Path.Combine(HostApi.DataDir, "wheel_emoji.json"); } }

        public static void Start()
        {
            var t = new Thread(() => { Thread.Sleep(20000); while (true) { try { Tick(); } catch (Exception ex) { Clog.Warn("wheel-emoji", ex.Message); } Thread.Sleep(15000); } }) { IsBackground = true };
            t.Start();
        }

        static string CardDir()
        {
            foreach (var d in new[] { Path.Combine(HostApi.DataDir, "lore", "person_cards"), Path.Combine(HostApi.DataDir, "..", "lore", "person_cards") }) if (Directory.Exists(d)) return d;
            return null;
        }

        public static List<string> Interests(string login)
        {
            var res = new List<string>(); string dir = CardDir(); if (dir == null || Boards.IsAnon(login)) return res;
            try
            {
                string f = Path.Combine(dir, login + ".json"); if (!File.Exists(f)) return res;
                var card = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF));
                foreach (var like in (card["likes"] as JArray ?? new JArray()).Select(x => ((string)x ?? "").ToLowerInvariant()))
                {
                    if (like == "" || Skip.IsMatch(like)) continue;
                    foreach (var tp in Topics) if (tp[0].Split('|').Any(k => Regex.IsMatch(like, @"(^|[^a-z])" + Regex.Escape(k) + @"([^a-z]|$)"))) { if (!res.Contains(tp[1])) res.Add(tp[1]); break; }
                }
            }
            catch (Exception) { }
            return res;
        }

        static bool IsEmoji(string s) { return !string.IsNullOrEmpty(s) && s.Length <= 8 && s.Any(ch => char.IsSurrogate(ch) || ch > 0x2000) && !s.Any(char.IsLetterOrDigit); }

        static string Guess(string name)
        {
            if (HostApi.SimMode) return null;
            try
            {
                string a = Gpt.Ask("You pick ONE plain Unicode emoji (no text, no Twitch emotes) that fits a Twitch username. Reply with only the emoji, or NONE if nothing fits.", "Username: " + name);
                if (a == null) return null; a = a.Trim();
                return IsEmoji(a) ? a : null;
            }
            catch (Exception) { return null; }
        }

        static void Tick()
        {
            var logins = new List<string>();
            foreach (var d in new[] { HostApi.DataDir, Path.Combine(HostApi.DataDir, "runtime") })
            {
                try { string f = Path.Combine(d, "wheel_session.json"); if (!File.Exists(f)) continue; var ses = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); foreach (var e in (ses["Entrants"] as JArray ?? new JArray())) { string l = ((string)e["Login"] ?? "").ToLowerInvariant(); if (l != "") logins.Add(l); } break; } catch (Exception) { }
            }
            if (logins.Count == 0) return;
            JObject cache; lock (L) { try { cache = File.Exists(F) ? JObject.Parse(File.ReadAllText(F).TrimStart((char)0xFEFF)) : new JObject(); } catch (Exception) { cache = new JObject(); } }
            int n = 0; bool changed = false;
            foreach (var l in logins.Distinct())
            {
                var c = cache[l] as JObject;
                if (c != null && (DateTime.UtcNow - DateTimeOffset.FromUnixTimeSeconds((long?)c["at"] ?? 0).UtcDateTime).TotalHours < 6) continue;
                if (n++ >= 8) break;
                var o = new JObject { { "i", new JArray(Interests(l)) }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } };
                string g = (c != null ? (string)c["g"] : null) ?? (Boards.IsAnon(l) ? null : Guess(l)); if (g != null) o["g"] = g;
                cache[l] = o; changed = true;
            }
            if (changed) lock (L) { try { string tmp = F + ".tmp"; File.WriteAllText(tmp, cache.ToString(), new System.Text.UTF8Encoding(false)); if (File.Exists(F)) File.Delete(F); File.Move(tmp, F); } catch (Exception) { } }
        }
    }
}
