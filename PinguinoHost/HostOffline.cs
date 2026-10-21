using System;
using System.IO;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>ONE "Offline mode" switch for the whole bot family. ON: Host timers, chimes, intros, economy and the bots (Helper, Chatty, B0t chat) behave as if the stream were live, so they chat and answer while offline.
    /// OFF (default): the normal online-only rules. The real live state is never faked: strikes, stream-start resets and !uptime still follow Twitch. Persisted in Data\config\offline_mode.json {enabled}; published to the bots as the
    /// non-persisted global pinguino.offlinemode ("1"/"0"); GET/POST /api/offline-mode; shown in GET /api/live-state; mods and the streamer can say !offlinemode on|off|status. Safety rules (duplicate guard, opt-outs, cooldowns, raids) are untouched.</summary>
    public static class OfflineMode
    {
        static bool _on, _loaded, _actRec = true; static HostCPH _cph; static readonly object L = new object();
        static string P { get { return Path.Combine(HostApi.DataDir, "config", "offline_mode.json"); } }
        public static bool Enabled { get { lock (L) { Load(); return _on; } } }
        static void Load()
        {
            if (_loaded) return; _loaded = true;
            try { if (File.Exists(P)) { var j = JObject.Parse(File.ReadAllText(P).TrimStart((char)0xFEFF)); _on = (bool?)j["enabled"] == true; _actRec = (bool?)j["actLiveWhileRecording"] != false; } } catch (Exception) { }
        }
        /// <summary>"Act live while recording" (default ON): an OBS recording makes the bots behave as if the stream were live.</summary>
        public static bool ActLiveWhileRecording { get { lock (L) { Load(); return _actRec; } } }
        static void SaveFile() { Directory.CreateDirectory(Path.GetDirectoryName(P)); File.WriteAllText(P, new JObject { { "note", "Offline mode: ON makes the bots (Helper, Chatty, B0t) and the Host timers/intros/economy act as if the stream were live. Default off. actLiveWhileRecording (default true): an OBS recording counts as live too." }, { "enabled", _on }, { "actLiveWhileRecording", _actRec } }.ToString()); }
        public static JObject SetActLiveWhileRecording(bool on, string who)
        {
            lock (L) { Load(); bool was = _actRec; _actRec = on; try { SaveFile(); } catch (Exception ex) { _actRec = was; return new JObject { { "ok", false }, { "error", "could not save: " + ex.Message } }; } }
            Publish(); ChannelControl.Audit(who ?? "api", "act-live-while-recording", on ? "on" : "off"); Clog.Info("offline", "act live while recording " + (on ? "ON" : "OFF") + " by " + who);
            return Api();
        }
        public static void Attach(HostCPH c) { _cph = c; Publish(); }
        public static void Publish() { try { if (_cph != null) _cph.SetGlobalVar("pinguino.offlinemode", LiveState.BotsActLive ? "1" : "0", false); } catch (Exception) { } }
        public static JObject Set(bool on, string who)
        {
            lock (L)
            {
                Load(); bool was = _on; _on = on;
                try { SaveFile(); }
                catch (Exception ex) { _on = was; return new JObject { { "ok", false }, { "error", "could not save: " + ex.Message } }; }
            }
            Publish(); ChannelControl.Audit(who ?? "api", "offline-mode", on ? "on" : "off"); Clog.Info("offline", "offline mode " + (on ? "ON" : "OFF") + " by " + who);
            return Api();
        }
        public static JObject Api() { return new JObject { { "ok", true }, { "enabled", Enabled }, { "live", LiveState.Live }, { "behavesLive", LiveState.Active }, { "actLiveWhileRecording", ActLiveWhileRecording }, { "recording", LiveState.Recording }, { "source", LiveState.Source } }; }

        /// <summary>!offlinemode on|off|status — mods and the streamer only (others are ignored without a reply).</summary>
        public static void Handle(string user, string[] args, int role, Action<string> say)
        {
            if (role < 3) return;
            string w = args.Length > 0 ? args[0].ToLowerInvariant() : "status";
            if (w == "on" || w == "off") { var r = Set(w == "on", user); say((bool?)r["ok"] == true ? (w == "on" ? "Offline mode is ON: the bots act as if the stream were live." : "Offline mode is OFF: the bots follow the real stream status.") : "Could not change offline mode: " + (string)r["error"]); }
            else if (w == "status") say("Offline mode is " + (Enabled ? "ON" : "OFF") + ". Use !offlinemode on|off.");
            else say("Use: !offlinemode on|off|status");
        }
    }
}
