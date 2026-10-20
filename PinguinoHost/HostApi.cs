using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    // Setup interface + status API (served by the same listener as the overlays). Localhost only.
    public static partial class HostApi
    {
        public static string DataDir = "";
        public static int Port = 8770;
        public static readonly string Helix = Environment.GetEnvironmentVariable("PINGUINO_HELIX_BASE") ?? "https://api.twitch.tv/helix";
        public static DateTime Started = DateTime.UtcNow;
        public static volatile bool IrcConnected, EventSubConnected, SimMode; public static volatile int EventSubRefused;
        public static long Messages; public static DateTime LastMessage = DateTime.MinValue;
        public static Func<bool> ObsConnected = () => false;
        static readonly string[] Secret = { "UserToken", "ObsPassword" };
        static readonly string[] Plain = { "Channel", "ClientId", "SenderId", "BroadcasterId", "ObsHost", "ObsPort", "OverlayPort" };
        public const string Scopes = "chat:read chat:edit user:write:chat moderator:manage:banned_users channel:read:subscriptions bits:read moderator:read:followers moderation:read channel:read:redemptions channel:moderate clips:edit channel:read:ads moderator:manage:shoutouts moderator:read:chatters";

        static string FilePath { get { return Path.Combine(DataDir, "host_secrets.json"); } }
        // read-only views that also see the key vault (a plaintext value wins; Save always uses Load() so a vault value is never written back to a file)
        /// <summary>the streamer sign-in (token from the file or the vault) for the Twitch API steps; never logged.</summary>
        public static JObject StreamerCreds() { return LoadV(); }
        static JObject LoadV()
        {
            var s = Load();
            foreach (var k in new[] { "UserToken", "ObsPassword" }) if (string.IsNullOrEmpty((string)s[k])) { var v = Vault.Get("HOST_SECRETS." + k); if (v != "") s[k] = v; }
            return s;
        }
        static JObject BotSecretsV()
        {
            var sec = LoadFile("bots_secrets.json");
            foreach (string role in BotIds)
            {
                string v = Vault.Get("BOTS_SECRETS." + role + ".UserToken"); var o = sec[role] as JObject;
                if (v != "" && o != null && string.IsNullOrEmpty((string)o["UserToken"])) o["UserToken"] = v;
            }
            return sec;
        }
        static JObject Load() { try { return File.Exists(FilePath) ? JObject.Parse(File.ReadAllText(FilePath)) : new JObject(); } catch (Exception) { return new JObject(); } }
        static void Save(JObject o) { File.WriteAllText(FilePath, o.ToString()); }

        static bool LocalOk(HttpListenerRequest r)
        {
            string h = r.Headers["Host"] ?? ""; if (!(h.StartsWith("127.0.0.1:") || h.StartsWith("localhost:"))) return false;
            string o = r.Headers["Origin"]; return string.IsNullOrEmpty(o) || o.StartsWith("http://127.0.0.1:") || o.StartsWith("http://localhost:") || IsTauri(o);
        }
        static bool IsTauri(string o) { return o == "tauri://localhost" || o == "http://tauri.localhost" || o == "https://tauri.localhost"; }
        // State-changing calls: our own page (same origin) is trusted; the Suite shell, Stream Deck and scripts must present the token when one is configured.
        static bool WriteOk(HttpListenerRequest r)
        {
            string o = r.Headers["Origin"] ?? "";
            if (o == "http://127.0.0.1:" + Port || o == "http://localhost:" + Port) return true;
            string a = Environment.GetEnvironmentVariable("PINGUINO_API_TOKEN") ?? "", m = Environment.GetEnvironmentVariable("PINGUINO_MODULE_TOKEN") ?? "";
            if (a == "" && m == "") return !IsTauri(o);
            string h = r.Headers["Authorization"] ?? ""; string t = h.StartsWith("Bearer ") ? h.Substring(7) : (r.Headers["X-Pinguino-Token"] ?? "");
            return t != "" && (t == a || t == m);
        }

        // returns true when it answered the request
        public static bool Handle(HttpListenerContext c)
        {
            string p = c.Request.Url.AbsolutePath;
            if (p != "/" && p != "/setup" && p != "/auth" && p != "/automations" && p != "/helper-review" && p != "/overlay/latest" && p != "/overlay/latest.html" && p != "/overlay/credits" && p != "/overlay/goal" && p != "/intro" && p != "/overlay/intro" && !p.StartsWith("/intro/media/") && p != "/overlay/subfooter" && p != "/subfooter" && !p.StartsWith("/api/")) return false;
            if (!LocalOk(c.Request)) { c.Response.StatusCode = 403; return true; }
            if (c.Request.HttpMethod == "POST" && !WriteOk(c.Request)) { c.Response.StatusCode = 401; Write(c, "{\"ok\":false,\"error\":\"token required\"}", "application/json"); return true; }
            try
            {
                if (c.Request.HttpMethod == "OPTIONS")   // CORS preflight from the Tauri shell
                { string o = c.Request.Headers["Origin"] ?? ""; if (o != "") c.Response.Headers["Access-Control-Allow-Origin"] = o; c.Response.Headers["Access-Control-Allow-Headers"] = "Authorization, X-Pinguino-Token, Content-Type"; c.Response.StatusCode = 204; return true; }
                { string o = c.Request.Headers["Origin"] ?? ""; if (o != "") c.Response.Headers["Access-Control-Allow-Origin"] = o; }
                if (p == "/api/bots" && c.Request.HttpMethod == "GET") { Write(c, Bots().ToString(), "application/json"); return true; }
                if (p == "/api/bots" && c.Request.HttpMethod == "POST") { Write(c, SaveBot(Body(c)).ToString(), "application/json"); return true; }
                if (p == "/" || p == "/setup" || p == "/auth") { Write(c, Html, "text/html; charset=utf-8"); return true; }
                if (AutoRoutes(c, p)) return true;
                if (p == "/api/summary" && c.Request.HttpMethod == "GET") { Write(c, Summary().ToString(), "application/json"); return true; }
                if (p == "/api/lease" && c.Request.HttpMethod == "GET") { Write(c, Lease.State().ToString(), "application/json"); return true; }
                if (p == "/api/prestream" && c.Request.HttpMethod == "GET") { Write(c, PrestreamCached().ToString(), "application/json"); return true; }
                if (p == "/api/status") { Write(c, Status().ToString(), "application/json"); return true; }
                if (p == "/api/config" && c.Request.HttpMethod == "GET") { Write(c, Config().ToString(), "application/json"); return true; }
                if (p == "/api/config" && c.Request.HttpMethod == "POST") { Write(c, SaveConfig(Body(c)).ToString(), "application/json"); return true; }
                if (p == "/api/run" && c.Request.HttpMethod == "POST")   // Stream Deck / hotkeys: {"text":"!next","user":"ivan"} runs as broadcaster
                { var b = Body(c); string t = (string)b["text"] ?? ""; string u = (string)b["user"] ?? "broadcaster"; if (t == "") { Write(c, "{\"ok\":false,\"error\":\"text required\"}", "application/json"); return true; }
                  System.Threading.Tasks.Task.Run(() => Program.Dispatch(u, t, null, 4, "deck", false, null)); Write(c, "{\"ok\":true}", "application/json"); return true; }
                if (p == "/api/signin" && c.Request.HttpMethod == "POST")   // opens Twitch's sign-in in the PC's default browser (an embedded window may block pop-ups)
                {
                    var b = Body(c); string role = ((string)b["role"] ?? "").Trim().ToLowerInvariant(); var cfg = Config(); string cid = (string)cfg["ClientId"];
                    if (string.IsNullOrEmpty(cid)) { Write(c, "{\"ok\":false,\"error\":\"paste the Client ID in the setup section first\"}", "application/json"); return true; }
                    string u = "https://id.twitch.tv/oauth2/authorize?response_type=token&force_verify=true&state=" + Uri.EscapeDataString(role) + "&client_id=" + Uri.EscapeDataString(cid)
                        + "&redirect_uri=" + Uri.EscapeDataString((string)cfg["redirect"]) + "&scope=" + Uri.EscapeDataString((string)cfg["scopes"]);
                    System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(u) { UseShellExecute = true });
                    Write(c, "{\"ok\":true}", "application/json"); return true;
                }
                if (p == "/api/account/streamer" && c.Request.HttpMethod == "GET") { Write(c, AccountStreamer().ToString(), "application/json"); return true; }
                if (p == "/api/account/streamer/signin" && c.Request.HttpMethod == "POST") { Write(c, AccountSignIn((bool?)Body(c)["open"] != false).ToString(), "application/json"); return true; }
                if (p == "/api/account/streamer/signout" && c.Request.HttpMethod == "POST") { Write(c, AccountSignOut().ToString(), "application/json"); return true; }
                if (p == "/api/bottest" && c.Request.HttpMethod == "POST") { Write(c, BotTest(Body(c)).ToString(), "application/json"); return true; }
                if (p == "/api/token" && c.Request.HttpMethod == "POST") { Write(c, TokenIn(Body(c)).ToString(), "application/json"); return true; }
                c.Response.StatusCode = 404;
            }
            catch (Exception ex) { Write(c, new JObject { { "ok", false }, { "error", ex.Message } }.ToString(), "application/json"); }
            return true;
        }

        static JObject Status()
        {
            var s = LoadV(); bool tok = !string.IsNullOrEmpty((string)s["UserToken"]);
            return new JObject {
                { "ok", true }, { "name", "PinguinoHost" }, { "uptimeSec", (int)(DateTime.UtcNow - Started).TotalSeconds }, { "sim", SimMode },
                { "channel", (string)s["Channel"] ?? "" }, { "chatConnected", IrcConnected }, { "eventSubConnected", EventSubConnected },
                { "obsConnected", ObsConnected() }, { "canSend", tok && !string.IsNullOrEmpty((string)s["ClientId"]) && !string.IsNullOrEmpty((string)s["SenderId"]) && !string.IsNullOrEmpty((string)s["BroadcasterId"]) },
                { "messages", Messages }, { "lastMessageAgoSec", LastMessage == DateTime.MinValue ? (int?)null : (int)(DateTime.UtcNow - LastMessage).TotalSeconds },
                { "overlayPort", Port }, { "dataDir", DataDir }, { "lease", Lease.State() } };
        }

        static JObject Config()
        {
            var s = LoadV(); var o = new JObject();
            foreach (var k in Plain) o[k] = s[k] ?? "";
            foreach (var k in Secret) o["has" + k] = !string.IsNullOrEmpty((string)s[k]);   // never return secret values
            o["scopes"] = Scopes; o["redirect"] = "http://localhost:" + Port + "/auth";
            return o;
        }

        static JObject SaveConfig(JObject b)
        {
            var s = Load();
            foreach (var k in Plain) if (b[k] != null) { if ((string)b[k] == "" && (k == "ObsHost" || k == "ObsPort" || k == "OverlayPort")) s.Remove(k); else s[k] = b[k]; }
            foreach (var k in Secret) if (b[k] != null && !string.IsNullOrEmpty((string)b[k])) s[k] = b[k];   // empty = keep
            Save(s); return new JObject { { "ok", true }, { "note", "Saved. Restart the PinguinoHost module in the Suite to apply." } };
        }

        // A bot signs in as its OWN Twitch account: its token goes to bots_secrets.json[role] (the Router's helix sender) and bots.json learns the account name.
        static JObject BotTokenIn(JObject b, string role)
        {
            string tok = (string)b["token"]; var s = Load(); string cid = (string)s["ClientId"];
            string ch = ((string)s["Channel"] ?? "").Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid)) return new JObject { { "ok", false }, { "error", "missing token or ClientId" } };
            if (ch == "") return new JObject { { "ok", false }, { "error", "set the Channel first (setup card), then sign the bot in" } };
            using (var http = new HttpClient())
            {
                JArray Get(string path)
                {
                    var rq = new HttpRequestMessage(HttpMethod.Get, Helix + path);
                    rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                    var r = http.SendAsync(rq).Result;
                    return r.IsSuccessStatusCode ? JObject.Parse(r.Content.ReadAsStringAsync().Result)["data"] as JArray : null;
                }
                var me = Get("/users"); if (me == null || me.Count == 0) return new JObject { { "ok", false }, { "error", "Twitch rejected the token" } };
                var chan = Get("/users?login=" + Uri.EscapeDataString(ch)); if (chan == null || chan.Count == 0) return new JObject { { "ok", false }, { "error", "channel " + ch + " not found" } };
                string login = (string)me[0]["login"];
                var sec = LoadFile("bots_secrets.json");
                sec[role] = new JObject { { "ClientId", cid }, { "UserToken", tok }, { "SenderId", me[0]["id"] }, { "BroadcasterId", chan[0]["id"] }, { "Login", login } };
                SaveFile("bots_secrets.json", sec); Vault.TrySet("BOTS_SECRETS." + role + ".UserToken", tok);
                var reg = LoadFile("bots.json");
                string expect = ((string)reg["Bots"]?[role]?["Account"] ?? "").ToLowerInvariant();
                if (reg["Bots"]?[role] != null) { reg["Bots"][role]["Account"] = login; reg["Bots"][role]["Sender"] = "helix"; SaveFile("bots.json", reg); }
                return new JObject { { "ok", true }, { "login", login }, { "note", role + " now chats as " + login + "." + (expect != "" && expect != login.ToLowerInvariant() ? " WARNING: this bot is meant to be " + expect + ". If that is wrong, sign in again as " + expect + "." : "") } };
            }
        }

        // OAuth callback hands us the token; resolve the account so the user types nothing else.
        static JObject TokenIn(JObject b)
        {
            string role = ((string)b["role"] ?? "").Trim().ToLowerInvariant();
            if (role == "core" || role == "chat" || role == "helper") return BotTokenIn(b, role);
            string tok = (string)b["token"]; var s = Load(); string cid = (string)s["ClientId"];
            if (string.IsNullOrEmpty(tok) || string.IsNullOrEmpty(cid)) return new JObject { { "ok", false }, { "error", "missing token or ClientId" } };
            using (var http = new HttpClient())
            {
                var rq = new HttpRequestMessage(HttpMethod.Get, Helix + "/users");
                rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                var resp = http.SendAsync(rq).Result;
                if (!resp.IsSuccessStatusCode) return new JObject { { "ok", false }, { "error", "Twitch rejected the token (" + (int)resp.StatusCode + ")" } };
                var u = (JObject.Parse(resp.Content.ReadAsStringAsync().Result)["data"] as JArray)[0];
                s["UserToken"] = tok; s["SenderId"] = u["id"]; s["BroadcasterId"] = u["id"];
                string ch = ((string)s["Channel"] ?? "").Trim().ToLowerInvariant();
                if (ch == "") s["Channel"] = u["login"];
                else if (ch != (string)u["login"])
                {   // signed in as a different account (the bot): it speaks, but the channel and its events stay the streamer's
                    var rq2 = new HttpRequestMessage(HttpMethod.Get, Helix + "/users?login=" + Uri.EscapeDataString(ch));
                    rq2.Headers.Add("Authorization", "Bearer " + tok); rq2.Headers.Add("Client-Id", cid);
                    var r2 = http.SendAsync(rq2).Result;
                    var d2 = r2.IsSuccessStatusCode ? JObject.Parse(r2.Content.ReadAsStringAsync().Result)["data"] as JArray : null;
                    if (d2 != null && d2.Count > 0) s["BroadcasterId"] = d2[0]["id"];
                }
                Save(s); Vault.TrySet("HOST_SECRETS.UserToken", tok); return new JObject { { "ok", true }, { "login", u["login"] }, { "note", "Signed in as " + u["login"] + ". Restart the PinguinoHost module to apply." } };
            }
        }

        static JObject Body(HttpListenerContext c) { using (var r = new StreamReader(c.Request.InputStream, Encoding.UTF8)) { var t = r.ReadToEnd(); return t == "" ? new JObject() : JObject.Parse(t); } }
        static void Write(HttpListenerContext c, string text, string type) { c.Response.ContentType = type; c.Response.Headers["Cache-Control"] = "no-store"; c.Response.Headers["Content-Security-Policy"] = "frame-ancestors 'self' tauri://localhost http://tauri.localhost https://tauri.localhost http://127.0.0.1:* http://localhost:*"; var b = Encoding.UTF8.GetBytes(text); c.Response.OutputStream.Write(b, 0, b.Length); }

        const string Html = @"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>PinguinoHost</title>
