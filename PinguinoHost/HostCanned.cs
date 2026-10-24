using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Editor backend for ChattyPinguino's canned commands (PinguinoChat\canned_commands.json, the same file Chatty reloads when it changes): list, change the text / choices /
    /// aliases, turn one on or off, add a new one, and a test line that renders $(user) $(touser) $(luck) without sending anything to chat. Loopback only (the routes refuse anything else).
    /// Delete is allowed (Ivan asked for it); every save, delete included, keeps the previous file as canned_commands.json.bak.</summary>
    public static class CannedEditor
    {
        static readonly object L = new object();
        static readonly Random Rng = new Random();
        // names that belong to real commands (mods, the Host, the games): a joke can never take them over
        static readonly HashSet<string> Reserved = new HashSet<string> { "ban", "unban", "timeout", "untimeout", "title", "game", "poll", "predict", "lock", "resolve", "cancel", "slow", "followers", "announce", "allow", "shield", "marker", "ad", "vip", "unvip", "confirm", "unraid",
            "chatbot", "golive", "opinion", "teach", "setrank", "rank", "commands", "command", "cmds", "cmd", "join", "leave", "queue", "next", "win", "me", "points", "gamble", "shop", "pg", "offlinemode", "forgetme", "optmeout", "8ball" };

        static string PathOf() { return ChannelLore.CannedPath(); }

        static JObject Read()
        {
            string p = PathOf();
            if (!File.Exists(p)) return new JObject { { "cooldownSec", 20 }, { "commands", new JArray() } };
            var r = JObject.Parse(File.ReadAllText(p, Encoding.UTF8).TrimStart((char)0xFEFF));
            if (!(r["commands"] is JArray)) r["commands"] = new JArray();
            return r;
        }

        static void Write(JObject root)
        {
            string p = PathOf(); string tmp = p + ".tmp";
            File.WriteAllText(tmp, root.ToString(), new UTF8Encoding(false));
            if (File.Exists(p)) File.Copy(p, p + ".bak", true);
            File.Copy(tmp, p, true); File.Delete(tmp);   // Chatty and the Host notice the new write time on their next look (about 4 s)
        }

        /// <summary>true when the name is taken by a real command: the fixed list above or anything the Host's own modules answer to (control, emotes, alerts, gambling)</summary>
        static bool HostOwns(string n)
        {
            if (Reserved.Contains(n)) return true;
            string b = "!" + n;
            try { return Control.IsCommand(b) || Emotes.IsCommand(b) || AlertBridge.IsCommand(b) || Gamble.IsCommand(b); } catch (Exception) { return false; }
        }

        /// <summary>everything the Suite page needs to build its editor in one read: the commands as stored (name, aliases, text, choices, enabled), the cooldown, the allowed variables and the rules</summary>
        public static JObject Export()
        {
            lock (L)
            {
                try
                {
                    var r = Read();
                    return new JObject { { "ok", true }, { "version", 1 }, { "exportedAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "cooldownSec", (int?)r["cooldownSec"] ?? 20 },
                        { "variables", new JArray("$(user)", "$(touser)", "$(luck)", "$(games)", "$(count)", "$(link:<name>)") },
                        { "rules", new JObject { { "name", "1-24 letters, digits or _" }, { "maxTextLength", 400 }, { "oneLine", true }, { "noControlCharacters", true }, { "reservedNames", new JArray(Reserved.OrderBy(x => x)) } } },
                        { "commands", new JArray(r["commands"].OfType<JObject>().Select(c => (JToken)c.DeepClone())) } };
                }
                catch (Exception ex) { return Err("could not read the canned commands: " + ex.Message); }
            }
        }

        static JObject Err(string e) { return new JObject { { "ok", false }, { "error", e } }; }
        static string CleanName(string n) { n = (n ?? "").Trim().TrimStart('!').ToLowerInvariant(); return Regex.IsMatch(n, "^[a-z0-9_]{1,24}$") ? n : ""; }

        /// <summary>null = fine, else why the text cannot be used</summary>
        static string BadText(string t)
        {
            if (string.IsNullOrWhiteSpace(t)) return "the text is empty";
            if (t.Length > 400) return "the text is longer than 400 characters (Twitch chat limit is 500 with the name)";
            if (t.IndexOfAny(new[] { '\r', '\n' }) >= 0) return "the text must be one line";
            if (t.Any(ch => char.IsControl(ch))) return "the text cannot contain control characters";
            string s = t.TrimStart();
            if (s.StartsWith("/") || s.StartsWith(".") || s.StartsWith("!")) return "the text cannot start with / . or ! (that would run a Twitch or bot command)";
            foreach (Match lm in Regex.Matches(t, @"\$\(link:([^)]*)\)")) if (!Regex.IsMatch(lm.Groups[1].Value, "^[a-z0-9_]+$") || Links.Get(lm.Groups[1].Value) == null) return "$(link:" + lm.Groups[1].Value + ") is not a known link (known: " + string.Join(", ", ((JObject)Links.Doc()["links"]).Properties().Select(x => x.Name)) + ")";
            if (Regex.IsMatch(Regex.Replace(t, @"\$\(link:[a-z0-9_]+\)", ""), @"\$\((?!user\)|touser\)|luck\)|games\)|count\))")) return "only $(user), $(touser), $(luck), $(games), $(count) and $(link:name) can be used";
            return null;
        }

                // ---- mod-made plain commands (!addcom / !editcom / !delcom): stored in the SAME canned_commands.json as entries with "custom": true, served by Chatty's canned path ----
        static readonly HashSet<string> CustomExtraReserved = new HashSet<string> { "addcom", "editcom", "delcom", "song", "vol", "songqueue", "voteskip", "skip", "help", "helper", "emote", "topemotes", "remindme", "reminders", "notme", "alias", "boards", "lookup", "names", "streaks", "subs",
            "leaderboards", "leaderboard", "gifted", "bits", "sub", "founders", "pm", "pmrules", "lore", "rules", "discord", "guess", "confirm", "raid", "vanish", "disappear", "countdown", "stopwatch", "timer", "timers", "remind", "alert", "alerts", "top", "leaders", "watchtime", "tip" };
        public static bool IsCustomCommand(string cmd) { return cmd == "!addcom" || cmd == "!editcom" || cmd == "!delcom"; }
        /// <summary>true when a real command already answers to this name: the fixed lists, the Host's modules, every non-canned entry of the command registry (built-ins, Helper, Host)</summary>
        static bool CustomCollides(string n)
        {
            if (HostOwns(n) || CustomExtraReserved.Contains(n)) return true;
            string b = "!" + n;
            try { if (Economy.IsViewerCommand(b) || Economy.IsModCommand(b) || Economy.IsBankCommand(b) || Economy.IsHiddenCommand(b) || Timers.IsCommand(b) || StreamTimers.IsCommand(b) || Teach.IsCommand(b) || Vanish.IsCommand(b) || SubTickets.IsModCommand(b) || Reminders.IsCommand(b) || Rank.IsCommand(b)) return true; } catch (Exception) { }
            try { if (ChannelLore.IsCommand(b) && !ChannelLore.ChattyOwns(b)) return true; } catch (Exception) { }
            try
            {
                foreach (var x in (CmdProfiles.All()["commands"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    if ((string)x["source"] == "canned") continue;
                    if (string.Equals(((string)x["id"] ?? "").TrimStart('!'), n, StringComparison.OrdinalIgnoreCase)) return true;
                    foreach (var al in x["aliases"] as JArray ?? new JArray()) if (string.Equals(((string)al ?? "").TrimStart('!'), n, StringComparison.OrdinalIgnoreCase)) return true;
                }
            }
            catch (Exception) { }
            return false;
        }
        /// <summary>null = fine; only $(user) $(touser) $(count) $(link:key) are allowed in a mod-made command</summary>
        static string CustomBadText(string t)
        {
            string bad = BadText(t); if (bad != null) return bad;
            if (Regex.IsMatch(Regex.Replace(t, @"\$\(link:[a-z0-9_]+\)", ""), @"\$\((?!user\)|touser\)|count\))")) return "only $(user), $(touser), $(count) and $(link:name) can be used";
            return null;
        }
        /// <summary>!addcom !name text / !editcom !name new text / !delcom !name. Mods and the broadcaster only (everyone else: nothing). One reply line to the mod.</summary>
        public static void CustomHandle(string user, string cmd, string[] args, int role, Action<string> say)
        {
            if (role < 3) return;
            string at = "@" + user + " ";
            string name = args != null && args.Length > 0 ? CleanName(args[0]) : "";
            string text = args != null && args.Length > 1 ? string.Join(" ", args.Skip(1)).Trim() : "";
            string usage = cmd == "!addcom" ? "use: !addcom !name text" : cmd == "!editcom" ? "use: !editcom !name new text" : "use: !delcom !name";
            if (name == "") { say(at + (args != null && args.Length > 0 ? "the name must be 1-24 letters, digits or _." : usage + ".")); return; }
            string line;
            lock (L)
            {
                try
                {
                    var root = Read(); var arr = (JArray)root["commands"];
                    Func<string, JObject> find = n => arr.OfType<JObject>().FirstOrDefault(x => ((string)x["name"] ?? "").ToLowerInvariant() == n || (x["aliases"] as JArray ?? new JArray()).Any(z => ((string)z ?? "").ToLowerInvariant().TrimStart('!') == n));
                    var cur = find(name); string who = role >= 4 ? "broadcaster" : "mod";
                    if (cmd == "!addcom")
                    {
                        if (text == "") { line = usage + "."; }
                        else if (cur != null && (bool?)cur["custom"] == true) line = "!" + name + " already exists, use !editcom.";
                        else if (cur != null || CustomCollides(name)) line = "!" + name + " is taken by a real command.";
                        else if (arr.OfType<JObject>().Count(x => (bool?)x["custom"] == true) >= 200) line = "that is too many custom commands (200).";
                        else
                        {
                            string bad = CustomBadText(text);
                            if (bad != null) line = bad + ".";
                            else
                            {
                                arr.Add(new JObject { { "name", name }, { "text", text }, { "custom", true }, { "cooldownSec", 10 }, { "addedBy", user.ToLowerInvariant() }, { "addedAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() } });
                                Write(root); ModAudit.Log(user, who, "!addcom", "!" + name, "", text); line = "added !" + name + ".";
                            }
                        }
                    }
                    else if (cur == null || (bool?)cur["custom"] != true) line = "!" + name + " is not a custom command.";
                    else if (cmd == "!delcom") { string before = (string)cur["text"] ?? ""; arr.Remove(cur); Write(root); ModAudit.Log(user, who, "!delcom", "!" + name, before, ""); line = "deleted !" + name + "."; }
                    else if (text == "") line = usage + ".";
                    else
                    {
                        string bad = CustomBadText(text);
                        if (bad != null) line = bad + ".";
                        else { string before = (string)cur["text"] ?? ""; cur["text"] = text; cur["editedBy"] = user.ToLowerInvariant(); cur["editedAt"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); Write(root); ModAudit.Log(user, who, "!editcom", "!" + name, before, text); line = "updated !" + name + "."; }
                    }
                }
                catch (Exception ex) { line = "could not save: " + ex.Message; }
            }
            say(at + line);
        }
        /// <summary>" Custom: !a !b ..." for !commands (empty when there are none), capped so the line stays short</summary>
        public static string CustomListLine()
        {
            try
            {
                lock (L)
                {
                    var names = Read()["commands"].OfType<JObject>().Where(x => (bool?)x["custom"] == true && (bool?)x["enabled"] != false).Select(x => "!" + (string)x["name"]).OrderBy(x => x).ToList();
                    if (names.Count == 0) return "";
                    var sb = new StringBuilder(" Custom: "); int shown = 0;
                    foreach (var n in names) { if (sb.Length + n.Length > 190) break; if (shown > 0) sb.Append(' '); sb.Append(n); shown++; }
                    if (shown < names.Count) sb.Append(" +" + (names.Count - shown) + " more");
                    return sb.ToString();
                }
            }
            catch (Exception) { return ""; }
        }

        static JObject View(JObject c)
        {
            return new JObject { { "name", c["name"] }, { "aliases", c["aliases"] ?? new JArray() }, { "text", c["text"] ?? "" }, { "choices", c["choices"] ?? new JArray() }, { "enabled", (bool?)c["enabled"] != false }, { "streamerOnlyHost", (bool?)c["skipBroadcaster"] == true } };
        }

        public static JObject List()
        {
            lock (L)
            {
                try
                {
                    var r = Read();
                    return new JObject { { "ok", true }, { "cooldownSec", (int?)r["cooldownSec"] ?? 20 }, { "variables", new JArray("$(user)", "$(touser)", "$(luck)", "$(games)", "$(count)", "$(link:<name>)") }, { "file", PathOf() }, { "commands", new JArray(r["commands"].OfType<JObject>().Select(View)) } };
                }
                catch (Exception ex) { return Err("could not read the canned commands: " + ex.Message); }
            }
        }

        /// <summary>what a viewer would see: the same replacements Chatty does ($(touser) must be a plain name, else the sender)</summary>
        public static string Render(string text, string user, string touser)
        {
            user = string.IsNullOrWhiteSpace(user) ? "Someone" : user.Trim();
            string to = (touser ?? "").Trim().TrimStart('@'); if (!Regex.IsMatch(to, @"^[A-Za-z0-9_]{1,25}$")) to = user;
            string r = (text ?? "").Replace("$(user)", user).Replace("$(touser)", to).Replace("$(count)", "1").Replace("$(luck)", (Rng.Next(50) + 1).ToString()).Replace("$(games)", "!gamble <amount>, !slots <amount> and Guess the Chatter (start it through !shop)");
            return Regex.Replace(r, @"\$\(link:([a-z0-9_]+)\)", m => Links.Get(m.Groups[1].Value) ?? m.Value);   // the same expansion Chatty does at serve time
        }

        /// <summary>body: { action: set|add|delete|test|cooldown, name, text?, choices?, aliases?, enabled?, user?, touser?, seconds? }</summary>
        public static JObject Handle(JObject b)
        {
            string action = ((string)b["action"] ?? "").ToLowerInvariant();
            lock (L)
            {
                try
                {
                    if (action == "test")
                    {
                        string text = (string)b["text"]; var ch = b["choices"] as JArray;
                        if (text == null && !string.IsNullOrEmpty((string)b["name"]))
                        {
                            var c0 = Read()["commands"].OfType<JObject>().FirstOrDefault(x => ((string)x["name"] ?? "").ToLowerInvariant() == CleanName((string)b["name"]));
                            if (c0 == null) return Err("no command with that name");
                            text = (string)c0["text"]; ch = c0["choices"] as JArray;
                        }
                        if (ch != null && ch.Count > 0) text = (string)ch[Rng.Next(ch.Count)];
                        string bad = BadText(text); if (bad != null) return Err(bad);
                        return new JObject { { "ok", true }, { "line", Render(text, (string)b["user"], (string)b["touser"]) } };   // shown here only, never sent to Twitch
                    }
                    var root = Read(); var arr = (JArray)root["commands"];
                    if (action == "cooldown")
                    {
                        int s = (int?)b["seconds"] ?? -1; if (s < 5 || s > 600) return Err("the cooldown must be 5 to 600 seconds");
                        root["cooldownSec"] = s; Write(root); return new JObject { { "ok", true }, { "cooldownSec", s } };
                    }
                    string name = CleanName((string)b["name"]); if (name == "") return Err("the name must be 1-24 letters, digits or _");
                    JObject cmd = arr.OfType<JObject>().FirstOrDefault(x => ((string)x["name"] ?? "").ToLowerInvariant() == name);
                    var taken = new HashSet<string>(); foreach (var x in arr.OfType<JObject>()) { taken.Add(((string)x["name"] ?? "").ToLowerInvariant()); foreach (var al in x["aliases"] as JArray ?? new JArray()) taken.Add(((string)al ?? "").ToLowerInvariant().TrimStart('!')); }
                    JArray newAliases = null;
                    if (b["aliases"] is JArray)
                    {
                        newAliases = new JArray();
                        foreach (var a0 in (JArray)b["aliases"])
                        {
                            string a = CleanName((string)a0); if (a == "") return Err("an alias must be 1-24 letters, digits or _");
                            if (HostOwns(a)) return Err("!" + a + " belongs to a real command");
                            bool mine = cmd != null && (cmd["aliases"] as JArray ?? new JArray()).Any(z => ((string)z ?? "").ToLowerInvariant().TrimStart('!') == a);
                            if (taken.Contains(a) && !mine && a != name) return Err("!" + a + " is already used");
                            if (!newAliases.Any(z => (string)z == a) && a != name) newAliases.Add(a);
                        }
                    }
                    if (action == "add")
                    {
                        if (cmd != null) return Err("!" + name + " already exists, use set");
                        if (HostOwns(name) || taken.Contains(name)) return Err("!" + name + " is already used by a command");
                        string text = (string)b["text"]; var ch = b["choices"] as JArray; string bad = ch != null && ch.Count > 0 ? ch.Select(x => BadText((string)x)).FirstOrDefault(x => x != null) : BadText(text); if (bad != null) return Err(bad);
                        cmd = new JObject { { "name", name } }; if (newAliases != null && newAliases.Count > 0) cmd["aliases"] = newAliases;
                        if (ch != null && ch.Count > 0) cmd["choices"] = new JArray(ch.Select(x => ((string)x).Trim())); else cmd["text"] = text.Trim();
                        if (b["enabled"] != null && (bool)b["enabled"] == false) cmd["enabled"] = false;
                        arr.Add(cmd); Write(root); return new JObject { { "ok", true }, { "command", View(cmd) } };
                    }
                    if (action == "delete")
                    {
                        if (cmd == null) return Err("no command called !" + name);
                        arr.Remove(cmd); Write(root);   // the previous file stays as canned_commands.json.bak
                        return new JObject { { "ok", true }, { "deleted", name } };
                    }
                    if (action != "set") return Err("unknown action");
                    if (cmd == null) return Err("no command called !" + name);
                    if (b["text"] != null) { string bad = BadText((string)b["text"]); if (bad != null) return Err(bad); cmd["text"] = ((string)b["text"]).Trim(); cmd.Remove("choices"); }
                    if (b["choices"] is JArray)
                    {
                        var ch = (JArray)b["choices"]; string bad = ch.Select(x => BadText((string)x)).FirstOrDefault(x => x != null); if (bad != null) return Err(bad);
                        if (ch.Count > 0) { cmd["choices"] = new JArray(ch.Select(x => ((string)x).Trim())); cmd.Remove("text"); }
                    }
                    if (newAliases != null) { if (newAliases.Count > 0) cmd["aliases"] = newAliases; else cmd.Remove("aliases"); }
                    if (b["enabled"] != null) { if ((bool)b["enabled"]) cmd.Remove("enabled"); else cmd["enabled"] = false; }
                    if (cmd["text"] == null && !(cmd["choices"] is JArray && ((JArray)cmd["choices"]).Count > 0)) return Err("a command needs a text or choices");
                    Write(root); return new JObject { { "ok", true }, { "command", View(cmd) } };
                }
                catch (Exception ex) { return Err("could not save: " + ex.Message); }
            }
        }
    }
}
