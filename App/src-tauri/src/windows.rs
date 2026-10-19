// Pop-out windows: open/close extra windows (chat, editor, any shell page or local module page), place them on a chosen
// monitor (full / top / bottom / left / right half, so one can sit above another), and remember position, size, monitor and
// always-on-top per label across launches. Layouts live in <data dir>/windows.json. Used from the UI through window.PGWin
// (App/src/bootstrap.js); contract in Docs/MODULE_CONTRACT.md ("Pop-out windows").
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, Monitor, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

#[derive(Serialize, Deserialize, Clone, Default)]
pub struct Saved {
    pub url: String,
    pub title: String,
    pub x: i32,
    pub y: i32,
    pub w: u32,
    pub h: u32,
    pub monitor: Option<String>,
    pub on_top: bool,
    pub decorations: bool,
    pub open: bool,
}

pub struct Layouts {
    map: Mutex<HashMap<String, Saved>>,
    path: PathBuf,
    last_write: Mutex<Instant>,
}

impl Layouts {
    pub fn load(path: PathBuf) -> Layouts {
        let map = std::fs::read_to_string(&path).ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or_default();
        Layouts { map: Mutex::new(map), path, last_write: Mutex::new(Instant::now() - Duration::from_secs(10)) }
    }
    fn flush(&self, force: bool) {
        let mut last = self.last_write.lock().unwrap();
        if !force && last.elapsed() < Duration::from_millis(600) {
            return;
        }
        *last = Instant::now();
        if let Some(dir) = self.path.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        let tmp = self.path.with_extension("json.tmp");
        if let Ok(s) = serde_json::to_string_pretty(&*self.map.lock().unwrap()) {
            if std::fs::write(&tmp, s).is_ok() {
                let _ = std::fs::rename(&tmp, &self.path);
            }
        }
    }
    pub fn open_labels(&self) -> Vec<(String, Saved)> {
        self.map.lock().unwrap().iter().filter(|(_, s)| s.open).map(|(k, v)| (k.clone(), v.clone())).collect()
    }
}

#[derive(Serialize)]
pub struct MonitorInfo {
    index: usize,
    name: String,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    scale: f64,
    primary: bool,
}

#[derive(Deserialize)]
pub struct OpenReq {
    pub label: String,
    /// http(s) address on 127.0.0.1/localhost, or a shell path such as "index.html?popout=console"
    pub url: String,
    pub title: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    /// monitor index (as listed by list_monitors) or monitor name; default: where it was last, else primary
    pub monitor: Option<String>,
    /// full | top | bottom | left | right: fill that part of the monitor (so one window can sit above another)
    pub place: Option<String>,
    pub always_on_top: Option<bool>,
    pub decorations: Option<bool>,
    /// ignore the remembered geometry
    pub reset: Option<bool>,
}

#[derive(Serialize)]
pub struct WinInfo {
    label: String,
    url: String,
    title: String,
    open: bool,
    on_top: bool,
    monitor: Option<String>,
}

fn clean_label(l: &str) -> Result<String, String> {
    let l = l.trim().to_lowercase();
    let l = if l.starts_with("pop-") { l } else { format!("pop-{}", l) };
    if l.len() > 40 || !l.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-') {
        return Err("label: letters, digits and '-' only (max 40)".into());
    }
    Ok(l)
}

fn monitors(app: &AppHandle) -> Vec<Monitor> {
    app.available_monitors().unwrap_or_default()
}

fn mon_name(m: &Monitor, i: usize) -> String {
    m.name().cloned().unwrap_or_else(|| format!("Monitor {}", i + 1))
}

#[tauri::command]
pub fn list_monitors(app: AppHandle) -> Vec<MonitorInfo> {
    let prim = app.primary_monitor().ok().flatten().map(|m| (m.position().x, m.position().y));
    monitors(&app)
        .iter()
        .enumerate()
        .map(|(i, m)| MonitorInfo {
            index: i,
            name: mon_name(m, i),
            x: m.position().x,
            y: m.position().y,
            width: m.size().width,
            height: m.size().height,
            scale: m.scale_factor(),
            primary: prim == Some((m.position().x, m.position().y)),
        })
        .collect()
}

fn find_monitor(app: &AppHandle, key: &str) -> Option<Monitor> {
    let ms = monitors(app);
    if let Ok(i) = key.parse::<usize>() {
        if let Some(m) = ms.get(i) {
            return Some(m.clone());
        }
    }
    ms.iter().enumerate().find(|(i, m)| mon_name(m, *i) == key).map(|(_, m)| m.clone())
}

fn on_any_monitor(app: &AppHandle, x: i32, y: i32, w: u32, h: u32) -> bool {
    // the window's centre must lie on a monitor that still exists (monitors get unplugged / rearranged)
    let (cx, cy) = (x + (w / 2) as i32, y + (h / 2) as i32);
    monitors(app).iter().any(|m| {
        let (p, s) = (m.position(), m.size());
        cx >= p.x && cx < p.x + s.width as i32 && cy >= p.y && cy < p.y + s.height as i32
    })
}

