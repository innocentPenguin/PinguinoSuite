# Feature audit (2026-10-19)
Sim = passes simulated tests. Live = verified in the real Streamer.bot. The new code is not deployed, so nothing new is Live.

| Feature | Code | Tests | Live |
|---|---|---|---|
| Queue/teams/matches/stats (Core) | yes | Sim (core suite passes) | old copy (BVQ Engine) runs; new not deployed |
| Chat conversation / AI providers | yes | Sim, 202 checks | old `chatbot` only |
| Helper deterministic help | yes | Sim, 81 checks | no |
| Router + fallbacks | yes | Sim, 54 checks | no (no bots.json) |
| Overlays players / vertical | fixed today | browser-verified; OBS pending | pending |
| First-time chatter / goodbye | partial (old First actions) | partial | legacy only |
| Sub/gift alerts | legacy actions | none | legacy |
| Non-overlapping intro scheduler | **missing** | – | – |
| Tournament wheel / `!me` | **missing** | – | – |
| Router per-message correlation + routing.log | yes | Sim, 54 checks | no (live RunAction semantics unverified) |
| PinguinoHost (Streamer.bot-free runner) | yes | Sim smoke test PASS (Tools/test-host.ps1) | live chat read verified; setup UI + Suite module verified (test-host-api PASS); helix send / EventSub / OBS untried |
| Paste package (Deploy\) | yes | sync --check green | not pasted yet |
| AI cost limits beyond MaxCallsPerHour | missing | – | – |

Test run 2026-10-19: core, chat (202), helper (81), bots (40) and history hook (10) all PASS; shared-code sync up to date.

PinguinoHost addendum: /api/run (Stream Deck) and mock-Twitch test (Tools/test-host-twitch.ps1) added; live Twitch sign-in, EventSub and real OBS remain unverified.

Separate chatters (3617350): each bot can sign in as its own Twitch account from the Host page (bots_secrets.json[role], Sender "helix"). Built and deployed by 00; live sign-in of pinguinob0t is pending Ivan's click-through, chat and helper accounts do not exist yet.
