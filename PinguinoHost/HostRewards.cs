using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Channel point rewards the Host owns. Twitch only lets the app (client id) that created a reward refund or fulfil its redemptions,
    /// so a reward made by another app (Streamer.bot) answers 403 "Client-Id must match" forever. List() shows which rewards are ours,
    /// Create() makes our own copy (explicit action, never automatic) and can point the song request automation at it.
    /// Steps for the streamer: Docs\SONG_REQUEST_REWARD.md.</summary>
    public static class Rewards
    {
        static readonly HashSet<string> _foreign = new HashSet<string>(); static readonly object L = new object();

        /// <summary>true once Twitch refused a redemption change of this reward because another app made it (the Host stops asking)</summary>
        public static bool KnownForeign(string rewardId) { lock (L) return rewardId != null && _foreign.Contains(rewardId); }

        /// <summary>called when a refund/fulfil came back 403 "Client-Id must match": one warning per reward, then silence</summary>
        public static void NoteNotOwned(string rewardId, string err)
        {
            if (string.IsNullOrEmpty(rewardId) || (err ?? "").IndexOf("Client-Id", StringComparison.OrdinalIgnoreCase) < 0) return;
            lock (L) _foreign.Add(rewardId);
            WarnOnce(rewardId);
        }
        static readonly HashSet<string> _warned = new HashSet<string>();
        /// <summary>the one-time warning for a reward the Host does not own (also when a listing already told us, so the skipped refund is not silent)</summary>
        public static void WarnOnce(string rewardId)
        {
            lock (L) { if (!_warned.Add(rewardId)) return; }
            Clog.Warn("rewards", "reward " + rewardId + " was created by another app, so the Host can never refund or fulfil its redemptions. Create the Host's own reward (POST /api/rewards/create, steps in Docs/SONG_REQUEST_REWARD.md) and delete the old one.");
            try { EventLog.Backend("rewards", "reward " + rewardId + " is not owned by the Host: refunds and auto-complete cannot work for it", new JObject { { "reward", rewardId } }, "warn"); } catch (Exception) { }
        }

        public static JObject List()
        {
            JObject all, mine; string e1, e2;
            string c1 = TwitchApi.CallFull(HttpMethod.Get, "/channel_points/custom_rewards?broadcaster_id={bid}", out all, out e1);
            if (!c1.StartsWith("2")) return new JObject { { "ok", false }, { "error", "HTTP " + c1 + " " + e1 } };
            string c2 = TwitchApi.CallFull(HttpMethod.Get, "/channel_points/custom_rewards?broadcaster_id={bid}&only_manageable_rewards=true", out mine, out e2);
            if (!c2.StartsWith("2")) return new JObject { { "ok", false }, { "error", "HTTP " + c2 + " " + e2 } };
            var ours = new HashSet<string>(((mine["data"] as JArray) ?? new JArray()).Select(x => (string)x["id"]));
            var rows = new JArray();
            foreach (var r in (all["data"] as JArray) ?? new JArray())
            {
                string id = (string)r["id"]; bool own = ours.Contains(id);
                if (!own) lock (L) _foreign.Add(id); else lock (L) _foreign.Remove(id);
                rows.Add(new JObject { { "id", id }, { "title", r["title"] }, { "cost", r["cost"] }, { "prompt", r["prompt"] }, { "enabled", r["is_enabled"] }, { "inputRequired", r["is_user_input_required"] }, { "owned", own } });
            }
            return new JObject { { "ok", true }, { "rewards", rows } };
        }

        /// <summary>{title (default "Song Request"), cost, prompt, inputRequired, automation (default "spotify-redeem": its redeem trigger is pointed at the new reward)}</summary>
        public static JObject Create(JObject b)
        {
            string title = ((string)b["title"] ?? "Song Request").Trim(); if (title == "" || title.Length > 45) return Err("title required (max 45 characters)");
            var l = List(); if (!(bool)l["ok"]) return l;
            var same = ((JArray)l["rewards"]).OfType<JObject>().FirstOrDefault(r => string.Equals((string)r["title"], title, StringComparison.OrdinalIgnoreCase));
            if (same != null && (bool)same["owned"]) return Switch(b, title, (string)same["id"], new JObject { { "ok", true }, { "already", true }, { "id", same["id"] } });
            int? cost = (int?)b["cost"] ?? (int?)same?["cost"]; if (cost == null || cost < 1) return Err("cost required (points), e.g. {\"cost\":1000}");
            if (same != null) return Err("a reward called \"" + title + "\" made by another app already exists (id " + same["id"] + ") and Twitch does not allow two with one title. In Twitch's Creator Dashboard rename or delete the old one first, then call this again (or pass another title).");
            string prompt = (string)b["prompt"] ?? (string)same?["prompt"] ?? "Type the song name or a Spotify/YouTube link";
            var body = new JObject { { "title", title }, { "cost", cost }, { "prompt", prompt }, { "is_user_input_required", (bool?)b["inputRequired"] ?? true } };
            JToken d; string err; string code = TwitchApi.Call(HttpMethod.Post, "/channel_points/custom_rewards?broadcaster_id={bid}", body, out d, out err);
            if (!code.StartsWith("2") || !(d is JArray a) || a.Count == 0) return Err("Twitch refused (HTTP " + code + "): " + err + (code == "401" || code == "403" ? " (the streamer needs channel:manage:redemptions: sign in again on the Host setup page)" : ""));
            string id = (string)a[0]["id"]; lock (L) _foreign.Remove(id);
            Clog.Info("rewards", "created the Host's own reward \"" + title + "\" (" + id + ")");
            try { ChannelControl.Audit("app", "rewards/create", "title=" + title + " id=" + id); } catch (Exception) { }
            return Switch(b, title, id, new JObject { { "ok", true }, { "created", true }, { "id", id }, { "title", title }, { "cost", cost } });
        }
        static JObject Switch(JObject b, string title, string id, JObject res)
        {
            string act = (string)b["automation"] ?? "spotify-redeem";
            res["automationSwitched"] = act != "" && Auto.SetRedeemReward(act, title, id); res["automation"] = act;
            return res;
        }
        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }
    }
}
