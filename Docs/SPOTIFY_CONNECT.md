# PinguinoSuite as a Spotify Connect device (design, 2026-10-23, 50 - Tools)

Goal (Ivan): the Suite itself is the Spotify device "PinguinoSuite", so one song can reach two outputs (OBS for the stream, his headphones) with separate volumes, and the same thing works on a Mac ("thru pinguinosuite ... work through mac pretty well"). The in-app Web Playback SDK player cannot do it (WebView2 has no Widevine), so the module runs **go-librespot** as a child process. Nothing is a separate install for Ivan: the module ships and starts it.

## 1. Pieces
- Binary: `Suite\modules\spotify\bin\<os>\go-librespot[.exe]` (today: `bin\go-librespot.exe` v0.10.5 Windows amd64 plus its MinGW DLLs libvorbis/libogg/libFLAC/libmpg123/libgcc/libstdc++/libwinpthread, already copied from MSYS2 by the spike). macOS: `brew install go-librespot` or the release binary; backend `audio-toolbox`. Linux: alsa. The module picks `bin\win\`, `bin\mac\`, `bin\linux\` by `sys.platform`; missing binary = feature shows "not installed on this PC" and the browser player stays the fallback.
- Config written by the module to `<PINGUINO_DATA_DIR>\spotify\connect\config.yml` (never inside bin, never committed); go-librespot started with `-config_dir <that folder>` (it also keeps `state.json` with its credentials and a `lockfile` there, which already prevents two instances on the same config).
- Login: `credentials.type: device_auth`. go-librespot prints a code and serves `GET /auth/code -> {url, code, expires_at}` while it waits; the Setup card shows "Go to spotify.com/pair and enter CODE" with a button that opens the URL. Ivan does the click and the login himself; no browser redirect port, works headless and on a Mac. Credentials persist in `state.json`; re-login only when Spotify revokes them (card shows the code again).
- Control: REST on `127.0.0.1:<connect_port>` (default 3678, picked free at start if taken): `GET /status` (device_id, volume, track, paused), `POST /player/volume {volume}` (0..volume_steps), `POST /player/output {device}` (switch output without restart), `POST /player/pause|resume|next|prev|play`, WebSocket `/events` (playing, paused, volume, playback_error, active/inactive). The Web API still sees it as a normal device, so the existing queue/JIT logic needs no change.

## 2. New file `Suite\modules\spotify\connect.py`
`class Connect` (owned by Engine, one instance):
- `start()`: refuse if disabled, binary missing, or already running; write config.yml (device_name "PinguinoSuite", device_type computer, zeroconf_enabled false, credentials device_auth, audio_backend per OS, audio_device = setting `connect_output` or `default`, initial_volume = `player_volume`, volume_steps 100, server enabled on 127.0.0.1:<port>, log_level info); `subprocess.Popen` with stdout/stderr piped to a reader thread that forwards lines to the Console source `spotify` (prefix `connect:`; info for normal lines, warn for `error`/`failed`), CREATE_NO_WINDOW on Windows, `start_new_session` elsewhere.
- Health: poll `GET /` every 5 s (`playback_ready`), `GET /status` every 10 s for `device_id` and volume; state machine `off | starting | waiting_login (code, url, expires) | ready | error(reason)`.
- Auto-restart with back-off 2, 5, 15, 60 s, max 5 tries then `error("gave up, press Restart")`; never restart while `waiting_login`.
- `stop()`: `POST /player/pause` best effort, then terminate, wait 3 s, kill. Called from Engine shutdown and `atexit`. On start, kill a stale child from a previous module run (pid file `connect\pid`), never anything else.
- `set_volume(v)`: `POST /player/volume {volume: v}`; `set_output(name)`: `POST /player/output {device: name}` and rewrite config for the next start.
- `info()`: `{enabled, installed, state, device_id, output, port, code, code_url, code_expires, last_error, restarts}` (no tokens, no credentials).
- Output device list: Windows via `sounddevice` if importable (the voice venv has it) else PowerShell `Get-CimInstance Win32_SoundDevice`; macOS `system_profiler SPAudioDataType` names. Cached 60 s, served as `GET /api/connect/outputs`.

## 3. Engine changes (engine.py)
- `player_live()` becomes: Connect `ready` with a `device_id` -> that id; else the existing browser-player rule. `PLAYER_NAME` stays "PinguinoSuite" for both, so `_player_tick` (transfer when something else is the target) and `player_device()` (start queue there) work unchanged. Manual override hold (10 min) unchanged.
- `_set_volume(v)`: if Connect is ready and is the current device -> `connect.set_volume(v)` and save `player_volume`; else the current path.
- Shutdown hook calls `connect.stop()`.
- Pre-stream item `connect`: pass = ready and visible in `api.devices()`; warn = enabled but waiting for login / not installed; skip when disabled.

## 4. Settings (config_schema.py, group "Playback")
`connect_on` bool default False (Ivan turns it on once; the first start shows the pairing code) · `connect_output` str "" (output device name, empty = system default) · `connect_port` int 3678 · `connect_bitrate` int 160 (96/160/320) · `connect_normalize` bool True. `player_native` keeps meaning "browser player allowed as fallback".

## 5. Server (server.py) and Setup tab
`GET /api/connect` -> `info()`; `POST /api/connect/{start|stop|restart}`; `GET /api/connect/outputs`; `POST /api/connect/output {name}`. Same auth as `/api/control` (page origin or module token). Setup tab card "PinguinoSuite device": status line, pairing code + "Open spotify.com/pair" button while waiting, output device dropdown, volume follows the existing volume box, Start/Stop/Restart, last 5 log lines. Master View needs nothing new (volume strip already calls `/api/control volume`); master.html line 100 text "Your own listening output is not available yet" becomes wrong once this ships (tell 20 - Suite).

## 6. Tests (tests/test_connect.py + e2e)
Fake go-librespot = small stdlib HTTP server in tests/fakes.py (`/`, `/status`, `/auth/code`, `/player/volume`, `/player/output`) and a fake process object; Connect gets injectable `popen` and `http`. Cases: disabled -> never spawns; binary missing -> state error, browser fallback used by `player_live`; config.yml content per OS (backend, device, name, port); waiting_login exposes code/url, no restart while waiting; ready -> `player_live` returns its device id and `_player_tick` transfers; volume routed to Connect only when it is the current device; crash -> back-off restarts then gives up; stop kills the child; stale pid cleanup; no credentials or tokens in `info()` or logs. e2e: one scenario "connect ready" through the real server with the fake.

## 7. Open questions (defaults)
1. Output default: VB-Cable "CABLE Input" (exists on this PC) - default yes. 2. Bitrate 160 (Spotify's "normal") - default yes, 320 later if CPU is fine. 3. Should Start happen automatically when the module starts and `connect_on` is true - default yes.

## 8. Routing steps for Ivan (Windows 11 + OBS; nothing here needs the stream to be live)
1. In the Suite, Spotify page > Setup > "PinguinoSuite device": switch it on, pick Output = **CABLE Input (VB-Audio Virtual Cable)**, press Start. When a code shows, open spotify.com/pair on your phone or PC, enter the code, approve. The card says "ready".
2. In the Spotify app on your phone/PC, pick the device **PinguinoSuite** from the devices list once (the Suite also selects it by itself when it sees it). Music now plays into the cable, so you hear nothing yet. That is expected.
3. OBS: Sources > + > **Audio Output Capture** > name it "Music" > Device = **CABLE Output (VB-Audio Virtual Cable)**. Its fader in the Audio Mixer is the stream's music volume.
4. OBS: Audio Mixer > gear on "Music" > **Advanced Audio Properties** > Audio Monitoring = **Monitor and Output**. In Settings > Audio > Advanced > Monitoring Device pick your **Headphones**. Now you hear the music too.
5. Your own volume: OBS has no separate monitor fader per source, so set it with the Windows volume mixer for the headphones (or Voicemeeter if you prefer); the stream's level is the OBS "Music" fader; Spotify's own volume (the Suite box, !volume) changes both at once. Keep the Spotify box high (70-100) and balance with the two faders.
6. Make sure OBS "Desktop Audio" does not also capture the cable (Settings > Audio > Desktop Audio = your speakers, not CABLE Output), or the music will be doubled.
7. The bot voice gets the same treatment on a second cable: see Docs\VOICE_ROUTING.md.
Mac later: same steps with BlackHole (2ch) in place of VB-Cable; the Suite picks the audio-toolbox backend by itself.
