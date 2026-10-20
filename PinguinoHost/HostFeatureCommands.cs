using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Chat commands for the leaderboard / subscriber / watch-streak features. Their documentation is in PinguinoB0t/commands.json (what the website reads) and GET /api/commands-doc.
    /// VIEWERS (everyone): !emote name  !topemotes [month]  !commands  !topgifters  !topbits (!topbitters)  !topyappers  !topstreak (!topstreaks)  [month]   !leaderboards   !gifted [user]   !bits [user]   !sub [user]   !founders   !streak  !streakrecord (in Streaks)
    /// MODS only (anyone else is ignored): !alias add|remove|list   !boards refresh|status   !subs import|status   !streaks backfill|status   !names refresh   !lookup user
    /// A month is optional: oct, october, 2026-10, this, last (UTC); without it the all-time board is used.</summary>
    public static class FeatureCommands
    {
        const string Link = "https://innocentpenguin.com/leaderboards";
        static readonly Dictionary<string, DateTime> Cool = new Dictionary<string, DateTime>();
        static bool Cooling(string key, int sec) { if (sec <= 0) return false; lock (Cool) { DateTime t; if (Cool.TryGetValue(key, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; Cool[key] = DateTime.UtcNow; return false; } }
        static int CoolSec(string env, int d) { int v; return int.TryParse(Environment.GetEnvironmentVariable(env), out v) ? v : d; }

        static readonly string[] MonthNames = { "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec" };
        /// <summary>"oct" / "october" / "2026-10" / "this" / "last" -> "2026-10"; "" when the word is no month.</summary>
        public static string ParseMonth(string w)
        {
            w = (w ?? "").Trim().ToLowerInvariant(); if (w == "") return "";
            var now = DateTime.UtcNow;
            if (w == "this" || w == "thismonth" || w == "now") return now.ToString("yyyy-MM");
            if (w == "last" || w == "lastmonth" || w == "prev") return now.AddMonths(-1).ToString("yyyy-MM");
            if (Regex.IsMatch(w, @"^\d{4}-\d{2}$")) return w;
            for (int i = 0; i < 12; i++) if (w.Length >= 3 && (CultureInfo.InvariantCulture.DateTimeFormat.MonthNames[i].ToLowerInvariant() == w || MonthNames[i] == w || (w.Length >= 3 && CultureInfo.InvariantCulture.DateTimeFormat.MonthNames[i].ToLowerInvariant().StartsWith(w))))
            { int y = now.Year; if (i + 1 > now.Month) y--; return y + "-" + (i + 1).ToString("00"); }   // a month later in the year than now = last year's
            return "";
        }
        static string MonthLabel(string m) { DateTime t; return DateTime.TryParseExact(m + "-01", "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out t) ? t.ToString("MMM yyyy", CultureInfo.InvariantCulture) : m; }

        // board name -> (field in the all-time users map, key in a month, chat title, anchor)
        static readonly Dictionary<string, string[]> Boards_ = new Dictionary<string, string[]>
        {
            { "gifters", new[] { "gifts", "gifters", "Top gifters", "gifters", "subs gifted" } },
            { "bits", new[] { "bits", "bits", "Top bitters", "bits", "bits" } },
            { "yappers", new[] { "messages", "yappers", "Top yappers", "yappers", "messages" } },
            { "streaks", new[] { "streakBest", "streaks", "Top watch streaks (best shared)", "streaks", "streams" } } };

        static string BoardOf(string cmd)
        {
            switch (cmd) { case "!topgifters": case "!topgifter": return "gifters"; case "!topbits": case "!topbitters": case "!topbitter": return "bits"; case "!topyappers": case "!topyapper": return "yappers"; case "!topstreak": case "!topstreaks": return "streaks"; }
            return "";
        }
        static string Num(long n) { return n.ToString("N0", CultureInfo.InvariantCulture); }

        public static bool Handle(string user, string text, int role, Action<string> say)
        {
            var parts = (text ?? "").Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries); if (parts.Length == 0 || !parts[0].StartsWith("!")) return false;
            string cmd = parts[0].ToLowerInvariant(); string[] args = parts.Skip(1).ToArray(); string me = user.ToLowerInvariant();
            bool mod = role >= 3;
            if (Teach.IsCommand(cmd)) { Teach.Handle(user, cmd, args, role, say); return true; }
            string b = BoardOf(cmd);
            bool viewer = b != "" || cmd == "!leaderboards" || cmd == "!leaderboard" || cmd == "!gifted" || cmd == "!bits" || cmd == "!sub" || cmd == "!founders" || cmd == "!commands" || cmd == "!pm" || Emotes.IsCommand(cmd) || ChannelLore.IsCommand(cmd) || cmd == "!remindme" || cmd == "!reminders" || cmd == "!cancelreminder" || Economy.IsViewerCommand(cmd);
            bool modOnly = cmd == "!alias" || cmd == "!boards" || cmd == "!subs" || cmd == "!streaks" || cmd == "!names" || cmd == "!lookup" || Timers.IsCommand(cmd) || StreamTimers.IsCommand(cmd) || cmd == "!remind" || Economy.IsModCommand(cmd);
            if (!viewer && !modOnly) return false;
            if (modOnly && !mod) return false;                                            // mods only: everybody else gets nothing (the word may belong to another bot)
            if (viewer)
            {
                if (Cooling("g|" + cmd, CoolSec("PINGUINO_STREAK_COOL_GLOBAL", 8)) || Cooling("u|" + cmd + "|" + me, CoolSec("PINGUINO_STREAK_COOL_USER", 20))) return true;
            }
            try
            {
                if (b != "") { Top(b, args, say); return true; }
                if (Economy.IsViewerCommand(cmd) || Economy.IsModCommand(cmd)) { Economy.Handle(user, cmd, args, mod, say, ParseMonth, MonthLabel); return true; }
                if (Timers.IsCommand(cmd)) { Timers.Handle(args, say); return true; }
                if (StreamTimers.IsCommand(cmd)) { StreamTimers.Handle(cmd, args, say); return true; }
                if (cmd == "!remind" || cmd == "!remindme" || cmd == "!reminders" || cmd == "!cancelreminder") { Reminders.Handle(user, cmd, args, mod, say); return true; }
                if (ChannelLore.IsCommand(cmd) && !Economy.IsViewerCommand(cmd)) { ChannelLore.Handle(user, cmd, args, mod, say); return true; }
                if (Emotes.IsCommand(cmd)) { Emotes.Handle(user, cmd, args, say, ParseMonth, MonthLabel); return true; }
                switch (cmd)
                {
                    case "!pm": say(HostApi.PrivateMatchLine()); return true;
                    case "!commands": say("Every chat command, with search: https://innocentpenguin.com/help#commands"); return true;
                    case "!leaderboards": case "!leaderboard": say("Leaderboards (top gifters, bitters, yappers and watch streaks, all time or by month): " + Link); return true;
                    case "!gifted": Mine("gifters", me, args, say, user); return true;
                    case "!bits": Mine("bits", me, args, say, user); return true;
                    case "!sub": SubInfo(me, args, say, user); return true;
                    case "!founders": Founders(say); return true;
                    case "!alias": Alias(args, say); return true;
                    case "!boards": BoardsCmd(args, say); return true;
                    case "!subs": SubsCmd(args, say); return true;
                    case "!streaks": StreaksCmd(args, say); return true;
                    case "!names": NamesCmd(args, say); return true;
                    case "!lookup": Lookup(args, say); return true;
                }
            }
            catch (Exception ex) { Clog.Warn("commands", cmd + " failed: " + ex.Message); }
            return true;
        }

        static JObject Data() { return Boards.Api(); }

        // ---- viewers ----
        static void Top(string board, string[] args, Action<string> say)
        {
            var d = Data(); var def = Boards_[board]; string month = "";
            foreach (var a in args) { month = ParseMonth(a); if (month != "") break; }
            JArray list;
            if (month == "") list = (JArray)d["top"][def[0] == "streakBest" ? "streaks" : def[0] == "gifts" ? "gifts" : def[0]];
            else list = ((d["months"] as JObject)?[month]?[def[1]] as JArray) ?? new JArray();
            string when = month == "" ? "all time" : MonthLabel(month);
            if (month == "" && board == "streaks") when = "all time";
            string baseTitle = def[2].Replace(" (best shared)", "");
            string title = board == "streaks" ? (month == "" ? def[2] : baseTitle + " (" + when + ")") : baseTitle + " (" + when + ", " + def[4] + ")";
            if (list.Count == 0) { say("Nobody on the " + def[2].ToLowerInvariant().Replace(" (best shared)", "") + " board for " + when + " yet. " + Link + "#" + def[3]); return; }
            say(title + ": " + string.Join(" | ", list.Take(5).Select((x, i) => (i + 1) + ". " + (string)x["name"] + " " + Num((long)x["value"]))) + " - full list: " + Link + "#" + def[3]);
        }

        static List<KeyValuePair<string, JObject>> Ranked(JObject d, string field)
        {
            string ch = (string)d["streamerLogin"] ?? "";
            return ((JObject)d["users"]).Properties().Where(p => p.Name != ch && (int)p.Value[field] > 0).OrderByDescending(p => (int)p.Value[field]).ThenBy(p => p.Name, StringComparer.Ordinal).Select(p => new KeyValuePair<string, JObject>(p.Name, (JObject)p.Value)).ToList();
        }
        static void Mine(string board, string me, string[] args, Action<string> say, string display)
        {
            var d = Data(); var def = Boards_[board]; string who = args.Length > 0 ? args[0].TrimStart('@').ToLowerInvariant() : me; bool self = who == me;
            who = Boards.CanonLogin(who); string label = self ? "@" + display + " you have" : who + " has";
            var rank = Ranked(d, def[0]); int pos = rank.FindIndex(k => k.Key == who);
            var u = ((JObject)d["users"])[who] as JObject; string nm = u != null ? (string)u["name"] : who;
            if (pos < 0) { say(self ? "@" + display + " I have no " + (board == "gifters" ? "gifted subs" : "bits") + " recorded for you yet. " + Link + "#" + def[3] : "No " + (board == "gifters" ? "gifted subs" : "bits") + " recorded for " + who + " yet."); return; }
            string extra = board == "bits" && (int)u["bitsBadge"] > 0 ? ", bits badge " + Num((int)u["bitsBadge"]) : "";
            say((self ? "@" + display + " you have " : nm + " has ") + (board == "gifters" ? "gifted " + Num((int)u["gifts"]) + " sub" + ((int)u["gifts"] == 1 ? "" : "s") : "cheered " + Num((int)u["bits"]) + " bits") + extra + " - rank #" + (pos + 1) + " of " + rank.Count + ". " + Link + "#" + def[3]);
        }
        static void SubInfo(string me, string[] args, Action<string> say, string display)
        {
            string who = args.Length > 0 ? args[0].TrimStart('@').ToLowerInvariant() : me; bool self = who == me; who = Boards.CanonLogin(who);
            var u = SubsImport.UserInfo(who);
            if (u == null) { say(self ? "@" + display + " I don't have a subscription on record for you (the list is imported from Twitch's subscriber export, so a brand-new sub can take a while)." : "No subscription on record for " + who + "."); return; }
            bool lapsed = (bool?)u["lapsed"] == true; bool founder = (bool?)u["founder"] == true;
            int tier = (int?)u["tier"] ?? 0, ten = (int?)u["tenure"] ?? 0, stk = (int?)u["streak"] ?? 0;
            string body = tier > 0 ? "a Tier " + tier + " subscriber for " + ten + " month" + (ten == 1 ? "" : "s") + (stk > 1 ? " (" + stk + " in a row)" : "") + (founder ? ", Founder" : "") + (lapsed ? " - not subscribed right now" : "")
                                   : "a Founder (Twitch Founders Badge)";
            say((self ? "@" + display + " you're " : who + " is ") + body + ".");
        }
        static void Founders(Action<string> say)
        {
            var f = SubsImport.FoundersList(); if (f.Count == 0) { say("No founders on record yet."); return; }
            say(f.Count + " Founders (Twitch Founders Badge): " + string.Join(", ", f.Select(x => x.Value) ) + ".");
        }

        // ---- mods ----
        static void Alias(string[] a, Action<string> say)
        {
            string sub = a.Length > 0 ? a[0].ToLowerInvariant() : "list";
            if (sub == "list") { var m = Boards.AliasMap(); say(m.Count == 0 ? "No aliases yet. !alias add <old login> <main login>" : "Aliases (" + m.Count + "): " + string.Join(", ", m.Take(25).Select(kv => kv.Key + " > " + kv.Value)) + (m.Count > 25 ? " ..." : "")); return; }
            if (sub == "add" && a.Length >= 3) { say(Boards.AliasAdd(a[1], a[2])); return; }
            if ((sub == "remove" || sub == "del" || sub == "delete") && a.Length >= 2) { say(Boards.AliasRemove(a[1])); return; }
            say("Usage: !alias add <old login> <main login> | !alias remove <old login> | !alias list");
        }
        static void BoardsCmd(string[] a, Action<string> say)
        {
            string sub = a.Length > 0 ? a[0].ToLowerInvariant() : "status";
            if (sub == "refresh")
            {
                Task.Run(() => { try { var r = Boards.Refresh(true); say("Boards recomputed (" + ((JObject)r["users"]).Count + " people) - " + Boards.PushNote()); } catch (Exception ex) { say("Boards refresh failed: " + ex.Message); } });
                say("Recomputing the boards and pushing them to the site..."); return;
            }
            var d = Data(); say("Boards: " + ((JObject)d["users"]).Count + " people, " + ((JObject)d["months"]).Count + " months. Last push: " + Boards.PushNote());
        }
        static void SubsCmd(string[] a, Action<string> say)
        {
            string sub = a.Length > 0 ? a[0].ToLowerInvariant() : "status";
            if (sub == "import")
            {
                var r = SubsImport.ScanAndImport(); var imp = (JArray)r["imported"];
                say(imp.Count == 0 ? "No new subscriber-list file found (looked in Downloads and Data\\subs\\incoming). " + (int)r["users"] + " subscribers on record." : "Imported " + imp.Count + " file(s): " + string.Join("; ", imp.Select(x => (string)x["file"] + " " + (x["error"] != null ? "ERROR " + (string)x["error"] : "+" + (int)x["added"] + " new, " + (int)x["updated"] + " updated, " + (int)x["lapsed"] + " lapsed"))));
                return;
            }
            var s = SubsImport.Api(); say("Subscribers on record: " + (int)s["active"] + " active (T1 " + (int)s["tiers"]["t1"] + ", T2 " + (int)s["tiers"]["t2"] + ", T3 " + (int)s["tiers"]["t3"] + "), " + (int)s["lapsed"] + " lapsed, " + ((JObject)s["founders"]).Count + " founders. Files imported: " + (int)s["files"] + ".");
        }
        static void StreaksCmd(string[] a, Action<string> say)
        {
            string sub = a.Length > 0 ? a[0].ToLowerInvariant() : "status";
            if (sub == "backfill") { var r = Streaks.Backfill(); say("Streak backfill: " + (int)r["filesScanned"] + " log files, " + (int)r["added"] + " new shares, " + (int)r["duplicates"] + " duplicates, " + (int)r["people"] + " people."); return; }
            var s = Streaks.Api(); say("Watch streaks: " + (int)s["people"] + " people have shared one. Backfilled: " + (((string)s["backfilledAt"] ?? "") == "" ? "never" : (string)s["backfilledAt"]) + ".");
        }
        static void NamesCmd(string[] a, Action<string> say)
        {
            if ((a.Length > 0 ? a[0].ToLowerInvariant() : "") != "refresh") { say("Usage: !names refresh (asks Twitch again for everyone's display name)"); return; }
            Boards.NamesReset(); Task.Run(() => { try { Boards.Refresh(true); say("Display names refreshed from Twitch."); } catch (Exception ex) { say("Names refresh failed: " + ex.Message); } });
            say("Asking Twitch for display names again...");
        }
        static void Lookup(string[] a, Action<string> say)
        {
            if (a.Length == 0) { say("Usage: !lookup <user>"); return; }
            string who = a[0].TrimStart('@').ToLowerInvariant(); string main = Boards.CanonLogin(who); var d = Data(); var u = ((JObject)d["users"])[main] as JObject; var sub = SubsImport.UserInfo(main);
            if (u == null && sub == null) { say("Nothing on record for " + who + "."); return; }
            var aka = u?["aka"] as JArray; string head = (u != null ? (string)u["name"] : main) + " (" + main + (who != main ? ", you typed an alias" : "") + (aka != null && aka.Count > 0 ? "; also " + string.Join(", ", aka.Select(x => (string)x)) : "") + ")";
            string s = sub == null ? "no sub on record" : "T" + (int?)sub["tier"] + " " + (int?)sub["tenure"] + "mo" + ((bool?)sub["founder"] == true ? " founder" : "") + ((bool?)sub["lapsed"] == true ? " lapsed" : "");
            say(head + ": " + s + " | gifts " + (u == null ? 0 : (int)u["gifts"]) + " | bits " + (u == null ? 0 : (int)u["bits"]) + (u != null && (int)u["bitsBadge"] > 0 ? " (badge " + (int)u["bitsBadge"] + ")" : "") + " | messages " + Num(u == null ? 0 : (int)u["messages"]) + " | watch streak best " + (u == null ? 0 : (int)u["streakBest"]) + ", last " + (u == null ? 0 : (int)u["streakCurrent"]));
        }

        // ---- the documentation: GET /api/commands-doc ----
        /// <summary>PinguinoB0t/commands.json (the file the website reads) split into viewer and mod commands, plus the generation time. Same entries: command, aliases, action, category, who, usage, description, examples.</summary>
        public static JObject Doc()
        {
            string f = Path.Combine(Program.SuiteDir ?? "", "PinguinoB0t", "commands.json");
            JObject src; try { src = SubsImport.ParseJ(File.ReadAllText(f)); } catch (Exception ex) { return new JObject { { "ok", false }, { "error", "commands.json: " + ex.Message } }; }
            var all = (src["commands"] as JArray) ?? new JArray();
            Func<JToken, string> who = c => ((string)c["who"] ?? "").ToLowerInvariant();
            var viewer = new JArray(all.Where(c => who(c).Contains("everyone") || who(c) == "automatic").Select(Norm)); var chan = ChannelLore.DocRows(); foreach (var r in chan) { viewer.Add(r); } var mod = new JArray(all.Where(c => who(c).Contains("mod")).Select(Norm));
            return new JObject { { "ok", true }, { "version", src["version"] }, { "updated", src["updated"] }, { "viewer", viewer }, { "mod", mod }, { "all", new JArray(all.Concat(chan)) }, { "counts", new JObject { { "viewer", viewer.Count }, { "mod", mod.Count }, { "channel", chan.Count } } } };
        }
        static JToken Norm(JToken c) { var o = (JObject)c.DeepClone(); string w = ((string)o["who"] ?? "").ToLowerInvariant(); o["permission"] = w.Contains("everyone") && w.Contains("mod") ? "everyone (mods can do more)" : w.Contains("mod") ? "mods" : w.Contains("everyone") ? "everyone" : w; return o; }
    }
}