fn rect_for(m: &Monitor, place: &str) -> (i32, i32, u32, u32) {
    let (p, s) = (m.position(), m.size());
    let (hw, hh) = (s.width / 2, s.height / 2);
    match place {
        "top" => (p.x, p.y, s.width, hh),
        "bottom" => (p.x, p.y + hh as i32, s.width, s.height - hh),
        "left" => (p.x, p.y, hw, s.height),
        "right" => (p.x + hw as i32, p.y, s.width - hw, s.height),
        _ => (p.x, p.y, s.width, s.height),
    }
}

/// Only local pages: shell paths or http(s) on 127.0.0.1 / localhost (a pop-out is never a way to browse elsewhere).
fn build_url(app: &AppHandle, raw: &str) -> Result<WebviewUrl, String> {
    if raw.starts_with("http://") || raw.starts_with("https://") {
        let u: tauri::Url = raw.parse().map_err(|_| "bad url")?;
        return match u.host_str() {
            Some("127.0.0.1") | Some("localhost") => Ok(WebviewUrl::External(u)),
            _ => Err("only local (127.0.0.1) pages can be opened in a pop-out".into()),
        };
    }
    let main = app.get_webview_window("main").ok_or("main window missing")?;
    let base = main.url().map_err(|e| e.to_string())?;
    let rel = raw.trim_start_matches('/');
    Ok(WebviewUrl::External(base.join(rel).map_err(|e| e.to_string())?))
}

fn snapshot(app: &AppHandle, win: &WebviewWindow, open: bool) {
    let lay = app.state::<Layouts>();
    let (Ok(p), Ok(s)) = (win.outer_position(), win.outer_size()) else { return };
    if s.width < 50 || p.x <= -30000 {
        return; // minimised / off-screen parking: keep the last good geometry
    }
    let mon = win.current_monitor().ok().flatten().map(|m| {
        let i = monitors(app).iter().position(|x| x.position() == m.position()).unwrap_or(0);
        mon_name(&m, i)
    });
    {
        let mut map = lay.map.lock().unwrap();
        if let Some(e) = map.get_mut(win.label()) {
            e.x = p.x;
            e.y = p.y;
            e.w = s.width;
            e.h = s.height;
            e.monitor = mon;
            e.open = open;
        }
    }
    lay.flush(!open);
}

#[tauri::command]
pub fn open_window(app: AppHandle, req: OpenReq) -> Result<WinInfo, String> {
    let label = clean_label(&req.label)?;
    let lay = app.state::<Layouts>();
    let prev = lay.map.lock().unwrap().get(&label).cloned();
    let reset = req.reset.unwrap_or(false);

    if let Some(w) = app.get_webview_window(&label) {
        // already open: bring it forward (and move it if a placement was asked for)
        let _ = w.show();
        let _ = w.unminimize();
        if req.place.is_some() || req.monitor.is_some() {
            place(&app, &w, &req, prev.as_ref(), reset);
        }
        if let Some(t) = req.always_on_top {
            let _ = w.set_always_on_top(t);
        }
        let _ = w.set_focus();
        return Ok(info(&app, &label));
    }

    let url = build_url(&app, &req.url)?;
    let title = req.title.clone().or_else(|| prev.as_ref().map(|p| p.title.clone())).unwrap_or_else(|| "PinguinoSuite".into());
    let on_top = req.always_on_top.or(prev.as_ref().map(|p| p.on_top)).unwrap_or(false);
    let deco = req.decorations.or(prev.as_ref().map(|p| p.decorations)).unwrap_or(true);
    let win = WebviewWindowBuilder::new(&app, &label, url)
        .title(&title)
        .inner_size(req.width.unwrap_or(900) as f64, req.height.unwrap_or(700) as f64)
        .always_on_top(on_top)
        .decorations(deco)
        .visible(false)
        .build()
        .map_err(|e| e.to_string())?;

    lay.map.lock().unwrap().insert(
        label.clone(),
        Saved { url: req.url.clone(), title, on_top, decorations: deco, open: true, x: prev.as_ref().map_or(0, |p| p.x), y: prev.as_ref().map_or(0, |p| p.y), w: prev.as_ref().map_or(0, |p| p.w), h: prev.as_ref().map_or(0, |p| p.h), monitor: prev.as_ref().and_then(|p| p.monitor.clone()) },
    );
    place(&app, &win, &req, prev.as_ref(), reset);
    let _ = win.show();
    let _ = win.set_focus();
    snapshot(&app, &win, true);

    let handle = app.clone();
    let w2 = win.clone();
    win.on_window_event(move |ev| match ev {
        WindowEvent::Moved(_) | WindowEvent::Resized(_) => snapshot(&handle, &w2, true),
        WindowEvent::CloseRequested { .. } => {
            // closing a pop-out keeps its geometry for next time but marks it closed (so it does not reopen at launch)
            let lay = handle.state::<Layouts>();
            if let Some(e) = lay.map.lock().unwrap().get_mut(w2.label()) {
                e.open = false;
            }
            lay.flush(true);
        }
        _ => {}
    });
    lay.flush(true);
    Ok(info(&app, &label))
}

