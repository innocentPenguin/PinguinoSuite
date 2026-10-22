// PinguinoSuiteSetup.exe: one file that carries the whole installer. Build-Installer.mjs appends a payload zip (node.exe, installer scripts, the release, the sealed repo key)
// plus a 16-byte trailer (payload length u64 LE + "PGSETUP1"). On start it unpacks the payload to %TEMP%\PinguinoSetup\<pid> with Windows' built-in tar and opens Installer.hta.
// Without a payload (a plain dev build) it opens Installer.hta next to itself. Std only, no crates. Build: rustc -O --edition 2021 pinguino_installer.rs -o PinguinoInstaller.exe
#![windows_subsystem = "windows"]
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::PathBuf;
use std::process::Command;

const MAGIC: &[u8; 8] = b"PGSETUP1";

fn alert(msg: &str) {
    let m = msg.replace('\'', " ").replace('\\', "/");
    let _ = Command::new("mshta").arg(format!("javascript:alert('{}');close()", m)).status();
}

/// (payload start, payload length) when the trailer is present.
fn payload_len(f: &mut File) -> Option<(u64, u64)> {
    let total = f.metadata().ok()?.len();
    if total < 16 {
        return None;
    }
    f.seek(SeekFrom::End(-16)).ok()?;
    let mut t = [0u8; 16];
    f.read_exact(&mut t).ok()?;
    if &t[8..16] != MAGIC {
        return None;
    }
    let n = u64::from_le_bytes(t[0..8].try_into().ok()?);
    if n == 0 || n + 16 > total {
        return None;
    }
    Some((total - 16 - n, n))
}

fn main() {
    let exe = match std::env::current_exe() {
        Ok(p) => p,
        Err(_) => return,
    };
    if let Ok(mut f) = File::open(&exe) {
        if let Some((start, len)) = payload_len(&mut f) {
            let base = std::env::temp_dir().join("PinguinoSetup").join(std::process::id().to_string());
            let _ = std::fs::remove_dir_all(&base);
            if std::fs::create_dir_all(&base).is_err() {
                return alert("Setup could not create a temporary folder.");
            }
            let zip: PathBuf = base.join("payload.zip");
            let ok = (|| -> std::io::Result<()> {
                f.seek(SeekFrom::Start(start))?;
                let mut out = File::create(&zip)?;
                let mut buf = vec![0u8; 1 << 20];
                let mut left = len;
                while left > 0 {
                    let want = left.min(buf.len() as u64) as usize;
                    let n = f.read(&mut buf[..want])?;
                    if n == 0 {
                        return Err(std::io::ErrorKind::UnexpectedEof.into());
                    }
                    out.write_all(&buf[..n])?;
                    left -= n as u64;
                }
                Ok(())
            })();
            if ok.is_err() {
                return alert("Setup could not unpack itself (is the disk full?).");
            }
            let x = base.join("x");
            let _ = std::fs::create_dir_all(&x);
            let tar = std::env::var("SystemRoot").map(|r| PathBuf::from(r).join("System32").join("tar.exe")).unwrap_or_else(|_| PathBuf::from("tar"));
            let st = Command::new(tar).arg("-xf").arg(&zip).arg("-C").arg(&x).status();
            let _ = std::fs::remove_file(&zip);
            if !matches!(st, Ok(s) if s.success()) {
                return alert("Setup could not unpack itself. Windows 10 1803 or newer is required.");
            }
            let hta = x.join("Installer").join("Installer.hta");
            if !hta.exists() {
                return alert("Setup is damaged (Installer.hta missing). Download it again.");
            }
            let _ = Command::new("mshta").arg(hta).status(); // wait for the window, then remove the unpacked copy
            let _ = std::fs::remove_dir_all(&base);
            return;
        }
    }
    let dir = exe.parent().map(|p| p.to_path_buf()).unwrap_or_default();
    let hta = dir.join("Installer.hta");
    if hta.exists() {
        let _ = Command::new("mshta").arg(hta).spawn();
    }
}
