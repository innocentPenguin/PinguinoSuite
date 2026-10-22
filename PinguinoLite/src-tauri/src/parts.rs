// Per-part updates for Lite: a thin wrapper around the shared Node updater (Suite/updater/updater.mjs), same contract as the Suite core (suite/updates.py).
// The updater does the hard parts: manifest.components hashes, sha256 on every file, safeRel path rules (no .., drives, Data\ or secrets), backup before each swap,
// rollback, one update at a time (lock file). Lite adds: which parts it may touch, stop/start of the Link it owns around a swap, refusing while live, no OBS contact.
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use serde_json::{json, Value};
use tauri::{AppHandle, Manager};

/// Parts Lite hosts: the bundled Link, Lite's own app files, and scripts/docs. Anything else in a release (shell, core, Host, listen, ...) belongs to the Suite.
pub const LITE_PARTS: &[&str] = &["link", "lite", "tools"];
/// App parts are staged and swapped by the updater's `launch` step before the next start (never under a running exe).
/// On-demand modules: present on a full install, absent on a "lite-minimal" one until the user clicks Install. (voice is hidden in Lite.)
pub const MODULE_PARTS: &[&str] = &["listen", "multi", "spotify"];
/// Install profiles, same table as Suite/updater/lib/profiles.mjs. None = every part.
pub fn profile_parts(profile: &str) -> Option<Vec<String>> {
    match profile {
        "lite-minimal" => Some(["lite", "link", "tools"].iter().map(|s| s.to_string()).collect()),
        _ => None,
    }
}
/// Parts an install keeps: explicit `parts` in install.json, else its profile, else None (= all).
pub fn installed_parts(inst: &Value) -> Option<Vec<String>> {
    if let Some(a) = inst["parts"].as_array() {
        return Some(a.iter().filter_map(|v| v.as_str().map(String::from)).collect());
    }
    inst["profile"].as_str().and_then(profile_parts)
}
pub fn is_installed(parts: &Option<Vec<String>>, id: &str) -> bool {
    parts.as_ref().map(|p| p.iter().any(|x| x == id)).unwrap_or(true)
}
fn module_name(id: &str) -> &'static str {
    match id {
        "listen" => "Listen",
        "multi" => "Multi",
        "spotify" => "Spotify",
        _ => "",
    }
}

pub const STAGED_PARTS: &[&str] = &["lite"];

static JOB: Mutex<Option<Value>> = Mutex::new(None);

// ---------- pure helpers (unit-tested) ----------

pub fn allowed_parts(ids: &[String]) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for i in ids {
        if (LITE_PARTS.contains(&i.as_str()) || MODULE_PARTS.contains(&i.as_str())) && !out.contains(i) {
            out.push(i.clone());
        }
    }
    out
}

/// The updater prints one JSON line; take the last line that parses as an object.
pub fn last_json(stdout: &str) -> Option<Value> {
    stdout.lines().rev().map(str::trim).filter(|l| l.starts_with('{')).find_map(|l| serde_json::from_str::<Value>(l).ok())
}

/// Keep only the parts Lite hosts, in a compact shape for the UI.
pub fn lite_view(check: &Value) -> Value {
    let parts: Vec<Value> = check["components"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter(|c| c["optional"] != true && c["installed"] != false)
                .filter(|c| c["id"].as_str().map(|i| LITE_PARTS.contains(&i) || MODULE_PARTS.contains(&i)).unwrap_or(false))
                .map(|c| {
                    json!({"id": c["id"], "name": c["name"], "changed": c["changed"].as_bool().unwrap_or(false), "files": c["files"], "bytes": c["bytes"],
                           "staged": c["id"].as_str().map(|i| STAGED_PARTS.contains(&i)).unwrap_or(false)})
                })
                .collect()
        })
        .unwrap_or_default();
    json!({"ok": check["ok"].as_bool().unwrap_or(false), "message": check["message"], "version": check["version"], "notes": check["notes"], "parts": parts,
           "any_changed": parts.iter().any(|p| p["changed"] == true)})
}

/// Fail safe: only an explicit "not live" lets an update through (Host not running counts as not live; an unreadable answer does not).
pub fn may_update(live: Option<bool>) -> Result<(), &'static str> {
    match live {
        Some(false) => Ok(()),
        Some(true) => Err("You are live. Updates wait until the stream is over."),
        None => Err("Could not tell whether you are live, so updates are held. Try again in a moment."),
    }
}

