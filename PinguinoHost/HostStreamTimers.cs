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
    /// <summary>On-stream countdown and stopwatch (the engine behind the site's /overlay/timer). The Host keeps ABSOLUTE timestamps in Data\runtime\stream_timers.json, so the overlay is only a
    /// clock renderer and a restart loses nothing. A countdown can grow on subs / gifted subs / bits (subathon mode) and says a line and/or runs an Automation at zero.
    /// Mods: !countdown 10m [label] | pause | resume | stop, !stopwatch start|stop|reset, !addtime <time> (negative takes time off), !stoptimer. API: GET/POST /api/stream-timers.</summary>
    public static class StreamTimers
    {
        static readonly object L = new object();
        static JObject _doc; static bool _started;
        static string PathF { get { return System.IO.Path.Combine(HostApi.DataDir, "stream_timers.json"); } }
        static long NowMs() { return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(); }

        /// <summary>"90", "90s", "10m", "1h30m", "1:30:00", "10:00" (mm:ss), "-2m". Bare numbers use defaultUnit ('s' or 'm'). Returns seconds, false when it is not a time.</summary>
        public static bool TryParseDuration(string s, char defaultUnit, out long seconds)
        {
            seconds = 0; s = (s ?? "").Trim().ToLowerInvariant(); if (s == "") return false;
            int sign = 1; if (s.StartsWith("-")) { sign = -1; s = s.Substring(1); } else if (s.StartsWith("+")) s = s.Substring(1);
            var inv = CultureInfo.InvariantCulture; double d;
            var colon = Regex.Match(s, @"^(?:(\d+):)?(\d{1,3}):(\d{2})$");
            if (colon.Success) { long h = colon.Groups[1].Success ? long.Parse(colon.Groups[1].Value) : 0; seconds = sign * (h * 3600 + long.Parse(colon.Groups[2].Value) * 60 + long.Parse(colon.Groups[3].Value)); if (!colon.Groups[1].Success) { seconds = sign * (long.Parse(colon.Groups[2].Value) * 60 + long.Parse(colon.Groups[3].Value)); } return true; }
            if (double.TryParse(s, NumberStyles.Float, inv, out d)) { seconds = sign * (long)Math.Round(d * (defaultUnit == 'm' ? 60 : 1)); return true; }
            var m = Regex.Match(s, @"^(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s)?$");
            if (!m.Success || (!m.Groups[1].Success && !m.Groups[2].Success && !m.Groups[3].Success)) return false;
            double tot = 0; if (m.Groups[1].Success) tot += double.Parse(m.Groups[1].Value, inv) * 3600; if (m.Groups[2].Success) tot += double.Parse(m.Groups[2].Value, inv) * 60; if (m.Groups[3].Success) tot += double.Parse(m.Groups[3].Value, inv);
            seconds = sign * (long)Math.Round(tot); return true;
        }
        public static string Fmt(long sec) { if (sec < 0) sec = 0; return sec >= 3600 ? (sec / 3600) + ":" + ((sec % 3600) / 60).ToString("D2") + ":" + (sec % 60).ToString("D2") : (sec / 60) + ":" + (sec % 60).ToString("D2"); }

        static JObject Doc()
        {
            if (_doc != null) return _doc;
            try { if (File.Exists(PathF)) _doc = JObject.Parse(File.ReadAllText(PathF, Encoding.UTF8)); } catch (Exception) { }
            if (_doc == null) _doc = new JObject { { "version", 1 }, { "timers", new JArray() } };
            if (_doc["timers"] == null) _doc["timers"] = new JArray();
            return _doc;
        }
        static void Save() { try { string tmp = PathF + ".tmp"; File.WriteAllText(tmp, _doc.ToString(), new UTF8Encoding(false)); if (File.Exists(PathF)) File.Delete(PathF); File.Move(tmp, PathF); } catch (Exception ex) { Clog.Warn("streamtimers", "could not save: " + ex.Message); } }
        static IEnumerable<JObject> All() { return ((JArray)Doc()["timers"]).OfType<JObject>(); }
        static JObject Find(string id) { id = (id ?? "").Trim().ToLowerInvariant(); return All().FirstOrDefault(t => ((string)t["id"]) == id); }

        public static void Start()
        {
            if (_started) return; _started = true;
            var th = new Thread(() => { Thread.Sleep(3000); while (true) { try { Tick(); } catch (Exception ex) { Clog.Warn("streamtimers", "tick: " + ex.Message); } Thread.Sleep(500); } }) { IsBackground = true };
            th.Start();
        }

        // ---- state helpers ----
        static long RemainingMs(JObject t, long now)
        {
            if ((string)t["type"] != "countdown") return 0;
            if ((bool?)t["paused"] == true) return Math.Max(0, (long?)t["remainingMs"] ?? 0);
            return Math.Max(0, ((long?)t["endsAt"] ?? now) - now);
        }
        static long ElapsedMs(JObject t, long now)
        {
            if ((string)t["type"] != "stopwatch") return 0;
            if ((bool?)t["running"] != true) return Math.Max(0, (long?)t["elapsedMs"] ?? 0);
            return Math.Max(0, (long?)t["elapsedMs"] ?? 0) + Math.Max(0, now - ((long?)t["startedAt"] ?? now));
        }

        static void Tick()
        {
            if (!Lease.MayRun) return;
            var fire = new List<JObject>(); long now = NowMs();
            lock (L)
            {
                foreach (var t in All())
                    if ((string)t["type"] == "countdown" && (bool?)t["paused"] != true && (bool?)t["done"] != true && RemainingMs(t, now) <= 0) { t["done"] = true; fire.Add((JObject)t.DeepClone()); }
                if (fire.Count > 0) Save();
            }
            foreach (var t in fire)
            {
                string say = ((string)t["onZero"]?["say"] ?? "").Trim(), auto = ((string)t["onZero"]?["automation"] ?? "").Trim();
                if (say != "") { string via; HostApi.SendAs("core", Auto.Expand(say, new Dictionary<string, string> { { "label", (string)t["label"] ?? "" } }), out via); }
                if (auto != "") try { Auto.Test(auto, null, false); } catch (Exception ex) { Clog.Warn("streamtimers", "onZero automation failed: " + ex.Message); }
                Clog.Info("streamtimers", "countdown " + (string)t["id"] + " reached zero");
            }
        }

        // ---- subathon: subs / gifts / bits add time to a countdown that asks for it ----
        public static void OnEvent(Dictionary<string, object> a)
        {
            try
            {
                object et; if (!a.TryGetValue("eventType", out et)) return; string ty = Convert.ToString(et); long addSec = 0; object n;
                lock (L)
                {
                    foreach (var t in All())
                    {
                        if ((string)t["type"] != "countdown" || (bool?)t["done"] == true) continue;
                        var add = t["add"] as JObject; if (add == null) continue;
                        long sec = 0;
                        if (ty == "TwitchSub" || ty == "TwitchReSub") sec = (long?)add["sub"] ?? 0;
                        else if (ty == "TwitchGiftBomb") { a.TryGetValue("total", out n); sec = ((long?)add["gift"] ?? 0) * (n == null ? 1 : Convert.ToInt64(n)); }
                        else if (ty == "TwitchCheer") { a.TryGetValue("bits", out n); sec = ((long?)add["bitsPer100"] ?? 0) * ((n == null ? 0 : Convert.ToInt64(n)) / 100); }
                        if (sec == 0) continue;
                        Shift(t, sec * 1000); addSec += sec;
                    }
                    if (addSec != 0) Save();
                }
            }
            catch (Exception ex) { Clog.Warn("streamtimers", "event: " + ex.Message); }
        }
        static void Shift(JObject t, long ms)
        {
            if ((bool?)t["paused"] == true) t["remainingMs"] = Math.Max(0, ((long?)t["remainingMs"] ?? 0) + ms); else t["endsAt"] = Math.Max(NowMs(), ((long?)t["endsAt"] ?? NowMs()) + ms);
            t["done"] = false;
        }

        // ---- API ----
        public static JObject Api(string only = null)
        {
            lock (L)
            {
                long now = NowMs();
                var list = new JArray(All().Where(t => string.IsNullOrEmpty(only) || (string)t["id"] == only.ToLowerInvariant()).Select(t =>
                {
                    var c = (JObject)t.DeepClone(); bool cd = (string)t["type"] == "countdown";
                    c["state"] = cd ? ((bool?)t["done"] == true ? "done" : (bool?)t["paused"] == true ? "paused" : "running") : ((bool?)t["running"] == true ? "running" : "stopped");
                    if (cd) { c["remainingMs"] = RemainingMs(t, now); c["text"] = Fmt(RemainingMs(t, now) / 1000); } else { c["elapsedMs"] = ElapsedMs(t, now); c["text"] = Fmt(ElapsedMs(t, now) / 1000); }
                    return c;
                }));
                return new JObject { { "ok", true }, { "nowMs", now }, { "timers", list } };
            }
        }

        /// <summary>{action:"countdown"|"stopwatch-start"|"stopwatch-stop"|"stopwatch-reset"|"pause"|"resume"|"add"|"stop"|"delete", id?, seconds?, label?, add:{sub,gift,bitsPer100}, onZero:{say,automation}}</summary>
        public static JObject Post(JObject b)
        {
            string action = ((string)b["action"] ?? "").ToLowerInvariant(); string id = ((string)b["id"] ?? "").Trim().ToLowerInvariant();
            lock (L)
            {
                var arr = (JArray)Doc()["timers"]; long now = NowMs();
                switch (action)
                {
                    case "countdown":
                    {
                        long sec = (long?)b["seconds"] ?? 0; if (sec <= 0) return Err("seconds must be more than 0"); if (sec > 7L * 86400) return Err("at most 7 days");
                        if (id == "") id = "countdown"; var old = Find(id); if (old != null) arr.Remove(old);
                        var t = new JObject { { "id", id }, { "type", "countdown" }, { "label", ((string)b["label"] ?? "").Trim() }, { "endsAt", now + sec * 1000 }, { "paused", false }, { "done", false }, { "createdAt", now } };
                        if (b["add"] is JObject add) t["add"] = add; if (b["onZero"] is JObject oz) t["onZero"] = oz;
                        arr.Add(t); Save(); return Api(id);
                    }
                    case "stopwatch-start":
                    {
                        if (id == "") id = "stopwatch"; var t = Find(id);
                        if (t == null) { t = new JObject { { "id", id }, { "type", "stopwatch" }, { "label", ((string)b["label"] ?? "").Trim() }, { "elapsedMs", 0 }, { "running", false }, { "startedAt", 0 } }; arr.Add(t); }
                        if ((string)t["type"] != "stopwatch") return Err("that id is a countdown");
                        if ((bool?)t["running"] != true) { t["running"] = true; t["startedAt"] = now; }
                        if (!string.IsNullOrWhiteSpace((string)b["label"])) t["label"] = ((string)b["label"]).Trim();
                        Save(); return Api(id);
                    }
                    case "stopwatch-stop":
                    {
                        if (id == "") id = "stopwatch"; var t = Find(id); if (t == null || (string)t["type"] != "stopwatch") return Err("no stopwatch");
                        t["elapsedMs"] = ElapsedMs(t, now); t["running"] = false; Save(); return Api(id);
                    }
                    case "stopwatch-reset":
                    {
                        if (id == "") id = "stopwatch"; var t = Find(id); if (t == null || (string)t["type"] != "stopwatch") return Err("no stopwatch");
                        t["elapsedMs"] = 0; t["startedAt"] = (bool?)t["running"] == true ? now : 0; Save(); return Api(id);
                    }
                    case "pause":
                    {
                        if (id == "") id = "countdown"; var t = Find(id); if (t == null || (string)t["type"] != "countdown") return Err("no countdown");
                        if ((bool?)t["paused"] != true) { t["remainingMs"] = RemainingMs(t, now); t["paused"] = true; } Save(); return Api(id);
                    }
                    case "resume":
                    {
                        if (id == "") id = "countdown"; var t = Find(id); if (t == null || (string)t["type"] != "countdown") return Err("no countdown");
                        if ((bool?)t["paused"] == true) { t["endsAt"] = now + ((long?)t["remainingMs"] ?? 0); t["paused"] = false; } Save(); return Api(id);
                    }
                    case "add":
                    {
                        if (id == "") id = "countdown"; var t = Find(id); if (t == null || (string)t["type"] != "countdown") return Err("no countdown");
                        long sec = (long?)b["seconds"] ?? 0; if (sec == 0) return Err("seconds is 0"); Shift(t, sec * 1000); Save(); return Api(id);
                    }
                    case "stop": case "delete":
                    {
                        if (id == "") { arr.Clear(); Save(); return Api(); }
                        var t = Find(id); if (t == null) return Err("no such timer"); arr.Remove(t); Save(); return Api();
                    }
                }
                return Err("unknown action");
            }
        }
        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }

        // ---- chat (mods) ----
        public static bool IsCommand(string cmd) { return cmd == "!countdown" || cmd == "!stopwatch" || cmd == "!addtime" || cmd == "!stoptimer"; }
        public static void Handle(string cmd, string[] args, Action<string> say)
        {
            try
            {
                if (cmd == "!stoptimer") { Post(new JObject { { "action", "stop" } }); say("All on-stream timers cleared."); return; }
                if (cmd == "!addtime")
                {
                    long s; if (args.Length < 1 || !TryParseDuration(args[0], 'm', out s) || s == 0) { say("Usage: !addtime <time> (like 5m, 90s, -2m)"); return; }
                    var r = Post(new JObject { { "action", "add" }, { "seconds", s } });
                    if ((bool?)r["ok"] == false) { say("No countdown is running."); return; }
                    var t = ((JArray)r["timers"]).FirstOrDefault(); say((s > 0 ? "Added " : "Took off ") + Fmt(Math.Abs(s)) + ". Countdown now " + (string)t["text"] + "."); return;
                }
                if (cmd == "!stopwatch")
                {
                    string sub = args.Length > 0 ? args[0].ToLowerInvariant() : "start";
                    if (sub == "start") { var r = Post(new JObject { { "action", "stopwatch-start" }, { "label", string.Join(" ", args.Skip(1)) } }); say("Stopwatch running."); return; }
                    if (sub == "stop") { var r = Post(new JObject { { "action", "stopwatch-stop" } }); say((bool?)r["ok"] == false ? "No stopwatch." : "Stopwatch stopped at " + (string)((JArray)r["timers"]).First()["text"] + "."); return; }
                    if (sub == "reset") { var r = Post(new JObject { { "action", "stopwatch-reset" } }); say((bool?)r["ok"] == false ? "No stopwatch." : "Stopwatch reset."); return; }
                    say("!stopwatch start [label] | stop | reset"); return;
                }
                // !countdown
                string first = args.Length > 0 ? args[0].ToLowerInvariant() : "";
                if (first == "pause" || first == "resume" || first == "stop")
                {
                    var r = Post(new JObject { { "action", first == "stop" ? "delete" : first }, { "id", "countdown" } });
                    say((bool?)r["ok"] == false ? "No countdown is running." : first == "pause" ? "Countdown paused." : first == "resume" ? "Countdown running again." : "Countdown stopped."); return;
                }
                long secs; if (args.Length < 1 || !TryParseDuration(args[0], 'm', out secs) || secs <= 0) { say("Usage: !countdown <time> [label] (like 10m, 1h30m, 90s) | pause | resume | stop"); return; }
                var res = Post(new JObject { { "action", "countdown" }, { "seconds", secs }, { "label", string.Join(" ", args.Skip(1)) }, { "onZero", new JObject { { "say", "Time's up" + (args.Length > 1 ? ": " + string.Join(" ", args.Skip(1)) : "") + "!" } } } });
                say((bool?)res["ok"] == false ? (string)res["error"] : "Countdown started: " + Fmt(secs) + (args.Length > 1 ? " (" + string.Join(" ", args.Skip(1)) + ")" : "") + ".");
            }
            catch (Exception ex) { Clog.Warn("streamtimers", "command failed: " + ex.Message); say("That timer command failed, see the log."); }
        }
    }
}
