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
            if (!c1.StartsWith("2")) return ListErr(new JObject { { "ok", false }, { "error", "HTTP " + c1 + " " + e1 } });
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
        public const string ScopeMsg = "the streamer sign-in is missing the channel:manage:redemptions permission: sign in as streamer again on the Host setup page, then retry";
        static bool NotOwnerRefusal(string code, string err) { return code == "403" && (err ?? "").IndexOf("Client-Id", StringComparison.OrdinalIgnoreCase) >= 0; }
        static bool ScopeRefusal(string code, string err) { return (code == "401" || code == "403") && !NotOwnerRefusal(code, err); }
        static JObject ListErr(JObject l)
        {
            string e = (string)l["error"] ?? ""; if (e.StartsWith("HTTP 401") || e.StartsWith("HTTP 403")) { l["error"] = ScopeMsg; l["needsScope"] = true; }
            return l;
        }

        /// <summary>{rewardId, automation (default "spotify-redeem")}: points any reward-driven automation at a reward the Host OWNS. A reward made by another app answers needsTakeover (use Takeover).</summary>
        public static JObject Use(JObject b)
        {
            string id = ((string)b["rewardId"] ?? "").Trim(); if (id == "") return Err("rewardId required");
            var l = List(); if (!(bool)l["ok"]) return ListErr(l);
            var r = ((JArray)l["rewards"]).OfType<JObject>().FirstOrDefault(x => (string)x["id"] == id); if (r == null) return Err("no reward with that id on this channel");
            if (!(bool)r["owned"]) return new JObject { { "ok", false }, { "needsTakeover", true }, { "id", id }, { "title", r["title"] }, { "error", "\"" + r["title"] + "\" was made by another app (Streamer.bot / Songify), so the Host cannot refund or complete its redemptions. Use \"Take over\" to make the Host's own copy." } };
            string act = (string)b["automation"] ?? "spotify-redeem";
            bool sw = Auto.SetRedeemReward(act, (string)r["title"], id); try { ChannelControl.Audit("app", "rewards/use", "automation=" + act + " id=" + id); } catch (Exception) { }
            return new JObject { { "ok", sw }, { "id", id }, { "title", r["title"] }, { "automation", act }, { "automationSwitched", sw }, { "owned", true }, { "message", sw ? "\"" + r["title"] + "\" now starts " + act : "automation " + act + " has no channel point trigger" } };
        }

        /// <summary>{rewardId, automation}: the Host makes its own copy of a reward another app owns (same title/cost/prompt/colour/cooldowns/limits), renames+disables the old one as "title (old)" when Twitch lets it (it normally does not: only the owning app may edit),
        /// and points the automation at the copy. One try each, never retried. If the old one cannot be renamed the copy is titled "title (Host)" (Twitch forbids two rewards with one title) and the result says to turn the old one off in the Twitch dashboard.</summary>
        public static JObject Takeover(JObject b)
        {
            string id = ((string)b["rewardId"] ?? "").Trim(); if (id == "") return Err("rewardId required");
            JObject all, mine; string e1, e2;
            string c1 = TwitchApi.CallFull(HttpMethod.Get, "/channel_points/custom_rewards?broadcaster_id={bid}", out all, out e1);
            if (!c1.StartsWith("2")) return ListErr(new JObject { { "ok", false }, { "error", "HTTP " + c1 + " " + e1 } });
            TwitchApi.CallFull(HttpMethod.Get, "/channel_points/custom_rewards?broadcaster_id={bid}&only_manageable_rewards=true", out mine, out e2);
            var rows = ((all["data"] as JArray) ?? new JArray()).OfType<JObject>().ToList(); var old = rows.FirstOrDefault(x => (string)x["id"] == id);
            if (old == null) return Err("no reward with that id on this channel");
            var ours = new HashSet<string>(((mine?["data"] as JArray) ?? new JArray()).Select(x => (string)x["id"]));
            string act = (string)b["automation"] ?? "spotify-redeem", title = (string)old["title"];
            if (ours.Contains(id)) { var u = Use(b); u["already"] = true; return u; }
            var res = new JObject { { "ok", true }, { "oldId", id }, { "oldTitle", title }, { "automation", act } };
            // 1) try to move the old one out of the way (only the owning app may; one attempt, never retried)
            string oldTitle = title + " (old)"; for (int n = 2; rows.Any(x => string.Equals((string)x["title"], oldTitle, StringComparison.OrdinalIgnoreCase)); n++) oldTitle = title + " (old " + n + ")";
            JToken dd; string er; string pc = TwitchApi.Call(new HttpMethod("PATCH"), "/channel_points/custom_rewards?broadcaster_id={bid}&id=" + Uri.EscapeDataString(id), new JObject { { "title", oldTitle }, { "is_enabled", false } }, out dd, out er);
            bool moved = pc.StartsWith("2");
            if (!moved && ScopeRefusal(pc, er)) return new JObject { { "ok", false }, { "needsScope", true }, { "error", ScopeMsg } };
            res["oldRenamed"] = moved; if (moved) res["oldNewTitle"] = oldTitle; else lock (L) _foreign.Add(id);
            // 2) the copy
            string newTitle = moved ? title : title + " (Host)"; if (!moved) for (int n = 2; rows.Any(x => string.Equals((string)x["title"], newTitle, StringComparison.OrdinalIgnoreCase)); n++) newTitle = title + " (Host " + n + ")";
            var body = new JObject { { "title", newTitle }, { "cost", old["cost"] }, { "prompt", old["prompt"] ?? "" }, { "is_user_input_required", old["is_user_input_required"] ?? false }, { "is_enabled", true } };
            if (old["background_color"] != null && (string)old["background_color"] != "") body["background_color"] = old["background_color"];
            if (old["should_redemptions_skip_request_queue"] != null) body["should_redemptions_skip_request_queue"] = old["should_redemptions_skip_request_queue"];
            var ms = old["max_per_stream_setting"] as JObject; if (ms != null && (bool?)ms["is_enabled"] == true) { body["is_max_per_stream_enabled"] = true; body["max_per_stream"] = ms["max_per_stream"]; }
            var mu = old["max_per_user_per_stream_setting"] as JObject; if (mu != null && (bool?)mu["is_enabled"] == true) { body["is_max_per_user_per_stream_enabled"] = true; body["max_per_user_per_stream"] = mu["max_per_user_per_stream"]; }
            var gc = old["global_cooldown_setting"] as JObject; if (gc != null && (bool?)gc["is_enabled"] == true) { body["is_global_cooldown_enabled"] = true; body["global_cooldown_seconds"] = gc["global_cooldown_seconds"]; }
            JToken d; string err; string code = TwitchApi.Call(HttpMethod.Post, "/channel_points/custom_rewards?broadcaster_id={bid}", body, out d, out err);
            if (!code.StartsWith("2") || !(d is JArray a) || a.Count == 0)
            {
                if (ScopeRefusal(code, err)) return new JObject { { "ok", false }, { "needsScope", true }, { "oldRenamed", moved }, { "error", ScopeMsg } };
                return new JObject { { "ok", false }, { "oldRenamed", moved }, { "error", "Twitch refused the copy (HTTP " + code + "): " + err + (moved ? " The old reward was already renamed to \"" + oldTitle + "\" and disabled; re-enable or rename it in the Twitch dashboard if you want it back." : "") } };
            }
            string nid = (string)a[0]["id"]; lock (L) _foreign.Remove(nid);
            Clog.Info("rewards", "took over \"" + title + "\": the Host's own copy is \"" + newTitle + "\" (" + nid + "), old " + id + (moved ? " renamed+disabled" : " left as it was (only its owner app may edit it)"));
            try { ChannelControl.Audit("app", "rewards/takeover", "old=" + id + " new=" + nid + " renamed=" + moved); } catch (Exception) { }
            bool sw = act != "" && Auto.SetRedeemReward(act, newTitle, nid);
            res["id"] = nid; res["title"] = newTitle; res["created"] = true; res["automationSwitched"] = sw;
            res["message"] = moved ? "The Host now owns \"" + newTitle + "\"; the old reward is renamed \"" + oldTitle + "\" and disabled."
                : "The Host now owns \"" + newTitle + "\" and " + act + " uses it. Twitch only lets the app that made the old reward edit it, so turn the old \"" + title + "\" off in the Twitch dashboard (Creator Dashboard > Viewer Rewards > Channel Points) and, if you like, rename the new one to \"" + title + "\".";
            if (!moved) res["manualStep"] = "turn the old one off in the Twitch dashboard";
            return res;
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
