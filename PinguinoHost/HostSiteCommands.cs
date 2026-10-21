using System;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Pushes the UNFILTERED command list (same objects as GET /api/commands/all) to the site: POST /api/bot/commands-all {commands:[...]} with the bot key.
    /// The site shows it staff-only; the public page only gets enabled everyone-commands. Checks every 10 s, pushes when anything but the usage counts changed, and every 60 s so the counts stay fresh.</summary>
    public static class SiteCommands
    {
        static bool _started; static string _result = "not started", _key = ""; static DateTime _last = DateTime.MinValue; static int _fails, _lastCode;
        public static string Status() { return _result; }
        public static void Start()
        {
            if (_started) return; _started = true;
            Task.Run(async () => { await Task.Delay(6000); while (true) { try { Tick(); } catch (Exception ex) { _result = "error: " + ex.Message; } await Task.Delay(10000); } });
        }
        public static void Tick()
        {
            string k = SiteHttp.Key(); if (k == "") { _result = "no site key"; return; }
            var all = CmdProfiles.All(); var arr = (JArray)all["commands"];
            var shape = new JArray(); foreach (JObject c in arr) { var o = (JObject)c.DeepClone(); o.Remove("createdBy"); o.Remove("editedBy"); o.Remove("createdAt"); o.Remove("editedAt"); shape.Add(o); }
            var stable = (JArray)shape.DeepClone(); foreach (JObject c in stable) { c.Remove("uses"); c.Remove("lastUsed"); }
            string key = Convert.ToBase64String(SHA1.Create().ComputeHash(Encoding.UTF8.GetBytes(stable.ToString(Newtonsoft.Json.Formatting.None))));
            if (key == _key && (DateTime.UtcNow - _last).TotalSeconds < 60) return;
            JObject r; int code = SiteHttp.Call("POST", "/api/bot/commands-all", new JObject { { "commands", shape } }, k, out r);
            _last = DateTime.UtcNow;
            if (code >= 200 && code < 300) { _fails = 0; _key = key; _result = "pushed " + shape.Count; }
            else { _fails++; _result = "site answered " + code; if (_fails == 1 || code != _lastCode || _fails % 20 == 0) Clog.Warn("commands", "command list push failed (HTTP " + code + ")"); }
            _lastCode = code;
        }
    }
}
