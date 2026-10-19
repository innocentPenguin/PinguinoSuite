# Routing and fallback architecture

Front door: **PinguinoRouter** on Twitch Chat Message (133). Roles, accounts, aliases, action names, senders and fallbacks come from `bots.json` (in the data folder; env `BVQ_DATA_DIR`). Only PinguinoB0t has a Twitch account; replies go through its sender (the helix sender is untried live).

Flow: message → ignore bots/self/`pinguinoRouted` → `!` command → Core; mention/alias → target role; otherwise → Chat. Each module returns `handled | pass | defer`; on `pass` or failure the router walks the role's fallback chain, finally a local canned reply.

## Correlation (done 2026-10-19)
- The router gives each chat message an id (`msgId` from Twitch, else a hash of user+text+2 s) and passes it as argument `pinguinoMsgId`.
- Modules write their answer to `pinguino.result.<msgId>`; the router reads then deletes it. Without the argument (module run by hand) the old `pinguino.result` is used.
- Replays: ids seen in the last 60 s (max 50, global `pinguino.seen`) are ignored.
- `routing.log` (data folder, rotates at 512 KB): `time, msgId, role, outcome, reason, ms` per decision (handled / pass / defer / skip / failed / duplicate / unhandled).
- Tests: `Testsots` (54 checks).

## Still open
1. Timeout → local fallback: `RunAction(name,true)` blocks, so a hung module cannot be timed out from C#. Needs a live check.
2. Verify in the real Streamer.bot (build 2026-08-06) what `CPH.RunAction(name, true)` does (argument inheritance, blocking, return value) with a throwaway action before relying on it; also that `msgId` is the real argument name on trigger 133.
