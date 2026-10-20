using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Chat timers: repeating chat messages that survive restarts. Data\runtime\timers.json holds the timers AND their state (lastRun, nextIndex), so a restart does not
    /// fire everything at once or reset the clocks. A timer only fires while the stream is live (onlineOnly), after "everySec" (min 60) and "minChatMessages" new chat lines, and never
    /// closer than "globalGapSec" to any other timer. Messages rotate, pick at random, or all go out (mode). A timer can run an Automation instead of (or after) its messages.
    /// Mods: !timer list | on <name> | off <name> | add <minutes> <message> | remove <name> | now <name> | gap <seconds>. API: GET/POST /api/timers.</summary>
    public static class Timers
    {
        static readonly object L = new object();
        static JObject _doc; static bool _started; static long _lastAny; static readonly Random Rng = new Random();
        static bool Fast { get { return Environment.GetEnvironmentVariable("PINGUINO_TIMERS_FAST") == "1"; } }          // tests: allow everySec < 60 and a quick loop
        static int MinEvery { get { return Fast ? 1 : 60; } }
        static string PathF { get { return System.IO.Path.Combine(HostApi.DataDir, "timers.json"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        static bool IsLive()
        {
            string o = Environment.GetEnvironmentVariable("PINGUINO_TIMERS_LIVE"); if (o == "1") return true; if (o == "0") return false;
            return LiveState.Live == true;
        }

        static JObject Doc()
        {
            if (_doc != null) return _doc;
            try { if (File.Exists(PathF)) _doc = JObject.Parse(File.ReadAllText(PathF, Encoding.UTF8)); } catch (Exception ex) { Clog.Warn("timers", "timers.json unreadable: " + ex.Message); }
            if (_doc == null)
            {
                _doc = new JObject { { "version", 1 }, { "globalGapSec", 60 }, { "timers", new JArray(
                    Mk("follow", "Follow reminder", 900, 10, "If you're enjoying the stream, a follow means a lot! innoce108Hello"),
                    Mk("commands", "Commands", 1200, 10, "All the chat commands with search: https://innocentpenguin.com/help#commands"),
                    Mk("leaderboards", "Leaderboards", 1800, 10, "Top gifters, bitters, yappers and watch streaks: https://innocentpenguin.com/leaderboards")) } };
                Save();
            }
            if (_doc["timers"] == null) _doc["timers"] = new JArray();
            return _doc;
        }
        static JObject Mk(string id, string name, int every, int minMsgs, params string[] msgs)
        {   // the samples start DISABLED: Ivan switches on the ones he wants
            return new JObject { { "id", id }, { "name", name }, { "enabled", false }, { "everySec", every }, { "minChatMessages", minMsgs }, { "onlineOnly", true }, { "mode", "rotate" }, { "messages", new JArray(msgs) }, { "automation", "" }, { "lastRun", 0 }, { "nextIndex", 0 } };
        }
        static void Save() { try { string tmp = PathF + ".tmp"; File.WriteAllText(tmp, _doc.ToString(), new UTF8Encoding(false)); if (File.Exists(PathF)) File.Delete(PathF); File.Move(tmp, PathF); } catch (Exception ex) { Clog.Warn("timers", "could not save timers.json: " + ex.Message); } }
        static IEnumerable<JObject> All() { return ((JArray)Doc()["timers"]).OfType<JObject>(); }
        static JObject Find(string key)
        {
            key = (key ?? "").Trim().TrimStart('"').TrimEnd('"').ToLowerInvariant(); if (key == "") return null;
            return All().FirstOrDefault(t => ((string)t["id"] ?? "").ToLowerInvariant() == key) ?? All().FirstOrDefault(t => ((string)t["name"] ?? "").ToLowerInvariant() == key);
        }

        public static void Start()
        {
            if (_started) return; _started = true;
            _lastAny = Now();      // a restart never fires timers at once: the first one waits out the global gap
            var th = new Thread(() =>
            {
                Thread.Sleep(Fast ? 500 : 10000);
                while (true)
                {
                    try { Tick(); } catch (Exception ex) { Clog.Warn("timers", "tick failed: " + ex.Message); }
                    Thread.Sleep(Fast ? 300 : 5000);
                }
            }) { IsBackground = true };
            th.Start();
        }

        static long _msgBase = -1;
        static readonly Dictionary<string, long> MsgAt = new Dictionary<string, long>();     // chat line counter at each timer's last run (memory only: after a restart the gate counts from the restart)

        static void Tick()
        {
            if (!Lease.MayRun || !(HostApi.IrcConnected || HostApi.SimMode)) return;
            JObject due = null; long now = Now();
            lock (L)
            {
                var gap = (int?)Doc()["globalGapSec"] ?? 60;
                long msgs = HostApi.Messages;
                double bestOver = -1;
                foreach (var t in All())
                {
                    string id = (string)t["id"];
                    if (!MsgAt.ContainsKey(id)) MsgAt[id] = msgs;
                    if ((bool?)t["enabled"] != true) continue;
                    long last = (long?)t["lastRun"] ?? 0;
                    if (last == 0) { t["lastRun"] = now; Save(); continue; }              // never ran: the clock starts now, not at once
                    if ((bool?)t["onlineOnly"] != false && !IsLive()) continue;
                    int every = Math.Max(MinEvery, (int?)t["everySec"] ?? 900);
                    if (now - last < every) continue;
                    if (msgs - MsgAt[id] < ((int?)t["minChatMessages"] ?? 0)) continue;
                    if (now - _lastAny < gap) continue;
                    double over = (now - last) - every;
                    if (over > bestOver) { bestOver = over; due = t; }
                }
            }
            if (due != null) Fire(due, false);
        }

        // sends the timer's message(s) / runs its automation, then records the run
        static string Fire(JObject t, bool manual)
        {
            var parts = new List<string>(); string automation;
            lock (L)
            {
                var msgs = ((JArray)t["messages"] ?? new JArray()).Select(x => (string)x).Where(x => !string.IsNullOrWhiteSpace(x)).ToList();
                string mode = ((string)t["mode"] ?? "rotate").ToLowerInvariant(); int idx = (int?)t["nextIndex"] ?? 0;
                if (msgs.Count > 0)
                {
                    if (mode == "all") parts.AddRange(msgs);
                    else if (mode == "random") { int pick = msgs.Count == 1 ? 0 : Rng.Next(msgs.Count); if (msgs.Count > 1 && pick == (idx - 1 + msgs.Count) % msgs.Count) pick = (pick + 1) % msgs.Count; parts.Add(msgs[pick]); t["nextIndex"] = pick + 1; }
                    else { parts.Add(msgs[idx % msgs.Count]); t["nextIndex"] = (idx + 1) % msgs.Count; }
                }
                automation = ((string)t["automation"] ?? "").Trim();
                t["lastRun"] = Now(); MsgAt[(string)t["id"]] = HostApi.Messages; _lastAny = Now(); Save();
            }
            var ctx = new Dictionary<string, string> { { "channel", ((string)HostApi.StreamerCreds()["Channel"] ?? "") }, { "timer", (string)t["name"] } };
            var thr = new Thread(() =>
            {
                try
                {
                    for (int i = 0; i < parts.Count; i++)
                    {
                        string text = Auto.Expand(parts[i], ctx).Trim(); if (text == "") continue;
                        string via; HostApi.SendAs("core", text, out via);
                        if (i + 1 < parts.Count) Thread.Sleep(Fast ? 100 : 2500);
                    }
                    if (automation != "") Auto.Test(automation, null, false);
                }
                catch (Exception ex) { Clog.Warn("timers", "timer " + (string)t["id"] + " failed: " + ex.Message); }
            }) { IsBackground = true };
            thr.Start();
            Clog.Info("timers", "timer " + (string)t["id"] + (manual ? " fired by a mod" : " fired") + (parts.Count > 0 ? ": " + parts.Count + " message(s)" : "") + (automation != "" ? ", automation " + automation : ""));
            return (string)t["id"];
        }

        static string Slug(string s) { s = Regex.Replace((s ?? "").ToLowerInvariant(), "[^a-z0-9]+", "-").Trim('-'); return s.Length > 30 ? s.Substring(0, 30).Trim('-') : s; }

        // ---- API ----
        public static JObject Api()
        {
            lock (L)
            {
                long now = Now();
                var list = new JArray(All().Select(t =>
                {
                    long last = (long?)t["lastRun"] ?? 0; int every = Math.Max(MinEvery, (int?)t["everySec"] ?? 900);
                    var c = (JObject)t.DeepClone(); c["nextInSec"] = last == 0 ? every : Math.Max(0, (int)(last + every - now)); return c;
                }));
                return new JObject { { "ok", true }, { "live", IsLive() }, { "globalGapSec", (int?)Doc()["globalGapSec"] ?? 60 }, { "minEverySec", MinEvery }, { "timers", list } };
            }
        }

        /// <summary>{timer:{id?,name,enabled,everySec,minChatMessages,onlineOnly,mode,messages[],automation}} to add/update | {id,enabled} | {delete:id} | {now:id} | {globalGapSec:n}</summary>
        public static JObject Post(JObject b)
        {
            lock (L)
            {
                var doc = Doc(); var arr = (JArray)doc["timers"];
                if (b["globalGapSec"] != null) { doc["globalGapSec"] = Math.Max(0, Math.Min(3600, (int)b["globalGapSec"])); Save(); }
                if (b["delete"] != null) { var d = Find((string)b["delete"]); if (d == null) return Err("no such timer"); arr.Remove(d); Save(); return Api(); }
                if (b["now"] != null) { var n = Find((string)b["now"]); if (n == null) return Err("no such timer"); Fire(n, true); return Api(); }
                if (b["timer"] is JObject tj)
                {
                    string name = ((string)tj["name"] ?? "").Trim(); string id = Slug(((string)tj["id"] ?? "") != "" ? (string)tj["id"] : name);
                    if (id == "") return Err("a timer needs a name");
                    var t = Find(id);
                    if (t == null) { t = Mk(id, name == "" ? id : name, 900, 10); t["enabled"] = (bool?)tj["enabled"] ?? false; arr.Add(t); }
                    if (name != "") t["name"] = name;
                    if (tj["enabled"] != null) t["enabled"] = (bool)tj["enabled"];
                    if (tj["everySec"] != null) t["everySec"] = Math.Max(MinEvery, Math.Min(86400, (int)tj["everySec"]));
                    if (tj["minChatMessages"] != null) t["minChatMessages"] = Math.Max(0, Math.Min(1000, (int)tj["minChatMessages"]));
                    if (tj["onlineOnly"] != null) t["onlineOnly"] = (bool)tj["onlineOnly"];
                    if (tj["mode"] != null) { string m = ((string)tj["mode"]).ToLowerInvariant(); t["mode"] = m == "random" || m == "all" ? m : "rotate"; }
                    if (tj["messages"] is JArray ms) { t["messages"] = new JArray(ms.Select(x => ((string)x ?? "").Trim()).Where(x => x != "").Select(x => x.Length > 450 ? x.Substring(0, 450) : x)); t["nextIndex"] = 0; }
                    if (tj["automation"] != null) t["automation"] = ((string)tj["automation"] ?? "").Trim();
                    Save(); return Api();
                }
                if (b["id"] != null && b["enabled"] != null) { var t = Find((string)b["id"]); if (t == null) return Err("no such timer"); t["enabled"] = (bool)b["enabled"]; if ((bool)b["enabled"]) t["lastRun"] = Now(); Save(); return Api(); }
                return Err("nothing to do");
            }
        }
        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }

        // ---- chat (mods only) ----
        public static bool IsCommand(string cmd) { return cmd == "!timer" || cmd == "!timers"; }
        public static void Handle(string[] args, Action<string> say)
        {
            string sub = args.Length > 0 ? args[0].ToLowerInvariant() : "list";
            try
            {
                if (sub == "list")
                {
                    var api = Api(); var ts = (JArray)api["timers"];
                    if (ts.Count == 0) { say("No timers yet. !timer add <minutes> <message>"); return; }
                    say("Timers (" + (((bool)api["live"]) ? "live" : "offline") + ", gap " + (int)api["globalGapSec"] + "s): " + string.Join(" | ", ts.Select(t => ((bool)t["enabled"] ? "ON " : "off ") + (string)t["id"] + " every " + ((int)t["everySec"] / 60) + "m")));
                    return;
                }
                if (sub == "on" || sub == "off")
                {
                    string key = string.Join(" ", args.Skip(1)); lock (L) { var t = Find(key); if (t == null) { say("No timer called '" + key + "'. !timer list"); return; } }
                    Post(new JObject { { "id", key }, { "enabled", sub == "on" } }); say("Timer " + key + " is " + sub.ToUpperInvariant() + "."); return;
                }
                if (sub == "remove" || sub == "delete")
                {
                    string key = string.Join(" ", args.Skip(1)); var r = Post(new JObject { { "delete", key } });
                    say((bool?)r["ok"] == false ? "No timer called '" + key + "'." : "Timer " + key + " removed."); return;
                }
                if (sub == "now")
                {
                    string key = string.Join(" ", args.Skip(1)); var r = Post(new JObject { { "now", key } });
                    say((bool?)r["ok"] == false ? "No timer called '" + key + "'." : "Timer " + key + " sent."); return;
                }
                if (sub == "gap")
                {
                    int g; if (args.Length < 2 || !int.TryParse(args[1], out g)) { say("Usage: !timer gap <seconds> (the quiet time between any two timers)"); return; }
                    Post(new JObject { { "globalGapSec", g } }); say("Timers now keep at least " + Math.Max(0, Math.Min(3600, g)) + "s apart."); return;
                }
                if (sub == "add")
                {
                    double min; if (args.Length < 3 || !double.TryParse(args[1], NumberStyles.Float, CultureInfo.InvariantCulture, out min) || min <= 0) { say("Usage: !timer add <minutes> <message>"); return; }
                    string msg = string.Join(" ", args.Skip(2)); string id = Slug(msg.Split(' ').Take(3).Aggregate((a, b) => a + " " + b)); if (id == "") id = "timer";
                    lock (L) { string baseId = id; int n = 2; while (Find(id) != null) id = baseId + "-" + n++; }
                    var r = Post(new JObject { { "timer", new JObject { { "id", id }, { "name", id }, { "enabled", true }, { "everySec", (int)Math.Round(min * 60) }, { "messages", new JArray(msg) } } } });
                    say("Timer '" + id + "' added: every " + min.ToString("0.#", CultureInfo.InvariantCulture) + " min while live. (!timer off " + id + " / !timer remove " + id + ")"); return;
                }
                say("!timer list | on <name> | off <name> | add <minutes> <message> | remove <name> | now <name> | gap <seconds>");
            }
            catch (Exception ex) { Clog.Warn("timers", "command failed: " + ex.Message); say("The timer command failed, see the log."); }
        }
    }
}