// ---------- environment ----------

/// A release install = a folder with install.json: env PINGUINO_LITE_INSTALL, else the suite root, else the folder of the exe.
fn install_dir() -> Option<PathBuf> {
    let mut c: Vec<PathBuf> = Vec::new();
    if let Ok(p) = std::env::var("PINGUINO_LITE_INSTALL") {
        c.push(PathBuf::from(p));
    }
    if let Some(r) = crate::suite_root() {
        c.push(r);
    }
    if let Some(d) = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.to_path_buf())) {
        c.push(d);
    }
    c.into_iter().find(|d| d.join("install.json").is_file())
}

fn updater_js(install: &PathBuf) -> Option<PathBuf> {
    let mut c = vec![install.join("Suite").join("updater").join("updater.mjs"), install.join("updater").join("updater.mjs")];
    if let Some(d) = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("updater").join("updater.mjs"))) {
        c.push(d);
    }
    c.into_iter().find(|p| p.is_file())
}

fn node_exe(install: &PathBuf) -> String {
    let mut c: Vec<PathBuf> = vec![install.join("node.exe")];
    if let Some(d) = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("node.exe"))) {
        c.push(d);
    }
    c.into_iter().find(|p| p.is_file()).map(|p| p.to_string_lossy().into_owned()).unwrap_or_else(|| "node".into())
}

fn run_updater(args: &[&str]) -> Value {
    let Some(install) = install_dir() else { return json!({"ok": false, "message": "This copy has no install.json (development build), so it does not update itself."}) };
    let Some(js) = updater_js(&install) else { return json!({"ok": false, "message": "The updater (updater.mjs) was not found next to this install."}) };
    let mut cmd = Command::new(node_exe(&install));
    cmd.arg(&js).args(args).arg("--install").arg(&install).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    match cmd.output() {
        Ok(o) => last_json(&String::from_utf8_lossy(&o.stdout))
            .unwrap_or_else(|| json!({"ok": false, "message": String::from_utf8_lossy(&o.stderr).trim().chars().take(200).collect::<String>()})),
        Err(_) => json!({"ok": false, "message": "Node.js was not found; updates are unavailable."}),
    }
}

/// GET /api/live on the Host: Some(live), or None when it cannot be told. Connection refused = Host not running = not live.
fn host_is_live() -> Option<bool> {
    use std::io::{Read, Write};
    let addr = std::net::SocketAddr::from(([127, 0, 0, 1], 8770));
    let mut s = match std::net::TcpStream::connect_timeout(&addr, Duration::from_millis(800)) {
        Ok(s) => s,
        Err(e) => return if e.kind() == std::io::ErrorKind::ConnectionRefused { Some(false) } else { None },
    };
    s.set_read_timeout(Some(Duration::from_millis(2000))).ok()?;
    s.write_all(b"GET /api/live HTTP/1.1\r\nHost: 127.0.0.1:8770\r\nConnection: close\r\n\r\n").ok()?;
    let mut buf = Vec::new();
    s.take(256 * 1024).read_to_end(&mut buf).ok()?;
    let t = String::from_utf8_lossy(&buf);
    let v: Value = serde_json::from_str(t.split_once("\r\n\r\n")?.1.trim()).ok()?;
    v["live"].as_bool()
}

// ---------- commands ----------

#[tauri::command]
pub async fn parts_check() -> Value {
    let mut v = lite_view(&run_updater(&["check"]));
    v["supported"] = json!(install_dir().is_some());
    v["live"] = json!(host_is_live());
    v
}

#[tauri::command]
pub fn parts_job() -> Value {
    JOB.lock().unwrap_or_else(|e| e.into_inner()).clone().unwrap_or_else(|| json!({"state": "idle"}))
}

fn set_job(v: Value) {
    *JOB.lock().unwrap_or_else(|e| e.into_inner()) = Some(v);
}

/// Stop the Link Lite owns (returns true when there was one), so its files can be swapped.
fn pause_link(app: &AppHandle) -> bool {
    let had = app.state::<crate::Link>().0.lock().unwrap().is_some();
    if had {
        crate::stop_link(app);
        std::thread::sleep(Duration::from_secs(2)); // let Windows release file locks
    }
    had
}

fn resume_link(app: &AppHandle, had: bool) {
    if had {
        *app.state::<crate::Link>().0.lock().unwrap() = crate::spawn_link(&app.package_info().version.to_string());
    }
}

