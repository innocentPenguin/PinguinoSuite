using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>POST /api/customs/sim-say: the customs simulator asks Chatty to say the SAME lines the Core says.
    /// Speaks only when the payload has speak:true and Data\sim_say.json is not {"enabled":false}. Otherwise it returns the lines (dry run).</summary>
    public static class SimSay
    {
        static string Label(string team) { return (team == "blue" ? "🔷 " : "🔶 ") + CustomsView.TeamName(team); }
        static string Str(JToken t) { return t == null || t.Type == JTokenType.Null ? "" : t.ToString().Trim(); }
        static int Int(JToken t, int d) { int v; return t != null && int.TryParse(t.ToString(), out v) ? v : d; }

        static bool Enabled()
        {
            try { var f = Path.Combine(HostApi.DataDir, "sim_say.json"); if (File.Exists(f)) { var o = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); var e = o["enabled"]; if (e != null && e.Type == JTokenType.Boolean && !(bool)e) return false; } } catch (Exception) { }
            return true;
        }

        static int Mmr(JObject match, string n)
        {
            var m = match == null ? null : match["mmr"] as JObject;
            return m != null && m[n] != null ? Int(m[n], 1000) : 1000;
        }
        static int Avg(JObject match, List<string> names, string key)
        {
            if (match != null && match[key] != null) return Int(match[key], 1000);
            return names.Count == 0 ? 0 : (int)Math.Round(names.Average(n => (double)Mmr(match, n)));
        }
        static List<string> Names(JToken t) { return (t as JArray ?? new JArray()).Select(x => Str(x)).Where(x => x != "").ToList(); }

        public static JObject Say(JObject b)
        {
            string ev = Str(b["event"]).ToLowerInvariant();
            var match = b["match"] as JObject;
            var queue = Names(b["queue"]);
            string player = Str(b["player"]);
            string winner = Str(b["winner"]).ToLowerInvariant();
            var lines = new List<string>();
            switch (ev)
            {
                case "match_start":
                {
                    var blue = Names(match == null ? null : match["blue"]); var orange = Names(match == null ? null : match["orange"]);
                    if (blue.Count + orange.Count == 0) return new JObject { { "ok", false }, { "error", "match.blue/orange needed" } };
                    string id = match != null && match["id"] != null ? "#" + Str(match["id"]) + " " : "";
                    int ba = Avg(match, blue, "blueAvg"), oa = Avg(match, orange, "orangeAvg");
                    int diff = match != null && match["diff"] != null ? Int(match["diff"], 0) : Math.Abs(ba - oa);
                    lines.Add(id + Label("blue") + " [avg " + ba + "]: " + string.Join(", ", blue.Select(n => n + "(" + Mmr(match, n) + ")")));
                    lines.Add(Label("orange") + " [avg " + oa + "]: " + string.Join(", ", orange.Select(n => n + "(" + Mmr(match, n) + ")")) + " | Diff: " + diff);
                    break;
                }
                case "result":
                {
                    if (winner != "blue" && winner != "orange") return new JObject { { "ok", false }, { "error", "winner must be blue or orange" } };
                    string mode = Str(b["mode"]).ToLowerInvariant();
                    string tail = mode == "koth" ? " (+1 win on the King of the Hill leaderboard)"
                        : mode == "points" ? " (+" + Int(b["pointsWin"], 3) + " pts winners, +" + Int(b["pointsLoss"], 1) + " pts losers)"
                        : " (casual: no points)";
                    lines.Add(Label(winner) + " wins match #" + Str(match == null ? null : match["id"]) + "!" + tail);
                    break;
                }
                case "queue_open": lines.Add("The queue is now OPEN! Type !join to enter."); break;
                case "queue_close": lines.Add("The queue is now CLOSED. No new joins accepted."); break;
                case "queue_clear": lines.Add("The queue has been cleared and closed."); break;
                case "join":
                    if (player == "") return new JObject { { "ok", false }, { "error", "player needed" } };
                    lines.Add("@" + player + " You joined the queue at position #" + (b["pos"] != null ? Int(b["pos"], queue.Count) : Math.Max(1, queue.Count)) + "!"); break;
                case "leave":
                    if (player == "") return new JObject { { "ok", false }, { "error", "player needed" } };
                    lines.Add("@" + player + " You left the queue."); break;
                case "kick":
                    if (player == "") return new JObject { { "ok", false }, { "error", "player needed" } };
                    lines.Add(player + " has been removed from the queue." + (b["inLobby"] != null && (bool)b["inLobby"] ? " Use !reroll to refill the lobby." : "")); break;
                case "koth_stays":
                    if (winner != "blue" && winner != "orange") return new JObject { { "ok", false }, { "error", "winner must be blue or orange" } };
                    lines.Add(Label(winner) + " stays on! Rotating in new challengers..."); break;
                case "koth_wait":
                    if (winner != "blue" && winner != "orange") return new JObject { { "ok", false }, { "error", "winner must be blue or orange" } };
                    lines.Add("KOTH: " + Label(winner) + " stays on, but there aren't enough challengers (need " + Int(b["need"], 0) + ", have " + Int(b["have"], queue.Count) + "). The winners wait at the front of the queue."); break;
                case "waiting":
                    lines.Add("Waiting for players: need " + Int(b["need"], 0) + " for " + (Str(b["format"]) == "" ? "2v2" : Str(b["format"])) + ", have " + Int(b["have"], queue.Count) + ". The next game starts by itself when the queue is full."); break;
                case "text":
                    if (Str(b["text"]) == "") return new JObject { { "ok", false }, { "error", "text needed" } };
                    lines.Add(Str(b["text"])); break;
                default: return new JObject { { "ok", false }, { "error", "unknown event" } };
            }
            bool speak = b["speak"] != null && b["speak"].Type == JTokenType.Boolean && (bool)b["speak"];
            if (!speak || !Enabled())
                return new JObject { { "ok", true }, { "spoke", false }, { "lines", new JArray(lines) } };
            int sent = 0, dup = 0;
            foreach (var l in lines)
            {
                if (HostApi.SimMode) { Console.WriteLine("[say] " + l); sent++; continue; }
                string via; if (HostApi.SendAs("chat", l, out via)) sent++; else dup++;
            }
            return new JObject { { "ok", true }, { "spoke", sent > 0 }, { "sent", sent }, { "blocked", dup }, { "lines", new JArray(lines) } };
        }
    }
}
