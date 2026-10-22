using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Channel title / category changes and guarded timeouts with the streamer token. Shared by the chat commands (title, game) and the loopback endpoints
    /// POST /api/channel/update and POST /api/mod/timeout (Speak module). Needs channel:manage:broadcast and moderator:manage:banned_users. Every endpoint call is audit-logged.</summary>
    public static class ChannelControl
    {
        static string AuditP { get { return Path.Combine(HostApi.DataDir, "runtime", "mod_audit.log"); } }
        public static void Audit(string who, string what, string detail)
        {
            try { Directory.CreateDirectory(Path.GetDirectoryName(AuditP)); File.AppendAllText(AuditP, DateTime.UtcNow.ToString("o") + "\t" + who + "\t" + what + "\t" + (detail ?? "").Replace('\n', ' ').Replace('\r', ' ') + "\n"); } catch (Exception) { }
            Clog.Info("channel", who + " " + what + " " + detail);
        }

        /// <summary>Resolves a category by name: exact (case-insensitive) match, else a single search hit; several candidates are reported as an error.</summary>
        public static string FindGame(string name, out string gameName, out string error)
        {
            gameName = ""; error = ""; JToken d; string err;
            TwitchApi.Call(HttpMethod.Get, "/games?name=" + Uri.EscapeDataString(name), null, out d, out err);
            var g = (d as JArray)?.FirstOrDefault(); if (g != null) { gameName = (string)g["name"]; return (string)g["id"]; }
            if (err != "") { error = err; return ""; }
            TwitchApi.Call(HttpMethod.Get, "/search/categories?first=8&query=" + Uri.EscapeDataString(name), null, out d, out err);
            var list = (d as JArray) ?? new JArray(); if (err != "") { error = err; return ""; }
            if (list.Count == 0) { error = "no category found for '" + name + "'"; return ""; }
            var exact = list.Where(x => string.Equals((string)x["name"], name, StringComparison.OrdinalIgnoreCase)).ToList();
            JToken pick = exact.Count == 1 ? exact[0] : list.Count == 1 ? list[0] : null;
            if (pick == null) { error = "ambiguous category '" + name + "': " + string.Join(", ", list.Take(5).Select(x => (string)x["name"])); return ""; }
            gameName = (string)pick["name"]; return (string)pick["id"];
        }

        /// <summary>GET /api/channel/info: the live title, category and tags (so the editor can load them)</summary>
        public static JObject Info()
        {
            JToken d; string err; string code = TwitchApi.Call(HttpMethod.Get, "/channels?broadcaster_id={bid}", null, out d, out err);
            var c = (d as JArray)?.FirstOrDefault() as JObject;
            if (c == null) return new JObject { { "ok", false }, { "error", err != "" ? err : "Twitch answered HTTP " + code } };
            return new JObject { { "ok", true }, { "title", (string)c["title"] }, { "game", (string)c["game_name"] }, { "tags", c["tags"] as JArray ?? new JArray() } };
        }

        /// <summary>tags: max 10, each 1-25 letters/digits (Twitch allows no spaces or symbols); returns null and an error for bad input</summary>
        public static JArray CleanTags(JToken tags, out string error)
        {
            error = ""; var o = new JArray(); var arr = tags as JArray; if (arr == null) { error = "tags must be a list"; return null; }
            foreach (var t in arr)
            {
                string s = ((string)t ?? "").Trim().Replace(" ", ""); if (s == "") continue;
                if (s.Length > 25) { error = "tag '" + s + "' is longer than 25 characters"; return null; }
                if (!System.Text.RegularExpressions.Regex.IsMatch(s, @"^[\p{L}\p{N}]+$")) { error = "tag '" + s + "' may only use letters and numbers"; return null; }
                if (!o.Any(x => string.Equals((string)x, s, StringComparison.OrdinalIgnoreCase))) o.Add(s);
            }
            if (o.Count > 10) { error = "at most 10 tags"; return null; }
            return o;
        }

        public static JObject Update(string title, string game, JToken tags = null)
        {
            var body = new JObject(); string gname = null;
            if (tags != null && tags.Type != JTokenType.Null) { string terr; var ct = CleanTags(tags, out terr); if (ct == null) return new JObject { { "ok", false }, { "error", terr } }; body["tags"] = ct; }
            if (!string.IsNullOrWhiteSpace(title)) { title = title.Trim(); if (title.Length > 140) title = title.Substring(0, 140); body["title"] = title; }
            if (!string.IsNullOrWhiteSpace(game))
            {
                string err; string id = FindGame(game.Trim(), out gname, out err);
                if (id == "") return new JObject { { "ok", false }, { "error", err } };
                body["game_id"] = id;
            }
            if (body.Count == 0) return new JObject { { "ok", false }, { "error", "give a title, a game and/or tags" } };
            JToken d; string e2; string code = TwitchApi.Call(new HttpMethod("PATCH"), "/channels?broadcaster_id={bid}", body, out d, out e2);
            if (code != "204" && code != "200") return new JObject { { "ok", false }, { "error", e2 != "" ? e2 : "Twitch answered HTTP " + code } };
            return new JObject { { "ok", true }, { "game", gname }, { "title", (string)body["title"] }, { "tags", body["tags"] } };
        }

        static readonly string[] ProtectedLogins = { "nightbot", "streamelements", "pinguinob0t", "chattypinguino", "pinguinohelper" };
        public static JObject Timeout(string user, int seconds, string reason)
        {
            user = (user ?? "").Trim().TrimStart('@').ToLowerInvariant();
            if (!System.Text.RegularExpressions.Regex.IsMatch(user, "^[a-z0-9_]{2,25}$")) return new JObject { { "ok", false }, { "error", "bad user name" } };
            if (seconds < 1) seconds = 1; if (seconds > 1209600) seconds = 1209600;
            var cr = HostApi.StreamerCreds(); string ch = ((string)cr["Login"] ?? "").ToLowerInvariant(), ch2 = ((string)cr["Channel"] ?? "").ToLowerInvariant();
            if (user == ch || user == ch2) return new JObject { { "ok", false }, { "error", "refused: that is the broadcaster" } };
            if (ProtectedLogins.Contains(user) || Boards.IsBot(user) || Boards.AllBots().Contains(user)) return new JObject { { "ok", false }, { "error", "refused: bot account" } };
            if (Roster.RoleOf(user) >= 2) return new JObject { { "ok", false }, { "error", "refused: moderator or VIP" } };
            string err; string uid = TwitchApi.UserId(user, out err); if (uid == "") return new JObject { { "ok", false }, { "error", err } };
            JToken d; TwitchApi.Call(HttpMethod.Get, "/moderation/moderators?broadcaster_id={bid}&user_id=" + uid, null, out d, out err);
            if ((d as JArray)?.Count > 0) return new JObject { { "ok", false }, { "error", "refused: moderator" } };
            if (err != "") return new JObject { { "ok", false }, { "error", "could not verify that the user is not a moderator: " + err } };
            var body = new JObject { { "data", new JObject { { "user_id", uid }, { "duration", seconds }, { "reason", (reason ?? "").Length > 500 ? reason.Substring(0, 500) : (reason ?? "") } } } };
            string code = TwitchApi.Call(HttpMethod.Post, "/moderation/bans?broadcaster_id={bid}&moderator_id=" + TwitchApi.BroadcasterId(), body, out d, out err);
            if (code != "200") return new JObject { { "ok", false }, { "error", err != "" ? err : "Twitch answered HTTP " + code } };
            return new JObject { { "ok", true } };
        }
    }
}