fn start_job(kind: &str, parts: &[String], f: impl FnOnce() -> Value + Send + 'static) -> Value {
    {
        let mut j = JOB.lock().unwrap_or_else(|e| e.into_inner());
        if j.as_ref().map(|v| v["state"] == "running").unwrap_or(false) {
            return json!({"ok": false, "message": "an update is already running"});
        }
        *j = Some(json!({"state": "running", "kind": kind, "parts": parts, "message": "working"}));
    }
    let kind = kind.to_string();
    std::thread::spawn(move || {
        let r = f();
        set_job(json!({"state": "done", "kind": kind, "ok": r["ok"].as_bool().unwrap_or(false), "message": r["message"], "result": r}));
    });
    json!({"ok": true})
}

#[tauri::command]
pub fn parts_apply(app: AppHandle, ids: Vec<String>) -> Value {
    let parts = allowed_parts(&ids);
    if parts.is_empty() {
        return json!({"ok": false, "message": "pick at least one part to update"});
    }
    if let Err(m) = may_update(host_is_live()) {
        return json!({"ok": false, "message": m});
    }
    // Link run by the Suite (not started by Lite) is the Suite's to update: Lite never stops what it did not start
    if parts.iter().any(|p| p == "link") && app.state::<crate::Link>().0.lock().unwrap().is_none() {
        return json!({"ok": false, "message": "PinguinoLink is being run by the Suite, not by Lite. Update it from the Suite."});
    }
    let ps = parts.clone();
    start_job("apply", &parts, move || {
        let mut last = json!({"ok": true, "message": "nothing to do"});
        for id in &ps {
            let stage = STAGED_PARTS.contains(&id.as_str());
            let had = if id == "link" { pause_link(&app) } else { false };
            let mut args = vec!["apply", "--only", id.as_str()];
            if stage {
                args.push("--stage");
            }
            let r = run_updater(&args);
            resume_link(&app, had); // always start Link again, whether the swap worked or was rolled back
            let ok = r["ok"].as_bool().unwrap_or(false);
            last = if stage && ok { json!({"ok": true, "message": format!("{id} is verified and staged; it is applied the next time Lite starts"), "staged": true}) } else { r };
            if !ok {
                break;
            }
        }
        last
    })
}

#[tauri::command]
pub fn parts_rollback(app: AppHandle) -> Value {
    if let Err(m) = may_update(host_is_live()) {
        return json!({"ok": false, "message": m});
    }
    let plan = run_updater(&["rollback", "--plan"]);
    if plan["ok"] != true {
        return json!({"ok": false, "message": plan["message"]});
    }
    let touches_link = plan["components"].as_array().map(|a| a.iter().any(|c| c == "link")).unwrap_or(false);
    if touches_link && app.state::<crate::Link>().0.lock().unwrap().is_none() {
        return json!({"ok": false, "message": "The last update included PinguinoLink, which the Suite runs. Roll back from the Suite."});
    }
    start_job("rollback", &[], move || {
        let had = touches_link && pause_link(&app);
        let r = run_updater(&["rollback"]);
        resume_link(&app, had);
        r
    })
}

fn read_install() -> Value {
    install_dir()
        .and_then(|d| std::fs::read(d.join("install.json")).ok())
        .map(|b| String::from_utf8_lossy(&b).trim_start_matches('\u{feff}').to_string())
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or(Value::Null)
}

/// The on-demand modules and whether this install has them. Nothing here downloads anything.
#[tauri::command]
pub fn parts_modules() -> Value {
    let inst = read_install();
    let parts = installed_parts(&inst);
    let mods: Vec<Value> = MODULE_PARTS.iter().map(|id| json!({"id": id, "name": module_name(id), "installed": is_installed(&parts, id)})).collect();
    json!({"supported": install_dir().is_some(), "profile": inst["profile"].as_str().unwrap_or("full"), "modules": mods, "link": is_installed(&parts, "link"), "live": host_is_live()})
}

/// Read-only integrity check of installed parts against the release (hashes from the shared updater). Not blocked by live: it changes nothing.
#[tauri::command]
pub fn parts_verify(ids: Vec<String>) -> Value {
    let parts = installed_parts(&read_install());
    let ids: Vec<String> = allowed_parts(&ids).into_iter().filter(|i| is_installed(&parts, i)).collect();
    if ids.is_empty() {
        return json!({"ok": false, "message": "nothing installed to verify"});
    }
    let list = ids.join(",");
    start_job("verify", &ids, move || run_updater(&["verify", "--only", &list]))
}

