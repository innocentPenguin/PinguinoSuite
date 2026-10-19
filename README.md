# PinguinoSuite

Everything for the stream, in one place. Open **PinguinoApp\PinguinoApp.lnk** (or `PinguinoApp.vbs`) to start the Suite.

| Folder | What it is |
|---|---|
| `PinguinoApp\` | Launcher: opens the Tauri shell if built (one window, tray, single-instance), else the standalone Suite |
| `Suite\` | Dashboard + module host. `modules\listen` = PinguinoListen, `modules\link` = PinguinoLink |
| `PinguinoB0t\` | The matchmaking/customs bot: `PinguinoBotCore.cs`, `PinguinoBotFirsts.cs`, `commands.json`, `overlays\`, CHANGES, cheat sheet |
| `PinguinoChat\` | The AI chat bot: `PinguinoChat.cs`, SETUP, history hook, `updates.json` (+ `add-update.mjs`) |
| `HelperPinguino\` | The helper bot: `PinguinoHelper.cs`, design doc |
| `Shared\` | Code all three bots share (`PinguinoBots.cs.txt`, router) + `sync-shared.mjs`, BOTS_DESIGN |
| `Pipeline\` | Scripts that fetch chat logs and build profiles / lore / nicknames / history (scheduled task "PinguinoBot Log Update", log agent for the site) |
| `Data\` | chat_logs, profiles, history, lore.json, common-words.txt, nickname-overrides.json |
| `PinguinoSite\` | The website (git: github.com/innocentPenguin/PenguinSite, deployed on Railway) |
| `Tests\` | `core`, `chat`, `helper`, `bots`, `history` test suites |
| `Archive\` | Old versions (`PinguinoBotCore.before-*.cs`) |
| `Tools\` | `remove-legacy-links.ps1`, `finish-site-move.ps1` |

## Run the tests
```
powershell -ExecutionPolicy Bypass -File Tests\core\run-tests.ps1
powershell -ExecutionPolicy Bypass -File Tests\chat\run-chat-tests.ps1
powershell -ExecutionPolicy Bypass -File Tests\helper\run-helper-tests.ps1
powershell -ExecutionPolicy Bypass -File Tests\bots\run-bots-tests.ps1
powershell -ExecutionPolicy Bypass -File Tests\history\run-hook-check.ps1
```
Site: `cd PinguinoSite; npm run build; npm test`.

## Still pointing at the old paths (works through links until you do these)
The folder used to be `D:\PinguinoBot`; compatibility links remain there (see `D:\PinguinoBot\README-MOVED.txt`).
1. **Streamer.bot**: the three actions hold *pasted copies* of the C# files. Paste the new `PinguinoB0t\PinguinoBotCore.cs`,
   `PinguinoChat\PinguinoChat.cs`, `HelperPinguino\PinguinoHelper.cs` and compile (new default paths inside).
2. **OBS**: browser sources for `players.html` / `queue.html` -> `D:\PinguinoSuite\PinguinoB0t\overlays\...`.
3. **%AppData%\BVQ\settings.json** (`OverlayDir`) and **chat_settings.json** (`CommandsFile`, `UpdatesFile`, `OpinionsFile`): change to the new paths.
4. Then run `Tools\remove-legacy-links.ps1`.
5. The site folder: done. The site lives in `D:\PinguinoSuite\PinguinoSite`; `D:\InnocentPenguinSite` is just a link to it.
