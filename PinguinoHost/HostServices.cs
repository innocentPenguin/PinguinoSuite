using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    // OBS control: obs-websocket v5. Method names are the ones PinguinoBotCore finds by reflection.
    public partial class HostCPH
    {
        public ObsClient Obs;
        public bool ObsIsConnected() { return Obs != null && Obs.Connected; }
        public bool ObsSetScene(string scene) { return Obs != null && Obs.Request("SetCurrentProgramScene", new JObject { { "sceneName", scene } }); }
        public bool ObsShowSource(string scene, string source) { return Obs != null && Obs.SetVisible(scene, source, true); }
        public bool ObsHideSource(string scene, string source) { return Obs != null && Obs.SetVisible(scene, source, false); }
    }

    public class ObsClient
    {
        readonly string url, password; ClientWebSocket ws; int seq; bool identified;
        readonly Dictionary<string, TaskCompletionSource<JObject>> pending = new Dictionary<string, TaskCompletionSource<JObject>>();
        public bool Connected { get { return ws != null && ws.State == WebSocketState.Open && identified; } }
        public ObsClient(string host, int port, string pw) { url = "ws://" + host + ":" + port; password = pw ?? ""; }

        public async Task RunForever()
        {
            int backoff = 3;
            while (true)
            {
                try
                {
                    identified = false; ws = new ClientWebSocket();
                    await ws.ConnectAsync(new Uri(url), CancellationToken.None);
                    while (ws.State == WebSocketState.Open)
                    {
                        var msg = await Receive();
                        if (msg == null) break;
                        int op = (int)msg["op"]; var d = msg["d"] as JObject;
                        if (op == 0)   // Hello -> Identify
                        {
                            var id = new JObject { { "rpcVersion", 1 } };
                            var auth = d["authentication"] as JObject;
                            if (auth != null && password != "")
                            {
                                string secret = B64(Sha(password + (string)auth["salt"]));
                                id["authentication"] = B64(Sha(secret + (string)auth["challenge"]));
                            }
                            await Send(new JObject { { "op", 1 }, { "d", id } });
                        }
                        else if (op == 2) { identified = true; backoff = 3; Console.WriteLine("OBS connected"); }
                        else if (op == 7)
                        {
                            string rid = (string)d["requestId"]; TaskCompletionSource<JObject> tcs;
                            lock (pending) { if (pending.TryGetValue(rid, out tcs)) pending.Remove(rid); else tcs = null; }
                            if (tcs != null) tcs.TrySetResult(d);
                        }
                    }
                }
                catch (Exception) { }
                identified = false;
                await Task.Delay(backoff * 1000); backoff = Math.Min(backoff * 2, 30);
            }
        }
        static byte[] Sha(string s) { using (var h = SHA256.Create()) return h.ComputeHash(Encoding.UTF8.GetBytes(s)); }
        static string B64(byte[] b) { return Convert.ToBase64String(b); }
        async Task<JObject> Receive()
        {
            var buf = new byte[65536]; var sb = new StringBuilder(); WebSocketReceiveResult r;
            do { r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), CancellationToken.None); if (r.MessageType == WebSocketMessageType.Close) return null; sb.Append(Encoding.UTF8.GetString(buf, 0, r.Count)); } while (!r.EndOfMessage);
            return JObject.Parse(sb.ToString());
        }
        Task Send(JObject o) { return ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(o.ToString(Newtonsoft.Json.Formatting.None))), WebSocketMessageType.Text, true, CancellationToken.None); }

        JObject Call(string type, JObject data)
        {
            if (!Connected) return null;
            string rid = "r" + Interlocked.Increment(ref seq); var tcs = new TaskCompletionSource<JObject>();
            lock (pending) pending[rid] = tcs;
            try
            {
                Send(new JObject { { "op", 6 }, { "d", new JObject { { "requestType", type }, { "requestId", rid }, { "requestData", data ?? new JObject() } } } }).Wait(3000);
                if (!tcs.Task.Wait(4000)) { lock (pending) pending.Remove(rid); return null; }
                return tcs.Task.Result;
            }
            catch (Exception) { return null; }
        }
        public bool Request(string type, JObject data) { var r = Call(type, data); return r != null && (bool)r["requestStatus"]["result"]; }
        public bool SetVisible(string scene, string source, bool on)
        {
            var r = Call("GetSceneItemId", new JObject { { "sceneName", scene }, { "sourceName", source } });
            if (r == null || !(bool)r["requestStatus"]["result"]) return false;
            return Request("SetSceneItemEnabled", new JObject { { "sceneName", scene }, { "sceneItemId", r["responseData"]["sceneItemId"] }, { "sceneItemEnabled", on } });
        }
    }

    // Twitch EventSub websocket: subs, gifts, cheers, raids, follows -> PinguinoChat (same args Streamer.bot passes).
    public static class EventSub
    {
        public static async Task RunForever(JObject s, Action<Dictionary<string, object>> raise)
        {
            string tok = s.Value<string>("UserToken"), cid = s.Value<string>("ClientId"), bid = s.Value<string>("BroadcasterId");
            if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid) || string.IsNullOrEmpty(bid)) { Console.WriteLine("(EventSub off: needs ClientId, UserToken, BroadcasterId)"); return; }
            var http = new HttpClient(); http.DefaultRequestHeaders.Add("Authorization", "Bearer " + tok); http.DefaultRequestHeaders.Add("Client-Id", cid);
            int backoff = 3;
            while (true)
            {
                try
                {
                    using (var ws = new ClientWebSocket())
                    {
                        await ws.ConnectAsync(new Uri(Environment.GetEnvironmentVariable("PINGUINO_EVENTSUB_URL") ?? "wss://eventsub.wss.twitch.tv/ws"), CancellationToken.None);
                        var buf = new byte[65536]; bool open = true;
                        while (open && ws.State == WebSocketState.Open)
                        {
                            var sb = new StringBuilder(); WebSocketReceiveResult r;
                            do
                            {
                                r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), CancellationToken.None);
                                if (r.MessageType == WebSocketMessageType.Close) { open = false; break; }
                                sb.Append(Encoding.UTF8.GetString(buf, 0, r.Count));
                            } while (!r.EndOfMessage);
                            if (!open) break;
                            var m = JObject.Parse(sb.ToString()); string type = (string)m["metadata"]["message_type"];
                            if (type == "session_welcome") { await Subscribe(http, (string)m["payload"]["session"]["id"], bid); Console.WriteLine("EventSub connected"); backoff = 3; HostApi.EventSubConnected = true; }
                            else if (type == "notification") Handle(m, raise);
                            else if (type == "session_reconnect") open = false;
                        }
                    }
                }
                catch (Exception ex) { Console.WriteLine("EventSub lost: " + ex.Message); }
                HostApi.EventSubConnected = false;
                await Task.Delay(backoff * 1000); backoff = Math.Min(backoff * 2, 60);
            }
        }
        static async Task Subscribe(HttpClient http, string session, string bid)
        {
            var subs = new[] {
                new[] { "channel.subscribe", "1", "broadcaster_user_id" }, new[] { "channel.subscription.message", "1", "broadcaster_user_id" },
                new[] { "channel.subscription.gift", "1", "broadcaster_user_id" }, new[] { "channel.cheer", "1", "broadcaster_user_id" },
                new[] { "channel.raid", "1", "to_broadcaster_user_id" }, new[] { "channel.follow", "2", "broadcaster_user_id" } };
            foreach (var s in subs)
            {
                var cond = new JObject { { s[2], bid } }; if (s[0] == "channel.follow") cond["moderator_user_id"] = bid;
                var body = new JObject { { "type", s[0] }, { "version", s[1] }, { "condition", cond }, { "transport", new JObject { { "method", "websocket" }, { "session_id", session } } } };
                var resp = await http.PostAsync(HostApi.Helix + "/eventsub/subscriptions", new StringContent(body.ToString(), Encoding.UTF8, "application/json"));
                if (!resp.IsSuccessStatusCode) Console.WriteLine("EventSub " + s[0] + " refused (" + (int)resp.StatusCode + "); check token scopes");
            }
        }
        static void Handle(JObject m, Action<Dictionary<string, object>> raise)
        {
            string t = (string)m["metadata"]["subscription_type"]; var e = m["payload"]["event"] as JObject; if (e == null) return;
            var a = new Dictionary<string, object>(); Func<string, string> U = k => (string)e[k] ?? "";
            string tier = U("tier") == "3000" ? "3" : U("tier") == "2000" ? "2" : "1";
            switch (t)
            {
                case "channel.subscribe": if ((bool?)e["is_gift"] == true) return; a["eventType"] = "TwitchSub"; a["userName"] = U("user_login"); a["tier"] = tier; break;
                case "channel.subscription.message": a["eventType"] = "TwitchReSub"; a["userName"] = U("user_login"); a["tier"] = tier; break;
                case "channel.subscription.gift": a["eventType"] = "TwitchGiftBomb"; a["userName"] = U("user_login"); a["tier"] = tier; break;
                case "channel.cheer": a["eventType"] = "TwitchCheer"; a["userName"] = U("user_login"); a["bits"] = (int?)e["bits"] ?? 0; break;
                case "channel.raid": a["eventType"] = "TwitchRaid"; a["userName"] = U("from_broadcaster_user_login"); a["viewers"] = (int?)e["viewers"] ?? 0; break;
                case "channel.follow": a["eventType"] = "TwitchFollow"; a["userName"] = U("user_login"); break;
                default: return;
            }
            raise(a);
        }
    }

    // Serves overlays + live_state to OBS browser sources (replaces python http.server on 8765).
    public static class OverlayServer
    {
        public static void Start(int port, params string[] roots)
        {
            var l = new HttpListener(); l.Prefixes.Add("http://127.0.0.1:" + port + "/");
            try { l.Start(); } catch (Exception ex) { Console.WriteLine("overlay server not started: " + ex.Message); return; }
            Console.WriteLine("overlays: http://127.0.0.1:" + port + "/players.html");
            Task.Run(async () =>
            {
                while (true)
                {
                    var c = await l.GetContextAsync();
                    try
                    {
                        if (HostApi.Handle(c)) continue;
                        string rel = Uri.UnescapeDataString(c.Request.Url.AbsolutePath.TrimStart('/')); if (rel == "") rel = "queue.html";
                        string file = null;
                        foreach (var r in roots.Where(x => !string.IsNullOrEmpty(x) && Directory.Exists(x)))
                        {
                            string p = Path.GetFullPath(Path.Combine(r, rel));
                            if (p.StartsWith(Path.GetFullPath(r), StringComparison.OrdinalIgnoreCase) && File.Exists(p)
                                && !p.EndsWith("secrets.json", StringComparison.OrdinalIgnoreCase) && !p.EndsWith("settings.json", StringComparison.OrdinalIgnoreCase)) { file = p; break; }
                        }
                        if (file == null) c.Response.StatusCode = 404;
                        else
                        {
                            string ext = Path.GetExtension(file).ToLowerInvariant();
                            c.Response.ContentType = ext == ".html" ? "text/html; charset=utf-8" : ext == ".js" ? "application/javascript" : ext == ".json" ? "application/json" : ext == ".css" ? "text/css" : ext == ".png" ? "image/png" : ext == ".webm" ? "video/webm" : ext == ".mp4" ? "video/mp4" : "application/octet-stream";
                            c.Response.Headers["Cache-Control"] = "no-store"; var bytes = File.ReadAllBytes(file); c.Response.OutputStream.Write(bytes, 0, bytes.Length);
                        }
                    }
                    catch (Exception) { try { c.Response.StatusCode = 500; } catch (Exception) { } }
                    finally { try { c.Response.Close(); } catch (Exception) { } }
                }
            });
        }
    }
}
