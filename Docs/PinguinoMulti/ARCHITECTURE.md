# PinguinoMulti — Architecture (as built, M1)

Location: `Suite\modules\multi\` · port **8766** (localhost only) · registered in `Suite\modules.json` (`multi`, not auto-started yet).

## Flow
```
connector (Twitch EventSub WS) -> Inbox (bounded 2000; never drops mentions/questions)
  -> Pipeline.ingest: dedupe(Seen LRU) -> score(rules.py, explainable) -> Store (SQLite WAL, PK = final dedupe)
  -> CardManager (medium/high tiers) -> hub.emit -> /ws -> every window (Edge --app now, native shell later)
```
Every window is a client of one WS stream of typed events: `hello`, `message`, `card.new`, `card.update`, `conn.status`, `layout.changed`.

## Modules
| File | Role |
|---|---|
| `config.py` | ports, paths, settings (`data\settings.json`, no secrets) |
| `models.py` | `ChatMessage`, `Decision` |
| `priority\rules.py` | local weighted rules, per-rule reset, `Context` for history |
| `cards.py` | card state machine, injectable clock, reply detection from own messages |
| `pipeline.py` | single ingest path + bounded `Inbox` |
| `store.py` | messages, cards, windows, profiles, events (learning log), kv; prune by retention |
| `windows.py` | layouts, profiles, monitor/DPI recovery (`place`), `EdgeShell` (swappable) |
| `connectors\` | `Connector` base (declared capabilities) + `twitch.py` |
| `secrets_store.py` | tokens in Windows Credential Manager (`keyring`) |
| `server.py` | REST + WS + auth callback; origin check on writes |
| `static\index.html` | one UI; window type chosen by `?win=<id>` |

## Safety decisions
- Sending targets exactly one named platform; there is no broadcast endpoint. Read-only connectors have `send:false` and the composer hides them.
- Tokens never touch JSON/logs. The plaintext AI key in `chat_settings.json` is not copied.
- Writes reject non-local `Origin`; WS rejects non-local origins; bind is 127.0.0.1. All chat text is escaped in the UI.
- Monitor loss: saved geometry is never mutated; `place()` computes a safe position each time, so the original is restored on reconnect.

## Native path
`EdgeShell` is the only shell-specific code. A native (Tauri/WebView2) shell replaces it and loads the same UI/WS (Unit 01 spike). Edge limits: no click-through; always-on-top not applied yet.

## Tests
`Suite\.venv\Scripts\python.exe -m pytest Suite\modules\multi\tests` — 27 tests: scoring, anti-gaming, dedupe/restart, card timers (15 s / 5 min), reply detection, burst, Twitch normalize, monitor/DPI.
