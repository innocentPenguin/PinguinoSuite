using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Keeps two live files for the profile push (Pipeline\push-profiles.mjs merges them into every profile):
    ///   Data\subs\live_subs.json  the ACTIVE subscribers straight from Twitch (Helix GET /subscriptions, paged): login, id, tier, gift/prime, gifter. Refreshed every 10 min and right after a sub/resub/gift event.
    ///   Data\avatars.json         profile pictures for every profile login (Helix GET /users by login, and by id for renamed accounts), alias/nickname fallback, last good url kept when a lookup fails.
    ///   Data\profile_bots.json    every login the site must flag isBot.
    /// Audit output: Data\subs\sub_audit.json and Data\avatar_report.json, plus a log line "active subs per Twitch X, per profiles Y, missing Z".</summary>
    public static class ProfileSync
    {
        static readonly object L = new object();
        static bool _started; static volatile bool _subsNow; static long _subsDue;
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? Path.GetDirectoryName(d) : d; } }
        static string ProfDir { get { return Path.Combine(Root, "profiles"); } }
        static string LiveP { get { return Path.Combine(Root, "subs", "live_subs.json"); } }
        static string AuditP { get { return Path.Combine(Root, "subs", "sub_audit.json"); } }
        static string AvaP { get { return Path.Combine(Root, "avatars.json"); } }
        static string AvaRepP { get { return Path.Combine(Root, "avatar_report.json"); } }
        static string BotsP { get { return Path.Combine(Root, "profile_bots.json"); } }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        static bool Fast { get { return Environment.GetEnvironmentVariable("PINGUINO_PROFILESYNC_FAST") == "1"; } }
        public static string LastSubNote = "not run yet", LastAvatarNote = "not run yet";

        static void SaveJson(string path, JToken j) { try { Directory.CreateDirectory(Path.GetDirectoryName(path)); string tmp = path + ".tmp"; File.WriteAllText(tmp, j.ToString(), new UTF8Encoding(false)); if (File.Exists(path)) File.Delete(path); File.Move(tmp, path); } catch (Exception ex) { Clog.Warn("profilesync", "could not save " + Path.GetFileName(path) + ": " + ex.Message); } }
        static JObject LoadObj(string path) { try { if (File.Exists(path)) return JObject.Parse(File.ReadAllText(path, Encoding.UTF8)); } catch (Exception) { } return new JObject(); }

        public static void Start()
        {
            if (_started) return; _started = true;
            new Thread(() =>
            {
                Thread.Sleep(Fast ? 500 : 20000); long nextAva = 0, nextSubs = 0;
                while (true)
                {
                    try
                    {
                        if (Lease.MayRun)
                        {
                            long now = Now();
                            if (_subsNow ? now >= _subsDue : now >= nextSubs) { _subsNow = false; SyncSubs(); nextSubs = now + (Fast ? 3 : 600); }
                            if (now >= nextAva) { SyncAvatars(); WriteBots(); nextAva = now + (Fast ? 4 : 600); }
                        }
                    }
                    catch (Exception ex) { Clog.Warn("profilesync", "tick: " + ex.Message); }
                    Thread.Sleep(Fast ? 300 : 3000);
                }
            }) { IsBackground = true }.Start();
        }

        /// <summary>a sub, resub or gift just happened: refresh the active list soon (debounced).</summary>
        public static void OnEvent(Dictionary<string, object> args)
        {
            object et; if (!args.TryGetValue("eventType", out et)) return;
            string t = Convert.ToString(et) ?? ""; if (t.IndexOf("Sub", StringComparison.OrdinalIgnoreCase) < 0 && t.IndexOf("Gift", StringComparison.OrdinalIgnoreCase) < 0) return;
            _subsDue = Now() + (Fast ? 1 : 20); _subsNow = true;
        }

        // ---- Helix with paging (TwitchApi.Call drops the cursor) ----
        static bool Get(string pathAndQuery, out JObject j, out string err)
        {
            j = null; err = ""; var s = HostApi.StreamerCreds();
            string tok = (string)s["UserToken"] ?? "", cid = (string)s["ClientId"] ?? "", bid = (string)s["BroadcasterId"] ?? "";
            if (tok == "" || cid == "" || bid == "") { err = "the streamer account is not signed in"; return false; }
            try
            {
                using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(15) })
                {
                    var rq = new HttpRequestMessage(HttpMethod.Get, HostApi.Helix + pathAndQuery.Replace("{bid}", bid));
                    rq.Headers.Add("Authorization", "Bearer " + tok); rq.Headers.Add("Client-Id", cid);
                    var r = h.SendAsync(rq).Result; string txt = r.Content.ReadAsStringAsync().Result;
                    if (!r.IsSuccessStatusCode) { int c = (int)r.StatusCode; err = "HTTP " + c + (c == 401 || c == 403 ? " (sign the streamer in again: channel:read:subscriptions)" : ""); return false; }
                    j = JObject.Parse(txt); return true;
                }
            }
            catch (Exception ex) { err = ex.Message; return false; }
        }

        // ---- active subscribers ----
        public static JObject SyncSubs()
        {
            var live = new JObject(); string after = "", err = ""; string bid = TwitchApi.BroadcasterId(); int pages = 0;
            for (; pages < 60; pages++)
            {
                JObject j; if (!Get("/subscriptions?broadcaster_id={bid}&first=100" + (after == "" ? "" : "&after=" + Uri.EscapeDataString(after)), out j, out err)) break;
                foreach (var x in j["data"] as JArray ?? new JArray())
                {
                    string id = (string)x["user_id"] ?? "", login = ((string)x["user_login"] ?? "").ToLowerInvariant(); if (login == "" || id == bid) continue;
                    string t = (string)x["tier"] ?? "1000"; int tier = t == "3000" ? 3 : t == "2000" ? 2 : 1;
                    bool gift = (bool?)x["is_gift"] == true; string plan = (string)x["plan_name"] ?? "";
                    live[login] = new JObject { { "id", id }, { "name", (string)x["user_name"] ?? login }, { "tier", tier }, { "isGift", gift }, { "gifter", ((string)x["gifter_login"] ?? "").ToLowerInvariant() }, { "prime", plan.IndexOf("Prime", StringComparison.OrdinalIgnoreCase) >= 0 } };
                }
                after = (string)j["pagination"]?["cursor"] ?? ""; if (after == "") { err = ""; break; }
            }
            if (err != "") { LastSubNote = "Twitch sub list unavailable: " + err + " (kept the last good list)"; Clog.Warn("profilesync", LastSubNote); return new JObject { { "ok", false }, { "error", err } }; }
            // audit against the profiles as they are now
            var prof = new Dictionary<string, JObject>(); var alias = Boards.AliasMap(); int profSub = 0; var mismatches = new JArray();
            try { if (Directory.Exists(ProfDir)) foreach (var f in Directory.GetFiles(ProfDir, "*.json")) { string lg = Path.GetFileNameWithoutExtension(f).ToLowerInvariant(); if (lg == "index") continue; try { var p = JObject.Parse(File.ReadAllText(f, Encoding.UTF8)); prof[lg] = p; if ((bool?)p["roles"]?["sub"] == true && (bool?)p["roles"]?["lapsed"] != true) profSub++; } catch (Exception) { } } } catch (Exception) { }
            int missing = 0;
            foreach (var kv in live.Properties())
            {
                string lg = kv.Name; JObject p; string reason = "";
                string canon = alias.ContainsKey(lg) ? alias[lg] : lg;
                if (!prof.TryGetValue(lg, out p)) reason = prof.ContainsKey(canon) && canon != lg ? "no profile under this login (alias of " + canon + ")" : "no profile";
                else if ((bool?)p["roles"]?["sub"] != true) reason = (bool?)p["roles"]?["lapsed"] == true ? "profile marked lapsed (stale csv import)" : "profile says not subbed";
                if (reason != "") { missing++; mismatches.Add(new JObject { { "login", lg }, { "reason", reason }, { "isGift", kv.Value["isGift"] }, { "tier", kv.Value["tier"] } }); }
            }
            var stale = new JArray(prof.Where(kv => (bool?)kv.Value["roles"]?["sub"] == true && (bool?)kv.Value["roles"]?["lapsed"] != true && !live.ContainsKey(kv.Key)).Select(kv => (JToken)kv.Key));
            long now = Now();
            SaveJson(LiveP, new JObject { { "version", 1 }, { "at", now }, { "count", live.Count }, { "users", live } });
            SaveJson(AuditP, new JObject { { "at", now }, { "twitch", live.Count }, { "profiles", profSub }, { "missing", missing }, { "missingLogins", mismatches }, { "profilesSubbedButNotOnTwitch", stale } });
            LastSubNote = "active subs per Twitch " + live.Count + ", per profiles " + profSub + ", missing " + missing;
            Clog.Info("profilesync", LastSubNote + (stale.Count > 0 ? "; " + stale.Count + " profiles still say subbed but Twitch has no active sub" : ""));
            return new JObject { { "ok", true }, { "twitch", live.Count }, { "profiles", profSub }, { "missing", missing } };
        }

        // ---- avatars ----
        public static JObject SyncAvatars()
        {
            var ava = LoadObj(AvaP); var alias = Boards.AliasMap(); long now = Now();
            var logins = new HashSet<string>(); var nick = new Dictionary<string, string>();
            try
            {
                if (Directory.Exists(ProfDir)) foreach (var f in Directory.GetFiles(ProfDir, "*.json"))
                {
                    string lg = Path.GetFileNameWithoutExtension(f).ToLowerInvariant(); if (lg == "index") continue; logins.Add(lg);
                    try { var p = JObject.Parse(File.ReadAllText(f, Encoding.UTF8)); foreach (var n in p["nicknames"] as JArray ?? new JArray()) { string nn = ((string)n ?? "").ToLowerInvariant(); if (nn != "" && !nick.ContainsKey(nn)) nick[nn] = lg; } } catch (Exception) { }
                }
            }
            catch (Exception) { }
            foreach (var kv in alias) { logins.Add(kv.Key); logins.Add(kv.Value); }
            var live = LoadObj(LiveP)["users"] as JObject; if (live != null) foreach (var kv in live.Properties()) logins.Add(kv.Name);
            // due: never looked up, or the last look is older than a day (a missing one is retried every day too)
            long maxAge = Fast ? 3 : 86400; var due = logins.Where(l => ava[l] == null || now - ((long?)ava[l]["checkedAt"] ?? 0) > maxAge).OrderBy(l => ava[l] == null ? 0 : 1).ToList();
            int looked = 0, fails = 0; string err = "";
            for (int i = 0; i < due.Count && err == ""; i += 100)
            {
                var batch = due.Skip(i).Take(100).ToList(); JObject j;
                if (!Get("/users?" + string.Join("&", batch.Select(l => "login=" + Uri.EscapeDataString(l))), out j, out err)) { fails++; break; }
                var found = new HashSet<string>();
                foreach (var u in j["data"] as JArray ?? new JArray())
                {
                    string lg = ((string)u["login"] ?? "").ToLowerInvariant(); if (lg == "") continue; found.Add(lg);
                    ava[lg] = new JObject { { "url", (string)u["profile_image_url"] ?? "" }, { "id", (string)u["id"] ?? "" }, { "name", (string)u["display_name"] ?? lg }, { "status", "ok" }, { "source", "twitch" }, { "checkedAt", now } };
                    looked++;
                }
                foreach (var l in batch.Where(l => !found.Contains(l)))
                {
                    var old = ava[l] as JObject ?? new JObject();   // keep the last good url; just note the miss
                    old["status"] = "gone"; old["checkedAt"] = now; old["note"] = "not found on Twitch by login (renamed, banned or deleted)"; ava[l] = old;
                }
            }
            // renamed accounts: ask by id for the ones we know an id for but the login no longer exists
            if (err == "")
            {
                var byId = ava.Properties().Where(p => (string)p.Value["status"] == "gone" && ((string)p.Value["id"] ?? "") != "" && (long?)p.Value["idCheckedAt"] == null).Take(100).ToList();
                if (byId.Count > 0)
                {
                    JObject j; if (Get("/users?" + string.Join("&", byId.Select(p => "id=" + Uri.EscapeDataString((string)p.Value["id"]))), out j, out err))
                    {
                        var byIdMap = new Dictionary<string, JObject>(); foreach (var u in j["data"] as JArray ?? new JArray()) byIdMap[(string)u["id"] ?? ""] = (JObject)u;
                        foreach (var p in byId)
                        {
                            var o = (JObject)p.Value; o["idCheckedAt"] = now; JObject u;
                            if (byIdMap.TryGetValue((string)o["id"], out u)) { o["url"] = (string)u["profile_image_url"] ?? (string)o["url"]; o["status"] = "ok"; o["source"] = "twitch (by id)"; o["renamedTo"] = ((string)u["login"] ?? "").ToLowerInvariant(); o["note"] = "account renamed"; }
                        }
                    }
                }
            }
            // fallbacks for what is still without a picture: the alias main account, the nickname owner
            int viaAlias = 0;
            foreach (var l in logins)
            {
                var e = ava[l] as JObject; if (e != null && ((string)e["url"] ?? "") != "") continue;
                string from = alias.ContainsKey(l) ? alias[l] : (nick.ContainsKey(l) ? nick[l] : "");
                var src = from != "" ? ava[from] as JObject : null;
                if (src != null && ((string)src["url"] ?? "") != "") { if (e == null) { e = new JObject(); ava[l] = e; } e["url"] = (string)src["url"]; e["status"] = "via"; e["source"] = (alias.ContainsKey(l) ? "alias of " : "nickname of ") + from; e["checkedAt"] = (long?)e["checkedAt"] ?? now; viaAlias++; }
            }
            if (err == "" || looked > 0 || due.Count == 0) SaveJson(AvaP, ava);
            var missing = new JArray(logins.Where(l => ((string)ava[l]?["url"] ?? "") == "").OrderBy(l => l).Select(l => (JToken)new JObject { { "login", l }, { "reason", ava[l] == null ? (err != "" ? "not looked up yet: " + err : "not looked up yet") : ((string)ava[l]["note"] ?? "no picture") } }));
            int with = logins.Count - missing.Count;
            SaveJson(AvaRepP, new JObject { { "at", now }, { "profilesTotal", logins.Count }, { "withAvatar", with }, { "stillMissing", missing.Count }, { "viaAliasOrNickname", viaAlias }, { "missing", missing } });
            LastAvatarNote = "avatars: " + logins.Count + " logins, " + with + " with a picture, " + missing.Count + " missing" + (err != "" ? " (" + err + ")" : "");
            if (looked > 0 || missing.Count > 0) Clog.Info("profilesync", LastAvatarNote);
            return new JObject { { "ok", err == "" }, { "total", logins.Count }, { "withAvatar", with }, { "missing", missing.Count } };
        }

        static void WriteBots()
        {
            var bots = Boards.AllBots();
            try { if (Directory.Exists(ProfDir)) foreach (var f in Directory.GetFiles(ProfDir, "*.json")) { string lg = Path.GetFileNameWithoutExtension(f).ToLowerInvariant(); if (lg != "index" && Boards.IsBot(lg)) bots.Add(lg); } } catch (Exception) { }
            string ch = ""; try { ch = (HostApi.StreamerCreds()["Channel"] ?? "").ToString().ToLowerInvariant(); } catch (Exception) { }
            bots.Remove(ch); bots.Remove("innocentpenguin_");
            SaveJson(BotsP, new JObject { { "at", Now() }, { "bots", new JArray(bots.OrderBy(x => x, StringComparer.Ordinal)) } });
        }

        public static JObject Api()
        {
            var live = LoadObj(LiveP); var rep = LoadObj(AvaRepP); var aud = LoadObj(AuditP);
            return new JObject { { "ok", true }, { "subs", LastSubNote }, { "avatars", LastAvatarNote }, { "liveSubsAt", live["at"] }, { "audit", aud }, { "avatarReport", new JObject { { "profilesTotal", rep["profilesTotal"] }, { "withAvatar", rep["withAvatar"] }, { "stillMissing", rep["stillMissing"] }, { "missing", rep["missing"] } } } };
        }
        public static JObject Post(JObject b)
        {
            var r = new JObject { { "ok", true } };
            r["subs"] = SyncSubs(); if (b != null && (bool?)b["avatars"] != false) { r["avatars"] = SyncAvatars(); WriteBots(); }
            return r;
        }
    }
}
