// PinguinoInstaller.exe: opens the Penguino-styled installer window (Installer.hta, built into Windows via mshta). Std only.
// Build: rustc -O --edition 2021 pinguino_installer.rs -o PinguinoInstaller.exe
#![windows_subsystem = "windows"]
use std::process::Command;
fn main() {
    let dir = std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.to_path_buf())).unwrap_or_default();
    let hta = dir.join("Installer.hta");
    if hta.exists() { let _ = Command::new("mshta").arg(hta).spawn(); }
}
