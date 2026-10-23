# Session notes: 53 Voice (worker under 50 - Tools)

Last updated: 2026-10-23 06:20. Hand-over from the old 06 session: `Docs\sessions\06-voice.md`. Docs: `Docs\VOICE.md`, `Docs\VOICE_ROUTING.md`.

## Done
- Task 1a: `output.device` matching (engine.py `dedupe_devices`/`pick_device`/`find_device`): case-insensitive substring, WASAPI > DirectSound > MME, `/api/devices` is de-duplicated and stable. WASAPI plays with `auto_convert` (shared mode otherwise rejects 22.05 kHz). Tests: tests/test_devices.py. (Committed inside 7844318 by another session's commit.)
- Task 2: audit rounds 2-3, findings in the shared notes (`53-voice-audit23.md`), 11 fixes, tests/test_audit23.py. Tests now 90.

## Open
- Tasks 3 (speech intervals + Listen check) and 4 (!speak readiness, module.json version).
- Needs a Voice restart by 100 to take effect.
