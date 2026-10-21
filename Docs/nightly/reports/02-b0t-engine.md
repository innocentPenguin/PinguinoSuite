# 02 PinguinoB0t engine - Phase 3 report (2026-10-21)

Scope: Core (`PinguinoB0t/PinguinoBotCore.cs`), Router, Firsts, Host modules for chat commands/boards, players overlays.

## New capabilities
- One duplicate guard for every send path: the same line (normalised) is sent once in 30 s (`PINGUINO_DUP_SECONDS`, 0 = off for tests). Host `SendAs`/`Say` and the bots share it; the Host bot-test line obeys it too.
- Hype/goal announcements, `!uptime`, `!tune names <seconds> <fadeMs>` (overlay name alternation, published to the overlays in `LIVE_STATE.overlay`).
- Players overlays (horizontal + vertical): stream name and Epic name crossfade, fixed-size text with ellipsis, mini team bar, demo URLs.
- First 5: payouts (15000/10500/7500/4500/3000) go straight into the economy through the `PinguinoGrantPoints` native action with an idempotent id, no `!addpoints` line in chat.
- `COMMANDS.md` is generated from `commands.json` (`Tools/gen-commands-md.py`).
- Privacy: viewers who typed `!optmeout` are shown as "Anonymous Penguin" on the Host top boards, `!mine`-style lines, streak tops and economy/gamble lines.

## Audit (3 rounds)
1. Send paths + secrets (e1e1fde): bot test line guarded; `Tools/test-host-secrets.py` (no token/client id/JWT in console, logs, data files, read APIs, even on 401/429/500); `Tools/test-host-audit.py` (one command = one reply, cooldowns, mod/broadcaster-only commands silent for viewers, viewers cannot move points).
2. Opt-outs (80a4f41): anon names on Host public boards fixed; `Tools/test-host-anon.py`.
3. Doubled replies: no command is handled by two modules (only Helper -> Core calls, guarded by a join guard + msgId dedupe in the Router). Suites: Core all pass, Chat 292, Helper 230, bots routing 93, `node Shared/sync-shared.mjs --check` clean.

## Known issues / open
- Host restart needed for: Firsts payout, `!tune names`, Core overlay block, anon-name fix (02/00 restart; I do not).
- `moderator:read:chatters` needs one streamer re-sign-in on the Host `/setup` page; until then the economy uses the "active in chat" fallback.
- `test-host-obs.py` fails (not mine); `test-host-profilesync.py` prints a TypeError while passing (reported).
- The anon list is cached 20 s, so a fresh `!optmeout` can show the name for up to 20 s on a board line.
- Overlays only need an OBS browser-source refresh.

## Plans
- Per-viewer cooldown coverage for Rank / BotMention / Latest / Ops (they have no cooldown of their own; they run behind the shared command cooldown).
- Fold the Chat privacy list and the Host anon list into one shared reader.
