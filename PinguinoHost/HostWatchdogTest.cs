using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace PinguinoHost
{
    /// <summary>sim line "watchdogtest": a stalled step is named, a held dispatchLock names its holder and a chat waiting on it is reported (and still answered), a skipped timer tick is logged once.</summary>
    public static class WatchdogTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        public static void Run()
        {
            var lines = new List<string>(); Watchdog.Sink = (lv, t) => { lock (lines) lines.Add(lv + "|" + t); };
            Func<string, bool> has = k => { lock (lines) return lines.Any(l => l.Contains(k)); };
            Watchdog.StallSec = 20;
            // 1. a stuck step is named
            var gate = new ManualResetEventSlim(false); var started = new ManualResetEventSlim(false);
            var th = new Thread(() => { Watchdog.Begin("chat dispatch (twitch, !followage)"); Watchdog.Step("Economy.OnChat"); started.Set(); gate.Wait(5000); Watchdog.End(); }); th.Start(); started.Wait(2000);
            Watchdog.Scan(DateTime.UtcNow); Check(!has("stalled"), "no stall report inside 20 s");
            Watchdog.Scan(DateTime.UtcNow.AddSeconds(30)); Check(has("error|stalled 3") && has("!followage") && has("step 'Economy.OnChat'"), "stall over 20 s names the operation and the step: " + string.Join(" // ", lines.Where(l => l.Contains("stalled"))));
            int n1 = lines.Count(l => l.Contains("stalled")); Watchdog.Scan(DateTime.UtcNow.AddSeconds(35)); Check(lines.Count(l => l.Contains("stalled")) == n1, "the same stall is not repeated inside a minute");
            Check(has("info|heartbeat: pool workers busy"), "heartbeat line with thread-pool state");
            gate.Set(); th.Join();
            // 2. a held dispatchLock: a chat waiting on it is reported with the holder, and is still answered once it frees
            lock (lines) lines.Clear();
            var release = new ManualResetEventSlim(false); var holding = new ManualResetEventSlim(false);
            var holder = new Thread(() => { lock (Program.DispatchLockForTest) { Watchdog.Hold("chat !gamble"); holding.Set(); release.Wait(8000); Watchdog.Release(); } }); holder.Start(); holding.Wait(2000);
            bool done = false; var chat = Task.Run(() => { Program.Dispatch("wdviewer", "just saying hello to everyone", "wd-1", 1, "id-wd", false, null); done = true; });
            Thread.Sleep(600);
            Watchdog.Scan(DateTime.UtcNow.AddSeconds(30));
            Check(has("waiting for dispatchLock") && has("held by chat !gamble"), "chat waiting on the lock is named with the holder: " + string.Join(" // ", lines.Where(l => l.Contains("stalled"))));
            Check(!done, "the chat waits (not dropped) while the lock is held");
            Watchdog.NoteSkippedTick("web sync tick"); Watchdog.NoteSkippedTick("web sync tick");
            Check(lines.Count(l => l.Contains("web sync tick skipped")) == 1 && has("held") && has("by chat !gamble"), "a skipped tick is logged once with the holder");
            release.Set(); holder.Join(); Check(chat.Wait(8000) && done, "the waiting chat ran as soon as the lock was free");
            Check(Watchdog.Holder == "", "holder cleared after the chat");
            Watchdog.Sink = null; Console.WriteLine(fails == 0 ? "[watchdogtest] ALL PASS" : "[watchdogtest] FAILS " + fails);
        }
    }
}
