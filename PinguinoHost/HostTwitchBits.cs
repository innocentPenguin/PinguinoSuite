using System;
using System.Linq;
using System.Net.Http;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>GET /api/boards/twitch-bits?period=all|day|week|month|year[&amp;count=100]: Twitch's own bits leaderboard (Helix /bits/leaderboard) with the streamer token that stays inside the Host.
    /// Read-only, answers {ok, period, rows:[{login, score}]} and never the token. Used to check our own bits ledger against what Twitch counts.</summary>
    public static class TwitchBits
    {
        public static JObject Get(string period, int count)
        {
            period = (period ?? "all").Trim().ToLowerInvariant(); if (period == "") period = "all";
            if (!new[] { "all", "day", "week", "month", "year" }.Contains(period)) return new JObject { { "ok", false }, { "error", "period must be all, day, week, month or year" } };
            count = Math.Max(1, Math.Min(100, count));
            var cr = HostApi.StreamerCreds(); string tok = (string)cr["UserToken"] ?? "", cid = (string)cr["ClientId"] ?? "";
            if (tok == "" || cid == "") return new JObject { { "ok", false }, { "error", "no streamer token configured" } };
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(15) })
                {
                    var rq = new HttpRequestMessage(HttpMethod.Get, HostApi.Helix + "/bits/leaderboard?period=" + period + "&count=" + count);
                    rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                    var resp = h.SendAsync(rq).Result;
                    if (!resp.IsSuccessStatusCode) return new JObject { { "ok", false }, { "error", "Twitch answered HTTP " + (int)resp.StatusCode } };
                    var data = JObject.Parse(resp.Content.ReadAsStringAsync().Result)["data"] as JArray ?? new JArray();
                    var rows = new JArray(data.OfType<JObject>().Select(u => new JObject { { "login", ((string)u["user_login"] ?? "").ToLowerInvariant() }, { "score", (long?)u["score"] ?? 0 } }));
                    return new JObject { { "ok", true }, { "period", period }, { "rows", rows } };
                }
            }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", "bits leaderboard failed: " + ex.GetType().Name } }; }
        }
    }
}
