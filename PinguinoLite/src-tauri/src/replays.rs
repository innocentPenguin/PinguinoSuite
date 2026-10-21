// Rocket League replay scanner + local parser (Docs/REPLAY_STATS_PLAN.md).
// Finds new .replay files in the streamer's own replay folders, parses the HEADER only (boxcars, no network data, offline, no key),
// and writes one small result JSON per match plus an index. Raw replays are never copied or sent; results carry no paths or account ids.
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{json, Map, Value};

static SCAN_LOCK: Mutex<()> = Mutex::new(());

fn root() -> PathBuf {
    crate::lite_dir().join("replays")
}

/// Folders watched: the two standard Rocket League ones (Steam: Demos, Epic: DemosEpic) + one path per line in <state dir>\replay_dirs.txt.
pub fn scan_dirs() -> Vec<PathBuf> {
    let mut v = Vec::new();
    if let Ok(home) = std::env::var("USERPROFILE") {
        let base = PathBuf::from(home).join("Documents").join("My Games").join("Rocket League").join("TAGame");
        v.push(base.join("Demos"));
        v.push(base.join("DemosEpic"));
    }
    if let Ok(t) = std::fs::read_to_string(crate::state_dir().join("replay_dirs.txt")) {
        for l in t.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
            v.push(PathBuf::from(l));
        }
    }
    v
}

// ---------- pure extraction (unit-tested) ----------

fn num(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.parse().ok(),
        Value::Object(o) => o.get("value").and_then(num),
        _ => None,
    }
}

fn text(v: &Value) -> Option<String> {
    match v {
        Value::String(s) => Some(s.clone()),
        Value::Object(o) => o.get("value").and_then(text),
        _ => None,
    }
}

fn platform(v: Option<&Value>) -> String {
    let t = v.and_then(text).unwrap_or_default();
    t.trim_start_matches("OnlinePlatform_").to_lowercase()
}

/// Header properties as a JSON object, whether boxcars serialised them as a map or as [key, value] pairs.
fn props_object(replay: &Value) -> Map<String, Value> {
    match replay.get("properties") {
        Some(Value::Object(o)) => o.clone(),
        Some(Value::Array(a)) => a
            .iter()
            .filter_map(|p| p.as_array().filter(|p| p.len() == 2).and_then(|p| Some((p[0].as_str()?.to_string(), p[1].clone()))))
            .collect(),
        _ => Map::new(),
    }
}

/// Twitch lookup: key "<platform>|<lowercase in-game name>" and "|<name>" -> Twitch username (from the Suite's players.json).
pub type TwitchMap = HashMap<String, String>;

pub fn twitch_map() -> TwitchMap {
    let mut m = TwitchMap::new();
    let Some(root) = crate::suite_root() else { return m };
    let Ok(t) = std::fs::read_to_string(root.join("Data").join("runtime").join("players.json")) else { return m };
    let Ok(Value::Object(o)) = serde_json::from_str::<Value>(t.trim_start_matches('\u{feff}')) else { return m };
    for (k, p) in o {
        let user = p.get("Username").and_then(|v| v.as_str()).unwrap_or(&k).to_string();
        if let Some(g) = p.get("GameId").and_then(|v| v.as_str()).filter(|g| !g.is_empty()) {
            let plat = p.get("Platform").and_then(|v| v.as_str()).unwrap_or("").to_lowercase();
            m.insert(format!("{plat}|{}", g.to_lowercase()), user.clone());
            m.entry(format!("|{}", g.to_lowercase())).or_insert(user);
        }
    }
    m
}

