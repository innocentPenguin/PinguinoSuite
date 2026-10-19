"""No-token pre-stream readiness list for the Console: [{id,label,status pass|warn|fail,detail}]."""
import config
import secrets_store

REQUIRED = {"twitch"}          # the stream cannot run without this one; others are optional


def _conn(c):
    st, name = c["status"], c["label"]
    if st == "connected":
        return "pass", c.get("detail") or "connected"
    if c["platform"] in REQUIRED:
        return "fail", f"{st}: {c.get('detail') or 'not connected'}"
    if st in ("needs_auth", "disabled", "disconnected", "waiting"):
        return "warn", f"{st} (optional): {c.get('detail') or ''}".strip()
    return "warn", f"{st}: {c.get('detail') or ''}".strip()


def run(connectors, store, pipeline, inbox):
    out = []

    def add(id, label, status, detail=""):
        out.append({"id": id, "label": label, "status": status, "detail": detail})

    for c in connectors.values():
        s, d = _conn(c.describe())
        add("conn-" + c.platform, c.label + " connection", s, d)
    try:
        n = len(store.recent(1))
        store.kv_get("active_profile")
        add("store", "Message database readable", "pass", "ok" + ("" if n else " (empty)"))
    except Exception as e:
        add("store", "Message database readable", "fail", str(e)[:120])
    for name, f in (("settings", config.SETTINGS_FILE), ("rules", config.RULES_FILE)):
        try:
            if f.exists():
                f.read_text("utf-8")
            add("file-" + name, f"{name}.json readable", "pass", "ok" if f.exists() else "using defaults")
        except Exception as e:
            add("file-" + name, f"{name}.json readable", "fail", str(e)[:120])
    q, dropped = inbox.q.qsize(), pipeline.stats.get("dropped", 0)
    add("queue", "Message queue healthy", "pass" if q < 200 and not dropped else "warn", f"queue {q}, dropped {dropped}")
    try:
        nw = len(store.load_windows())
        add("windows", "Chat windows set up", "pass" if nw else "warn", f"{nw} window(s)" if nw else "none saved: pick a layout in Multi")
    except Exception as e:
        add("windows", "Chat windows set up", "fail", str(e)[:120])
    s = config.settings()
    if s["priority_mode"] != "local":
        ok = bool(secrets_store.get("ai_key")) or s["ai_provider"] == "ollama"
        add("ai", "AI-assisted ranking", "pass" if ok else "warn", "ready" if ok else "mode is on but no AI key (falls back to local)")
    else:
        add("ai", "Ranking mode", "pass", "local rules (no AI needed)")
    return out
