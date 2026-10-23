using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Viewer intros: each viewer can set a short text + one sound that Multi plays when they chat for the first time in a stream.
    /// One record per viewer ("platform:user_id"): {platform, user_id, login, text, sound_id, status pending|approved|rejected|removed, submitted_at, approved_by, decided_at}.
    /// Submit/edit goes through a profanity + link filter, then waits for a mod (status pending); an edit of an approved intro goes back to pending. Every decision is written to the mod audit.
    /// Multi reads GET /api/intro?platform=&amp;user_id= (approved only, else 404). Mods/the site: GET /api/intros?status=, POST /api/intros {action: submit|remove|approve|reject|settings, ...}.
    /// The site reaches the same actions through the economy queue (intro_submit | intro_remove | intro_approve | intro_reject). File: Data\viewer_intros.json.</summary>
    public static class ViewerIntro
    {
        static readonly object L = new object();
        static string P { get { return Path.Combine(HostApi.DataDir, "viewer_intros.json"); } }
        static readonly Regex RxPlat = new Regex(@"^[a-z]{3,12}$"), RxId = new Regex(@"^[A-Za-z0-9_\-]{1,64}$"), RxSound = new Regex(@"^[A-Za-z0-9_\-\.]{1,60}$");
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        static JObject Doc()
        {
            var d = SiteHttp.ReadJ(P); var s = new JObject { { "maxLen", 80 }, { "requireApproval", true } };
            if (d["settings"] is JObject o) foreach (var p in o.Properties()) s[p.Name] = p.Value;
            d["settings"] = s; if (!(d["intros"] is JObject)) d["intros"] = new JObject(); return d;
        }
        static void Save(JObject d) { Directory.CreateDirectory(Path.GetDirectoryName(P)); SiteHttp.WriteJ(P, d); }
        static string Key(string platform, string uid) { return platform + ":" + uid; }
        static JObject Fail(string e) { return new JObject { { "ok", false }, { "error", e } }; }

        // ---- filters ----
        static readonly string[] Bad = { "fuck", "bitch", "cunt", "pussy", "asshole", "bastard", "whore", "nigg", "fagg", "retard", "hitler", "killyourself" };
        static readonly Regex BadWord = new Regex(@"\b(shit\w*|dick|cock|slut|rape|rapist|nazi|kys|porn|cum|sex|anal)\b");
        static string Norm(string t)
        {
            t = (t ?? "").ToLowerInvariant();
            var sb = new StringBuilder();
            foreach (char ch in t)
            {
                switch (ch) { case '0': sb.Append('o'); break; case '1': case '!': case '|': sb.Append('i'); break; case '3': sb.Append('e'); break; case '4': case '@': sb.Append('a'); break; case '5': case '$': sb.Append('s'); break; case '7': sb.Append('t'); break; default: sb.Append(ch); break; }
            }
            return sb.ToString();
        }
        /// <summary>null when fine, otherwise the reason</summary>
        public static string Check(string text, int maxLen)
        {
            text = (text ?? "").Trim();
            if (text.Length == 0) return "write something for your intro";
            if (text.Length > maxLen) return "your intro is too long (max " + maxLen + " characters)";
            foreach (char ch in text) if (ch < ' ') return "no line breaks please";
            if (Regex.IsMatch(text, @"(https?:|www\.|\b[a-z0-9\-]+\.(com|net|org|io|gg|tv|ly|me|co|xyz|app|dev|link)\b)", RegexOptions.IgnoreCase)) return "no links in an intro";
            if (Regex.IsMatch(text, @"^[!/.][a-z]", RegexOptions.IgnoreCase)) return "an intro cannot start a chat command";
            string n = Norm(text), squashed = Regex.Replace(n, @"[^a-z]", "");
            if (BadWord.IsMatch(n)) return "that word is not allowed in an intro";
            foreach (var b in Bad) if (squashed.Contains(b)) return "that word is not allowed in an intro";
            return null;
        }

        // ---- actions ----
        public static JObject Submit(string platform, string uid, string login, string text, string sound)
        {
            platform = (platform ?? "twitch").Trim().ToLowerInvariant(); uid = (uid ?? "").Trim(); sound = (sound ?? "").Trim(); login = (login ?? "").Trim().TrimStart('@').ToLowerInvariant();
            if (!RxPlat.IsMatch(platform) || !RxId.IsMatch(uid)) return Fail("bad viewer");
            if (sound != "" && !RxSound.IsMatch(sound)) return Fail("bad sound");
            lock (L)
            {
                var d = Doc(); var s = (JObject)d["settings"]; int max = Math.Max(10, Math.Min(200, (int?)s["maxLen"] ?? 80));
                text = Regex.Replace((text ?? "").Trim(), @"[ \t]+", " ");
                string why = Check(text, max); if (why != null) return Fail(why);
                bool auto = (bool?)s["requireApproval"] == false;
                var it = new JObject { { "platform", platform }, { "user_id", uid }, { "login", login }, { "text", text }, { "sound_id", sound }, { "status", auto ? "approved" : "pending" }, { "submitted_at", Now() }, { "approved_by", auto ? "auto" : "" }, { "decided_at", auto ? Now() : 0 } };
                ((JObject)d["intros"])[Key(platform, uid)] = it; Save(d);
                ModAudit.Log(login == "" ? uid : login, "viewer", "intro submitted", Key(platform, uid), "", text);
                return new JObject { { "ok", true }, { "intro", it }, { "message", auto ? "Your intro is live." : "Your intro was sent to the mods for approval." } };
            }
        }
        public static JObject Remove(string platform, string uid)
        {
            platform = (platform ?? "twitch").Trim().ToLowerInvariant(); uid = (uid ?? "").Trim();
            lock (L)
            {
                var d = Doc(); var it = ((JObject)d["intros"])[Key(platform, uid)] as JObject; if (it == null) return Fail("no intro to remove");
                string was = (string)it["text"]; it["status"] = "removed"; it["text"] = ""; it["sound_id"] = ""; it["decided_at"] = Now(); Save(d);
                ModAudit.Log((string)it["login"] ?? uid, "viewer", "intro removed", Key(platform, uid), was, "");
                return new JObject { { "ok", true }, { "message", "Your intro was removed." } };
            }
        }
        public static JObject Decide(string platform, string uid, bool approve, string by)
        {
            platform = (platform ?? "twitch").Trim().ToLowerInvariant(); uid = (uid ?? "").Trim(); by = string.IsNullOrWhiteSpace(by) ? "suite" : by.Trim().TrimStart('@').ToLowerInvariant();
            lock (L)
            {
                var d = Doc(); var it = ((JObject)d["intros"])[Key(platform, uid)] as JObject; if (it == null) return Fail("no such intro");
                if ((string)it["status"] != "pending") return Fail("that intro is not waiting for approval");
                it["status"] = approve ? "approved" : "rejected"; it["approved_by"] = by; it["decided_at"] = Now(); Save(d);
                ModAudit.Log(by, "mod", approve ? "intro approved" : "intro rejected", Key(platform, uid) + " " + (string)it["login"], "", (string)it["text"]);
                return new JObject { { "ok", true }, { "intro", it } };
            }
        }
        /// <summary>the approved intro Multi plays; null = none</summary>
        public static JObject Approved(string platform, string uid)
        {
            platform = (platform ?? "twitch").Trim().ToLowerInvariant(); uid = (uid ?? "").Trim();
            lock (L)
            {
                var it = ((JObject)Doc()["intros"])[Key(platform, uid)] as JObject;
                if (it == null || (string)it["status"] != "approved" || string.IsNullOrEmpty((string)it["text"])) return null;
                return new JObject { { "text", it["text"] }, { "sound_id", it["sound_id"] }, { "status", "approved" } };
            }
        }
        /// <summary>the intro rows the site keeps in step with the Host (POST /api/bot/economy/users, key "intros"): removed rows are sent with status "removed" and empty text; newest 500</summary>
        public static JArray PushList()
        {
            lock (L)
            {
                var d = Doc();
                return new JArray(((JObject)d["intros"]).Properties().Select(p => (JObject)p.Value).OrderByDescending(x => Math.Max((long?)x["decided_at"] ?? 0, (long?)x["submitted_at"] ?? 0)).Take(500).Select(x =>
                    new JObject { { "login", (string)x["login"] ?? "" }, { "user_id", (string)x["user_id"] ?? "" }, { "text", (string)x["text"] ?? "" }, { "sound_id", (string)x["sound_id"] ?? "" }, { "status", (string)x["status"] ?? "" },
                        { "note", (string)x["status"] == "approved" || (string)x["status"] == "rejected" ? "by " + ((string)x["approved_by"] ?? "") : "" }, { "updatedAt", Math.Max((long?)x["decided_at"] ?? 0, (long?)x["submitted_at"] ?? 0) } }));
            }
        }
        public static int MaxLen() { lock (L) return Math.Max(10, Math.Min(200, (int?)Doc()["settings"]["maxLen"] ?? 80)); }
        /// <summary>same as Approved, found by chat login when the caller has no user id (newest decision wins)</summary>
        public static JObject ApprovedByLogin(string platform, string login)
        {
            platform = (platform ?? "twitch").Trim().ToLowerInvariant(); login = (login ?? "").Trim().TrimStart('@').ToLowerInvariant(); if (login == "") return null;
            lock (L)
            {
                var it = ((JObject)Doc()["intros"]).Properties().Select(p => p.Value as JObject).Where(x => x != null && (string)x["platform"] == platform && (string)x["login"] == login && (string)x["status"] == "approved" && !string.IsNullOrEmpty((string)x["text"]))
                    .OrderByDescending(x => (long?)x["decided_at"] ?? 0).FirstOrDefault();
                return it == null ? null : new JObject { { "text", it["text"] }, { "sound_id", it["sound_id"] }, { "status", "approved" } };
            }
        }
        public static JObject Mine(string platform, string uid)
        {
            platform = (platform ?? "twitch").Trim().ToLowerInvariant(); uid = (uid ?? "").Trim();
            lock (L) { var d = Doc(); var it = ((JObject)d["intros"])[Key(platform, uid)] as JObject; return new JObject { { "ok", true }, { "intro", it }, { "maxLen", d["settings"]["maxLen"] } }; }
        }
        public static JObject List(string status)
        {
            lock (L)
            {
                var d = Doc(); var all = ((JObject)d["intros"]).Properties().Select(p => (JObject)p.Value).Where(x => string.IsNullOrEmpty(status) || (string)x["status"] == status).OrderBy(x => (long?)x["submitted_at"] ?? 0).ToList();
                return new JObject { { "ok", true }, { "settings", d["settings"] }, { "pending", ((JObject)d["intros"]).Properties().Count(p => (string)p.Value["status"] == "pending") }, { "intros", new JArray(all.Take(500)) } };
            }
        }
        static JObject SetSettings(JObject b)
        {
            lock (L)
            {
                var d = Doc(); var s = (JObject)d["settings"];
                if (b["maxLen"] != null) s["maxLen"] = Math.Max(10, Math.Min(200, (int)b["maxLen"]));
                if (b["requireApproval"] != null) s["requireApproval"] = (bool)b["requireApproval"];
                d["settings"] = s; Save(d); return new JObject { { "ok", true }, { "settings", s } };
            }
        }

        /// <summary>POST /api/intros and the queue actions share this</summary>
        public static JObject Act(string action, JObject b)
        {
            string plat = (string)b["platform"] ?? "twitch", uid = (string)b["user_id"] ?? (string)b["userId"] ?? "";
            switch ((action ?? "").ToLowerInvariant().Replace("intro_", ""))
            {
                case "submit": case "set": return Submit(plat, uid, (string)b["login"], (string)b["text"], (string)b["sound_id"]);
                case "remove": return Remove(plat, uid);
                case "approve": return Decide(plat, uid, true, (string)b["by"]);
                case "reject": return Decide(plat, uid, false, (string)b["by"]);
                case "settings": return SetSettings(b);
                default: return Fail("action must be submit, remove, approve, reject or settings");
            }
        }
    }
}
