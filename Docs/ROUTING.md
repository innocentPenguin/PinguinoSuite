# Routing and fallback architecture

Front door: **PinguinoRouter** on Twitch Chat Message (133). Roles, accounts, aliases, action names, senders and fallbacks come from `bots.json` (in the data folder; env `BVQ_DATA_DIR`). Only PinguinoB0t has a Twitch account; replies go through its sender (the helix sender is untried live).

Flow: message → ignore bots/self/`pinguinoRouted` → `!` command → Core; mention/alias → target role; otherwise → Chat. Each module returns `handled | pass | defer`; on `pass` or failure the router walks the role's fallback chain, finally a local canned reply.

## Known weakness (fix before enabling live)
Result passing uses ONE global var `pinguino.result` (`Shared\PinguinoRouter.cs` ~line 209). Two near-simultaneous chat messages can read each other's result. Plan:
1. Key by message: `pinguino.result.<msgId>`, deleted after read.
2. Dedupe on `msgId` (ignore a replayed message).
3. Append one line per decision to `routing.log` (msgId, role, who answered, reason, ms).
4. Timeout → local fallback so chat never goes silent.
5. Verify in the real Streamer.bot (build 2026-08-06) what `CPH.RunAction(name, true)` does (argument inheritance, blocking, return value) with a throwaway action before relying on it.

Status: design only. The code change is not made yet; `Tests\bots` has 40 passing simulated routing checks to extend.
