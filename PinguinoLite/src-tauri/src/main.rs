// PinguinoLite shell: one window (Dashboard + Modules), single-instance, remembered window placement.
// No core, no modules, no sidecars. All module logic (catalog, install, update, connect) belongs to PinguinoLink (session 04);
// this shell only reads the files 04 writes and drops request files for 04 to pick up. Contract: Docs/LITE_APP.md.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod mainwin;
mod replays;

use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use serde_json::{json, Value};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

/// PinguinoLink (session 04) is the one bundled component: Lite starts it at launch and stops it on exit.
struct Link(Mutex<Option<Child>>);

/// Folder holding Link's code + link.json ({"cmd": ["node","src/cli.mjs","lite"], "cwd": "."} relative to that folder).
/// env PINGUINO_LITE_LINK_DIR, else <exe dir>\link (installed), else <suite root>\Suite\modules\link (dev).
fn link_dir() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("PINGUINO_LITE_LINK_DIR") {
        return Some(PathBuf::from(p));
    }
    let mut c: Vec<PathBuf> = Vec::new();
    if let Some(d) = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("link"))) {
        c.push(d);
    }
    if let Some(r) = suite_root() {
        c.push(r.join("Suite").join("modules").join("link"));
    }
    c.into_iter().find(|d| d.join("link.json").exists())
}

fn spawn_link(version: &str) -> Option<Child> {
    let dir = link_dir()?;
    let cfg: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("link.json")).ok()?).ok()?;
    let argv: Vec<String> = cfg.get("cmd")?.as_array()?.iter().filter_map(|v| v.as_str().map(String::from)).collect();
    // A Link already answering on its port (e.g. the Suite's own) is reused: no second copy, and Lite never owns (so never kills) it.
    let port = cfg.get("port").and_then(|v| v.as_u64()).unwrap_or(7777) as u16;
    if TcpStream::connect_timeout(&std::net::SocketAddr::from(([127, 0, 0, 1], port)), Duration::from_millis(500)).is_ok() {
        return None;
    }
    let (exe, args) = argv.split_first()?;
    let cwd = dir.join(cfg.get("cwd").and_then(|v| v.as_str()).unwrap_or("."));
    let ld = lite_dir();
    let _ = std::fs::create_dir_all(&ld);
    // "node" resolves to a bundled node.exe (next to link\ or next to the Lite exe) before falling back to PATH
    let bundled = if exe == "node" {
        let mut c = vec![dir.parent().map(|p| p.join("node.exe"))];
        c.push(std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join("node.exe"))));
        c.into_iter().flatten().find(|p| p.exists())
    } else {
        None
    };
    let mut cmd = Command::new(bundled.unwrap_or_else(|| PathBuf::from(exe)));
    cmd.args(args).current_dir(cwd).env("PINGUINO_LITE_DIR", &ld).env("PINGUINO_LITE_VERSION", version).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn().ok()
}

fn stop_link(app: &AppHandle) {
    if let Some(mut c) = app.state::<Link>().0.lock().unwrap().take() {
        let _ = c.kill();
        let _ = c.wait();
    }
}

const HOST: &str = "127.0.0.1:8770";

/// Contract files 04 writes into <lite dir>. Only these names can be read by the UI.
const CONTRACT_FILES: &[&str] = &["modules_catalog", "installed", "update_manifest", "update_status", "status"];
/// Actions the UI may ask 04 for (request files, see send_request).
const ACTIONS: &[&str] = &["install", "update", "uninstall", "rollback", "start", "stop", "restart", "check", "selfupdate-apply", "restart-link"];

/// Per-device UI state (window placement). Own folder, never shared with the full app.
pub fn state_dir() -> PathBuf {
    if let Ok(p) = std::env::var("PINGUINO_LITE_STATE") {
        return PathBuf::from(p);
    }
    std::env::var("APPDATA").map(|a| PathBuf::from(a).join("gg.pinguino.lite")).unwrap_or_else(|_| std::env::temp_dir().join("PinguinoLite"))
}

/// The suite root (folder holding Suite/suite/suite.py): env, then <state dir>/suite_root.txt, then walking up from the exe / source folder.
pub fn suite_root() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("PINGUINO_SUITE_ROOT") {
        return Some(PathBuf::from(p));
    }
    if let Ok(t) = std::fs::read_to_string(state_dir().join("suite_root.txt")) {
        let p = PathBuf::from(t.trim());
        if p.join("Suite").join("suite").join("suite.py").exists() {
            return Some(p);
        }
    }
    let mut starts: Vec<PathBuf> = vec![PathBuf::from(env!("CARGO_MANIFEST_DIR"))];
    if let Ok(exe) = std::env::current_exe() {
        starts.push(exe);
    }
    for start in starts {
        let mut cur = Some(start.as_path());
        while let Some(dir) = cur {
            if dir.join("Suite").join("suite").join("suite.py").exists() {
                return Some(dir.to_path_buf());
            }
            cur = dir.parent();
        }
    }
    None
}

