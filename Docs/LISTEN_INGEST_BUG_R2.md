# Listen ingest: orphan VOD downloads (evidence for the listen owner)

Written by Runner 2, read-only, 2026-10-20 ~22:40 CDT. Nothing was changed.

## Symptom
`Suite\modules\listen\data\sources` holds 24 `vod-*.mp4` files, each exactly 876,626,811 bytes (835.99 MiB), all with the same full SHA256 `9ce1053dafda3c06fb3288e27e0756c90edc1c765b140a19988950dc553838de`. About 21 GB. A new one lands roughly every 30 minutes (mtimes 09:44, 10:27, 10:55, 11:25, 11:55, ... 20:57, 21:36 today).

File ids: 0242eb56, 12528281, 12833b25, 17dced9a, 1f197848, 22ffc2f2, 233835b8, 35616aa9, 3e1b0d65, 4e735b93, 659b1d96, 698c9b7c, 792bc956, 9403c816, a157c3a8, a45af728, a4820434, aaf6a028, c85371e1, ccb8aee2, d9aad889, e1010e3d, e9f7b2d9, fdf575ae (each `vod-<id>.mp4`).
None of these ids exist in `data\ears.db` `sessions`. Different file: `vod-5254f0b6.mp4` (384,048,781 bytes, 09:23, also no row). Live one: `vod-b40bde2d` (row exists, status `converting`, source `vod:2904591605`, created 21:56).

## The file is good
Opened one with PyAV: AAC 48 kHz stereo, 1,583,934 packets demux with no error (about 9.4 hours of audio, a normal complete VOD). So the download completes and the file is valid.

## Log evidence (`Suite\logs\listen.log`)
- yt-dlp progress lines for a 3380-fragment VOD recur many times (`frag N/3380`, 11 lines contain it), ending `[download] 100% of 835.02MiB in 00:33:33 at 424.60KiB/s`. So one download takes about 33 minutes, matching the 30-minute file cadence.
- Repeated `ConnectionResetError: [WinError 10054]` and `ERROR: [download] Got error: Connection broken` (lines 43-80 and 105-107).
- 14 consecutive `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8765)` (lines 82-95): Listen was launched repeatedly while another instance already held the port. So several Listen processes have been starting and dying, each running its own in-memory job queue against the same `ears.db`.

## Mechanism (from code; the parts marked "likely" are not proven)
`ingest.py`:
1. `_run` downloads to `data\sources\<sid>.<ext>`, runs `to_ogg`, then `src.unlink()` (line ~134). The mp4 is only removed if conversion finishes. If the process dies or `to_ogg`/ASR raises first, the mp4 stays.
2. `recover()` (called at every start) marks any queued/downloading/converting/transcribing non-live row as `interrupted` ("interrupted by a Listen restart - press Learn again") when it has no segments.
3. `submit()` for a source whose row is `interrupted` or `error` and has no segments does `DELETE FROM sessions WHERE id=old` and inserts a new row with a fresh `uuid4()[:8]` id. The old id's mp4 on disk is never cleaned up, and nothing links it to the new row.
4. `autolearn_loop` in `server.py` runs `sync_twitch()` every 1800 s (autolearn on, `autolearn_vods: 3`), which re-submits the latest 3 VODs that are not `done`.
Net: every restart or error leaves a stranded full download whose row is deleted, and the next sync downloads the same VOD again under a new id. That fits identical bytes, 30-minute cadence and no matching rows. The 9 `interrupted` VOD rows from 2026-10-19 23:49 (`vod:2895516303` .. `vod:2902651575`) show the same restart path.
Likely, not confirmed: the repeated restarts (port 8765 collisions) or a `to_ogg` failure on this one ~9.4 h VOD are what keep it from reaching `unlink`. The log has no traceback for the conversion step, so the reason is not captured; `_push(... status="error", error=...)` stores it in the row, but the row is then deleted by the next `submit()`.

## Suggested fixes (for the owner to judge)
- In `submit()`, delete `data\sources\<old_id>.*` (and `.part*`) when dropping the old shell, or reuse the old id instead of making a new one.
- On startup, sweep `data\sources` for files whose id has no `sessions` row and are older than a few hours.
- Keep the failure text (log it with a traceback in `_worker`) before the row is deleted.
- Find out why Listen starts several times (port 8765 in use), and why this VOD never finishes converting.
- Optional: the 33-minute re-download for a 9.4 h VOD could be skipped by keeping the file when conversion is what failed.
