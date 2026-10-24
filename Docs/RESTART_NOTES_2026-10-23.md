# What the next Host restart brings (2026-10-23)

For 100 and Ivan. Scope: Host / Chatty / Helper / Core (bot core) / overlays only. Base: commits after the Host build of 06:10 (`git log --since="2026-10-23 06:10" -- PinguinoHost PinguinoB0t PinguinoChat HelperPinguino Shared`). If the live Host was built later than 06:10, drop the items that are already in it.
Rules while verifying: **never go live in OBS, no real chat messages.** Static overlay pages (`?part=`, wheel look, CSS guards) are served from disk and already live.

**Right after the restart run:** `python Tools\post-restart-check.py` (read-only, GET only). Expected on the live Host after sign-in and with OBS up: all PASS. Expected WARN/FAIL on a sim Host or before sign-in: `prestream: chat/eventsub/streamer/bot-core/bot-chat/bot-helper/obs/ai/overlays` (no Twitch/OBS/keys in sim; `--lenient` turns these into WARN), and `scene widgets ... unavailable` (a sim Host's overlay folder is a temp dir). Any other FAIL is real.

## 1. Alerts / Multi bridge
| What changes | Verify live (1 line) | Switch afterwards |
|---|---|---|
| Multi alert emits ON by default: hype start/level/end, tip (whole amount), gamble win, shop, guess, give, loan, through one door (55b9a25). Id-less tips get a unique id, hype state locked (eb479f1). | `GET http://127.0.0.1:8770/api/alerts-settings` shows `EmitHypeTip:true`; Multi dashboard shows the Host status line. Do not use `/api/alerts/fire` or `/test` live (they play on stream). | `Data\alert_bridge.json` overrides defaults: if it exists with `"EmitHypeTip": false` (75d1721 era) delete that key or set true. |

## 2. Economy / games
| What changes | Verify | Switch |
|---|---|---|
| Slots pay per symbol: triple cherry 2, fish 3, star 4, soccer 6, penguin 11, pair 1.5 (92.8% back) (7314ea8, `Docs/SLOTS_TABLE.md`). | `python Tools\slots-ev.py` prints the RTP; `Tools\test-host-gamble.py` passes. | Table is `slotsSymbolPayouts` in the gamble config; edit there. |
| Per-stream ledger shows loans, repayments, depreciation as rows (77d0269). | Host page > economy ledger after a loan in sim. | none |
| Site economy `intro_*` answers carry `data.intro.status` (5565abd). | `GET /api/intro` answers 200 (checked by the post-restart script). | none |
| Back-pay 40% and firsts rebuild: dry runs exist (`Docs/nightly/reports/`). | read the report | **Apply is a coordinator action:** back-pay `POST /api/economy/backpay {apply:true}`; firsts `POST /api/firsts/rebuild {"apply":true}` (dry run: 191 people would change, see `firsts-dryrun.md`). Only after Ivan reviews. |

## 3. Chat commands, Chatty, Helper, shared send path
| What changes | Verify | Switch |
|---|---|---|
| Reply rejected by Twitch with 400 (stale/deleted parent) is dropped, never resent without the reply or via another account (284e5ba, all bot copies). | `Tests\bots` harness / `Tools\test-host-*` pass; no live check needed. | none |
| Chatty pins the Twitch msgId reply target for every send (92d6fb0); Guess-the-Chatter lines via PgGame kind=guess (55f1e53). | `Tools	est-host-gamble.py` (guess lines). | none |
| CmdFix: `!!points`, long-name typos (`!leaderbrds`), Host-owned commands `!bank`/gamble/rank are known so `!bank` no longer turns into `!rank` (d5fbfe4, a09e37c). | sim stdin `user: !bank` answers the bank line. | none |
| Every viewer command answers with at most one chat line (test guard 815b00f/d5fbfe4). | `python Tools\test-host-oneline.py <dll>` | none |
| RxHeat: "bot/bots" alone is not heat (693043e). | test only | none |
| Timeout lines: private people graph (closeness only, opt-outs and bots excluded) (a82bf19); friendly varied no-match / could-not-time-out lines (bf97722); lore clip lines follow the shared clip rule (689a02a). | `Tools\test-host-timeoutgraph.py` | none |
| Shoutout: no Twitch card after a Multi timeout, one cooldown line per window, no-clip shoutout keeps the cooldown (d0424d2). | sim `#ivan: !so name` twice | none |
| Clip routes: `reserve=1` atomic pick+mark with confirm/release, 60 s Helix cache, refuses requests carrying an Origin header (58d4531). | **do not hit `/api/clips-pick`** (it reserves); `Tools\test-host-clips.py` in sim. | none |
| Live resubs refresh the sub master and profile (months, streak, tier), idempotent per event id (84222a6). | sim `PINGUINO_SIM_SUBS=1` + `eventsub channel.subscription.message`; `Tools\test-host-resub.py` | none |
| No AI-key carry-over into `--sim` or non-runtime data dirs (815b00f). | sim shows `ai` prestream item as WARN | none |
| Helper pack v15 (`Data\helper\knowledge.json`, mod pack `knowledge_mod.json`). | Helper prestream item `faq` = pass; ask Helper a known question in sim. | Pack is read at Host start; no extra switch. |

## 4. Site / ForwardToSite / Speak
| What changes | Verify | Switch |
|---|---|---|
| Activity push to the site is ON by default (`ForwardToSite`, ef14dd7), still off without BOT_API_KEY. | Host log shows activity forwards only if the key is set. | **`Data\runtime\latest_settings.json` line 22 has `"ForwardToSite": false` pinned: change to true (or delete the line) if Ivan wants the push.** |
| `!speak` Host side (7d423b6): two seeded actions, "Speak: !speak (mods)" and "Speak: channel point !speak", both **disabled**; Speak module's own `tts.enabled` is also off. | Host page > Automations > group Speak shows the two disabled actions. | To use: create a 100-point reward titled `Speak` on Twitch, enable the action, switch `tts.enabled` in the Speak module. Until all are on nothing is spoken. |

## 5. Overlays and scenes (mine)
| What changes | Verify | Switch |
|---|---|---|
| `GET /api/scene-health` plus a pre-stream item `scenes` (edb1e54). | `curl http://127.0.0.1:8770/api/scene-health` returns `ok:true`. | none |
| `players_vertical` is a 1080x250 strip registered at the bottom of the vertical stage (e790497). | `scene-editor.html?profile=v` shows it at y 1670. | **Layout reset:** a vertical layout saved BEFORE the fix keeps the old 1080x1920 box: in the editor set x 0, y 1670, w 1080, h 250, scale 1 and Save, or Delete the layout for the fresh default. |
| Sim/test Hosts never write the real overlays dir (d22835c). | `Tools\test-host-overlaydir.py` | none |
| Customs overlay fades out when the Host is unreachable (d4aab26); CSS guards for names (9c4afd9); wheel look, `?part=` modes, safe-area profiles (static, already live). | open `customs.html`, `players.html?demo`, `wheel.html` in a plain browser tab | none |
| Live-check + operator pages. | `Docs\OVERLAYS_LIVE_CHECKLIST.md`, `Docs\OVERLAYS_OPERATOR.md` | none |

## 5b. Lore / people graph (14)
| What changes | Verify | Switch |
|---|---|---|
| Welcome-back line is a pure function with tests (ec539eb, IDEAS #36), 10 new channel-voice lines. | `python Tools\test-welcomeback.py` prints PASS welcomeback. | none |
| The Host and bots read the scrubbed people graph (a18f2be): no verbatim excerpts in `people_graph.public.json` / `person_cards_public`; `scrub-graph.mjs` runs inside `build.mjs`. | `node Tools\lore-mining\verify-apply.mjs`: every line OK. | none |
| Timeout and welcome graph lines skip people with `!forgetme` / anon (ee0fad9). | `python Tools\test-host-timeoutgraph.py` prints PASS. | none |
| Spam/viewbot accounts never get a welcome-back line (login pattern guard in `WelcomeBack.IsSpamLogin`, `PeopleGraph.WelcomeLine`) and never enter lore mining (`Tools\lore-mining\spam.mjs`) (7e36eb3). Needs the Host build for the welcome guard; the mining filter is live in the tools already. | `python Tools\test-welcomeback.py` and `node Tools\lore-mining\test-spam.mjs` print PASS. | none |
| Live lore was rebuilt 2026-10-23 22:32 (196 cards, 217 edges, 6 groups, 5 stale alias cards gone, spam filtered); no restart needed for the graph (reloads on file change). Backups in `Data\lore-work\backup-*`. | `verify-apply.mjs` all OK. | Keep one backup, delete the rest after a quiet day. |
| NOT applied, waiting for Ivan: ace/ziu/peng + `ssl` entries, `squishy`, fnaf/fortnite words (`Docs
ightlyeports\lore-ivan-decisions.md`, `phase1-proposals-2026-10-2[23].md`). | n/a | Add to `LORE` in `notes.mjs`, backup, `build.mjs`, `verify-apply.mjs`. |

## 6. Known gaps (not in this restart)
- Shared 400 retry dropped on purpose: a reply with a stale parent is lost, not re-sent plain (284e5ba). Viewers can miss one line.
- Intros push items are still coming (the pull `/api/intro` works; push to Multi is pending).
- Welcome-back lines are pending.
- `!layout` chat command held until Ivan has seen the scene editor.
- Items that need OBS live (real stage test, audio of framed alerts) are not done: no one goes live to test.
