# PinguinoLite on the gaming PC: day-one guide

For Ivan. Plain steps. Written 2026-10-23 by 21-Lite. Nothing here was tried on a real second PC yet; the steps match what the code does and what the tests cover. If a step does not behave as written, make a support bundle (step 7) and send it.

## Checklist (tick as you go)
- [ ] 1. Node.js 22 or newer is on the gaming PC (`node -v`).
- [ ] 2. The release is published and you have its manifest link (and the public key if it is signed). See `LITE_RELEASE.md`.
- [ ] 3. Copy `Installer\` and `Suite\updater\` to the gaming PC (for example `C:\PinguinoSetup\`).
- [ ] 4. Run the one install command (step 3 below). It must end with `"ok": true`.
- [ ] 5. Start Lite with the shortcut. The Dashboard shows the version and the Parts card.
- [ ] 6. Play one match, save the replay, and see it on the Replays page.
- [ ] 7. Make a support bundle once, even if all is fine, and look inside (no tokens).
- [ ] 8. You know how to uninstall (step 8). It moves things, it deletes nothing.

## 1. What the gaming PC needs
- Windows 10/11 and internet for the first install.
- **Node.js 22 or newer**. Check in a command window: `node -v`. If it is missing, install it from nodejs.org (LTS), then open a NEW command window.
- Rocket League installed and played at least once on this PC (so the Demos folder exists).
- You do NOT need Python, .NET or the Suite itself. A "lite-minimal" install is about 8 MB.

## 2. What to copy
From the main PC copy two folders to the gaming PC (USB stick or cloud drive), side by side:
```
C:\PinguinoSetup\Installer\
C:\PinguinoSetup\Suite\updater\
```
Keep the names exactly. Nothing else is needed.

## 3. The install command
Open a command window (Win+R, type `cmd`) and run it as ONE line. Replace the two placeholders:
```
node C:\PinguinoSetup\Installer\install.mjs --target C:\PinguinoLite --url <MANIFEST-URL> --pubkey <PUBLIC-KEY> --profile lite-minimal --shortcuts
```
- `<MANIFEST-URL>` is the link to `manifest.json` of the release, for example `https://github.com/innocentPenguin/PinguinoLite/releases/latest/download/manifest.json` (this exists only after you publish the release).
- `<PUBLIC-KEY>` is the signing public key. Leave `--pubkey <PUBLIC-KEY>` out completely if the release is not signed.
- No internet, or a release on a USB stick? Use `--local D:\release` (the folder holding `manifest.json` and `suite-<version>.zip`) instead of `--url`. Then Lite cannot fetch updates later by itself.
- It refuses, and says why, if there is not enough disk space, if Node is too old, or if the folder is not empty.

Success looks like: the last line says `"ok": true`, the folder `C:\PinguinoLite` has `install.json`, and a PinguinoLite shortcut is on the Desktop and in the Start menu.

## 4. First launch
Double-click the **PinguinoLite** shortcut (it runs `C:\PinguinoLite\PinguinoLite\Start-Lite.bat`). A splash shows, then the window.
What the Dashboard should show on a healthy gaming PC:
- **Host: Not reachable** is normal here (the Host runs on the streaming PC). Lite works without it.
- **App version**: the release you installed.
- **Parts** card: a list (lite, link, tools), each "Up to date". If it says "This copy has no install.json", the install did not finish; run the command again.
- **PinguinoLink**: a name and version within a few seconds. If a yellow note says Link is not running, wait a few seconds or restart Lite.
- **Modules installed**: 0 or a few. Other modules (listen, multi, spotify) show "Not installed" with an Install button.
Empty pages now say why they are empty and what to do (no Link, no replay folder, no install.json).

## 5. Replays check with one real match
1. Open the **Replays** page. "Watching" lists the Demos folders it found; the real one is under `Documents\My Games\Rocket League\TAGame\Demos` (also found under `OneDrive\Documents` if Windows moved Documents there; OneDrive must be running).
2. Play one match (casual is fine) to the end. In Rocket League open the match history or post-game screen and **Save replay**.
3. Within a few seconds (the interval slider on the page, default 3 s) a row appears: time, size (2v2), score, winner, MVP. Also the Dashboard "Replays" card shows 1 match.
4. Nothing is uploaded; only the replay header is read. Broken, empty or huge files are skipped and never freeze Lite.
5. The winner is attributed to a Twitch viewer only while a Suite custom match is running with the Host. Without the Host you still get score and MVP.
Not working? Press **Scan now**, check the "Watching" folder names, then make a support bundle.

## 6. Updating
Dashboard / Parts: **Check parts** then **Update**. Updates wait while you are live. **Roll back last update** puts the previous version back.

## 7. Support bundle (when something is wrong)
Dashboard > **Make support bundle**. Wait a few seconds, then **Open bundle folder**. Send the `.zip` (or the whole `bundle-<number>` folder) to Ivan. It holds: logs (secrets removed), `install.json` without secrets, the parts check, how many replays were read, Windows version, free disk and memory numbers. It never holds replay contents, tokens or passwords. It is fine to open the files first and look.

## 8. Uninstall (moving, never deleting)
Close Lite and the Suite first. In a command window:
```
node C:\PinguinoSetup\Installer\install.mjs --target C:\PinguinoLite --uninstall
```
This only LISTS what would move. To do it, add `--yes`:
```
node C:\PinguinoSetup\Installer\install.mjs --target C:\PinguinoLite --uninstall --yes
```
Everything except `Data\` is MOVED into `C:\PinguinoLite\Data\updates\ejected\uninstall-<time>\`. Your settings and tokens in `Data\` stay (add `--purge-data` only if you want those moved too). Shortcuts stay until you delete them. To free the space, delete the dated `uninstall-<time>` folder yourself once you are sure.

A damaged install (missing files after an antivirus run, say) can be fixed without uninstalling: `node C:\PinguinoSetup\Installer\install.mjs --target C:\PinguinoLite --repair`.

## Things that are NOT done by this guide
- No push, no release publishing, no live stream, no OAuth or passwords. The release must already exist (Ivan publishes it; see `LITE_RELEASE.md`).
- Do not go live in OBS while testing.
