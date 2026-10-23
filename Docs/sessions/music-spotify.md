# Session notes: Music (PinguinoSpotify module)

Module: `Suite\modules\spotify\` (id `spotify`, port 8771). Docs: `Docs\SPOTIFY.md`, `Docs\SPOTIFY_CONTRACT.md` (site contract v1).
Only session 00 restarts the module (`App\Update-Module.bat spotify`). I commit only my own files and never push. Commit trailer: Co-Authored-By: Claude Sonnet 5.5.

## 1. What was built, and why (newest first; hashes from git log)
- 33348b3 / aa9e7ed Channel playlist. Ivan: site mod music controls become "a minimal version of his Suite ones: no scrubbing, no like/heart"; plus a "Channel playlist" he picks in the Suite Spotify page. Setup tab picker, `GET /api/playlists`, `POST /api/channel-playlist`, `POST /api/channel-playlist/add` (dedupe, 10/min overall, 4/min per user), push `status.channelPlaylist={name}` (name only, never the id), site mod action `playlist_add`, acks added|duplicate|no_playlist|rate_limited|error. Contract agreed with 05.
- 2c1d20b YouTube links in requests (`ytlink.py`): oEmbed title/channel only, cleaned, scored against Spotify search (title 65 / artist 35), settings `yt_links`, `yt_min_score` (70). Logged in Logs (source youtube).
- 2289ff0, 55bb711 Vote skip (`activeChatters`, `skipNeed` from 02's Host; never skips twice), `!vol` readable by everyone and settable by mods, Logs tab (`GET /api/logs?since=`; console log plus chat commands, skips, volume changes).
- 4a9170c Settings view keeps scroll, open groups and focus across redraws and reloads (Ivan: scrolling Settings jumped to the top).
- b084e34, 2ca1482, 7c1041e, fb98432 Leaderboard (`/api/leaderboard`, also in the site push, song pages only), lyrics overlay (`/overlay/lyrics`, setting `lyrics_on`, LRCLIB), mod queue chat commands (!srremove/!srmove/!srtop, !srpause/!srplay, !srmute/!srunmute). Fallback playlist already existed (`fallback_*` settings). Ivan said yes to: lyrics widget toggleable, mod queue commands, request leaderboard ONLY on song pages, fallback playlist, site /queue page.
- Earlier: 075658b audit round 1; 91e6c08..09de601 mod ban commands (!bansong/!unbansong/!pardon, artist variants, !srban, !srsuspend, !songclear), Master view actions (like/skip/back/ban song/ban artist via `/api/mod-action`, CORS + tauri origin guard), richer `/api/now`, native player (Web Playback SDK device "PinguinoSuite" at `/player`, hidden iframe in the page), fix of "internal error" when picking a device (non-JSON 2xx in `default_http`), blocklist import, phantom modal fix (inline display on #dlg), tab persistence.

## 2. Decisions and failures
- Module never posts chat itself; Host polls `/api/announcements`.
- Two separate audio outputs with separate volumes is not possible inside the app (Widevine DRM, cross-origin SDK iframe); needs OBS per-source audio monitoring.
- Tokenless endpoints (`/api/mod-action`, `/api/control`, chat endpoints) rely on the Origin header; a local non-browser process can spoof it. Accepted risk.
- Artist ban uses substring match on the artist name: can over-block.
- Settings scroll jump: could not reproduce a poll-driven cause; fixed page-side, the rest was the shell iframe reset (01 fixed, 031bf59).
- Python edits: bash heredoc turns `\n` inside strings into real newlines; use `bytes([92,110])` or write files via small Python scripts. Files are CRLF.

## 3. For the next session
- Tests: `python -I -m unittest discover -s Suite/modules/spotify/tests -p "test_*.py"` (129) and `python Suite/modules/spotify/tests/e2e.py` (205, picks free ports). Never use port 8799 (taken by another module). Temp instance: `SPOTIFY_PORT=<free> PINGUINO_DATA_DIR=<tmp> python server.py`.
- After any server change, 00 must run Update-Module spotify. Pages in `static\` are served from disk (a reload picks them up).
- Tests monkeypatch api methods on `FakeApi`; `Engine.settings` is a property; `lyrics_http`/`yt_http` are injectable HTTP functions.
- Open: audit rounds 2 and 3 of the nightly audit not done; Spotify real-API behaviour of playlist add/list, lyrics fetch and YouTube lookups untried; week/month requester counts for the site leaderboard not available (05 asked).

## 4. Ideas, in priority order
1. Audit rounds 2 and 3. 2. Real-flow check after the next restart (playlist add, YT link, lyrics overlay in OBS). 3. Lyrics on/off button in the Master view. 4. Week/month leaderboard counts. 5. Show duration in YouTube match score (needs another data source). 6. Distinct reply for suspended viewers.

## 5. Chat history
Session transcript: `C:\Users\ivanm\.claude\projects\D--PinguinoSuite\3c399816-41c4-4048-9669-5a2086c857b7.jsonl`. Grep for: "Cycle 7", "leaderboard", "channel playlist", "YouTube", "Logs tab", "vote skip", "hostPlayer".

## 6. Things Ivan may be forgetting
- `SPOTIFY_API_KEY` is missing in the key vault (the site bridge cannot authenticate until he adds it).
- Spotify must stay connected; the streaming scope needed a re-login once (`needs_reauth` was false last check).
- The native player ("PinguinoSuite" device) has never been checked in a real browser; the Master View volume "Me" slider must stay disabled.
- Refunds for skipped/removed redeems depend on Host wiring (02) and the scope channel:manage:redemptions.
- Module restart is pending for everything after the last 00 rebuild: 55bb711, 2289ff0, aa9e7ed, 33348b3, 2c1d20b.
- Site /queue page is 05's to build; it needs Ivan's decision on whether week/month counts matter.

## Hand-over (2026-10-23): player, go-librespot spike

- Widevine: WebView2 has no EME, so the Web Playback SDK player (/player) only works in Edge/Chrome. The module's "Open player in my browser" button uses shell op `external`; the shell (App\src\index.html ~584) must allow loopback http (01 owns it). Until then the URL is copied.
- Module restart pending for commits 55bb711, 2289ff0, aa9e7ed, 33348b3, 2c1d20b. Not verified live: channel playlist add, YouTube lookup, lyrics fetch, real-browser player.
- go-librespot spike (Ivan: same song to two outputs with separate volumes; ToS risk accepted, own Premium only): BLOCKED.
  - Files in Suite\modules\spotify\bin (gitignored): go-librespot.exe v0.10.5, README, dl\golibrespot.tar.gz, spike-cfg\config.yml (device_name PinguinoSuite, zeroconf off, interactive login, API 127.0.0.1:3678), spike.log.
  - SHA-256 archive 5f5a28df9fca9cd6545ec4344d750d55167f15537370ce8cc3bc7c087f571d07; exe 3c6dfb087964120b27ec246e2f0b0cbebd391fa3e65a295c657435e99094f740.
  - The exe needs MinGW DLLs (libogg, libvorbis, libvorbisenc, libFLAC, libmpg123, libwinpthread, libgcc). MSYS2 was installed with winget at C:\msys64 (Ivan approved). The pacman download and DLL copy were denied by auto mode, so no DLLs are in bin\ yet.
  - Next steps: (1) pacman -S mingw-w64-x86_64-{libogg,libvorbis,flac,mpg123} in C:\msys64; (2) copy the DLLs from C:\msys64\mingw64\bin into bin\; (3) run go-librespot.exe -config_dir bin\spike-cfg, Ivan approves the browser login; (4) check "PinguinoSuite" in the Spotify device list and at 127.0.0.1:3678/status; (5) README shows no WASAPI device key (audio_device is ALSA-only), so likely route by setting the Windows default or per-app output to a virtual cable; confirm.
  - Routing target: one instance -> virtual cable -> OBS captures it -> OBS monitoring to headphones with own volume. Keep the browser player as fallback.
