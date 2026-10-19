# 09 — Milestone 1: Real-Device Test Plan

Needs the MacBook and the user present. Each install or config change is approved separately.

## Prep (hub)
Register `link` in the Suite only after approval; allowed new items: Tailscale login, MediaMTX, ffmpeg; create OBS scene `Remote Cam`; consider rotating the OBS WebSocket password.

## Steps
1. **Join** hub and MacBook to one tailnet; apply tags/ACL; save `tailscale status --json` from both.
2. **Path tests** on home Wi-Fi, phone hotspot, and a campus/other Wi-Fi if available: `tailscale ping` ×20 (direct/relay, RTT), `tailscale netcheck`, 10-min ping for jitter/loss, `iperf3` up/down through tunnel vs a plain baseline; repeat with Speedify off/on; force relay (block UDP) to measure the DERP penalty.
3. **Stability**: 30-min soak per network; count direct<->relay flips; reconnect time after Wi-Fi drop and hotspot toggle.
4. **A/V feed**: Mac -> SRT -> hub -> OBS at Mobile (8 Mbps, 1080p60), Quality, Rough; 15 min each; log RTT, loss, retransmits, bitrate, dropped frames, CPU/GPU both ends; clap test for lip-sync; 10 s network cut to confirm automatic recovery.
5. **Authenticated OBS command**: restrict 4455 by firewall; run one T1 action (scene switch) with token via the prototype API; verify rejection of no token, wrong token, loopback web-page POST (confirms finding 1), non-tailnet caller; record click-to-ack latency.
6. **Report**: measurement table, go/no-go on Tailscale, SRT vs WebRTC decision, profile numbers, prototype change list. Only then propose M2.

## Proposed pass criteria
Direct path on home + hotspot; tunnel adds <5 ms RTT vs baseline when direct; recovery <10 s after a drop; 8 Mbps stream with <1% unrecovered loss; command ack <300 ms when direct.

## Record
Results go in `Docs\PinguinoLink\results\` (create at test time).