/// Replay (boxcars JSON) -> result JSON. `fallback_id` is used when the header has no match GUID.
pub fn extract(replay: &Value, tw: &TwitchMap, fallback_id: &str) -> Value {
    let p = props_object(replay);
    let g = |k: &str| p.get(k);
    let score = |k: &str| g(k).and_then(num).unwrap_or(0.0) as i64; // RL omits a zero score
    let (s0, s1) = (score("Team0Score"), score("Team1Score"));
    let stats = g("PlayerStats").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    let fps = g("RecordFPS").and_then(num).filter(|f| *f > 0.0).unwrap_or(30.0);
    let mk = |team: i64| -> Vec<Value> {
        stats
            .iter()
            .filter(|s| s.get("Team").and_then(num).map(|t| t as i64) == Some(team))
            .map(|s| {
                let name = s.get("Name").and_then(text).unwrap_or_default();
                let plat = platform(s.get("Platform"));
                let twitch = tw.get(&format!("{plat}|{}", name.to_lowercase())).or_else(|| tw.get(&format!("|{}", name.to_lowercase()))).cloned();
                let n = |k: &str| s.get(k).and_then(num).unwrap_or(0.0) as i64;
                json!({"name": name, "platform": plat, "twitch": twitch, "score": n("Score"), "goals": n("Goals"), "assists": n("Assists"), "saves": n("Saves"), "shots": n("Shots"),
                       "bot": s.get("bBot").and_then(|b| b.as_bool()).unwrap_or(false)})
            })
            .collect()
    };
    let (blue, orange) = (mk(0), mk(1));
    let goals: Vec<Value> = g("Goals")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .map(|x| {
                    let team = if x.get("PlayerTeam").and_then(num).map(|t| t as i64) == Some(0) { "blue" } else { "orange" };
                    let t_s = x.get("frame").and_then(num).map(|f| (f / fps * 10.0).round() / 10.0);
                    json!({"team": team, "player": x.get("PlayerName").and_then(text), "t_s": t_s})
                })
                .collect()
        })
        .unwrap_or_default();
    let complete = !stats.is_empty() && (s0 + s1 > 0 || g("Team0Score").is_some() || g("Team1Score").is_some() || !goals.is_empty());
    let winner = if !complete { Value::Null } else if s0 > s1 { json!("blue") } else if s1 > s0 { json!("orange") } else { json!("draw") };
    // MVP = highest in-game score, only when unique
    let mut all: Vec<(i64, String)> = blue.iter().chain(orange.iter()).map(|x| (x["score"].as_i64().unwrap_or(0), x["name"].as_str().unwrap_or("").to_string())).collect();
    all.sort_by(|a, b| b.0.cmp(&a.0));
    let mvp = if all.len() >= 1 && (all.len() == 1 || all[0].0 > all[1].0) { json!(all[0].1) } else { Value::Null };
    let played = g("Date").and_then(text).map(|d| {
        // "2026-10-21 15-04-05" -> "2026-10-21T15:04:05"
        let d = d.trim().replace(' ', "T");
        match d.split_once('T') { Some((day, t)) => format!("{day}T{}", t.replace('-', ":")), None => d }
    });
    json!({
        "schema": 1,
        "match_id": g("Id").and_then(text).filter(|s| !s.is_empty()).unwrap_or_else(|| fallback_id.to_string()),
        "played_at": played,
        "status": if complete { "complete" } else { "incomplete" },
        "team_size": g("TeamSize").and_then(num).map(|n| n as i64),
        "map": g("MapName").and_then(text),
        "duration_s": g("TotalSecondsPlayed").and_then(num).map(|n| n as i64),
        "blue": {"score": s0, "players": blue},
        "orange": {"score": s1, "players": orange},
        "winner": winner,
        "goals": goals,
        "mvp": mvp,
        "source": "lite-replay-v1"
    })
}

// ---------- scanning ----------

fn fnv(data: &[u8]) -> String {
    let mut h: u64 = 0xcbf29ce484222325;
    for b in data {
        h ^= *b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    format!("f{h:016x}")
}

fn write_atomic(path: &Path, body: &str) -> std::io::Result<()> {
    if let Some(d) = path.parent() {
        std::fs::create_dir_all(d)?;
    }
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, body)?;
    std::fs::rename(&tmp, path)
}

fn safe_name(id: &str) -> String {
    id.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_').take(80).collect()
}

fn parse_file(data: &[u8]) -> Result<Value, String> {
    let r = boxcars::ParserBuilder::new(data).never_parse_network_data().parse().map_err(|e| e.to_string())?;
    serde_json::to_value(&r).map_err(|e| e.to_string())
}

