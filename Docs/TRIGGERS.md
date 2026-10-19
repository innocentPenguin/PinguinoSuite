# Trigger ownership (one owner per trigger)

| Trigger (Streamer.bot type) | Owner after cutover | Today (legacy owner) |
|---|---|---|
| `!` game commands (401 ×22: join leave queue pos kick next reroll balance register mmr win lobby format setmmr …) | **PinguinoBot** (Core) | BVQ Engine |
| Twitch Chat Message (133) | **PinguinoRouter** only | chatbot, chat |
| First Words (120) | **PinguinoChat** (First module) | chat (first time today) T2 (+Copy), First TIme System (Bell) |
| Sub / Resub / Gift (103/104/105) + prime/super | **PinguinoChat** Alert module | Normal/Resub/Super/Prime/Gifted actions |
| Stream status (154/155) | PinguinoBot (WasLive flag) | BVQ Engine |
| Follow / Cheer / Raid | unchanged legacy actions until M2 | Followed, Cheers, Raided (off) |
| Command `ChatGPT Call` (regex `@?PinguinoB0t`) | **disabled** — Router handles mentions | enabled (double-answer risk) |
| `!me` (wheel) | Router → Core wheel module | n/a (new) |
| Helper | no trigger; invoked via Router | n/a |

Rules: the Router never owns `!` command triggers (Core does). Legacy actions are disabled, not deleted. Messages already routed carry `pinguinoRouted=true`, so bots never re-enter the router.

- `!me`, `!wheel`: chat commands -> PinguinoB0t core action (owner adds in Streamer.bot).
