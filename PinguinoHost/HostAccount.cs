using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Streamer-account API for the Suite's Accounts page. Never returns a token.</summary>
    public static partial class HostApi
    {
        // scope -> (feature text, needed for the normal stream)
        static readonly string[][] ScopeInfo = {
            new[] { "chat:read", "reading chat", "1" }, new[] { "chat:edit", "sending chat (fallback sender)", "1" }, new[] { "user:write:chat", "bots posting as themselves", "1" },
            new[] { "moderator:manage:banned_users", "timeouts and bans from commands", "1" }, new[] { "channel:read:subscriptions", "sub alerts", "1" },
            new[] { "bits:read", "cheer alerts", "1" }, new[] { "moderator:read:followers", "follow alerts", "1" }, new[] { "moderation:read", "moderator checks", "1" },
            new[] { "channel:read:redemptions", "channel-point redemptions", "1" }, new[] { "channel:moderate", "bans/moderation events (ban alert)", "1" },
            new[] { "clips:edit", "clips: !clip", "1" }, new[] { "channel:read:ads", "ads: !preroll / ad commands", "0" }, new[] { "moderator:manage:shoutouts", "native Twitch shoutouts (!shout)", "0" }, new[] { "moderator:read:chatters", "who is in the chatroom (points and watch time)", "0" },
            new[] { "channel:manage:broadcast", "!title / !game and the Speak channel update", "0" }, new[] { "channel:manage:redemptions", "refunding channel-point song requests the module turns down, and creating/editing rewards", "1" },
            new[] { "channel:read:goals", "goal announcements", "0" }, new[] { "channel:read:hype_train", "hype train announcements", "0" },
            new[] { "channel:manage:polls", "!poll", "0" }, new[] { "channel:read:polls", "poll events and results", "0" }, new[] { "channel:manage:predictions", "!predict / !lock / !resolve / !cancel", "0" }, new[] { "channel:read:predictions", "prediction events and results", "0" },
            new[] { "channel:manage:raids", "!raid (Ivan only, trusted list, confirmed)", "0" }, new[] { "channel:manage:moderators", "adding and removing moderators (Ivan only)", "0" }, new[] { "channel:read:vips", "!vips list", "0" }, new[] { "channel:manage:vips", "!vip / !unvip", "0" },
            new[] { "moderator:manage:chat_settings", "!slow / !emote-only / !followers / !subs-only", "0" }, new[] { "moderator:manage:announcements", "!announce and milestone announcements", "0" }, new[] { "moderator:manage:automod", "approving or denying held messages", "0" },
            new[] { "moderator:manage:blocked_terms", "blocked terms list", "0" }, new[] { "moderator:manage:chat_messages", "deleting chat messages", "0" }, new[] { "moderator:manage:warnings", "chat warnings", "0" }, new[] { "moderator:manage:unban_requests", "unban requests queue", "0" },
            new[] { "moderator:read:automod_settings", "reading AutoMod settings", "0" }, new[] { "moderator:read:suspicious_users", "suspicious user list", "0" }, new[] { "moderator:read:shield_mode", "shield mode state", "0" }, new[] { "moderator:manage:shield_mode", "!shield", "0" },
            new[] { "user:manage:whispers", "opt-in whisper reminders", "0" }, new[] { "channel:manage:schedule", "stream schedule edits", "0" }, new[] { "channel:edit:commercial", "!ad (Ivan only)", "0" }, new[] { "channel:read:charity", "charity campaign alerts", "0" },
            new[] { "channel:read:guest_star", "Guest Star state", "0" }, new[] { "channel:manage:guest_star", "Guest Star control", "0" }, new[] { "channel:read:editors", "channel editors list", "0" }, new[] { "user:read:chat", "EventSub chat events", "0" },
            new[] { "user:read:follows", "followed channels", "0" }, new[] { "user:read:subscriptions", "subscription checks", "0" }, new[] { "user:read:emotes", "emote lists", "0" }, new[] { "user:bot", "bot accounts in chat (EventSub)", "0" }, new[] { "channel:bot", "bot accounts in chat (EventSub)", "0" },
            new[] { "analytics:read:games", "game analytics", "0" }, new[] { "moderator:read:moderators", "moderator list", "0" }, new[] { "moderator:read:vips", "VIP list", "0" }, new[] { "channel:manage:ads", "ad schedule snooze", "0" } };

        static JObject AccountStreamer()
        {
            var s = LoadV(); string tok = (string)s["UserToken"], cid = (string)s["ClientId"];
            var have = new HashSet<string>(); JObject v = null; string err = null;
            if (!string.IsNullOrEmpty(tok))
                using (var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) })
                {
                    try
                    {
                        var rq = new HttpRequestMessage(HttpMethod.Get, "https://id.twitch.tv/oauth2/validate"); rq.Headers.Add("Authorization", "OAuth " + tok);
                        var r = http.SendAsync(rq).Result;
                        if (r.IsSuccessStatusCode) v = JObject.Parse(r.Content.ReadAsStringAsync().Result);
                        else err = r.StatusCode == HttpStatusCode.Unauthorized ? "token rejected or expired" : "Twitch answered HTTP " + (int)r.StatusCode;
                    }
                    catch (Exception ex) { err = "could not reach Twitch: " + ex.Message; }
                }
            if (v != null) foreach (var x in v["scopes"] as JArray ?? new JArray()) have.Add((string)x);
            var req = new JArray(); foreach (var i in ScopeInfo) req.Add(new JObject { { "scope", i[0] }, { "feature", i[1] }, { "needed", i[2] == "1" }, { "granted", have.Contains(i[0]) } });
            var o = new JObject { { "ok", true }, { "signedIn", v != null }, { "login", v?["login"] }, { "userId", v?["user_id"] }, { "displayName", v?["login"] },
                { "expiresInSec", v?["expires_in"] }, { "validatedAt", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "scopes", new JArray(have.OrderBy(x => x)) }, { "required", req },
                { "missing", new JArray(ScopeInfo.Where(i => !have.Contains(i[0])).Select(i => (JToken)i[0])) }, { "hasClientId", !string.IsNullOrEmpty(cid) } };
            if (err != null) o["error"] = err; else if (string.IsNullOrEmpty(tok)) o["error"] = "not signed in";
            return o;
        }
        static JObject AccountSignIn(bool open)
        {
            var cfg = Config(); string cid = (string)cfg["ClientId"];
            if (string.IsNullOrEmpty(cid)) return new JObject { { "ok", false }, { "error", "the Twitch Client ID is not set yet (bot setup page)" } };
            string u = "https://id.twitch.tv/oauth2/authorize?response_type=token&force_verify=true&state=streamer&client_id=" + Uri.EscapeDataString(cid)
                + "&redirect_uri=" + Uri.EscapeDataString((string)cfg["redirect"]) + "&scope=" + Uri.EscapeDataString((string)cfg["scopes"]);
            if (open) System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(u) { UseShellExecute = true });
            return new JObject { { "ok", true }, { "url", u }, { "opened", open } };
        }
        static JObject AccountSignOut()
        {
            var s = Load(); s["UserToken"] = ""; Save(s); Vault.Clear("HOST_SECRETS.UserToken");
            return new JObject { { "ok", true }, { "note", "Streamer token cleared. Restart the PinguinoHost module to apply." } };
        }
    }
}