/// The contract folder shared with PinguinoLink: env PINGUINO_LITE_DIR, else <suite root>\Data\lite, else <state dir>\lite.
pub fn lite_dir() -> PathBuf {
    if let Ok(p) = std::env::var("PINGUINO_LITE_DIR") {
        return PathBuf::from(p);
    }
    suite_root().map(|r| r.join("Data").join("lite")).unwrap_or_else(|| state_dir().join("lite"))
}

fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0)
}

#[derive(Serialize)]
struct Info {
    link_dir: Option<String>,
    version: String,
    lite_dir: String,
    state_dir: String,
    suite_root: Option<String>,
    host: String,
}

#[tauri::command]
fn lite_info(app: AppHandle) -> Info {
    Info {
        version: app.package_info().version.to_string(),
        lite_dir: lite_dir().display().to_string(),
        state_dir: state_dir().display().to_string(),
        suite_root: suite_root().map(|p| p.display().to_string()),
        host: HOST.to_string(),
        link_dir: link_dir().map(|p| p.display().to_string()),
    }
}

/// Is PinguinoHost answering on 127.0.0.1:8770? GET /api/live; any HTTP answer counts as reachable.
/// Returns {reachable, ms, status, live} where live is the parsed JSON body when there is one.
#[tauri::command]
async fn host_live() -> Value {
    let t0 = Instant::now();
    let Some(addr) = HOST.to_socket_addrs().ok().and_then(|mut a| a.next()) else { return json!({"reachable": false}) };
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(800)) else { return json!({"reachable": false}) };
    let _ = s.set_read_timeout(Some(Duration::from_millis(1500)));
    let _ = s.set_write_timeout(Some(Duration::from_millis(800)));
    let req = format!("GET /api/live HTTP/1.1\r\nHost: {HOST}\r\nAccept: application/json\r\nConnection: close\r\n\r\n");
    if s.write_all(req.as_bytes()).is_err() {
        return json!({"reachable": false});
    }
    let mut buf = Vec::new();
    let _ = s.take(256 * 1024).read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    let status: Option<u16> = text.lines().next().and_then(|l| l.split_whitespace().nth(1)).and_then(|c| c.parse().ok());
    let body = text.split_once("\r\n\r\n").map(|(_, b)| b).unwrap_or("");
    let live: Value = serde_json::from_str(body.trim()).unwrap_or(Value::Null);
    json!({"reachable": status.is_some(), "ms": t0.elapsed().as_millis() as u64, "status": status, "live": live})
}

/// Availability probe for the sidebar dots: which of the Suite's fixed local ports answer right now (TCP connect, 300 ms each).
/// Returns {"8760": true, ...}. Only these ports can be asked about.
#[tauri::command]
async fn probe_ports() -> Value {
    let mut m = serde_json::Map::new();
    for port in [8760u16, 8765, 8766, 7777, 8770, 8771] {
        let up = TcpStream::connect_timeout(&std::net::SocketAddr::from(([127, 0, 0, 1], port)), Duration::from_millis(300)).is_ok();
        m.insert(port.to_string(), Value::Bool(up));
    }
    Value::Object(m)
}

/// Read one contract file (<lite dir>\<name>.json). Returns {exists, data?, error?, mtime_ms?}; a missing file is normal ("04 has not written it yet").
#[tauri::command]
fn read_contract(name: String) -> Value {
    if !CONTRACT_FILES.contains(&name.as_str()) {
        return json!({"exists": false, "error": "unknown contract file"});
    }
    let path = lite_dir().join(format!("{name}.json"));
    let Ok(txt) = std::fs::read_to_string(&path) else { return json!({"exists": false}) };
    let mtime = std::fs::metadata(&path).and_then(|m| m.modified()).ok().and_then(|m| m.duration_since(UNIX_EPOCH).ok()).map(|d| d.as_millis() as u64);
    match serde_json::from_str::<Value>(txt.trim_start_matches('\u{feff}')) {
        Ok(v) => json!({"exists": true, "data": v, "mtime_ms": mtime}),
        Err(e) => json!({"exists": true, "error": format!("invalid JSON: {e}"), "mtime_ms": mtime}),
    }
}

