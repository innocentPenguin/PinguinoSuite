# 11 — Device mesh: registry, master lease, shortcut relay (DRAFT for approval)

Status: PLAN, 2026-10-19. Requested by 00 (Ivan's ask). Nothing here is implemented yet. Role stays `client` until Ivan approves a hub change; any role change is behind a visible confirmation.

## Goal
Several PCs/Macs run the Suite. One device at a time is the **master** (normally the streaming PC); the rest are **auxiliary**. Link carries who is who, who may act, and relays shortcuts and actions between devices. No custom VPN or crypto.

## Transport: Tailscale only, LAN included
- Link already binds `127.0.0.1` plus the Tailscale address (never `0.0.0.0`). Devices on the same LAN reach each other over Tailscale's **direct** path, so LAN traffic is still WireGuard-encrypted and no plain-HTTP LAN listener is needed.
- Consequence: pairing needs Tailscale up on both devices. Without it a device runs standalone (own master of itself). A plain-LAN fallback would be unencrypted HTTP, so it is NOT proposed unless Ivan asks (Decision 2).
- Reconnect: heartbeat every 2 s; peer marked offline after 3 missed beats; exponential backoff (1 s → 15 s) while re-dialing; every state change is logged to the Console and shown per peer in `/api/prestream`.

## 1. Device registry
Record per device: `id` (random UUID, created once), `name`, `os`, `class` (`streaming-pc` | `gaming-pc` | `mac`), `role` (`master` | `aux`), `online`, `streaming_now` (OBS output active), `last_seen`, `tailnet_ip`, `epoch_seen`.
Stored in `<DATA_DIR>/link/mesh.json` (no secrets besides per-peer tokens, file readable by the user only). Each device keeps its own copy; peers exchange records on heartbeat (last-writer by `last_seen`).

### Pairing (by code)
1. On device A: "Add device" shows a 6-digit code, valid 5 minutes, single use, 3 wrong tries then it expires.
2. On device B: enter A's tailnet name and the code. B sends `{id,name,os,class}` + code over the tailnet.
3. A shows "Pair with <name> (<os>)?" and Ivan must click Allow on A. Then both store a random 256-bit per-peer token.
4. Revoke = delete the peer on either side; the token stops working at once. Peers must also be tagged/approved in Tailscale itself.

## 2. Master lease
Rules requested: priority streaming PC > gaming PC > Mac, **unless a device is actively streaming (then it wins)**; manual "Take control here"; dead master replaced after timeout; never two masters.

Design:
- **Lease** = `{holder, epoch, expires}`. The holder renews it with every heartbeat (TTL 10 s). `epoch` is a counter that increases on every change of holder.
- **Election** among *online, paired* devices, deterministic so all agree without a server: streaming-now device first; else highest `class` priority; ties by `id`. A device claims the lease only if the current lease is expired/released or the claimant outranks the holder AND the holder is not streaming.
- **Manual take-over**: "Take control here" asks a visible confirmation ("X is streaming now" is an extra warning). The old master is told to release; epoch increments.
- **Dead master**: no renewal for 10 s → the best-ranked online device claims with epoch+1.
- **Fencing**: every cross-device action carries the sender's `epoch`; receivers ignore actions from an older epoch. 02's Host must check "am I lease holder" before master-only work (chat bot replies, EventSub, overlays) and stop within one heartbeat of losing it.
- **A device with no reachable peers** is master of itself (single-PC use must keep working). This is the honest limit: during a real network partition two isolated devices can each think they are master; fencing stops them from affecting the *same* shared actions once they reconnect (lower epoch loses), but "never two masters" holds only among devices that can reach each other.
- API for others (to agree with 01 and 02): `GET /api/mesh/lease` → `{holder, epoch, i_am_master, expires}`; `GET /api/mesh/devices`; `POST /api/mesh/takeover` (confirmation required, UI-initiated only).

## 3. Shortcut relay
Pieces: **capture** on the source device, **route** to a target device, **execute** on the target.
- **Capture**: global hotkeys via Windows `RegisterHotKey` in a small helper process (registers only the exact combos the user defined; no keylogging, no key hook). macOS later via the system hotkey API; needs no Accessibility permission for hotkeys alone.
- **Rule** (defined on a Suite page): `shortcut → target device → action`. Action types, in order of preference:
  1. OBS action (scene/source) via the existing Link macros on the target hub.
  2. Host action from 02's *Actions & Events* (needs an invoke endpoint from 02).
  3. Media action (Spotify skip) via OS media keys.
  4. **Key injection** (last resort, see below).
- **Safety**: per-device on/off switch; per-rule enabled flag; relayed actions are named and allow-listed on the target, never free text or shell commands; rate limit (default 5/s per rule); stale commands (> 3 s old) dropped, not replayed after a reconnect.
- **Loop prevention**: each relayed message carries `origin_id`, `msg_id`, `hop` (max 1) and a TTL; a device never re-relays a message that has an origin or `hop >= 1`, dedupes on `msg_id` for 30 s, and injected input is ignored by its own capture (rules may not target a combo they also capture).
- **Key-stuck safety**: the target tracks every key it holds down; on disconnect, lease loss, 3 s without a refresh, or app exit it releases all of them. Relays are press+release pairs by default (no "hold" unless the rule says so, with a max hold of 2 s).

### Key injection (needs Ivan's explicit approval — Decision 3)
OS-level injection (Windows `SendInput`) lets one device press keys on another, which is a remote-control surface. Proposed guard rails if approved: off by default and enabled **on the target device itself** with a visible indicator; only combos on a per-device allow-list (no arbitrary text typing); only from paired peers holding the current-or-higher epoch; never into password fields is not enforceable, so the allow-list stays small; full audit in the Console (`source: "inject"`). macOS needs the Accessibility permission, granted by the user in System Settings; the app cannot grant it.

## 4. File/clipboard transfer
Keep the existing Taildrop CLI path. Add: mesh-aware "send to device <name>" using the registry, clear failure messages when a peer is offline, and per-peer status in `/api/prestream` (`peer:<name>` = pass/warn/fail with direct/relayed detail). Clipboard sync stays out of scope until files are solid (clipboard can carry secrets; needs its own opt-in).

## 5. Phasing
| Phase | Content | Testable here without a Mac |
|---|---|---|
| P1 | Registry, pairing, heartbeat, lease/fencing, `/api/mesh/*`, Console logs, prestream per peer, selfcheck | Yes: two Link instances on one PC (different ports and data dirs) |
| P2 | Hotkey capture helper + rule page + relay of OBS/Host/media actions, loop/rate protections | Yes (two instances); real hotkeys need a manual check |
| P3 | Key injection behind per-device permission | Windows yes; macOS needs the MacBook |
| P4 | Mesh-aware file send, reconnect polish | Partly |

Contracts to agree before P1: **01** (core) — lease/devices endpoints, `Docs\MODULE_CONTRACT.md` section, restart policy; **02** (Host) — `i_am_master` check and a Host action-invoke endpoint for rules.

## Decisions for Ivan
1. Approve P1 (registry, pairing, lease) as the first implementation step?
2. Tailscale-only transport for LAN too (recommended), or also an unencrypted LAN fallback (not recommended)?
3. Is key injection wanted at all? If yes, with the guard rails above?
4. Confirm priority: streaming PC > gaming PC > Mac, streaming device always wins, manual take-over always asks to confirm?
