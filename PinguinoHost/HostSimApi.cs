using System;
using System.Net;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    public static partial class HostApi
    {
        /// <summary>Simulated players: GET /api/sim/status; POST /api/sim/start {count, mode} | add {n} | remove {n} | join {names[]} | leave {names[]} | tick | clear | config {sendSimToSite, churnPerMin, startBalance, gambling, earnPerMin}.</summary>
        static bool SimRoutes(HttpListenerContext c, string p, string m)
        {
            if (!p.StartsWith("/api/sim/")) return false;
            if (p == "/api/sim/status" && m == "GET") { Write(c, Sim.Status().ToString(), "application/json"); return true; }
            if (m != "POST") return false;
            if (Sim.Exec == null) Sim.Exec = text => { string who = "innocentpenguin_"; try { var ch = (string)StreamerCreds()["Channel"]; if (!string.IsNullOrEmpty(ch)) who = ch; } catch (Exception) { } Control.Synthetic = true; try { Program.Dispatch(who, text, null, 4, "deck", false, null); } finally { Control.Synthetic = false; } };
            var b = Body(c); JObject r;
            switch (p)
            {
                case "/api/sim/start": r = Sim.Start((int?)b["count"] ?? 12, (string)b["mode"]); break;
                case "/api/sim/add": r = Sim.Add((int?)b["n"] ?? 1); break;
                case "/api/sim/remove": r = Sim.Remove((int?)b["n"] ?? 1); break;
                case "/api/sim/join": r = Sim.JoinNames(b["names"] as JArray ?? new JArray()); break;
                case "/api/sim/leave": r = Sim.LeaveNames(b["names"] as JArray ?? new JArray()); break;
                case "/api/sim/tick": r = Sim.Tick(); break;
                case "/api/sim/clear": r = Sim.Clear("cleared from the app"); break;
                case "/api/sim/config": r = Sim.Config(b); break;
                default: return false;
            }
            Write(c, r.ToString(), "application/json"); return true;
        }
    }
}
