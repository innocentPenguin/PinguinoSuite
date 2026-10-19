using System;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Only ONE Host may run the bots (several PCs can have the Suite). The Suite core decides which device is master (Docs\MODULE_CONTRACT.md,
    /// "Devices: master / auxiliary"); Host is a singleton module: it asks GET /api/device/lease every 10 s, does nothing until it has seen is_master:true, and
    /// shuts down cleanly (chat and EventSub disconnected first) when that turns false or the core stays unreachable for 60 s. Standalone runs (no core token) are not gated.
    /// A per-data-folder mutex also keeps two Hosts off one PC.</summary>
    public static class Lease
    {
        public static readonly string MachineId = Environment.GetEnvironmentVariable("PINGUINO_MACHINE_ID") ?? Environment.MachineName;
        static readonly string Base = (Environment.GetEnvironmentVariable("PINGUINO_LEASE_URL") ?? Environment.GetEnvironmentVariable("PINGUINO_CORE_URL") ?? "http://127.0.0.1:8760").TrimEnd('/');
        static readonly string ApiToken = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? "";
        /// <summary>gated only when the core launched us (module token present) or a lease URL was given explicitly.</summary>
        public static readonly bool Enabled = ApiToken != "" || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("PINGUINO_LEASE_URL"));
        static readonly int PollSec = int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_LEASE_POLL"), out int p) && p >= 1 ? p : 10;
        static readonly int GraceSec = int.TryParse(Environment.GetEnvironmentVariable("PINGUINO_LEASE_GRACE"), out int g) && g >= 2 ? g : 60;
        static volatile string _state = "none"; static string _masterName = "", _error = ""; static DateTime _lastOk = DateTime.MinValue; static int _falses;
        static CancellationTokenSource _cts = new CancellationTokenSource(); static readonly object _l = new object();
        static Mutex _mutex; static readonly HttpClient Http = new HttpClient { Timeout = TimeSpan.FromSeconds(4) };

        /// <summary>true when this process may talk to Twitch chat, EventSub, OBS and run the bots.</summary>
        public static bool MayRun { get { return !Enabled || _state == "master"; } }
        /// <summary>cancelled when the master role is lost; connection loops pass it to their socket calls.</summary>
        public static CancellationToken Token { get { lock (_l) return _cts.Token; } }

        public static JObject State()
        {
            return new JObject { { "state", Enabled ? _state : "none" }, { "mayRun", MayRun }, { "machine", MachineId }, { "masterName", _masterName }, { "error", _error }, { "gated", Enabled } };
        }

        /// <summary>One Host per data folder per PC: wait up to 12 s for a previous instance (a restart in progress) to let go.</summary>
        public static bool TakeMutex(string dataDir)
        {
            try
            {
                string h = Math.Abs(System.IO.Path.GetFullPath(dataDir ?? "").ToLowerInvariant().GetHashCode()).ToString();
                _mutex = new Mutex(false, @"Global\PinguinoHost-" + h);
                try { return _mutex.WaitOne(12000); } catch (AbandonedMutexException) { return true; }
            }
            catch (Exception) { return true; }   // a platform without named mutexes: do not block
        }

        public static void Start()
        {
            if (!Enabled) return;
            _state = "waiting"; Clog.Info("lease", "waiting to be told this device is the master (" + Base + ")");
            Task.Run(async () => { while (true) { try { await Poll(); } catch (Exception ex) { _error = ex.Message; } await Task.Delay(PollSec * 1000); } });
        }

        static async Task Poll()
        {
            try
            {
                var rq = new HttpRequestMessage(HttpMethod.Get, Base + "/api/device/lease"); if (ApiToken != "") rq.Headers.Add("Authorization", "Bearer " + ApiToken);
                var r = await Http.SendAsync(rq);
                if ((int)r.StatusCode == 404) { _falses = 0; Became("single device (this core has no device lease yet)"); return; }   // an older core: one device, we are the master
                string txt = await r.Content.ReadAsStringAsync();
                if (!r.IsSuccessStatusCode) throw new Exception("lease check answered HTTP " + (int)r.StatusCode);
                var j = JObject.Parse(txt); _lastOk = DateTime.UtcNow; _error = ""; _masterName = (string)j["master_name"] ?? "";
                if ((bool?)j["is_master"] == true) { _falses = 0; Became("this device is the master"); return; }
                _falses++;
                if (_state == "master" || _falses >= 2) Stop("this device is not the master (master: " + (_masterName == "" ? "another device" : _masterName) + ")");
                else _state = "waiting";
            }
            catch (Exception ex)
            {
                _error = "lease check failed: " + ex.Message;
                if (_state == "master" && (DateTime.UtcNow - _lastOk).TotalSeconds > GraceSec) Stop("the core has been unreachable for " + GraceSec + " s");
            }
        }

        static void Became(string why)
        {
            _lastOk = DateTime.UtcNow; if (_state == "master") return;
            lock (_l) { if (_cts.IsCancellationRequested) _cts = new CancellationTokenSource(); }
            _state = "master"; Clog.Info("lease", why + ": starting chat, EventSub and bots");
        }

        // disconnect first (cancel the sockets), give them a moment, release the PC lock, then exit so the core can start us again on promotion
        static void Stop(string why)
        {
            _state = "waiting"; lock (_l) _cts.Cancel();
            Clog.Warn("lease", why + ": disconnecting and shutting down");
            Task.Run(async () => { await Task.Delay(1500); try { _mutex?.ReleaseMutex(); } catch (Exception) { } Environment.Exit(0); });
        }

        /// <summary>tells the core while OBS is streaming here, so a device that really is live can win the master role.</summary>
        public static void StartStreamingReporter(Func<bool?> streaming)
        {
            if (!Enabled) return;
            Task.Run(async () =>
            {
                bool? last = null; DateTime lastPost = DateTime.MinValue;
                while (true)
                {
                    await Task.Delay(Math.Max(1, Math.Min(15, PollSec)) * 1000);
                    try
                    {
                        bool? on = streaming(); if (on == null) continue;
                        if (on != last || (on == true && (DateTime.UtcNow - lastPost).TotalSeconds > 60))
                        {
                            var rq = new HttpRequestMessage(HttpMethod.Post, Base + "/api/device/streaming") { Content = new StringContent(new JObject { { "on", on } }.ToString(), Encoding.UTF8, "application/json") };
                            if (ApiToken != "") rq.Headers.Add("Authorization", "Bearer " + ApiToken);
                            var r = await Http.SendAsync(rq);
                            if (r.IsSuccessStatusCode || (int)r.StatusCode == 404) { if (on != last) Clog.Info("lease", "reported streaming=" + on.ToString().ToLowerInvariant() + " to the core"); last = on; lastPost = DateTime.UtcNow; }
                        }
                    }
                    catch (Exception) { }
                }
            });
        }
    }
}
