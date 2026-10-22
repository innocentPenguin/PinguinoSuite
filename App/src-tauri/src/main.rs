// PinguinoSuite shell: window + tray + single-instance + autostart, and supervisor of the core sidecar.
// The core (Suite/suite/suite.py) owns modules, the event bus and the API; this shell only hosts it.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod mainwin;
mod siteicon;
mod splash;
mod windows;

use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use rand::{distributions::Alphanumeric, Rng};
use serde::Serialize;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_autostart::MacosLauncher;

/// Set by the tray's "Quit and stop all modules". A plain quit leaves the modules running (they are separate programs; the next core adopts them).
static STOP_MODULES: AtomicBool = AtomicBool::new(false);

/// True once a quit has begun, so the close handler lets windows close instead of hiding them to the tray.
static QUITTING: AtomicBool = AtomicBool::new(false);

/// Ports of everything the Suite starts: core, Listen, Multi, Link, Host, Spotify, Voice. Force quit stops whatever listens here.
fn suite_ports() -> Vec<u16> {
    vec![port(), 8765, 8766, 7777, 8770, 8771, 8772]
}

/// Pids LISTENING on a local port (netstat; no token, no core needed).
fn listening_pids(p: u16) -> Vec<u32> {
    let mut out = Vec::new();
    let mut c = Command::new("netstat");
    c.args(["-ano", "-p", "TCP"]).stdin(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x0800_0000);
    }
    if let Ok(o) = c.output() {
        for ln in String::from_utf8_lossy(&o.stdout).lines() {
            let parts: Vec<&str> = ln.split_whitespace().collect();
            if parts.len() >= 5 && parts[3].eq_ignore_ascii_case("LISTENING") && parts[1].rsplit(':').next() == Some(&p.to_string()) {
                if let Ok(pid) = parts[4].parse::<u32>() {
                    if pid != 0 && pid != std::process::id() {
                        out.push(pid);
                    }
                }
            }
        }
    }
    out
}

/// Last resort: kill the core and every module by port, plus the pids the core recorded when it spawned them. Needs nothing from the core.
fn force_kill_all() {
    let mut pids: Vec<u32> = suite_ports().into_iter().flat_map(listening_pids).collect();
    if let Ok(rd) = std::fs::read_dir(data_dir().join("pids")) {
        for e in rd.flatten() {
            if let Ok(txt) = std::fs::read_to_string(e.path()) {
                if let Some(i) = txt.find("\"pid\":") {
                    let n: String = txt[i + 6..].chars().skip_while(|c| !c.is_ascii_digit()).take_while(|c| c.is_ascii_digit()).collect();
                    if let Ok(pid) = n.parse::<u32>() {
                        if pid != std::process::id() {
                            pids.push(pid);
                        }
                    }
                }
            }
        }
    }
    pids.sort();
    pids.dedup();
    for pid in pids {
        let mut c = Command::new("taskkill");
        c.args(["/F", "/T", "/PID", &pid.to_string()]).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            c.creation_flags(0x0800_0000);
        }
        let _ = c.status();
    }
}

#[cfg(windows)]
fn alt_down() -> bool {
    extern "system" {
        fn GetAsyncKeyState(vk: i32) -> i16;
    }
    unsafe { (GetAsyncKeyState(0x12) as u16) & 0x8000 != 0 }
}
#[cfg(not(windows))]
fn alt_down() -> bool {
    false
}

/// Quit for real. A watchdog guarantees the process ends even if the graceful path hangs (a hung core used to leave Quit doing nothing).
fn quit_now(app: &AppHandle, stop_modules: bool) {
    QUITTING.store(true, Ordering::SeqCst);
    if stop_modules {
        STOP_MODULES.store(true, Ordering::SeqCst);
    }
    if let Some(w) = app.get_webview_window("main") {
        mainwin::save(&w, true);
    }
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(6));
        if stop_modules {
            force_kill_all();
        }
        std::process::exit(0);
    });
    app.exit(0);
}

