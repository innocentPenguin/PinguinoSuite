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
    parked: Mutex<HashMap<String, Instant>>,   // windows just moved off a missing monitor: keep their saved home until the user moves them
    path: PathBuf,
    last_write: Mutex<Instant>,
}

impl Layouts {
    pub fn load(path: PathBuf) -> Layouts {
        let map = std::fs::read_to_string(&path).ok().and_then(|s| serde_json::from_str(&s).ok()).unwrap_or_default();
        Layouts { map: Mutex::new(map), parked: Mutex::new(HashMap::new()), path, last_write: Mutex::new(Instant::now() - Duration::from_secs(10)) }
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

#[derive(Deserialize, Clone)]
pub struct Bounds {
    pub x: i32,
    pub y: i32,
    pub w: u32,
    pub h: u32,
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
    /// last position the caller remembers (virtual-desktop pixels); used when nothing is remembered here
    pub bounds: Option<Bounds>,
    /// false: do not restore / keep geometry for this label (default true)
    pub remember: Option<bool>,
    /// true: remembered geometry beats monitor/place (those are only the first-time default). Module pages use this.
    pub soft: Option<bool>,
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
    if let Some(t) = lay.parked.lock().unwrap().get(win.label()) {
        if t.elapsed() < Duration::from_millis(1500) {
            return; // our own move onto a substitute monitor: the saved home stays so it can return when that monitor does
        }
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
    let prev = if req.remember == Some(false) { None } else { lay.map.lock().unwrap().get(&label).cloned() };
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

fn nearest_monitor(app: &AppHandle, cx: i32, cy: i32) -> Option<Monitor> {
    monitors(app).into_iter().min_by_key(|m| {
        let (p, s) = (m.position(), m.size());
        let (mx, my) = (p.x + (s.width / 2) as i32, p.y + (s.height / 2) as i32);
        ((mx - cx) as i64).pow(2) + ((my - cy) as i64).pow(2)
    })
}

/// Decide where the window goes: an explicit placement, else the remembered geometry (if its monitor still exists), else centred on a monitor.
fn place(app: &AppHandle, win: &WebviewWindow, req: &OpenReq, prev: Option<&Saved>, reset: bool) {
    let remember = req.remember.unwrap_or(true);
    let explicit = !req.soft.unwrap_or(false) && (req.place.is_some() || req.monitor.is_some());
    if !explicit && !reset && remember {
        if let Some(p) = prev {
            if p.w > 0 {
                if on_any_monitor(app, p.x, p.y, p.w, p.h) {
                    let _ = win.set_size(PhysicalSize::new(p.w, p.h));
                    let _ = win.set_position(PhysicalPosition::new(p.x, p.y));
                    return;
                }
                // its monitor is gone: sit on the nearest one, but keep the saved spot so it goes back when that monitor returns
                if let Some(m) = nearest_monitor(app, p.x + (p.w / 2) as i32, p.y + (p.h / 2) as i32) {
                    let (mp, ms) = (m.position(), m.size());
                    let (w, h) = (p.w.min(ms.width), p.h.min(ms.height));
                    let x = p.x.max(mp.x).min(mp.x + (ms.width - w) as i32);
                    let y = p.y.max(mp.y).min(mp.y + (ms.height - h) as i32);
                    let _ = win.set_size(PhysicalSize::new(w, h));
                    let _ = win.set_position(PhysicalPosition::new(x, y));
                    app.state::<Layouts>().parked.lock().unwrap().insert(win.label().to_string(), Instant::now());
                    return;
                }
            }
        }
    }
    if !reset {
        if let Some(bd) = &req.bounds {
            if bd.w >= 100 && bd.h >= 80 && on_any_monitor(app, bd.x, bd.y, bd.w, bd.h) {
                let _ = win.set_size(PhysicalSize::new(bd.w, bd.h));
                let _ = win.set_position(PhysicalPosition::new(bd.x, bd.y));
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
        if label == SITE_LABEL {
            let _ = open_site_window(app.clone(), None);
            continue;
        }
        let req = OpenReq { label, url: s.url.clone(), title: Some(s.title.clone()), width: None, height: None, monitor: None, place: None, always_on_top: Some(s.on_top), decorations: Some(s.decorations), reset: None, bounds: None, remember: None, soft: None };
        let _ = open_window(app.clone(), req);
    }
}

// ---- Website pop-out (055): innocentpenguin.com in its own window, own icon/taskbar entry and own login profile ----
// Not a general remote opener: the address is fixed to SITE_HOME (+ an optional plain path on that host), and navigation is
// limited to the site and its sign-in providers. Everything else opens in the system browser (see site_nav_allowed / nav_guard).
// Contract: Docs/SITE_POPOUT.md.
pub const SITE_LABEL: &str = "pop-site";
const SITE_HOME: &str = "https://innocentpenguin.com";
const SITE_TITLE: &str = "Innocent Penguin - Website";
const SITE_AUMID: &str = "gg.pinguino.suite.site";
const SITE_HOSTS: &[&str] = &["innocentpenguin.com", "www.innocentpenguin.com"];
const SIGNIN_HOSTS: &[&str] = &["id.twitch.tv", "passport.twitch.tv", "www.twitch.tv", "accounts.google.com", "id.kick.com", "kick.com", "www.tiktok.com"];

/// True if the site window may navigate to `u` (https only: the site itself or one of its sign-in providers).
pub fn site_nav_allowed(u: &tauri::Url) -> bool {
    u.scheme() == "https" && u.host_str().map_or(false, |h| SITE_HOSTS.contains(&h) || SIGNIN_HOSTS.contains(&h))
}

fn site_path_ok(p: &str) -> bool {
    p.starts_with('/') && !p.contains("//") && !p.contains("..") && p.len() <= 80 && p.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '/' | '-' | '_'))
}

fn site_url(path: Option<&str>) -> Result<tauri::Url, String> {
    let p = path.map(str::trim).filter(|p| !p.is_empty() && *p != "/");
    if let Some(p) = p {
        if !site_path_ok(p) {
            return Err("site path: letters, digits, '/', '-' and '_' only".into());
        }
    }
    format!("{}{}", SITE_HOME, p.unwrap_or("/")).parse::<tauri::Url>().map_err(|_| "bad site url".to_string())
}

fn site_profile_dir(app: &AppHandle) -> PathBuf {
    // Cookies/localStorage of the site login live here (WebView2 encrypts them). Outside the Suite data folder and the repo.
    app.path().app_local_data_dir().unwrap_or_else(|_| crate::data_dir()).join("webview-site")
}

fn open_in_system_browser(app: &AppHandle, u: &tauri::Url) {
    if matches!(u.scheme(), "http" | "https") {
        #[allow(deprecated)]
        let _ = tauri_plugin_shell::ShellExt::shell(app).open(u.as_str(), None);
    }
}

#[tauri::command]
pub fn open_site_window(app: AppHandle, path: Option<String>) -> Result<WinInfo, String> {
    let url = site_url(path.as_deref())?;
    let lay = app.state::<Layouts>();

    if let Some(w) = app.get_webview_window(SITE_LABEL) {
        let _ = w.show();
        let _ = w.unminimize();
        if path.as_deref().map_or(false, |p| !p.trim().is_empty() && p.trim() != "/") {
            let _ = w.navigate(url);
        }
        let _ = w.set_focus();
        return Ok(info(&app, SITE_LABEL));
    }

    let prev = lay.map.lock().unwrap().get(SITE_LABEL).cloned();
    let on_top = prev.as_ref().map_or(false, |p| p.on_top);
    let icon = tauri::image::Image::new(include_bytes!("../icons/site.rgba"), 256, 256);
    let nav_app = app.clone();
    let win = WebviewWindowBuilder::new(&app, SITE_LABEL, WebviewUrl::External(url))
        .title(SITE_TITLE)
        .icon(icon)
        .map_err(|e| e.to_string())?
        .inner_size(1280.0, 860.0)
        .min_inner_size(480.0, 400.0)
        .always_on_top(on_top)
        .data_directory(site_profile_dir(&app))
        .on_navigation(site_nav_allowed)
        .on_new_window(move |u, _| {
            // target=_blank / window.open: stay in this window for the site and its sign-in, otherwise the system browser
            if site_nav_allowed(&u) {
                if let Some(w) = nav_app.get_webview_window(SITE_LABEL) {
                    let _ = w.navigate(u);
                }
            } else {
                open_in_system_browser(&nav_app, &u);
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .visible(false)
        .build()
        .map_err(|e| e.to_string())?;

    crate::siteicon::set_window_aumid(&win, SITE_AUMID);

    lay.map.lock().unwrap().insert(
        SITE_LABEL.to_string(),
        Saved { url: SITE_HOME.to_string(), title: SITE_TITLE.to_string(), on_top, decorations: true, open: true, x: prev.as_ref().map_or(0, |p| p.x), y: prev.as_ref().map_or(0, |p| p.y), w: prev.as_ref().map_or(0, |p| p.w), h: prev.as_ref().map_or(0, |p| p.h), monitor: prev.as_ref().and_then(|p| p.monitor.clone()) },
    );
    let req = OpenReq { label: SITE_LABEL.into(), url: SITE_HOME.into(), title: None, width: None, height: None, monitor: None, place: None, always_on_top: None, decorations: None, reset: None, bounds: None, remember: None, soft: None };
    place(&app, &win, &req, prev.as_ref(), false);
    let _ = win.show();
    let _ = win.set_focus();
    snapshot(&app, &win, true);

    let handle = app.clone();
    let w2 = win.clone();
    win.on_window_event(move |ev| match ev {
        WindowEvent::Moved(_) | WindowEvent::Resized(_) => snapshot(&handle, &w2, true),
        WindowEvent::CloseRequested { .. } => {
            let lay = handle.state::<Layouts>();
            if let Some(e) = lay.map.lock().unwrap().get_mut(w2.label()) {
                e.open = false;
            }
            lay.flush(true);
        }
        _ => {}
    });
    lay.flush(true);
    Ok(info(&app, SITE_LABEL))
}

/// Sign out of the site window for good: deletes its own WebView2 profile folder (only that one). The window must be closed.
#[tauri::command]
pub fn clear_site_data(app: AppHandle) -> Result<(), String> {
    if app.get_webview_window(SITE_LABEL).is_some() {
        return Err("close the site window first".into());
    }
    let dir = site_profile_dir(&app);
    if dir.file_name().map_or(false, |n| n == "webview-site") && dir.exists() {
        std::fs::remove_dir_all(&dir).map_err(|e| e.to_string())?;
    }
    Ok(())
}
