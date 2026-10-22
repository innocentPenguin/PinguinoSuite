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

## Watch celebrations
Types: **streak** (watch streak), **watchtime** (hours milestones), **anniversary** (years watching), **comeback** (first stream back). Variables `{streak}` `{hours}` `{years}` (each falls back to `amount`). Streak / watchtime / anniversary have editable **celebration tiers** (default streak 3/5/10/25/50/100, hours 10/50/100/250/500/1000, years 1-5): each tier can override text, second line, priority, duration, accent colour and confetti (confetti canvas in the overlay, penguin palette). The biggest tier reached is used; "exact" types (streak, anniversary) only fire when the number IS a tier, hours fires when at or above the first tier. Test with variants `small mid big huge` (e.g. `!alert test streak penguin big`). Per-viewer overrides work as for every type.
Feeds: Host posts real ones to `POST /api/alerts/fire {type: streak|watchtime|anniversary|comeback, user, streak|hours|years, rank_colour?, avatar?, id}`; EventSub `viewer_milestone` streaks arrive the same way (or as a `streak` activity item).

## Media library + Host import
Sound / image / gif / video fields in the editor have **Upload file...**, **Pick from library** and **Play**. Files (mp3 wav ogg m4a png jpg gif webp webm mp4, max 25 MB, never overwritten) live in `Data\multi\alert_media` and are served at `/alert-media/<name>`. API: `GET/POST /api/alerts/media?name=` (raw body), `POST /api/alerts/media/delete`.
**Import Host sounds** (editor header): reads `Data\runtime\alerts_settings.json` (read-only), shows what it would do, then copies follow/sub/resub/gift/cheer/raid sounds + volumes into the active profile (existing sounds are kept unless `overwrite`). Files must sit inside the Host runtime folder. Host popup scene/source settings are not imported (OBS-scene popups are the old system).

## Other platforms (Kick, YouTube, TikTok)
Events from the other platforms enter the same queue (see Docs/MULTISTREAM_PLAN.md): Super Chat / KICKs / TikTok gifts arrive as `cheer` (amount = whole currency units / KICKs / coins), memberships as `sub`/`resub`/`gift`, follows as `follow`. Extra variables `{platform}` (Kick, Youtube, Tiktok...) and `{currency}` (USD, KICKs, coins). Cards from a non-Twitch platform get a small platform tag; the dedupe key includes the platform so the same name on two platforms is not merged.
