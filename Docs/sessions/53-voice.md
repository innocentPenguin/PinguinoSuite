# Session notes: 53 Voice (worker under 50 - Tools)

Last updated: 2026-10-23 06:20. Hand-over from the old 06 session: `Docs\sessions\06-voice.md`. Docs: `Docs\VOICE.md`, `Docs\VOICE_ROUTING.md`.

## Done
- Task 1a: `output.device` matching (engine.py `dedupe_devices`/`pick_device`/`find_device`): case-insensitive substring, WASAPI > DirectSound > MME, `/api/devices` is de-duplicated and stable. WASAPI plays with `auto_convert` (shared mode otherwise rejects 22.05 kHz). Tests: tests/test_devices.py. (Committed inside 7844318 by another session's commit.)
- Task 2: audit rounds 2-3, findings in the shared notes (`53-voice-audit23.md`), 11 fixes, tests/test_audit23.py. Tests now 90.

## Open
- Task 3: tests/test_intervals.py (4). Listen only uses speaking.json to ignore voice commands (listen/voice.py bot_speaking), it does not skip transcribing; request for 20 sent via 50.
- Item 4 of 06 section 4 (mic-lost alert): event `mic_alert` (OFF by default), server.mic_loop polls Listen /api/status every 10 s, speaks one fixed line per distinct alert, never Listen's text. tests/test_micalert.py. Tests 101.
- Task 4: role bug fixed (Host sends numeric role), redeem path, module.json version 0.9.0, Docs/VOICE.md "!speak: what the Host needs". Tests 97.
- Needs a Voice restart by 100 to take effect.
