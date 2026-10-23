# Session notes: 021 Helper (fork of 02 PinguinoBots)

Last updated 2026-10-23. Owner of `HelperPinguino/PinguinoHelper.cs` and its tests. Reports to 02 (`local_58156ab8-4c1b-4654-a4a3-48687e71d813`); 00 (`local_9b055c40-005d-4fad-892a-7133e1382dd1`) is the coordinator and the only session that restarts the Host. Chatty = 022 (`local_7135181f-2c8d-4cec-8cda-1c0d6edae3ff`). I never push and never restart anything; all commits are local.

## 1. What I built and why

| What | Commits | Why (Ivan's words, relayed by 00/02) |
|---|---|---|
| `!helper` / `!ask` / `!pinguino`: short friendly answers from a nightly knowledge pack (public tier, plus mod tier for mods), AI only phrases, no-AI read-out, unanswered questions logged to `Docs/nightly` | 909ad33, 7947459, 7f9d374, 9893551 | Chat kept asking the same questions; he wanted a thankful one-line helper that cannot invent facts or leak secrets. |
| Console answer: Bedrock Connect link only | 03b719b | "Consoles join Minecraft through Bedrock Connect." I checked the official page: it recommends DNS; Ivan thinks "no DNS". The reply only links the page so nothing wrong is claimed. |
| Lobby: NAME only | e134683, c6430e4, 6e5572f | Final decision: "bots NEVER grab, store or say lobby passwords... lobby NAME only... strip anything labelled password/pass/pw." `!lobbypass` is refused; a leftover `LobbyPassword` key is scrubbed from `helper_settings.json`. |
| Mod and public knowledge, leave/points/recycler/customs timeout | 2d6345d, 1b39b71, 3fead6a | From chat-log mining and Ivan's answers. |
| `!notme` leaves the tournament wheel (not `!leave`) | b453d84 | 02: "!notme for leaving the wheel". |
| Stream schedule | b888b8f | Ivan: "he streams at 5pm every day, Rocket League first for a couple of hours, then other games" (Minecraft Mon, Fortnite Fri, Scary Sat). |
| Ranking synonyms for the pack search | swept into d213195 | Better matches for "ways to enter", "remove me", etc. |
| Name recognition | bd7b13a (+ Chatty's 223bd42, 5c89b3f for the Router) | Ivan: "Ivan is called penguin, peng, peg plus typos; bots are called pinguino, pinguinos, penguins." The Helper drops bot names from `!helper` questions and treats penguin/peng/peg as Ivan. |
| Audit 1-3 | 74fd13a (cooldown list pruned), 54a6ad0 (opted-out viewers get no organic help), 54ef677 (secrets scrubbed from review and unanswered logs) | Held end-of-night audit: commands/cooldowns, no doubled replies/opt-outs, no secrets in logs. |
| Phase 3 report | bc6138c (`Docs/nightly/reports/02-helper-engine.md`) | Nightly run. |
| English + Mexican Spanish, typo commands, `!helperpack`, `!helper` follow-ups, drafts tool, yes/no fix | 91be8c0 | Ivan: "help replies in English + Mexican Spanish ONLY... info commands just execute when the typo is a clear near-miss; !join/!leave-type commands ask 'did you mean !join?' and wait for a yes." |

Also changed: `Docs/LOBBY_CONTRACT.md` (name-only contract with the site's `match-private` store), `Docs/HELPER_PUBLIC.md`, `Docs/HELPER_MOD.md` (pack source text), `Tools/build-helper-pack.py`, `Tools/test-helper-pack.py` (fails if a lobby password text appears in a pack), `Tools/helper-drafts.py`, `PinguinoB0t/commands.json` (+ `COMMANDS.md`, new `!helperpack` row).

## 2. Decisions, reasons, failures

- **Spanish only explains, never acts.** Action asks ("quiero unirme") only describe `!register`/`!join`; no confirm flow in Spanish, so a mistranslation can never add someone to a queue.
- **Typos: who runs what.** The Helper can run Core viewer info commands through `CallCore` (allow-list `TypoExec`: !pos !queue !mmr !stats !myrank !topwins !strikes, always as a normal viewer, never mod). It cannot run Host- or Chatty-owned commands, so it only suggests them. Join/leave ask and wait for yes/sí (existing `_pending` flow). Needs at least 40 known commands or the feature turns itself off (avoids correcting real commands).
- **Synonyms are title-only.** Body synonyms boosted unrelated entries ("join minecraft on xbox" went to customs). Phrase-pair bonus is title+keywords only (body pairs broke "title match beats body-only match").
- **Router changes stay out of my hands.** Aliases are in the shared block (`Shared/PinguinoRouter.cs`); Chatty (022) owns that edit and its tests.
- **Failed/denied:** a permission classifier blocked password-related weakening edits ("Security Weaken"); I stopped and asked. Ivan then decided "no reversal: bots never touch passwords".
- **Bug found while testing:** the yes/no regexes matched any word ending in y or n while a confirmation was open ("when" = no). Fixed in 91be8c0.

## 3. Gotchas, how to test, restart

- **Tests:** `powershell -NoProfile -ExecutionPolicy Bypass -File Tests\helper\run-helper-tests.ps1` (262 checks); `python -I Tools/test-helper-pack.py`; `node Shared/sync-shared.mjs --check` (all four files must say "up to date"). Pack: `python -I Tools/build-helper-pack.py` (currently v13: 134 public, 84 mod). The Helper compiles as C# 7.3.
- **Never put `\b` in a Python/bash heredoc that writes C# regexes:** it becomes a backspace (0x08). Write backslashes via a file written with the Write tool, then scan for 0x08. Keep non-ASCII (¿ ñ á...) as `\uXXXX` in the source.
- **Hand-staging:** git blobs are LF, working tree CRLF. Other sessions sometimes sweep my uncommitted edits into their commits (d213195 contained mine). Always `git diff HEAD` before assuming something is uncommitted.
- **Shared block** (lines ~54-360 of PinguinoHelper.cs) is generated by `sync-shared`; never edit it in the .cs files.
- **INDEX block** at the top of PinguinoHelper.cs is regenerated by a scratch script (`idx.py`, lost with the scratchpad; `Tools/gen-index.py` is the official one named in the header).
- **Restart:** only 00 restarts the Host. Pack files reload on their own (`!helperpack reload` forces it).
- **Open bugs / waiting on others:** 02 must push the lobby NAME to `/api/bot/match-private` at match start (the site store exists, commit bec0647); `!pm` was name-only in the current source but I never ran it live. Typos of Host-owned info commands are only suggested.
- **Not verified live:** `!helperpack`, typo handling, Spanish answers. Offline tests pass. If typos do nothing live, check that the Helper finds a command list of 40+ entries (`commands.json` under the Suite folder).

## 4. Plans, in priority order

1. Have 02 re-dispatch typos of Host-owned info commands (!points, !rank...) in the Host router so they run.
2. Live check of Spanish, `!helperpack`, typos from a test account.
3. A mod pass over `Docs/HELPER_DRAFTS.md` (run `python -I Tools/helper-drafts.py` after a few streams) and move good answers into the pack docs.
4. Spanish pack entries so the no-AI read-out is Spanish (needs Ivan's OK on the translated public text).
5. More intents for the AI picker (points, strikes, opt-out), costing more AI calls.
6. Follow-up context beyond `!helper` (queue/lobby answers).

## 5. Where my history is

- Session: "021 Helper", id `6f5d97c2-3914-477d-b04a-e7e5bec9c3af`.
- Transcript: `C:\Users\ivanm\.claude\projects\D--\6f5d97c2-3914-477d-b04a-e7e5bec9c3af.jsonl`. Grep for: `NormalizeAsk`, `RespondEs`, `TypoCommand`, `LobbyPassword`, `Bedrock Connect`, `!notme`, `audit`.
- Memory notes: `C:\Users\ivanm\.claude\projects\D--\memory\MEMORY.md`.

## 6. Things Ivan may be forgetting

- **Lobby password policy is "never".** If a customs lobby really needs a password, there is currently no bot path for it; players must be told by a person.
- **Bedrock Connect and DNS:** Ivan believes "no DNS"; the official page recommends DNS (only DNS-free option: Add Friend, with the bots currently off). Worth a decision before the console answer is promoted.
- **`!pm` and the Host push of the lobby name** were 02's open items; confirm both are live and that no stored password still exists in any data file.
- **Spanish and typo features were never exercised live** and the Host needs a restart after any Helper commit.
- **Host-owned typos only suggest.** If he expects "!poinst" to just work, that needs 02's router.
- **Nothing is pushed.** All my commits are local; the site/Host batches decide when they go out.
- **AI budget:** `MaxAiCallsPerHour` defaults to 40 for the Helper; a busy night of `!helper` can hit it, then answers fall back to the English pack read-out.
- **Review log** `Data/helper/review.jsonl` is git-ignored but holds chat text; old lines were written before secret scrubbing (no labelled password values found).
