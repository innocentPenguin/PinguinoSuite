// Main window placement: a normal window sized from the monitor (62% x 62%, centred) on first launch, then the size, position and
// maximized state are remembered in <state dir>/window.json. A saved position that is no longer on a connected monitor
// (monitor unplugged, resolution changed) falls back to the default.
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tauri::{LogicalSize, Monitor, PhysicalPosition, PhysicalSize, WebviewWindow};

const FRACTION: f64 = 0.62;
const MIN_W: f64 = 860.0; // logical px
const MIN_H: f64 = 560.0;

#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
struct Saved {
    x: i32,
    y: i32,
    w: u32,
    h: u32,
    maximized: bool,
    /// the monitor the window was on (x, y, w, h): if no connected monitor matches, the saved placement is not trusted
    mon: [i64; 4],
}

fn file() -> PathBuf {
    crate::state_dir().join("window.json")
}

fn mon_sig(m: &Monitor) -> [i64; 4] {
    let (p, s) = (m.position(), m.size());
    [p.x as i64, p.y as i64, s.width as i64, s.height as i64]
}

fn load() -> Option<Saved> {
    serde_json::from_str(&std::fs::read_to_string(file()).ok()?).ok()
}

/// The default: 62% of the monitor's width and height (never below the minimum, never above the monitor), centred on it.
fn default_rect(m: &Monitor) -> (i32, i32, u32, u32) {
    let sf = m.scale_factor();
    let (mp, ms) = (m.position(), m.size());
    let w = ((ms.width as f64 * FRACTION).max(MIN_W * sf)).min(ms.width as f64) as u32;
    let h = ((ms.height as f64 * FRACTION).max(MIN_H * sf)).min(ms.height as f64) as u32;
    let x = mp.x + ((ms.width - w) / 2) as i32;
    let y = mp.y + ((ms.height - h) / 2) as i32;
    (x, y, w, h)
}

/// Is the saved placement still sensible on the monitors that are connected now?
fn usable(s: &Saved, mons: &[Monitor]) -> bool {
    let Some(m) = mons.iter().find(|m| mon_sig(m) == s.mon) else { return false };
    let (mp, ms) = (m.position(), m.size());
    let sf = m.scale_factor();
    if (s.w as f64) < MIN_W * sf * 0.9 || (s.h as f64) < MIN_H * sf * 0.9 || s.w > ms.width + 16 || s.h > ms.height + 16 {
        return false;
    }
    // the title bar (top centre) must be on the monitor so the window can be grabbed
    let (cx, ty) = (s.x as i64 + s.w as i64 / 2, s.y as i64 + 20);
    cx >= mp.x as i64 && cx < mp.x as i64 + ms.width as i64 && ty >= mp.y as i64 && ty < mp.y as i64 + ms.height as i64
}

/// Place the main window (before it is shown): saved placement if still valid, else the 62% centred default.
pub fn place(w: &WebviewWindow) {
    let _ = w.set_min_size(Some(LogicalSize::new(MIN_W, MIN_H)));
    let mons = w.available_monitors().unwrap_or_default();
    let primary = w.primary_monitor().ok().flatten().or_else(|| w.current_monitor().ok().flatten()).or_else(|| mons.first().cloned());
    if let Some(s) = load().filter(|s| usable(s, &mons)) {
        let _ = w.set_size(PhysicalSize::new(s.w, s.h));
        let _ = w.set_position(PhysicalPosition::new(s.x, s.y));
        if s.maximized {
            let _ = w.maximize();
        }
        return;
    }
    if let Some(m) = primary {
        let (x, y, ww, hh) = default_rect(&m);
        let _ = w.set_size(PhysicalSize::new(ww, hh));
        let _ = w.set_position(PhysicalPosition::new(x, y));
    } else {
        let _ = w.center();
    }
}

static LAST: AtomicU64 = AtomicU64::new(0);

fn now_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0)
}

/// Remember the window. `force` skips the throttle (close / quit). Minimized or hidden windows are ignored (their reported position is bogus);
/// while maximized only the flag changes, so un-maximizing returns to the previous normal size.
pub fn save(w: &WebviewWindow, force: bool) {
    if crate::FULLSCREEN.load(Ordering::Relaxed) {
        return; // full screen is not the window's remembered size
    }
    if !force {
        let t = now_ms();
        if t.saturating_sub(LAST.load(Ordering::Relaxed)) < 400 {
            return;
        }
        LAST.store(t, Ordering::Relaxed);
    }
    if w.is_minimized().unwrap_or(false) || !w.is_visible().unwrap_or(true) {
        return;
    }
    let maximized = w.is_maximized().unwrap_or(false);
    let Some(m) = w.current_monitor().ok().flatten() else { return };
    let mut s = if maximized { load().unwrap_or_else(|| { let (x, y, ww, hh) = default_rect(&m); Saved { x, y, w: ww, h: hh, maximized, mon: mon_sig(&m) } }) } else {
        let (Ok(p), Ok(sz)) = (w.outer_position(), w.outer_size()) else { return };
        Saved { x: p.x, y: p.y, w: sz.width, h: sz.height, maximized: false, mon: mon_sig(&m) }
    };
    s.maximized = maximized;
    if maximized {
        s.mon = mon_sig(&m);
    }
    if load().as_ref() == Some(&s) {
        return;
    }
    if let Ok(txt) = serde_json::to_string_pretty(&s) {
        let f = file();
        if let Some(d) = f.parent() {
            let _ = std::fs::create_dir_all(d);
        }
        let _ = std::fs::write(f, txt);
    }
}
