// Support bundle: one folder (and a .zip when tar.exe is there) Ivan can be sent when something is wrong.
// Everything goes through scrub() first; secrets never leave the PC. Nothing here changes any setting.
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

const TAIL_BYTES: usize = 200_000;
const KEYWORDS: &[&str] = &["token", "secret", "password", "api_key", "api-key", "apikey", "authorization"];

fn is_tok(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b"._~+/=-".contains(&b)
}

/// End of a secret that starts at `i` (lower = ascii-lowercased copy of the same bytes), or None.
fn secret_end(lower: &[u8], i: usize) -> Option<usize> {
    let rest = &lower[i..];
    let run = |from: usize, min: usize, ok: fn(u8) -> bool| -> Option<usize> {
        let n = rest[from..].iter().take_while(|b| ok(**b)).count();
        if n >= min {
            Some(i + from + n)
        } else {
            None
        }
    };
    if rest.starts_with(b"oauth:") {
        return run(6, 10, |b| b.is_ascii_alphanumeric());
    }
    if rest.starts_with(b"bearer") {
        let ws = rest[6..].iter().take_while(|b| b.is_ascii_whitespace()).count();
        if ws == 0 {
            return None;
        }
        return run(6 + ws, 16, is_tok);
    }
    for k in KEYWORDS {
        if rest.starts_with(k.as_bytes()) {
            let mut p = k.len();
            if rest.get(p) == Some(&b'"') || rest.get(p) == Some(&b'\'') {
                p += 1;
            }
            p += rest[p..].iter().take_while(|b| b.is_ascii_whitespace()).count();
            if !matches!(rest.get(p), Some(b':') | Some(b'=')) {
                return None;
            }
            p += 1;
            p += rest[p..].iter().take_while(|b| b.is_ascii_whitespace()).count();
            if rest.get(p).map_or(false, |b| *b == b'"' || *b == b'\'') {
                p += 1;
            }
            let n = rest[p..].iter().take_while(|b| !b.is_ascii_whitespace() && **b != b'"' && **b != b'\'' && **b != b',').count();
            let mut end = p + n;
            if matches!(&rest[p..end], b"bearer" | b"basic") {
                end += rest[end..].iter().take_while(|b| b.is_ascii_whitespace()).count();
                end += rest[end..].iter().take_while(|b| !b.is_ascii_whitespace() && **b != b'"' && **b != b'\'' && **b != b',').count();
            } else if n < 6 {
                return None;
            }
            return Some(i + end);
        }
    }
    None
}

/// Hide the Windows account name in paths: C:\Users\<name>\x becomes C:\Users\<user>\x (also with /, and with the doubled backslashes of JSON).
pub fn mask_user(text: &str) -> String {
    let lower = text.to_ascii_lowercase();
    let (b, l) = (text.as_bytes(), lower.as_bytes());
    let sep = |c: u8| c == b'/' || c == b'\\';
    let (mut out, mut last, mut i) = (String::with_capacity(text.len()), 0, 0);
    while i + 7 < b.len() {
        if l[i..].starts_with(b"users") && i > 0 && sep(b[i - 1]) && sep(b[i + 5]) {
            let mut s = i + 6;
            while s < b.len() && sep(b[s]) {
                s += 1; // JSON escaping doubles the backslash
            }
            let n = b[s..].iter().take_while(|c| !sep(**c) && !matches!(**c, b'"' | b'\'' | b'<' | b'>' | b'|' | b'\r' | b'\n')).count();
            if n > 0 && &text[s..s + n] != "<user>" {
                out.push_str(&text[last..s]);
                out.push_str("<user>");
                last = s + n;
                i = s + n;
                continue;
            }
        }
        i += 1;
    }
    out.push_str(&text[last..]);
    out
}

/// Replace secret-looking text with [removed] (same patterns as the Suite's feedback scrub, plus quoted JSON values), and hide the Windows account name in paths.
pub fn scrub(text: &str) -> String {
    mask_user(&scrub_secrets(text))
}

