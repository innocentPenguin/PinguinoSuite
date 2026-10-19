using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Imports what can be converted from a Streamer.bot data folder (actions.json + commands.json + twitch_rewards.json) into Actions &amp; Events.
    /// Everything imported is created DISABLED so it can be reviewed; C# actions (the Pinguino bots), game commands the bots own and sub-actions without an equivalent
    /// are reported and skipped (a "comment" step marks the gap). Never reads or copies secrets: prompts, API keys and credentials are ignored.</summary>
    public static class AutoImport
    {
        static string FindDir(string hint)
        {
            var c = new List<string>(); if (!string.IsNullOrWhiteSpace(hint)) c.Add(hint);
            string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), app = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            c.Add(Path.Combine(docs, "PinguinoB0t", "data")); c.Add(Path.Combine(app, "Streamer.bot", "data")); c.Add(Path.Combine(docs, "Streamer.bot", "data"));
            foreach (var d in c) { var dir = File.Exists(d) ? Path.GetDirectoryName(d) : d; if (Directory.Exists(dir) && File.Exists(Path.Combine(dir, "actions.json"))) return dir; }
            return null;
        }
        static JObject ReadJson(string f) { return File.Exists(f) ? JObject.Parse(File.ReadAllText(f, Encoding.UTF8).TrimStart('﻿')) : null; }

        static string Conv(string t)
        {
            if (t == null) return "";
            t = Regex.Replace(t, @"~([A-Za-z0-9_]+)~", "{var:$1}");
            var map = new Dictionary<string, string> { { "user", "user" }, { "userName", "userName" }, { "targetUser", "arg1" }, { "viewers", "viewers" }, { "bits", "bits" }, { "tier", "tier" }, { "rawInput", "args" }, { "input0", "arg1" }, { "input1", "arg2" }, { "input2", "arg3" }, { "message", "message" }, { "counter", "count" } };
            return Regex.Replace(t, @"%([A-Za-z0-9_]+)%", m => "{" + (map.ContainsKey(m.Groups[1].Value) ? map[m.Groups[1].Value] : m.Groups[1].Value) + "}");
        }
        static string Perm(string groups)
        {
            string g = groups ?? ""; if (g.Contains("Broadcaster")) return "broadcaster"; if (g.Contains("Moderators")) return "mod"; if (g.Contains("VIP")) return "vip"; if (g.Contains("Subscribers")) return "sub"; return "everyone";
        }

        public static JObject Run(JObject body)
        {
            string dir = FindDir((string)body["path"]); bool apply = (string)body["mode"] == "merge";
            if (dir == null) return new JObject { { "ok", false }, { "error", "Streamer.bot data folder not found. Give the folder that holds actions.json in 'path'." } };
            JObject src, cmds, rewards;
            try { src = ReadJson(Path.Combine(dir, "actions.json")); cmds = ReadJson(Path.Combine(dir, "commands.json")); rewards = ReadJson(Path.Combine(dir, "twitch_rewards.json")); }
            catch (Exception ex) { return new JObject { { "ok", false }, { "error", "could not read the Streamer.bot files: " + ex.Message } }; }
            var cmdById = new Dictionary<string, JObject>(); foreach (var c in (cmds?["commands"] as JArray ?? new JArray()).OfType<JObject>()) cmdById[(string)c["id"]] = c;
            var rewardTitle = new Dictionary<string, string>(); foreach (var r in (rewards?["rewards"] as JArray ?? new JArray()).OfType<JObject>()) rewardTitle[(string)r["id"]] = (string)r["title"];
            var nameById = new Dictionary<string, string>(); foreach (var a in (src["actions"] as JArray ?? new JArray()).OfType<JObject>()) nameById[(string)a["id"]] = (string)a["name"];
            var coreCmds = new HashSet<string>(Program.CoreCommandList(), StringComparer.OrdinalIgnoreCase);
            var imported = new JArray(); var skipped = new JArray(); var made = new List<JObject>();

            foreach (var a in (src["actions"] as JArray ?? new JArray()).OfType<JObject>())
            {
                string name = (string)a["name"] ?? "";
                var subs = (a["subActions"] as JArray ?? new JArray()).OfType<JObject>().ToList();
                if (subs.Any(s => (int?)s["type"] == 99999 || (int?)s["type"] == 99998)) { skipped.Add(new JObject { { "name", name }, { "why", "C# code (a Pinguino bot or script): the Host bots replace it" } }); continue; }
                var triggers = new JArray();
                foreach (var t in (a["triggers"] as JArray ?? new JArray()).OfType<JObject>())
                {
                    int ty = (int?)t["type"] ?? 0; string perm = "everyone";
                    switch (ty)
                    {
                        case 401:
                            JObject c; if (!cmdById.TryGetValue((string)t["commandId"] ?? "", out c) || (int?)c["mode"] == 1) break;
                            var names = ((string)c["command"] ?? "").Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries).Select(x => x.Trim()).Where(x => x.StartsWith("!")).ToList();
                            if (names.Count == 0 || names.All(n => coreCmds.Contains(n))) break;
                            perm = Perm(c["permittedGroups"] == null ? "" : c["permittedGroups"].ToString(Newtonsoft.Json.Formatting.None));
                            triggers.Add(new JObject { { "type", "command" }, { "names", new JArray(names) }, { "permission", perm }, { "cooldownSec", (int?)c["globalCooldown"] ?? 0 }, { "userCooldownSec", (int?)c["userCooldown"] ?? 0 } }); break;
                        case 101: triggers.Add(new JObject { { "type", "follow" } }); break;
                        case 102: triggers.Add(new JObject { { "type", "cheer" }, { "min", (int?)t["min"] ?? -1 }, { "max", (int?)t["max"] ?? -1 } }); break;
                        case 103: triggers.Add(new JObject { { "type", "sub" } }); break;
                        case 104: triggers.Add(new JObject { { "type", "resub" } }); break;
                        case 105: triggers.Add(new JObject { { "type", "gift" }, { "min", (int?)t["min"] ?? -1 } }); break;
                        case 107: triggers.Add(new JObject { { "type", "raid" }, { "min", (int?)t["min"] ?? -1 } }); break;
                        case 154: triggers.Add(new JObject { { "type", "stream_online" } }); break;
                        case 155: triggers.Add(new JObject { { "type", "stream_offline" } }); break;
                        case 112: { string rid = (string)t["rewardId"] ?? ""; string title; if (rewardTitle.TryGetValue(rid, out title)) triggers.Add(new JObject { { "type", "redeem" }, { "title", title } }); break; }
                    }
                }
                if (triggers.Count == 0 && !subs.Any(s => (int?)s["type"] == 4) && (a["triggers"] as JArray ?? new JArray()).Count > 0) { skipped.Add(new JObject { { "name", name }, { "why", "its trigger has no equivalent yet (or the bots own the command)" } }); continue; }
                if (triggers.Count == 0 && (a["triggers"] as JArray ?? new JArray()).Count == 0 && subs.Count == 0) { skipped.Add(new JObject { { "name", name }, { "why", "empty action" } }); continue; }
                var steps = new JArray(); int gaps = 0;
                foreach (var s in subs)
                {
                    int ty = (int?)s["type"] ?? 0;
                    switch (ty)
                    {
                        case 10: case 23: steps.Add(new JObject { { "type", "say" }, { "as", "core" }, { "text", Conv((string)s["text"]) } }); break;
                        case 1002: steps.Add(new JObject { { "type", "delay" }, { "ms", (int?)s["value"] ?? 1000 } }); break;
                        case 1: steps.Add(new JObject { { "type", "sound" }, { "file", (string)s["soundFile"] ?? "" }, { "volume", (double?)s["volume"] ?? 1.0 } }); break;
                        case 4: { string tn; if (nameById.TryGetValue((string)s["actionId"] ?? "", out tn)) steps.Add(new JObject { { "type", "run_action" }, { "name", tn } }); else { gaps++; steps.Add(new JObject { { "type", "comment" }, { "text", "[import] run action: target not found" } }); } break; }
                        case 123: steps.Add(new JObject { { "type", "set_var" }, { "name", (string)s["variableName"] ?? "" }, { "value", Conv((string)s["value"]) } }); break;
                        case 1009: break;   // a comment in Streamer.bot
                        default: gaps++; steps.Add(new JObject { { "type", "comment" }, { "text", "[import] Streamer.bot sub-action " + ty + " was not converted" } }); break;
                    }
                }
                made.Add(new JObject {
                    { "id", string.IsNullOrEmpty((string)a["id"]) ? Guid.NewGuid().ToString("N").Substring(0, 10) : (string)a["id"] }, { "name", name }, { "group", (string)a["group"] ?? "Imported" }, { "enabled", false }, { "imported", true },
                    { "triggers", triggers }, { "conditions", new JArray() }, { "steps", steps }, { "importNotes", gaps == 0 ? "converted fully" : gaps + " step(s) need a manual rebuild" } });
                imported.Add(new JObject { { "name", name }, { "triggers", triggers.Count }, { "steps", steps.Count }, { "gaps", gaps } });
            }

            int added = 0;
            if (apply)
            {
                var doc = Auto.Doc(); var acts = (JArray)doc["actions"]; var have = new HashSet<string>(acts.OfType<JObject>().Select(x => ((string)x["name"] ?? "").ToLowerInvariant()));
                foreach (var m in made) if (have.Add(((string)m["name"]).ToLowerInvariant())) { acts.Add(m); added++; }
                string err = Auto.Save(doc); if (err != null) return new JObject { { "ok", false }, { "error", err } };
            }
            return new JObject { { "ok", true }, { "folder", dir }, { "mode", apply ? "merge" : "preview" }, { "importable", made.Count }, { "added", added }, { "imported", imported }, { "skipped", skipped },
                { "note", apply ? "Added disabled. Review each one on the Actions & Events page, then enable it." : "Preview only. Send mode:\"merge\" to add them (disabled) to Actions & Events." } };
        }
    }
}
