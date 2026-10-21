using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Replay results written by Lite (Data\lite\replays\results\*.json, see Docs\REPLAY_STATS_PLAN.md), served read-only and public-safe:
    /// GET /api/replays[?limit=], GET /api/replays/{id}. Only whitelisted fields leave (no file paths, no account ids). Queue matches whose Winner is still empty get a
    /// PROPOSAL when a replay has a decisive winner and its Twitch names match the roster exactly: GET /api/replays/proposals. Nothing is set on its own;
    /// POST /api/replays/apply {matchId, replayId} (the streamer's/mod's approval) re-checks the proposal and runs the normal "!matchwin" so stats and history stay consistent.
    /// PINGUINO_LITE_DIR overrides the Lite folder (tests).</summary>
    public static class Replays
    {
        static string LiteDir() { string e = Environment.GetEnvironmentVariable("PINGUINO_LITE_DIR"); return !string.IsNullOrEmpty(e) ? e : Path.Combine(Program.SuiteDir ?? "", "Data", "lite"); }
        static string ResultsDir() { return Path.Combine(LiteDir(), "replays", "results"); }

        static JObject Read(string f) { try { return JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { return null; } }

        static JObject Team(JToken t)
        {
            var players = new JArray();
            foreach (var p in (t?["players"] as JArray) ?? new JArray())
                players.Add(new JObject { { "name", (string)p["name"] ?? "" }, { "platform", (string)p["platform"] ?? "" }, { "twitch", p["twitch"] == null || p["twitch"].Type == JTokenType.Null ? null : (string)p["twitch"] }, { "score", (int?)p["score"] ?? 0 }, { "goals", (int?)p["goals"] ?? 0 }, { "assists", (int?)p["assists"] ?? 0 }, { "saves", (int?)p["saves"] ?? 0 }, { "shots", (int?)p["shots"] ?? 0 }, { "bot", (bool?)p["bot"] ?? false } });
            return new JObject { { "score", (int?)t?["score"] ?? 0 }, { "players", players } };
        }
        static string Str(JToken t) { return t == null || t.Type == JTokenType.Null ? null : (string)t; }

        /// <summary>the public-safe view of one result file</summary>
        static JObject Safe(JObject r, bool full)
        {
            var o = new JObject { { "id", Str(r["match_id"]) }, { "playedAt", Str(r["played_at"]) }, { "status", Str(r["status"]) ?? "complete" }, { "teamSize", (int?)r["team_size"] ?? 0 }, { "map", Str(r["map"]) }, { "durationS", (int?)r["duration_s"] ?? 0 },
                { "blue", Team(r["blue"]) }, { "orange", Team(r["orange"]) }, { "winner", Str(r["winner"]) }, { "attributed", (bool?)r["attributed"] ?? true }, { "mvp", Str(r["mvp"]) } };
            if (r["winner_detected"] != null) o["winnerDetected"] = Str(r["winner_detected"]);
            if (full && r["goals"] is JArray gs) o["goals"] = new JArray(gs.Select(g => new JObject { { "team", Str(g["team"]) }, { "player", Str(g["player"]) }, { "tS", g["t_s"] } }));
            return o;
        }
        static string SafeId(string id) { return string.IsNullOrEmpty(id) || id.Length > 80 || id.Any(c => !(char.IsLetterOrDigit(c) || c == '-' || c == '_')) ? null : id; }

        static List<JObject> All()
        {
            var l = new List<JObject>(); string d = ResultsDir();
            if (Directory.Exists(d)) foreach (var f in Directory.GetFiles(d, "*.json")) { var r = Read(f); if (r != null && Str(r["match_id"]) != null) l.Add(r); }
            return l.OrderByDescending(r => Str(r["played_at"]) ?? "").ToList();
        }

        public static JObject List(System.Collections.Specialized.NameValueCollection q)
        {
            int limit; if (!int.TryParse(q["limit"], out limit) || limit < 1) limit = 50; if (limit > 500) limit = 500;
            var all = All(); var items = new JArray(all.Take(limit).Select(r => Safe(r, false)));
            var idx = Read(Path.Combine(LiteDir(), "replays", "index.json"));
            return new JObject { { "ok", true }, { "count", items.Count }, { "total", all.Count }, { "updatedAtMs", idx?["updated_at_ms"] }, { "items", items } };
        }

        public static JObject One(string id)
        {
            string sid = SafeId(id); if (sid == null) return new JObject { { "ok", false }, { "error", "bad replay id" } };
            var r = Read(Path.Combine(ResultsDir(), sid + ".json")); if (r == null) return new JObject { { "ok", false }, { "error", "replay not found" } };
            return new JObject { { "ok", true }, { "replay", Safe(r, true) } };
        }

        static List<string> Names(JToken team, bool replay)
        {
            var l = new List<string>();
            foreach (var p in (team as JArray) ?? new JArray()) { string n = Str(replay ? p["twitch"] : p["Username"]); if (!string.IsNullOrEmpty(n)) l.Add(n.ToLowerInvariant()); }
            l.Sort(StringComparer.Ordinal); return l;
        }
        static bool Same(List<string> a, List<string> b) { return a.Count > 0 && a.SequenceEqual(b); }

        static JArray Matches()
        {
            foreach (var f in new[] { Path.Combine(HostApi.DataDir, "runtime", "matches.json"), Path.Combine(HostApi.DataDir, "matches.json") }.Where(File.Exists).OrderByDescending(File.GetLastWriteTimeUtc))   // the live layout varies: the file the Core wrote last wins
                try { return JArray.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF)); } catch (Exception) { }
            return new JArray();
        }

        /// <summary>queue matches with no winner yet that a replay settles: every player on both sides has a Twitch name and both rosters equal the match's rosters</summary>
        public static JArray Proposals()
        {
            var res = new JArray(); var open = Matches().OfType<JObject>().Where(m => (m["Winner"] == null || m["Winner"].Type == JTokenType.Null) && (bool?)m["Incomplete"] != true && m["FinishedAt"] != null && m["FinishedAt"].Type != JTokenType.Null).ToList();
            if (open.Count == 0) return res;
            foreach (var r in All())
            {
                string w = (Str(r["winner"]) ?? Str(r["winner_detected"]) ?? "").ToLowerInvariant(); if (w != "blue" && w != "orange") continue;
                var rb = Names(r["blue"]?["players"], true); var ro = Names(r["orange"]?["players"], true);
                int nb = ((r["blue"]?["players"] as JArray)?.Count) ?? 0, no = ((r["orange"]?["players"] as JArray)?.Count) ?? 0;
                if (rb.Count != nb || ro.Count != no || nb == 0 || no == 0) continue;   // someone has no Twitch name: not decisive
                foreach (var m in open)
                {
                    var mb = Names(m["Blue"], false); var mo = Names(m["Orange"], false); string team = null;
                    if (Same(rb, mb) && Same(ro, mo)) team = w; else if (Same(rb, mo) && Same(ro, mb)) team = w == "blue" ? "orange" : "blue";
                    if (team == null) continue;
                    res.Add(new JObject { { "matchId", m["Id"] }, { "replayId", Str(r["match_id"]) }, { "winner", team }, { "replayWinner", w }, { "score", (int?)r["blue"]?["score"] + "-" + (int?)r["orange"]?["score"] }, { "playedAt", Str(r["played_at"]) }, { "attributed", (bool?)r["attributed"] ?? true } });
                }
            }
            return res;
        }

        // ---- automatic winners: a replay that matches a finished, winner-less queue match exactly settles it (same strict rules as the proposals), once per replay id
        static readonly object _lk = new object(); static HashSet<string> _applied; static System.Threading.Timer _timer;
        static string SettingsFile() { return Path.Combine(HostApi.DataDir, "replays_settings.json"); }
        static string AppliedFile() { return Path.Combine(HostApi.DataDir, "replays_applied.json"); }
        public static bool AutoWinner() { try { var j = Read(SettingsFile()); return (bool?)j?["ReplayAutoWinner"] != false; } catch (Exception) { return true; } }
        public static JObject Settings(string method, JObject body)
        {
            if (method == "POST")
            {
                if (body == null || body["ReplayAutoWinner"] == null || body["ReplayAutoWinner"].Type != JTokenType.Boolean) return new JObject { { "ok", false }, { "error", "ReplayAutoWinner must be true or false" } };
                File.WriteAllText(SettingsFile(), new JObject { { "ReplayAutoWinner", (bool)body["ReplayAutoWinner"] } }.ToString());
            }
            return new JObject { { "ok", true }, { "ReplayAutoWinner", AutoWinner() }, { "autoApplied", new JArray(Applied().OrderBy(x => x)) }, { "pending", Proposals().Count } };
        }
        static HashSet<string> Applied()
        {
            lock (_lk)
            {
                if (_applied == null) { _applied = new HashSet<string>(); try { foreach (var s in (JArray.Parse(File.ReadAllText(AppliedFile())) as JArray) ?? new JArray()) _applied.Add((string)s); } catch (Exception) { } }
                return new HashSet<string>(_applied);
            }
        }
        static void MarkApplied(string id)
        {
            lock (_lk) { Applied(); _applied.Add(id); try { File.WriteAllText(AppliedFile(), new JArray(_applied).ToString()); } catch (Exception) { } }
        }
        static bool ActivityActive()
        {
            try
            {
                var s = CustomsView.State(); if ((bool?)s["sim"] == true && Environment.GetEnvironmentVariable("PINGUINO_REPLAY_ALLOW_SIM") != "1") return false;
                string a = ((string)s["activity"] ?? "competitive").ToLowerInvariant(); return a == "competitive" || a == "casual" || a == "koth";
            }
            catch (Exception) { return false; }
        }
        public static void Start()
        {
            int sec; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_REPLAY_TICK_SEC"), out sec) || sec < 1) sec = 20;
            _timer = new System.Threading.Timer(_ => { try { Tick(); } catch (Exception ex) { Clog.Warn("replays", "auto winner tick failed: " + ex.Message); } }, null, sec * 1000, sec * 1000);
        }
        public static int Tick()
        {
            if (!AutoWinner() || !ActivityActive()) return 0;
            int n = 0; var done = Applied();
            foreach (var p in Proposals().OfType<JObject>())
            {
                string rid = (string)p["replayId"]; if (done.Contains(rid)) continue;
                var r = Apply(new JObject { { "matchId", (string)p["matchId"] }, { "replayId", rid }, { "by", "auto" } });
                MarkApplied(rid); done.Add(rid);   // once per replay id, whatever the outcome (a wrong auto result is corrected with !matchwin)
                bool ok = (bool?)r["ok"] == true; if (ok) n++;
                EventLog.Backend("replays", ok ? "replay " + rid + " set match #" + p["matchId"] + " winner " + p["winner"] : "replay " + rid + " could not be applied: " + (string)r["error"], new JObject { { "replayId", rid }, { "matchId", p["matchId"] }, { "winner", p["winner"] }, { "auto", true } }, ok ? "info" : "warn");
                done.Add(rid);
            }
            return n;
        }

        public static JObject Apply(JObject body)
        {
            string rid = Str(body["replayId"]); long mid; if (!long.TryParse((string)body["matchId"], out mid) || SafeId(rid) == null) return new JObject { { "ok", false }, { "error", "matchId and replayId are required" } };
            var p = Proposals().OfType<JObject>().FirstOrDefault(x => (long)x["matchId"] == mid && (string)x["replayId"] == rid);
            if (p == null) return new JObject { { "ok", false }, { "error", "no matching proposal (the rosters differ, or the match already has a winner)" } };
            string team = (string)p["winner"], by = (string)body["by"]; if (string.IsNullOrWhiteSpace(by)) by = "replay";
            string ch = ""; try { ch = ((string)HostApi.StreamerCreds()["Channel"] ?? "").ToLowerInvariant(); } catch (Exception) { }
            if (ch == "") ch = "streamer";
            try { Program.Dispatch(ch, "!matchwin " + mid + " " + team, "replay-" + rid, 4, "", false, null); }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", ex.Message } }; }
            Clog.Info("replays", "winner of match #" + mid + " set to " + team + " from replay " + rid + " (approved by " + by + ")");
            return new JObject { { "ok", true }, { "matchId", mid }, { "winner", team }, { "replayId", rid } };
        }
    }
}