fn scrub_secrets(text: &str) -> String {
    let lower = text.to_ascii_lowercase();
    let (b, l) = (text.as_bytes(), lower.as_bytes());
    let mut out = String::with_capacity(text.len());
    let (mut i, mut last) = (0, 0);
    while i < b.len() {
        if let Some(end) = secret_end(l, i) {
            out.push_str(&text[last..i]);
            out.push_str("[removed]");
            i = end;
            last = end;
        } else {
            i += 1;
        }
    }
    out.push_str(&text[last..]);
    out
}

/// install.json without anything secret: drop keys that look like secrets (pubkey is public and stays).
pub fn sanitize_install(v: &Value) -> Value {
    match v {
        Value::Object(m) => {
            let mut o = serde_json::Map::new();
            for (k, x) in m {
                let kl = k.to_ascii_lowercase();
                let secret = kl != "pubkey" && (KEYWORDS.iter().any(|w| kl.contains(w)) || kl.contains("sealed") || kl == "key");
                if secret {
                    o.insert(k.clone(), json!("[removed]"));
                } else {
                    o.insert(k.clone(), sanitize_install(x));
                }
            }
            Value::Object(o)
        }
        Value::Array(a) => Value::Array(a.iter().map(sanitize_install).collect()),
        Value::String(s) => Value::String(scrub(s)),
        _ => v.clone(),
    }
}

/// Last `max` bytes of a text, cut on a char boundary and after a line break when possible.
pub fn tail(text: &str, max: usize) -> String {
    if text.len() <= max {
        return text.to_string();
    }
    let mut s = text.len() - max;
    while !text.is_char_boundary(s) {
        s += 1;
    }
    let t = &text[s..];
    match t.find('\n') {
        Some(n) if n + 1 < t.len() => t[n + 1..].to_string(),
        _ => t.to_string(),
    }
}

pub fn bundle_name(secs: u64) -> String {
    format!("bundle-{}", secs)
}

/// Bundles kept in <lite dir>\support: older ones are removed so repeated clicks never fill the disk.
pub const KEEP_BUNDLES: usize = 5;

/// Which entries of the support folder to remove: only "bundle-<digits>" folders and "bundle-<digits>.zip" files, all but the newest `keep`.
pub fn bundles_to_remove(names: &[String], keep: usize) -> Vec<String> {
    let num = |n: &str| -> Option<u64> {
        let stem = n.strip_suffix(".zip").unwrap_or(n);
        stem.strip_prefix("bundle-").filter(|d| !d.is_empty() && d.bytes().all(|b| b.is_ascii_digit())).and_then(|d| d.parse().ok())
    };
    let mut ids: Vec<u64> = names.iter().filter_map(|n| num(n)).collect();
    ids.sort_unstable();
    ids.dedup();
    let cut = ids.len().saturating_sub(keep);
    let old: Vec<u64> = ids.into_iter().take(cut).collect();
    names.iter().filter(|n| num(n).map_or(false, |v| old.contains(&v))).cloned().collect()
}

fn prune_bundles(support: &Path) {
    let Ok(rd) = std::fs::read_dir(support) else { return };
    let names: Vec<String> = rd.flatten().filter_map(|e| e.file_name().into_string().ok()).collect();
    for n in bundles_to_remove(&names, KEEP_BUNDLES) {
        let p = support.join(&n);
        let _ = if p.is_dir() { std::fs::remove_dir_all(&p) } else { std::fs::remove_file(&p) };
    }
}

fn write(dir: &Path, name: &str, body: &str) {
    let p = dir.join(name);
    if let Some(d) = p.parent() {
        let _ = std::fs::create_dir_all(d);
    }
    let _ = std::fs::write(p, body);
}

fn powershell(script: &str) -> String {
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-Command", script]).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    cmd.output().map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_default()
}

