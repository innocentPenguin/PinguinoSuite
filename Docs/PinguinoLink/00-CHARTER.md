# PinguinoLink (Unit 04) — Charter

Status: PLANNING. Created 2026-10-19.

## Mission
A secure device ecosystem linking the user's machines (MacBook <-> Windows streaming PC running OBS) from any network: device networking, Mac-to-OBS streaming, remote OBS control, remote Stream Deck, file transfer, device dashboard, security, diagnostics, cross-platform support.

## Rules
- Planning only until real-device measurements exist. The prototype in `Suite\modules\link` is NOT rewritten without agreement (exception: the /goal integration edits, see 10).
- All work lives under `D:\PinguinoSuite`. Related outside material is moved in only after the user approves (see 08 and the move table below).
- Every Claude task directive for this unit begins with `/plan`.
- No custom VPN or crypto. No default remote shell. Least privilege. Risky changes need explicit approval.
- OBS WebSocket is never exposed to the public internet.
- The app must be fully useful with AI off. AI never runs commands on its own.
- No promise of remote power-on that the hardware/network cannot deliver.

## Session protocol
- One permanent planning session (this one) owns the docs and the roadmap.
- Each task session is logged in `SESSIONS.md` and archived after its result is documented here.

## Document map
01 Prototype inventory · 02 Network · 03 Security · 04 Streaming · 05 Control · 06 Files · 07 Dashboard/Diagnostics · 08 Roadmap/Costs/Risks · 09 Milestone 1 test plan · 10 Suite integration

## Outside-the-suite items (not moved yet — awaiting user approval)
| Item | Proposal |
|---|---|
| `D:\PinguinoBackup\2026-10-19-pre-reorg\PinguinoBot\GPT\PinguinoLink` | Identical to the module; COPIED 2026-10-19 to `Archive\PinguinoLink-prototype-v0.1` (verified identical; original backup left in place) |
| `C:\Users\ivanm\.pinguinolink\config.json` | Stay (holds secrets) |
| `D:\Recordings` | Stay (OBS path); user decides |
| OBS config, Tailscale install | External dependencies |
| `D:\PinguinoBot` | Existing compat-link process, no action |
