using System.Net;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    public static partial class HostApi
    {
        /// <summary>Discord go-live routes (170): GET /api/discord (status + settings, never the webhook), POST /api/discord/settings, POST /api/discord/test {mode: status|dry|send|end}, POST /api/discord/secret {webhook} (write-only, "" removes).</summary>
        static bool DiscordRoutes(HttpListenerContext c, string p, string m)
        {
            if (p == "/api/discord" && m == "GET") { Write(c, DiscordAnnounce.Api().ToString(), "application/json"); return true; }
            if (p == "/api/discord/settings" && m == "POST") { Write(c, DiscordAnnounce.SaveSettings(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/discord/test" && m == "POST") { Write(c, DiscordAnnounce.Test((string)Body(c)["mode"]).ToString(), "application/json"); return true; }
            if (p == "/api/discord/secret" && m == "POST") { Write(c, DiscordAnnounce.SetSecret(Body(c)).ToString(), "application/json"); return true; }
            return false;
        }
    }
}
