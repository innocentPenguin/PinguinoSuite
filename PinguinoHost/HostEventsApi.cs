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
            if (p == "/api/customs/state" && m == "GET") { Write(c, CustomsView.State().ToString(), "application/json"); return true; }
            if (p == "/api/customs/mod" && m == "POST") { Write(c, CustomsView.Mod(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/wheel/state" && m == "GET") { Write(c, Events.WheelState().ToString(), "application/json"); return true; }
            return false;
        }
    }
}
