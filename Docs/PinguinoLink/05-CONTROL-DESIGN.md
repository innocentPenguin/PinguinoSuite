# 05 — Remote OBS Control and Remote Stream Deck

## Architecture
Client UI / Stream Deck -> signed command -> **hub agent** (scope, tier, idempotency key, dedupe window, rate limit) -> adapters (OBS WebSocket on loopback, Streamer.bot, PinguinoSuite bus `ws://127.0.0.1:8760/ws`) -> confirmed state pushed back (ack = state actually changed).

## Action catalogue (hub-side, versioned JSON)
Scenes, source visibility, overlays, mic mute/volume, replay-buffer save, approved record start/stop, Streamer.bot actions, viewer intros, Suite module start/stop, read-only OBS status. Each action defines tier, argument schema and confirmation text. The current prototype's 5 macros become entries here; stream start/stop become T3.

## Errors
Typed: `obs_unavailable`, `scene_missing`, `denied_scope`, `needs_confirm`, `hub_offline`, `timeout` — each with a plain message and the matching doctor check.

## Stream Deck options
- (a) Bitfocus Companion on hub + Companion Satellite on the Mac: real remote hardware, feedback, OBS/Streamer.bot modules. Fastest proof.
- (b) Elgato Stream Deck + web-request plugin to the agent: simple, no feedback. (Elgato software is not installed here.)
- (c) Custom plugin or dashboard software deck: best long-term fit.
Plan: spike (a); keep the agent API clean so (c) can replace it. Coordinate profiles/catalogue editing with Unit 01 via the Suite bus.

## Duplicate presses and reconnects
Idempotency key per press, 500–1000 ms dedupe, state-setting actions ("set scene X", not "toggle") where possible; client drops commands older than ~3 s instead of replaying after reconnect.
