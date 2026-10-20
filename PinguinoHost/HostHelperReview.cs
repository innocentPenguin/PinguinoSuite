using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>Browse the helper's PRIVATE review log (Data\helper\review.jsonl, written by HelperPinguino): every answer and every probably-missed question with the chat
    /// before and after it, plus a note field for Ivan (Data\helper\review_notes.json). Local only: the routes refuse anything that is not loopback; nothing is pushed to the site.</summary>
    public static class HelperReview
    {
        static readonly object L = new object();
        static string Root { get { string d = HostApi.DataDir.TrimEnd('\\', '/'); return string.Equals(Path.GetFileName(d), "runtime", StringComparison.OrdinalIgnoreCase) ? (Path.GetDirectoryName(d) ?? d) : d; } }
        static string Dir { get { var d = Path.Combine(Root, "helper"); Directory.CreateDirectory(d); return d; } }
        static string NotesPath { get { return Path.Combine(Dir, "review_notes.json"); } }

        static JObject Notes()
        {
            try { if (File.Exists(NotesPath)) return JObject.Parse(File.ReadAllText(NotesPath, Encoding.UTF8)); } catch (Exception) { }
            return new JObject();
        }

        /// <summary>newest first. kind = "" | answered | missed; q filters on user / text / reply / reason / note; limit 0 = 100.</summary>
        public static JObject List(string kind, string q, int limit)
        {
            if (limit <= 0) limit = 100; if (limit > 1000) limit = 1000;
            kind = (kind ?? "").Trim().ToLowerInvariant(); q = (q ?? "").Trim().ToLowerInvariant();
            lock (L)
            {
                var triggers = new List<JObject>(); var after = new Dictionary<string, JArray>(); var notes = Notes();
                string f = Path.Combine(Dir, "review.jsonl");
                if (File.Exists(f))
                {
                    using (var fs = new FileStream(f, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                    using (var sr = new StreamReader(fs, Encoding.UTF8))
                    {
                        string line;
                        while ((line = sr.ReadLine()) != null)
                        {
                            if (line.Length < 5) continue;
                            JObject r; try { r = JObject.Parse(line.TrimStart('﻿')); } catch (Exception) { continue; }
                            string type = (string)r["type"], id = (string)r["id"] ?? "";
                            if (type == "trigger") triggers.Add(r);
                            else if (type == "after") { JArray a; if (!after.TryGetValue(id, out a)) after[id] = a = new JArray(); a.Add(new JObject { { "at", r["at"] }, { "u", r["u"] }, { "t", r["t"] } }); }
                        }
                    }
                }
                var rows = new List<JObject>(); int missed = 0, answered = 0;
                foreach (var t in Enumerable.Reverse(triggers))
                {
                    string id = (string)t["id"]; string k = (string)t["kind"];
                    if (k == "missed") missed++; else answered++;
                    if (kind != "" && k != kind) continue;
                    t["after"] = after.ContainsKey(id) ? after[id] : new JArray();
                    t["note"] = (string)notes[id] ?? "";
                    t["iso"] = DateTimeOffset.FromUnixTimeSeconds((long?)t["at"] ?? 0).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ");
                    if (q != "" && !(t.ToString(Newtonsoft.Json.Formatting.None)).ToLowerInvariant().Contains(q)) continue;
                    if (rows.Count < limit) rows.Add(t);
                }
                return new JObject { { "ok", true }, { "private", true }, { "total", triggers.Count }, { "answered", answered }, { "missed", missed }, { "shown", rows.Count }, { "entries", new JArray(rows) } };
            }
        }

        public static JObject SetNote(string id, string note)
        {
            id = (id ?? "").Trim(); if (id.Length == 0 || id.Length > 40) return new JObject { { "ok", false }, { "error", "no id" } };
            note = (note ?? "").Trim(); if (note.Length > 1000) note = note.Substring(0, 1000);
            lock (L)
            {
                var n = Notes(); if (note == "") n.Remove(id); else n[id] = note;
                File.WriteAllText(NotesPath, n.ToString(), Encoding.UTF8);
            }
            return new JObject { { "ok", true }, { "id", id }, { "note", note } };
        }
    }
}
