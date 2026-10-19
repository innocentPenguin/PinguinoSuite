using System;
using System.Collections.Generic;
public class CPHStubBase { public CPHProxy CPH = new CPHProxy(); }
public class CPHProxy
{
    public static List<string> Sent = new List<string>();
    public static List<Dictionary<string, object>> Runs = new List<Dictionary<string, object>>();   // every RunAction: name + a copy of the arguments at that moment
    public static Dictionary<string, object> Args = new Dictionary<string, object>();
    public void SendMessage(string m, bool useBot = true) { Sent.Add(m); }
    public bool RunAction(string name, bool runImmediately = true)
    {
        var snap = new Dictionary<string, object>(Args); snap["_action"] = name; Runs.Add(snap); return true;
    }
    public void SetArgument(string k, object v) { Args[k] = v; }
    public void LogInfo(string m) { Console.WriteLine("INFO " + m); }
    public void LogWarn(string m) { Console.WriteLine("WARN " + m); }
    public void LogError(string m) { Console.WriteLine("ERR " + m); }
    public bool TryGetArg<T>(string k, out T v) { object o; if (Args.TryGetValue(k, out o) && o is T) { v = (T)o; return true; } v = default(T); return false; }

  public static System.Collections.Generic.Dictionary<string,object> Globals = new System.Collections.Generic.Dictionary<string,object>();
  public bool SetGlobalVar(string name, object value, bool persisted = true){ Globals[name] = value; return true; }
  public bool UnsetGlobalVar(string name, bool persisted = true){ return Globals.Remove(name); }
  public T GetGlobalVar<T>(string name, bool persisted = true){ object o; return Globals.TryGetValue(name, out o) && o is T ? (T)o : default(T); }
    public static HashSet<string> Missing = new HashSet<string>();   // actions that do not exist in Streamer.bot
    public bool ActionExists(string name) { return !Missing.Contains(name); }
}