fn mtime_secs(p: &Path) -> Option<u64> {
    std::fs::metadata(p).and_then(|m| m.modified()).ok().and_then(|m| m.duration_since(UNIX_EPOCH).ok()).map(|d| d.as_secs())
}

/// One scan pass. Returns {scanned, new, errors, dirs:[{path,exists}]}.
pub fn scan() -> Value {
    let _g = SCAN_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let dirs = scan_dirs();
    let state_path = root().join("state.json");
    let mut state: Map<String, Value> = std::fs::read_to_string(&state_path).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default();
    let tw = twitch_map();
    let (mut new, mut errors, mut scanned) = (0, 0, 0);
    let now = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    for d in &dirs {
        let Ok(rd) = std::fs::read_dir(d) else { continue };
        for e in rd.flatten() {
            let path = e.path();
            if path.extension().and_then(|x| x.to_str()).map(|x| x.eq_ignore_ascii_case("replay")) != Some(true) {
                continue;
            }
            let (Some(mt), Ok(meta)) = (mtime_secs(&path), e.metadata()) else { continue };
            if now.saturating_sub(mt) < 5 {
                continue; // still being written
            }
            scanned += 1;
            // state key = hash-free fingerprint (name + size + mtime); no full path is stored in any output
            let key = format!("{}|{}|{}", path.file_name().and_then(|n| n.to_str()).unwrap_or(""), meta.len(), mt);
            if state.contains_key(&key) {
                continue;
            }
            let Ok(data) = std::fs::read(&path) else { continue };
            match parse_file(&data) {
                Ok(rep) => {
                    let res = extract(&rep, &tw, &fnv(&data));
                    let id = safe_name(res["match_id"].as_str().unwrap_or(""));
                    if id.is_empty() || write_atomic(&root().join("results").join(format!("{id}.json")), &serde_json::to_string_pretty(&res).unwrap_or_default()).is_err() {
                        errors += 1;
                        state.insert(key, json!({"error": "could not write result"}));
                    } else {
                        new += 1;
                        state.insert(key, json!({"match_id": id}));
                    }
                }
                Err(e) => {
                    errors += 1;
                    state.insert(key, json!({"error": e}));
                }
            }
        }
    }
    if new > 0 || errors > 0 || !state_path.exists() {
        let _ = write_atomic(&state_path, &serde_json::to_string_pretty(&state).unwrap_or_default());
        rebuild_index(&dirs);
    }
    json!({"scanned": scanned, "new": new, "errors": errors, "dirs": dirs.iter().map(|d| json!({"name": d.file_name().and_then(|n| n.to_str()), "exists": d.is_dir()})).collect::<Vec<_>>()})
}

fn rebuild_index(dirs: &[PathBuf]) {
    let mut items: Vec<Value> = Vec::new();
    if let Ok(rd) = std::fs::read_dir(root().join("results")) {
        for e in rd.flatten() {
            if let Some(v) = std::fs::read_to_string(e.path()).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok()) {
                items.push(json!({"match_id": v["match_id"], "played_at": v["played_at"], "status": v["status"], "team_size": v["team_size"],
                    "blue": v["blue"]["score"], "orange": v["orange"]["score"], "winner": v["winner"], "mvp": v["mvp"],
                    "file": format!("results/{}", e.file_name().to_string_lossy())}));
            }
        }
    }
    items.sort_by(|a, b| b["played_at"].as_str().unwrap_or("").cmp(a["played_at"].as_str().unwrap_or("")));
    let ms = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0);
    // dir names only (no personal paths)
    let names: Vec<Value> = dirs.iter().map(|d| json!(d.file_name().and_then(|n| n.to_str()))).collect();
    let _ = write_atomic(&root().join("index.json"), &serde_json::to_string_pretty(&json!({"schema": 1, "updated_at_ms": ms, "scan_dirs": names, "items": items})).unwrap_or_default());
}

/// Background loop: scan at start and every 30 s. Never blocks the UI; never touches anything but the replay folders (read) and <lite dir>\replays (write).
pub fn start() {
    std::thread::spawn(|| loop {
        let _ = scan();
        std::thread::sleep(Duration::from_secs(30));
    });
}

#[tauri::command]
pub async fn replay_scan() -> Value {
    scan()
}