<style>:root{color-scheme:dark;--bg:#050505;--bg2:#0a0a0b;--panel:#101012;--panel2:#17171a;--line:#232326;--line2:#34343a;--fg:#f2f0ec;--dim:#a39f98;--faint:#85827b;--accent:#ff9900;--accent-hover:#ffad33;--accent-active:#e68a00;--accent-soft:#ff990022;--accent-line:#ff990066;--on-accent:#140b00;--focus:#ffc266;--ok:#3ddc97;--warn:#e8d44d;--bad:#ff5c5c;--live:#ff4d4f;--info:#9fb4c7;--r:14px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px 'Segoe UI',system-ui,sans-serif}
main{max-width:1060px;margin:0 auto;padding:18px 16px}h1{font-size:20px;margin:0 0 2px}h2{font-size:15px;margin:0 0 10px}.sub{color:var(--dim);font-size:12.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:16px}
.head{display:flex;align-items:center;gap:10px;margin-bottom:8px}.head b{flex:1;font-size:15px}
.sw{position:relative;width:42px;height:24px;flex:none}.sw input{opacity:0;width:100%;height:100%;margin:0;position:absolute;cursor:pointer;z-index:1}
.sw i{position:absolute;inset:0;background:var(--line2);border-radius:99px;transition:.15s}.sw i:after{content:'';position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:var(--fg);transition:.15s}
.sw input:checked+i{background:var(--ok)}.sw input:checked+i:after{left:21px;background:#06130e}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;margin:2px 4px 2px 0;background:var(--panel2);border:1px solid var(--line)}
.on{color:var(--ok);border-color:rgba(76,217,160,.35)}.off{color:var(--live);border-color:rgba(255,71,87,.35)}
.set{margin:12px 0 0}.set label{display:flex;justify-content:space-between;color:var(--dim);font-size:12.5px;gap:8px}.set label span:last-child{color:var(--fg);font-variant-numeric:tabular-nums}
input[type=range]{width:100%;accent-color:var(--accent);margin:6px 0 0}.chk{display:flex;gap:8px;align-items:center;margin-top:12px;color:var(--dim);font-size:12.5px}
.err{margin-top:10px;padding:8px 10px;border-radius:10px;background:rgba(255,71,87,.1);border:1px solid rgba(255,71,87,.3);color:#ffb3ba;font-size:12px;word-break:break-word}
.row{display:flex;gap:8px;align-items:center;margin:6px 0;flex-wrap:wrap}.row>label{width:150px;color:var(--dim);flex:none}
input[type=text],input[type=password]{flex:1;min-width:120px;background:var(--bg2);color:var(--fg);border:1px solid var(--line2);border-radius:10px;padding:8px}
button{background:var(--accent);color:var(--on-accent);border:0;border-radius:10px;padding:9px 14px;font-weight:600;cursor:pointer}button:hover{background:var(--accent-hover)}
small{color:var(--dim)}#msg{min-height:18px;color:var(--ok);margin-top:6px}code{background:var(--bg2);padding:2px 6px;border-radius:6px;word-break:break-all}
details{margin:14px 0}summary{cursor:pointer;color:var(--accent);font-weight:600;padding:6px 0}
@media(max-width:560px){.row>label{width:100%}}</style><link rel=stylesheet href=http://127.0.0.1:8760/theme.css></head><body><main>
<h1>PinguinoHost</h1><div class=sub>Runs the Pinguino bots without Streamer.bot. Only reachable from this PC.</div>
<div class=sub style='margin-top:6px'><a id=autolink href=/automations style='color:var(--accent);font-weight:600'>Actions &amp; Events &rarr;</a> build chat commands, alerts, timers and OBS actions</div>
<div class=card style='margin-top:14px'><div id=st>loading...</div></div>
<div class=grid id=bots></div>
<div class=sub id=botnote></div>
<details id=setup><summary>Twitch and OBS setup</summary>
<div class=grid>
<div class=card><h2>1. Twitch sign-in</h2><p class=sub>Create an app at dev.twitch.tv/console, add redirect URL <code id=redir></code>, paste its Client ID, then sign in. You will leave this page for Twitch and come back.</p>
<div class=row><label>Client ID</label><input type=text id=ClientId></div>
<div class=row><small>Streamer sign-in now lives in the Suite: <b>Accounts</b>.</small><small id=tokstate></small></div></div>
<div class=card><h2>2. Channel and OBS</h2>
<div class=row><label>Channel</label><input type=text id=Channel placeholder='your login name'></div>
<div class=row><label>OBS host</label><input type=text id=ObsHost placeholder=127.0.0.1></div>
<div class=row><label>OBS port</label><input type=text id=ObsPort placeholder=4455></div>
<div class=row><label>OBS password</label><input type=password id=ObsPassword placeholder='(unchanged)'></div>
<div class=row><label>Sender / Broadcaster ID</label><input type=text id=SenderId><input type=text id=BroadcasterId></div>
<div class=row><button onclick=save()>Save</button><small>Secrets are never shown again.</small></div><div id=msg></div></div>
</div></details>
<script>
const $=id=>document.getElementById(id);const F=['ClientId','Channel','ObsHost','ObsPort','SenderId','BroadcasterId'];let CFG={},BOTS=null,busy=0,TESTRES={};
const TOK=new URLSearchParams(location.search).get('token')||'';
$('autolink').href='/automations'+(TOK?'?token='+encodeURIComponent(TOK):'');
const H=()=>TOK?{'X-Pinguino-Token':TOK}:{};
async function j(u,o){o=o||{};o.headers=Object.assign(H(),o.headers||{});return (await fetch(u,o)).json()}
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function load(){CFG=await j('/api/config');F.forEach(k=>$(k).value=CFG[k]||'');$('redir').textContent=CFG.redirect;$('tokstate').textContent=CFG.hasUserToken?'token saved':'not signed in';if(!CFG.hasUserToken)$('setup').open=true}
async function status(){const s=await j('/api/status');let sm=null;try{sm=await j('/api/summary')}catch(e){}const p=(n,v)=>`<span class='pill ${v?'on':'off'}'>${n}: ${v?'on':'off'}</span>`;
$('st').innerHTML=p('chat #'+(s.channel||'?'),s.chatConnected)+p('can reply',s.canSend)+p('events',s.eventSubConnected)+p('OBS',s.obsConnected)+(sm&&sm.chat?`<br><small>${sm.chat.messagesLastMinute}/min - ${sm.chat.chatters5} chatting - ${sm.chat.modsActive30} mods active${sm.lease&&sm.lease.state!='none'?' - lease: '+sm.lease.state:''}</small>`:'')+`<br><small>${s.messages} messages${s.lastMessageAgoSec!=null?', last '+s.lastMessageAgoSec+' s ago':''} - up ${s.uptimeSec}s${s.sim?' - SIM':''}</small>`}
function ago(s){return s<90?s+' s':s<5400?Math.round(s/60)+' min':Math.round(s/3600)+' h'}
function fmt(d,v){return d.step<1?(v*100).toFixed(2)+'%':v}
function draw(){const g=$('bots');g.innerHTML='';BOTS.bots.forEach(b=>{const c=document.createElement('div');c.className='card';
let h=`<div class=head><b>${esc(b.title)}</b><span class='pill ${b.enabled?'on':'off'}'>${b.enabled?'on':'off'}</span><label class=sw><input type=checkbox ${b.enabled?'checked':''} data-id=${b.id}><i></i></label></div>
<div class=sub>Speaks as: <b>${b.sender=='helix'&&b.account?esc(b.account):'(shared account)'}</b> <button data-signin=${b.id}>${b.sender=='helix'?'Change account':'Sign in as '+(b.account?esc(b.account):'this bot')}</button></div>
<div class=sub><button data-test=${b.id}>Send test</button> <span id=t_${b.id}>${esc(TESTRES[b.id]||'')}</span></div>
<div class=sub>Login: ${b.signedIn?'signed in as <b>'+esc(b.signedInAs)+'</b>':'not signed in'} <span class='pill ${b.health=='pass'?'on':'off'}'>${esc(b.health)}</span> ${esc(b.healthDetail||'')}</div>
<details><summary>Commands (${b.commands.length})</summary><div class=sub>${b.commands.map(esc).join(' - ')}</div></details>
<div class=sub>${b.runs} runs${b.lastRunAgoSec!=null?', last '+ago(b.lastRunAgoSec)+' ago':', not run yet'}</div>`;
b.settings.forEach(s=>{if(s.type=='bool')h+=`<div class=chk><input type=checkbox ${s.value?'checked':''} data-id=${b.id} data-k=${s.key}> ${esc(s.label)}</div>`;
else if(s.type=='text')h+=`<div class=set><label><span>${esc(s.label)}</span></label><input type=text value='${esc(s.value).replace(/'/g,'&#39;')}' placeholder='${esc(s.hint).replace(/'/g,'&#39;')}' data-id=${b.id} data-k=${s.key} title='${esc(s.hint)}' style='width:100%'></div>`;
else h+=`<div class=set><label><span>${esc(s.label)}</span><span id=v_${b.id}_${s.key}>${fmt(s,s.value)}</span></label><input type=range min=${s.min} max=${s.max} step=${s.step} value=${s.value} data-id=${b.id} data-k=${s.key} title='${esc(s.hint)}'></div>`});
if(b.lastError)h+=`<div class=err>${esc(b.lastError)} <small>(${ago(b.lastErrorAgoSec)} ago)</small></div>`;
c.innerHTML=h;g.appendChild(c)});
g.querySelectorAll('button[data-test]').forEach(x=>x.onclick=async()=>{const k=x.dataset.test;TESTRES[k]='sending...';$('t_'+k).textContent=TESTRES[k];const r=await j('/api/bottest',{method:'POST',body:JSON.stringify({id:k})});TESTRES[k]=r.ok?'OK: '+r.note:'Failed: '+r.error;$('t_'+k).textContent=TESTRES[k]});
g.querySelectorAll('button[data-signin]').forEach(x=>x.onclick=()=>signin(x.dataset.signin));
g.querySelectorAll('input').forEach(i=>{
 if(i.type=='text')i.oninput=()=>{busy=Date.now()+55000};
 if(i.type=='range')i.oninput=()=>{busy=Date.now();const d=BOTS.bots.find(b=>b.id==i.dataset.id).settings.find(s=>s.key==i.dataset.k);$('v_'+i.dataset.id+'_'+i.dataset.k).textContent=fmt(d,+i.value)};
 i.onchange=async()=>{busy=Date.now();const b={id:i.dataset.id};if(i.dataset.k){b.settings={};b.settings[i.dataset.k]=i.type=='range'?+i.value:i.type=='text'?i.value:i.checked}else b.enabled=i.checked;
  const r=await j('/api/bots',{method:'POST',body:JSON.stringify(b)});if(!r.ok)alert(r.error);busy=0;bots(true)}})}
async function bots(force){if(!force&&Date.now()-busy<4000)return;BOTS=await j('/api/bots');$('botnote').textContent=BOTS.routerError?'Router: '+BOTS.routerError:BOTS.note;draw()}
async function save(){const b={};F.forEach(k=>b[k]=$(k).value);b.ObsPassword=$('ObsPassword').value;const r=await j('/api/config',{method:'POST',body:JSON.stringify(b)});$('msg').textContent=r.note||r.error;$('ObsPassword').value='';load()}
async function signin(role){await save();const r=await j('/api/signin',{method:'POST',body:JSON.stringify({role:role||''})});$('botnote').textContent=$('msg').textContent=r.ok?'Finish signing in in the browser window that just opened; this card updates by itself.':(r.error||'Could not open the browser.')}
async function callback(){const h=new URLSearchParams(location.hash.slice(1));const t=h.get('access_token');if(!t)return;history.replaceState(null,'','/setup');
const r=await j('/api/token',{method:'POST',body:JSON.stringify({token:t,role:h.get('state')||''})});document.body.innerHTML=r.ok?'<main><h1>Signed in'+(r.login?' as '+esc(r.login):'')+'</h1>'+(r.note&&r.note.indexOf('WARNING')>=0?'<p class=sub style=color:#ffb3ba>'+esc(r.note)+'</p>':'')+'<p class=sub>You can close this tab and return to PinguinoSuite.</p></main>':'<main><h1>Sign-in failed</h1><p class=sub>'+esc(r.error||'unknown error')+'</p><p class=sub>Close this tab, then try again from PinguinoSuite.</p></main>'}
async function tokpoll(){try{const c=await j('/api/config');$('tokstate').textContent=c.hasUserToken?'token saved':'not signed in'}catch(e){}}
if(location.hash.indexOf('access_token')>=0){callback()}else{load();setInterval(tokpoll,3000);status();bots(true);setInterval(status,3000);setInterval(()=>bots(false),5000)}
//bots(true);setInterval(status,3000);setInterval(()=>bots(false),5000);
</script></main></body></html>";
    }
}