/// Called by the in-page "Are you sure you want to quit?" dialog.
#[tauri::command]
fn quit_app(app: AppHandle, stop_modules: bool) {
    quit_now(&app, stop_modules);
}

/// Full-screen state. While set, mainwin::save ignores the window (the full-screen rectangle must never become the remembered window).
pub static FULLSCREEN: AtomicBool = AtomicBool::new(false);
/// Window rectangle and maximized flag from just before full screen, so leaving it restores exactly that.
static FS_PREV: Mutex<Option<(tauri::PhysicalPosition<i32>, tauri::PhysicalSize<u32>, bool)>> = Mutex::new(None);

fn set_fs(app: &AppHandle, on: bool) {
    let Some(w) = app.get_webview_window("main") else { return };
    if on == FULLSCREEN.load(Ordering::SeqCst) {
        return;
    }
    if on {
        mainwin::save(&w, true);
        if let (Ok(p), Ok(s), Ok(m)) = (w.outer_position(), w.outer_size(), w.is_maximized()) {
            *FS_PREV.lock().unwrap() = Some((p, s, m));
        }
        FULLSCREEN.store(true, Ordering::SeqCst);
        let _ = w.show();
        let _ = w.set_fullscreen(true);
        let _ = w.set_focus();
    } else {
        let _ = w.set_fullscreen(false);
        FULLSCREEN.store(false, Ordering::SeqCst);
        if let Some((p, s, m)) = FS_PREV.lock().unwrap().take() {
            if m {
                let _ = w.maximize();
            } else {
                let _ = w.unmaximize();
                let _ = w.set_size(s);
                let _ = w.set_position(p);
            }
        }
        let _ = w.eval("window.pgFsBar&&window.pgFsBar(false)");
    }
    let _ = w.eval(&format!("window.pgFsState&&window.pgFsState({})", on));
}

#[tauri::command]
fn set_fullscreen(app: AppHandle, on: bool) {
    set_fs(&app, on);
}

#[tauri::command]
fn toggle_fullscreen(app: AppHandle) {
    set_fs(&app, !FULLSCREEN.load(Ordering::SeqCst));
}

#[cfg(windows)]
fn f11_down() -> bool {
    extern "system" {
        fn GetAsyncKeyState(vk: i32) -> i16;
    }
    unsafe { (GetAsyncKeyState(0x7A) as u16) & 0x8000 != 0 }
}
#[cfg(not(windows))]
fn f11_down() -> bool {
    false
}

/// Rust-side watcher (iframes swallow mouse and key events, so the page cannot see them): F11 toggles full screen while the window is focused;
/// in full screen the cursor touching the bottom screen edge shows the exit bar (drawn by the page, above the iframes) and leaving it hides the bar.
fn start_fs_watcher(app: AppHandle) {
    std::thread::spawn(move || {
        let (mut f11_prev, mut bar) = (false, false);
        loop {
            std::thread::sleep(Duration::from_millis(40));
            let Some(w) = app.get_webview_window("main") else { continue };
            let down = f11_down() && w.is_focused().unwrap_or(false);
            if down && !f11_prev {
                set_fs(&app, !FULLSCREEN.load(Ordering::SeqCst));
            }
            f11_prev = down;
            if !FULLSCREEN.load(Ordering::SeqCst) {
                bar = false;
                continue;
            }
            let (Ok(c), Ok(Some(m))) = (w.cursor_position(), w.current_monitor()) else { continue };
            let (mp, ms) = (m.position(), m.size());
            let inside_x = c.x >= mp.x as f64 && c.x < (mp.x + ms.width as i32) as f64;
            let bottom = (mp.y + ms.height as i32) as f64;
            let want = inside_x && if bar { c.y >= bottom - 56.0 } else { c.y >= bottom - 2.0 };
            if want != bar {
                bar = want;
                let _ = w.eval(&format!("window.pgFsBar&&window.pgFsBar({})", bar));
            }
        }
    });
}

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
            "POST /api/quit{} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
            if STOP_MODULES.load(Ordering::SeqCst) { "?modules=stop" } else { "" },
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
            if webview.label() == windows::SITE_LABEL {
                // the website pop-out: only the site and its sign-in pages; everything else goes to the system browser
                let ok = windows::site_nav_allowed(url);
                if !ok && matches!(url.scheme(), "http" | "https") {
                    #[allow(deprecated)]
                    let _ = tauri_plugin_shell::ShellExt::shell(webview).open(url.as_str(), None);
                }
                return ok;
            }
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

