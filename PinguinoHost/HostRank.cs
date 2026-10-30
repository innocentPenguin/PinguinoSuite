using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Stored Rocket League ranks of registered viewers. The streamer's own !rank is RocketRankBot's job (a third-party Twitch bot): a bare "!rank" gets NO answer from us, and nothing here looks up the streamer or any site by itself.
    /// The three forms: bare !rank = the streamer's rank, RocketRankBot's single reply (we stay silent so there is never a second line); !rank &lt;player&gt; = the stored rank (below);
    /// !rank lookup &lt;twitch name | Epic name&gt; [playlist] = a focused live search through <see cref="Fetcher"/> (nothing is stored from it; 30 s per person, mods exempt). Without a live source it says so in one line and shows the stored rank.
    /// !rank &lt;player&gt; [1s|2s|3s|4s|hoops|rumble|dropshot|snowday|heatseeker|tournament] answers from the stored value with its date; no automatic refresh. Ranks are fetched ONCE when someone registers (!register by the viewer, or by a mod for them)
    /// through <see cref="Fetcher"/> (empty until a live source is switched on) and a mod refreshes one player with !refreshrank &lt;player&gt;. Mods can always write a rank by hand: !setrank &lt;player&gt; 2v2 Champion I Div II (1400).
    /// Store: Data\runtime\rank_players.json {players:{login:{epic, plat, ranks:{"1v1":"Champion I Div II (999)"}, at, src(register|fetch|setrank), registeredAt}}}. The epic name comes from Core's players.json after the !register went through.</summary>
    public static class Rank
    {
        static readonly object L = new object();
        static string StoreP { get { return Path.Combine(HostApi.DataDir, "rank_players.json"); } }
        static readonly string[] Lists = { "1v1", "2v2", "3v3" };
        static readonly string[] AllLists = { "1v1", "2v2", "3v3", "4v4", "hoops", "rumble", "dropshot", "snowday", "heatseeker", "tournament" };
        public static bool IsCommand(string cmd) { return cmd == "!rank" || cmd == "!setrank" || cmd == "!refreshrank"; }
        public static bool IsModCommand(string cmd) { return cmd == "!setrank" || cmd == "!refreshrank"; }

        /// <summary>the live source: (platform, epic name) -> ranks {"1v1":"Champion I Div II (999)", ...} or null when it could not read them. Null until a source is switched on: then ranks are only set by hand.</summary>
        public static Func<string, string, JObject> Fetcher = FixtureFetcher();
        /// <summary>tests only: PINGUINO_RANK_FIXTURE = a folder with one flat ranks file per epic name (rank.&lt;epic lower&gt;.json), PINGUINO_RANK_CALLLOG = one line per fetch. Without the variable there is no live source.</summary>
        static Func<string, string, JObject> FixtureFetcher()
        {
            string dir = Environment.GetEnvironmentVariable("PINGUINO_RANK_FIXTURE"); if (string.IsNullOrEmpty(dir)) return null;
            return (plat, epic) =>
            {
                string log = Environment.GetEnvironmentVariable("PINGUINO_RANK_CALLLOG"); if (!string.IsNullOrEmpty(log)) { try { File.AppendAllText(log, plat + ":" + epic + Environment.NewLine); } catch (Exception) { } }
                string f = Path.Combine(dir, "rank." + epic.ToLowerInvariant() + ".json"); return File.Exists(f) ? JObject.Parse(File.ReadAllText(f)) : null;
            };
        }
        /// <summary>tests: wait for a background register to finish</summary>
        public static int RegisterDelayMs = 3000;

        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        static string Label(string k) { return char.IsDigit(k[0]) ? "Ranked " + k : char.ToUpperInvariant(k[0]) + k.Substring(1); }
        static string Date(long at) { return DateTimeOffset.FromUnixTimeSeconds(at).UtcDateTime.ToString("MMM d", CultureInfo.InvariantCulture); }

        static string Clean(string s)
        {   // no pings, links or command starts in anything the bot repeats
            s = Regex.Replace(s ?? "", @"https?://\S+|www\.\S+|@\w+", "").Trim(); s = Regex.Replace(s, @"\s+", " ");
            while (s.StartsWith("!") || s.StartsWith("/") || s.StartsWith(".")) s = s.Substring(1).TrimStart();
            return s.Length > 80 ? s.Substring(0, 80) : s;
        }

        static string ListOf(string w)
        {
            w = (w ?? "").ToLowerInvariant().Replace("'", "").Trim('/', '-', ' ');
            switch (w)
            {
                case "1s": case "1v1": case "ones": case "duel": case "solo": return "1v1";
                case "2s": case "2v2": case "twos": case "doubles": return "2v2";
                case "3s": case "3v3": case "threes": case "standard": return "3v3";
                case "4s": case "4v4": case "quads": case "fours": return "4v4";
                case "hoops": case "hoop": case "basketball": return "hoops";
                case "rumble": return "rumble";
                case "dropshot": case "drop": return "dropshot";
                case "snowday": case "snow": case "hockey": case "puck": return "snowday";
                case "heatseeker": case "heatseek": case "heat": case "hs": case "seeker": return "heatseeker";
                case "tournament": case "tournaments": case "tourney": return "tournament";
            }
            return "";
        }

        // ================= store =================
        static JObject Load()
        {
            try { if (File.Exists(StoreP)) { var d = JObject.Parse(File.ReadAllText(StoreP, Encoding.UTF8).TrimStart((char)0xFEFF)); if (d["players"] is JObject) return d; } } catch (Exception) { }
            return new JObject { { "players", new JObject() } };
        }
        static void Save(JObject d)
        {
            try { Directory.CreateDirectory(Path.GetDirectoryName(StoreP)); string tmp = StoreP + ".tmp"; File.WriteAllText(tmp, d.ToString(), new UTF8Encoding(false)); if (File.Exists(StoreP)) File.Delete(StoreP); File.Move(tmp, StoreP); }
            catch (Exception ex) { Clog.Warn("rank", "rank store not saved: " + ex.Message); }
        }

        /// <summary>Core's players.json: twitch login -> (platform, game id) of someone who registered</summary>
        static bool Registered(string login, out string plat, out string epic)
        {
            plat = "epic"; epic = "";
            try
            {
                var pj = JObject.Parse(File.ReadAllText(Path.Combine(HostApi.DataDir, "players.json"), Encoding.UTF8).TrimStart((char)0xFEFF));
                foreach (var p in pj.Properties())
                {
                    var o = p.Value as JObject; if (o == null) continue;
                    if (!string.Equals(((string)o["Username"] ?? p.Name), login, StringComparison.OrdinalIgnoreCase) || string.IsNullOrWhiteSpace((string)o["GameId"])) continue;
                    epic = ((string)o["GameId"]).Trim(); string pf = ((string)o["Platform"] ?? "epic").ToLowerInvariant(); plat = pf == "" ? "epic" : pf; return true;
                }
            }
            catch (Exception) { }
            return false;
        }

        /// <summary>the stored record of a login, or of the player whose Epic name was typed</summary>
        static JObject Find(JObject d, string who, out string login)
        {
            login = who.ToLowerInvariant().TrimStart('@'); var ps = (JObject)d["players"];
            var r = ps[login] as JObject; if (r != null) return r;
            foreach (var p in ps.Properties()) if (string.Equals((string)((JObject)p.Value)["epic"], who.TrimStart('@'), StringComparison.OrdinalIgnoreCase)) { login = p.Name; return (JObject)p.Value; }
            return null;
        }

        static JObject Rec(JObject d, string login, string plat, string epic)
        {
            var ps = (JObject)d["players"]; var r = ps[login] as JObject;
            if (r == null) { r = new JObject { { "registeredAt", Now() } }; ps[login] = r; }
            r["epic"] = epic; r["plat"] = plat; if (r["ranks"] == null) r["ranks"] = new JObject();
            return r;
        }

        /// <summary>one fetch for one player; stores the ranks with the date. false when no source is on or it found nothing (the old values stay)</summary>
        static bool FetchInto(string login, string plat, string epic)
        {
            var f = Fetcher; if (f == null) return false;
            JObject got = null; try { got = f(plat, epic); } catch (Exception ex) { Clog.Warn("rank", "fetch for " + login + " failed: " + ex.Message); }
            if (got == null || !got.HasValues) return false;
            lock (L)
            {
                var d = Load(); var r = Rec(d, login, plat, epic); var ranks = (JObject)r["ranks"]; int n = 0;
                foreach (var k in AllLists) { string v = Clean((string)got[k] ?? ""); if (v != "") { ranks[k] = v; n++; } }
                if (n == 0) return false;
                r["at"] = Now(); r["src"] = "fetch"; Save(d);
            }
            try { PublishProfile(login); } catch (Exception ex) { Clog.Warn("rank", "profile ranks not saved: " + ex.Message); }
            return true;
        }

        /// <summary>called for every "!register ..." line (the Core handles the registration itself): a moment later the player's epic name is read from players.json, the record is created and the ONE rank fetch is made</summary>
        public static void OnRegister(string user, string[] args, bool mod)
        {
            string target = (user ?? "").ToLowerInvariant();
            if (mod && args.Length > 0 && args[0].StartsWith("@")) target = args[0].TrimStart('@').ToLowerInvariant();
            if (target == "") return;
            System.Threading.Tasks.Task.Run(() =>
            {
                try
                {
                    System.Threading.Thread.Sleep(RegisterDelayMs);
                    string plat, epic; if (!Registered(target, out plat, out epic)) return;
                    if (!Regex.IsMatch(epic, @"^[A-Za-z0-9_.\- ]{2,32}$")) return;
                    bool same; lock (L) { var d = Load(); var r = (JObject)((JObject)d["players"])[target]; same = r != null && string.Equals((string)r["epic"], epic, StringComparison.OrdinalIgnoreCase) && ((r["ranks"] as JObject)?.HasValues == true); Rec(d, target, plat, epic); Save(d); }
                    if (!same) FetchInto(target, plat, epic);   // a repeated !register of the same name does not fetch again
                }
                catch (Exception ex) { Clog.Warn("rank", "register hook: " + ex.Message); }
            });
        }

        /// <summary>Data\ranks\rl_ranks.json {users:{login:{at, ranks}}} feeds the profile push (rocketLeague chip)</summary>
        static string DataRoot { get { string d = HostApi.DataDir.TrimEnd((char)92, '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d; } }
        static string RanksP { get { return Path.Combine(DataRoot, "ranks", "rl_ranks.json"); } }
        static void PublishProfile(string login)
        {
            lock (L)
            {
                var r = (Load()["players"] as JObject)?[login] as JObject; var ranks = r?["ranks"] as JObject; if (ranks == null || !ranks.HasValues) return;
                JObject doc = null; try { if (File.Exists(RanksP)) doc = JObject.Parse(File.ReadAllText(RanksP, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { }
                if (doc == null) doc = new JObject(); var users = doc["users"] as JObject ?? new JObject(); doc["users"] = users;
                string canon = login; try { canon = Boards.CanonLogin(login); } catch (Exception) { }
                users[canon] = new JObject { { "at", (long?)r["at"] ?? Now() }, { "ranks", ranks.DeepClone() } }; doc["updatedAt"] = Now();
                Directory.CreateDirectory(Path.GetDirectoryName(RanksP)); string tmp = RanksP + ".tmp";
                File.WriteAllText(tmp, doc.ToString(), new UTF8Encoding(false)); if (File.Exists(RanksP)) File.Delete(RanksP); File.Move(tmp, RanksP);
            }
        }

        public static JObject HealthJson()
        {
            int n, withRanks; lock (L) { var ps = (JObject)Load()["players"]; n = ps.Count; withRanks = ps.Properties().Count(p => (((JObject)p.Value)["ranks"] as JObject)?.HasValues == true); }
            return new JObject { { "owner", "RocketRankBot (third party); we stay silent on a bare !rank" }, { "liveFetch", Fetcher != null }, { "players", n }, { "withRanks", withRanks } };
        }

        // ================= chat =================
        static bool IsOwnerName(string w)
        {
            w = (w ?? "").ToLowerInvariant().TrimStart('@'); string owner = ""; try { owner = (Boards.Channel() ?? "").ToLowerInvariant(); } catch (Exception) { }
            return w == "innocentpenguin" || w == "innocentpenguin_" || w == "ivan" || w == "penguin" || (owner != "" && w == owner);
        }

        public static void Handle(string user, string cmd, string[] args, bool mod, Action<string> say)
        {
            if (cmd == "!setrank") { if (mod) Set(args, say); return; }
            if (cmd == "!refreshrank") { if (mod) Refresh(args, say); return; }
            if (args.Length > 0 && args[0].ToLowerInvariant() == "lookup") { Lookup(user, args.Skip(1).ToArray(), mod, say); return; }
            string only = "", who = "";
            foreach (var a in args) { string l = ListOf(a); if (l != "") only = l; else if (who == "") who = a.TrimStart('@'); }
            if (who == "" || IsOwnerName(who)) return;   // the streamer's own rank is RocketRankBot's: no second line from us
            JObject d; lock (L) d = Load();
            string login; var r = Find(d, who, out login);
            if (r == null)
            {
                string plat, epic;
                if (Registered(login, out plat, out epic)) say(who + " is registered as " + epic + " but has no saved rank yet. A mod can set it with !setrank " + login + " 2v2 Champion I Div II (1400).");
                else say(who + " has no saved rank. They can type !register <EpicName>; a mod can set one with !setrank " + who + " 2v2 Champion I Div II (1400).");
                return;
            }
            string name = (string)r["epic"] ?? login;
            if (!(r["ranks"] as JObject ?? new JObject()).HasValues) { say(name + " is registered but has no saved rank yet. A mod can set it with !setrank " + login + " 2v2 Champion I Div II (1400)."); return; }
            say(StoredLine(r, login, only));
        }

        /// <summary>"Epic - Ranked 1v1: ... | Ranked 2v2: ... (as of Oct 30)" of a stored record</summary>
        static string StoredLine(JObject r, string login, string only)
        {
            var ranks = r["ranks"] as JObject ?? new JObject(); string name = (string)r["epic"] ?? login;
            var keys = only != "" ? new[] { only } : Lists;
            var parts = keys.Select(k => new { k, v = (string)ranks[k] ?? "" }).Where(x => x.v != "").Select(x => Label(x.k) + ": " + x.v).ToList();
            if (parts.Count == 0 && only == "") parts = AllLists.Select(k => new { k, v = (string)ranks[k] ?? "" }).Where(x => x.v != "").Select(x => Label(x.k) + ": " + x.v).ToList();
            if (parts.Count == 0) return name + ": no " + Label(only) + " rank saved.";
            long at = (long?)r["at"] ?? 0;
            return name + " - " + string.Join(" | ", parts) + (at > 0 ? " (as of " + Date(at) + ")" : "");
        }

        static readonly Dictionary<string, DateTime> LookupCool = new Dictionary<string, DateTime>();
        static bool LookupCooling(string user, bool mod)
        {
            if (mod) return false; int sec; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_RANK_LOOKUP_COOL"), out sec)) sec = 30; if (sec <= 0) return false;
            lock (LookupCool) { DateTime t; if (LookupCool.TryGetValue(user, out t) && (DateTime.UtcNow - t).TotalSeconds < sec) return true; LookupCool[user] = DateTime.UtcNow; return false; }
        }

        /// <summary>!rank lookup &lt;twitch name | Epic name&gt; [playlist]: a focused live search. Nothing is saved from it. With no live source: one honest line plus the stored rank.</summary>
        static void Lookup(string user, string[] args, bool mod, Action<string> say)
        {
            string only = "", name = "";
            foreach (var a in args) { string l = ListOf(a); if (l != "" && only == "") only = l; else name += (name == "" ? "" : " ") + a.TrimStart('@'); }
            name = name.Trim();
            if (name == "") { say("Usage: !rank lookup <Twitch name or Epic name> [1s|2s|3s|hoops|rumble|dropshot|snowday|heatseeker]"); return; }
            if (IsOwnerName(name)) { say("That is the streamer: a bare !rank shows his rank."); return; }
            if (LookupCooling((user ?? "").ToLowerInvariant(), mod)) return;
            JObject d; lock (L) d = Load(); string login; var r = Find(d, name, out login);
            string plat = "epic", epic = name; bool hasStored = r != null && (r["ranks"] as JObject)?.HasValues == true;
            if (r != null) { plat = (string)r["plat"] ?? "epic"; epic = (string)r["epic"] ?? login; } else { string p2, e2; if (Registered(login, out p2, out e2)) { plat = p2; epic = e2; } }
            string stored = hasStored ? StoredLine(r, login, only) : "";
            var f = Fetcher;
            if (f == null) { say("Live lookup isn't available yet; " + (hasStored ? "stored rank: " + stored : "no stored rank for " + name + ".")); return; }
            if (!Regex.IsMatch(epic, @"^[A-Za-z0-9_.\- ]{2,32}$")) { say("That name does not look like a Twitch or Epic name."); return; }
            System.Threading.Tasks.Task.Run(() =>
            {
                JObject got = null; try { got = f(plat, epic); } catch (Exception ex) { Clog.Warn("rank", "lookup for " + epic + " failed: " + ex.Message); }
                var live = new JObject(); if (got != null) foreach (var k in AllLists) { string v = Clean((string)got[k] ?? ""); if (v != "") live[k] = v; }
                if (!live.HasValues) { say("Could not read " + epic + "'s rank right now" + (hasStored ? "; stored rank: " + stored : ".")); return; }
                var rec = new JObject { { "epic", epic }, { "ranks", live }, { "at", Now() } };
                say(StoredLine(rec, login, only).Replace(" (as of " + Date(Now()) + ")", "") + " (live)");
            });
        }

        static void Refresh(string[] args, Action<string> say)
        {
            string who = args.FirstOrDefault(a => ListOf(a) == "") ?? ""; who = who.TrimStart('@');
            if (who == "") { say("Usage: !refreshrank <player>"); return; }
            JObject d; lock (L) d = Load(); string login; var r = Find(d, who, out login); string plat = "epic", epic = "";
            if (r != null) { plat = (string)r["plat"] ?? "epic"; epic = (string)r["epic"] ?? ""; }
            else if (!Registered(login, out plat, out epic)) { say(who + " is not registered."); return; }
            if (Fetcher == null) { say("Live rank lookup is off, so ranks are set by hand: !setrank " + login + " 2v2 Champion I Div II (1400)."); return; }
            say(FetchInto(login, plat, epic) ? "Refreshed " + epic + "'s rank." : "Could not read " + epic + "'s rank right now. The saved one stays; a mod can use !setrank " + login + " 2v2 Champion I Div II (1400).");
        }

        static void Set(string[] args, Action<string> say)
        {
            if (args.Length < 2) { say("Usage: !setrank <player> 2v2 Champion I Div II (1400), or paste 'Ranked 1v1: ... | Ranked 2v2: ...' after the name."); return; }
            string who = args[0].TrimStart('@'); string rest = string.Join(" ", args.Skip(1)).Trim();
            if (ListOf(args[0]) != "") { say("Name the player first: !setrank <player> " + args[0] + " Champion I Div II (1400)."); return; }
            string plat = "epic", epic; JObject d; string login; string reply;
            lock (L)
            {
                d = Load(); var r = Find(d, who, out login);
                if (r != null) { plat = (string)r["plat"] ?? "epic"; epic = (string)r["epic"] ?? login; } else if (!Registered(login, out plat, out epic)) { plat = "epic"; epic = who; }
                int n = 0; var set = new Dictionary<string, string>();
                var bulk = Regex.Matches(rest, @"Ranked\s+(1v1|2v2|3v3)\s*:\s*(.+?)(?=\s*\|\s*Ranked\s|\s*$)", RegexOptions.IgnoreCase);
                if (bulk.Count > 0) foreach (Match m in bulk) { string v = Clean(m.Groups[2].Value); if (v != "") set[m.Groups[1].Value.ToLowerInvariant()] = v; }
                else
                {
                    string key = ListOf(args[1]); if (key == "") { say("Which one? Use 1v1, 2v2, 3v3 (or 4s, hoops, rumble, dropshot, snowday, heatseeker, tournament), like !setrank " + login + " 2v2 Champion I Div II (1400)."); return; }
                    set[key] = Clean(string.Join(" ", args.Skip(2)));
                }
                if (set.Count == 0) { say("Could not read that rank."); return; }
                var rec = Rec(d, login, plat, epic); var ranks = (JObject)rec["ranks"];
                foreach (var kv in set) { if (kv.Value == "" || kv.Value.ToLowerInvariant() == "clear") ranks.Remove(kv.Key); else { ranks[kv.Key] = kv.Value; n++; } }
                rec["at"] = Now(); rec["src"] = "setrank"; Save(d);
                reply = n > 0 ? "Saved " + epic + "'s rank (as of " + Date(Now()) + ")." : "Cleared " + epic + "'s rank.";
            }
            try { PublishProfile(login); } catch (Exception ex) { Clog.Warn("rank", "profile ranks not saved: " + ex.Message); }
            say(reply);
        }
    }
}
