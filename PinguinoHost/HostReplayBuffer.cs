using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Keeps the OBS replay buffer running. Only ever STARTS it (StartReplayBuffer, and only after GetReplayBufferStatus says it is not active) - never toggles.
    /// Triggers: OBS (re)connects / Host boots with OBS up, stream started, recording started. Setting autoStartReplayBuffer (config/obs_replaybuffer.json, default ON).</summary>
    public static class ReplayBuf
    {
        static readonly object L = new object();
        static bool _loaded, _auto = true, _running, _active, _enabled = true; static long _lastAuto; static string _lastError = "", _loggedErr = "";
        static string P { get { return Path.Combine(HostApi.DataDir, "config", "obs_replaybuffer.json"); } }
        static void Load()
        {
            if (_loaded) return; _loaded = true;
            try { if (File.Exists(P)) _auto = (bool?)JObject.Parse(File.ReadAllText(P).TrimStart((char)0xFEFF))["autoStartReplayBuffer"] != false; } catch (Exception) { }
        }
        public static bool AutoStart { get { lock (L) { Load(); return _auto; } } }
        public static void SetAutoStart(bool on)
        {
            lock (L) { Load(); _auto = on; try { Directory.CreateDirectory(Path.GetDirectoryName(P)); File.WriteAllText(P, new JObject { { "autoStartReplayBuffer", on } }.ToString(), new UTF8Encoding(false)); } catch (Exception) { } }
        }
        public static void OnState(bool active) { lock (L) { _active = active; if (active) { _enabled = true; _lastError = ""; } } }
        public static void OnDisconnect() { lock (L) { _active = false; } }
        public static JObject Status()
        {
            lock (L) { Load(); return new JObject { { "active", _active }, { "lastAutoStart", _lastAuto }, { "lastError", _lastError } }; }
        }
        public static bool Enabled { get { lock (L) return _enabled; } }

        /// <summary>start the replay buffer if it is not running (idempotent, off the caller's thread, a few retries with backoff)</summary>
        public static void Ensure(ObsClient o, string reason)
        {
            lock (L) { Load(); if (!_auto || _running) return; _running = true; }
            Task.Run(() =>
            {
                try
                {
                    int[] wait = { 0, 1500, 3000, 6000 }; string err = "";
                    for (int i = 0; i < wait.Length; i++)
                    {
                        if (wait[i] > 0) Thread.Sleep(wait[i]);
                        if (!o.Connected) { err = "OBS not connected"; break; }
                        var st = o.Raw("GetReplayBufferStatus", null);
                        if (st == null) { err = "no answer from OBS"; continue; }
                        if (!(bool)st["requestStatus"]["result"]) { err = Comment(st, "GetReplayBufferStatus failed"); lock (L) _enabled = false; continue; }
                        lock (L) _enabled = true;
                        if ((bool?)(st["responseData"] as JObject)?["outputActive"] == true) { lock (L) { _active = true; _lastError = ""; } return; }
                        var r = o.Raw("StartReplayBuffer", null);
                        if (r != null && (bool)r["requestStatus"]["result"])
                        {
                            lock (L) { _active = true; _enabled = true; _lastError = ""; _lastAuto = DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
                            Clog.Info("obs", "replay buffer auto-started (" + reason + ")"); return;
                        }
                        err = r == null ? "no answer from OBS" : Comment(r, "StartReplayBuffer refused");
                    }
                    lock (L) { _lastError = err; _active = false; }
                    bool first; lock (L) { first = _loggedErr != err; _loggedErr = err; }
                    if (first) Clog.Warn("obs", "replay buffer not started (" + reason + "): " + err + " - is it enabled in OBS settings > Output > Replay Buffer?");
                }
                catch (Exception ex) { lock (L) _lastError = ex.Message; }
                finally { lock (L) _running = false; }
            });
        }
        static string Comment(JObject r, string dflt) { var s = r["requestStatus"] as JObject; string c = s == null ? null : (string)s["comment"]; return string.IsNullOrEmpty(c) ? dflt : c; }
    }
}
