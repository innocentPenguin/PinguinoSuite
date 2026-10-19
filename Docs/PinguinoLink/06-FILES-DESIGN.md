# 06 — File Transfer and Sync

## Tools
- **Taildrop** (already wrapped in the prototype): quick small drops.
- **Syncthing**: selected folders; block hash verification, resume, conflict copies, versioning, direct-or-relay, Win/mac/Linux.
- **rclone / SFTP-style resumable push** over the tailnet for one-shot large files.
PinguinoLink provides one queue/UI: progress, history, hash check, "send to device".

## Rules
- Never transfer a file still being written (OBS recordings: wait for close/finalize of hybrid MP4; size-stable check).
- Never overwrite; conflicts keep both versions.
- Per-device allow-listed folders; no traversal or symlink escape; quarantine inbox.
- Path normalization at the edge; history kept on the hub.
- Input path to know about: OBS replay files in `D:\Recordings`; recordings default to `C:\Users\ivanm\Videos`.

## Remote project editing
Do not edit Premiere/Resolve projects over SMB/WebDAV across the internet (lock/corruption risk). Use sync copy + single-writer "checked out by" marker; LAN-only SMB acceptable for read/render. Revisit after measuring throughput.