/// Take an on-demand module out: stop it (via Link), then the updater MOVES its files aside (never deletes). Reversible with Install.
#[tauri::command]
pub fn parts_eject(app: AppHandle, id: String) -> Value {
    if !MODULE_PARTS.contains(&id.as_str()) {
        return json!({"ok": false, "message": "only on-demand modules can be taken out"});
    }
    if !is_installed(&installed_parts(&read_install()), &id) {
        return json!({"ok": false, "message": format!("{} is not installed", module_name(&id))});
    }
    if let Err(m) = may_update(host_is_live()) {
        return json!({"ok": false, "message": m});
    }
    start_job("eject", &[id.clone()], move || {
        crate::request_module(app, "stop", &id); // best effort: Link stops the module before its files move
        std::thread::sleep(Duration::from_secs(3));
        run_updater(&["eject", "--only", &id])
    })
}

/// Fetch an on-demand module on request (only ever called from the Install button). The module is not started; start it from Modules.
#[tauri::command]
pub fn parts_install(id: String) -> Value {
    if !MODULE_PARTS.contains(&id.as_str()) {
        return json!({"ok": false, "message": "unknown module"});
    }
    if is_installed(&installed_parts(&read_install()), &id) {
        return json!({"ok": false, "message": format!("{} is already installed", module_name(&id))});
    }
    if let Err(m) = may_update(host_is_live()) {
        return json!({"ok": false, "message": m});
    }
    start_job("install", &[id.clone()], move || run_updater(&["install", "--only", &id]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_lite_parts_pass() {
        let ids: Vec<String> = ["link", "shell", "listen", "lite", "link", "../x", "tools"].iter().map(|s| s.to_string()).collect();
        assert_eq!(allowed_parts(&ids), vec!["link", "listen", "lite", "tools"]);
        assert!(allowed_parts(&["voice".to_string()]).is_empty());
    }

    #[test]
    fn updater_output_is_the_last_json_line() {
        assert_eq!(last_json("noise\n{\"ok\":false}\n{\"ok\":true,\"x\":1}\n").unwrap()["x"], 1);
        assert!(last_json("no json here").is_none());
    }

    #[test]
    fn view_keeps_lite_parts_and_marks_staged() {
        let c = json!({"ok": true, "version": "0.2.0", "notes": "n", "components": [
            {"id": "shell", "name": "App shell", "changed": true}, {"id": "link", "name": "Link", "changed": true, "files": 3, "bytes": 99},
            {"id": "lite", "name": "Lite", "changed": false}, {"id": "voice", "changed": true}]});
        let v = lite_view(&c);
        let ids: Vec<&str> = v["parts"].as_array().unwrap().iter().map(|p| p["id"].as_str().unwrap()).collect();
        assert_eq!(ids, vec!["link", "lite"]);
        assert_eq!(v["any_changed"], true);
        assert_eq!(v["parts"][1]["staged"], true);
        assert_eq!(v["parts"][0]["staged"], false);
        assert_eq!(lite_view(&json!({"ok": false, "message": "no source"}))["any_changed"], false);
    }

    #[test]
    fn profiles_decide_what_is_installed() {
        let full = installed_parts(&json!({"version": "1"}));
        assert!(full.is_none() && is_installed(&full, "spotify"));
        let min = installed_parts(&json!({"profile": "lite-minimal"}));
        assert!(is_installed(&min, "link") && is_installed(&min, "lite") && !is_installed(&min, "spotify") && !is_installed(&min, "multi"));
        // explicit parts win over the profile (after an Install or Eject)
        let p = installed_parts(&json!({"profile": "lite-minimal", "parts": ["lite", "link", "tools", "spotify"]}));
        assert!(is_installed(&p, "spotify") && !is_installed(&p, "listen"));
        // not-installed modules never show up as updates
        let c = json!({"ok": true, "components": [{"id": "spotify", "optional": true, "installed": false, "changed": true}, {"id": "link", "changed": true}]});
        assert_eq!(lite_view(&c)["parts"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn live_gate_fails_safe() {
        assert!(may_update(Some(false)).is_ok());
        assert!(may_update(Some(true)).is_err());
        assert!(may_update(None).is_err());
    }
}
