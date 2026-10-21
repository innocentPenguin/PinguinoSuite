# 02 ChattyPinguino engine report, 2026-10-21 (Phase 3)

## New capabilities (all committed locally, none pushed, no module restarted by me)
- 7257d8d, 3223158: the old Nightbot fun/lore commands (87 enabled in `PinguinoChat/canned_commands.json`) are answered by Chatty with the same texts; the Host stays silent on any term Chatty owns. HostLore speaks fun/person lines as Chatty and info/link/clip lines as B0t.
- 2b403fe: honest answers to "can you make commands / change the title" (no AI call), playful single reply to a bare name call, `ChatReplies` default on.
- c24ce4e: Chatty stays out of everything the Helper answers (points, recycler, 15-min timeout, incomplete games, wheel), with a regression test.
- 223bd42, 5c89b3f: names rule. "pinguino(s)", "penguins" and typos call a bot; "penguin", "peng", "peg" mean Ivan and never call one.
- afc0417: per Ivan, `!gay` on, `!grindr` / `!feetfinder` / `!onlyfans` point to the Discord, `!trapaccount` removed, `!goon` / `!weiner` stay held.

## Audit (3 rounds)
- R1 a4a6a21: an alias no longer bypasses a canned command's cooldown; one canned line per person per 6 s and one per 2 s chat-wide; `$(touser)` must be a plain username (no links or /commands through the bot); bare `!8ball` hint has a 30 s cooldown.
- R2 d0ecab5: a replayed chat message id (`pinguinoMsgId` / `msgId`) is handled once per pass; no welcome plus random chime on the same message; `!8ball` no longer puts profile facts of an opted-out viewer into the AI prompt. Every other memory path already checks the opt-out.
- R3 28970e5: every bot log line (and the "last problem" shown to mods) goes through `PgScrub`, which blanks API keys, bearer/oauth tokens and key=value secrets, plus the configured key itself. The repo and chat logs hold no real key.
- Tests: Chat 292/292, Helper 230/230, Core pass, Bots routing 93/93, Host lore 0 FAIL, `sync-shared --check` clean.

## Known issues / open
- Canned double-reply check in live chat: no chat lines existed after the 03:58 restart when I looked; re-check from `Data/chat_logs` once chat has run.
- Needs a Host restart (00 owns it) so the stub modules load the new alias list, the audit fixes and the new canned file.
- `!rank` playlist ids (10, 11, 13, 61, 27, 28, 29, 30, 63, 34) cannot be verified offline; the name fallback covers a wrong id.
- The welcome-plus-random-chime fix (R2) is a one-line guard without its own test (the harness would need the random-chime setup).
- `Data/runtime/channel_lore.json` still holds the old texts of grindr / feetfinder / onlyfans (inert while Chatty owns the terms; Host data, left alone).

## Plans
- Re-check canned replies in the live log after the restart; tune the 6 s / 2 s canned gates if chat finds them too tight.
- Optional: a Commands-page row for the Discord replies once the page shows Chatty-owned commands.

## Hard rules kept
No OBS go-live or stream tests, no site push, no deletions of user data, no duplicate bot messages from new code (the duplicate guard stays on every send path).
