using System;
using System.Collections.Generic;
public class CPHStubBase { public CPHProxy CPH = new CPHProxy(); }
public class CPHProxy
{
    public static List<string> Sent = new List<string>();
    public static List<string> Runs = new List<string>();                         // action names in the order they were run
    public static Dictionary<string, object> Args = new Dictionary<string, object>();
    public static Dictionary<string, object> Globals = new Dictionary<string, object>();
    public static HashSet<string> Existing = new HashSet<string>();               // actions that "exist" in Streamer.bot
    public static Dictionary<string, Func<string>> Behaviors = new Dictionary<string, Func<string>>();   // what each module reports: handled / pass / defer ("" = nothing)
    public static List<string> Log = new List<string>();

    public void SendMessage(string m, bool useBot = true) { Sent.Add(m); }
    public bool ActionExists(string name) { return Existing.Contains(name); }
    public bool RunAction(string name, bool runImmediately = true)
    {
        Runs.Add(name + (Args.ContainsKey("pinguinoNoDefer") ? "*" : ""));
        Func<string> b;
        if (Behaviors.TryGetValue(name, out b)) { string r = b(); if (r != "") { object mid; Globals[Args.TryGetValue("pinguinoMsgId", out mid) ? "pinguino.result." + mid : "pinguino.result"] = r; } }
        return true;
    }
    public void SetArgument(string k, object v) { Args[k] = v; }
    public bool SetGlobalVar(string name, object value, bool persisted = true) { Globals[name] = value; return true; }
    public bool UnsetGlobalVar(string name, bool persisted = true) { return Globals.Remove(name); }
    public T GetGlobalVar<T>(string name, bool persisted = true) { object o; return Globals.TryGetValue(name, out o) && o is T ? (T)o : default(T); }
    public void LogInfo(string m) { Log.Add("INFO " + m); }
    public void LogWarn(string m) { Log.Add("WARN " + m); }
    public void LogError(string m) { Log.Add("ERR " + m); }
    public bool TryGetArg<T>(string k, out T v) { object o; if (Args.TryGetValue(k, out o) && o is T) { v = (T)o; return true; } v = default(T); return false; }
}
