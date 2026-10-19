# 08 — Roadmap, Costs, Risks, Extra Features

## Roadmap
M0 docs (this) -> **M1 real-device test (09)** -> M2 hub agent v1 (signed API, tiers, audit, OBS adapter, Suite registration) -> M3 streaming profiles + MediaMTX service -> M4 Companion/Stream Deck + dashboard -> M5 files (Syncthing + queue) -> M6 diagnostics assistant + enrollment installer -> M7 macOS polish (launchd, Keychain, menubar); Linux later. Coordinate with Unit 01 on Suite integration.
Architecture: `core/` (transport, policy, audit, API) has no OS code; `adapters/{windows,macos,linux}` hold service install, credential store, power/WoL, capture devices.

## Costs
Tailscale personal, Syncthing, MediaMTX, Companion, SRT: free (verify Tailscale limits). Optional VPS ~$5/mo (Headscale/relay). Mobile data: 8 Mbps ≈ 3.6 GB/h, 12 Mbps ≈ 5.4 GB/h.

## Risks
- Relay-only networks (campus, CGNAT) degrade video — measure, keep WebRTC/low-bitrate fallbacks.
- Vendor dependence on Tailscale control plane — keep transport interface; Headscale as exit.
- Remote OBS misuse — tiers, confirmations, audit; OBS never public.
- Mac cannot be remotely powered on; WoL needs LAN helper.
- Speedify/VPN interference; MTU issues.
- Scope creep before measurements — gate M2 on M1 results.

## Alternatives considered
Raw WireGuard, Headscale, NetBird/ZeroTier/Nebula, Cloudflare Tunnel, RIST, WebRTC/WHIP, RTMP, NDI (see 02, 04).

## Overlooked valuable features
Phone alerts on stream health; auto-BRB on feed loss; per-profile data-usage meter; bonded uplink (Speedify + SRT evaluation); Mac-side backup recording; talkback/IFB; OBS preview thumbnail; auto-pull of replay clips from Recordings; per-network profile memory; config backup/restore; update channel.