/// For the Replays page: the index (latest 50) and which watch folders exist (names only for the UI; the real paths stay on this PC).
#[tauri::command]
pub fn replay_index() -> Value {
    let idx: Value = std::fs::read_to_string(root().join("index.json")).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or(Value::Null);
    let items: Vec<Value> = idx["items"].as_array().map(|a| a.iter().take(50).cloned().collect()).unwrap_or_default();
    let dirs: Vec<Value> = scan_dirs().iter().map(|d| json!({"name": d.file_name().and_then(|n| n.to_str()), "exists": d.is_dir()})).collect();
    json!({"items": items, "dirs": dirs})
}

#[cfg(test)]
mod tests {
    use super::*;

    // shaped like `rrrocket` output (boxcars serialisation); a zero score is omitted, as in real replays
    fn sample() -> Value {
        json!({"properties": {
            "Id": "ABCD1234", "Date": "2026-10-21 15-04-05", "TeamSize": 3, "MapName": "Stadium_P", "TotalSecondsPlayed": 312, "RecordFPS": 30.0,
            "Team0Score": 4, "Team1Score": 2,
            "PlayerStats": [
                {"Name": "We1rdShark2.0", "Platform": {"kind": "OnlinePlatform", "value": "OnlinePlatform_Epic"}, "OnlineID": "99887766", "Team": 0, "Score": 512, "Goals": 2, "Assists": 1, "Saves": 3, "Shots": 5, "bBot": false},
                {"Name": "Rival", "Platform": {"kind": "OnlinePlatform", "value": "OnlinePlatform_Steam"}, "OnlineID": 9, "Team": 1, "Score": 300, "Goals": 2, "Assists": 0, "Saves": 1, "Shots": 4, "bBot": false}
            ],
            "Goals": [{"frame": 1230, "PlayerName": "We1rdShark2.0", "PlayerTeam": 0}, {"frame": 3000, "PlayerName": "Rival", "PlayerTeam": 1}]
        }})
    }

    #[test]
    fn winner_stats_and_twitch_link() {
        let mut tw = TwitchMap::new();
        tw.insert("epic|we1rdshark2.0".into(), "yoohoo15".into());
        let r = extract(&sample(), &tw, "fallback");
        assert_eq!(r["status"], "complete");
        assert_eq!(r["winner"], "blue");
        assert_eq!(r["match_id"], "ABCD1234");
        assert_eq!(r["played_at"], "2026-10-21T15:04:05");
        assert_eq!(r["blue"]["players"][0]["twitch"], "yoohoo15");
        assert_eq!(r["blue"]["players"][0]["saves"], 3);
        assert_eq!(r["orange"]["players"][0]["platform"], "steam");
        assert_eq!(r["orange"]["players"][0]["twitch"], Value::Null);
        assert_eq!(r["mvp"], "We1rdShark2.0");
        assert_eq!(r["goals"][0]["t_s"], 41.0);
        assert!(!r.to_string().contains("OnlineID") && !r.to_string().contains("99887766"), "no account ids in output");
    }

    #[test]
    fn zero_score_omitted_and_pairs_format() {
        // orange scored 0 (key absent), properties as [key, value] pairs
        let mut s = sample();
        let o = s["properties"].as_object_mut().unwrap();
        o.remove("Team1Score");
        let pairs: Vec<Value> = o.iter().map(|(k, v)| json!([k, v])).collect();
        let r = extract(&json!({"properties": pairs}), &TwitchMap::new(), "x");
        assert_eq!(r["orange"]["score"], 0);
        assert_eq!(r["winner"], "blue");
    }

    #[test]
    fn unfinished_replay_is_incomplete_and_uses_fallback_id() {
        let r = extract(&json!({"properties": {"PlayerStats": []}}), &TwitchMap::new(), "f123");
        assert_eq!(r["status"], "incomplete");
        assert_eq!(r["winner"], Value::Null);
        assert_eq!(r["match_id"], "f123");
    }

    #[test]
    fn draw() {
        let mut s = sample();
        s["properties"]["Team1Score"] = json!(4);
        assert_eq!(extract(&s, &TwitchMap::new(), "x")["winner"], "draw");
    }
}
