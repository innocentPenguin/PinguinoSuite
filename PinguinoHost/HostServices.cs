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
        public bool? ObsStreaming() { if (Obs == null || !Obs.Connected) return null; var d = Obs.Data("GetStreamStatus", null); return d == null ? (bool?)null : (bool?)d["outputActive"]; }
        /// <summary>true/false from OBS GetRecordStatus (paused counts as recording); null when OBS is not reachable</summary>
        public bool? ObsRecording() { if (Obs == null || !Obs.Connected) return null; var d = Obs.Data("GetRecordStatus", null); if (d == null) return null; bool on = (bool?)d["outputActive"] == true || (bool?)d["outputPaused"] == true; Obs.SetRec(on); return on; }
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
        /// <summary>true while OBS is recording (a paused recording counts); false when OBS is not connected</summary>
        public bool Recording { get { return Connected && _rec; } }
        volatile bool _rec;
        public void SetRec(bool on) { if (_rec == on) return; _rec = on; LiveState.OnRecording(on); }
        public ObsClient(string host, int port, string pw) { url = "ws://" + host + ":" + port; password = pw ?? ""; }

        public async Task RunForever()
        {
            int backoff = 3;
            while (true)
            {
                while (!Lease.MayRun) await Task.Delay(1500);
                try
                {
                    identified = false; ws = new ClientWebSocket();
                    await ws.ConnectAsync(new Uri(url), CancellationToken.None);
                    while (ws.State == WebSocketState.Open)
                    {
                        var msg = await Receive();
                        if (msg == null) break;
                        int op = (int)msg["op"]; var d = msg["d"] as JObject;
                        if (op == 5 && d != null) { try { Events.OnObsEvent((string)d["eventType"]); } catch (Exception) { } }   // Master View: scene / item / output change -> push at once
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
                        else if (op == 2) { identified = true; backoff = 3; Console.WriteLine("OBS connected"); Clog.Info("obs", "OBS connected"); Task.Run(() => { try { var rs = Data("GetRecordStatus", null); if (rs != null) SetRec((bool?)rs["outputActive"] == true); } catch (Exception) { } }); ReplayBuf.Ensure(this, "OBS connected"); }
                        else if (op == 5 && d != null && (string)d["eventType"] == "StreamStateChanged")
                        { var ed = d["eventData"] as JObject; if (ed != null && (bool?)ed["outputActive"] == true) ReplayBuf.Ensure(this, "stream started"); }
                        else if (op == 5 && d != null && (string)d["eventType"] == "ReplayBufferStateChanged")
                        { var ed = d["eventData"] as JObject; if (ed != null) ReplayBuf.OnState((bool?)ed["outputActive"] == true); }
                        else if (op == 5 && d != null && (string)d["eventType"] == "RecordStateChanged")   // started / stopped / paused / resumed
                        { var ed = d["eventData"] as JObject; if (ed != null) { if ((bool?)ed["outputActive"] == true && (string)ed["outputState"] == "OBS_WEBSOCKET_OUTPUT_STARTED") ReplayBuf.Ensure(this, "recording started"); string st = (string)ed["outputState"] ?? ""; SetRec((bool?)ed["outputActive"] == true || st.IndexOf("PAUSED", StringComparison.OrdinalIgnoreCase) >= 0); } }
                        else if (op == 7)
                        {
                            string rid = (string)d["requestId"]; TaskCompletionSource<JObject> tcs;
                            lock (pending) { if (pending.TryGetValue(rid, out tcs)) pending.Remove(rid); else tcs = null; }
                            if (tcs != null) tcs.TrySetResult(d);
                        }
                    }
                }
                catch (Exception) { }
                if (identified) Clog.Warn("obs", "OBS connection lost");
                identified = false; SetRec(false); ReplayBuf.OnDisconnect();
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
        /// <summary>the raw obs-websocket response (requestStatus + responseData); null when OBS did not answer</summary>
        public JObject Raw(string type, JObject data) { return Call(type, data); }
        public JObject Data(string type, JObject data) { var r = Call(type, data); return r != null && (bool)r["requestStatus"]["result"] ? r["responseData"] as JObject : null; }
        public bool Toggle(string scene, string source)
        {
            var r = Call("GetSceneItemId", new JObject { { "sceneName", scene }, { "sourceName", source } });
            if (r == null || !(bool)r["requestStatus"]["result"]) return false;
            var id = r["responseData"]["sceneItemId"]; var cur = Call("GetSceneItemEnabled", new JObject { { "sceneName", scene }, { "sceneItemId", id } });
            if (cur == null || !(bool)cur["requestStatus"]["result"]) return false;
            return Request("SetSceneItemEnabled", new JObject { { "sceneName", scene }, { "sceneItemId", id }, { "sceneItemEnabled", !(bool)cur["responseData"]["sceneItemEnabled"] } });
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
                while (!Lease.MayRun) await Task.Delay(1500);
                var lt = Lease.Token;
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
                                r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), lt);
                                if (r.MessageType == WebSocketMessageType.Close) { open = false; break; }
                                sb.Append(Encoding.UTF8.GetString(buf, 0, r.Count));
                            } while (!r.EndOfMessage);
                            if (!open) break;
                            var m = JObject.Parse(sb.ToString()); string type = (string)m["metadata"]["message_type"];
                            Lag.Note((string)m["metadata"]["message_timestamp"], type == "notification");
                            if (type == "session_welcome") { HostApi.EventSubRefused = 0; _bid = bid; await Subscribe(http, (string)m["payload"]["session"]["id"], bid); Console.WriteLine("EventSub connected"); Clog.Info("eventsub", "EventSub connected"); backoff = 3; HostApi.EventSubConnected = true; }
                            else if (type == "notification") Handle(m, raise);
                            else if (type == "session_reconnect") open = false;
                        }
                    }
                }
                catch (Exception ex) { Console.WriteLine("EventSub lost: " + ex.Message); Clog.Warn("eventsub", "EventSub lost: " + ex.Message); }
                HostApi.EventSubConnected = false;
                await Task.Delay(backoff * 1000); backoff = Math.Min(backoff * 2, 60);
            }
        }
        static async Task Subscribe(HttpClient http, string session, string bid)
        {
            var subs = new[] {
                new[] { "channel.subscribe", "1", "broadcaster_user_id" }, new[] { "channel.subscription.message", "1", "broadcaster_user_id" },
                new[] { "channel.subscription.gift", "1", "broadcaster_user_id" }, new[] { "channel.cheer", "1", "broadcaster_user_id" },
                new[] { "channel.raid", "1", "to_broadcaster_user_id" }, new[] { "channel.follow", "2", "broadcaster_user_id" },
                new[] { "stream.online", "1", "broadcaster_user_id", "opt" }, new[] { "stream.offline", "1", "broadcaster_user_id", "opt" },
                new[] { "channel.channel_points_custom_reward_redemption.add", "1", "broadcaster_user_id", "opt" },
                new[] { "channel.ban", "1", "broadcaster_user_id", "opt" }, new[] { "channel.unban", "1", "broadcaster_user_id", "opt" }, new[] { "channel.moderator.add", "1", "broadcaster_user_id", "opt" }, new[] { "channel.moderator.remove", "1", "broadcaster_user_id", "opt" }, new[] { "channel.raid", "1", "from_broadcaster_user_id", "opt" },
                new[] { "channel.poll.begin", "1", "broadcaster_user_id", "opt" }, new[] { "channel.poll.progress", "1", "broadcaster_user_id", "opt" }, new[] { "channel.poll.end", "1", "broadcaster_user_id", "opt" },
                new[] { "channel.prediction.begin", "1", "broadcaster_user_id", "opt" }, new[] { "channel.prediction.progress", "1", "broadcaster_user_id", "opt" }, new[] { "channel.prediction.lock", "1", "broadcaster_user_id", "opt" }, new[] { "channel.prediction.end", "1", "broadcaster_user_id", "opt" },
                new[] { "channel.hype_train.begin", "2", "broadcaster_user_id", "opt" }, new[] { "channel.hype_train.progress", "2", "broadcaster_user_id", "opt" }, new[] { "channel.hype_train.end", "2", "broadcaster_user_id", "opt" },
                new[] { "automod.message.hold", "1", "broadcaster_user_id", "opt" }, new[] { "automod.message.update", "1", "broadcaster_user_id", "opt" },
                new[] { "channel.goal.begin", "1", "broadcaster_user_id", "opt" }, new[] { "channel.goal.progress", "1", "broadcaster_user_id", "opt" }, new[] { "channel.goal.end", "1", "broadcaster_user_id", "opt" } };
            foreach (var s in subs)
            {
                var cond = new JObject { { s[2], bid } }; if (s[0] == "channel.follow" || s[0].StartsWith("automod.")) cond["moderator_user_id"] = bid;
                var body = new JObject { { "type", s[0] }, { "version", s[1] }, { "condition", cond }, { "transport", new JObject { { "method", "websocket" }, { "session_id", session } } } };
                var resp = await http.PostAsync(HostApi.Helix + "/eventsub/subscriptions", new StringContent(body.ToString(), Encoding.UTF8, "application/json"));
                if (!resp.IsSuccessStatusCode) { if (s.Length < 4) HostApi.EventSubRefused++; Console.WriteLine("EventSub " + s[0] + " refused (" + (int)resp.StatusCode + "); check token scopes"); Clog.Warn("eventsub", "subscription " + s[0] + " refused (HTTP " + (int)resp.StatusCode + (resp.StatusCode == System.Net.HttpStatusCode.Unauthorized ? ", token rejected - sign in again" : ", check token scopes") + ")"); }
            }
        }
        static string _bid = "";
        /// <summary>sim mode: "eventsub channel.poll.end {json event}" runs the same mapping as a real EventSub notification</summary>
        public static void Simulate(string type, string json, Action<Dictionary<string, object>> raise)
        {
            var m = new JObject { { "metadata", new JObject { { "subscription_type", type }, { "sim", true } } }, { "payload", new JObject { { "event", JObject.Parse(json) } } } }; Handle(m, raise);
        }
        static void Handle(JObject m, Action<Dictionary<string, object>> raise)
        {
            string t = (string)m["metadata"]["subscription_type"]; var e = m["payload"]["event"] as JObject; if (e == null) return;
            var a = new Dictionary<string, object>(); Func<string, string> U = k => (string)e[k] ?? "";
            a["eventId"] = (string)m["metadata"]["message_id"] ?? U("id");
            a["months"] = U("cumulative_months"); a["streakMonths"] = U("streak_months"); a["message"] = e["message"] is JObject ? (string)e["message"]["text"] ?? "" : U("message");
            if ((bool?)m["metadata"]["sim"] == true) a["sim"] = "true";   // simulated EventSub: shown as sim, never paid, never alerted
            string tier = U("tier") == "3000" ? "3" : U("tier") == "2000" ? "2" : "1";
            switch (t)
            {
                case "channel.subscribe": if ((bool?)e["is_gift"] == true) { try { Economy.PointsEvent(new Dictionary<string, object> { { "eventType", "TwitchGiftRecipient" }, { "userName", U("user_login") }, { "eventId", (string)a["eventId"] }, { "tier", tier } }); } catch (Exception) { } return; } a["eventType"] = "TwitchSub"; a["userName"] = U("user_login"); a["tier"] = tier; break;
                case "channel.subscription.message": a["eventType"] = "TwitchReSub"; a["userName"] = U("user_login"); a["tier"] = tier; break;
                case "channel.subscription.gift": a["eventType"] = "TwitchGiftBomb"; a["userName"] = (bool?)e["is_anonymous"] == true ? "Anonymous" : U("user_login"); a["tier"] = tier; a["total"] = (int?)e["total"] ?? 1; a["cumulative"] = (int?)e["cumulative_total"] ?? 0; a["anonymous"] = ((bool?)e["is_anonymous"] ?? false).ToString().ToLowerInvariant(); break;
                case "channel.cheer": a["eventType"] = "TwitchCheer"; a["userName"] = U("user_login"); a["bits"] = (int?)e["bits"] ?? 0; a["bitsType"] = U("type"); break;
                case "channel.raid":
                    if (U("from_broadcaster_user_id") == _bid && _bid != "") { a["eventType"] = "TwitchRaidOut"; a["userName"] = U("to_broadcaster_user_login"); a["target"] = U("to_broadcaster_user_login"); a["viewers"] = (int?)e["viewers"] ?? 0; }
                    else { a["eventType"] = "TwitchRaid"; a["userName"] = U("from_broadcaster_user_login"); a["viewers"] = (int?)e["viewers"] ?? 0; }
                    break;
                case "channel.ban": a["eventType"] = "TwitchBan"; a["userName"] = U("user_login"); a["moderator"] = U("moderator_user_login"); a["reason"] = U("reason"); a["permanent"] = ((bool?)e["is_permanent"] ?? false).ToString().ToLowerInvariant(); break;
                case "channel.unban": a["eventType"] = "TwitchUnban"; a["userName"] = U("user_login"); a["moderator"] = U("moderator_user_login"); break;
                case "channel.moderator.add": a["eventType"] = "TwitchMod"; a["userName"] = U("user_login"); a["moderator"] = U("broadcaster_user_login"); break;
                case "channel.moderator.remove": a["eventType"] = "TwitchUnmod"; a["userName"] = U("user_login"); a["moderator"] = U("broadcaster_user_login"); break;
                case "channel.follow": a["eventType"] = "TwitchFollow"; a["userName"] = U("user_login"); break;
                case "channel.poll.begin": case "channel.poll.progress": case "channel.poll.end":
                    a["eventType"] = "TwitchPoll"; a["state"] = t.Substring(13); a["userName"] = U("broadcaster_user_login"); a["x.id"] = U("id"); a["x.title"] = U("title"); a["x.choices"] = (e["choices"] ?? new JArray()).ToString(Newtonsoft.Json.Formatting.None);
                    a["x.status"] = U("status"); a["x.endsAt"] = U("ends_at"); a["x.startedAt"] = U("started_at"); break;
                case "channel.prediction.begin": case "channel.prediction.progress": case "channel.prediction.lock": case "channel.prediction.end":
                    a["eventType"] = "TwitchPrediction"; a["state"] = t.Substring(19); a["userName"] = U("broadcaster_user_login"); a["x.id"] = U("id"); a["x.title"] = U("title"); a["x.outcomes"] = (e["outcomes"] ?? new JArray()).ToString(Newtonsoft.Json.Formatting.None);
                    a["x.status"] = U("status"); a["x.winningOutcomeId"] = U("winning_outcome_id"); a["x.locksAt"] = U("locks_at"); a["x.startedAt"] = U("started_at"); break;
                case "channel.hype_train.begin": case "channel.hype_train.progress": case "channel.hype_train.end":
                    a["eventType"] = "TwitchHype"; a["state"] = t.Substring(19); a["userName"] = U("broadcaster_user_login"); a["x.id"] = U("id"); a["x.level"] = U("level"); a["x.total"] = U("total"); a["x.progress"] = U("progress"); a["x.goal"] = U("goal");
                    a["x.type"] = U("type"); a["x.expiresAt"] = U("expires_at"); a["x.topContributions"] = (e["top_contributions"] ?? new JArray()).ToString(Newtonsoft.Json.Formatting.None); break;
                case "channel.goal.begin": case "channel.goal.progress": case "channel.goal.end":
                    a["eventType"] = "TwitchGoal"; a["state"] = t.Substring(13); a["userName"] = U("broadcaster_user_login"); a["x.id"] = U("id"); a["x.type"] = U("type"); a["x.description"] = U("description"); a["x.isAchieved"] = U("is_achieved");
                    a["x.current"] = U("current_amount"); a["x.target"] = U("target_amount"); a["x.startedAt"] = U("started_at"); break;
                case "automod.message.hold": case "automod.message.update": AutomodHeld.Note(t, e); return;
                case "stream.online": a["eventType"] = "StreamOnline"; break;
                case "stream.offline": a["eventType"] = "StreamOffline"; break;
                case "channel.channel_points_custom_reward_redemption.add": a["eventType"] = "TwitchRedeem"; a["userName"] = U("user_login"); a["title"] = (string)e["reward"]?["title"] ?? ""; a["input"] = U("user_input"); a["cost"] = (int?)e["reward"]?["cost"] ?? 0; a["redemptionId"] = (string)e["id"] ?? ""; a["rewardId"] = (string)e["reward"]?["id"] ?? ""; break;
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
            OverlayFiles.Root = roots.Take(2).FirstOrDefault(x => !string.IsNullOrEmpty(x) && Directory.Exists(x)) ?? "";   // the managed (writable) overlay folder: OverlayDir, else the suite overlays
            Console.WriteLine("overlays: http://127.0.0.1:" + port + "/players.html");
            Task.Run(async () =>
            {
                while (true)
                {
                    var c = await l.GetContextAsync(); bool keepOpen = false;
                    try
                    {
                        if (c.Request.HttpMethod == "GET" && c.Request.Url.AbsolutePath == "/api/events" && HostApi.EventsOk(c.Request)) { keepOpen = Events.Accept(c); continue; }   // SSE: a long-lived response owned by Events
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
                            c.Response.ContentType = ext == ".html" ? "text/html; charset=utf-8" : ext == ".js" ? "application/javascript" : ext == ".json" ? "application/json" : ext == ".css" ? "text/css" : ext == ".png" ? "image/png" : ext == ".webp" ? "image/webp" : ext == ".gif" ? "image/gif" : ext == ".svg" ? "image/svg+xml" : ext == ".jpg" ? "image/jpeg" : ext == ".webm" ? "video/webm" : ext == ".mp4" ? "video/mp4" : "application/octet-stream";
                            c.Response.Headers["Cache-Control"] = (ext == ".webp" || ext == ".png" || ext == ".gif" || ext == ".jpg" || ext == ".woff2") ? "max-age=3600" : "no-store"; var bytes = File.ReadAllBytes(file);   // art can be cached (no re-download / animation restart); pages and data stay fresh
                             c.Response.OutputStream.Write(bytes, 0, bytes.Length);
                        }
                    }
                    catch (Exception) { try { c.Response.StatusCode = 500; } catch (Exception) { } }
                    finally { if (!keepOpen) { try { c.Response.Close(); } catch (Exception) { } } }
                }
            });
        }
    }
}
