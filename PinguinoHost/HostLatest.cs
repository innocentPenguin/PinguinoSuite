using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The "latest" feed (replaces the third-party latest widget): every follow, sub, resub, gift, cheer, raid and channel point redeem is kept, so an OBS browser source
    /// (<c>http://127.0.0.1:8770/overlay/latest</c>) and the !latest command can show the newest of each. Optionally also writes the newest line into an OBS text source.
    /// Store: Data\runtime\latest.json. Settings: latest_settings.json { "TextSource": "" (an OBS text source to keep updated), "Kinds": "follow,sub,cheer,raid" }.</summary>
    public static class Latest
    {
        static readonly object L = new object(); static JArray _items; static DateTime _t;
        static string Path_ { get { return System.IO.Path.Combine(HostApi.DataDir, "latest.json"); } }
        static JArray Items()
        {
            lock (L)
            {
                if (_items == null) { try { _items = File.Exists(Path_) ? JArray.Parse(File.ReadAllText(Path_)) : new JArray(); } catch (Exception) { _items = new JArray(); } }
                return _items;
            }
        }
        /// <summary>Ivan's look for the overlay and feed (edit latest_settings.json; the OBS page URL can still override each one: ?color=ff9900&amp;size=64 ...).</summary>
        public static JObject Settings()
        {
            var d = new JObject {
                { "Types", "follow,sub,cheer,raid" }, { "Color", "ff9900" }, { "TextColor", "ffffff" }, { "Size", 64 }, { "Font", "bahnschrift" }, { "Rotate", 5 }, { "Bold", true }, { "Shadow", true }, { "ShowDetail", true },
                { "Align", "center" }, { "Labels", new JObject { { "follow", "follower" }, { "sub", "sub" }, { "resub", "resub" }, { "gift", "gifter" }, { "cheer", "cheer" }, { "raid", "raid" }, { "redeem", "redeem" } } },
                { "TextSource", "" }, { "ForwardToSite", false }, { "SiteEventsUrl", "https://innocentpenguin.com/api/bot/events" } };
            try
            {
                var f = System.IO.Path.Combine(HostApi.DataDir, "latest_settings.json");
                if (File.Exists(f)) { foreach (var p in JObject.Parse(File.ReadAllText(f))) { if (p.Key == "Labels" && p.Value is JObject lo) foreach (var l in lo) d["Labels"][l.Key] = l.Value; else d[p.Key] = p.Value; } }
                else File.WriteAllText(f, d.ToString());
            }
            catch (Exception) { }
            return d;
        }

        static long _seq = -1;
        /// <summary>called for every Twitch event (Auto.OnEvent) and by the clip / shoutout steps: kind = follow|sub|resub|gift|cheer|raid|redeem|ban|clip|shoutout.</summary>
        public static void Record(string kind, Dictionary<string, string> ctx)
        {
            if (!new[] { "follow", "sub", "resub", "gift", "cheer", "raid", "redeem", "ban", "unban", "mod", "unmod", "clip", "replay", "first5", "shoutout", "raid_out", "poll", "prediction", "hype", "streak" }.Contains(kind)) return;
            Func<string, string> g = k => ctx.ContainsKey(k) ? ctx[k] : "";
            if ((kind == "poll" || kind == "prediction" || kind == "hype") && g("state") == "progress") return;   // only begin / lock / end go in the feed (progress would flood it)
            string who = g("user") != "" ? g("user") : g("userName"), what = ""; int amount = 0, tier = 0; string message = "";
            int.TryParse(g("tier"), out tier);
            switch (kind)
            {
                case "sub": case "resub": what = "tier " + (tier == 0 ? 1 : tier); break;
                case "gift": int.TryParse(g("total"), out amount); if (amount == 0) amount = 1; what = amount + " sub(s)"; break;
                case "cheer": int.TryParse(g("bits"), out amount); what = amount + " bits"; break;
                case "raid": int.TryParse(g("viewers"), out amount); what = amount + " viewers"; break;
                case "redeem": what = g("title"); message = g("input"); int.TryParse(g("cost"), out amount); break;
                case "ban": what = g("permanent") == "false" ? "timed out" : "banned"; message = g("reason"); break;
                case "unban": what = "unbanned"; break;
                case "mod": what = "modded"; break;
                case "unmod": what = "unmodded"; break;
                case "clip": case "replay": what = g("clip.url"); break;
                case "shoutout": what = g("shoutoutUser"); break;
                case "raid_out": int.TryParse(g("viewers"), out amount); what = g("target"); break;
                case "poll": case "prediction": case "hype": what = kind == "hype" ? "level " + g("x.level") : g("x.title"); break;
                case "streak": int.TryParse(g("count"), out amount); what = amount + " streams"; break;
                case "first5": what = "place " + g("place"); int.TryParse(g("place"), out amount); break;
            }
            if (kind == "cheer") Credits.Add("bits", who, amount); else if (kind == "redeem") Credits.Add("points", who, amount);
            var e = new JObject { { "ts", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "kind", kind }, { "type", kind }, { "user", who }, { "what", what }, { "detail", what } };
            if (kind == "follow") { e["refollow"] = RefollowCheck(who); LastRefollow = (bool)e["refollow"]; }
            if (kind == "gift") { int cum; if (int.TryParse(g("cumulative"), out cum) && cum > 0) e["cumulative"] = cum; if (g("anonymous") == "true") e["anonymous"] = true; }
            if (kind == "raid_out") e["target"] = g("target");
            if (kind == "poll" || kind == "prediction" || kind == "hype")
            {
                e["state"] = g("state"); var data = new JObject();
                foreach (var kv in ctx) if (kv.Key.StartsWith("x.")) { string v = kv.Value ?? ""; JToken jt = null; if (v.StartsWith("[") || v.StartsWith("{")) { try { jt = JToken.Parse(v); } catch (Exception) { } } data[kv.Key.Substring(2)] = jt ?? (JToken)v; }
                e["data"] = data;
            }
            if (amount > 0) e["amount"] = amount; if (tier > 0 && (kind == "sub" || kind == "resub" || kind == "gift")) e["tier"] = tier; if (message != "") e["message"] = message;
            if (g("moderator") != "" && (kind == "ban" || kind == "unban" || kind == "mod" || kind == "unmod")) e["moderator"] = g("moderator");
            lock (L)
            {
                var a = Items(); if (_seq < 0) _seq = a.OfType<JObject>().Select(x => (long?)x["seq"] ?? 0).DefaultIfEmpty(0).Max();
                e["seq"] = ++_seq; a.Add(e); while (a.Count > 500) a.RemoveAt(0);
                try { File.WriteAllText(Path_, a.ToString()); } catch (Exception) { }
            }
            if (kind == "ban" || kind == "unban" || kind == "mod" || kind == "unmod" || kind == "clip" || kind == "replay" || kind == "shoutout" || kind == "first5" || kind == "poll" || kind == "prediction" || kind == "hype" || kind == "raid_out" || kind == "streak") return;   // the overlay text only follows follower/sub/cheer/raid-type events
            try { string ts = (string)Settings()["TextSource"]; if (!string.IsNullOrWhiteSpace(ts)) Program.ObsRaw("SetInputSettings", new JObject { { "inputName", ts }, { "inputSettings", new JObject { { "text", Line(e) } } } }); }
            catch (Exception ex) { Clog.Warn("latest", "could not update the OBS text source: " + ex.Message); }
        }
        // refollow: this login followed before (our own follow log, or the profile has a followingSince date). Persisted in followed.json next to the activity file.
        public static bool LastRefollow;
        static bool RefollowCheck(string login)
        {
            login = (login ?? "").ToLowerInvariant(); if (login == "") return false;
            try
            {
                lock (L)
                {
                    string fp = System.IO.Path.Combine(HostApi.DataDir, "followed.json");
                    var d = File.Exists(fp) ? JObject.Parse(File.ReadAllText(fp)) : new JObject(); var lg = d["logins"] as JObject ?? new JObject(); d["logins"] = lg;
                    bool before = lg[login] != null;
                    if (!before)
                    {
                        string dd = HostApi.DataDir.TrimEnd((char)92, '/'); string root = string.Equals(System.IO.Path.GetFileName(dd), "runtime", StringComparison.OrdinalIgnoreCase) ? System.IO.Path.GetDirectoryName(dd) : dd;
                        string pf = System.IO.Path.Combine(root, "profiles", login + ".json");
                        if (File.Exists(pf)) { try { before = !string.IsNullOrEmpty((string)JObject.Parse(File.ReadAllText(pf).TrimStart((char)0xFEFF))["seen"]?["followingSince"]); } catch (Exception) { } }
                        lg[login] = DateTime.UtcNow.ToString("yyyy-MM-dd");
                        File.WriteAllText(fp, d.ToString());
                    }
                    return before;
                }
            }
            catch (Exception) { return false; }
        }
        /// <summary>GET /api/activity?since=&amp;limit=&amp;type= for the shell's Activity Feed: newest last, only items with seq &gt; since.</summary>
        public static JObject Activity(long since, int limit, string type)
        {
            lock (L)
            {
                var all = Items().OfType<JObject>().Where(x => ((long?)x["seq"] ?? 0) > since && (string.IsNullOrEmpty(type) || type.Split(',').Contains((string)x["type"]))).ToList();
                if (limit <= 0) limit = 100; if (all.Count > limit) all = all.Skip(all.Count - limit).ToList();
                if (_seq < 0) _seq = Items().OfType<JObject>().Select(x => (long?)x["seq"] ?? 0).DefaultIfEmpty(0).Max();
                return new JObject { { "ok", true }, { "seq", _seq }, { "items", new JArray(all) } };
            }
        }
        public static string Label(string kind) { try { var o = Settings()["Labels"]?[kind]; if (o != null && (string)o != "") return (string)o; } catch (Exception) { } return DefaultLabel(kind); }
        static string DefaultLabel(string kind) { switch (kind) { case "follow": return "follower"; case "sub": return "sub"; case "resub": return "resub"; case "gift": return "gifter"; case "cheer": return "cheer"; case "raid": return "raid"; case "ban": return "ban"; case "clip": return "clip"; case "replay": return "replay"; case "first5": return "first-5"; case "shoutout": return "shoutout"; default: return "redeem"; } }
        public static string Line(JObject e) { string what = (string)e["what"] ?? ""; return "Latest " + Label((string)e["kind"]) + ": " + (string)e["user"] + (what != "" ? " (" + what + ")" : ""); }

        /// <summary>newest entry of each kind, newest first.</summary>
        public static List<JObject> Newest(IEnumerable<string> kinds = null)
        {
            lock (L)
            {
                var res = new List<JObject>(); var want = new HashSet<string>(kinds ?? new[] { "follow", "sub", "resub", "gift", "cheer", "raid", "redeem" });
                foreach (var e in Items().OfType<JObject>().Reverse())
                    if ((want == null || want.Contains((string)e["kind"])) && !res.Any(r => (string)r["kind"] == (string)e["kind"])) res.Add(e);
                return res.OrderByDescending(r => (long)r["ts"]).ToList();
            }
        }
        /// <summary>for the !latest command: "Latest follower: a | sub: b | cheer: c (200 bits) | raid: d (30 viewers)"</summary>
        public static string Summary()
        {
            var n = Newest(new[] { "follow", "sub", "resub", "gift", "cheer", "raid" }); if (n.Count == 0) return "Nothing yet this stream.";
            return string.Join(" | ", n.Select(e => Label((string)e["kind"]) + ": " + (string)e["user"] + (((string)e["what"] ?? "") != "" ? " (" + (string)e["what"] + ")" : "")));
        }

        public static JObject Api()
        {
            var all = Newest(); var list = new JArray(all);
            return new JObject { { "ok", true }, { "now", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "latest", list }, { "recent", new JArray(Items().OfType<JObject>().Reverse().Take(20)) }, { "settings", Settings() } };
        }
        public static string PagePath()
        {
            foreach (var d in new[] { System.IO.Path.Combine(AppContext.BaseDirectory, "web"), System.IO.Path.Combine(Program.SuiteDir ?? "", "PinguinoHost", "web") })
            { var f = System.IO.Path.Combine(d, "latest.html"); if (File.Exists(f)) return f; }
            return null;
        }
    }

    /// <summary>Shoutout queue (replaces the StreamUP one): a mod or the raid handler adds a streamer; the worker sends Twitch's own shoutout card (one per 2 minutes, Twitch's limit)
    /// and a chat line with their last game and pronouns (alejo.io, they/them when unknown). The same streamer is not shouted out twice within the dedupe window.
    /// Settings: shout_settings.json. State: shoutouts.json (recent). Spoken by PinguinoB0t.</summary>
    public static class Shout
    {
        class Item { public string User, By; public bool Native; public DateTime At; }
        static readonly Queue<Item> Q = new Queue<Item>(); static readonly object L = new object();
        static readonly Dictionary<string, DateTime> Recent = new Dictionary<string, DateTime>(); static DateTime _lastNative = DateTime.MinValue, _lastPlain = DateTime.MinValue;
        static readonly SemaphoreSlim Sig = new SemaphoreSlim(0); static bool _started; static string _current = "";
        static readonly Dictionary<string, DateTime> NativeRecent = new Dictionary<string, DateTime>();   // login -> when Twitch's own card was last sent for them (Twitch: same target once per 60 min)
        static readonly Dictionary<string, string[]> InfoCache = new Dictionary<string, string[]>();      // login -> {uid, login, name, game}
        static readonly Random Rng = new Random();

        public static JObject Settings()
        {
            var d = new JObject {
                { "Line", "Go and Follow {user}, {subject} {were} last seen streaming {game} you can find {object} at {channel}!!" },
                { "QueuedLine", "Shoutout for {user} has been queued, there are currently {n} people in the queue." },
                { "NotFoundLine", "Sorry {by}, {user} was not found." }, { "DuplicateLine", "{user} was already shouted out recently." },
                { "TempLine", "Shoutout queued, in the meantime please check out {user} at {channel}. Last playing {game}" }, { "TempLineOn", true },
                { "NativeDelayMinSec", 1 }, { "NativeDelayMaxSec", 5 }, { "LineAfterNative", false }, { "NativeSameTargetMinutes", 61 },
                { "DedupeMinutes", 60 }, { "ManualDedupeMinutes", 2 }, { "Native", true }, { "ShoutRaiders", true }, { "NativeGapSec", 125 } };
            try { var f = System.IO.Path.Combine(HostApi.DataDir, "shout_settings.json"); if (File.Exists(f)) foreach (var p in JObject.Parse(File.ReadAllText(f))) d[p.Key] = p.Value; else File.WriteAllText(f, d.ToString()); } catch (Exception) { }
            return d;
        }
        static string RecentPath { get { return System.IO.Path.Combine(HostApi.DataDir, "shoutouts.json"); } }
        static void LoadRecent()
        {
            try { if (File.Exists(RecentPath)) foreach (var p in JObject.Parse(File.ReadAllText(RecentPath))) Recent[p.Key] = DateTime.Parse((string)p.Value, null, System.Globalization.DateTimeStyles.RoundtripKind); } catch (Exception) { }
        }
        static void SaveRecent() { try { File.WriteAllText(RecentPath, new JObject(Recent.Where(r => (DateTime.UtcNow - r.Value).TotalHours < 24).Select(r => new JProperty(r.Key, r.Value.ToString("o")))).ToString()); } catch (Exception) { } }
        static void Start()
        {
            if (_started) return; _started = true; LoadRecent();
            var t = new Thread(Worker) { IsBackground = true }; t.Start();
        }
        static string F(string t, params string[] kv) { for (int i = 0; i + 1 < kv.Length; i += 2) t = t.Replace("{" + kv[i] + "}", kv[i + 1]); return t; }
        static void SayCore(string text) { string via; HostApi.SendAs("core", text, out via); }

        /// <summary>adds a streamer to the queue. auto = true for raid shoutouts (longer dedupe). Returns a short status for logs: queued | duplicate.</summary>
        public static string Enqueue(string user, string by, bool auto = false)
        {
            user = (user ?? "").Trim().TrimStart('@').ToLowerInvariant(); if (user == "") return "no user";
            var s = Settings(); Start(); int ahead;
            lock (L)
            {
                DateTime last; double win = auto ? (double)s["DedupeMinutes"] : (double)s["ManualDedupeMinutes"];
                if (Recent.TryGetValue(user, out last) && (DateTime.UtcNow - last).TotalMinutes < win) { if (!auto) SayCore(F((string)s["DuplicateLine"], "user", user)); return "duplicate"; }
                if (Q.Any(i => i.User == user)) return "duplicate";
                Recent[user] = DateTime.UtcNow; SaveRecent();
                ahead = Q.Count + (_current != "" ? 1 : 0);
                Q.Enqueue(new Item { User = user, By = by ?? "", Native = (bool?)s["Native"] != false, At = DateTime.UtcNow });
            }
            if ((bool?)s["TempLineOn"] != false)
            {
                // right away, without waiting for Twitch's 2 minute shoutout gap: a plain chat line with the channel link and the game they last played
                ThreadPool.QueueUserWorkItem(_ => { try { var inf = Info(user); SayCore(F((string)s["TempLine"], "user", inf != null ? inf[2] : user, "channel", "https://twitch.tv/" + (inf != null ? inf[1] : user), "game", inf != null ? inf[3] : "something fun")); } catch (Exception ex) { Clog.Warn("shoutout", "temp line failed: " + ex.Message); } });
            }
            else if (ahead > 0 && !auto) SayCore(F((string)s["QueuedLine"], "user", user, "n", ahead.ToString()));
            Sig.Release(); return "queued";
        }
        public static JObject Status()
        {
            lock (L) return new JObject { { "ok", true }, { "current", _current }, { "pending", new JArray(Q.Select(i => new JObject { { "user", i.User }, { "by", i.By }, { "queuedSecAgo", (int)(DateTime.UtcNow - i.At).TotalSeconds } })) },
                { "recent", new JArray(Recent.OrderByDescending(r => r.Value).Take(20).Select(r => new JObject { { "user", r.Key }, { "minAgo", (int)(DateTime.UtcNow - r.Value).TotalMinutes } })) } };
        }

        static void Worker()
        {
            while (true)
            {
                Sig.Wait(); Item it; lock (L) { if (Q.Count == 0) continue; it = Q.Dequeue(); _current = it.User; }
                try { Do(it); } catch (Exception ex) { Clog.Warn("shoutout", "shoutout for " + it.User + " failed: " + ex.Message); }
                finally { lock (L) _current = ""; }
            }
        }
        /// <summary>{uid, login, display name, last game} for a streamer (Helix, cached for 10 minutes); null when Twitch does not know the name.</summary>
        static string[] Info(string user)
        {
            lock (InfoCache) { string[] c; if (InfoCache.TryGetValue(user, out c)) return c; }
            string err, uid = TwitchApi.UserId(user, out err); if (uid == "") return null;
            JToken d; TwitchApi.Call(HttpMethod.Get, "/channels?broadcaster_id=" + uid, null, out d, out err);
            var ch = (d as JArray)?.FirstOrDefault();
            var r = new[] { uid, ((string)ch?["broadcaster_login"] ?? user).ToLowerInvariant(), (string)ch?["broadcaster_name"] ?? user, ((string)ch?["game_name"] ?? "") != "" ? (string)ch["game_name"] : "something fun" };
            lock (InfoCache) { InfoCache[user] = r; if (InfoCache.Count > 200) InfoCache.Clear(); }
            ThreadPool.QueueUserWorkItem(_ => { Thread.Sleep(10 * 60 * 1000); lock (InfoCache) InfoCache.Remove(user); });
            return r;
        }
        static void Do(Item it)
        {
            var s = Settings(); var inf = Info(it.User);
            if (inf == null) { SayCore(F((string)s["NotFoundLine"], "user", it.User, "by", it.By)); Clog.Warn("shoutout", it.User + ": no such Twitch user"); return; }
            string uid = inf[0], login = inf[1], name = inf[2], game = inf[3];
            string sub, obj, were; Pronouns(login, out sub, out obj, out were);
            string note = ""; bool cardSent = false;
            if (it.Native)   // Twitch's own shoutout card. Twitch limits (per channel, whoever sends): one shoutout per 2 minutes, the same streamer once per 60 minutes
            {
                DateTime lastTarget; bool targetBlocked; lock (L) targetBlocked = NativeRecent.TryGetValue(login, out lastTarget) && (DateTime.UtcNow - lastTarget).TotalMinutes < (double)s["NativeSameTargetMinutes"];
                if (targetBlocked) note = "native card skipped: " + login + " already got one in the last hour";
                else
                {
                    double wait = (double)s["NativeGapSec"] - (DateTime.UtcNow - _lastNative).TotalSeconds; if (wait > 0) Thread.Sleep((int)(Math.Min(wait, 130) * 1000));
                    int lo = Math.Max(0, (int?)s["NativeDelayMinSec"] ?? 1), hi = Math.Max(lo, (int?)s["NativeDelayMaxSec"] ?? 5);
                    int jitter = Rng.Next(lo * 1000, hi * 1000 + 1); Thread.Sleep(jitter);
                    JToken d; string err;
                    string code = TwitchApi.Call(HttpMethod.Post, "/chats/shoutouts?from_broadcaster_id={bid}&to_broadcaster_id=" + uid + "&moderator_id=" + TwitchApi.BroadcasterId(), null, out d, out err);
                    if (code == "429") { Thread.Sleep(30000); code = TwitchApi.Call(HttpMethod.Post, "/chats/shoutouts?from_broadcaster_id={bid}&to_broadcaster_id=" + uid + "&moderator_id=" + TwitchApi.BroadcasterId(), null, out d, out err); }
                    _lastNative = DateTime.UtcNow; cardSent = code == "204";
                    if (cardSent) lock (L) NativeRecent[login] = DateTime.UtcNow;
                    note = cardSent ? "native shoutout sent after " + jitter + " ms" : "native shoutout refused (HTTP " + code + (err != "" ? ": " + err : "") + ")";
                }
            }
            else
            {
                double wait = 8 - (DateTime.UtcNow - _lastPlain).TotalSeconds; if (wait > 0) Thread.Sleep((int)(wait * 1000));
            }
            _lastPlain = DateTime.UtcNow;
            // the temp line already told chat and the card does the shouting; the full line is only for when the temp line is switched off (or LineAfterNative)
            bool tempSent = (bool?)s["TempLineOn"] != false;
            if (!tempSent || (bool?)s["LineAfterNative"] == true)
                SayCore(F((string)s["Line"], "user", name, "game", game, "channel", "https://twitch.tv/" + login, "subject", sub, "object", obj, "were", were));
            Latest.Record("shoutout", new Dictionary<string, string> { { "user", it.By }, { "shoutoutUser", name } });
            Clog.Info("shoutout", "shouted out " + name + " (" + game + ")" + (note != "" ? "; " + note : ""));
        }

        static readonly Dictionary<string, string> PronCache = new Dictionary<string, string>();
        static void Pronouns(string login, out string subject, out string obj, out string were)
        {
            subject = "they"; obj = "them"; were = "were"; string id;
            lock (PronCache) PronCache.TryGetValue(login, out id);
            if (id == null)
            {
                id = "";
                try
                {
                    using (var h = new HttpClient { Timeout = TimeSpan.FromSeconds(4) })
                    { var arr = JArray.Parse(h.GetStringAsync("https://pronouns.alejo.io/api/users/" + Uri.EscapeDataString(login)).Result); id = (string)arr.FirstOrDefault()?["pronoun_id"] ?? ""; }
                }
                catch (Exception) { }
                lock (PronCache) PronCache[login] = id;
            }
            switch (id)
            {
                case "hehim": case "hethem": case "heshe": subject = "he"; obj = "him"; were = "was"; break;
                case "sheher": case "shethem": subject = "she"; obj = "her"; were = "was"; break;
                case "itits": subject = "it"; obj = "it"; were = "was"; break;
            }
        }
    }
}
