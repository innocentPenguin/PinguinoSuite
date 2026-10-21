using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The Suite's tuning panel: GET /api/tune lists areas (wheel, queue, gambling, economy, alias) with typed fields and their live values;
    /// POST /api/tune {area, values} validates + clamps server-side and applies (unknown key = error, null clears an optional field).
    /// Also the one-button actions: POST /api/wheel/spin|new|reset, POST /api/gamble/simulate, POST /api/economy/grant (hidden, silent, audited).
    /// Core settings (wheel, queue) are changed by sending the mod command to the bot as the streamer, so Core stays the only writer of its own files.</summary>
    public static partial class HostApi
    {
        class TF
        {
            public string Key, Label, Type, Unit, Help; public double? Min, Max, Step; public string[] Options; public bool Optional; public JToken Default;
            public JObject Json(JToken value)
            {
                var o = new JObject { { "key", Key }, { "label", Label }, { "type", Type }, { "value", value ?? JValue.CreateNull() }, { "default", Default ?? JValue.CreateNull() }, { "help", Help ?? "" } };
                if (Unit != null) o["unit"] = Unit; if (Min.HasValue) o["min"] = Min.Value; if (Max.HasValue) o["max"] = Max.Value; if (Step.HasValue) o["step"] = Step.Value;
                if (Options != null) o["options"] = new JArray(Options); if (Optional) o["optional"] = true; return o;
            }
        }
        static TF Num(string k, string label, double min, double max, double step, string unit, JToken def, string help, bool opt = false) { return new TF { Key = k, Label = label, Type = "number", Min = min, Max = max, Step = step, Unit = unit, Default = def, Help = help, Optional = opt }; }
        static TF Bool(string k, string label, bool def, string help) { return new TF { Key = k, Label = label, Type = "bool", Default = def, Help = help }; }
        static TF Sel(string k, string label, string def, string help, params string[] opts) { return new TF { Key = k, Label = label, Type = "select", Options = opts, Default = def, Help = help }; }

        static JObject ReadState(string name)
        {
            foreach (var d in new[] { DataDir, Path.Combine(DataDir, "runtime") })
            { try { string f = Path.Combine(d, name); if (File.Exists(f)) return JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { } }
            return new JObject();
        }
        static void RunAsStreamer(string text)
        {
            string who = "innocentpenguin_"; try { var ch = (string)StreamerCreds()["Channel"]; if (!string.IsNullOrEmpty(ch)) who = ch; } catch (Exception) { }
            System.Threading.Tasks.Task.Run(() => { Control.Synthetic = true; try { Program.Dispatch(who, text, null, 4, "deck", false, null); } finally { Control.Synthetic = false; } });
        }
        static JToken Pick(JToken t, JToken d) { return t == null || t.Type == JTokenType.Null ? d : t; }
        static string Inv(double v) { return v.ToString("0.##", CultureInfo.InvariantCulture); }

        // ---- the areas ----
        static List<TF> WheelFields() { return new List<TF> {
            Num("spinSpeed", "Spin length", 1500, 30000, 500, "ms", 8500, "How long one spin of the wheel takes."),
            Sel("mode", "Team mode", "random", "True random, or balanced by MMR (labelled rigged on screen).", "random", "balanced"),
            Num("teamSize", "Team size", 1, 4, 1, "players", 2, "Players per team."),
            Sel("oddPolicy", "Odd player out", "waitlist", "What happens when the players do not divide evenly.", "waitlist", "trio", "partial", "hold", "mod"),
            Sel("eligibility", "Who can join", "all", "Everyone, or subscribers only.", "all", "subs"),
            Bool("autoReopen", "Open the next round by itself", true, "After the finished teams have been shown, a new round opens."),
            Num("holdTimeSec", "Show final teams for", 0, 600, 5, "s", 40, "How long the finished teams stay up before the next round."),
            Num("joinFeedSec", "Join/leave line visible for", 0.5, 10, 0.5, "s", 2, "How long a joined/left line stays on the overlay."),
            Bool("showSignedUp", "Show the signed-up count", true, "The 'N signed up' badge on the overlay.") }; }
        static JObject WheelValues()
        {
            var pf = ReadState("wheel_public.json")["prefs"] as JObject ?? new JObject();
            return new JObject { { "spinSpeed", Pick(pf["spinMs"], 8500) }, { "mode", Pick(pf["mode"], "random") }, { "teamSize", Pick(pf["teamSize"], 2) }, { "oddPolicy", Pick(pf["oddPolicy"], "waitlist") }, { "eligibility", Pick(pf["eligibility"], "all") },
                { "autoReopen", Pick(pf["autoNew"], true) }, { "holdTimeSec", Pick(pf["holdSec"], 40) }, { "joinFeedSec", Pick(pf["feedSec"], 2) }, { "showSignedUp", Pick(pf["showSignedUp"], true) } };
        }
        static List<TF> QueueFields() { return new List<TF> {
            Bool("open", "Queue open", false, "Open or close the customs queue."),
            Bool("recycler", "Recycler allowed", true, "Players who turned !recycle on go back to the end of the queue after a game."),
            Num("inactivityMinutes", "Close after idle", 0, 240, 5, "min", 15, "The queue closes by itself after this many minutes with no activity (0 = never)."),
            Num("strikeLimit", "Strikes that block joining", 1, 10, 1, "strikes", 3, "At this many strikes (temporary + permanent) a player cannot join customs or the tournament wheel.") }; }
        static JObject QueueValues()
        {
            var s = ReadState("live_state.json");
            return new JObject { { "open", Pick(s["queueOpen"], false) }, { "recycler", Pick(s["recyclerEnabled"], true) }, { "inactivityMinutes", Pick(s["inactivityMinutes"], 15) }, { "strikeLimit", Pick(s["strikeLimit"], 3) } };
        }
        static List<TF> GamblingFields() { return new List<TF> {
            Bool("enabled", "Gambling on", true, "Master switch for !gamble, !slots, !duel and !give."),
            Num("winChance", "Win chance (!gamble)", 0, 1, 0.01, null, 0.45, "Chance to win a !gamble, 0..1."),
            Num("payout", "Payout (!gamble)", 1, 100, 0.1, "x", 2.0, "A win pays this many times the bet."),
            Num("pairPayout", "Slots: pair", 0, 100, 0.1, "x", 1.5, "Payout for two matching symbols."),
            Num("triplePayout", "Slots: three of a kind", 0, 1000, 0.5, "x", 5.0, "Payout for three matching symbols."),
            Num("jackpotPayout", "Slots: jackpot", 0, 10000, 1, "x", 10.0, "Payout for three of the jackpot symbol."),
            Num("minBet", "Minimum bet", 1, 1000000000, 1, "points", 1, "Smallest allowed bet."),
            Num("maxBet", "Maximum bet", 1, 1000000000, 1, "points", JValue.CreateNull(), "Empty = no maximum bet.", true),
            Num("cooldownSec", "Cooldown per user", 0, 3600, 1, "s", 15, "Seconds between two bets by the same person."),
            Bool("slotsEnabled", "!slots on", true, ""), Bool("duelEnabled", "!duel on", true, ""), Bool("giveEnabled", "!give on", true, "") }; }
        static readonly Dictionary<string, string> GambleKey = new Dictionary<string, string> { { "enabled", "enabled" }, { "winChance", "gambleWinChance" }, { "payout", "gamblePayout" }, { "pairPayout", "slotsPairPayout" }, { "triplePayout", "slotsTriplePayout" }, { "jackpotPayout", "slotsJackpotPayout" }, { "minBet", "minBet" }, { "maxBet", "maxBet" }, { "cooldownSec", "cooldownSec" }, { "slotsEnabled", "slotsEnabled" }, { "duelEnabled", "duelEnabled" }, { "giveEnabled", "giveEnabled" } };
        static JObject GamblingValues()
        {
            var c = Gamble.Config(); var o = new JObject();
            foreach (var kv in GambleKey) { var v = c[kv.Value]; if (kv.Key == "maxBet" && (v == null || (double)v <= 0)) v = JValue.CreateNull(); o[kv.Key] = v ?? JValue.CreateNull(); }
            return o;
        }
        static List<TF> EconomyFields() { return new List<TF> {
            Bool("Earning", "Earning points", true, "Master switch for watch-time points."),
            Num("PointsPerMinute", "Points per minute", 0, 1000, 0.1, "points", 1.0, "Paid to everyone chatting while live."),
            Num("SubMultiplier", "Subscriber multiplier", 0, 20, 0.1, "x", 2.0, ""),
            Num("VipMultiplier", "VIP multiplier", 0, 20, 0.1, "x", 1.5, ""),
            Num("ModMultiplier", "Moderator multiplier", 0, 20, 0.1, "x", 1.0, ""),
            Bool("OnlyWhileLive", "Only while live", true, "Turn off to earn points while offline too (offline mode)."),
            Bool("ActivityBonus", "Chat activity bonus", true, "Extra points for chatting."),
            Num("ActivityLinesPerPoint", "Chat lines per bonus point", 1, 100, 1, "lines", 5, ""),
            Num("ActivityCapPer10Min", "Bonus cap per 10 min", 0, 100, 1, "points", 2, "") }; }
        static JObject EconomyValues() { var s = Economy.SettingsView(); var o = new JObject(); foreach (var f in EconomyFields()) o[f.Key] = s[f.Key] ?? JValue.CreateNull(); return o; }
        static List<TF> AliasFields() { return new List<TF> {
            Bool("enabled", "Fix typos in commands", true, "!jon, ! join and similar become the right command."),
            Bool("didYouMean", "Answer 'did you mean'", true, "A near miss of a known command gets one 'did you mean !join?' per person.") }; }
        static string CmdFixP { get { return Path.Combine(DataDir, "config", "cmdfix.json"); } }
        static JObject CmdFixDoc() { try { return JObject.Parse(File.ReadAllText(CmdFixP).TrimStart((char)0xFEFF)); } catch (Exception) { return new JObject(); } }
        static JObject AliasValues() { var c = CmdFixDoc(); return new JObject { { "enabled", (bool?)c["enabled"] != false }, { "didYouMean", (bool?)c["didYouMean"] != false } }; }

        static List<TF> ObsFields() { return new List<TF> { Bool("autoStartReplayBuffer", "Auto-start the replay buffer", true, "Starts the OBS replay buffer when OBS connects and when the stream or a recording starts. It only ever starts it, never toggles.") }; }
        static JObject ObsValues() { return new JObject { { "autoStartReplayBuffer", ReplayBuf.AutoStart } }; }

        static readonly string[] AreaIds = { "wheel", "queue", "gambling", "economy", "alias", "obs" };
        static List<TF> Fields(string a) { return a == "wheel" ? WheelFields() : a == "queue" ? QueueFields() : a == "gambling" ? GamblingFields() : a == "economy" ? EconomyFields() : a == "alias" ? AliasFields() : a == "obs" ? ObsFields() : null; }
        static JObject Values(string a) { return a == "wheel" ? WheelValues() : a == "queue" ? QueueValues() : a == "gambling" ? GamblingValues() : a == "economy" ? EconomyValues() : a == "obs" ? ObsValues() : AliasValues(); }
        static JObject TuneGet()
        {
            var titles = new Dictionary<string, string[]> {
                { "wheel", new[] { "Tournament wheel", "Spin length, teams, odd player, how long the final teams stay and what the overlay shows." } },
                { "queue", new[] { "Customs queue", "Open/close, recycler and the idle timeout." } },
                { "gambling", new[] { "Gambling", "Chances, payouts, bet limits and cooldown for !gamble, !slots, !duel and !give." } },
                { "economy", new[] { "Points", "How points are earned." } },
                { "alias", new[] { "Command typos", "Near-miss command handling." } },
                { "obs", new[] { "OBS", "Replay buffer auto-start." } } };
            var areas = new JArray();
            foreach (var id in AreaIds)
            {
                var vals = Values(id); var fl = new JArray(); foreach (var f in Fields(id)) fl.Add(f.Json(vals[f.Key]));
                areas.Add(new JObject { { "id", id }, { "title", titles[id][0] }, { "help", titles[id][1] }, { "fields", fl } });
            }
            return new JObject { { "ok", true }, { "areas", areas } };
        }

        // validate one value against its spec; returns an error text (or null) and the clean token
        static string Clean(TF f, JToken v, out JToken clean)
        {
            clean = null;
            if (v == null || v.Type == JTokenType.Null) { if (f.Optional) { clean = JValue.CreateNull(); return null; } return f.Key + " cannot be empty"; }
            if (f.Type == "bool") { if (v.Type != JTokenType.Boolean) return f.Key + " must be true or false"; clean = v; return null; }
            if (f.Type == "select") { string s = ((string)v ?? "").ToLowerInvariant(); if (!f.Options.Contains(s)) return f.Key + " must be one of " + string.Join("|", f.Options); clean = s; return null; }
            double d;
            if (v.Type == JTokenType.Integer || v.Type == JTokenType.Float) d = Convert.ToDouble(((JValue)v).Value, CultureInfo.InvariantCulture);
            else if (v.Type != JTokenType.String || !double.TryParse((string)v, NumberStyles.Float, CultureInfo.InvariantCulture, out d)) return f.Key + " must be a number";
            if (double.IsNaN(d) || double.IsInfinity(d)) return f.Key + " must be a number";
            if (f.Min.HasValue) d = Math.Max(f.Min.Value, d); if (f.Max.HasValue) d = Math.Min(f.Max.Value, d);
            if (f.Step.HasValue && f.Step.Value >= 1) d = Math.Round(d); else if (f.Step.HasValue) d = Math.Round(d / f.Step.Value) * f.Step.Value;
            clean = d == Math.Floor(d) ? (JToken)(long)d : (JToken)Math.Round(d, 4); return null;
        }

        static JObject TunePost(JObject b)
        {
            string area = ((string)b["area"] ?? "").ToLowerInvariant(); var fl = Fields(area);
            if (fl == null) return new JObject { { "ok", false }, { "error", "unknown area" } };
            var vals = b["values"] as JObject; if (vals == null) return new JObject { { "ok", false }, { "error", "values required" } };
            var errors = new JObject(); var clean = new Dictionary<string, JToken>();
            foreach (var p in vals.Properties())
            {
                var f = fl.FirstOrDefault(x => x.Key == p.Name); if (f == null) { errors[p.Name] = "unknown key"; continue; }
                JToken cv; string e = Clean(f, p.Value, out cv); if (e != null) errors[p.Name] = e; else clean[p.Name] = cv;
            }
            var applied = new JObject();
            if (area == "wheel")
            {
                var cmd = new Dictionary<string, Func<JToken, string>> {
                    { "spinSpeed", v => "!tune wheel speed " + (long)v }, { "mode", v => "!tune wheel mode " + (string)v }, { "teamSize", v => "!tune wheel size " + (long)v }, { "oddPolicy", v => "!tune wheel odd " + (string)v }, { "eligibility", v => "!tune wheel eligibility " + (string)v },
                    { "autoReopen", v => "!tune wheel auto " + ((bool)v ? "on" : "off") }, { "holdTimeSec", v => "!tune wheel hold " + (long)v }, { "joinFeedSec", v => "!tune wheel feed " + Inv((double)v) }, { "showSignedUp", v => "!tune wheel signed " + ((bool)v ? "on" : "off") } };
                foreach (var kv in clean) { RunAsStreamer(cmd[kv.Key](kv.Value)); applied[kv.Key] = kv.Value; }
            }
            else if (area == "queue")
            {
                foreach (var kv in clean)
                {
                    if (kv.Key == "open") RunAsStreamer("!queue " + ((bool)kv.Value ? "open" : "close"));
                    else if (kv.Key == "recycler") RunAsStreamer("!tune recycler " + ((bool)kv.Value ? "on" : "off"));
                    else if (kv.Key == "strikeLimit") RunAsStreamer("!tune strikes " + (long)kv.Value);
                    else RunAsStreamer("!tune idle " + (long)kv.Value);
                    applied[kv.Key] = kv.Value;
                }
            }
            else if (area == "gambling")
            {
                var patch = new JObject(); foreach (var kv in clean) { patch[GambleKey[kv.Key]] = kv.Key == "maxBet" && kv.Value.Type == JTokenType.Null ? (JToken)0 : kv.Value; applied[kv.Key] = kv.Value; }
                if (patch.Count > 0) Gamble.SaveConfig(patch);
            }
            else if (area == "economy")
            {
                var patch = new JObject(); foreach (var kv in clean) { patch[kv.Key] = kv.Value; applied[kv.Key] = kv.Value; }
                if (patch.Count > 0) Economy.SetSettings(patch);
            }
            else if (area == "obs")
            {
                foreach (var kv in clean) { if (kv.Key == "autoStartReplayBuffer") ReplayBuf.SetAutoStart((bool)kv.Value); applied[kv.Key] = kv.Value; }
            }
            else if (area == "alias")
            {
                var doc = CmdFixDoc(); foreach (var kv in clean) { doc[kv.Key] = kv.Value; applied[kv.Key] = kv.Value; }
                if (clean.Count > 0) { Directory.CreateDirectory(Path.GetDirectoryName(CmdFixP)); File.WriteAllText(CmdFixP, doc.ToString(), new UTF8Encoding(false)); }
            }
            Clog.Info("tune", area + ": " + string.Join(", ", applied.Properties().Select(p => p.Name + "=" + p.Value.ToString(Newtonsoft.Json.Formatting.None))) + (errors.Count > 0 ? " (errors: " + string.Join(", ", errors.Properties().Select(p => p.Name)) + ")" : ""));
            return new JObject { { "ok", errors.Count == 0 }, { "applied", applied }, { "errors", errors } };
        }

        static JObject GambleSim(JObject b)
        {
            string game = ((string)b["game"] ?? "gamble").ToLowerInvariant(); if (game == "bet") game = "gamble";
            if (game != "gamble" && game != "slots") return new JObject { { "ok", false }, { "error", "game must be gamble or slots" } };
            long bet = Math.Max(1, Math.Min(1000000000, (long)D2(b["bet"], 100))); int rounds = (int)Math.Max(1, Math.Min(1000, D2(b["rounds"], 100)));
            var r = Gamble.Simulate(game, bet, rounds); long net = (long)r["net"], wins = (long)r["wins"];
            var sample = new JArray();
            for (int i = 0; i < Math.Min(10, rounds); i++) { var one = Gamble.Simulate(game, bet, 1); long pay = (long)one["net"] + bet; sample.Add(new JObject { { "win", pay > 0 }, { "payout", pay }, { "net", (long)one["net"] } }); }
            return new JObject { { "ok", true }, { "game", game }, { "bet", bet }, { "rounds", rounds }, { "wins", wins }, { "losses", rounds - wins }, { "net", net }, { "avgPayout", Math.Round((double)(net + bet * rounds) / rounds, 2) }, { "sample", sample }, { "note", "simulation only: no points moved" } };
        }
        static double D2(JToken t, double d) { try { return t == null || t.Type == JTokenType.Null ? d : Convert.ToDouble(((JValue)t).Value, CultureInfo.InvariantCulture); } catch (Exception) { return d; } }

        /// <summary>routes added for the Suite; returns true when answered</summary>
        static bool TuneRoutes(HttpListenerContext c, string p, string m)
        {
            if (p == "/api/tune" && m == "GET") { Write(c, TuneGet().ToString(), "application/json"); return true; }
            if (p == "/api/tune" && m == "POST") { Write(c, TunePost(Body(c)).ToString(), "application/json"); return true; }
            if (m == "POST" && (p == "/api/wheel/spin" || p == "/api/wheel/new" || p == "/api/wheel/reset"))
            { RunAsStreamer("!wheel " + p.Substring("/api/wheel/".Length)); System.Threading.Thread.Sleep(600); Events.Kick(); Write(c, new JObject { { "ok", true }, { "wheel", Events.WheelState() } }.ToString(), "application/json"); return true; }
            if (p == "/api/gamble/simulate" && m == "POST") { Write(c, GambleSim(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/economy/grant" && m == "POST") { var b = Body(c); if (b["by"] == null) b["by"] = "suite"; Write(c, Economy.Grant(b).ToString(), "application/json"); return true; }
            return false;
        }
    }
}
