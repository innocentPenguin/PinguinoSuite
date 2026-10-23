using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>One log of every mod/owner action: the site's (the Host POLLS GET /api/bot/modaudit?after=&lt;seq&gt; and appends what is new) and the Host's own (chat mod commands, timeouts, the control layer: ChannelControl.Audit
    /// lands here too, and the entry is PUSHED to POST /api/bot/modaudit with page "host" so the site's log has them as well).
    /// Entry: {id, at (unix s), who, role, action, target, before, after, page, src: site|host, seq (site entries)}. No IPs. File: Data\runtime\mod_audit.jsonl, rotated at 5 MB (.1 ... .5).
    /// Read: GET /api/modaudit?limit=200&amp;before=&lt;id&gt; (newest first; the Host API listens on this PC only, so this is for the owner).</summary>
    public static class ModAudit
    {
        static readonly object L = new object(); static bool _started; static string _result = "not started"; static long _n;
        static string Dir { get { return Path.Combine(HostApi.DataDir, "runtime"); } }
        static string F { get { return Path.Combine(Dir, "mod_audit.jsonl"); } }
        static string StateP { get { return Path.Combine(Dir, "mod_audit_state.json"); } }
        static string OutboxP { get { return Path.Combine(Dir, "mod_audit_outbox.json"); } }
        static long MaxBytes { get { long v; return long.TryParse(Environment.GetEnvironmentVariable("PINGUINO_MODAUDIT_MAXBYTES"), out v) && v > 0 ? v : 5L * 1024 * 1024; } }

        public static JObject Status() { lock (L) return new JObject { { "result", _result }, { "lastSeq", (long?)SiteHttp.ReadJ(StateP)["lastSeq"] ?? 0 }, { "waitingToPush", ((SiteHttp.ReadJ(OutboxP)["entries"] as JArray) ?? new JArray()).Count } }; }

        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(9000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(SiteHttp.PollSec * 1000); } });
        }

        static string Clip(string s, int n) { s = (s ?? "").Replace('\n', ' ').Replace('\r', ' '); return s.Length > n ? s.Substring(0, n) : s; }

        /// <summary>a mod/owner action done on this PC (chat command, timeout, control layer). Never throws.</summary>
        public static void Log(string who, string role, string action, string target, string before = "", string after = "")
        {
            try
            {
                var e = new JObject { { "id", "h-" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + "-" + System.Threading.Interlocked.Increment(ref _n) }, { "at", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "who", Clip(who, 60) }, { "role", Clip(role, 20) }, { "action", Clip(action, 80) },
                    { "target", Clip(target, 300) }, { "before", Clip(before, 300) }, { "after", Clip(after, 300) }, { "page", "host" }, { "src", "host" } };
                lock (L)
                {
                    Append(e);
                    var o = SiteHttp.ReadJ(OutboxP); var arr = o["entries"] as JArray ?? new JArray(); arr.Add(e); while (arr.Count > 2000) arr.RemoveAt(0); o["entries"] = arr; SiteHttp.WriteJ(OutboxP, o);
                }
            }
            catch (Exception) { }
        }

        static void Append(JObject e)
        {
            Directory.CreateDirectory(Dir);
            try { var fi = new FileInfo(F); if (fi.Exists && fi.Length > MaxBytes) Rotate(); } catch (Exception) { }
            File.AppendAllText(F, e.ToString(Newtonsoft.Json.Formatting.None) + "\n", new UTF8Encoding(false));
        }
        static void Rotate()
        {
            for (int i = 5; i >= 1; i--) { string a = F + "." + i; if (!File.Exists(a)) continue; if (i == 5) File.Delete(a); else File.Move(a, F + "." + (i + 1)); }
            File.Move(F, F + ".1");
        }

        public static void Tick()
        {
            if (!SiteHttp.Enabled("SiteModAudit")) { _result = "off"; return; }
            string key = SiteHttp.Key(); if (key == "") { _result = "no key (vault name BOT_API_KEY)"; return; }
            if (!Lease.MayRun) return;
            long last; lock (L) last = (long?)SiteHttp.ReadJ(StateP)["lastSeq"] ?? 0;
            int pulled = 0;
            for (int page = 0; page < 20; page++)   // up to 20 pages of the backlog per tick
            {
                JObject j; int code = SiteHttp.Call("GET", "/api/bot/modaudit?after=" + last, null, key, out j);
                if (code == 401) { _result = "site refused the key (HTTP 401)"; return; }
                if (code != 200 || j == null) { _result = code == 0 ? "site not reachable" : "site answered HTTP " + code; break; }
                var items = (j["entries"] ?? j["items"]) as JArray ?? new JArray(); if (items.Count == 0) { _result = "ok"; break; }
                lock (L)
                {
                    foreach (var x in items.OfType<JObject>().OrderBy(x => (long?)x["seq"] ?? 0))
                    {
                        long seq = (long?)x["seq"] ?? 0; if (seq <= last) continue;
                        var e = new JObject { { "id", "s-" + seq }, { "at", x["at"] ?? 0 }, { "who", Clip((string)x["who"], 60) }, { "role", Clip((string)x["role"], 20) }, { "action", Clip((string)x["action"], 80) }, { "target", Clip((string)x["target"], 300) },
                            { "before", Clip((string)x["before"], 300) }, { "after", Clip((string)x["after"], 300) }, { "page", Clip((string)x["page"], 40) }, { "src", "site" }, { "seq", seq } };
                        Append(e); last = seq; pulled++;
                    }
                    var st = SiteHttp.ReadJ(StateP); st["lastSeq"] = last; SiteHttp.WriteJ(StateP, st);
                }
                _result = "ok";
            }
            // push what happened here
            JArray todo; lock (L) todo = (JArray)((SiteHttp.ReadJ(OutboxP)["entries"] as JArray) ?? new JArray()).DeepClone();
            if (todo.Count > 0)
            {
                var send = new JArray(todo.Take(200).Select(t => new JObject { { "at", t["at"] }, { "who", t["who"] }, { "role", t["role"] }, { "action", t["action"] }, { "target", t["target"] }, { "before", t["before"] }, { "after", t["after"] }, { "page", "host" } }));
                JObject r; int code = SiteHttp.Call("POST", "/api/bot/modaudit", new JObject { { "entries", send } }, key, out r);
                if (code == 200)
                {
                    lock (L) { var o = SiteHttp.ReadJ(OutboxP); var arr = o["entries"] as JArray ?? new JArray(); for (int i = 0; i < send.Count && arr.Count > 0; i++) arr.RemoveAt(0); o["entries"] = arr; SiteHttp.WriteJ(OutboxP, o); }
                }
                else if (code == 401) { _result = "site refused the key (HTTP 401)"; }
                else if (code == 404) { /* site has no endpoint yet: keep them */ }
            }
        }

        /// <summary>newest first. before = an entry id to continue from; limit max 1000.</summary>
        public static JObject Read(int limit, string before)
        {
            limit = Math.Max(1, Math.Min(1000, limit)); var res = new List<JObject>();
            lock (L)
            {
                var files = new List<string> { F }; for (int i = 1; i <= 5; i++) files.Add(F + "." + i);
                bool skipping = !string.IsNullOrEmpty(before);
                foreach (var f in files)
                {
                    if (!File.Exists(f) || res.Count >= limit) continue;
                    string[] lines; try { lines = File.ReadAllLines(f, Encoding.UTF8); } catch (Exception) { continue; }
                    for (int i = lines.Length - 1; i >= 0 && res.Count < limit; i--)
                    {
                        JObject e; try { e = JObject.Parse(lines[i]); } catch (Exception) { continue; }
                        if (skipping) { if ((string)e["id"] == before) skipping = false; continue; }
                        res.Add(e);
                    }
                }
            }
            return new JObject { { "ok", true }, { "entries", new JArray(res) }, { "more", res.Count >= limit } };
        }
    }
}
