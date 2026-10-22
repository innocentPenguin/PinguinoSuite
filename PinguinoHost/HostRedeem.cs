using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Song-request refunds. Remembers recent module-routed channel point redemptions (user, redemption id, reward id) and cancels one
    /// (Helix Update Redemption Status = CANCELED, which gives the points back) when the module rejects it with refund:true, or later when the
    /// Spotify module reports a queued song skipped/removed (GET /api/refunds?since=seq). Twitch only lets the client_id that made a reward touch its redemptions.</summary>
    public static class Redeems
    {
        class Rec { public string User, Id, Reward, Song; public DateTime At; }
        static readonly List<Rec> _recent = new List<Rec>(); static readonly object L = new object();
        static bool _started; static long _lastSeq; static string _result = "not started";
        static string P { get { return Path.Combine(HostApi.DataDir, "refund_state.json"); } }
        public static string Status() { return _result; }

        public static void Record(string user, string redemptionId, string rewardId, string title)
        {
            if (string.IsNullOrEmpty(redemptionId) || string.IsNullOrEmpty(user)) return;
            lock (L) { _recent.Add(new Rec { User = user.ToLowerInvariant(), Id = redemptionId, Reward = rewardId ?? "", Song = title ?? "", At = DateTime.UtcNow }); if (_recent.Count > 200) _recent.RemoveAt(0); }
        }
        public static string Cancel(string redemptionId, string rewardId) { return SetStatus(redemptionId, rewardId, "CANCELED"); }
        /// <summary>marks the redemption fulfilled in Twitch's queue (auto-complete)</summary>
        public static string Fulfill(string redemptionId, string rewardId) { return SetStatus(redemptionId, rewardId, "FULFILLED"); }
        static string SetStatus(string redemptionId, string rewardId, string status)
        {
            if (string.IsNullOrEmpty(redemptionId) || string.IsNullOrEmpty(rewardId)) return "no redemption id";
            JToken d; string err;
            string code = TwitchApi.Call(new HttpMethod("PATCH"), "/channel_points/custom_rewards/redemptions?id=" + Uri.EscapeDataString(redemptionId) + "&broadcaster_id={bid}&reward_id=" + Uri.EscapeDataString(rewardId), new JObject { { "status", status } }, out d, out err);
            if (code.StartsWith("2")) { Clog.Info("refund", (status == "CANCELED" ? "refunded" : "completed") + " redemption " + redemptionId); try { EventLog.Backend("refund", "refunded a channel-point redemption", new JObject { { "redemption", redemptionId } }); } catch (Exception) { } return status == "CANCELED" ? "refunded" : "completed"; }
            string why = code == "401" || code == "403" ? " (the streamer account needs channel:manage:redemptions: sign in again on the Host setup page; Twitch also only lets the app that created a reward refund it)" : code == "404" ? " (already fulfilled, cancelled or older than Twitch keeps it)" : "";
            Clog.Warn("refund", "could not refund redemption (HTTP " + code + "): " + err + why);
            try { EventLog.Backend("refund", "could not refund a redemption: HTTP " + code + why, new JObject { { "redemption", redemptionId } }, "warn"); } catch (Exception) { }
            return "failed " + code + " " + err;
        }
        /// <summary>newest still-unrefunded redemption of that user, within the last 3 hours</summary>
        static Rec Take(string user)
        {
            user = (user ?? "").ToLowerInvariant();
            lock (L) { for (int i = _recent.Count - 1; i >= 0; i--) if (_recent[i].User == user && (DateTime.UtcNow - _recent[i].At).TotalHours < 3) { var r = _recent[i]; _recent.RemoveAt(i); return r; } }
            return null;
        }
        public static void Start()
        {
            if (_started) return; _started = true;
            var s = SiteHttp.ReadJ(P); _lastSeq = (long?)s["lastSeq"] ?? 0;
            int sec; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_REFUND_POLL_SEC"), out sec) || sec < 1) sec = 5;
            Task.Run(async () => { await Task.Delay(4000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(sec * 1000); } });
        }
        public static void Tick()
        {
            string baseUrl = Environment.GetEnvironmentVariable("PINGUINO_SPOTIFY_URL") ?? "http://127.0.0.1:8771";
            string txt;
            using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(4) })
            {
                string tok = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? "";
                var rq = new HttpRequestMessage(HttpMethod.Get, baseUrl + "/api/refunds?since=" + _lastSeq); if (tok != "") rq.Headers.Add("Authorization", "Bearer " + tok);
                var r = h.SendAsync(rq).Result; if (!r.IsSuccessStatusCode) { _result = "module answered " + (int)r.StatusCode; return; }
                txt = r.Content.ReadAsStringAsync().Result;
            }
            var j = JObject.Parse(txt); long top = _lastSeq; int n = 0;
            if (j["refunds"] is JArray a)
                foreach (var it in a)
                {
                    long seq = (long?)it["seq"] ?? 0; if (seq <= _lastSeq) continue;
                    var rec = Take((string)it["user"]);
                    if (rec != null) { Cancel(rec.Id, rec.Reward); n++; }
                    else Clog.Info("refund", "no recent redemption for " + (string)it["user"] + " (" + (string)it["why"] + ")");
                    if (seq > top) top = seq;
                }
            long modSeq = (long?)j["seq"] ?? 0; if (modSeq < _lastSeq) top = modSeq;   // module restarted and its counter reset
            if (top != _lastSeq) { _lastSeq = top; SiteHttp.WriteJ(P, new JObject { { "lastSeq", _lastSeq } }); }
            _result = "ok, seq " + _lastSeq + (n > 0 ? ", refunded " + n : "");
        }
    }
}
