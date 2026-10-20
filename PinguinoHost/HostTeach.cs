using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>One source of truth for the channel's links (Data\runtime\links.json). Lore entries write {link:discord}; a change here changes every answer.</summary>
    public static class Links
    {
        static readonly object L = new object();
        static string P { get { return Path.Combine(HostApi.DataDir, "links.json"); } }
        static readonly string[][] Defaults = {
            new[] { "discord", "https://discord.gg/fktz5sq4b8" }, new[] { "website", "https://innocentpenguin.com" },
            new[] { "youtube", "https://www.youtube.com/@InnocentPinguino" }, new[] { "twitch", "https://twitch.tv/innocentpenguin_" } };
        public static JObject Doc()
        {
            lock (L)
            {
                JObject d = null;
                try { if (File.Exists(P)) d = JObject.Parse(File.ReadAllText(P, Encoding.UTF8).TrimStart('﻿')); } catch (Exception ex) { Clog.Warn("links", "links.json: " + ex.Message); }
                bool dirty = false; if (d == null) { d = new JObject(); dirty = true; }
                if (!(d["links"] is JObject)) { d["links"] = new JObject(); dirty = true; }
                foreach (var kv in Defaults) if (d["links"][kv[0]] == null) { d["links"][kv[0]] = kv[1]; dirty = true; }
                if (dirty) { try { Directory.CreateDirectory(HostApi.DataDir); File.WriteAllText(P, d.ToString(), new UTF8Encoding(false)); } catch (Exception) { } }
                return d;
            }
        }
        public static string Get(string key) { var t = Doc()["links"][(key ?? "").ToLowerInvariant()]; return t == null ? null : (string)t; }
        /// <summary>{link:key} -> the current link (unknown keys stay as written, so a typo is visible).</summary>
        public static string Expand(string s)
        {
            if (string.IsNullOrEmpty(s) || s.IndexOf("{link:", StringComparison.Ordinal) < 0) return s;
            return Regex.Replace(s, @"\{link:([a-z0-9_]+)\}", m => Get(m.Groups[1].Value) ?? m.Value, RegexOptions.IgnoreCase);
        }
        static readonly Regex RxUrl = new Regex(@"https?://[^\s]+", RegexOptions.IgnoreCase);
        static string Norm(string u) { u = Regex.Replace((u ?? "").Trim().TrimEnd('/', '.', ',', ')', '!'), @"^https?://(www\.)?", "", RegexOptions.IgnoreCase); return u.ToLowerInvariant(); }
        static string Host(string n) { int i = n.IndexOf('/'); return i < 0 ? n : n.Substring(0, i); }
        static int Segs(string n) { int i = n.IndexOf('/'); return i < 0 ? 0 : n.Substring(i + 1).Split('/').Count(x => x != ""); }
        /// <summary>Lore answers (and helper facts) that hold a hard-coded link to the same site as a current link but a different address.</summary>
        public static JArray Audit(IEnumerable<JObject> entries)
        {
            var res = new JArray(); var cur = ((JObject)Doc()["links"]).Properties().ToDictionary(p => p.Name, p => Norm((string)p.Value));
            foreach (var e in entries)
            {
                var texts = new List<string> { (string)e["response"] ?? "" }; texts.AddRange(((e["variants"] as JArray) ?? new JArray()).Select(x => (string)x ?? ""));
                foreach (var t in texts) foreach (Match m in RxUrl.Matches(t))
                {
                    string n = Norm(m.Value);
                    foreach (var kv in cur)
                        if (Host(n) == Host(kv.Value) && Segs(kv.Value) <= 1 && Segs(n) <= 1 && n != kv.Value)
                            res.Add(new JObject { { "id", e["id"] }, { "found", m.Value }, { "current", Get(kv.Key) }, { "key", kv.Key } });
                }
            }
            return res;
        }
    }

    /// <summary>Teach inbox: mods and trusted people feed the bots information, but NOTHING takes effect until Ivan approves it.
    /// Submissions are DATA only (never run as prompts or commands). Data\runtime\teach_inbox.json {items, audit}; Data\runtime\trusted.json {logins}.
    /// Chat: !teach / !correct (mods + trusted), !trust / !untrust (owner). Site: POST /api/teach. Owner: GET /api/teach?status=pending, POST /api/teach/decide.</summary>
    public static class Teach
    {
        static readonly object L = new object();
        static string InboxP { get { return Path.Combine(HostApi.DataDir, "teach_inbox.json"); } }
        static string TrustP { get { return Path.Combine(HostApi.DataDir, "trusted.json"); } }
        static readonly string[] Kinds = { "fact", "lore", "command", "instruction", "correction" };
        static readonly string[] Targets = { "helper", "chatty", "lore", "b0t" };
        const int MaxLen = 400, PerHour = 5, MinGapSec = 20, MaxPending = 200;
        static readonly Dictionary<string, List<long>> Sent = new Dictionary<string, List<long>>();
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }

        static JObject Read(string f, JObject dflt)
        {
            try { if (File.Exists(f)) return JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart('﻿')); } catch (Exception ex) { Clog.Warn("teach", Path.GetFileName(f) + ": " + ex.Message); }
            return dflt;
        }
        static void Write(string f, JObject d) { Directory.CreateDirectory(HostApi.DataDir); string tmp = f + ".tmp"; File.WriteAllText(tmp, d.ToString(), new UTF8Encoding(false)); if (File.Exists(f)) File.Delete(f); File.Move(tmp, f); }
        static JObject Inbox() { var d = Read(InboxP, new JObject()); if (!(d["items"] is JArray)) d["items"] = new JArray(); if (!(d["audit"] is JArray)) d["audit"] = new JArray(); return d; }
        static void Audit(JObject d, string action, string id, string by, string note = "")
        {
            var a = (JArray)d["audit"]; a.Add(new JObject { { "ts", Now() }, { "action", action }, { "id", id }, { "by", by }, { "note", note } });
            while (a.Count > 1000) a.RemoveAt(0);
        }

        // ---- trusted list ----
        public static List<string> Trusted() { lock (L) { return ((Read(TrustP, new JObject())["logins"] as JArray) ?? new JArray()).Select(x => ((string)x ?? "").ToLowerInvariant()).Where(x => x != "").ToList(); } }
        static bool SetTrusted(string login, bool on)
        {
            lock (L)
            {
                var l = Trusted(); bool has = l.Contains(login); if (on == has) return false;
                if (on) l.Add(login); else l.Remove(login);
                Write(TrustP, new JObject { { "logins", new JArray(l) } }); return true;
            }
        }

        // ---- cleaning: text from other people is stripped of links, mentions and control characters ----
        static readonly Regex RxLink = new Regex(@"(https?://|www\.)\S+|\b[a-z0-9-]+\.(com|gg|tv|net|org|io|co|me|ly|xyz)(/\S*)?\b", RegexOptions.IgnoreCase);
        static readonly Regex RxMention = new Regex(@"@\w+");
        public static string Clean(string s, out bool stripped)
        {
            s = Regex.Replace(s ?? "", @"[\u0000-\u001F\u007F​-‏‪-‮⁦-⁩]", " ");
            string c = RxMention.Replace(RxLink.Replace(s, ""), ""); stripped = c != s;
            c = Regex.Replace(c, @"\s+", " ").Trim(); if (c.Length > MaxLen) c = c.Substring(0, MaxLen).Trim();
            return c;
        }

        // ---- submitting ----
        /// <summary>role is the verified Twitch role (4 broadcaster, 3 mod, 2 vip, 1 viewer). Returns the item, or null when the sender may not teach (or is rate limited).</summary>
        public static JObject Submit(string from, int role, string rawText, string forceKind, string via, out string why, string siteId = null)
        {
            why = ""; string login = (from ?? "").ToLowerInvariant().TrimStart('@'); if (login == "") { why = "no sender"; return null; }
            string label = role >= 3 ? "mod" : Trusted().Contains(login) ? (role == 2 ? "vip" : "trusted") : "";
            if (label == "") { why = "not allowed"; return null; }
            string kind = forceKind ?? "fact", target = null, txt = (rawText ?? "").Trim();
            var m = Regex.Match(txt, @"^\s*(?:(fact|lore|command|instruction|correction)|(helper|chatty|lore|b0t))\s*:\s*(.+)$", RegexOptions.IgnoreCase | RegexOptions.Singleline);
            if (m.Success) { if (m.Groups[1].Success && forceKind == null) kind = m.Groups[1].Value.ToLowerInvariant(); if (m.Groups[2].Success) target = m.Groups[2].Value.ToLowerInvariant(); txt = m.Groups[3].Value; }
            if (target == null) target = kind == "lore" || kind == "command" ? "lore" : kind == "instruction" ? "chatty" : "helper";
            if (!Kinds.Contains(kind)) kind = "fact";
            bool stripped; string clean = Clean(txt, out stripped); if (clean.Length < 3) { why = "empty"; return null; }
            lock (L)
            {
                long now = Now(); List<long> h; if (!Sent.TryGetValue(login, out h)) Sent[login] = h = new List<long>();
                var d = Inbox(); var items = (JArray)d["items"];
                if (siteId != null && items.OfType<JObject>().Any(x => (string)x["siteId"] == siteId)) { why = "duplicate"; return null; }   // the site bridge polls again and again: one site id is one item, ever
                if (siteId == null) { h.RemoveAll(t => now - t > 3600); if (h.Count >= PerHour || (h.Count > 0 && now - h[h.Count - 1] < MinGapSec)) { why = "rate limited"; return null; } }   // the site already rate limits its own form
                if (items.OfType<JObject>().Count(x => (string)x["status"] == "pending") >= MaxPending) { why = "inbox full"; return null; }
                if (siteId == null) h.Add(now);
                var it = new JObject { { "id", Guid.NewGuid().ToString("N").Substring(0, 10) }, { "from", login }, { "role", label }, { "kind", kind }, { "text", clean }, { "target", target },
                    { "status", "pending" }, { "ts", now }, { "reviewer", "" }, { "note", "" }, { "via", via ?? "chat" }, { "linksStripped", stripped }, { "raw", txt.Length > 600 ? txt.Substring(0, 600) : txt } };
                if (siteId != null) it["siteId"] = siteId;
                items.Add(it); Audit(d, "submit", (string)it["id"], login, kind + "->" + target); Write(InboxP, d); return it;
            }
        }

        public static bool IsCommand(string cmd) { return cmd == "!teach" || cmd == "!correct" || cmd == "!trust" || cmd == "!untrust"; }
        /// <summary>!teach / !correct text (mods + trusted); !trust / !untrust login (owner only). Everyone else gets nothing.</summary>
        public static void Handle(string user, string cmd, string[] args, int role, Action<string> say)
        {
            try
            {
                if (cmd == "!trust" || cmd == "!untrust")
                {
                    if (role < 4 || args.Length == 0) return; string who = args[0].TrimStart('@').ToLowerInvariant(); if (!Regex.IsMatch(who, @"^[a-z0-9_]{2,25}$")) return;
                    bool ch = SetTrusted(who, cmd == "!trust"); lock (L) { var d = Inbox(); Audit(d, cmd.Substring(1), "", user.ToLowerInvariant(), who); Write(InboxP, d); }
                    say(cmd == "!trust" ? (ch ? who + " can now send teach notes (Ivan still approves everything)." : who + " was already trusted.") : (ch ? who + " is no longer trusted." : who + " was not on the trusted list.")); return;
                }
                string why; var it = Submit(user, role, string.Join(" ", args), cmd == "!correct" ? "correction" : null, "chat", out why);
                if (it != null) say("@" + user + " Thanks, sent to Ivan for review");
            }
            catch (Exception ex) { Clog.Warn("teach", cmd + " failed: " + ex.Message); }
        }

        // ---- the owner's side ----
        public static JObject Api(string status)
        {
            lock (L)
            {
                var d = Inbox(); var items = ((JArray)d["items"]).OfType<JObject>().Where(x => string.IsNullOrEmpty(status) || (string)x["status"] == status).OrderByDescending(x => (long?)x["ts"] ?? 0);
                return new JObject { { "ok", true }, { "items", new JArray(items) }, { "pending", ((JArray)d["items"]).OfType<JObject>().Count(x => (string)x["status"] == "pending") }, { "trusted", new JArray(Trusted()) }, { "audit", new JArray(((JArray)d["audit"]).Reverse().Take(100)) } };
            }
        }

        /// <summary>POST /api/teach from the site form. The Host cannot see Twitch badges there, so only a login that is trusted, or that the Host itself has seen as a mod in chat, may submit.</summary>
        public static JObject Post(JObject b)
        {
            string from = ((string)b["from"] ?? "").ToLowerInvariant().TrimStart('@'); int role = Roster.RoleOf(from);
            string kind = ((string)b["kind"] ?? "").ToLowerInvariant(); string tg = ((string)b["target"] ?? "").ToLowerInvariant(); string text = (string)b["text"] ?? "";
            if (Targets.Contains(tg) && !Regex.IsMatch(text, @"^\s*\w+\s*:")) text = tg + ": " + text;
            string why; var it = Submit(from, role, text, Kinds.Contains(kind) ? kind : null, "site", out why);
            if (it == null) return new JObject { { "ok", false }, { "error", why } };
            return new JObject { { "ok", true }, { "id", it["id"] }, { "message", "Thanks, sent to Ivan for review" } };
        }

        /// <summary>POST /api/teach/decide {id, action approve|reject|edit|undo, text, note, target, reviewer}</summary>
        public static JObject Decide(JObject b)
        {
            string id = (string)b["id"] ?? "", act = ((string)b["action"] ?? "").ToLowerInvariant(), by = (string)b["reviewer"] ?? "ivan";
            lock (L)
            {
                var d = Inbox(); var it = ((JArray)d["items"]).OfType<JObject>().FirstOrDefault(x => (string)x["id"] == id); if (it == null) return new JObject { { "ok", false }, { "error", "no such item" } };
                string st = (string)it["status"];
                if (act == "undo")
                {
                    if (it["applied"] == null) return new JObject { { "ok", false }, { "error", "nothing applied" } };
                    Unapply(it); it.Remove("applied"); it["status"] = "rejected"; it["note"] = "undone"; it["reviewer"] = by; Audit(d, "undo", id, by); Write(InboxP, d); Raise(it); return new JObject { { "ok", true }, { "status", "rejected" } };
                }
                if (st != "pending") return new JObject { { "ok", false }, { "error", "already " + st } };
                if (act == "reject") { it["status"] = "rejected"; it["reviewer"] = by; it["note"] = (string)b["note"] ?? ""; Audit(d, "reject", id, by); Write(InboxP, d); Raise(it); return new JObject { { "ok", true }, { "status", "rejected" } }; }
                if (act != "approve" && act != "edit") return new JObject { { "ok", false }, { "error", "action: approve | reject | edit | undo" } };
                if (act == "edit")
                {   // the owner's own text may keep links / mentions: it is Ivan's text now
                    string et = Regex.Replace((string)b["text"] ?? "", @"\s+", " ").Trim(); if (et.Length < 3) return new JObject { { "ok", false }, { "error", "text required" } };
                    it["original"] = it["text"]; it["text"] = et.Length > 600 ? et.Substring(0, 600) : et;
                }
                string t = ((string)b["target"] ?? "").ToLowerInvariant(); if (Targets.Contains(t)) it["target"] = t;
                it["applied"] = Apply(it); it["status"] = act == "edit" ? "edited" : "approved"; it["reviewer"] = by; it["note"] = (string)b["note"] ?? ""; it["decidedAt"] = Now();
                Audit(d, act, id, by, (string)it["target"]); Write(InboxP, d); Raise(it);
                return new JObject { { "ok", true }, { "status", it["status"] }, { "applied", it["applied"] } };
            }
        }

        // ---- what an approved note becomes (with provenance); every one can be undone ----
        /// <summary>raised after every decision (approve / edit / reject / undo) with a copy of the item; the site bridge uses it to tell the site. Never throws into Decide.</summary>
        public static event Action<JObject> Decided;
        static void Raise(JObject it) { try { var h = Decided; if (h != null) h((JObject)it.DeepClone()); } catch (Exception ex) { Clog.Warn("teach", "decision hook: " + ex.Message); } }
        /// <summary>a copy of the item that came from this site id, or null</summary>
        public static JObject FindSite(string siteId) { lock (L) { var it = ((JArray)Inbox()["items"]).OfType<JObject>().FirstOrDefault(x => (string)x["siteId"] == siteId); return it == null ? null : (JObject)it.DeepClone(); } }
        static JObject Prov(JObject it) { return new JObject { { "taughtBy", it["from"] }, { "role", it["role"] }, { "taughtAt", it["ts"] }, { "teachId", it["id"] } }; }
        static JObject Apply(JObject it)
        {
            string target = (string)it["target"], text = (string)it["text"], id = (string)it["id"], kind = (string)it["kind"];
            if (target == "lore")
            {
                var e = new JObject { { "id", "taught-" + id }, { "kind", "info" }, { "response", text }, { "enabled", true }, { "publicSafe", true }, { "contextual", false }, { "triggers", new JArray() }, { "source", "teach" }, { "taught", Prov(it) } };
                var m = Regex.Match(text, @"^(![a-z0-9_]{2,24})\s+(.+)$", RegexOptions.IgnoreCase | RegexOptions.Singleline);
                if (kind == "command" && m.Success) { ((JArray)e["triggers"]).Add(m.Groups[1].Value.ToLowerInvariant()); e["response"] = m.Groups[2].Value; }
                ChannelLore.Post(new JObject { { "action", "upsert" }, { "entry", e } });
                return new JObject { { "kind", "lore" }, { "entry", "taught-" + id } };
            }
            if (target == "helper")
            {   // "Key: value" sets that helper fact (the old value is kept for undo); anything else joins the Taught list
                string f = Path.Combine(HostApi.DataDir, "helper_facts.json"); var h = Read(f, new JObject());
                var m = Regex.Match(text, @"^([A-Z][A-Za-z0-9]{2,30})\s*:\s*(.+)$");
                if (m.Success && h[m.Groups[1].Value] != null && h[m.Groups[1].Value].Type == JTokenType.String)
                {
                    string key = m.Groups[1].Value; var res = new JObject { { "kind", "helperFact" }, { "key", key }, { "prev", h[key] } }; h[key] = m.Groups[2].Value; Write(f, h); return res;
                }
                var arr = h["Taught"] as JArray ?? new JArray(); var n = new JObject { { "id", id }, { "text", text } }; foreach (var p in Prov(it).Properties()) n[p.Name] = p.Value; arr.Add(n); h["Taught"] = arr; Write(f, h);
                return new JObject { { "kind", "helperTaught" } };
            }
            // chatty / b0t: an approved-notes file the bot reads as data (b0t: for Ivan to act on by hand)
            string nf = Path.Combine(HostApi.DataDir, target == "chatty" ? "taught_chatty.json" : "taught_b0t.json"); var nd = Read(nf, new JObject()); var na = nd["items"] as JArray ?? new JArray();
            var ni = new JObject { { "id", id }, { "kind", kind }, { "text", text } }; foreach (var p in Prov(it).Properties()) ni[p.Name] = p.Value; na.Add(ni); nd["items"] = na; Write(nf, nd);
            return new JObject { { "kind", target + "Note" } };
        }
        static void Unapply(JObject it)
        {
            var a = it["applied"] as JObject; if (a == null) return; string k = (string)a["kind"], id = (string)it["id"];
            if (k == "lore") ChannelLore.Post(new JObject { { "action", "delete" }, { "id", (string)a["entry"] } });
            else if (k == "helperFact" || k == "helperTaught")
            {
                string f = Path.Combine(HostApi.DataDir, "helper_facts.json"); var h = Read(f, new JObject());
                if (k == "helperFact") h[(string)a["key"]] = a["prev"]; else if (h["Taught"] is JArray t) foreach (var x in t.OfType<JObject>().Where(x => (string)x["id"] == id).ToList()) x.Remove();
                Write(f, h);
            }
            else
            {
                string nf = Path.Combine(HostApi.DataDir, k == "chattyNote" ? "taught_chatty.json" : "taught_b0t.json"); var nd = Read(nf, new JObject());
                if (nd["items"] is JArray na) foreach (var x in na.OfType<JObject>().Where(x => (string)x["id"] == id).ToList()) x.Remove();
                Write(nf, nd);
            }
        }
    }
}