/// Windows version, RAM, commit used/limit (KB) and free/used bytes per drive.
fn system_info() -> Value {
    let raw = powershell(
        "$o=Get-CimInstance Win32_OperatingSystem; $d=@(Get-PSDrive -PSProvider FileSystem | ForEach-Object {@{name=$_.Name;free=$_.Free;used=$_.Used}}); \
         @{windows=($o.Caption+' '+$o.Version);ramKB=$o.TotalVisibleMemorySize;commitLimitKB=$o.TotalVirtualMemorySize;commitUsedKB=($o.TotalVirtualMemorySize-$o.FreeVirtualMemory);drives=$d} | ConvertTo-Json -Compress -Depth 4",
    );
    serde_json::from_str(&raw).unwrap_or_else(|_| json!({"error": "could not read system info"}))
}

fn copy_logs(src: &Path, dst: &Path, tag: &str) -> usize {
    let mut n = 0;
    if let Ok(rd) = std::fs::read_dir(src) {
        for e in rd.flatten() {
            let p = e.path();
            let name = p.file_name().and_then(|f| f.to_str()).unwrap_or("file").to_string();
            let ext = p.extension().and_then(|x| x.to_str()).unwrap_or("").to_ascii_lowercase();
            let wanted = ext == "log" || ext == "txt" || (ext == "json" && (name.starts_with("update_status") || name == "status.json"));
            if p.is_file() && wanted {
                if let Ok(t) = std::fs::read_to_string(&p) {
                    write(dst, &format!("logs/{}-{}", tag, name), &scrub(&tail(&t, TAIL_BYTES)));
                    n += 1;
                }
            }
        }
    }
    n
}

pub fn make_bundle(lite: &Path, state: &Path, install: Option<&Path>, verify: Value, replays: Value) -> Result<PathBuf, String> {
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let dir = lite.join("support").join(bundle_name(secs));
    std::fs::create_dir_all(&dir).map_err(|e| format!("could not create {}: {}", dir.display(), e))?;
    write(&dir, "summary.json", &serde_json::to_string_pretty(&json!({"app": "PinguinoLite", "version": env!("CARGO_PKG_VERSION"), "made_at_unix": secs, "note": "Secrets were removed. Check the files if you want."})).unwrap_or_default());
    let inst = install.and_then(|d| std::fs::read_to_string(d.join("install.json")).ok()).and_then(|t| serde_json::from_str::<Value>(&t).ok()).unwrap_or(Value::Null);
    write(&dir, "install.json", &serde_json::to_string_pretty(&sanitize_install(&inst)).unwrap_or_default());
    write(&dir, "verify.json", &scrub(&serde_json::to_string_pretty(&verify).unwrap_or_default()));
    write(&dir, "replays.json", &serde_json::to_string_pretty(&replays).unwrap_or_default());
    write(&dir, "system.json", &serde_json::to_string_pretty(&system_info()).unwrap_or_default());
    let n = copy_logs(lite, &dir, "lite") + copy_logs(state, &dir, "state");
    write(&dir, "logs/count.txt", &format!("{} files\n", n));
    Ok(dir)
}

