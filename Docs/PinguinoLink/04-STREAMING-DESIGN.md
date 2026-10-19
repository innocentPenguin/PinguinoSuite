# 04 — Mac -> Home OBS Streaming

## Proposed pipeline (to be proven in Milestone 1)
MacBook (OBS or ffmpeg, VideoToolbox H.264, AAC) --SRT caller, AES passphrase, latency ≈ 3–4× RTT--> hub MediaMTX (SRT listener) --> OBS Media Source from 127.0.0.1 --> scene "Remote Cam".
MediaMTX hop keeps OBS's source alive across Mac reconnects and exposes stats; direct OBS SRT listener is the simpler fallback.

## Transport comparison
| Transport | Latency | Loss handling | Notes |
|---|---|---|---|
| SRT | ~100–500 ms | ARQ, tunable | Best fit; A/V in one stream (sync); stats |
| RIST | similar | ARQ/FEC | Good second choice; less Mac tooling |
| WebRTC/WHIP | lowest | built-in congestion control | OBS does WHIP output, not input; receive via Browser Source (e.g. VDO.Ninja); strong fallback for rough networks |
| RTMP | medium | TCP stalls | fallback only |
| NDI | very low | LAN-oriented | not for remote |

## Profiles
Quality 1080p60 ~12–15 Mbps · **Mobile 1080p60 (or 30) ~8 Mbps** · Rough 720p30 ~3–4 Mbps · Rescue 480–720p ~1.5 Mbps audio-priority. H.264 default; HEVC optional where the hub decodes it.

## Adaptation
SRT has no built-in rate adaptation. Phase A: manual/suggested profile switch. Phase B: controller reads SRT stats (RTT, loss, buffer) and steps profile; needs an ffmpeg-style sender or WebRTC for smooth live bitrate changes (OBS cannot retune the encoder live).

## Resilience
Sender auto-reconnect with backoff; OBS source restart on drop; auto-BRB scene after N s of stall and auto-return; hub-side relay survives reconnects; clap/flash test for A/V sync.

## Limits
A powered-off or away Mac cannot be woken over the internet; "turn on remotely" means starting the session from the Mac/app.

## Unknowns to measure
Direct vs relay per network, real loss/RTT, MacBook model/encoder load, hub NVENC headroom, ffmpeg/MediaMTX/SRT availability (ffmpeg and srt-live-transmit are not installed on the hub).
