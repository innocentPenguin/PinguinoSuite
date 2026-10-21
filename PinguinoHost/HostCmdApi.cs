using System.Net;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    public static partial class HostApi
    {
        /// <summary>GET /api/commands/profiles, GET /api/commands/archive, POST /api/commands/profile | archive | restore (POST is Origin/Bearer gated by Handle).</summary>
        static bool CmdRoutes(HttpListenerContext c, string p, string m)
        {
            if (!p.StartsWith("/api/commands/")) return false;
            if (p == "/api/commands/profiles" && m == "GET") { Write(c, CmdProfiles.List().ToString(), "application/json"); return true; }
            if (p == "/api/commands/all" && m == "GET") { Write(c, CmdProfiles.All().ToString(), "application/json"); return true; }
            if (p == "/api/commands/archive" && m == "GET") { Write(c, CmdProfiles.ArchiveList().ToString(), "application/json"); return true; }
            if (p == "/api/commands/profile" && m == "POST") { Write(c, CmdProfiles.Edit(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/commands/archive" && m == "POST") { Write(c, CmdProfiles.Archive(Body(c)).ToString(), "application/json"); return true; }
            if (p == "/api/commands/restore" && m == "POST") { Write(c, CmdProfiles.Restore(Body(c)).ToString(), "application/json"); return true; }
            return false;
        }
    }
}