/// Ask PinguinoLink to do something: writes <lite dir>\requests\<ms>-<action>[-<id>].json ({schema, action, id?, requested_at, from}).
/// 04 consumes (deletes) the file and reports progress in status.json / installed.json. No endpoint call, so nothing here needs a token.
#[tauri::command]
fn send_request(app: AppHandle, action: String, id: Option<String>) -> Result<Value, String> {
    if action == "restart-link" {
        // handled here, not by Link (it cannot restart itself while swapping its own files)
        if app.state::<Link>().0.lock().unwrap().is_none() {
            return Ok(json!({"restarted": false, "reason": "Link is not owned by Lite (external or absent); not touched"}));
        }
        stop_link(&app);
        let child = spawn_link(&app.package_info().version.to_string());
        let started = child.is_some();
        *app.state::<Link>().0.lock().unwrap() = child;
        return Ok(json!({"restarted": started}));
    }
    if !ACTIONS.contains(&action.as_str()) {
        return Err("unknown action".into());
    }
    if let Some(i) = &id {
        if i.is_empty() || i.len() > 40 || !i.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_') {
            return Err("bad module id".into());
        }
    }
    let dir = lite_dir().join("requests");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let ms = now_ms();
    let name = match &id {
        Some(i) => format!("{ms}-{action}-{i}.json"),
        None => format!("{ms}-{action}.json"),
    };
    let body = json!({"schema": 1, "action": action, "id": id, "requested_at": ms as u64, "from": "pinguino-lite"});
    let tmp = dir.join(format!("{name}.tmp"));
    std::fs::write(&tmp, serde_json::to_string_pretty(&body).unwrap()).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, dir.join(&name)).map_err(|e| e.to_string())?; // atomic: 04 only ever sees whole files (it ignores *.tmp)
    if action == "selfupdate-apply" {
        // the installer cannot replace a running exe: Link's helper waits for us to exit (04 contract)
        let a = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(800));
            if let Some(w) = a.get_webview_window("main") {
                mainwin::save(&w, true);
            }
            a.exit(0);
        });
    }
    Ok(json!({"file": name}))
}

/// Open the Host dashboard or the contract folder. Only those two targets exist; no arbitrary paths or URLs from the UI.
#[tauri::command]
fn open_target(target: String) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let mut c = match target.as_str() {
            "host" => {
                let mut c = std::process::Command::new("rundll32");
                c.args(["url.dll,FileProtocolHandler", &format!("http://{HOST}/")]);
                c
            }
            "folder" => {
                let d = lite_dir();
                let _ = std::fs::create_dir_all(&d);
                let mut c = std::process::Command::new("explorer");
                c.arg(d);
                c
            }
            _ => return Err("unknown target".into()),
        };
        c.creation_flags(0x0800_0000).spawn().map(|_| ()).map_err(|e| e.to_string())
    }
    #[cfg(not(windows))]
    {
        let _ = target;
        Err("only implemented on Windows".into())
    }
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .manage(Link(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![lite_info, host_live, probe_ports, read_contract, send_request, open_target, replays::replay_scan, replays::replay_index])
        .setup(|app| {
            replays::start();
            // Splash (the lightning bolt) first; the main window is placed and shown when it closes.
            let a = app.handle().clone();
            let splash = WebviewWindowBuilder::new(app, "splash", WebviewUrl::App("splash.html".into()))
                .title("PinguinoLite").inner_size(340.0, 340.0).decorations(false).resizable(false).always_on_top(true).skip_taskbar(true).center().build();
            let wait = if splash.is_ok() { 1500 } else { 0 };
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_millis(wait));
                if let Some(s) = a.get_webview_window("splash") {
                    let _ = s.close();
                }
                if let Some(w) = a.get_webview_window("main") {
                    if let Ok(ic) = tauri::image::Image::from_bytes(include_bytes!("../icons/64x64.png")) { let _ = w.set_icon(ic); } // small-size art for the taskbar
                    mainwin::place(&w); // saved size/position/maximized, or ~62% of the monitor, centred
                    let _ = w.show();
                    let _ = w.set_focus();
                }
            });
            // tray: left click shows the window, right click menu has Show / Quit (closing the window still quits Lite and stops Link)
            let open = MenuItem::with_id(app, "open", "Show PinguinoLite", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("PinguinoLite")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, ev| match ev.id.as_ref() {
                    "open" => show_main(app),
                    "quit" => {
                        if let Some(w) = app.get_webview_window("main") {
                            mainwin::save(&w, true);
                        }
                        app.exit(0)
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, ev| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                        show_main(tray.app_handle());
                    }
                })
                .build(app)?;
            let child = spawn_link(&app.package_info().version.to_string()); // None = no Link bundled here (dev without Link): Lite still opens
            *app.state::<Link>().0.lock().unwrap() = child;
            Ok(())
        })
        .on_window_event(|window, event| {
            use tauri::WindowEvent;
            if window.label() == "main" {
                match event {
                    WindowEvent::CloseRequested { .. } => {
                        if let Some(w) = window.app_handle().get_webview_window("main") {
                            mainwin::save(&w, true);
                        }
                    }
                    WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
                        if let Some(w) = window.app_handle().get_webview_window("main") {
                            mainwin::save(&w, false);
                        }
                    }
                    _ => {}
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building PinguinoLite");
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            stop_link(handle);
        }
    });
}
