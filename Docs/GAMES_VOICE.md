# ChattyPinguino as the voice of the games: plan

Status: plan + implementation by 12 (Chatty). Economy stays in the Host (bets, balances, cooldowns, payouts); Chatty only speaks. `!shop` purchase confirmations (kind `shop`) are NOT touched (Ivan decides first).

## What already works (verified in code)
One door: `Gamble.GameOut` (HostGamble.cs) -> a `PgGame` event goes straight to the PinguinoChat action (Program.DispatchEvent, not through the router) -> `Chatty.GameEvent` -> `GameLine` (persona text) -> `PgSay("chat")`, the Chatty account. Kinds: gamble, slots, duel, give, guess, shop. Guess the Chatter's start, invalid/refusal ("the game is cooling down", "you played a moment ago", stake range, "round already running"), retry/win/lose/expired already go through it. Fallback today: when `chat_settings.json` has Enabled / ChatReplies / GameVoice off, the Host says its own plain line (`ChattyCanPost`). Never both; `gameId` dedupes.

## Gaps found
1. **Chatty off in the router is ignored.** `ChattyCanPost` reads only chat_settings.json; `bots.json` `chat.Enabled=false` (dashboard, `!pg chat off`, the Spotify hand-off button) is not looked at, so a switched-off Chatty still speaks the games, and nobody answers as B0t.
2. **A Chatty failure loses the line.** If the PinguinoChat action throws, `DispatchEvent` only logs; the Host's plain fallback runs only when the dispatch itself throws.
3. **Direct B0t lines left in the guess flow** (HostSiteBridge.HandleShop): usage ("I show an old chat line..."), "not open yet", "no such item", and the Spend error. They go through `say` = B0t's voice.
4. **Refusals read flat.** The refusal reasons (cooldown, round running, stake range, not enough points) are sent as the plain Host sentence, even in Chatty's voice.
5. **Reply threading.** Result lines to the person who typed the command are plain lines with `@name`; the Host's own fallback line is threaded to the command. Both should thread.

## Plan
| # | Change | Who speaks | Fallback |
|---|---|---|---|
| 1 | `ChattyCanPost` also requires `bots.json` chat `Enabled` (read with the same 4 s cache) | Chatty | B0t plain line (Host `say`), exactly one |
| 2 | Chatty marks the event done in a Host-visible global (`pinguino.game.done.<gameId>`) whenever it handled it (spoke, or skipped on purpose: duplicate id, empty line); the Host checks after the dispatch returns and says the plain line if the mark is missing (exception / crash) | Chatty, else B0t | one line either way, never both (the mark is set before anything is said) |
| 3 | The guess usage / not-open / no-such-item / Spend-error lines go through `GameOut` (kind guess, outcome invalid) | Chatty | B0t plain via `say` |
| 4 | `GameLine` gives refusals a Chatty phrasing from a small pool (cooldown, round running, played a moment ago, stake range, not enough); optout / heated chat / `plain` keep the exact Host sentence | Chatty | n/a (same text, plain) |
| 5 | `GameOut` passes the command's message id (`msgId`, from `ReplyCtx`, only when it is a live reply context) for gamble / slots / give / guess lines to the invoker; Chatty pins with `PgReplyTo(id, login)`; duel challenge/result, expiry and event lines stay plain | Chatty | the Host fallback already threads |
| 6 | Untouched: `!shop` list and purchase confirmations (kind shop), points mechanics, Multi alert emit (`AlertBridge.OnGame`), the 30 s duplicate-line guard, one line per action |

## Tests
- Chat harness: refusal phrasing pool + plain mode keeps the exact sentence; threaded id pinned on gamble/guess lines, none on duel/expired; done-mark set on spoke / duplicate / empty; no done-mark path when GameVoice is off.
- Host: `Tools/test-host-gamble.py` (+ guess) still green; new checks for `ChattyCanPost` with router `Enabled=false` -> plain line only, and for the guess usage line going through `GameOut`.
