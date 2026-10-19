// PinguinoSuite shell: window + tray + single-instance + autostart, and supervisor of the core sidecar.
// The core (Suite/suite/suite.py) owns modules, the event bus and the API; this shell only hosts it.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use rand::{distributions::Alphanumeric, Rng};
use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_autostart::MacosLauncher;

fn port() -> u16 {
    std::env::var("PINGUINO_PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(8760)
}

struct Core {
    child: Mutex<Option<Child>>,
    token: String,
}

#[derive(Serialize)]
struct CoreConfig {
    base: String,
    token: String,
}

/// UI -> shell: where the core is and the per-launch token to call it with.
#[tauri::command]
fn core_config(core: tauri::State<Core>) -> CoreConfig {
    CoreConfig { base: format!("http://127.0.0.1:{}", port()), token: core.token.clone() }
}

/// Find the suite root (the folder holding Suite/suite/suite.py).
fn suite_root() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("PINGUINO_SUITE_ROOT") {
        return Some(PathBuf::from(p));
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

fn python_for(root: &PathBuf) -> PathBuf {
    let venv = if cfg!(windows) { root.join("Suite/.venv/Scripts/python.exe") } else { root.join("Suite/.venv/bin/python") };
    if venv.exists() {
        venv
    } else if cfg!(windows) {
        PathBuf::from("python")
    } else {
        PathBuf::from("python3")
    }
}

/// A bundled core binary (PyInstaller build) next to the exe or under binaries/, if present.
fn bundled_core() -> Option<PathBuf> {
    let name = if cfg!(windows) { "pinguino-core.exe" } else { "pinguino-core" };
    let mut dirs: Vec<PathBuf> = vec![PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries")];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            dirs.insert(0, d.join("binaries"));
            dirs.insert(0, d.to_path_buf());
        }
    }
    dirs.into_iter().map(|d| d.join(name)).find(|p| p.exists())
}

fn spawn_core(token: &str) -> Option<Child> {
    let root = suite_root()?;
    let mut cmd = match bundled_core() {
        // Bundled core: no Python needed for the core itself; modules still use the venv/system Python.
        Some(bin) => {
            let mut c = Command::new(bin);
            c.env("PINGUINO_SUITE_DIR", root.join("Suite")).env("PINGUINO_PYTHON", python_for(&root));
            c
        }
        None => {
            let mut c = Command::new(python_for(&root));
            c.arg(root.join("Suite/suite/suite.py"));
            c
        }
    };
    cmd.arg("--headless")
        .current_dir(root.join("Suite"))
        .env("PINGUINO_API_TOKEN", token)
        .env("PINGUINO_PORT", port().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn().ok()
}

/// Ask the core to stop itself (it stops its modules too); fall back to killing the process.
fn stop_core(core: &Core) {
    if let Ok(mut s) = TcpStream::connect_timeout(&format!("127.0.0.1:{}", port()).parse().unwrap(), Duration::from_millis(500)) {
        let req = format!(
            "POST /api/quit HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
            port(),
            core.token
        );
        let _ = s.set_read_timeout(Some(Duration::from_secs(3)));
        let _ = s.write_all(req.as_bytes());
        let mut buf = [0u8; 64];
        let _ = s.read(&mut buf);
    }
    if let Some(mut child) = core.child.lock().unwrap().take() {
        std::thread::sleep(Duration::from_millis(500));
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Navigation guard: the window stays on the shell and on local module pages (127.0.0.1 / localhost).
/// Any other http(s) address (e.g. Twitch sign-in started by a module) opens in the system browser instead.
fn nav_guard<R: tauri::Runtime>() -> tauri::plugin::TauriPlugin<R> {
    tauri::plugin::Builder::new("nav-guard")
        .on_navigation(|webview, url| {
            let local = match url.scheme() {
                "http" | "https" => matches!(url.host_str(), Some("127.0.0.1") | Some("localhost") | Some("tauri.localhost")),
                "https+tauri" | "tauri" | "about" | "data" | "blob" => true,
                _ => false,
            };
            if !local && matches!(url.scheme(), "http" | "https") {
                #[allow(deprecated)]
                let _ = tauri_plugin_shell::ShellExt::shell(webview).open(url.as_str(), None);
            }
            local
        })
        .build()
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn main() {
    let token: String = rand::thread_rng().sample_iter(&Alphanumeric).take(40).map(char::from).collect();
    let child = spawn_core(&token);

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec!["--background"])))
        .plugin(tauri_plugin_shell::init())
        .plugin(nav_guard())
        .manage(Core { child: Mutex::new(child), token })
        .invoke_handler(tauri::generate_handler![core_config])
        .setup(|app| {
            let open = MenuItem::with_id(app, "open", "Show PinguinoSuite", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit (stops all modules)", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("PinguinoSuite")
                .menu(&menu)
                .on_menu_event(|app, ev| match ev.id.as_ref() {
                    "open" => show_main(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                // Left click reopens the window; the menu (Show / Quit) is on right click.
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, ev| match ev {
                    TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. }
                    | TrayIconEvent::DoubleClick { button: MouseButton::Left, .. } => show_main(tray.app_handle()),
                    _ => {}
                })
                .build(app)?;
            // Started by autostart: stay in the tray.
            if std::env::args().any(|a| a == "--background") {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.hide();
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Close button hides to tray; Quit lives in the tray menu.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building PinguinoSuite");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_core(&handle.state::<Core>());
        }
    });
}
