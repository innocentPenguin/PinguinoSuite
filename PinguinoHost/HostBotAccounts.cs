using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Accounts that are bots, not viewers (BotRix, Sery_Bot, Nightbot ...). They get no First 5 place, no welcome bonus or greeting, no watch / presence points and no place on the boards or the Latest feed.
    /// The list is Data\runtime\bot_accounts.json {"names":[...]}: case-insensitive display names / logins and platform keys ("yt:ucxxxx", "tt:xxx"). It is seeded with the known bots on first use; mods extend it with !botaccount add|remove|list.</summary>
    public static class BotAccounts
    {
        static readonly string[] Seed = { "botrix", "sery_bot", "synchrabot", "nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "potatbot", "yt:uctuynlwrjh1sxgkxae6u_8q" };
        static readonly object L = new object();
        static HashSet<string> _set; static DateTime _stamp;
        static string FilePath { get { return Path.Combine(HostApi.DataDir, "bot_accounts.json"); } }

        static HashSet<string> Load()
        {
            lock (L)
            {
                try
                {
                    string f = FilePath;
                    if (!File.Exists(f)) { Save(new HashSet<string>(Seed)); }
                    var st = File.GetLastWriteTimeUtc(f);
                    if (_set == null || st != _stamp)
                    {
                        var o = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF));
                        _set = new HashSet<string>(((o["names"] as JArray) ?? new JArray()).Select(x => Norm((string)x)).Where(x => x != ""));
                        _stamp = st;
                    }
                }
                catch (Exception ex) { if (_set == null) _set = new HashSet<string>(Seed); Clog.Warn("botaccounts", "bot_accounts.json: " + ex.Message); }
                return _set;
            }
        }
        static string Norm(string s) { return (s ?? "").Trim().TrimStart('@').ToLowerInvariant(); }
        static void Save(HashSet<string> set)
        {
            string f = FilePath; string tmp = f + ".tmp";
            Directory.CreateDirectory(Path.GetDirectoryName(f));
            File.WriteAllText(tmp, new JObject { { "names", new JArray(set.OrderBy(x => x)) } }.ToString());
            if (File.Exists(f)) File.Delete(f); File.Move(tmp, f);
            _set = set; _stamp = File.GetLastWriteTimeUtc(f);
        }

        /// <summary>true for a login or platform key ("yt:id") on the list, or whose shown name is on it; our own bot accounts count too</summary>
        public static bool Is(string login)
        {
            string k = Norm(login); if (k == "") return false;
            try
            {
                var s = Load();
                if (s.Contains(k)) return true;
                if (k.IndexOf(':') > 0) { string d = Norm(PlatformUsers.Display(login)); if (d != "" && s.Contains(d)) return true; }
                return HostApi.IsOwnBotName(k);
            }
            catch (Exception) { return false; }
        }
        public static string Add(string name) { name = Norm(name); if (name == "") return "name needed"; lock (L) { var s = new HashSet<string>(Load()); if (!s.Add(name)) return name + " is already on the bot list."; Save(s); } return "Added " + name + " to the bot list (no points, First 5 or boards)."; }
        public static string Remove(string name) { name = Norm(name); lock (L) { var s = new HashSet<string>(Load()); if (!s.Remove(name)) return name + " is not on the bot list."; Save(s); } return "Removed " + name + " from the bot list."; }
        public static string ListText() { var s = Load(); return "Bot accounts (" + s.Count + "): " + string.Join(", ", s.OrderBy(x => x).Take(40)); }
    }
}
