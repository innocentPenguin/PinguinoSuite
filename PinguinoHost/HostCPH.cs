using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Reflection;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Base class the bot sources inherit from (the host rewrites "public class CPHInline" to derive from it). Gives them the CPH field Streamer.bot would inject.</summary>
    public class HostBase { public HostCPH CPH = HostCPH.Current; }

    /// <summary>The slice of Streamer.bot's CPH the four bots actually use, implemented against files, Twitch helix and the console.</summary>
    public partial class HostCPH
    {
        public static HostCPH Current;
        public Dictionary<string, object> Args = new Dictionary<string, object>();
        public readonly Dictionary<string, Func<HostCPH, bool>> Actions = new Dictionary<string, Func<HostCPH, bool>>(StringComparer.OrdinalIgnoreCase);
        public readonly List<string> Sent = new List<string>();           // everything the bots said (tests / sim)
        public Func<string, bool> Say;                                    // how a line reaches chat (helix or console)
        public Func<string, int, string, bool> Timeout;
        readonly Dictionary<string, object> _g = new Dictionary<string, object>();
        readonly string _persistPath;
        readonly object _lock = new object();
        public int Depth; public string CurAction;

        public HostCPH(string dataDir)
        {
            _persistPath = Path.Combine(dataDir, "host_globals.json");
            try { if (File.Exists(_persistPath)) foreach (var p in JObject.Parse(File.ReadAllText(_persistPath))) _g[p.Key] = p.Value.ToString(); } catch (Exception) { }
        }
        void Persist() { try { File.WriteAllText(_persistPath, new JObject(_g.Where(k => !k.Key.StartsWith("pinguino.result") && !k.Key.StartsWith("pinguino.secret.") && k.Value is string).Select(k => new JProperty(k.Key, k.Value))).ToString()); } catch (Exception) { } }

        // ---- chat ----
        public void SendMessage(string m, bool useBot = true) { Sent.Add(m); Console.WriteLine("[say] " + m); try { if (Say != null) Say(m); } catch (Exception e) { LogWarn("send failed: " + e.Message); } }
        public bool TwitchTimeoutUser(string user, int secs, string reason, bool useBot = false) { Console.WriteLine("[timeout] " + user + " " + secs + "s " + reason); try { return Timeout != null && Timeout(user, secs, reason); } catch (Exception) { return false; } }

        // ---- actions ----
        public bool ActionExists(string name) { return Actions.ContainsKey(name); }
        /// <summary>Runs another action the way Streamer.bot does: it inherits the current arguments, and later changes made by it stay visible to the caller.</summary>
        public bool RunAction(string name, bool runImmediately = true)
        {
            Func<HostCPH, bool> a;
            if (!Actions.TryGetValue(name, out a)) return false;
            if (Depth > 8) { LogWarn("RunAction depth limit at " + name); return false; }
            Depth++; string prev = CurAction; CurAction = name; HostApi.NoteRun(name);
            try { a(this); return true; } catch (Exception e) { HostApi.NoteLog(name, "ERROR", e.Message); throw; } finally { Depth--; CurAction = prev; }
        }

        // ---- arguments ----
        public void SetArgument(string k, object v) { Args[k] = v; }
        public bool TryGetArg<T>(string k, out T v)
        {
            object o;
            if (Args.TryGetValue(k, out o) && o != null)
            {
                try
                {
                    if (o is T) { v = (T)o; return true; }
                    var t = typeof(T);
                    if (t == typeof(string)) { v = (T)(object)Convert.ToString(o); return true; }
                    v = (T)Convert.ChangeType(o, Nullable.GetUnderlyingType(t) ?? t, System.Globalization.CultureInfo.InvariantCulture); return true;
                }
                catch (Exception) { }
            }
            v = default(T); return false;
        }

        // ---- global variables (persisted ones survive a restart) ----
        public bool SetGlobalVar(string name, object value, bool persisted = true) { lock (_lock) { _g[name] = value; if (persisted) Persist(); } return true; }
        public T GetGlobalVar<T>(string name, bool persisted = true)
        {
            lock (_lock)
            {
                object o;
                if (!_g.TryGetValue(name, out o) || o == null) return default(T);
                if (o is T) return (T)o;
                try { return (T)Convert.ChangeType(o, typeof(T), System.Globalization.CultureInfo.InvariantCulture); } catch (Exception) { return default(T); }
            }
        }
        public bool UnsetGlobalVar(string name, bool persisted = true) { lock (_lock) { bool r = _g.Remove(name); if (persisted) Persist(); return r; } }

        // ---- log ----
        public void LogInfo(string m) { Console.WriteLine("INFO  " + m); }
        public void LogVerbose(string m) { }
        public void LogWarn(string m) { HostApi.NoteLog(CurAction, "WARN", m); Clog.Warn("bot:" + (CurAction ?? "host"), m); Console.WriteLine("WARN  " + m); }
        public void LogError(string m) { HostApi.NoteLog(CurAction, "ERROR", m); Clog.Error("bot:" + (CurAction ?? "host"), m); Console.WriteLine("ERROR " + m); }
    }
}
