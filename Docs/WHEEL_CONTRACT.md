# Tournament wheel — integration contract (PinguinoBot ⇄ PinguinoSite, Unit 05)

Principle: **one authoritative owner.** Core owns the wheel session; the Site only renders and asks to spin. No second selection engine.

## Chat commands
- `!me` registers for the wheel (separate from `!join`). The Router passes it to Core's wheel module. Mods: open / close / remove / undo / retry.

## Session file `wheel_session.json` (Core-owned)
`id, status(open|closed|spun), mode(random|balanced), teamSize(default 2), seed, entrants[{twitchId, name, epic, mmr|null, flagged}], teams[{n, members, announced}], history[], undo[]`

## Rules
- Dedupe by twitchId; missing MMR → DefaultMmr and `flagged` (balanced mode only).
- `random` = uniform seeded shuffle. `balanced` is labelled **RIGGED/BALANCED by MMR** everywhere, never "random".
- Odd count: config `oddPolicy` = trio | bye.
- Seeded PRNG: same seed + entrants = same teams (unit-testable). Undo restores the previous teams; retry draws with a new seed and keeps the old one in history.

## Site API (authenticated, same WebSyncKey scheme)
- `GET /api/wheel/session` → current session (read-only).
- `POST /api/wheel/spin {sessionId}` → Core computes with its stored seed and returns the result; the Site animates it for the OBS source. Reconnects re-fetch; they never re-spin.

## Announcements (PinguinoB0t)
Per team: `Team 1: Ivan + Player2!` (set `announced=true`, so reconnects never repeat), then the full roster in one paragraph, split at team boundaries to stay under the Twitch limit (450 chars per message).

Status: contract only; implementation is Milestone 2.
