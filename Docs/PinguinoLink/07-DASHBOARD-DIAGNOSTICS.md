# 07 — Dashboard, Wake-on-LAN, Diagnostics, Optional AI

## Dashboard (Suite page fed by the hub agent)
Devices online/offline; path (direct/relay + region), RTT, loss, bandwidth; active stream and SRT stats; transfer queue; service health (OBS, Streamer.bot, agent); enroll/revoke; recent audit events; diagnostics button.

## Wake-on-LAN
Hub: wired Realtek GbE on an MSI board; one NIC property shows magic-packet wake Enabled (BIOS and Windows Fast Startup unverified). WoL only works on the local LAN, so remote power-on needs an always-on home device (Pi, router, or other tailnet node) to send the packet. An away MacBook cannot be woken. Documented as "possible with a helper", not promised.

## Diagnostics (rule-based first)
Detect: Tailscale stopped/logged out, peer offline, relayed path, high RTT/loss, agent down, OBS WebSocket unreachable/auth failure, scene missing, stream feed stalled, disk/file transfer stuck. Each maps to a plain-English cause and a fix list. One-click repairs only from a whitelist of reversible actions (restart agent/Tailscale, `tailscale up`, re-apply firewall rule, reconnect OBS, restart sender).

## Optional AI
Allow-list-redacted report (no IPs, hostnames, tokens) may be sent to Claude for interpretation. Claude can only return ids from the fix whitelist; every fix needs a user click. The app is fully usable with AI off. The prototype's doctor already follows this pattern; keep it and fix the redaction (inventory finding 5).
