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
    /// There is no delete on purpose: turning a command off keeps it, and every save keeps the previous file as canned_commands.json.bak.</summary>
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

        static JObject Err(string e) { return new JObject { { "ok", false }, { "error", e } }; }
        static string CleanName(string n) { n = (n ?? "").Trim().TrimStart('!').ToLowerInvariant(); return Regex.IsMatch(n, "^[a-z0-9_]{1,24}$") ? n : ""; }

        /// <summary>null = fine, else why the text cannot be used</summary>
        static string BadText(string t)
        {
            if (string.IsNullOrWhiteSpace(t)) return "the text is empty";
            if (t.Length > 400) return "the text is longer than 400 characters (Twitch chat limit is 500 with the name)";
            if (t.IndexOfAny(new[] { '\r', '\n' }) >= 0) return "the text must be one line";
            string s = t.TrimStart();
            if (s.StartsWith("/") || s.StartsWith(".") || s.StartsWith("!")) return "the text cannot start with / . or ! (that would run a Twitch or bot command)";
            if (Regex.IsMatch(t, @"\$\((?!user\)|touser\)|luck\))")) return "only $(user), $(touser) and $(luck) can be used";
            return null;
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
                    return new JObject { { "ok", true }, { "cooldownSec", (int?)r["cooldownSec"] ?? 20 }, { "variables", new JArray("$(user)", "$(touser)", "$(luck)") }, { "file", PathOf() }, { "commands", new JArray(r["commands"].OfType<JObject>().Select(View)) } };
                }
                catch (Exception ex) { return Err("could not read the canned commands: " + ex.Message); }
            }
        }

        /// <summary>what a viewer would see: the same replacements Chatty does ($(touser) must be a plain name, else the sender)</summary>
        public static string Render(string text, string user, string touser)
        {
            user = string.IsNullOrWhiteSpace(user) ? "Someone" : user.Trim();
            string to = (touser ?? "").Trim().TrimStart('@'); if (!Regex.IsMatch(to, @"^[A-Za-z0-9_]{1,25}$")) to = user;
            return (text ?? "").Replace("$(user)", user).Replace("$(touser)", to).Replace("$(luck)", (Rng.Next(50) + 1).ToString());
        }

        /// <summary>body: { action: set|add|test|cooldown, name, text?, choices?, aliases?, enabled?, user?, touser?, seconds? }</summary>
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
                            if (Reserved.Contains(a)) return Err("!" + a + " belongs to a real command");
                            bool mine = cmd != null && (cmd["aliases"] as JArray ?? new JArray()).Any(z => ((string)z ?? "").ToLowerInvariant().TrimStart('!') == a);
                            if (taken.Contains(a) && !mine && a != name) return Err("!" + a + " is already used");
                            if (!newAliases.Any(z => (string)z == a) && a != name) newAliases.Add(a);
                        }
                    }
                    if (action == "add")
                    {
                        if (cmd != null) return Err("!" + name + " already exists, use set");
                        if (Reserved.Contains(name) || taken.Contains(name)) return Err("!" + name + " is already used by a command");
                        string text = (string)b["text"]; var ch = b["choices"] as JArray; string bad = ch != null && ch.Count > 0 ? ch.Select(x => BadText((string)x)).FirstOrDefault(x => x != null) : BadText(text); if (bad != null) return Err(bad);
                        cmd = new JObject { { "name", name } }; if (newAliases != null && newAliases.Count > 0) cmd["aliases"] = newAliases;
                        if (ch != null && ch.Count > 0) cmd["choices"] = new JArray(ch.Select(x => ((string)x).Trim())); else cmd["text"] = text.Trim();
                        if (b["enabled"] != null && (bool)b["enabled"] == false) cmd["enabled"] = false;
                        arr.Add(cmd); Write(root); return new JObject { { "ok", true }, { "command", View(cmd) } };
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
