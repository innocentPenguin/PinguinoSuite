// PinguinoUpdater.exe: headless launch hook. Runs `node Suite\updater\updater.mjs launch` (max 10 s, then gives up),
// shows a tray balloon only when something happened (updated / waiting until off stream / failed). Always exits 0 so the app starts anyway.
// Build: rustc -O --edition 2021 pinguino_updater.rs -o PinguinoUpdater.exe   (std only, no crates)
#![windows_subsystem = "windows"]
use std::io::Read;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

fn toast(title: &str, msg: &str) {
    let q = |s: &str| s.replace('\'', "''");
    let ps = format!("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;$n=New-Object Windows.Forms.NotifyIcon;$n.Icon=[Drawing.SystemIcons]::Information;$n.Visible=$true;$n.ShowBalloonTip(6000,'{}','{}',[Windows.Forms.ToolTipIcon]::Info);Start-Sleep 7;$n.Dispose()", q(title), q(msg));
    let _ = Command::new("powershell").args(["-NoProfile", "-WindowStyle", "Hidden", "-Command", &ps]).creation_flags(0x0800_0000).spawn();
}

fn json_str(s: &str, key: &str) -> Option<String> {
    let k = format!("\"{}\":", key);
    let i = s.find(&k)? + k.len();
    let r = s[i..].trim_start();
    if r.starts_with("true") { return Some("true".into()); }
    if r.starts_with("false") { return Some("false".into()); }
    let r = r.strip_prefix('"')?;
    Some(r[..r.find('"')?].to_string())
}

fn main() {
    let exe = std::env::current_exe().unwrap_or_default();
    // install root = folder holding Suite\updater (exe lives next to PinguinoApp or in Suite\updater\exe)
    let mut root: Option<PathBuf> = None;
    let mut cur = exe.parent().map(|p| p.to_path_buf());
    while let Some(d) = cur { if d.join("Suite").join("updater").join("updater.mjs").exists() { root = Some(d); break; } cur = d.parent().map(|p| p.to_path_buf()); }
    let Some(root) = root else { return };
    let mut c = Command::new("node");
    c.arg(root.join("Suite").join("updater").join("updater.mjs")).args(["launch", "--install"]).arg(&root)
        .stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null()).creation_flags(0x0800_0000);
    let Ok(mut child) = c.spawn() else { return };
    let t0 = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) if t0.elapsed() > Duration::from_secs(10) => { let _ = child.kill(); return; }
            Ok(None) => std::thread::sleep(Duration::from_millis(100)),
            Err(_) => return,
        }
    }
    let mut out = String::new();
    if let Some(mut so) = child.stdout.take() { let _ = so.read_to_string(&mut out); }
    let line = out.lines().last().unwrap_or("");
    if json_str(line, "skipped").as_deref() == Some("true") { return; }
    let msg = json_str(line, "message").unwrap_or_default();
    if json_str(line, "deferred").as_deref() == Some("true") { toast("PinguinoSuite update waiting", "It will install the next time you start the Suite while off stream."); }
    else if json_str(line, "ok").as_deref() == Some("false") { toast("PinguinoSuite update failed", &format!("Old version kept. {}", msg)); }
    else if json_str(line, "upToDate").as_deref() != Some("true") && msg.contains("->") { toast("PinguinoSuite updated", &msg); }
}
