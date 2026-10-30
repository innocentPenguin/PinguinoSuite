using System;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Pushes the ranked history (RankedActivity.PushPayload: last 30 days with their games, breaks and times, 12 weeks, 12 months, the live break and settings) to the site:
    /// POST /api/bot/ranked with the bot key, replace-all. Polls every PINGUINO_RANKED_POLL_SEC (default 10) and pushes when the payload changed (generatedAt ignored), at most once a minute.
    /// Data\runtime\ranked_push.json keeps only the hash of the last accepted push. Same failure backoff as the lobby push; the site endpoint may not be live yet.</summary>
    public static class RankedPush
    {
        static bool _started; static string _result = "not started"; static int _fails, _lastCode; static DateTime _lastPush = DateTime.MinValue;
        static string P { get { return System.IO.Path.Combine(HostApi.DataDir, "ranked_push.json"); } }
        public static string Status() { return _result; }
        public static void Start()
        {
            if (_started || HostApi.SimMode) return; _started = true;
            int sec; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_RANKED_POLL_SEC"), out sec) || sec < 1) sec = 10;
            Task.Run(async () => { await Task.Delay(5000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(Math.Min(300, sec * (1 + Math.Min(_fails, 6) * 4)) * 1000); } });
        }
        /// <summary>the hash that says "changed": the payload without its timestamp</summary>
        public static string Key(JObject payload)
        {
            var c = (JObject)payload.DeepClone(); c.Remove("generatedAt");
            return Convert.ToBase64String(SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(c.ToString(Newtonsoft.Json.Formatting.None))));
        }
        public static void Tick()
        {
            var payload = RankedActivity.PushPayload(); string key = Key(payload);
            if ((string)SiteHttp.ReadJ(P)["key"] == key) { _result = "up to date"; return; }
            if ((DateTime.UtcNow - _lastPush).TotalSeconds < 60) { _result = "changed, waiting (once a minute)"; return; }
            string k = SiteHttp.Key(); if (k == "") { _result = "no site key"; return; }
            _lastPush = DateTime.UtcNow; JObject r; int code = SiteHttp.Call("POST", "/api/bot/ranked", payload, k, out r);
            if (code >= 200 && code < 300) { _fails = 0; SiteHttp.WriteJ(P, new JObject { { "key", key }, { "pushedAt", DateTime.UtcNow.ToString("o") } }); _result = "pushed"; Clog.Info("ranked", "ranked history pushed to the site"); }
            else { _fails++; _result = "site answered " + code; if (_fails == 1 || code != _lastCode || _fails % 20 == 0) Clog.Warn("ranked", "ranked push failed (HTTP " + code + ")" + (_fails > 1 ? ", " + _fails + " tries in a row (the site endpoint may not be live yet)" : "")); _lastCode = code; }
        }
    }
}
