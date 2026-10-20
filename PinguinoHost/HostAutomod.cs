using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Messages AutoMod is holding (EventSub automod.message.hold, dropped on automod.message.update) so a mod can release one from chat: !allow [user].
    /// Releasing uses POST /moderation/automod/message {user_id, msg_id, action:ALLOW} (scope moderator:manage:automod). Only the newest 30 held messages are kept, for 30 minutes.</summary>
    public static class AutomodHeld
    {
        class Item { public string Id, User, Text; public DateTime At; }
        static readonly List<Item> Held = new List<Item>(); static readonly object L = new object();

        public static void Note(string type, JObject e)
        {
            string id = (string)e["message_id"] ?? ""; if (id == "") return;
            lock (L)
            {
                Held.RemoveAll(x => x.Id == id || (DateTime.UtcNow - x.At).TotalMinutes > 30);
                if (type == "automod.message.hold")
                {
                    Held.Add(new Item { Id = id, User = ((string)e["user_login"] ?? "").ToLowerInvariant(), Text = ((string)e["message"]?["text"] ?? ""), At = DateTime.UtcNow });
                    while (Held.Count > 30) Held.RemoveAt(0);
                }
            }
        }

        /// <summary>!allow [user]: releases that user's newest held message, or the newest one of all.</summary>
        public static string Allow(string[] args, Action<string> say)
        {
            string who = args.Length > 0 ? args[0].TrimStart('@').ToLowerInvariant() : ""; Item it;
            lock (L) { Held.RemoveAll(x => (DateTime.UtcNow - x.At).TotalMinutes > 30); it = Held.LastOrDefault(x => who == "" || x.User == who); }
            if (it == null) { say(who == "" ? "No message is being held by AutoMod right now." : "No held message from " + who + " that I know of."); return "none"; }
            JToken d; string err; string code = TwitchApi.Call(HttpMethod.Post, "/moderation/automod/message", new JObject { { "user_id", TwitchApi.BroadcasterId() }, { "msg_id", it.Id }, { "action", "ALLOW" } }, out d, out err);
            if (code == "200" || code == "204") { lock (L) Held.Remove(it); say("Released " + it.User + "'s held message."); return "ok"; }
            string why = err != "" ? err : "Twitch answered HTTP " + code; say("Could not release it: " + (why.Length > 120 ? why.Substring(0, 120) : why)); return why;
        }
    }
}
