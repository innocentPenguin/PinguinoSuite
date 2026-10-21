using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Simulated players for rehearsing the wheel, the customs queue, the recycler and the gambling games from the Suite app, without Twitch viewers.
    /// The sim players are Core "practice" players (memory only, never saved) driven through "!practice sim ..." (silent in chat); their points live on a SEPARATE in-memory ledger
    /// (Economy routes any sim login there), so the real ledger, strikes, profiles, stats, standings and match history are never touched. The Host never says anything in chat for them.
    /// Names: the site's member pool when it answers (GET {SimNamesPath}, default /api/bot/names), cached in Data\sim\names.json, else Data\boards\names.json, else a built-in list.
    /// Safety: refuses to start while the REAL stream is live and stops by itself the moment it goes live; Core already marks everything it pushes sim:true and can leave the sim out of the site push (sendSimToSite).</summary>
    public static class Sim
    {
        static readonly object L = new object();
        static readonly Random Rng = new Random();
        static bool _on, _loop; static DateTime _since = DateTime.MinValue;
        static readonly Dictionary<string, string> NameOf = new Dictionary<string, string>();   // sim login -> display name (order of joining kept in Order)
        static readonly List<string> Order = new List<string>();
        static readonly Dictionary<string, long> Led = new Dictionary<string, long>();
        static readonly List<JObject> Log = new List<JObject>();
        static string _mode = "both", _namesSrc = "none"; static List<string> _pool = new List<string>(); static DateTime _poolAt = DateTime.MinValue;
        static string _stopReason = "";
        static long _bets, _wins, _joins, _leaves;
        /// <summary>runs a text as the streamer, on the calling thread (set by HostApi)</summary>
        public static Action<string> Exec;

        static readonly string[] Builtin = { "NovaRider", "FrostByte", "PixelPanda", "GlitchGoblin", "TurboToast", "NightOwl77", "SaltyBiscuit", "CrimsonFox", "WaffleKnight", "ZenMango", "ThunderPaws", "MochaMoose", "RocketRaccoon",
            "SilentYeti", "BlueberryBlitz", "CosmicCobra", "DizzyDrifter", "EchoEagle", "FuzzyFalcon", "GiggleGhost", "HazyHusky", "IcyIguana", "JollyJaguar", "KiwiKicker", "LunarLynx", "MellowMagpie", "NeonNarwhal",
            "OliveOtter", "PepperPuffin", "QuirkyQuokka", "RustyRhino", "SunnySeal", "TacoTiger", "UmbraUrchin", "VividViper", "WobblyWalrus", "XenonXerus", "YodelYak", "ZippyZebra", "AceAvalanche", "BoostBandit",
            "ChipChaser", "DashDragon", "EmberElk", "FlipFlop42", "GoalGopher", "HoopHawk", "InkImp", "JetJackal", "KnockoutKoala", "LagLlama", "MuffinMage", "NitroNewt", "OrbitOwl", "PuckPenguin", "QuickQuail" };

        // ---- settings (config/sim.json) ----
        static string CfgP { get { return Path.Combine(HostApi.DataDir, "config", "sim.json"); } }
        static JObject Cfg()
        {
            var d = new JObject { { "sendSimToSite", true }, { "churnPerMin", 0 }, { "startBalance", 1000 }, { "gambling", true }, { "earnPerMin", 5 } };
            try { if (File.Exists(CfgP)) foreach (var p in JObject.Parse(File.ReadAllText(CfgP).TrimStart((char)0xFEFF))) if (d[p.Key] != null) d[p.Key] = p.Value; } catch (Exception) { }
            return d;
        }
        static void SaveCfg(JObject c) { try { Directory.CreateDirectory(Path.GetDirectoryName(CfgP)); File.WriteAllText(CfgP, c.ToString(), new UTF8Encoding(false)); } catch (Exception) { } }
        public static bool SendToSite { get { return (bool?)Cfg()["sendSimToSite"] != false; } }
        public static bool On { get { lock (L) return _on; } }

        // ---- the sim ledger ----
        static string Lg(string login) { return (login ?? "").Trim().TrimStart('@').ToLowerInvariant(); }
        public static bool IsSim(string login) { lock (L) return _on && Led.ContainsKey(Lg(login)); }
        public static long Balance(string login) { lock (L) { long v; return Led.TryGetValue(Lg(login), out v) ? v : 0; } }
        public static string Spend(string login, long amt) { lock (L) { string k = Lg(login); long v; if (!Led.TryGetValue(k, out v)) return "no user"; if (v < amt) return "not enough points"; Led[k] = v - amt; return null; } }
        public static bool Credit(string login, long amt) { lock (L) { string k = Lg(login); long v; if (!Led.TryGetValue(k, out v)) return false; Led[k] = v + amt; return true; } }
        public static JObject Grant(string login, string mode, double amt)
        {
            lock (L)
            {
                string k = Lg(login); long v; if (!Led.TryGetValue(k, out v)) return new JObject { { "ok", false }, { "error", "not a sim player" } };
                long nv = mode == "set" ? (long)amt : Math.Max(0, v + (long)amt); Led[k] = nv;
                return new JObject { { "ok", true }, { "message", "(sim) " + k + " now has " + nv + " points." }, { "affected", 1 }, { "total", nv - v }, { "sim", true } };
            }
        }

        static void Note(string kind, string text)
        {
            lock (L) { Log.Add(new JObject { { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "kind", kind }, { "text", text } }); while (Log.Count > 60) Log.RemoveAt(0); }
        }

        // ---- names ----
        static string NamesP { get { return Path.Combine(HostApi.DataDir, "sim", "names.json"); } }
        static void AddNames(List<string> into, JToken t)
        {
            if (t is JArray) foreach (var x in (JArray)t)
            {
                string n = x.Type == JTokenType.String ? (string)x : x is JObject ? ((string)x["name"] ?? (string)x["displayName"] ?? (string)x["display"] ?? (string)x["login"] ?? (string)x["username"]) : null;
                if (!string.IsNullOrEmpty(n)) into.Add(n);
            }
        }
        static string Clean(string n) { return System.Text.RegularExpressions.Regex.Replace(n ?? "", @"[^A-Za-z0-9_]", ""); }
        /// <summary>site pool (cached an hour) -> boards names -> built-in; always returns something</summary>
        static List<string> Pool()
        {
            lock (L) { if (_pool.Count > 0 && (DateTime.UtcNow - _poolAt).TotalMinutes < 60) return _pool; }
            var names = new List<string>(); string src = "built-in";
            try
            {
                string key = SiteKey(); string path = null; try { path = (string)Latest.Settings()["SimNamesPath"]; } catch (Exception) { }
                if (key != "")
                {
                    JObject j; int code = SiteHttp.Call("GET", string.IsNullOrEmpty(path) ? "/api/bot/names" : path, null, key, out j);
                    if (code >= 200 && code < 300 && j != null) { foreach (var k in new[] { "names", "members", "chatters", "users" }) AddNames(names, j[k]); if (names.Count > 0) src = "site"; }
                }
            }
            catch (Exception) { }
            if (names.Count == 0)
            {
                try { if (File.Exists(NamesP)) { AddNames(names, JObject.Parse(File.ReadAllText(NamesP).TrimStart((char)0xFEFF))["names"]); if (names.Count > 0) src = "cache"; } } catch (Exception) { }
            }
            else { try { Directory.CreateDirectory(Path.GetDirectoryName(NamesP)); File.WriteAllText(NamesP, new JObject { { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "source", "site" }, { "names", new JArray(names.Distinct()) } }.ToString(), new UTF8Encoding(false)); } catch (Exception) { } }
            if (names.Count == 0)
            {
                try
                {
                    foreach (var root in new[] { HostApi.DataDir, Path.GetDirectoryName(HostApi.DataDir.TrimEnd('\\', '/')) })
                    {
                        string f = Path.Combine(root ?? "", "boards", "names.json");
                        if (File.Exists(f)) { foreach (var p in JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)).Properties()) { string n = (string)(p.Value as JObject)?["name"]; if (!string.IsNullOrEmpty(n)) names.Add(n); } if (names.Count > 0) { src = "boards"; break; } }
                    }
                }
                catch (Exception) { }
            }
            names = names.Select(Clean).Where(n => n.Length >= 3 && n.Length <= 25).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            if (names.Count < 12) { names.AddRange(Builtin); names = names.Distinct(StringComparer.OrdinalIgnoreCase).ToList(); if (src != "site" && src != "cache") src = "built-in"; }
            lock (L) { _pool = names; _poolAt = DateTime.UtcNow; _namesSrc = src; }
            return names;
        }
        static string SiteKey() { try { return SiteHttp.Key(); } catch (Exception) { return ""; } }

        static List<string> PickNames(int n)
        {
            var pool = Pool(); List<string> used; lock (L) used = NameOf.Values.ToList();
            var free = pool.Where(x => !used.Contains(x, StringComparer.OrdinalIgnoreCase)).OrderBy(x => Rng.Next()).Take(n).ToList();
            return free;
        }

        // ---- Core calls (silent) ----
        static void CoreAdd(IEnumerable<string> names)
        {
            var l = names.ToList();
            for (int i = 0; i < l.Count; i += 15) Exec("!practice sim add " + string.Join(",", l.Skip(i).Take(15)));
        }
        static void CoreDrop(IEnumerable<string> names)
        {
            var l = names.ToList();
            for (int i = 0; i < l.Count; i += 15) Exec("!practice sim drop " + string.Join(",", l.Skip(i).Take(15)));
        }

        static string Login(string name) { return "sim_" + Clean(name).ToLowerInvariant(); }

        // ---- engine ----
        public static JObject Start(int count, string mode)
        {
            string live = LiveState.Source; if (live == "live") return Fail("the real stream is live: the simulator only runs while it is not");
            count = Math.Max(1, Math.Min(200, count));
            lock (L) { if (_on) return Fail("the simulation is already running (add or remove players, or clear it first)"); _on = true; _since = DateTime.UtcNow; _mode = string.IsNullOrEmpty(mode) ? "both" : mode; _stopReason = ""; _bets = _wins = _joins = _leaves = 0; }
            Note("start", "simulation started with " + count + " players (mode " + _mode + ")");
            Clog.Info("sim", "simulation ON (" + count + " players)");
            Join(PickNames(count));
            StartLoop();
            return Status();
        }
        static JObject Fail(string e) { return new JObject { { "ok", false }, { "error", e } }; }

        static void Join(IEnumerable<string> names)
        {
            var add = new List<string>(); long start = (long)(Cfg()["startBalance"] ?? 1000);
            lock (L) foreach (var n0 in names) { string n = Clean(n0); if (n.Length < 2 || NameOf.ContainsKey(Login(n))) continue; NameOf[Login(n)] = n; Order.Add(n); Led[Login(n)] = start; add.Add(n); _joins++; }
            if (add.Count == 0) return;
            CoreAdd(add); foreach (var n in add) Note("join", n + " joined");
        }
        static void Leave(IEnumerable<string> names)
        {
            var gone = new List<string>();
            lock (L) foreach (var n0 in names) { string lg = Login(n0); string disp; if (!NameOf.TryGetValue(lg, out disp)) continue; NameOf.Remove(lg); Order.Remove(disp); Led.Remove(lg); gone.Add(disp); _leaves++; }
            if (gone.Count == 0) return;
            CoreDrop(gone); foreach (var n in gone) Note("leave", n + " left");
        }

        public static JObject Add(int n)
        {
            if (!On) return Fail("the simulation is not running");
            if (LiveState.Source == "live") { Stop("stream went live"); return Fail("the real stream is live"); }
            n = Math.Max(1, Math.Min(100, n)); Join(PickNames(n)); return Status();
        }
        public static JObject Remove(int n)
        {
            if (!On) return Fail("the simulation is not running");
            List<string> pick; lock (L) pick = Order.OrderBy(x => Rng.Next()).Take(Math.Max(1, Math.Min(100, n))).ToList();
            Leave(pick); return Status();
        }
        public static JObject JoinNames(JArray names)
        {
            if (!On) return Fail("the simulation is not running");
            Join(names.Select(x => (string)x).Where(x => x != null)); return Status();
        }
        public static JObject LeaveNames(JArray names)
        {
            if (!On) return Fail("the simulation is not running");
            Leave(names.Select(x => (string)x).Where(x => x != null)); return Status();
        }
        public static JObject Clear(string why)
        {
            bool was;
            lock (L) { was = _on; if (was) _stopReason = why ?? "cleared"; _on = false; }
            if (was) { try { Exec("!practice sim clear"); } catch (Exception ex) { Clog.Warn("sim", "clear failed: " + ex.Message); } }
            lock (L) { NameOf.Clear(); Order.Clear(); Led.Clear(); }
            if (was) { Note("stop", "simulation off (" + (why ?? "cleared") + ")"); Clog.Info("sim", "simulation OFF (" + (why ?? "cleared") + ")"); }
            return Status();
        }
        public static void Stop(string why) { Clear(why); }

        /// <summary>one churn + activity step (also run by the background loop)</summary>
        public static JObject Tick()
        {
            if (!On) return Fail("the simulation is not running");
            if (LiveState.Source == "live") { Stop("stream went live"); return Status(); }
            var c = Cfg(); double perMin = (double)(c["churnPerMin"] ?? 0);
            if (perMin > 0)
            {
                int events = (int)Math.Floor(perMin / 12.0) + (Rng.NextDouble() < (perMin / 12.0) % 1 ? 1 : 0);   // the loop ticks every 5 s
                for (int i = 0; i < events; i++)
                {
                    int cnt; lock (L) cnt = Order.Count;
                    if (cnt < 3 || (cnt < 80 && Rng.Next(2) == 0)) Join(PickNames(1)); else { List<string> one; lock (L) one = new List<string> { Order[Rng.Next(Order.Count)] }; Leave(one); }
                }
            }
            long earn = (long)Math.Round((double)(c["earnPerMin"] ?? 0) / 12.0 + (Rng.NextDouble() < ((double)(c["earnPerMin"] ?? 0) / 12.0) % 1 ? 1 : 0));
            if (earn > 0) lock (L) foreach (var k in Led.Keys.ToList()) Led[k] += earn;
            if ((bool?)c["gambling"] != false) Play();
            return Status();
        }

        /// <summary>a random sim player bets (gamble / slots) or challenges another sim player; the output goes to the sim log, never to chat</summary>
        static void Play()
        {
            string a, b; lock (L) { if (Order.Count < 1) return; a = Order[Rng.Next(Order.Count)]; b = Order[Rng.Next(Order.Count)]; }
            string la = Login(a), lb = Login(b); long bal = Balance(la); if (bal < 10) { Credit(la, 100); return; }
            long bet = Math.Max(1, (long)(bal * (0.05 + Rng.NextDouble() * 0.2)));
            int roll = Rng.Next(10); Action<string> say = s => { Note("chat", s); };
            try
            {
                if (roll < 5) { long before = Balance(la); Gamble.Handle(la, "!gamble", new[] { bet.ToString() }, say); lock (L) { _bets++; if (Balance(la) > before) _wins++; } }
                else if (roll < 8) { long before = Balance(la); Gamble.Handle(la, "!slots", new[] { bet.ToString() }, say); lock (L) { _bets++; if (Balance(la) > before) _wins++; } }
                else if (la != lb) { Gamble.Handle(la, "!duel", new[] { "@" + lb, bet.ToString() }, say); Gamble.Handle(lb, "!accept", new string[0], say); lock (L) _bets++; }
            }
            catch (Exception ex) { Clog.Warn("sim", "play failed: " + ex.Message); }
        }

        static void StartLoop()
        {
            lock (L) { if (_loop) return; _loop = true; }
            Task.Run(async () =>
            {
                while (true)
                {
                    await Task.Delay(5000);
                    try { if (!On) { lock (L) _loop = false; return; } Tick(); } catch (Exception ex) { Clog.Warn("sim", "tick failed: " + ex.Message); }
                }
            });
        }

        public static JObject Config(JObject b)
        {
            var c = Cfg(); var errors = new JObject();
            foreach (var p in b.Properties())
            {
                if (p.Name == "sendSimToSite" || p.Name == "gambling") { if (p.Value.Type == JTokenType.Boolean) c[p.Name] = p.Value; else errors[p.Name] = "true or false"; }
                else if (p.Name == "churnPerMin" || p.Name == "startBalance" || p.Name == "earnPerMin")
                {
                    double v; if (p.Value.Type != JTokenType.Integer && p.Value.Type != JTokenType.Float || !double.TryParse(p.Value.ToString(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out v) || v < 0 || v > 100000) errors[p.Name] = "a number from 0 to 100000";
                    else c[p.Name] = p.Name == "churnPerMin" ? Math.Min(120, v) : Math.Round(v);
                }
                else if (p.Name != "by") errors[p.Name] = "unknown key";
            }
            if (errors.Count > 0) return new JObject { { "ok", false }, { "error", "invalid settings" }, { "errors", errors } };
            SaveCfg(c);
            if (b["sendSimToSite"] != null && On) { try { Exec("!practice sim site " + ((bool)c["sendSimToSite"] ? "on" : "off")); } catch (Exception) { } }
            Clog.Info("sim", "settings: " + c.ToString(Newtonsoft.Json.Formatting.None));
            return Status();
        }

        /// <summary>what Core currently holds for the sim (from its own public files): queue entries flagged sim, wheel sign-ups</summary>
        static void CoreCounts(out int queueSim, out int wheelSigned)
        {
            queueSim = 0; wheelSigned = 0;
            try
            {
                foreach (var root in new[] { HostApi.DataDir, Path.Combine(HostApi.DataDir, "runtime") })
                {
                    string f = Path.Combine(root, "live_state.json");
                    if (File.Exists(f)) { var j = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); queueSim = (j["queue"] as JArray ?? new JArray()).Count(x => (bool?)x["sim"] == true); break; }
                }
                foreach (var root in new[] { HostApi.DataDir, Path.Combine(HostApi.DataDir, "runtime") })
                {
                    string f = Path.Combine(root, "wheel_public.json");
                    if (File.Exists(f)) { var j = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); wheelSigned = (int?)j["signedUp"] ?? 0; break; }
                }
            }
            catch (Exception) { }
        }

        public static JObject Status()
        {
            var c = Cfg(); int q, w; CoreCounts(out q, out w);
            lock (L)
            {
                var pl = new JArray(Order.Select(n => new JObject { { "name", n }, { "login", Login(n) }, { "points", Led.ContainsKey(Login(n)) ? Led[Login(n)] : 0 } }));
                return new JObject { { "ok", true }, { "on", _on }, { "simulation", _on }, { "count", Order.Count }, { "mode", _mode }, { "players", pl }, { "sendSimToSite", (bool)c["sendSimToSite"] }, { "churnPerMin", c["churnPerMin"] },
                    { "startBalance", c["startBalance"] }, { "gambling", c["gambling"] }, { "earnPerMin", c["earnPerMin"] }, { "namesSource", _namesSrc }, { "namesAvailable", _pool.Count },
                    { "startedAt", _on ? (long?)new DateTimeOffset(_since, TimeSpan.Zero).ToUnixTimeSeconds() : null }, { "stopReason", _stopReason }, { "realStreamLive", LiveState.Source == "live" },
                    { "queueSim", q }, { "wheelSignedUp", w }, { "stats", new JObject { { "joins", _joins }, { "leaves", _leaves }, { "bets", _bets }, { "wins", _wins } } },
                    { "log", new JArray(Log.Skip(Math.Max(0, Log.Count - 30))) } };
            }
        }
    }
}
