# PinguinoSuite

Host app for all the Pinguino tools. Run `PinguinoSuite.bat` (hidden, tray icon) -> http://127.0.0.1:8760

- Watches Twitch for the channel going live (polls every 20s; a 3-minute grace period ignores stream blips).
- Starts/stops modules and tells them when you go live (`modules.json` defines each module + its on_live / on_offline hooks).
- PinguinoListen (modules/listen) stays warm with the model loaded; on go-live the Suite tells it to start your last-used mic.
- "Test: go live / end" simulates a stream so you can check auto-start without actually streaming.
- "start with Windows" toggle (HKCU Run key) in the header; tray icon -> Quit stops everything.
- Logs: logs/. Settings: suite_settings.json. Twitch creds: env, Suite\.env or D:\PinguinoSuite\PinguinoSite\.env.

Adding a module = a folder + an entry in modules.json (any language, just needs a port and a health URL).
Events flow through the Suite's bus (ws://127.0.0.1:8760/ws) - the seed for Streamer.bot-style actions later.
