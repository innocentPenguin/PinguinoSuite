using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Reads the Host's secrets from the Suite key vault (GET {core}/api/vault/NAME with the module token; Docs\MODULE_CONTRACT.md "Key vault").
    /// The plaintext files stay as the fallback and WIN when they hold a value (a fresh sign-in writes the newest token there); once Ivan removes the plaintext the vault value is used.
    /// Values live in memory only: never logged, never written to a file, never put in a URL. The bots (which also run inside Streamer.bot) get theirs through
    /// non-persisted global variables named pinguino.secret.*.</summary>
    public static class Vault
    {
        /// <summary>declared in the module manifest ("secrets") by 01.</summary>
        public static readonly string[] Names = { "CHAT_BOT_API_KEY", "HOST_SECRETS.UserToken", "HOST_SECRETS.ObsPassword", "BOTS_SECRETS.core.UserToken", "BOTS_SECRETS.chat.UserToken", "BOTS_SECRETS.helper.UserToken" };
        static readonly string Core = (Environment.GetEnvironmentVariable("PINGUINO_CORE_URL") ?? "http://127.0.0.1:8760").TrimEnd('/');
        static readonly string Token = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? "";
        public static bool Enabled { get { return Token != ""; } }
        static readonly Dictionary<string, string> _v = new Dictionary<string, string>(); static readonly object _l = new object();
        static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(4) };
        public static string Reach = "not checked"; public static DateTime At = DateTime.MinValue; public static List<string> Missing = new List<string>();

        public static string Get(string name) { lock (_l) { string v; return _v.TryGetValue(name, out v) ? v : ""; } }

        /// <summary>fetch every declared key (a 404 = not set yet, 403/409/503 and network errors = keep what we have).</summary>
        public static void Refresh()
        {
            if (!Enabled) { Reach = "no module token (standalone run)"; return; }
            var missing = new List<string>(); string reach = "ok";
            foreach (string n in Names)
            {
                try
                {
                    var rq = new HttpRequestMessage(HttpMethod.Get, Core + "/api/vault/" + Uri.EscapeDataString(n)); rq.Headers.Add("Authorization", "Bearer " + Token);
                    var r = Http.SendAsync(rq).Result; int code = (int)r.StatusCode;
                    if (code == 200) { var j = JObject.Parse(r.Content.ReadAsStringAsync().Result); string v = (string)j["value"] ?? ""; lock (_l) { if (v != "") _v[n] = v; else _v.Remove(n); } }
                    else if (code == 404) { lock (_l) _v.Remove(n); missing.Add(n); }
                    else if (code == 409) { reach = "this device is not the master (no vault here)"; break; }
                    else if (code == 403) { reach = "the manifest does not declare this key yet (HTTP 403)"; break; }
                    else if (code == 503) { reach = "no key store on this OS"; break; }
                    else { reach = "vault answered HTTP " + code; break; }
                }
                catch (Exception ex) { reach = "core unreachable: " + ex.Message; break; }
            }
            Reach = reach; At = DateTime.UtcNow; Missing = missing;
        }
        public static void StartLoop(Action onRefresh)
        {
            Task.Run(async () => { while (true) { try { Refresh(); onRefresh?.Invoke(); } catch (Exception) { } await Task.Delay(TimeSpan.FromMinutes(10)); } });
        }

        /// <summary>best effort: a fresh sign-in tells the vault the new token (needs the module to be allowed to set its own declared keys; a refusal is ignored).</summary>
        public static void TrySet(string name, string value)
        {
            if (!Enabled || string.IsNullOrEmpty(value)) return;
            try
            {
                var rq = new HttpRequestMessage(HttpMethod.Post, Core + "/api/vault/" + Uri.EscapeDataString(name) + "/set") { Content = new StringContent(new JObject { { "value", value } }.ToString(), Encoding.UTF8, "application/json") };
                rq.Headers.Add("Authorization", "Bearer " + Token);
                var r = Http.SendAsync(rq).Result; if (r.IsSuccessStatusCode) lock (_l) _v[name] = value;
            }
            catch (Exception) { }
        }

        /// <summary>what the in-process bots read (CPH global variables, memory only): the AI key and each bot account's token, when their own files do not hold them.</summary>
        public static void PushToBots(HostCPH cph)
        {
            if (cph == null) return;
            cph.SetGlobalVar("pinguino.secret.aikey", Get("CHAT_BOT_API_KEY"), false);
            foreach (string role in new[] { "core", "chat", "helper" }) cph.SetGlobalVar("pinguino.secret.token." + role, Get("BOTS_SECRETS." + role + ".UserToken"), false);
        }
    }
}
