# Lore privacy check - welcome-back + timeout lines (worker 14, 2026-10-23)

Scope: Host `WelcomeBack` / `PeopleGraph.WelcomeLine` (ec539eb), Chatty's use of it (f74fa86, by reflection, 12's file), the timeout reward lines (`HostTimeoutReward.cs`, `HostTimeoutSelf.cs`) and the lore data they read. Method: code read plus the Host sim tests (`test-host-timeoutgraph.py` has a SECRET marker in every graph excerpt; `test-welcomeback.py`).

## Verdict
No verbatim quote, number, date or "how the bot knows" can reach chat from these paths, and opted-out people are excluded. One real gap was found and fixed (`!forgetme`); one policy question is left for Ivan (the name of an anon person inside a timeout line).

## Opt-outs (`!optmeout` = Privacy "anon", `!forgetme` = Privacy "forget")
| Path | anon | forget | Evidence |
|---|---|---|---|
| Timeout graph lines (`FriendLine`, AI hint `Hint`) | excluded (`Boards.IsAnon`) | **was NOT excluded, fixed in ee0fad9** (`Forgotten()` reads chat_memory.json by key / Login / Aliases, 20 s cache) | `test-host-timeoutgraph.py`: optout1 (anon) and forget1 (forget, keyed by Twitch id with Login) both get the plain line and `closeness none`; the forget case FAILS on the pre-fix code (checked by temporarily removing the check) |
| `WelcomeLine` (Host) | excluded (`Allowed`) | excluded since ee0fad9 (same `Allowed`) | shared gate, covered by the test above; `WelcomeLine` has no sim command, so it is not exercised end to end |
| Chatty welcome-back | `optedOut = NoMem(v)` covers anon AND forget; `prevSeen` is only set when `!NoMem(pv)` | same | `PinguinoChat.cs` around lines 983-1015: a double gate, Chatty and the Host |
| `nightly-phase1.mjs`, `nightly-review.py` | by key, Login and Aliases | same | `test-nightly-optout.py` (fails on the old code, checked) |
| `build.mjs` (graph / cards) | excluded at rebuild | excluded | 0 opt-outs today; between rebuilds the Host ignores them anyway |

## Verbatim quotes and numbers
- Graph `edges[].example` and card `treatsIvan.evidence` hold real chat excerpts. The Host reads only `mutual` (turned into a coarse level) and group membership, never `example`; the SECRET test shows nothing from the graph reaches a `[say]` line. The scrubbed `people_graph.public.json` (a18f2be) is preferred by the Host, so the file it loads contains no excerpts at all.
- Welcome-back lines are fixed templates with `{u}` only; the unit test asserts no digit and no unreplaced placeholder over 640 samples. Extra lines from `Data\lore\welcome_lines.json` must contain `{u}` and be under 200 characters; nothing else is validated, so whoever edits that file must keep it free of private facts (it is git-ignored).
- AI timeout lines get at most one background sentence ("Private background (do not quote or explain): ..."), a coarse relation (duo / buddies / acquainted / crowd) without counts, dates or sources. Model output is not post-filtered for that wording; the sentence tells the model not to explain it.
- Chatty's fixed fallback pool (used when the Host method is missing) contains only the name.
- The Host log line `people-graph closeness <level>` contains no names.

## Left for Ivan / 100 (policy, not changed)
1. A timeout line names the TARGET by Twitch display name even when that person is `anon` (for example `optout1 has been timed out by alice` in the test). Twitch itself shows a timeout publicly, but the product rule says anon = "name + id hidden everywhere". Option: use `Boards.DisplayName(login)` ("Anonymous Penguin") in the timeout and failure lines. It is a small change in `HostTimeoutReward.cs` (the lines that use `tname`); I will do it with a test on request.
2. `welcome_lines.json` extras are unvalidated free text (see above); fine while only Ivan or the lore worker edits it.
3. Between a `!forgetme` and the next graph rebuild the person's node and card stay on disk (the Host ignores them). `graph-apply-runbook.md` says to rebuild after opt-outs.
