# 02 — Network Architecture

## Recommendation
Tailscale (WireGuard) for Milestone 1, behind a thin `transport` interface so Headscale / NetBird / raw WireGuard can replace it. No custom VPN or crypto.

| Option | Direct path | Fallback | Fit |
|---|---|---|---|
| Tailscale | STUN + disco probing, direct UDP when NAT allows | DERP relay over HTTPS | Best: zero config, ACLs, device approval, key expiry, free personal tier (verify limits) |
| Raw WireGuard | none (port-forward/static endpoint) | none | Breaks on hotspot/CGNAT |
| Headscale | same clients | self-hosted DERP | Later, avoids vendor dependence; needs ~$5/mo VPS |
| NetBird / ZeroTier / Nebula | ICE-style | TURN / lighthouses | Viable alternates, more setup or less polish |
| Cloudflare Tunnel/WARP | none | always relayed | Added latency; unsuited to 1080p60 |
| SRT with port-forward | needs inbound hole | none | Useful only as a latency baseline |

## What a VPN/tunnel adds over the raw internet
- Encryption + authentication of every packet and identity-based access (device names, ACLs) instead of open ports.
- NAT traversal: no router port-forwarding; works behind CGNAT/hotspots.
- Stable private addresses across networks.
- Cost: ~60 B/packet overhead and MTU 1280 (≈5% more packets; ~0.4 Mbps at 8 Mbps), negligible CPU (ChaCha20-Poly1305), and when direct essentially no added latency. Measure in Milestone 1.

## Direct vs relayed
- **Direct**: peers exchange candidate addresses via the coordination server, probe, and send UDP straight to each other. Latency = normal internet path. Preferred for video.
- **Relayed (DERP)**: traffic goes through a relay (HTTPS/TCP). Works almost anywhere, but adds a detour, head-of-line blocking and throughput limits; poor for live video under loss.
- Typical causes of relay: carrier CGNAT, symmetric NAT, campus Wi-Fi with client isolation or UDP blocked. This PC: UDP ok, no IPv6, nearest DERP Chicago 17 ms, NAT mapping stable — promising, but only real tests count.
- The app must display path type, relay region and RTT, and warn before starting a high-bitrate stream on a relayed path.

## Notes
- Speedify (installed here) may change routing/MTU; test with it on and off.
- Cellular data cost: 8 Mbps ≈ 3.6 GB/h.
