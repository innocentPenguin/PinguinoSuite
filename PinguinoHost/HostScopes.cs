using System;
using System.Collections.Generic;
using System.Linq;

namespace PinguinoHost
{
    /// <summary>The ONE list of Twitch permissions the streamer sign-in asks for (bot accounts keep their own tokens and lists). Every row names the feature that
    /// calls it; a row that starts "reserved:" is asked for now, called by nothing yet (Ivan: widest sign-in Twitch allows, so no new approval later). Adding a Twitch call = add its scope here, then Ivan re-signs in once (the Host page and the
    /// prestream check list what is missing).</summary>
    public static partial class HostApi
    {
        // { scope, feature that uses it, "1" = the normal stream breaks without it }
        public static readonly string[][] ScopeInfo = {
            new[] { "chat:read", "reading chat (IRC)", "1" },
            new[] { "chat:edit", "sending chat, fallback sender (IRC)", "1" },
            new[] { "user:write:chat", "bots and the Host posting in chat; Multi sends", "1" },
            new[] { "user:read:chat", "Multi's Twitch chat connector reads chat through EventSub", "0" },
            new[] { "channel:read:subscriptions", "sub / resub / gift EventSub alerts and the Helix subscriber pull", "1" },
            new[] { "bits:read", "cheer EventSub alerts and the bits leaderboard", "1" },
            new[] { "moderator:read:followers", "follow EventSub alerts", "1" },
            new[] { "channel:read:redemptions", "channel-point redemption events", "1" },
            new[] { "channel:manage:redemptions", "creating/editing the Host's own rewards, refunding and completing redemptions (song requests, timeout, Speak)", "1" },
            new[] { "moderator:manage:banned_users", "timeouts and bans from commands and the timeout reward; Multi moderation", "1" },
            new[] { "moderator:manage:chat_messages", "deleting chat messages (Multi moderation)", "0" },
            new[] { "moderation:read", "moderator checks (is the bot a mod, moderator list)", "1" },
            new[] { "channel:moderate", "ban / unban / moderator add-remove EventSub events", "1" },
            new[] { "moderator:manage:automod", "AutoMod held-message events and approve / deny", "0" },
            new[] { "moderator:manage:shoutouts", "native Twitch shoutouts (!shout, raid shoutout)", "0" },
            new[] { "moderator:read:chatters", "who is in the chatroom (points, watch time)", "0" },
            new[] { "moderator:manage:chat_settings", "!slow / !emote-only / !followers / !subs-only", "0" },
            new[] { "moderator:manage:announcements", "!announce and milestone announcements", "0" },
            new[] { "moderator:manage:shield_mode", "!shield on|off", "0" },
            new[] { "clips:edit", "!clip and the recap clips", "1" },
            new[] { "channel:read:ads", "ad schedule (!preroll, ad commands, ad triggers)", "0" },
            new[] { "channel:edit:commercial", "!ad (Ivan only)", "0" },
            new[] { "channel:manage:broadcast", "!title / !game, stream markers and the Speak channel update", "0" },
            new[] { "channel:read:goals", "goal EventSub events", "0" },
            new[] { "channel:read:hype_train", "hype train EventSub events", "0" },
            new[] { "channel:manage:polls", "!poll", "0" },
            new[] { "channel:read:polls", "poll EventSub events and results", "0" },
            new[] { "channel:manage:predictions", "!predict / !lock / !resolve / !cancel", "0" },
            new[] { "channel:read:predictions", "prediction EventSub events and results", "0" },
            new[] { "channel:manage:raids", "!raid (Ivan only, trusted list, confirmed)", "0" },
            new[] { "channel:manage:vips", "!vip / !unvip", "0" },
            // Reserved: nothing calls these yet. Ivan asked for the widest sign-in Twitch allows so a new feature never means another approval.
            // Left out on purpose: channel:read:stream_key (the stream key), user:read:email, channel:manage:videos (deletes VODs), user:edit (legacy), whispers:read (PubSub only, which no longer exists).
            new[] { "channel:manage:moderators", "reserved: adding and removing moderators (Ivan only)", "0" },
            new[] { "channel:read:vips", "reserved: !vips list", "0" },
            new[] { "moderator:manage:blocked_terms", "reserved: blocked terms list", "0" },
            new[] { "moderator:manage:warnings", "reserved: chat warnings", "0" },
            new[] { "moderator:manage:unban_requests", "reserved: unban requests queue", "0" },
            new[] { "moderator:read:automod_settings", "reserved: reading AutoMod settings", "0" },
            new[] { "moderator:read:suspicious_users", "reserved: suspicious user list", "0" },
            new[] { "moderator:read:shield_mode", "reserved: shield mode state", "0" },
            new[] { "user:manage:whispers", "reserved: opt-in whisper reminders", "0" },
            new[] { "channel:manage:schedule", "reserved: stream schedule edits", "0" },
            new[] { "channel:read:charity", "reserved: charity campaign alerts", "0" },
            new[] { "channel:read:guest_star", "reserved: Guest Star state", "0" },
            new[] { "channel:manage:guest_star", "reserved: Guest Star control", "0" },
            new[] { "channel:read:editors", "reserved: channel editors list", "0" },
            new[] { "user:read:follows", "reserved: followed channels", "0" },
            new[] { "user:read:subscriptions", "reserved: subscription checks", "0" },
            new[] { "user:read:emotes", "reserved: emote lists", "0" },
            new[] { "user:bot", "reserved: bot accounts in chat (EventSub)", "0" },
            new[] { "channel:bot", "reserved: bot accounts in chat (EventSub)", "0" },
            new[] { "analytics:read:games", "reserved: game analytics", "0" },
            new[] { "moderator:read:moderators", "reserved: moderator list", "0" },
            new[] { "moderator:read:vips", "reserved: VIP list", "0" },
            new[] { "channel:manage:ads", "reserved: ad schedule snooze", "0" },
            new[] { "analytics:read:extensions", "reserved: extension analytics", "0" },
            new[] { "channel:manage:clips", "reserved: managing clips", "0" },
            new[] { "channel:manage:extensions", "reserved: extension configuration", "0" },
            new[] { "editor:manage:clips", "reserved: clips as an editor", "0" },
            new[] { "moderator:manage:automod_settings", "reserved: AutoMod settings", "0" },
            new[] { "moderator:read:banned_users", "reserved: ban list", "0" },
            new[] { "moderator:read:blocked_terms", "reserved: blocked terms list (read)", "0" },
            new[] { "moderator:read:chat_messages", "reserved: reading chat messages through EventSub", "0" },
            new[] { "moderator:read:chat_settings", "reserved: reading chat settings (slow, followers-only...)", "0" },
            new[] { "moderator:read:guest_star", "reserved: Guest Star (moderator view)", "0" },
            new[] { "moderator:manage:guest_star", "reserved: Guest Star (moderator control)", "0" },
            new[] { "moderator:read:shoutouts", "reserved: shoutout events", "0" },
            new[] { "moderator:manage:suspicious_users", "reserved: suspicious user handling", "0" },
            new[] { "moderator:read:unban_requests", "reserved: unban requests (read)", "0" },
            new[] { "moderator:read:warnings", "reserved: chat warnings (read)", "0" },
            new[] { "user:edit:broadcast", "reserved: broadcast configuration", "0" },
            new[] { "user:read:broadcast", "reserved: broadcast configuration (read)", "0" },
            new[] { "user:read:blocked_users", "reserved: blocked users list", "0" },
            new[] { "user:manage:blocked_users", "reserved: blocking and unblocking users", "0" },
            new[] { "user:manage:chat_color", "reserved: chat colour", "0" },
            new[] { "user:read:moderated_channels", "reserved: channels the account moderates", "0" },
            new[] { "user:read:whispers", "reserved: reading whispers", "0" } };

        /// <summary>Space-separated list sent to Twitch's authorize page.</summary>
        public static readonly string Scopes = string.Join(" ", ScopeInfo.Select(i => i[0]));

        /// <summary>Scopes of the list that the token does not carry (the scopes Twitch returned at validate), in list order.</summary>
        public static List<string> MissingScopes(IEnumerable<string> have)
        {
            var h = new HashSet<string>(have ?? new string[0]);
            return ScopeInfo.Select(i => i[0]).Where(s => !h.Contains(s)).ToList();
        }

        /// <summary>One line for the Host page: empty when complete.</summary>
        public static string MissingScopesText(IEnumerable<string> have)
        {
            var m = MissingScopes(have);
            if (m.Count == 0) return "";
            // a short line for the Host page: how many and the first 3; the whole list stays in the "missing" array
            return "missing scopes: " + (m.Count <= 3 ? string.Join(", ", m) : m.Count + " (" + string.Join(", ", m.Take(3)) + ", ...)") + " (sign the streamer in again, once)";
        }
    }
}