#[tauri::command]
pub fn support_bundle() -> Value {
    let verify = crate::parts::run_updater(&["verify"]);
    let replays = {
        let r = crate::replays::replay_index();
        json!({"scanned_matches": r["items"].as_array().map_or(0, |a| a.len()), "folders": r["dirs"], "latest": r["items"].as_array().map(|a| a.iter().take(5).cloned().collect::<Vec<_>>())})
    };
    let install = crate::parts::install_dir();
    match make_bundle(&crate::lite_dir(), &crate::state_dir(), install.as_deref(), verify, replays) {
        Ok(dir) => {
            let parent = dir.parent().map(|p| p.to_path_buf()).unwrap_or_default();
            let name = dir.file_name().and_then(|n| n.to_str()).unwrap_or("bundle").to_string();
            let zip = parent.join(format!("{}.zip", name));
            let ok = Command::new("tar.exe")
                .arg("-a")
                .arg("-c")
                .arg("-f")
                .arg(&zip)
                .arg("-C")
                .arg(&parent)
                .arg(&name)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .map(|s| s.success())
                .unwrap_or(false);
            prune_bundles(&parent);
            json!({"ok": true, "folder": dir.to_string_lossy(), "zip": if ok { json!(zip.to_string_lossy()) } else { Value::Null }})
        }
        Err(m) => json!({"ok": false, "message": m}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scrubs_secrets_but_not_plain_text() {
        assert_eq!(scrub("pass oauth:abcdefghij1234 ok"), "pass [removed] ok");
        assert_eq!(scrub("Authorization: Bearer abcdefghijklmnop.qrs"), "[removed]");
        assert_eq!(scrub("x token=abc12345 y"), "x [removed] y");
        assert_eq!(scrub("{\"token\": \"abcdef123456\", \"n\": 1}"), "{\"[removed]\", \"n\": 1}");
        assert_eq!(scrub("password: hunter22"), "[removed]");
        assert_eq!(scrub("token=abc"), "token=abc");
        assert_eq!(scrub("oauth:short"), "oauth:short");
        assert_eq!(scrub("bearer short"), "bearer short");
        let sha = "sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        assert_eq!(scrub(sha), sha);
        assert_eq!(scrub("Größe ÄÖ token=abcdefgh ü"), "Größe ÄÖ [removed] ü");
    }

    #[test]
    fn install_json_loses_secret_keys_only() {
        let v = json!({"profile": "lite", "pubkey": "MCow", "source": {"kind": "github", "sealedToken": "zzzz", "repo": "a/b"}, "parts": ["lite"], "api_key": "k"});
        let s = sanitize_install(&v);
        assert_eq!(s["pubkey"], "MCow");
        assert_eq!(s["source"]["sealedToken"], "[removed]");
        assert_eq!(s["source"]["repo"], "a/b");
        assert_eq!(s["api_key"], "[removed]");
        assert_eq!(s["parts"][0], "lite");
    }

    #[test]
    fn account_name_in_paths_is_hidden() {
        let u = |s: &str| mask_user(s);
        assert_eq!(u(r"C:\Users\ivanm\AppData\x.log"), r"C:\Users\<user>\AppData\x.log");
        assert_eq!(u("c:/users/Ivan M/Documents"), "c:/users/<user>/Documents");
        assert_eq!(u(r#"{"p":"C:\\Users\\ivanm\\x"}"#), r#"{"p":"C:\\Users\\<user>\\x"}"#);
        assert_eq!(u(r"see 'D:\Users\bob' ok"), r"see 'D:\Users\<user>' ok");
        assert_eq!(u("no users here, users/ x"), "no users here, users/ x");
        assert_eq!(u(r"Ünï C:\Users\Zoë\a"), r"Ünï C:\Users\<user>\a");
        assert_eq!(u(&u(r"C:\Users\ivanm\a")), r"C:\Users\<user>\a");
        assert_eq!(scrub(r"token=abcdefgh in C:\Users\ivanm\z"), r"[removed] in C:\Users\<user>\z");
    }

    #[test]
    fn only_old_bundles_are_removed() {
        let n = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<String>>();
        let all = n(&["bundle-1", "bundle-1.zip", "bundle-2", "bundle-3.zip", "bundle-3", "bundle-10", "notes.txt", "bundle-x", "bundle-", "bundle-5.zip.bak"]);
        let mut r = bundles_to_remove(&all, 2);
        r.sort();
        assert_eq!(r, n(&["bundle-1", "bundle-1.zip", "bundle-2"]));
        assert!(bundles_to_remove(&all, 5).is_empty());
        assert!(bundles_to_remove(&n(&["bundle-9"]), 0) == n(&["bundle-9"]));
    }

    #[test]
    fn tail_keeps_the_end_on_a_line() {
        assert_eq!(tail("abc", 10), "abc");
        assert_eq!(tail("aaaa\nbbbb\ncccc", 8), "cccc");
        assert_eq!(tail("ééééé", 5), "éé");
        assert_eq!(bundle_name(5), "bundle-5");
    }
}
