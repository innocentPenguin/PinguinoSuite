using System;
using System.Net;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    public static partial class HostApi
    {
        /// <summary>Master View routes: GET /api/chat/recent?since=&limit=, GET /api/customs/state, POST /api/customs/mod {action,value}, GET /api/wheel/state (GET /api/events is served by Events from the listener loop).</summary>
        static bool EventRoutes(HttpListenerContext c, string p, string m)
        {
            if (p == "/api/chat/recent" && m == "GET")
            {
                long since = 0; long.TryParse(c.Request.QueryString["since"], out since); int lim = 50; int.TryParse(c.Request.QueryString["limit"], out lim);
                Write(c, new JObject { { "ok", true }, { "seq", ChatFeed.Seq }, { "messages", ChatFeed.Recent(since, lim) } }.ToString(), "application/json"); return true;
            }
            if (p == "/api/alerts-settings" && (m == "GET" || m == "POST")) { Write(c, Sounds.Api(m, m == "POST" ? Body(c) : null).ToString(), "application/json"); return true; }
            if (p == "/api/replays" && m == "GET") { Write(c, Replays.List(c.Request.QueryString).ToString(), "application/json"); return true; }
            if (p == "/api/replays/settings" && (m == "GET" || m == "POST")) { Write(c, Replays.Settings(m, m == "POST" ? Body(c) : null).ToString(), "application/json"); return true; }
            if (p == "/api/replays/proposals" && m == "GET") { Write(c, new JObject { { "ok", true }, { "autoWinner", Replays.AutoWinner() }, { "proposals", Replays.Proposals() } }.ToString(), "application/json"); return true; }
            if (p == "/api/replays/apply" && m == "POST") { Write(c, Replays.Apply(Body(c)).ToString(), "application/json"); return true; }
            if (p.StartsWith("/api/replays/") && m == "GET") { Write(c, Replays.One(p.Substring("/api/replays/".Length)).ToString(), "application/json"); return true; }
            if (p == "/api/eventlog" && m == "GET") { Write(c, EventLog.Query(c.Request.QueryString).ToString(), "application/json"); return true; }
            if (p == "/api/customs/state" && m == "GET") { Write(c, CustomsView.State().ToString(), "application/json"); return true; }
            if (p == "/api/customs/mod" && m == "POST") { Write(c, CustomsView.Mod(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/customs/teams" && m == "POST") { Write(c, CustomsView.SetTeams(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/customs/sim-say" && m == "POST") { Write(c, SimSay.Say(Body(c)).ToString(), "application/json"); return true; }
            if (m == "POST" && (p == "/api/wheel/queue-add" || p == "/api/wheel/remove" || p == "/api/wheel/cancel" || p == "/api/customs/queue-add"))
            { string kind = p == "/api/wheel/queue-add" ? "wheeladd" : p == "/api/wheel/remove" ? "wheelremove" : p == "/api/wheel/cancel" ? "wheelcancel" : "queueadd"; Write(c, Bulk.Run(kind, Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/wheel/state" && m == "GET") { Write(c, Events.WheelState().ToString(), "application/json"); return true; }
            return false;
        }
    }
}
