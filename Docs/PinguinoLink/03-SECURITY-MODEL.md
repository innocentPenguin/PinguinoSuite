# 03 — Security Model

## Network layer
Tailnet with device approval, key expiry and MFA on the identity provider; tags `tag:hub` / `tag:client`; ACL: clients -> hub only on PinguinoLink ports (agent 7777, SRT range, Syncthing 22000, Companion satellite 16622); hub -> clients none; Tailscale SSH off; shields-up on clients.

## OBS exposure
OBS WebSocket reachable only from the hub agent on loopback; Windows Firewall blocks 4455 from everything else. Clients only talk to the PinguinoLink agent. Never expose to the public internet.

## Application layer (being on the tailnet is not authorization)
- Per-device Ed25519 key created at enrollment; private key in Credential Manager/DPAPI (Windows) or Keychain (macOS).
- Requests signed with timestamp + nonce (replay protection); short-lived sessions (~12 h); revocation list on the hub plus tailnet removal.
- Enrollment: hub shows a single-use 5-minute pairing code/QR; user approves on the hub and assigns scopes.

## Risk tiers
| Tier | Examples | Rule |
|---|---|---|
| T0 | status, scene list | read-only |
| T1 | scene switch, source toggle, mic mute, overlays | allowed by scope |
| T2 | replay save, record, Streamer.bot actions | confirm |
| T3 | start/stop stream, delete, settings | confirm on initiating device + optional hub notice, cooldown |
| T4 | shell, firewall/OBS-auth/key management | never remote; hub-local only |

No remote shell, no free-form commands: only named actions from a hub-defined allow-list.

## Local API hardening (fixes inventory finding 1)
Bind loopback + tailnet only; require token on loopback too; verify Host/Origin; accept JSON only; constant-time token compare.

## Audit and files
- Append-only hash-chained JSONL audit log on the hub (device, action, tier, result, path type).
- File access: per-device allow-listed folders, no traversal/symlink escape, size/type limits, quarantine inbox.
- Unknown networks: client opens no listening ports; extra prompt for T2+ when relayed from a never-seen network.

## Secrets
OBS password stays on the hub; tokens/keys never in the suite tree, logs, diagnostics bundles or AI reports. Recommend rotating the OBS WebSocket password before Milestone 1 (it appeared in session output).
