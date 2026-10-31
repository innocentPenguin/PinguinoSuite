using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace PinguinoHost
{
    /// <summary>sim line "subfiletest": SubsImport.WriteAtomic / ReadShared under a concurrent read/write loop, with an outside reader that holds the file open, and prints PASS/FAIL lines</summary>
    public static class SubFileTest
    {
        static int fails;
        static void Check(bool ok, string what) { Console.WriteLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }
        public static void Run()
        {
            string dir = Path.Combine(Path.GetTempPath(), "pgsubfile_" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(dir);
            string p = Path.Combine(dir, "subscribers_master.json");
            SubsImport.WriteAtomic(p, "{\"n\":0}");
            Check(File.Exists(p) && !File.Exists(p + ".tmp"), "first write creates the file, no temp left");
            int bad = 0, reads = 0, writes = 0; var errs = new System.Collections.Concurrent.ConcurrentBag<string>(); bool stop = false;
            var tasks = new Task[6];
            for (int w = 0; w < 2; w++) { int id = w; tasks[w] = Task.Run(() => { for (int i = 1; i <= 150; i++) { try { SubsImport.WriteAtomic(p, "{\"n\":" + (id * 1000 + i) + ",\"pad\":\"" + new string('x', 20000) + "\"}"); Interlocked.Increment(ref writes); } catch (Exception ex) { errs.Add("write " + ex.Message); } } }); }
            for (int r = 0; r < 3; r++) tasks[2 + r] = Task.Run(() => { while (!stop) { try { var j = SubsImport.ParseJ(SubsImport.ReadShared(p)); if (j["n"] == null) Interlocked.Increment(ref bad); Interlocked.Increment(ref reads); } catch (Exception ex) { errs.Add("read " + ex.Message); } } });
            // an outside reader that keeps the file open the way a naive tool does (share read+write, no delete) for a short while
            tasks[5] = Task.Run(() => { for (int i = 0; i < 6; i++) { try { using (var fs = new FileStream(p, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)) Thread.Sleep(60); } catch (IOException) { } Thread.Sleep(30); } });
            if (!Task.WaitAll(new[] { tasks[0], tasks[1], tasks[5] }, 20000)) Console.WriteLine("writers stuck: writes=" + writes + " reads=" + reads + " errs=" + errs.Count + " first=" + (errs.TryPeek(out var fe) ? fe : "-")); stop = true; Task.WaitAll(tasks, 10000);
            Check(errs.IsEmpty, "no read or write threw under the concurrent loop (" + writes + " writes, " + reads + " reads)" + (errs.IsEmpty ? "" : ": " + string.Join(" | ", errs)));
            Check(bad == 0, "no reader ever saw a half-written file");
            Check(!File.Exists(p + ".tmp"), "no temp file left behind");
            try { Directory.Delete(dir, true); } catch (Exception) { }
            Console.WriteLine(fails == 0 ? "[subfiletest] ALL PASS" : "[subfiletest] FAIL " + fails);
        }
    }
}
