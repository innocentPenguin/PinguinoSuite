using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Master View bulk routes (all POST, same write gating as /api/customs/mod): wheel/queue-add, wheel/remove, wheel/cancel, customs/queue-add.
    /// They run the silent mod-only Core commands !wheeladd !wheelremove !wheelcancel !queueadd and return what the Core wrote to bulk_result.json.</summary>
    public static class Bulk
    {
        static readonly object L = new object();
        static string ResultFile(string d) { return Path.Combine(d, "bulk_result.json"); }

        static JArray Users(JObject b)
        {
            var u = new JArray();
            foreach (var x in (b["users"] as JArray ?? new JArray())) { var n = (x.Type == JTokenType.Object ? (string)x["login"] : (string)x) ?? ""; n = n.Trim().TrimStart('@').ToLowerInvariant(); if (n.Length > 0 && n.Length <= 40 && n.All(ch => char.IsLetterOrDigit(ch) || ch == '_') && !u.Any(y => (string)y == n)) u.Add(n); }
            return u;
        }

        public static JObject Run(string kind, JObject b)
        {
            var users = Users(b ?? new JObject());
            if (kind != "wheelcancel" && users.Count == 0) return new JObject { { "ok", false }, { "error", "users needed" } };
            lock (L)
            {
                var dirs = new[] { HostApi.DataDir, Path.Combine(HostApi.DataDir, "runtime") };
                foreach (var d in dirs) { try { File.Delete(ResultFile(d)); } catch (Exception) { } }
                HostApi.RunAsStreamerSync("!" + kind + " " + string.Join(" ", users.Select(x => (string)x)));
                JObject r = null;
                foreach (var d in dirs) { try { if (File.Exists(ResultFile(d))) { r = JObject.Parse(File.ReadAllText(ResultFile(d)).TrimStart((char)0xFEFF)); break; } } catch (Exception) { } }
                Events.Kick();
                if (r == null) return new JObject { { "ok", false }, { "error", "the bot did not answer (is customs running?)" } };
                if (r["ok"] != null && (bool)r["ok"] == false) return new JObject { { "ok", false }, { "error", (string)r["error"] ?? "failed" } };
                var o = new JObject { { "ok", true } };
                if (kind == "wheelremove") o["removed"] = r["removed"] ?? new JArray();
                else if (kind == "queueadd") { o["added"] = r["added"] ?? new JArray(); o["skipped"] = r["skipped"] ?? new JArray(); }
                else if (kind == "wheeladd") { o["added"] = r["added"] ?? new JArray(); o["skipped"] = r["skipped"] ?? new JArray(); }
                return o;
            }
        }
    }

    public static partial class HostApi
    {
        internal static void RunAsStreamerSync(string text)
        {
            string who = "innocentpenguin_"; try { var ch = (string)StreamerCreds()["Channel"]; if (!string.IsNullOrEmpty(ch)) who = ch; } catch (Exception) { }
            Control.Synthetic = true; try { Program.Dispatch(who, text, null, 4, "deck", false, null); } finally { Control.Synthetic = false; }
        }
    }
}
