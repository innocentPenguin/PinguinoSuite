# Sub intro clips (PinguinoHost)

A subscriber's FIRST chat message of each stream plays their own clip on the stream. Nothing is said in chat.

- **Who**: Twitch subscriber badge tier from the chat tags (`subscriber/3012` = T3, `2xxx` = T2, below 1000 = T1). Once per person per stream (the list is cleared when the stream goes live; it survives a Host restart in `intro_state.json`). Only while live (setting).
- **Clips**: `Data\intros\<twitch login>.mp4` (or `.webm`, `.gif`). Vertical T3 clips: `<login>_v.mp4` (plays on the T3 vertical source). Optional per-tier fallbacks `_default_t1.mp4`, `_default_t2.mp4`, `_default_t3.mp4`. No clip and no default = nothing plays.
- **OBS browser sources** (800x600 each; resize them in OBS; clips are letterboxed): `http://127.0.0.1:8770/overlay/intro?slot=t1`, `...slot=t2`, `...slot=t3`, `...slot=t3v`. Audio plays through the source.
- **Queue**: one intro at a time across all sources; the next is the highest tier waiting (T3 > T2 > T1), first come first served inside a tier; nobody is queued twice. An intro whose browser source is not open in OBS is skipped, not stuck.
- **Controls**: `http://127.0.0.1:8770/intro` (skip, clear, test a name, forget who played, settings). API: `GET /api/intro`, `POST /api/intro/skip|clear|reset|test|settings`. Settings live in `Data\runtime\intro_settings.json` (Enabled, OnlyWhileLive, T1/T2/T3, UseTierDefaults, SkipOfflineSlots, MaxPlaySec, GifSec, Volume, Dir).
- **Tests**: `python Tools/test-host-intro.py`.
