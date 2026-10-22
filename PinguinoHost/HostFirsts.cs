using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The First 5 leaderboard. The live game (PinguinoBotFirsts) keeps five global vars firstPlaceStats .. fifthPlaceStats ({login: count}); this class rebuilds them from the stored chat
    /// (Data\chat_logs day files + the Host's own recording) and serves the board.
    /// Score: 1st = 5, 2nd and 3rd = 3 each, 4th and 5th = 1 each. top3 and top5 are cumulative (a 1st also counts in top3 and top5).</summary>
    public static class Firsts
    {
        static readonly string[] Vars = { "firstPlaceStats", "secondPlaceStats", "thirdPlaceStats", "fourthPlaceStats", "fifthPlaceStats" };
        static readonly int[] Pts = { 5, 3, 3, 1, 1 };
        internal static Func<string, string> GetVar = n => Program.GetGlobal(n);
        internal static Action<string, string> SetVar = (n, v) => Program.SetGlobal(n, v);
        static string Root { get { return Boards.RootDir; } }
        static string Dir { get { return Path.Combine(Root, "firsts"); } }

        internal sealed class Msg { public long T; public string U; }
        static readonly Regex Line = new Regex(@"^\[(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)\] #(\S+) (\S+): (.*)$", RegexOptions.Compiled);

        /// <summary>every chat line and the stream markers (the bot's "Stream is live!" / "Stream offline" lines) from the day files, plus the Host's own recording (deduplicated by second + user + text)</summary>
        internal static void Load(string chatDir, out List<Msg> msgs, out List<KeyValuePair<long, bool>> marks, out int days, out string chan)
        {
            chan = null; var ms = new List<Msg>(); var mk = new List<KeyValuePair<long, bool>>(); var seen = new HashSet<string>(); int dc = 0;
            Action<long, string, string> add = (t, u, text) =>
            {
                u = (u ?? "").ToLowerInvariant(); if (u == "") return;
                if (u == "pinguinob0t" && (text ?? "").StartsWith("Stream is live")) { mk.Add(new KeyValuePair<long, bool>(t, true)); return; }
                if (u == "pinguinob0t" && (text ?? "").StartsWith("Stream offline")) { mk.Add(new KeyValuePair<long, bool>(t, false)); return; }
                if (!seen.Add(t + "|" + u + "|" + text)) return;
                ms.Add(new Msg { T = t, U = u });
            };
            if (Directory.Exists(chatDir))
                foreach (var f in Directory.EnumerateFiles(chatDir, "*.txt", SearchOption.AllDirectories).OrderBy(x => x, StringComparer.Ordinal))
                {
                    if (!Regex.IsMatch(Path.GetFileName(f), @"^\d{4}-\d\d-\d\d\.txt$")) continue; dc++;
                    foreach (var ln in File.ReadLines(f))
                    {
                        var m = Line.Match(ln); if (!m.Success) continue;
                        long t = new DateTimeOffset(int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value), int.Parse(m.Groups[3].Value), int.Parse(m.Groups[4].Value), int.Parse(m.Groups[5].Value), int.Parse(m.Groups[6].Value), TimeSpan.Zero).ToUnixTimeSeconds();
                        if (chan == null) chan = m.Groups[7].Value.ToLowerInvariant(); add(t, m.Groups[8].Value, m.Groups[9].Value);
                    }
                }
            string live = Path.Combine(chatDir, "live");
            if (Directory.Exists(live))
                foreach (var f in Directory.EnumerateFiles(live, "*.jsonl").OrderBy(x => x, StringComparer.Ordinal))
                    foreach (var ln in File.ReadLines(f))
                    {
                        try { var o = JObject.Parse(ln); long ms2 = (long?)o["t"] ?? 0; if (ms2 > 0) add(ms2 / 1000, (string)o["u"], (string)o["m"]); } catch (Exception) { }
                    }
            ms.Sort((a, b) => a.T != b.T ? a.T.CompareTo(b.T) : string.CompareOrdinal(a.U, b.U)); mk.Sort((a, b) => a.Key.CompareTo(b.Key));
            msgs = ms; marks = mk; days = dc;
        }

        /// <summary>the streams found in the chat: start (unix s), end, how it was found, and its first 5 distinct chatters. A pure function of its inputs, so a rebuild always gives the same answer.</summary>
        internal static List<JObject> Streams(List<Msg> all, List<KeyValuePair<long, bool>> marks, Func<string, bool> skip, Func<string, string> canon, long streamGap = 3 * 3600)
        {
            var viewers = all.Where(m => !skip(m.U)).ToList(); var res = new List<JObject>(); if (viewers.Count == 0) return res;
            // clusters of viewer chat separated by more than streamGap
            var clusters = new List<List<Msg>>(); var cur = new List<Msg> { viewers[0] };
            for (int i = 1; i < viewers.Count; i++) { if (viewers[i].T - cur[cur.Count - 1].T > streamGap) { clusters.Add(cur); cur = new List<Msg>(); } cur.Add(viewers[i]); }
            clusters.Add(cur);
            foreach (var c in clusters)
            {
                long s = c[0].T, e = c[c.Count - 1].T;
                var ons = marks.Where(x => x.Value && x.Key >= s - 1800 && x.Key <= e).Select(x => x.Key).ToList();
                var offs = marks.Where(x => !x.Value && x.Key >= s && x.Key <= e + 1800).Select(x => x.Key).ToList();
                // a start = an "on" marker that follows an "off" marker (or the first "on" of the cluster); repeated "on" lines (restarts, tests) are not new streams
                var starts = new List<long>();
                foreach (long on in ons) { long lastOff = offs.Where(o => o <= on).DefaultIfEmpty(0).Max(); long lastStart = starts.Count == 0 ? 0 : starts[starts.Count - 1]; if (starts.Count == 0 || lastOff > lastStart) starts.Add(on); }
                string how = "marker";
                if (starts.Count == 0)
                {
                    int chatters = c.Select(m => m.U).Distinct().Count();
                    if (offs.Count > 0 && c.Count >= 2) { starts.Add(s); how = "off-marker only (start = first message)"; }
                    else if (chatters >= 5 && c.Count >= 100) { starts.Add(s); how = "inferred from chat (no markers)"; }
                    else continue;
                }
                for (int k = 0; k < starts.Count; k++)
                {
                    long st = starts[k], en = k + 1 < starts.Count ? starts[k + 1] : e + 1;
                    long off = offs.Where(o => o > st && o < en).DefaultIfEmpty(0).Min(); if (off > 0) en = off + 1;   // chat after the offline line does not count
                    var places = new List<string>();
                    foreach (var m in c) { if (m.T < st || m.T >= en) continue; string who = canon(m.U); if (places.Contains(who)) continue; places.Add(who); if (places.Count == 5) break; }
                    if (places.Count == 0) continue;
                    res.Add(new JObject { { "start", st }, { "end", Math.Min(en - 1, e) }, { "how", how }, { "places", new JArray(places) } });
                }
            }
            return res;
        }

        internal static JObject Build(string chatDirOverride = null, Func<string, bool> skipOverride = null, Func<string, string> canonOverride = null)
        {
            var bots = Boards.AllBots();
            List<Msg> msgs; List<KeyValuePair<long, bool>> marks; int days; string chan; Load(chatDirOverride ?? Path.Combine(Root, "chat_logs"), out msgs, out marks, out days, out chan);
            string streamer = (Boards.Channel() ?? "").ToLowerInvariant(); string logChan = chan ?? "";   // the channel owner never takes a place (configured name, and the channel the logs are for)
            Func<string, bool> skip = skipOverride ?? (u => u == streamer || u == logChan || Boards.IsBot(u) || bots.Contains(u));
            Func<string, string> canon = canonOverride ?? (u => Boards.CanonLogin(u));
            var streams = Streams(msgs, marks, skip, canon);
            var counts = new Dictionary<string, int[]>();
            foreach (var st in streams) { var pl = (JArray)st["places"]; for (int i = 0; i < pl.Count; i++) { string u = (string)pl[i]; int[] a; if (!counts.TryGetValue(u, out a)) counts[u] = a = new int[5]; a[i]++; } }
            var users = new JObject(); foreach (var kv in counts.OrderBy(k => k.Key, StringComparer.Ordinal)) users[kv.Key] = new JArray(kv.Value.Select(x => (object)x));
            var how = new JObject(); foreach (var g in streams.GroupBy(s => (string)s["how"])) how[g.Key] = g.Count();
            return new JObject { { "ok", true }, { "days", days }, { "messages", msgs.Count }, { "streams", new JArray(streams) }, { "users", users }, { "people", counts.Count },
                { "markers", marks.Count(x => x.Value) + " live / " + marks.Count(x => !x.Value) + " offline" }, { "how", how }, { "short", streams.Count(s => ((JArray)s["places"]).Count < 5) } };
        }

        /// <summary>current counts per login from the five global vars</summary>
        static Dictionary<string, int[]> Current()
        {
            var d = new Dictionary<string, int[]>();
            for (int i = 0; i < 5; i++)
            {
                string j = GetVar(Vars[i]); if (string.IsNullOrWhiteSpace(j)) continue;
                JObject o; try { o = JObject.Parse(j); } catch (Exception) { continue; }
                foreach (var p in o.Properties()) { string u = Boards.CanonLogin(p.Name); int[] a; if (!d.TryGetValue(u, out a)) d[u] = a = new int[5]; a[i] += (int?)p.Value ?? 0; }
            }
            return d;
        }

        internal static JObject Rows(Dictionary<string, int[]> d, int limit = 100)
        {
            var bots = Boards.AllBots();
            var rows = d.Where(kv => !Boards.IsBot(kv.Key) && !bots.Contains(kv.Key)).Select(kv => new { login = kv.Key, p = kv.Value, score = Enumerable.Range(0, 5).Sum(i => kv.Value[i] * Pts[i]) })
                .OrderByDescending(r => r.score).ThenByDescending(r => r.p[0]).ThenByDescending(r => r.p[0] + r.p[1] + r.p[2]).ThenBy(r => r.login, StringComparer.Ordinal).ToList();
            var arr = new JArray(rows.Take(limit).Select(r => new JObject { { "login", r.login }, { "display", Boards.DisplayName(r.login) }, { "firsts", r.p[0] }, { "top3", r.p[0] + r.p[1] + r.p[2] }, { "top5", r.p.Sum() }, { "score", r.score }, { "places", new JArray(r.p.Select(x => (object)x)) } }));
            return new JObject { { "metric", "firsts" }, { "scoring", "1st = 5, 2nd and 3rd = 3 each, 4th and 5th = 1 each" }, { "updatedAt", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() }, { "people", rows.Count }, { "rows", arr } };
        }

        static List<JObject> _streams; static DateTime _streamsAt = DateTime.MinValue;
        /// <summary>every stream with its first 5 (rebuilt from the chat logs at most every 10 minutes)</summary>
        internal static List<JObject> CachedStreams()
        {
            lock (typeof(Firsts)) { if (_streams == null || (DateTime.UtcNow - _streamsAt).TotalMinutes > 10) { _streams = ((JArray)Build()["streams"]).OfType<JObject>().ToList(); _streamsAt = DateTime.UtcNow; } return _streams; }
        }
        static Dictionary<string, int[]> Count(IEnumerable<JObject> streams)
        {
            var d = new Dictionary<string, int[]>();
            foreach (var st in streams) { var pl = (JArray)st["places"]; for (int i = 0; i < pl.Count; i++) { string u = (string)pl[i]; int[] a; if (!d.TryGetValue(u, out a)) d[u] = a = new int[5]; a[i]++; } }
            return d;
        }
        /// <summary>periods.firsts for POST /api/bot/boards: {day|week|month|year|all: {current, keys, boards: {key: {total, rows[value=score, firsts, top3, top5]}}}}</summary>
        public static JObject ForSite()
        {
            var streams = CachedStreams(); long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); var o = new JObject();
            var keep = new Dictionary<string, int> { { "day", 14 }, { "week", 12 }, { "month", 1000 }, { "year", 1000 }, { "all", 1 } };
            foreach (string per in new[] { "day", "week", "month", "year", "all" })
            {
                string cur = per == "all" ? "all" : Periods.KeyFor(per, now); var byKey = new Dictionary<string, List<JObject>>();
                foreach (var st in streams) { string k = per == "all" ? "all" : Periods.KeyFor(per, (long)st["start"]); List<JObject> l; if (!byKey.TryGetValue(k, out l)) byKey[k] = l = new List<JObject>(); l.Add(st); }
                var keys = byKey.Keys.OrderByDescending(k => k, StringComparer.Ordinal).ToList(); if (!keys.Contains(cur)) keys.Insert(0, cur);
                var boards = new JObject();
                foreach (string k in keys.Take(keep[per]))
                {
                    List<JObject> l; if (!byKey.TryGetValue(k, out l)) continue; var board = Rows(Count(l), 100);
                    var rows = new JArray(); int rank = 0;
                    foreach (JObject r in (JArray)board["rows"]) { rank++; rows.Add(new JObject { { "rank", rank }, { "login", r["login"] }, { "name", r["display"] }, { "value", r["score"] }, { "firsts", r["firsts"] }, { "top3", r["top3"] }, { "top5", r["top5"] } }); }
                    boards[k] = new JObject { { "total", board["people"] }, { "rows", rows } };
                }
                o[per] = new JObject { { "current", cur }, { "keys", new JArray(keys) }, { "boards", boards } };
            }
            return o;
        }

        /// <summary>the board for the apps (top 100), from the chat logs</summary>
        public static JObject Board(int limit = 100) { try { return Rows(Count(CachedStreams()), limit); } catch (Exception ex) { Clog.Warn("firsts", "board: " + ex.Message); return new JObject { { "metric", "firsts" }, { "rows", new JArray() } }; } }

        /// <summary>dry run (apply=false) returns what the rebuild would write; apply backs up the five vars to Data\firsts and then replaces them</summary>
        public static JObject Rebuild(bool apply, string chatDirOverride = null)
        {
            var b = Build(chatDirOverride); var users = (JObject)b["users"]; var before = Current();
            var now = new Dictionary<string, int[]>(); foreach (var p in users.Properties()) now[p.Name] = ((JArray)p.Value).Select(x => (int)x).ToArray();
            var diff = new JArray(); int changed = 0;
            foreach (var u in now.Keys.Union(before.Keys).OrderBy(x => x, StringComparer.Ordinal))
            { int[] a, c; before.TryGetValue(u, out a); now.TryGetValue(u, out c); a = a ?? new int[5]; c = c ?? new int[5]; if (a.SequenceEqual(c)) continue; changed++; if (diff.Count < 40) diff.Add(new JObject { { "login", u }, { "before", string.Join("/", a) }, { "after", string.Join("/", c) } }); }
            var res = new JObject { { "ok", true }, { "applied", false }, { "days", b["days"] }, { "messages", b["messages"] }, { "streams", ((JArray)b["streams"]).Count }, { "people", b["people"] }, { "markers", b["markers"] }, { "found_by", b["how"] }, { "streams_with_under_5_chatters", b["short"] }, { "people_changed", changed }, { "sample_changes", diff }, { "top10", Rows(now, 10)["rows"] } };
            if (!apply) return res;
            try
            {
                Directory.CreateDirectory(Dir); string ts = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
                var bak = new JObject(); foreach (string v in Vars) bak[v] = GetVar(v) ?? "";
                File.WriteAllText(Path.Combine(Dir, "globals-before-" + ts + ".json"), bak.ToString());
                for (int i = 0; i < 5; i++) { var o = new JObject(); foreach (var kv in now.OrderBy(k => k.Key, StringComparer.Ordinal)) if (kv.Value[i] > 0) o[kv.Key] = kv.Value[i]; SetVar(Vars[i], o.ToString(Formatting.None)); }
                File.WriteAllText(Path.Combine(Dir, "streams.json"), new JObject { { "builtAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "streams", b["streams"] } }.ToString(Formatting.None));
                res["applied"] = true; res["backup"] = "Data\\firsts\\globals-before-" + ts + ".json"; Clog.Info("firsts", "rebuilt from the chat logs: " + ((JArray)b["streams"]).Count + " streams, " + now.Count + " people");
            }
            catch (Exception ex) { res["ok"] = false; res["error"] = ex.Message; }
            return res;
        }
    }
}
