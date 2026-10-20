using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PinguinoHost
{
    /// <summary>The live OBS tree for the Master View (Plan 6): scenes with folders, and the sources of a scene with live visibility, groups nested.
    /// GET /api/obs/tree[?scene=X], POST /api/obs/scene {scene}, POST /api/obs/item {scene,itemId,enabled|toggle}. Everything is looked up by scene name + item id,
    /// never by label, and only names OBS really reports are accepted. Folders: scene-name prefixes ("A / B", "[tag] x", "A - B" when 2+ scenes share the prefix)
    /// plus overrides in Data\config\obs_folders.json {"scenes":{"Scene":"Folder"}}; real OBS source Groups are nested in the item list. OBS offline -> {connected:false}.</summary>
    public static class ObsTree
    {
        static readonly object L = new object();
        static JObject _scenes; static DateTime _scenesAt = DateTime.MinValue;
        static readonly Dictionary<string, KeyValuePair<DateTime, JArray>> _items = new Dictionary<string, KeyValuePair<DateTime, JArray>>();
        const double CacheSec = 2.0;
        static string FoldersP { get { return Path.Combine(HostApi.DataDir, "config", "obs_folders.json"); } }
        static string TreeP { get { return Path.Combine(HostApi.DataDir, "runtime", "obs_tree.json"); } }

        /// <summary>folder + label for a scene name; sharedDash = the "A - B" prefixes that two or more scenes use.</summary>
        public static void Split(string name, ISet<string> sharedDash, out string folder, out string label)
        {
            folder = ""; label = name; name = name ?? "";
            int i = name.IndexOf(" / ", StringComparison.Ordinal);
            if (i > 0 && i + 3 < name.Length) { folder = name.Substring(0, i).Trim(); label = name.Substring(i + 3).Trim(); return; }
            if (name.StartsWith("[")) { int j = name.IndexOf(']'); if (j > 1 && j + 1 < name.Length && name.Substring(j + 1).Trim() != "") { folder = name.Substring(0, j + 1); label = name.Substring(j + 1).Trim(); return; } }
            i = name.IndexOf(" - ", StringComparison.Ordinal);
            if (i > 0 && i + 3 < name.Length && sharedDash != null && sharedDash.Contains(name.Substring(0, i).Trim())) { folder = name.Substring(0, i).Trim(); label = name.Substring(i + 3).Trim(); }
        }

        static JObject Overrides() { try { return File.Exists(FoldersP) ? JObject.Parse(File.ReadAllText(FoldersP)) : new JObject(); } catch (Exception) { return new JObject(); } }

        static JObject SceneList(bool fresh)
        {
            lock (L)
            {
                if (!fresh && _scenes != null && (DateTime.UtcNow - _scenesAt).TotalSeconds < CacheSec) return _scenes;
                var d = Program.ObsData("GetSceneList", null); if (d == null) { _scenes = null; return null; }
                _scenes = d; _scenesAt = DateTime.UtcNow; return d;
            }
        }

        static JArray ItemsOf(string sceneOrGroup, bool group, bool fresh)
        {
            string key = (group ? "g:" : "s:") + sceneOrGroup;
            lock (L)
            {
                KeyValuePair<DateTime, JArray> c;
                if (!fresh && _items.TryGetValue(key, out c) && (DateTime.UtcNow - c.Key).TotalSeconds < CacheSec) return c.Value;
            }
            var d = Program.ObsData(group ? "GetGroupSceneItemList" : "GetSceneItemList", new JObject { { "sceneName", sceneOrGroup } });
            var raw = d == null ? null : d["sceneItems"] as JArray; if (raw == null) return null;
            var list = new JArray();
            foreach (var it in raw.OfType<JObject>().OrderByDescending(x => (int?)x["sceneItemIndex"] ?? 0))   // OBS lists bottom-first; the panel shows top-first
            {
                bool isGroup = (bool?)it["isGroup"] == true; string name = (string)it["sourceName"] ?? "";
                var o = new JObject { { "id", (int?)it["sceneItemId"] ?? 0 }, { "name", name }, { "kind", (string)it["inputKind"] ?? (isGroup ? "group" : (string)it["sourceType"] ?? "") }, { "enabled", (bool?)it["sceneItemEnabled"] == true }, { "group", isGroup } };
                if (isGroup) o["children"] = ItemsOf(name, true, fresh) ?? new JArray();
                list.Add(o);
            }
            lock (L) _items[key] = new KeyValuePair<DateTime, JArray>(DateTime.UtcNow, list);
            return list;
        }

        /// <summary>the tree for the Master View: every scene (with folder) and the items of one scene (default: the live one).</summary>
        public static JObject Get(string scene)
        {
            var sl = SceneList(false);
            if (sl == null) return new JObject { { "connected", false }, { "scenes", new JArray() }, { "folders", new JArray() }, { "items", new JArray() } };
            string current = (string)sl["currentProgramSceneName"] ?? "";
            var names = (sl["scenes"] as JArray ?? new JArray()).OfType<JObject>().OrderByDescending(s => (int?)s["sceneIndex"] ?? 0).Select(s => (string)s["sceneName"] ?? "").Where(s => s != "").ToList();
            var dash = new HashSet<string>(names.Where(n => n.IndexOf(" - ", StringComparison.Ordinal) > 0).GroupBy(n => n.Substring(0, n.IndexOf(" - ", StringComparison.Ordinal)).Trim()).Where(g => g.Count() >= 2).Select(g => g.Key));
            var ov = (Overrides()["scenes"] as JObject) ?? new JObject();
            var scenes = new JArray(); var folders = new List<string>();
            foreach (var n in names)
            {
                string f, l; Split(n, dash, out f, out l); var o = ov[n]; if (o != null) { f = (string)o ?? ""; l = n; }
                if (f != "" && !folders.Contains(f)) folders.Add(f);
                scenes.Add(new JObject { { "name", n }, { "folder", f }, { "label", l }, { "current", n == current } });
            }
            string want = string.IsNullOrEmpty(scene) ? current : scene;
            var items = names.Contains(want) ? ItemsOf(want, false, false) : null;
            var res = new JObject { { "connected", true }, { "current", current }, { "scene", want }, { "scenes", scenes }, { "folders", new JArray(folders) }, { "items", items ?? new JArray() } };
            try { Directory.CreateDirectory(Path.GetDirectoryName(TreeP)); File.WriteAllText(TreeP, new JObject { { "ts", DateTimeOffset.UtcNow.ToUnixTimeSeconds() }, { "connected", true }, { "current", current }, { "scenes", scenes }, { "folders", new JArray(folders) }, { "items", items ?? new JArray() } }.ToString(Newtonsoft.Json.Formatting.None)); } catch (Exception) { }   // the bot's BuildObsState reads this
            return res;
        }

        public static JObject SetScene(string scene)
        {
            var sl = SceneList(true); if (sl == null) return Err("OBS is not connected");
            bool known = (sl["scenes"] as JArray ?? new JArray()).Any(s => (string)s["sceneName"] == scene);
            if (!known) return Err("OBS has no scene called that");
            bool ok = Program.ObsRaw("SetCurrentProgramScene", new JObject { { "sceneName", scene } });
            if (ok) lock (L) _scenesAt = DateTime.MinValue;
            ChannelControl.Audit("obs", "scene", scene + " ok=" + ok);
            return ok ? new JObject { { "ok", true } } : Err("OBS refused the scene change");
        }

        static bool HasItem(JArray list, int id) { return list != null && list.OfType<JObject>().Any(o => (int)o["id"] == id || HasItem(o["children"] as JArray, id)); }
        static string GroupHolding(JArray list, int id, string scene)
        {
            foreach (var o in list.OfType<JObject>()) { if ((int)o["id"] == id) return scene; var ch = o["children"] as JArray; if (ch != null) { var g = GroupHolding(ch, id, (string)o["name"]); if (g != null) return g; } }
            return null;
        }

        /// <summary>show/hide/toggle one item of a scene; the id must be in that scene (or in one of its groups) right now.</summary>
        public static JObject SetItem(string scene, int itemId, bool? enabled, bool toggle)
        {
            var sl = SceneList(true); if (sl == null) return Err("OBS is not connected");
            if (!(sl["scenes"] as JArray ?? new JArray()).Any(s => (string)s["sceneName"] == scene)) return Err("OBS has no scene called that");
            var items = ItemsOf(scene, false, true); string holder = items == null ? null : GroupHolding(items, itemId, scene);
            if (holder == null) return Err("that source is not in the scene");
            bool target;
            if (toggle || enabled == null)
            {
                var cur = Program.ObsData("GetSceneItemEnabled", new JObject { { "sceneName", holder }, { "sceneItemId", itemId } });
                if (cur == null) return Err("OBS did not answer"); target = (bool?)cur["sceneItemEnabled"] != true;
            }
            else target = enabled.Value;
            bool ok = Program.ObsRaw("SetSceneItemEnabled", new JObject { { "sceneName", holder }, { "sceneItemId", itemId }, { "sceneItemEnabled", target } });
            if (ok) lock (L) _items.Clear();
            ChannelControl.Audit("obs", "item", scene + "#" + itemId + " enabled=" + target + " ok=" + ok);
            return ok ? new JObject { { "ok", true }, { "enabled", target } } : Err("OBS refused the change");
        }

        static JObject Err(string m) { return new JObject { { "ok", false }, { "error", m } }; }
    }
}
