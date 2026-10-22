// "Check for updates" against the public GitHub repo (releases/latest, falling back to tags). No token, no new dependency: HTTPS goes through
// the curl.exe that ships with Windows 10+, with a hard timeout. The UI never talks to the network itself (CSP stays connect-src 'self').
use serde_json::{json, Value};

pub const REPO: &str = "innocentPenguin/PinguinoLite";
pub const RELEASES_URL: &str = "https://github.com/innocentPenguin/PinguinoLite/releases";

/// "v1.2.3-beta" -> [1,2,3] (pre-release suffix ignored); None when there is no number at all.
pub fn parse_ver(s: &str) -> Option<Vec<u64>> {
    let t = s.trim().trim_start_matches(['v', 'V']);
    let core = t.split(['-', '+']).next().unwrap_or("");
    let v: Vec<u64> = core.split('.').map(|p| p.parse::<u64>()).collect::<Result<_, _>>().ok()?;
    if v.is_empty() { None } else { Some(v) }
}

fn padded(a: Vec<u64>, b: Vec<u64>) -> (Vec<u64>, Vec<u64>) {
    let n = a.len().max(b.len());
    let (mut a, mut b) = (a, b);
    a.resize(n, 0);
    b.resize(n, 0);
    (a, b)
}

pub fn newer(latest: &str, current: &str) -> bool {
    match (parse_ver(latest), parse_ver(current)) {
        (Some(a), Some(b)) => {
            let (a, b) = padded(a, b);
            a > b
        }
        _ => false,
    }
}

/// Highest version among tag names ([{name}]); non-version tags are skipped.
pub fn best_tag(tags: &Value) -> Option<String> {
    tags.as_array()?
        .iter()
        .filter_map(|t| t["name"].as_str())
        .filter(|n| parse_ver(n).is_some())
        .max_by(|a, b| {
            let (x, y) = padded(parse_ver(a).unwrap(), parse_ver(b).unwrap());
            x.cmp(&y)
        })
        .map(|s| s.to_string())
}

const RATE: &str = "GitHub is rate-limiting update checks right now. Try again later.";

/// Pure result builder. `rel` = (http status, body) of releases/latest, `tags` = same for /tags (None if not asked).
pub fn build_result(current: &str, rel: (u16, Value), tags: Option<(u16, Value)>) -> Value {
    let mk = |latest: &str, url: String, notes: Value| {
        json!({"ok": true, "current": current, "latest": latest.trim_start_matches(['v', 'V']), "update": newer(latest, current), "url": url, "notes": notes})
    };
    if rel.0 == 200 {
        if let Some(tag) = rel.1["tag_name"].as_str().filter(|t| parse_ver(t).is_some()) {
            let url = rel.1["html_url"].as_str().unwrap_or(RELEASES_URL).to_string();
            return mk(tag, url, rel.1["name"].clone());
        }
    }
    if rel.0 == 403 || rel.0 == 429 {
        return json!({"ok": false, "current": current, "error": RATE});
    }
    if let Some((st, body)) = tags {
        if st == 200 {
            if let Some(t) = best_tag(&body) {
                return mk(&t, format!("{RELEASES_URL}/tag/{t}"), Value::Null);
            }
        }
        if st == 403 || st == 429 {
            return json!({"ok": false, "current": current, "error": RATE});
        }
    }
    json!({"ok": false, "current": current, "error": "No release published yet (or the repository is private). You are on the latest build available to you."})
}

fn get(path: &str) -> Result<(u16, Value), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let out = std::process::Command::new("curl.exe")
            .args(["-s", "-m", "8", "-H", "Accept: application/vnd.github+json", "-H", "User-Agent: PinguinoLite-update-check", "-w", "\n%{http_code}", &format!("https://api.github.com/repos/{REPO}/{path}")])
            .creation_flags(0x0800_0000)
            .output()
            .map_err(|_| "Could not run the update check (curl.exe missing).".to_string())?;
        if !out.status.success() {
            return Err("Could not reach GitHub (offline?).".into());
        }
        let text = String::from_utf8_lossy(&out.stdout);
        let (body, code) = text.rsplit_once('\n').ok_or("Unexpected answer from GitHub.")?;
        Ok((code.trim().parse().unwrap_or(0), serde_json::from_str(body).unwrap_or(Value::Null)))
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Err("Update check is Windows-only.".into())
    }
}

#[tauri::command]
pub async fn check_update(current: String) -> Value {
    let rel = match get("releases/latest") {
        Ok(r) => r,
        Err(e) => return json!({"ok": false, "current": current, "error": e}),
    };
    let tags = if rel.0 == 200 { None } else { get("tags?per_page=30").ok() };
    build_result(&current, rel, tags)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions() {
        assert!(newer("v0.2.0", "0.1.9"));
        assert!(newer("1.10.0", "1.9.0"));
        assert!(newer("0.1.1", "0.1"));
        assert!(!newer("0.1.0", "0.1.0"));
        assert!(!newer("v0.1.0", "0.1.1"));
        assert!(!newer("nightly", "0.1.0"));
        assert_eq!(parse_ver("v1.2.3-beta.1"), Some(vec![1, 2, 3]));
    }

    #[test]
    fn release_newer_equal_and_tags_fallback() {
        let r = build_result("0.1.0", (200, json!({"tag_name": "v0.2.0", "html_url": "https://github.com/x/y/releases/tag/v0.2.0", "name": "Lite 0.2"})), None);
        assert_eq!((r["ok"].clone(), r["update"].clone(), r["latest"].clone()), (json!(true), json!(true), json!("0.2.0")));
        let r = build_result("0.2.0", (200, json!({"tag_name": "v0.2.0"})), None);
        assert_eq!(r["update"], false);
        let tags = json!([{"name": "v0.1.0"}, {"name": "v0.3.1"}, {"name": "latest"}, {"name": "v0.3.0"}]);
        let r = build_result("0.1.0", (404, Value::Null), Some((200, tags)));
        assert_eq!(r["latest"], "0.3.1");
        assert_eq!(r["update"], true);
        assert!(r["url"].as_str().unwrap().ends_with("/tag/v0.3.1"));
    }

    #[test]
    fn no_release_private_and_rate_limit_are_graceful() {
        let r = build_result("0.1.0", (404, Value::Null), Some((404, Value::Null)));
        assert_eq!(r["ok"], false);
        assert!(r["error"].as_str().unwrap().contains("No release"));
        let r = build_result("0.1.0", (403, json!({"message": "rate limit"})), None);
        assert!(r["error"].as_str().unwrap().contains("rate-limiting"));
        assert_eq!(build_result("0.1.0", (404, Value::Null), Some((200, json!([]))))["ok"], false);
    }
}
