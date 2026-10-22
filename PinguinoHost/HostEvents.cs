using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Recent chat lines for the Suite's Master View: GET /api/chat/recent?since=&lt;seq&gt;&amp;limit=50 and the "chat" SSE event. Memory only (last 200). Fed by Program.Dispatch.</summary>
    public static class ChatFeed
    {
        static readonly object L = new object(); static readonly List<JObject> _items = new List<JObject>(); static long _seq;
        public static void Add(string user, string text, int role, bool sub, int subTier)
        {
            if (string.IsNullOrEmpty(user) || text == null) return;
            var badges = new JArray(); if (role >= 4) badges.Add("broadcaster"); else if (role == 3) badges.Add("moderator"); else if (role == 2) badges.Add("vip"); if (sub || subTier > 0) badges.Add("subscriber");
            JObject o; lock (L) { o = new JObject { { "seq", ++_seq }, { "user", user.ToLowerInvariant() }, { "display", user }, { "text", text }, { "color", "" }, { "badges", badges }, { "ts", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() } }; _items.Add(o); if (_items.Count > 200) _items.RemoveAt(0); }
            Events.Publish("chat", o);
        }
        public static JArray Recent(long since, int limit) { lock (L) { limit = limit <= 0 ? 50 : Math.Min(limit, 200); var r = _items.Where(x => (long)x["seq"] > since).ToList(); if (r.Count > limit) r = r.Skip(r.Count - limit).ToList(); return new JArray(r.Select(x => x.DeepClone())); } }
        public static long Seq { get { lock (L) return _seq; } }
    }

    /// <summary>The customs queue as the Master View needs it (read from Core's live_state.json) + one mod-action endpoint that runs the chat command as the streamer and answers with the new state.</summary>
    public static class CustomsView
    {
        static readonly Dictionary<string, string> Actions = new Dictionary<string, string> { { "queue", "!queue" }, { "next", "!next" }, { "match", "!match" }, { "win", "!win" }, { "finish", "!finish" }, { "balance", "!balance" }, { "reroll", "!reroll" }, { "kick", "!kick" }, { "mode", "!mode" }, { "format", "!format" }, { "koth", "!koth" }, { "casual", "!casual" } };
        static string StateFile()
        {
            foreach (var f in new[] { Path.Combine(HostApi.DataDir, "live_state.json"), Path.Combine(HostApi.DataDir, "runtime", "live_state.json") }) if (File.Exists(f)) return f;
            return null;
        }
        public static JObject State()
        {
            JObject s = null; try { var f = StateFile(); if (f != null) s = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); } catch (Exception) { }
            if (s == null) return new JObject { { "ok", false }, { "open", false }, { "queue", new JArray() }, { "match", null } };
            var q = new JArray(); foreach (var e in (s["queue"] as JArray ?? new JArray()).OfType<JObject>())
            { var o = new JObject { { "username", (string)e["user"] ?? "" }, { "display", (string)e["epic"] ?? (string)e["user"] ?? "" }, { "mmr", e["mmr"] ?? 0 }, { "joinedAt", e["joinedAt"] ?? 0 } }; if ((bool?)e["practice"] == true) o["practice"] = true; if ((bool?)e["sim"] == true) o["sim"] = true; q.Add(o); }
            JObject match = null; var cm = s["liveMatch"] as JObject ?? s["currentMatch"] as JObject;
            if (cm != null)
            {
                Func<JToken, JArray> names = t => new JArray((t as JArray ?? new JArray()).OfType<JObject>().Select(x => (string)x["Username"] ?? (string)x["user"] ?? (string)x["username"] ?? "").Where(x => x != ""));
                var blue = names(cm["blue"]); var orange = names(cm["orange"]); var pl = new JArray();
                foreach (var n in blue) pl.Add(new JObject { { "username", n }, { "team", "blue" } }); foreach (var n in orange) pl.Add(new JObject { { "username", n }, { "team", "orange" } });
                match = new JObject { { "id", cm["id"] }, { "players", pl }, { "orange", orange }, { "blue", blue }, { "status", cm["status"] } };
            }
            return new JObject { { "ok", true }, { "open", (bool?)s["queueOpen"] ?? false }, { "activity", s["activity"] }, { "mode", s["mode"] }, { "gameMode", s["gameMode"] }, { "format", s["format"] }, { "koth", (bool?)s["koth"] ?? false }, { "casualStyle", s["casualStyle"] },
 { "teams", Teams(s) }, { "strikes", s["strikes"] ?? new JObject() }, { "strikeLimit", s["strikeLimit"] ?? 3 }, { "strikeGame", s["strikeGame"] ?? "rl" },                { "queue", q }, { "match", match }, { "controlHolder", s["controlHolder"] }, { "sim", (bool?)s["sim"] ?? false }, { "updatedAt", s["updatedAt"] } };
        }
        static readonly System.Text.RegularExpressions.Regex Hex = new System.Text.RegularExpressions.Regex("^#[0-9a-fA-F]{6}$");
        public static JObject Teams(JObject s)
        {
            Func<string, string, string, JObject> one = (k, dn, dc) => { var t = s == null ? null : s["teams"]?[k] as JObject; return new JObject { { "name", (string)t?["name"] ?? dn }, { "color", (string)t?["color"] ?? dc } }; };
            return new JObject { { "orange", one("orange", "Orange", "#ff7a00") }, { "blue", one("blue", "Blue", "#1e8fff") } };
        }
        public static string TeamName(string team)
        {
            try { var f = StateFile(); if (f != null) return (string)Teams(JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)))[team]["name"]; } catch (Exception) { }
            return team == "blue" ? "Blue" : "Orange";
        }
        /// <summary>POST /api/customs/teams {orange:{name?,color?}, blue:{name?,color?}} -> {ok, teams}. Validated here (name 1-20 chars, no leading ! or /, color #rrggbb), applied through !teamname.</summary>
        public static JObject SetTeams(JObject b)
        {
            var plan = new List<string>();
            foreach (var k in new[] { "orange", "blue" })
            {
                var t = b[k] as JObject; if (t == null) continue;
                string name = ((string)t["name"] ?? "").Trim(), color = ((string)t["color"] ?? "").Trim();
                if (color != "" && !Hex.IsMatch(color)) return new JObject { { "ok", false }, { "error", k + ".color must be #rrggbb" } };
                if (name != "" && (name.Length > 20 || name.StartsWith("!") || name.StartsWith("/") || name.Any(char.IsControl))) return new JObject { { "ok", false }, { "error", k + ".name must be 1-20 characters and cannot start with ! or /" } };
                if (name == "" && color == "") continue;
                plan.Add("!teamname " + k + " " + (color == "" ? "-" : color) + (name != "" ? " " + name : ""));
            }
            string who = "innocentpenguin_"; try { var ch = (string)HostApi.StreamerCreds()["Channel"]; if (!string.IsNullOrEmpty(ch)) who = ch; } catch (Exception) { }
            foreach (var text in plan) { try { Control.Synthetic = true; Program.Dispatch(who, text, null, 4, "deck", false, null); } finally { Control.Synthetic = false; } }
            Thread.Sleep(350); Events.Kick(); var st = State();
            return new JObject { { "ok", true }, { "ran", new JArray(plan) }, { "teams", st["teams"] } };
        }
        /// <summary>{action, value}: queue open|close|clear, next [blue|orange], match clear|fill|queue, win blue|orange, finish, balance, reroll, kick &lt;name&gt;, mode/format/koth/casual &lt;value&gt;.</summary>
        public static JObject Mod(JObject b)
        {
            string a = ((string)b["action"] ?? "").Trim().ToLowerInvariant(), v = ((string)b["value"] ?? "").Trim(); string cmd;
            if (!Actions.TryGetValue(a, out cmd)) return new JObject { { "ok", false }, { "error", "action must be one of " + string.Join("|", Actions.Keys) } };
            if (v.Length > 40 || v.Any(ch => !(char.IsLetterOrDigit(ch) || ch == '_' || ch == ' ' || ch == '.' || ch == ':' || ch == '-' || ch == '/'))) return new JObject { { "ok", false }, { "error", "value has characters that are not allowed" } };
            string who = "innocentpenguin_"; try { var ch = (string)HostApi.StreamerCreds()["Channel"]; if (!string.IsNullOrEmpty(ch)) who = ch; } catch (Exception) { }
            string text = cmd + (v != "" ? " " + v : "");
            try { Control.Synthetic = true; Program.Dispatch(who, text, null, 4, "deck", false, null); } finally { Control.Synthetic = false; }
            Thread.Sleep(350); Events.Kick();
            return new JObject { { "ok", true }, { "ran", text }, { "customs", State() } };
        }
    }

    /// <summary>GET /api/events: Server-Sent Events for the Suite's Master View. First message = snapshot (obs, obsstatus, live, customs, wheel, activity, last 50 chat lines); then only what changed.
    /// A 700 ms watcher compares each section with the last one sent (OBS scene / item / output events kick it at once), so nothing has to be wired into every code path.
    /// Same loopback + Origin rules as the other GETs (Access-Control-Allow-Origin is echoed by HostApi). Heartbeat comment every 15 s, "retry: 1000", ids = sequence numbers.</summary>
    public static class Events
    {
        static readonly object L = new object(); static readonly List<KeyValuePair<long, string>> _ring = new List<KeyValuePair<long, string>>(); static long _seq;
        static readonly Dictionary<string, string> _last = new Dictionary<string, string>(); static readonly ManualResetEventSlim _kick = new ManualResetEventSlim(false);
        static int _clients; static bool _started; static long _actSeq = -1;
        public static int Clients { get { return _clients; } }

        public static void Kick() { _kick.Set(); }
        public static void OnObsEvent(string type)
        {
            if (string.IsNullOrEmpty(type)) return;
            if (type.StartsWith("Scene") || type.StartsWith("CurrentProgramScene") || type.StartsWith("CurrentPreviewScene") || type.StartsWith("InputNameChanged") || type.EndsWith("StateChanged") || type == "CurrentSceneCollectionChanged") { ObsTree.Invalidate(); Kick(); }
        }

        public static void Publish(string type, JToken data)
        {
            lock (L) { _seq++; _ring.Add(new KeyValuePair<long, string>(_seq, Frame(_seq, type, data))); if (_ring.Count > 400) _ring.RemoveAt(0); Monitor.PulseAll(L); }
        }
        static string Frame(long id, string type, JToken data) { return "id: " + id + "\nevent: " + type + "\ndata: " + (data == null ? "null" : data.ToString(Newtonsoft.Json.Formatting.None)) + "\n\n"; }

        static JObject ObsStatus()
        {
            bool con = HostApi.ObsConnected(); var rb = ReplayBuf.Status();
            return new JObject { { "ok", true }, { "connected", con }, { "recording", LiveState.Recording }, { "autoStartReplayBuffer", ReplayBuf.AutoStart }, { "replayBufferEnabled", ReplayBuf.Enabled }, { "replayBuffer", rb } };
        }
        /// <summary>the mod view of the wheel: status, round, entrants and the settings; the seed and any pre-drawn teams are never included (the public overlay file shows only picks already made).</summary>
        public static JObject WheelState()
        {
            JObject pub = null, ses = null;
            foreach (var d in new[] { HostApi.DataDir, Path.Combine(HostApi.DataDir, "runtime") })
            {
                try { var f = Path.Combine(d, "wheel_public.json"); if (pub == null && File.Exists(f)) pub = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); } catch (Exception) { }
                try { var f = Path.Combine(d, "wheel_session.json"); if (ses == null && File.Exists(f)) ses = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); } catch (Exception) { }
            }
            pub = pub ?? new JObject { { "status", "none" } };
            var ent = new JArray((pub["queue"] as JArray ?? new JArray()).Select(x => x.Type == JTokenType.String ? x : (x["name"] ?? x)));
            return new JObject { { "ok", true }, { "id", pub["id"] }, { "status", pub["status"] ?? "none" }, { "round", pub["round"] ?? 0 }, { "mode", pub["mode"] ?? ses?["Mode"] }, { "teamSize", pub["teamSize"] ?? ses?["TeamSize"] }, { "oddPolicy", ses?["OddPolicy"] }, { "eligibility", ses?["Eligibility"] },
                { "entrants", ent }, { "signedUp", pub["signedUp"] ?? ent.Count }, { "practice", pub["practice"] ?? false }, { "sim", pub["sim"] ?? false }, { "public", PublicView(pub) } };
        }
        static JObject PublicView(JObject pub) { var v = WheelPublic.Adapt((JObject)pub.DeepClone()); v.Remove("serverNow"); return v; }   // serverNow changes every call: it would make the section look "changed" forever
        static JObject Section(string name)
        {
            switch (name)
            {
                case "obs": return ObsTree.Get(null);
                case "obsstatus": return ObsStatus();
                case "live": return LiveState.Api();
                case "customs": return CustomsView.State();
                case "wheel": return WheelState();
            }
            return null;
        }
        static readonly string[] Sections = { "obs", "obsstatus", "live", "customs", "wheel" };
        static string Strip(JObject o) { var c = (JObject)o.DeepClone(); c.Remove("checkedAgoSec"); c.Remove("now"); c.Remove("updatedAt"); return c.ToString(Newtonsoft.Json.Formatting.None); }

        static void Start()
        {
            lock (L) { if (_started) return; _started = true; }
            Task.Run(() =>
            {
                while (true)
                {
                    _kick.Wait(700); _kick.Reset();
                    if (_clients <= 0) continue;
                    try
                    {
                        foreach (var s in Sections)
                        {
                            JObject o; try { o = Section(s); } catch (Exception) { continue; }
                            if (o == null) continue; string key = Strip(o); string prev; lock (L) { _last.TryGetValue(s, out prev); }
                            if (prev == key) continue; lock (L) _last[s] = key; Publish(s, o);
                        }
                        var act = Latest.Activity(_actSeq < 0 ? long.MaxValue : _actSeq, 50, null);
                        long top = (long?)act["seq"] ?? 0; if (_actSeq < 0) _actSeq = top;
                        else foreach (var it in (act["items"] as JArray ?? new JArray())) { Publish("activity", it); _actSeq = Math.Max(_actSeq, (long?)it["seq"] ?? _actSeq); }
                    }
                    catch (Exception ex) { Clog.Warn("events", "watcher: " + ex.Message); }
                }
            });
        }

        static JObject Snapshot()
        {
            var s = new JObject();
            foreach (var n in Sections) { try { s[n] = Section(n); } catch (Exception) { s[n] = null; } }
            try { var act = Latest.Activity(0, 30, null); s["activity"] = act["items"]; } catch (Exception) { s["activity"] = new JArray(); }
            s["chat"] = ChatFeed.Recent(0, 50); s["chatSeq"] = ChatFeed.Seq; s["simulation"] = Sim.On;
            return s;
        }

        /// <summary>called by the listener loop for GET /api/events: takes over the response (returns true = the caller must NOT close it).</summary>
        public static bool Accept(HttpListenerContext c)
        {
            Start();
            Task.Run(() => Serve(c));
            return true;
        }
        static void Serve(HttpListenerContext c)
        {
            var r = c.Response; Interlocked.Increment(ref _clients);
            try
            {
                string o = c.Request.Headers["Origin"] ?? ""; if (o != "") r.Headers["Access-Control-Allow-Origin"] = o;
                r.ContentType = "text/event-stream; charset=utf-8"; r.Headers["Cache-Control"] = "no-store"; r.Headers["X-Accel-Buffering"] = "no"; r.SendChunked = true; r.KeepAlive = true;
                var os = r.OutputStream;
                Action<string> send = t => { var b = Encoding.UTF8.GetBytes(t); os.Write(b, 0, b.Length); os.Flush(); };
                long sent;
                lock (L) { sent = _seq; foreach (var s in Sections) { JObject cur = null; try { cur = Section(s); } catch (Exception) { } if (cur != null && !_last.ContainsKey(s)) _last[s] = Strip(cur); } }
                send("retry: 1000\n\n"); send(Frame(sent, "snapshot", Snapshot()));
                DateTime beat = DateTime.UtcNow;
                while (true)
                {
                    List<string> frames = null;
                    lock (L)
                    {
                        if (_ring.Count == 0 || _ring[_ring.Count - 1].Key <= sent) Monitor.Wait(L, 1000);
                        frames = _ring.Where(x => x.Key > sent).Select(x => x.Value).ToList(); if (_ring.Count > 0) sent = Math.Max(sent, _ring[_ring.Count - 1].Key);
                    }
                    foreach (var f in frames) send(f);
                    if ((DateTime.UtcNow - beat).TotalSeconds >= 15) { send(": hb\n\n"); beat = DateTime.UtcNow; } else if (frames.Count > 0) beat = DateTime.UtcNow;
                }
            }
            catch (Exception) { }
            finally { Interlocked.Decrement(ref _clients); try { r.Close(); } catch (Exception) { } }
        }
    }
}
