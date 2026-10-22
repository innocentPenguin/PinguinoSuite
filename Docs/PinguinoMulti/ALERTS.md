# Central alerts (Multi)

One engine, one queue, one OBS source. Replaces the scattered follow widget, Host alert popups and intro overlays (those stay as aliases until Ivan switches).

## Use
- OBS browser source, 800x600: `http://127.0.0.1:8766/obs/alerts` (add `?bg=1` to look at it in a normal browser, `?demo=1` loops samples). Works offline; it only renders what the engine sends.
- Editor + tester: Multi `/?type=alerts` (also linked from the OBS widget editor). Profiles (Penguin / Light / Minimal, duplicate your own), per-type template, per-viewer overrides, tests, "what fired" log. Edits save automatically and appear in OBS instantly.
- Types: follow, refollow, sub, resub, gift, cheer (bits), raid, hype, goal, redeem, streak, intro.
- Variables: `{user}` (drawn in the viewer's rank colour), `{amount}`, `{tier}`, `{months}`, `{message}`, `{level}`, `{recipient}`.
- Per type: enabled, silent, priority 1-9, duration, min amount, per-viewer cooldown, max per minute, first-time-only, tiers, layout (card/banner/center/stack), animation in/out, font, colours, opacity/radius/border, sound (file, volume, per-tier file), image/gif/video (above/left/background).

## How events flow
Host feed / `POST /api/events` -> pipeline (stored, shown in chat) -> engine (`alerts.py`, hook `Pipeline.on_event`). Direct real alerts without a chat row: `POST /api/alerts/fire` (intro, goal). Dedupe: event id (kept across restarts, last 500) and same type+viewer+amount within 10 s. Queue: highest priority first, one at a time, gap 0.6 s, max 50. Sim/test-flagged Host items never fire real alerts.

## Testing (never touches credits, stats, points or chat)
- API: `POST /api/alerts/test {type,user,amount,tier,months,message,variant[],source}` (module token). Variants: tier1 tier2 tier3 prime first refollow noavatar long unicode msg.
- `POST /api/alerts/testall`, `/stress {n}`, `/control {action: skip|clear|pause|resume|profile:<name>}`, `GET /api/alerts` (config + log), `POST /api/alerts/preview`.
- Chat (Host, mods/owner): `!alert test <type> [user] [amount] [variant...]`, `!alert testall`, `!alert stress [n]`, `!alert profile <name>`, `!alert skip`, `!alert clear` -> Host POSTs to `/api/alerts/test|testall|stress|control` and says the returned `text`. Contract sent to 02.

## Host fields wanted (02)
`/api/activity` items: stable id, tier, months, message, amount, recipient, avatar, level, rank_colour, first_time, refollow, anonymous, sim, test. Until then Multi falls back to what the feed has.
