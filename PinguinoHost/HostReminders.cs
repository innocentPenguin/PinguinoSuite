using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>!remindme 30m text: the bot @mentions you in chat when it is due. Persisted in Data\runtime\reminders.json, so it survives a restart (delivered late with a note).
    /// Viewers: !remindme <time> <text> (max 3 open each, 1 min to 24 h), !reminders, !cancelreminder [number]. Mods: !remind @user <time> <text>.</summary>
    public static class Reminders
    {
        static readonly object L = new object();
        static JObject _doc; static bool _started;
        const int MaxPerUser = 3; const int MinSec = 60, MaxSec = 86400;
        static string PathF { get { return System.IO.Path.Combine(HostApi.DataDir, "reminders.json"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        static bool Fast { get { return Environment.GetEnvironmentVariable("PINGUINO_TIMERS_FAST") == "1"; } }

        static JObject Doc()
        {
            if (_doc != null) return _doc;
            try { if (File.Exists(PathF)) _doc = JObject.Parse(File.ReadAllText(PathF, Encoding.UTF8)); } catch (Exception) { }
            if (_doc == null) _doc = new JObject { { "version", 1 }, { "seq", 0 }, { "reminders", new JArray() } };
            if (_doc["reminders"] == null) _doc["reminders"] = new JArray();
            return _doc;
        }
        static void Save() { try { string tmp = PathF + ".tmp"; File.WriteAllText(tmp, _doc.ToString(), new UTF8Encoding(false)); if (File.Exists(PathF)) File.Delete(PathF); File.Move(tmp, PathF); } catch (Exception ex) { Clog.Warn("reminders", "could not save: " + ex.Message); } }
        static IEnumerable<JObject> All() { return ((JArray)Doc()["reminders"]).OfType<JObject>(); }

        public static void Start()
        {
            if (_started) return; _started = true;
            var th = new Thread(() => { Thread.Sleep(Fast ? 300 : 8000); while (true) { try { Tick(); } catch (Exception ex) { Clog.Warn("reminders", "tick: " + ex.Message); } Thread.Sleep(Fast ? 300 : 5000); } }) { IsBackground = true };
            th.Start();
        }

        static void Tick()
        {
            if (!Lease.MayRun || !(HostApi.IrcConnected || HostApi.SimMode)) return;
            var due = new List<JObject>(); long now = Now();
            lock (L)
            {
                foreach (var r in All().Where(r => ((long?)r["at"] ?? 0) <= now).OrderBy(r => (long)r["at"]).Take(3)) due.Add((JObject)r.DeepClone());   // a few per tick: never a flood after a long downtime
                if (due.Count > 0) { var arr = (JArray)Doc()["reminders"]; foreach (var d in due) { var o = arr.OfType<JObject>().FirstOrDefault(x => (string)x["id"] == (string)d["id"]); if (o != null) arr.Remove(o); } Save(); }
            }
            foreach (var r in due)
            {
                long late = now - (long)r["at"]; string who = (string)r["display"] ?? (string)r["login"];
                string line = "@" + who + " reminder: " + (string)r["text"] + (late > 120 ? " (sorry, this is " + (late >= 3600 ? (late / 3600) + "h" : (late / 60) + "m") + " late)" : "") + ((string)r["by"] != "" && (string)r["by"] != (string)r["login"] ? " (from " + (string)r["by"] + ")" : "");
                string via; HostApi.SendAs("core", line, out via);
            }
        }

        static string Clean(string t) { t = (t ?? "").Trim(); t = System.Text.RegularExpressions.Regex.Replace(t, @"\s+", " "); t = t.TrimStart('!', '/', '.'); return t.Length > 250 ? t.Substring(0, 250) : t; }

        public static string Add(string login, string display, string by, long seconds, string text, bool mod)
        {
            text = Clean(text); if (text.Length < 1) return "Say what to remind you about: !remindme 30m take the pizza out";
            if (seconds < MinSec && !Fast) return "The shortest reminder is 1 minute.";
            if (seconds > MaxSec) return "The longest reminder is 24 hours.";
            lock (L)
            {
                if (!mod && All().Count(r => (string)r["login"] == login) >= MaxPerUser) return "You already have " + MaxPerUser + " reminders. !cancelreminder 1 removes one.";
                var d = Doc(); d["seq"] = ((int?)d["seq"] ?? 0) + 1;
                ((JArray)d["reminders"]).Add(new JObject { { "id", "r" + (int)d["seq"] }, { "login", login }, { "display", display }, { "by", by }, { "at", Now() + seconds }, { "created", Now() }, { "text", text } });
                Save();
            }
            return "OK @" + display + ", I'll remind you in " + StreamTimers.Fmt(seconds) + (seconds >= 3600 ? "" : " (min:sec)") + ".";
        }

        public static JObject Api(string login = null)
        {
            lock (L) return new JObject { { "ok", true }, { "reminders", new JArray(All().Where(r => string.IsNullOrEmpty(login) || (string)r["login"] == login).OrderBy(r => (long)r["at"]).Select(r => r.DeepClone())) } };
        }

        public static bool IsCommand(string cmd) { return cmd == "!remindme" || cmd == "!reminders" || cmd == "!cancelreminder" || cmd == "!remind"; }

        public static void Handle(string user, string cmd, string[] args, bool mod, Action<string> say)
        {
            string login = user.ToLowerInvariant();
            try
            {
                if (cmd == "!remindme")
                {
                    long s; if (args.Length < 2 || !StreamTimers.TryParseDuration(args[0], 'm', out s) || s <= 0) { say("Usage: !remindme <time> <what> - like !remindme 30m take the pizza out"); return; }
                    say(Add(login, user, login, s, string.Join(" ", args.Skip(1)), false)); return;
                }
                if (cmd == "!remind")
                {
                    long s; if (!mod) return;
                    if (args.Length < 3 || !StreamTimers.TryParseDuration(args[1], 'm', out s) || s <= 0) { say("Usage: !remind @user <time> <what>"); return; }
                    string target = args[0].TrimStart('@'); say(Add(target.ToLowerInvariant(), target, login, s, string.Join(" ", args.Skip(2)), true)); return;
                }
                if (cmd == "!reminders")
                {
                    var mine = ((JArray)Api(login)["reminders"]);
                    if (mine.Count == 0) { say("@" + user + " you have no reminders. !remindme 30m something"); return; }
                    long now = Now(); say("@" + user + " your reminders: " + string.Join(" | ", mine.Select((r, i) => (i + 1) + ") in " + StreamTimers.Fmt(Math.Max(0, (long)r["at"] - now)) + ": " + (string)r["text"]))); return;
                }
                if (cmd == "!cancelreminder")
                {
                    int n = 1; if (args.Length > 0) int.TryParse(args[0], out n);
                    lock (L)
                    {
                        var mine = All().Where(r => (string)r["login"] == login).OrderBy(r => (long)r["at"]).ToList();
                        if (mine.Count == 0) { say("@" + user + " you have no reminders."); return; }
                        if (n < 1 || n > mine.Count) { say("@" + user + " you have " + mine.Count + " reminder(s): !cancelreminder 1"); return; }
                        ((JArray)Doc()["reminders"]).Remove(mine[n - 1]); Save();
                    }
                    say("@" + user + " reminder " + n + " cancelled."); return;
                }
            }
            catch (Exception ex) { Clog.Warn("reminders", "command failed: " + ex.Message); }
        }
    }
}
