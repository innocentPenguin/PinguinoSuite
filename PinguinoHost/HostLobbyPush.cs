using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Pushes the private match (helper_settings.json LobbyName / LobbyPassword) to the site's private store: POST /api/bot/match-private {name,password,active}.
    /// Polls every PINGUINO_LOBBY_POLL_SEC (default 10) and once at start; pushes when LobbyUpdatedAt (or the name+password) changed since lobby_push.json. The password is never logged,
    /// and lobby_push.json keeps only a stamp and a hash. !pm still prints the answer in chat (Ivan's decision).</summary>
    public static class LobbyPush
    {
        static bool _started; static string _result = "not started"; static int _fails;
        static string P { get { return Path.Combine(HostApi.DataDir, "lobby_push.json"); } }
        public static string Status() { return _result; }
        public static void Start()
        {
            if (_started) return; _started = true;
            int sec; if (!int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_LOBBY_POLL_SEC"), out sec) || sec < 1) sec = 10;
            Task.Run(async () => { await Task.Delay(3000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(Math.Min(300, sec * (1 + Math.Min(_fails, 6) * 4)) * 1000); } });
        }
        public static void Tick()
        {
            string f = Path.Combine(HostApi.DataDir, "helper_settings.json"); if (!File.Exists(f)) { _result = "no helper_settings.json"; return; }
            var j = JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart((char)0xFEFF));
            string name = ((string)j["LobbyName"] ?? "").Trim(), pw = ((string)j["LobbyPassword"] ?? "").Trim();
            string h = Convert.ToBase64String(SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(name + "\n" + pw))), key = h;
            var last = SiteHttp.ReadJ(P); if ((string)last["key"] == key) { _result = "up to date"; return; }
            string k = SiteHttp.Key(); if (k == "") { _result = "no site key"; return; }
            var body = new JObject { { "name", name.Length > 60 ? name.Substring(0, 60) : name }, { "password", pw.Length > 60 ? pw.Substring(0, 60) : pw }, { "active", name != "" || pw != "" } };
            JObject r; int code = SiteHttp.Call("POST", "/api/bot/match-private", body, k, out r);
            if (code >= 200 && code < 300) { _fails = 0; SiteHttp.WriteJ(P, new JObject { { "key", key }, { "pushedAt", DateTime.UtcNow.ToString("o") } }); _result = "pushed"; Clog.Info("lobby", "private match pushed to the site"); }
            else { _fails++; _result = "site answered " + code; Clog.Warn("lobby", "private match push failed (HTTP " + code + ")"); }
        }
    }
}
