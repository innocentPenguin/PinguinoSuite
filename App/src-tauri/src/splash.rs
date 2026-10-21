// Start-up splash: shown at once on a normal launch while the main window stays hidden. When the UI says it is ready (command
// `app_ready`, after the core answered) and the minimum time has passed, the splash closes, the main window appears where it was
// left, and then every pop-out window is reopened where it was left. A failsafe thread does the same if the UI never answers.
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

use crate::{mainwin, windows};

const MIN_SHOW: Duration = Duration::from_millis(1600);
const FAILSAFE: Duration = Duration::from_secs(20);

static DONE: AtomicBool = AtomicBool::new(false);
static STARTED: std::sync::OnceLock<Instant> = std::sync::OnceLock::new();

/// Open the splash and arm the failsafe. If the splash cannot be created, go straight to the windows.
pub fn start(app: &AppHandle) {
    let _ = STARTED.set(Instant::now());
    let made = WebviewWindowBuilder::new(app, "splash", WebviewUrl::App("splash.html".into()))
        .title("PinguinoSuite")
        .inner_size(440.0, 440.0)
        .decorations(false)
        .transparent(true) // the rounded card is the only thing drawn: no square window behind it
        .shadow(false)
        .background_color(tauri::window::Color(0, 0, 0, 0))
        .resizable(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .center()
        .build();
    if made.is_err() {
        finish(app);
        return;
    }
    let a = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(FAILSAFE);
        finish(&a);
    });
}

/// Close the splash, show the main window, then reopen the pop-outs. Safe to call more than once.
pub fn finish(app: &AppHandle) {
    if DONE.swap(true, Ordering::SeqCst) {
        return;
    }
    if let Some(w) = app.get_webview_window("splash") {
        let _ = w.close();
    }
    if let Some(w) = app.get_webview_window("main") {
        mainwin::place(&w); // saved size/position/maximized, or the 62% centred default
        let _ = w.show();
        let _ = w.set_focus();
    }
    windows::restore(app);
}

/// Called by the shell UI once the core has answered.
#[tauri::command]
pub fn app_ready(app: AppHandle) {
    let wait = STARTED.get().map(|t| MIN_SHOW.saturating_sub(t.elapsed())).unwrap_or_default();
    std::thread::spawn(move || {
        std::thread::sleep(wait);
        finish(&app);
    });
}
