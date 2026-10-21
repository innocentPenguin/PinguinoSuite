# 02 Helper engine report, 2026-10-21 (Phase 3)

All commits are local, none pushed. The Host needs a restart (by 00) for the Helper commits to go live; the knowledge packs reload by themselves.

## Audit (3 rounds, Helper)
- Round 1, commands and cooldowns (74fd13a): `!helper` / `!ask` / `!pinguino` are answered before any other path; opted-out viewers get silence before a cooldown is taken; 30 s per-viewer cooldown (mods exempt) and 10 s global one hold; replies are one clean line with no leading `!` and no promised action. Fixed: the per-viewer cooldown list grew without limit, it is now pruned past 500 entries.
- Round 2, replies not doubled and opt-outs (54a6ad0): every line goes through the shared "never send the same line twice" guard (30 s). Fixed: a viewer who opted out of the bots or used `!unping` still got organic help in chat; now silent on every path (chime and `!helper` already were).
- Round 3, secrets in logs (54ef677): fixed: a password, token, long key or e-mail typed into a `!helper` question was written raw to Docs\nightly and to the private review log; both now replace it with `[hidden]`. The live review log (git-ignored) holds no labelled password value.
- Final state: 230 Helper checks, 21 pack checks, `sync-shared --check` clean.

## New capabilities since the last report
- `!helper` / `!ask` / `!pinguino` with a nightly-built knowledge pack (public and mod tiers), ranked search with synonyms, AI phrasing from the pack only, and a no-AI read-out.
- Name recognition (bd7b13a): bot names (pinguino, pinguinos, penguins + typos) are ignored in questions; penguin, peng, peg (+ typos) mean Ivan.
- Lobby: name only. The Helper never stores or says a password and cuts anything labelled password/pass/pw.
- New answers: console join via Bedrock Connect link, leaving the queue, leaving the wheel (`!notme`), points, recycler, customs timeout, stream schedule (every day 5:00 PM Central).

## Known issues / plans
- `!pm` in PinguinoHost/HostBots.cs (lines 68-70) still prints a stored password; the Host also needs to push the lobby NAME only to `/api/bot/match-private` (02).
- Bedrock Connect: Ivan believes it needs no DNS, the official page recommends DNS; the answer only links the page.
- Old review-log lines may mention the word "password" in normal chat; none carry a value.
- Plan: let the nightly run feed the unanswered list into the pack.
