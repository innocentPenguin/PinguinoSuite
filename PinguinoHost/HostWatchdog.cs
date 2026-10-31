using System;
using System.Collections.Concurrent;
using System.Linq;
using System.Threading;

namespace PinguinoHost
{
    /// <summary>Names a stall while it happens (logging only, never restarts anything). Chat dispatches, events and the web-sync tick register as an operation and
    /// mark the step they are in; a dedicated thread (not the thread pool, so starvation cannot silence it) reports any operation older than StallSec with its
    /// step name and who holds dispatchLock, and writes a heartbeat with the thread-pool state every HeartbeatSec so starvation shows in host.jsonl.</summary>
    public static class Watchdog
    {
        class Op { public Op Parent; public string Name, Step = ""; public DateTime Start = DateTime.UtcNow, Reported = DateTime.MinValue; public int Thread = Environment.CurrentManagedThreadId; }
        static readonly ConcurrentDictionary<int, Op> ops = new ConcurrentDictionary<int, Op>();
        public static int StallSec = 20, HeartbeatSec = 60, ScanMs = 5000;
        public static Action<string, string> Sink;   // tests: (level, text); null = Clog
        static string _holder = ""; static DateTime _holderAt = DateTime.MinValue;
        static DateTime _lastDrop = DateTime.MinValue; static int _drops; static Thread _t; static DateTime _lastBeat = DateTime.MinValue;

        /// <summary>"!followage" from a chat line (the command word only, never the rest of the text).</summary>
        public static string CmdWord(string text)
        {
            string t = (text ?? "").TrimStart(); if (!t.StartsWith("!")) return "line";
            string w = t.Split(' ')[0]; return w.Length > 30 ? w.Substring(0, 30) : w;
        }
        /// <summary>A Begin inside a Begin on the same thread keeps the outer one: End brings it back (it keeps its own start time, so a stall in the outer op is still reported).</summary>
        public static void Begin(string name) { int t = Environment.CurrentManagedThreadId; Op o; ops.TryGetValue(t, out o); ops[t] = new Op { Name = name, Parent = o }; }
        public static void End() { int t = Environment.CurrentManagedThreadId; Op o; if (!ops.TryRemove(t, out o)) return; if (o.Parent != null) ops[t] = o.Parent; }
        public static void Step(string step) { Op o; if (ops.TryGetValue(Environment.CurrentManagedThreadId, out o)) o.Step = step; }
        /// <summary>This thread just got dispatchLock (what = what it will run); Release when it gives it back.</summary>
        public static void Hold(string what) { _holder = what ?? ""; _holderAt = DateTime.UtcNow; Step("running " + what); }
        public static void Release() { _holder = ""; }
        public static string Holder { get { return _holder; } }

        static void Log(string level, string text)
        {
            if (Sink != null) { Sink(level, text); return; }
            if (level == "error") Clog.Error("watchdog", text); else if (level == "warn") Clog.Warn("watchdog", text); else Clog.Info("watchdog", text);
        }

        /// <summary>A timer tick found dispatchLock busy and skipped: say who has it, at most once a minute (with how many were skipped).</summary>
        public static void NoteSkippedTick(string what)
        {
            _drops++;
            if ((DateTime.UtcNow - _lastDrop).TotalSeconds < 60) return;
            int n = _drops; _drops = 0; _lastDrop = DateTime.UtcNow;
            string h = _holder; double held = h == "" ? 0 : (DateTime.UtcNow - _holderAt).TotalSeconds;
            Log("warn", what + " skipped " + n + "x: dispatchLock busy" + (h != "" ? " (held " + (int)held + " s by " + h + ")" : ""));
        }

        public static void Start()
        {
            if (_t != null) return;
            _t = new Thread(() => { while (true) { Thread.Sleep(ScanMs); try { Scan(DateTime.UtcNow); } catch (Exception) { } } }) { IsBackground = true, Name = "pg-watchdog" };
            _t.Start();
        }

        /// <summary>One pass (the test calls it directly).</summary>
        public static void Scan(DateTime now)
        {
            foreach (var o in ops.Values.ToArray())
            {
                double s = (now - o.Start).TotalSeconds; if (s < StallSec || (now - o.Reported).TotalSeconds < 60) continue;
                o.Reported = now; string h = _holder;
                Log("error", "stalled " + (int)s + " s: " + o.Name + " (thread " + o.Thread + ") is in step '" + o.Step + "'; dispatchLock " + (h == "" ? "is free" : "is held by " + h + " for " + (int)(now - _holderAt).TotalSeconds + " s"));
            }
            if ((now - _lastBeat).TotalSeconds >= HeartbeatSec)
            {
                _lastBeat = now; int w, io, mw, mio; ThreadPool.GetAvailableThreads(out w, out io); ThreadPool.GetMaxThreads(out mw, out mio);
                Log("info", "heartbeat: pool workers busy " + (mw - w) + "/" + mw + ", io busy " + (mio - io) + "/" + mio + ", queued " + ThreadPool.PendingWorkItemCount + ", threads " + ThreadPool.ThreadCount + ", ops " + ops.Count + ", dispatchLock " + (_holder == "" ? "free" : "held by " + _holder));
            }
        }
    }
}