/// Where per-device UI state lives (same folder as the core's data: PINGUINO_DATA_DIR, else <Suite root>/Data/runtime).
fn data_dir() -> PathBuf {
    if let Ok(p) = std::env::var("PINGUINO_DATA_DIR") {
        return PathBuf::from(p);
    }
    suite_root().map(|r| r.join("Data").join("runtime")).unwrap_or_else(|| std::env::temp_dir().join("PinguinoSuite"))
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
        .manage(windows::Layouts::load(data_dir().join("windows.json")))
        .invoke_handler(tauri::generate_handler![core_config, quit_app, set_fullscreen, toggle_fullscreen, windows::list_monitors, windows::open_window, windows::close_window, windows::set_window_on_top, windows::list_windows, windows::open_site_window, windows::clear_site_data, splash::app_ready])
        .setup(|app| {
            let open = MenuItem::with_id(app, "open", "Show PinguinoSuite", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit (modules keep running)", true, None::<&str>)?;
            let quit_all = MenuItem::with_id(app, "quit_all", "Quit and stop all modules", true, None::<&str>)?;
            let force = MenuItem::with_id(app, "force_quit", "Force quit (kills everything)", true, None::<&str>)?;
            let fs_item = MenuItem::with_id(app, "fullscreen", "Full screen (F11)", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &fs_item, &quit, &quit_all, &force])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("PinguinoSuite")
                .menu(&menu)
                .on_menu_event(|app, ev| match ev.id.as_ref() {
                    "open" => show_main(app),
                    "fullscreen" => {
                        show_main(app);
                        set_fs(app, !FULLSCREEN.load(Ordering::SeqCst));
                    }
                    "quit" | "quit_all" => quit_now(app, ev.id.as_ref() == "quit_all"),
                    "force_quit" => {
                        force_kill_all();
                        std::process::exit(0);
                    }
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
            start_fs_watcher(app.handle().clone());
            // Started by autostart: stay in the tray.
            if std::env::args().any(|a| a == "--background") {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.hide();
                }
            } else {
                // Splash first; it hands over to the main window and the pop-outs when the UI is ready (see splash.rs).
                splash::start(app.handle());
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Close button on the main window hides to tray; Quit lives in the tray menu. Pop-outs really close.
            if window.label() == "main" {
                match event {
                    WindowEvent::CloseRequested { api, .. } => {
                        if QUITTING.load(Ordering::SeqCst) {
                            return;
                        }
                        if let Some(w) = window.app_handle().get_webview_window("main") {
                            mainwin::save(&w, true);
                        }
                        api.prevent_close();
                        if alt_down() {
                            // Alt+F4: ask first (confirm() is blocked in the webview, so the page shows its own dialog)
                            let _ = window.show();
                            let _ = window.set_focus();
                            if let Some(w) = window.app_handle().get_webview_window("main") {
                                let _ = w.eval("window.pgQuitPrompt&&window.pgQuitPrompt()");
                            }
                        } else {
                            let _ = window.hide(); // the X button keeps hiding to the tray
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
        .expect("error while building PinguinoSuite");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_core(&handle.state::<Core>());
        }
    });
}
