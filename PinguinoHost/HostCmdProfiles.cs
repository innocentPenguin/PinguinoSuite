using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>One profile per chat command (built-ins from PinguinoB0t\commands.json, Chatty canned commands, Actions &amp; Events commands) with a runtime-editable permission tier,
    /// cooldowns, enabled flag, description and category; usage stats; archive instead of delete (Data\config\commands_archive.json, restorable); an audit log of every change.
    /// Storage: Data\config\command_profiles.json (only what was changed from the defaults), command_usage.json, commands_archive.json, commands_audit.log.
    /// Enforcement is central: Program.Dispatch calls Gate() before any bot sees a chat line. It RESTRICTS (an edited tier, disabled, archived, cooldowns) and stays silent;
    /// commands never changed behave exactly as before. Loosening a tier a handler checks itself (e.g. making a mod-only command public) cannot grant more than the handler allows.</summary>
    public static class CmdProfiles
    {
        static readonly object L = new object();
        static readonly string[] Tiers = { "everyone", "sub", "vip", "mod", "broadcaster" };
        static JObject _over, _use, _arch; static DateTime _loadAt = DateTime.MinValue; static bool _useDirty; static DateTime _useSaved = DateTime.UtcNow;
        static List<Prof> _reg; static DateTime _regAt = DateTime.MinValue; static Dictionary<string, Prof> _byName = new Dictionary<string, Prof>();
        static readonly Dictionary<string, DateTime> _cool = new Dictionary<string, DateTime>();

        class Prof { public string Id, Name, Description, Category, Permission, DefaultPermission, Owner, Source; public List<string> Aliases = new List<string>(); public int CdG, CdU; public bool Enabled = true; }

        static string Dir { get { return Path.Combine(HostApi.DataDir, "config"); } }
        static string F(string n) { return Path.Combine(Dir, n); }
        static JObject ReadObj(string f) { try { if (File.Exists(f)) { var j = JObject.Parse(File.ReadAllText(f).TrimStart((char)0xFEFF)); return j; } } catch (Exception ex) { Clog.Warn("cmdprofiles", Path.GetFileName(f) + " unreadable: " + ex.Message); } return new JObject(); }
        static void WriteObj(string f, JObject o) { Directory.CreateDirectory(Dir); var tmp = f + ".tmp"; File.WriteAllText(tmp, o.ToString()); if (File.Exists(f)) File.Replace(tmp, f, null); else File.Move(tmp, f); }
        static void Load() { if ((DateTime.UtcNow - _loadAt).TotalSeconds < 4 && _over != null) return; _loadAt = DateTime.UtcNow; _over = ReadObj(F("command_profiles.json")); _arch = ReadObj(F("commands_archive.json")); if (!(_arch["archived"] is JArray)) _arch["archived"] = new JArray(); if (_use == null) _use = ReadObj(F("command_usage.json")); }

        public static int Rank(string p) { int i = Array.IndexOf(Tiers, (p ?? "").ToLowerInvariant()); return i < 0 ? 0 : i; }
        static int UserRank(int role, bool sub) { return role >= 4 ? 4 : role >= 3 ? 3 : role == 2 ? 2 : sub ? 1 : 0; }
        static string DefaultTier(JObject c) { string t = ((string)c["tier"] ?? "").ToLowerInvariant(); if (Array.IndexOf(Tiers, t) >= 0) return t; string w = ((string)c["who"] ?? "").ToLowerInvariant(); return w.Contains("everyone") || w == "automatic" ? "everyone" : w.Contains("mod") ? "mod" : "everyone"; }
        static string Owner(string a) { switch (a) { case "PinguinoHost": return "Host"; case "PinguinoBotCore": case "PinguinoBotFirsts": return "B0t"; case "PinguinoChat": return "Chatty"; case "PinguinoHelper": return "Helper"; default: return a ?? ""; } }
        static string Bang(string n) { n = (n ?? "").Trim().ToLowerInvariant(); return n == "" ? "" : n.StartsWith("!") ? n : "!" + n; }

        static List<Prof> Registry()
        {
            if (_reg != null && (DateTime.UtcNow - _regAt).TotalSeconds < 4) return _reg;
            var list = new List<Prof>(); var seen = new HashSet<string>();
            try
            {
                var src = SubsImport.ParseJ(File.ReadAllText(Path.Combine(Program.SuiteDir ?? "", "PinguinoB0t", "commands.json")));
                foreach (var c in (src["commands"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    string id = Bang((string)c["command"]); if (id == "" || !seen.Add(id)) continue; string d = DefaultTier(c);
                    var p = new Prof { Id = id, Name = id, Description = (string)c["description"] ?? "", Category = (string)c["category"] ?? "", Permission = d, DefaultPermission = d, Owner = Owner((string)c["action"]), Source = "builtin" };
                    foreach (var a in c["aliases"] as JArray ?? new JArray()) p.Aliases.Add(Bang((string)a)); list.Add(p);
                }
            }
            catch (Exception ex) { Clog.Warn("cmdprofiles", "commands.json: " + ex.Message); }
            try
            {
                string cf = Path.Combine(Program.SuiteDir ?? "", "PinguinoChat", "canned_commands.json");
                if (File.Exists(cf)) foreach (var c in (SubsImport.ParseJ(File.ReadAllText(cf))["commands"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    string id = Bang((string)c["name"]); if (id == "" || !seen.Add(id)) continue;
                    string t = (string)c["text"] ?? ((c["choices"] as JArray)?.FirstOrDefault()?.ToString() ?? ""); if (t.Length > 110) t = t.Substring(0, 107) + "...";
                    var p = new Prof { Id = id, Name = id, Description = t, Category = "Fun", Permission = "everyone", DefaultPermission = "everyone", Owner = "Chatty", Source = "canned", Enabled = (bool?)c["enabled"] != false };
                    foreach (var a in c["aliases"] as JArray ?? new JArray()) p.Aliases.Add(Bang((string)a)); list.Add(p);
                }
            }
            catch (Exception ex) { Clog.Warn("cmdprofiles", "canned_commands.json: " + ex.Message); }
            try
            {
                foreach (var a in (Auto.Doc()["actions"] as JArray ?? new JArray()).OfType<JObject>())
                    foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>().Where(t => string.Equals((string)t["type"], "command", StringComparison.OrdinalIgnoreCase)))
                    {
                        var names = (t["names"] as JArray ?? new JArray()).Select(n => Bang((string)n)).Where(n => n != "").ToList(); if (names.Count == 0 || !seen.Add(names[0])) continue;
                        string d = (string)t["permission"] ?? "everyone"; if (Array.IndexOf(Tiers, d) < 0) d = "everyone";
                        list.Add(new Prof { Id = names[0], Name = names[0], Description = (string)a["description"] ?? (string)a["name"] ?? "", Category = "Custom", Permission = d, DefaultPermission = d, Owner = "Host", Source = "custom", CdG = (int?)t["cooldownSec"] ?? 0, CdU = (int?)t["userCooldownSec"] ?? 0, Enabled = (bool?)a["enabled"] != false, Aliases = names.Skip(1).ToList() });
                    }
            }
            catch (Exception ex) { Clog.Warn("cmdprofiles", "automations: " + ex.Message); }
            var by = new Dictionary<string, Prof>(); foreach (var p in list) { by[p.Id] = p; foreach (var a in p.Aliases) if (!by.ContainsKey(a)) by[a] = p; }
            _byName = by; _reg = list; _regAt = DateTime.UtcNow; return list;
        }

        static JObject Over(string id) { var o = _over[id] as JObject; return o; }
        static void Apply(Prof p)   // layer the saved edits over the defaults
        {
            var o = Over(p.Id); if (o == null) return;
            if (o["permission"] != null) p.Permission = (string)o["permission"]; if (o["cooldownGlobal"] != null) p.CdG = (int)o["cooldownGlobal"]; if (o["cooldownUser"] != null) p.CdU = (int)o["cooldownUser"];
            if (o["enabled"] != null) p.Enabled = (bool)o["enabled"]; if (o["description"] != null) p.Description = (string)o["description"]; if (o["category"] != null) p.Category = (string)o["category"];
        }
        static bool IsArchived(string id) { return ((JArray)_arch["archived"]).OfType<JObject>().Any(a => (string)a["id"] == id); }
        static JObject View(Prof p)
        {
            var o = Over(p.Id); var u = _use[p.Id] as JObject;
            return new JObject { { "id", p.Id }, { "name", p.Name }, { "aliases", new JArray(p.Aliases) }, { "description", p.Description }, { "category", p.Category }, { "permission", p.Permission }, { "defaultPermission", p.DefaultPermission },
                { "cooldownGlobal", p.CdG }, { "cooldownUser", p.CdU }, { "enabled", p.Enabled }, { "uses", (long?)u?["uses"] ?? 0 }, { "lastUsed", (long?)u?["last"] ?? 0 }, { "ownerBot", p.Owner }, { "source", p.Source },
                { "createdBy", (string)o?["createdBy"] ?? "system" }, { "createdAt", (long?)o?["createdAt"] ?? 0 }, { "editedBy", (string)o?["editedBy"] ?? "" }, { "editedAt", (long?)o?["editedAt"] ?? 0 }, { "archived", false } };
        }
        static Prof Find(string id) { Registry(); Prof p; return _byName.TryGetValue(Bang(id), out p) ? p : null; }
        static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        static void Audit(string who, string id, string what) { try { Directory.CreateDirectory(Dir); File.AppendAllText(F("commands_audit.log"), new JObject { { "at", Now() }, { "by", who }, { "id", id }, { "change", what } }.ToString(Newtonsoft.Json.Formatting.None) + "\n"); } catch (Exception) { } Clog.Info("cmdprofiles", who + ": " + id + " " + what); }

        // ---------------- central gate ----------------
        /// <summary>true = swallow this chat line (disabled, archived, tier too low, cooldown). Counts usage of the commands that run. Silent: no chat reply.</summary>
        public static bool Gate(string user, string text, int role, bool isSub)
        {
            text = (text ?? "").TrimStart(); if (!text.StartsWith("!")) return false;
            string tok = text.Split(' ')[0].ToLowerInvariant();
            lock (L)
            {
                Load(); Registry(); Prof p; if (!_byName.TryGetValue(tok, out p)) return false;
                if (IsArchived(p.Id)) return true;
                Apply(p);
                if (!p.Enabled && p.Source != "custom") return true;   // custom commands: Actions & Events already skips a disabled action
                var ov = Over(p.Id); if (ov?["permission"] != null && UserRank(role, isSub) < Rank(p.Permission)) return true;   // only an edited tier is enforced here: unedited commands keep their own checks
                int cg = ov?["cooldownGlobal"] != null ? p.CdG : 0, cu = ov?["cooldownUser"] != null ? p.CdU : 0;   // likewise: only edited cooldowns
                if (role < 4 && (cg > 0 || cu > 0))
                {
                    var now = DateTime.UtcNow; string kg = p.Id + "|g", ku = p.Id + "|u|" + (user ?? "").ToLowerInvariant(); DateTime d;
                    if (cg > 0 && _cool.TryGetValue(kg, out d) && (now - d).TotalSeconds < cg) return true;
                    if (cu > 0 && _cool.TryGetValue(ku, out d) && (now - d).TotalSeconds < cu) return true;
                    if (cg > 0) _cool[kg] = now; if (cu > 0) _cool[ku] = now;
                }
                var u = _use[p.Id] as JObject; if (u == null) { u = new JObject { { "uses", 0 }, { "last", 0 } }; _use[p.Id] = u; }
                u["uses"] = (long)u["uses"] + 1; u["last"] = Now(); _useDirty = true;
                if (_useDirty && (DateTime.UtcNow - _useSaved).TotalSeconds > 20) FlushUse();
            }
            return false;
        }
        static void FlushUse() { try { WriteObj(F("command_usage.json"), _use); _useDirty = false; _useSaved = DateTime.UtcNow; } catch (Exception) { } }

        // ---------------- API ----------------
        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }

        public static JObject List()
        {
            lock (L) { Load(); var arr = new JArray(); foreach (var p in Registry()) { if (IsArchived(p.Id)) continue; Apply(p); arr.Add(View(p)); } if (_useDirty) FlushUse(); return new JObject { { "ok", true }, { "commands", arr } }; }
        }
        public static JObject ArchiveList() { lock (L) { Load(); var arr = new JArray(); foreach (var a in ((JArray)_arch["archived"]).OfType<JObject>()) { var o = (JObject)((JObject)a["profile"]).DeepClone(); o["archived"] = true; o["archivedBy"] = a["archivedBy"]; o["archivedAt"] = a["archivedAt"]; arr.Add(o); } return new JObject { { "ok", true }, { "commands", arr } }; } }

        public static JObject Edit(JObject b)
        {
            string by = ((string)b["by"] ?? "api").Trim(); string id = Bang((string)b["id"]);
            lock (L)
            {
                Load(); var p = Find(id); if (p == null || IsArchived(p.Id)) return Err("unknown command " + id); Apply(p); var over = (Over(p.Id) ?? new JObject()); var ch = new List<string>(); var errs = new List<string>();
                foreach (var kv in b.Properties())
                {
                    string k = kv.Name; if (k == "id" || k == "by") continue;
                    switch (k)
                    {
                        case "permission": { string v = ((string)kv.Value ?? "").ToLowerInvariant(); if (Array.IndexOf(Tiers, v) < 0) { errs.Add("permission must be one of " + string.Join("|", Tiers)); break; } if (v != p.Permission) { ch.Add("permission " + p.Permission + " -> " + v); p.Permission = v; } over["permission"] = v; break; }
                        case "cooldownGlobal": case "cooldownUser": { int v; if (kv.Value.Type != JTokenType.Integer || (v = (int)kv.Value) < 0 || v > 86400) { errs.Add(k + " must be a whole number of seconds 0-86400"); break; } int old = k == "cooldownGlobal" ? p.CdG : p.CdU; if (v != old) ch.Add(k + " " + old + " -> " + v); if (k == "cooldownGlobal") p.CdG = v; else p.CdU = v; over[k] = v; break; }
                        case "enabled": { if (kv.Value.Type != JTokenType.Boolean) { errs.Add("enabled must be true or false"); break; } bool v = (bool)kv.Value; if (v != p.Enabled) ch.Add("enabled " + p.Enabled + " -> " + v); p.Enabled = v; over["enabled"] = v; break; }
                        case "description": { string v = ((string)kv.Value ?? "").Trim(); if (v.Length > 400) { errs.Add("description is limited to 400 characters"); break; } if (v != p.Description) ch.Add("description edited"); p.Description = v; over["description"] = v; break; }
                        case "category": { string v = ((string)kv.Value ?? "").Trim(); if (v.Length > 40 || v == "") { errs.Add("category must be 1-40 characters"); break; } if (v != p.Category) ch.Add("category " + p.Category + " -> " + v); p.Category = v; over["category"] = v; break; }
                        case "name": if (!string.Equals(Bang((string)kv.Value), p.Name)) errs.Add("name cannot be changed (the bots recognise the built-in name)"); break;
                        case "aliases": if (!string.Join(",", ((kv.Value as JArray) ?? new JArray()).Select(x => Bang((string)x))).Equals(string.Join(",", p.Aliases))) errs.Add("aliases cannot be changed here (use the typo/alias settings)"); break;
                        case "uses": case "lastUsed": case "ownerBot": case "editedBy": case "editedAt": case "archived": case "defaultPermission": case "source": case "createdBy": case "createdAt": break;   // read-only echoes are ignored
                        default: errs.Add("unknown field " + k); break;
                    }
                }
                if (errs.Count > 0) return Err(string.Join("; ", errs));
                if (ch.Count > 0)
                {
                    over["editedBy"] = by; over["editedAt"] = Now(); if (over["createdAt"] == null) { over["createdBy"] = "system"; over["createdAt"] = 0; }
                    _over[p.Id] = over; try { WriteObj(F("command_profiles.json"), _over); } catch (Exception ex) { return Err("could not save: " + ex.Message); }
                    Audit(by, p.Id, string.Join("; ", ch)); _regAt = DateTime.MinValue;
                }
                return new JObject { { "ok", true }, { "command", View(p) } };
            }
        }

        public static JObject Archive(JObject b)
        {
            string by = ((string)b["by"] ?? "api").Trim(); string id = Bang((string)b["id"]);
            lock (L)
            {
                Load(); var p = Find(id); if (p == null) return Err("unknown command " + id); if (IsArchived(p.Id)) return Err(p.Id + " is already archived"); Apply(p);
                var a = new JObject { { "id", p.Id }, { "archivedBy", by }, { "archivedAt", Now() }, { "profile", View(p) } }; ((JArray)_arch["archived"]).Add(a);
                try { WriteObj(F("commands_archive.json"), _arch); } catch (Exception ex) { ((JArray)_arch["archived"]).Remove(a); return Err("could not save: " + ex.Message); }
                Audit(by, p.Id, "archived"); return new JObject { { "ok", true } };
            }
        }
        public static JObject Restore(JObject b)
        {
            string by = ((string)b["by"] ?? "api").Trim(); string id = Bang((string)b["id"]);
            lock (L)
            {
                Load(); var arr = (JArray)_arch["archived"]; var a = arr.OfType<JObject>().FirstOrDefault(x => (string)x["id"] == id); if (a == null) return Err(id + " is not in the archive");
                arr.Remove(a); try { WriteObj(F("commands_archive.json"), _arch); } catch (Exception ex) { arr.Add(a); return Err("could not save: " + ex.Message); }
                Audit(by, id, "restored"); _regAt = DateTime.MinValue; var p = Find(id); if (p == null) return Err(id + " no longer exists in the command files"); Apply(p); return new JObject { { "ok", true }, { "command", View(p) } };
            }
        }

        /// <summary>for the public /commands doc: false = hide the entry (archived or disabled); tier = the effective permission (null when the command was never edited).</summary>
        public static bool DocVisible(string name, out string tier)
        {
            tier = null; lock (L) { Load(); Registry(); Prof p; if (!_byName.TryGetValue(Bang(name), out p)) return true; if (IsArchived(p.Id)) return false; Apply(p); if (!p.Enabled && p.Source != "custom") return false; if (Over(p.Id)?["permission"] != null) tier = p.Permission; return true; }
        }
    }
}
