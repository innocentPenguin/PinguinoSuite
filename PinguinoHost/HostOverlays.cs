using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The overlay folder as a managed place (Plan 6 part C): list, read, write, rename, delete-to-trash. Everything is confined to ONE root (settings.json OverlayDir,
    /// else PinguinoB0t\overlays); paths are relative, forward-slash, no "..", no drive letters, extension allow-list, size caps, no settings/secrets files, and the trash folder is
    /// invisible. Every change is backed up to Data\runtime\overlay_trash\&lt;time&gt;\ and audit-logged (Data\runtime\mod_audit.log). Routes in HostAutoApi: GET /api/overlays,
    /// GET /api/overlays/file?path=, POST /api/overlays/write | /delete | /rename (POST needs same-origin or a token like every state change).</summary>
    public static class OverlayFiles
    {
        public static string Root = "";
        static readonly HashSet<string> TextExt = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { ".html", ".css", ".js", ".json", ".svg", ".txt" };
        static readonly HashSet<string> BinExt = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { ".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".wav", ".ogg", ".webm", ".mp4", ".woff2", ".woff", ".ttf" };
        public const int MaxText = 2 * 1024 * 1024, MaxBin = 12 * 1024 * 1024, MaxFiles = 3000;
        static string TrashRoot { get { return Path.Combine(HostApi.DataDir, "runtime", "overlay_trash"); } }

        /// <summary>safe absolute path for a relative overlay path, or null (with the reason in err).</summary>
        public static string Resolve(string rel, bool needExt, out string err)
        {
            err = ""; string root = Root;
            if (string.IsNullOrEmpty(root) || !Directory.Exists(root)) { err = "no overlay folder"; return null; }
            rel = (rel ?? "").Replace('\\', '/').Trim();
            if (rel == "" || rel.StartsWith("/") || rel.Contains(":") || rel.Contains("\0") || rel.Length > 200) { err = "bad path"; return null; }
            var parts = rel.Split('/');
            foreach (var p in parts)
                if (p == "" || p == "." || p == ".." || p.EndsWith(".") || p.EndsWith(" ") || p.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0) { err = "bad path"; return null; }
            string first = parts[0].ToLowerInvariant(); if (first == "overlay_trash" || first == ".git") { err = "that folder is not available"; return null; }
            string name = parts[parts.Length - 1].ToLowerInvariant();
            if (name.Contains("secret") || name == "settings.json" || name.EndsWith(".exe") || name.EndsWith(".dll")) { err = "that file is protected"; return null; }
            if (needExt) { string ext = Path.GetExtension(name); if (!TextExt.Contains(ext) && !BinExt.Contains(ext)) { err = "file type not allowed"; return null; } }
            string full = Path.GetFullPath(Path.Combine(root, rel)), rootFull = Path.GetFullPath(root).TrimEnd('\\', '/') + Path.DirectorySeparatorChar;
            if (!full.StartsWith(rootFull, StringComparison.OrdinalIgnoreCase)) { err = "outside the overlay folder"; return null; }
            return full;
        }

        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }
        static string Rel(string full) { return full.Substring(Path.GetFullPath(Root).TrimEnd('\\', '/').Length + 1).Replace('\\', '/'); }

        public static JObject List()
        {
            if (string.IsNullOrEmpty(Root) || !Directory.Exists(Root)) return Err("no overlay folder");
            var files = new JArray(); string rootFull = Path.GetFullPath(Root);
            foreach (var f in Directory.EnumerateFiles(rootFull, "*", SearchOption.AllDirectories))
            {
                string r = Rel(f), ext = Path.GetExtension(f).ToLowerInvariant(); string e;
                if (Resolve(r, true, out e) == null) continue;
                var fi = new FileInfo(f); files.Add(new JObject { { "path", r }, { "size", fi.Length }, { "mtime", new DateTimeOffset(fi.LastWriteTimeUtc).ToUnixTimeSeconds() }, { "ext", ext }, { "text", TextExt.Contains(ext) }, { "url", "/" + Uri.EscapeUriString(r) } });
                if (files.Count >= MaxFiles) break;
            }
            return new JObject { { "ok", true }, { "root", Path.GetFileName(rootFull.TrimEnd('\\', '/')) }, { "files", new JArray(files.OrderBy(x => (string)x["path"], StringComparer.OrdinalIgnoreCase)) } };
        }

        public static JObject Read(string rel)
        {
            string e, full = Resolve(rel, true, out e); if (full == null) return Err(e);
            if (!File.Exists(full)) return Err("no such file");
            var fi = new FileInfo(full); string ext = fi.Extension.ToLowerInvariant();
            if (!TextExt.Contains(ext)) return new JObject { { "ok", true }, { "path", Rel(full) }, { "binary", true }, { "size", fi.Length } };
            if (fi.Length > MaxText) return Err("file too large to open here");
            return new JObject { { "ok", true }, { "path", Rel(full) }, { "text", File.ReadAllText(full, Encoding.UTF8) }, { "size", fi.Length }, { "mtime", new DateTimeOffset(fi.LastWriteTimeUtc).ToUnixTimeSeconds() } };
        }

        static void Backup(string full, string why)
        {
            if (!File.Exists(full)) return;
            string dest = Path.Combine(TrashRoot, DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fff") + "-" + why, Rel(full).Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(dest)); File.Copy(full, dest, true);
        }

        /// <summary>creates or replaces a file; text for text types, base64 for the rest. Replacing keeps the old copy in the trash.</summary>
        public static JObject Write(string rel, string text, string base64, string who)
        {
            string e, full = Resolve(rel, true, out e); if (full == null) return Err(e);
            string ext = Path.GetExtension(full).ToLowerInvariant(); byte[] data;
            if (TextExt.Contains(ext))
            {
                if (text == null) return Err("text required for this file type"); data = new UTF8Encoding(false).GetBytes(text); if (data.Length > MaxText) return Err("file too large (max 2 MB)");
                if (ext == ".json") { try { JToken.Parse(text); } catch (Exception) { return Err("that is not valid JSON"); } }
            }
            else
            {
                if (string.IsNullOrEmpty(base64)) return Err("base64 required for this file type");
                try { data = Convert.FromBase64String(base64); } catch (Exception) { return Err("bad base64"); }
                if (data.Length > MaxBin) return Err("file too large (max 12 MB)");
            }
            bool existed = File.Exists(full);
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(full)); Backup(full, "write");
                string tmp = full + ".tmp"; File.WriteAllBytes(tmp, data); if (existed) File.Delete(full); File.Move(tmp, full);
            }
            catch (Exception ex) { return Err("could not write: " + ex.Message); }
            ChannelControl.Audit(who, "overlay/write", Rel(full) + " bytes=" + data.Length + (existed ? " replaced" : " new"));
            return new JObject { { "ok", true }, { "path", Rel(full) }, { "created", !existed }, { "size", data.Length } };
        }

        public static JObject Delete(string rel, string who)
        {
            string e, full = Resolve(rel, true, out e); if (full == null) return Err(e);
            if (!File.Exists(full)) return Err("no such file");
            try { Backup(full, "delete"); File.Delete(full); } catch (Exception ex) { return Err("could not delete: " + ex.Message); }
            ChannelControl.Audit(who, "overlay/delete", Rel(full) + " (moved to overlay_trash)");
            return new JObject { { "ok", true } };
        }

        public static JObject Rename(string from, string to, string who)
        {
            string e, a = Resolve(from, true, out e); if (a == null) return Err(e);
            string b = Resolve(to, true, out e); if (b == null) return Err(e);
            if (!File.Exists(a)) return Err("no such file");
            if (File.Exists(b) || Directory.Exists(b)) return Err("a file with that name already exists");
            if (!string.Equals(Path.GetExtension(a), Path.GetExtension(b), StringComparison.OrdinalIgnoreCase)) return Err("keep the same file type");
            try { Directory.CreateDirectory(Path.GetDirectoryName(b)); File.Move(a, b); } catch (Exception ex) { return Err("could not rename: " + ex.Message); }
            ChannelControl.Audit(who, "overlay/rename", Rel(a) + " -> " + Rel(b));
            return new JObject { { "ok", true }, { "path", Rel(b) } };
        }
    }
}
