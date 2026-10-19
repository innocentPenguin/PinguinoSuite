using System;
public class CPHStubBase {
  public CPHProxy CPH = new CPHProxy();
}
public class CPHProxy {
  public static System.Collections.Generic.List<string> Sent = new System.Collections.Generic.List<string>();
  public static System.Collections.Generic.Dictionary<string,object> Args = new System.Collections.Generic.Dictionary<string,object>();
  public void SendMessage(string m, bool useBot = true){ Sent.Add(m); }
  public void SendAction(string m, bool bot = true){ Sent.Add("/me " + m); }
  public void TwitchAnnounce(string m, bool bot = false, string color = null, bool fallback = false){ Sent.Add("[announce " + color + "] " + m); }
  public void LogInfo(string m){ Console.WriteLine("INFO "+m); }
  public void LogWarn(string m){ Console.WriteLine("WARN "+m); }
  public void LogError(string m){ Console.WriteLine("ERR "+m); }
  public void LogVerbose(string m){}
  // OBS (what Streamer.bot provides); calls are recorded so the tests can check them.
  public static System.Collections.Generic.List<string> Obs = new System.Collections.Generic.List<string>();
  public static bool ObsConnected = true;
  public bool ObsIsConnected(int connection = 0){ return ObsConnected; }
  public bool ObsSetScene(string scene, int connection = 0){ Obs.Add("scene:"+scene); return ObsConnected; }
  public bool ObsShowSource(string scene, string source, int connection = 0){ Obs.Add("show:"+scene+"/"+source); return ObsConnected; }
  public bool ObsHideSource(string scene, string source, int connection = 0){ Obs.Add("hide:"+scene+"/"+source); return ObsConnected; }
  public static System.Collections.Generic.List<string> Games = new System.Collections.Generic.List<string>();
  public static bool GameOk = true;
  public bool SetChannelGame(string game){ Games.Add(game); return GameOk; }
  public bool TryGetArg<T>(string k, out T v){ object o; if(Args.TryGetValue(k,out o)){ v=(T)o; return true;} v=default(T); return false; }

  public static System.Collections.Generic.Dictionary<string,object> Globals = new System.Collections.Generic.Dictionary<string,object>();
  public bool SetGlobalVar(string name, object value, bool persisted = true){ Globals[name] = value; return true; }
  public bool UnsetGlobalVar(string name, bool persisted = true){ return Globals.Remove(name); }
  public T GetGlobalVar<T>(string name, bool persisted = true){ object o; return Globals.TryGetValue(name, out o) && o is T ? (T)o : default(T); }

  public void SetArgument(string k, object v){ Args[k] = v; }
}
