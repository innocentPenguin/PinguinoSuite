using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Self-timeout reward, redemption status (auto-complete / refund), the timeout event log and the context fed to Chatty's GPT lines.</summary>
    public static partial class TimeoutReward
    {
        public static void OnRedeem(Dictionary<string, object> args)
        {
            object t; if (!args.TryGetValue("title", out t)) return;
            var cfg = Config(); if ((bool?)cfg["enabled"] == false) return;
            string title = Convert.ToString(t) ?? "";
            bool other = string.Equals(title, (string)cfg["title"] ?? "Timeout", StringComparison.OrdinalIgnoreCase), self = string.Equals(title, (string)cfg["selfTitle"] ?? "Self Timeout", StringComparison.OrdinalIgnoreCase);
            if (!other && !self) return;
            string who = Convert.ToString(args.ContainsKey("userName") ? args["userName"] : ""), typed = Convert.ToString(args.ContainsKey("input") ? args["input"] : "");
            string rid = Convert.ToString(args.ContainsKey("redemptionId") ? args["redemptionId"] : ""), rw = Convert.ToString(args.ContainsKey("rewardId") ? args["rewardId"] : "");
            Task.Run(() => { try { if (self) HandleSelf(cfg, who, typed, rid, rw); else Handle(cfg, who, typed, rid, rw); } catch (Exception ex) { Clog.Warn("timeout-reward", "failed: " + ex.Message); } });
        }

        // ------------------------------------------------------------------ redemption status
        static void Refund(JObject cfg, string rid, string rw) { if (Sim) Out("redemption canceled (refund)"); else if ((bool?)cfg["refund"] != false && rid != "") Redeems.Cancel(rid, rw); }
        static void Complete(JObject cfg, string rid, string rw) { if (Sim) Out("redemption fulfilled"); else if ((bool?)cfg["autoComplete"] != false && rid != "") Redeems.Fulfill(rid, rw); }
        static List<string> Actors(JObject cfg) { var a = (cfg["actors"] as JArray ?? new JArray()).Select(x => (string)x).ToList(); return a.Count == 0 ? new List<string> { "helper", "core", "streamer" } : a; }

        // ------------------------------------------------------------------ self timeout
        static readonly Regex DurRx = new Regex(@"(\d+(?:[.,]\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)?(?![a-z])", RegexOptions.IgnoreCase);
        /// <summary>Seconds from free text: the first number wins, a bare number is seconds, units s/sec/m/min/h/hour. Exactly "1" (no unit) is a coin flip between 1 and 60 s
        /// (note says which). Over maxSec becomes exactly maxSec. No number: defSec.</summary>
        public static int ParseDuration(string text, int defSec, int maxSec, Func<bool> coin, out string note)
        {
            note = ""; text = (text ?? "").Trim();
            if (text == "1") { bool one = coin(); note = "You didn't say secs or mins so I chose " + (one ? "1 second" : "60 seconds") + " \U0001F603"; return one ? 1 : 60; }
            var m = DurRx.Match(text); double n;
            if (!m.Success || !double.TryParse(m.Groups[1].Value.Replace(',', '.'), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out n)) return Math.Min(defSec, maxSec);
            string u = m.Groups[2].Value.ToLowerInvariant(); double mult = u == "" || u.StartsWith("s") ? 1 : u.StartsWith("m") ? 60 : 3600;
            double secs = n * mult; if (secs < 1) secs = 1; if (secs > maxSec) return maxSec; return (int)Math.Round(secs);
        }

        public static string HandleSelf(JObject cfg, string redeemer, string typed, string redemptionId, string rewardId)
        {
            string rlogin = Norm(redeemer); var roster = Roster.Recent(24);
            var me = roster.FirstOrDefault(r => r.Item1 == rlogin); string rname = me?.Item2 ?? redeemer; int role = me?.Item3 ?? 1;
            if (role >= 3 || Boards.IsBot(rlogin) || Boards.AllBots().Contains(rlogin) || IsLiveMod(rlogin)) { Refund(cfg, redemptionId, rewardId); return Done("self timeout refused for " + rlogin + " (mod/broadcaster/bot), refunded"); }
            string note; int secs = ParseDuration(typed, (int?)cfg["selfDefaultSec"] ?? 60, (int?)cfg["selfMaxSec"] ?? 300, () => Rnd.Next(2) == 0, out note);
            string reason = "You timed yourself out!" + (note != "" ? " " + note : "");
            var ai = Task.Run(() => AiLine(cfg, "self", rname, rname, secs, typed));
            Wait(1000, 5000);
            string by = Ban(Actors(cfg), rlogin, secs, reason);
            if (by == null) { Refund(cfg, redemptionId, rewardId); return Done("could not time out " + rlogin + " (self), refunded"); }
            LogEvent("self", rlogin, rlogin, secs, (string)cfg["selfTitle"], by);
            Complete(cfg, redemptionId, rewardId);
            Thread.Sleep(Sim ? 10 : 1000);
            ChattySay(Pick(ai, cfg, rname + " needs a break from us! D:", rname, rname));
            return Done("self timed out " + rlogin + " " + secs + " s via " + by);
        }

        static string Pick(Task<string> ai, JObject cfg, string plain, string mustA, string mustB)
        {
            string l = null; try { if (ai.Wait(((int?)cfg["aiWaitSec"] ?? 6) * 1000)) l = ai.Result; } catch (Exception) { }
            string pick = plain;
            if (l != null) { string ll = l.ToLowerInvariant(); if (ll.Contains(mustA.ToLowerInvariant()) && ll.Contains(mustB.ToLowerInvariant())) pick = l; }
            lock (_lines) { _lines.Add(pick); while (_lines.Count > 12) _lines.RemoveAt(0); }
            return pick;
        }

        // ------------------------------------------------------------------ event log + context
        static string EvPath { get { return Path.Combine(HostApi.DataDir, "timeout_events.jsonl"); } }
        /// <summary>one line per timeout: kind self|timeout|blunder, by (who redeemed), target (who was timed out), secs, reward title, actor.</summary>
        public static void LogEvent(string kind, string by, string target, int secs, string reward, string actor)
        {
            try { lock (L) File.AppendAllText(EvPath, new JObject { { "ts", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "kind", kind }, { "by", by }, { "target", target }, { "secs", secs }, { "reward", reward }, { "actor", actor } }.ToString(Newtonsoft.Json.Formatting.None) + "\n", new UTF8Encoding(false)); } catch (Exception) { }
        }
        /// <summary>earlier timeout events involving either person (oldest first) as short sentences</summary>
        public static List<string> History(string a, string b, int max)
        {
            var res = new List<string>(); a = Norm(a); b = Norm(b);
            try
            {
                if (!File.Exists(EvPath)) return res;
                foreach (var l in File.ReadAllLines(EvPath).Reverse().Take(400))
                {
                    JObject o; try { o = JObject.Parse(l); } catch (Exception) { continue; }
                    string by = (string)o["by"] ?? "", tg = (string)o["target"] ?? "", kind = (string)o["kind"] ?? "";
                    if (by != a && by != b && tg != a && tg != b) continue;
                    long age = DateTimeOffset.UtcNow.ToUnixTimeSeconds() - (long)(o["ts"] ?? 0);
                    string when = age < 3600 ? (age / 60) + " min ago" : age < 172800 ? (age / 3600) + " h ago" : (age / 86400) + " days ago";
                    res.Add(kind == "self" ? by + " timed themselves out for " + o["secs"] + " s (" + when + ")" : kind == "blunder" ? by + " tried to time out a mod (" + tg + ") and got timed out instead (" + when + ")" : by + " timed out " + tg + " for " + o["secs"] + " s (" + when + ")");
                    if (res.Count >= max) break;
                }
            }
            catch (Exception) { }
            res.Reverse(); return res;
        }
        /// <summary>recent chat lines by the given people, then the last few lines of the room, from the live chat log (today, else yesterday)</summary>
        public static List<string> ChatContext(string a, string b, int perUser, int room)
        {
            var res = new List<string>(); a = Norm(a); b = Norm(b);
            try
            {
                foreach (var day in new[] { DateTime.Now, DateTime.Now.AddDays(-1) })
                {
                    string f = Path.Combine(HostApi.DataDir, "chat_logs", day.ToString("yyyy-MM-dd") + ".jsonl"); if (!File.Exists(f)) continue;
                    var parsed = new List<Tuple<string, string>>();
                    using (var fs = new FileStream(f, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    {
                        fs.Seek(-Math.Min(fs.Length, 120000), SeekOrigin.End);
                        using (var r = new StreamReader(fs, Encoding.UTF8)) { string x; while ((x = r.ReadLine()) != null) { try { var o = JObject.Parse(x); parsed.Add(Tuple.Create(((string)o["u"] ?? "").ToLowerInvariant(), Clip((string)o["m"] ?? "", 90))); } catch (Exception) { } } }
                    }
                    if (parsed.Count == 0) continue;
                    var mine = parsed.Where(p => p.Item1 == a || p.Item1 == b).Reverse().Take(perUser * 2).Reverse();
                    var tail = parsed.Skip(Math.Max(0, parsed.Count - room));
                    foreach (var p in mine.Concat(tail).Distinct()) res.Add(p.Item1 + ": " + p.Item2);
                    break;
                }
            }
            catch (Exception) { }
            return res;
        }

        // ------------------------------------------------------------------ Chatty's personalised line
        /// <summary>kind: valid (a timeout landed on target, redeemed by redeemer) | blunder (redeemer tried a protected target and was timed out) | self. null when the AI is off, slow or unusable.</summary>
        static string AiLine(JObject cfg, string kind, string redeemer, string target, int secs, string typed)
        {
            if ((bool?)cfg["ai"] == false || Sim) return null;
            try
            {
                List<string> recent; lock (_lines) recent = _lines.ToList();
                var chat = ChatContext(redeemer, target, 4, 6); var hist = History(redeemer, target, 6);
                string sys = "You are ChattyPinguino, a cheeky, playful penguin in a Twitch chat. Write ONE short line (under 15 words, no quotes, no hashtags, at most one emoji) reacting to a timeout. Be playful, never mean or insulting. "
                    + "Use the chat context and past timeouts only if they make the joke land (someone arguing, spamming, being cheeky, a rematch between the same two people). Never reuse wording of these earlier lines: " + (recent.Count == 0 ? "(none)" : string.Join(" | ", recent)) + ". Output only the line.";
                string what = kind == "self" ? redeemer + " spent channel points to time themselves out for " + secs + " s" + (typed != "" ? " (they typed: " + Clip(typed, 40) + ")" : "") + ". Mention " + redeemer + " by name."
                    : kind == "blunder" ? redeemer + " spent channel points to time out " + target + ", but " + target + " is protected, so " + redeemer + " got timed out instead. Mention " + redeemer + " by name."
                    : redeemer + " spent channel points to time out " + target + " for " + secs + " s and it worked. Mention both " + redeemer + " and " + target + " by name.";
                string usr = what + "\nRecent chat (oldest first):\n" + (chat.Count == 0 ? "(nothing)" : string.Join("\n", chat)) + "\nPrevious timeouts involving them:\n" + (hist.Count == 0 ? "(none)" : string.Join("\n", hist));
                for (int i = 0; i < 2; i++)
                {
                    string l = Gpt.Ask(sys, usr + (i > 0 ? "\n(Be different and shorter.)" : "")); if (l == null) return null;
                    l = Regex.Replace(l.Trim().Trim('"'), @"\s+", " ");
                    if (l == "" || l.Length > 120 || Words(l) >= 15 || Seen(l)) continue;
                    return l;
                }
            }
            catch (Exception ex) { Clog.Warn("timeout-reward", "AI line failed: " + ex.Message); }
            return null;
        }
        static int Words(string s) { return Regex.Matches(s ?? "", @"\S+").Count; }
        static bool Seen(string l) { string n = Norm(l); lock (_lines) return _lines.Any(x => Norm(x) == n); }
    }
}