/// Decide where the window goes: an explicit placement, else the remembered geometry (if its monitor still exists), else centred on a monitor.
fn place(app: &AppHandle, win: &WebviewWindow, req: &OpenReq, prev: Option<&Saved>, reset: bool) {
    let explicit = req.place.is_some() || req.monitor.is_some();
    if !explicit && !reset {
        if let Some(p) = prev {
            if p.w > 0 && on_any_monitor(app, p.x, p.y, p.w, p.h) {
                let _ = win.set_size(PhysicalSize::new(p.w, p.h));
                let _ = win.set_position(PhysicalPosition::new(p.x, p.y));
                return;
            }
        }
    }
    let mon = req
        .monitor
        .as_deref()
        .and_then(|k| find_monitor(app, k))
        .or_else(|| if explicit || reset { None } else { prev.and_then(|p| p.monitor.as_deref()).and_then(|k| find_monitor(app, k)) })
        .or_else(|| app.primary_monitor().ok().flatten());
    let Some(m) = mon else { return };
    match req.place.as_deref() {
        Some(pl @ ("full" | "top" | "bottom" | "left" | "right")) => {
            let (x, y, w, h) = rect_for(&m, pl);
            let _ = win.set_size(PhysicalSize::new(w, h));
            let _ = win.set_position(PhysicalPosition::new(x, y));
        }
        _ => {
            let (sz, p) = (m.size(), m.position());
            let sc = m.scale_factor();
            let w = ((req.width.unwrap_or(900) as f64) * sc).min(sz.width as f64) as u32;
            let h = ((req.height.unwrap_or(700) as f64) * sc).min(sz.height as f64) as u32;
            let _ = win.set_size(PhysicalSize::new(w, h));
            let _ = win.set_position(PhysicalPosition::new(p.x + ((sz.width - w) / 2) as i32, p.y + ((sz.height - h) / 2) as i32));
        }
    }
}

fn info(app: &AppHandle, label: &str) -> WinInfo {
    let lay = app.state::<Layouts>();
    let map = lay.map.lock().unwrap();
    let s = map.get(label).cloned().unwrap_or_default();
    WinInfo { label: label.to_string(), url: s.url, title: s.title, open: app.get_webview_window(label).is_some(), on_top: s.on_top, monitor: s.monitor }
}

#[tauri::command]
pub fn close_window(app: AppHandle, label: String, forget: Option<bool>) -> Result<(), String> {
    let label = clean_label(&label)?;
    if let Some(w) = app.get_webview_window(&label) {
        w.destroy().map_err(|e| e.to_string())?;
    }
    let lay = app.state::<Layouts>();
    {
        let mut map = lay.map.lock().unwrap();
        if forget.unwrap_or(false) {
            map.remove(&label);
        } else if let Some(e) = map.get_mut(&label) {
            e.open = false;
        }
    }
    lay.flush(true);
    Ok(())
}

#[tauri::command]
pub fn set_window_on_top(app: AppHandle, label: String, on: bool) -> Result<(), String> {
    let label = clean_label(&label)?;
    let w = app.get_webview_window(&label).ok_or("no such window")?;
    w.set_always_on_top(on).map_err(|e| e.to_string())?;
    let lay = app.state::<Layouts>();
    if let Some(e) = lay.map.lock().unwrap().get_mut(&label) {
        e.on_top = on;
    }
    lay.flush(true);
    Ok(())
}

/// Every pop-out we know about (open now or remembered).
#[tauri::command]
pub fn list_windows(app: AppHandle) -> Vec<WinInfo> {
    let lay = app.state::<Layouts>();
    let labels: Vec<String> = lay.map.lock().unwrap().keys().cloned().collect();
    labels.iter().map(|l| info(&app, l)).collect()
}

/// At launch: reopen the pop-outs that were open when the Suite last closed (geometry restored from windows.json).
pub fn restore(app: &AppHandle) {
    let lay = app.state::<Layouts>();
    for (label, s) in lay.open_labels() {
        let req = OpenReq { label, url: s.url.clone(), title: Some(s.title.clone()), width: None, height: None, monitor: None, place: None, always_on_top: Some(s.on_top), decorations: Some(s.decorations), reset: None };
        let _ = open_window(app.clone(), req);
    }
}
