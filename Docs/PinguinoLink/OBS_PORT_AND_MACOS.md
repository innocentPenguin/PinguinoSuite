# OBS port 4455 restriction (design only) and macOS pass
Session 52, 2026-10-23. Items 5 and 6 of section 4 in Docs/sessions/04-pinguinolink.md. No setting, firewall rule or code was changed for the port; the macOS findings below list what a real Mac run still has to prove.

## 1. Restricting OBS WebSocket port 4455 (design, not applied)
Facts
- obs-websocket has no "bind address" option: OBS listens on all interfaces. The only knobs are port, password and "Enable authentication".
- Link only ever talks to OBS at `127.0.0.1:4455` (config `obs.host` default). So nothing remote needs 4455.
- Today something else uses 4455 from outside Link: the replay-buffer hotkey path (per the 04 hand-over, "restrict only after Link replaces the replay-buffer hotkey"). That must be replaced first.
- Authentication is on (password required), which already stops casual use. The risk is a LAN or tailnet device guessing the password, or a leaked password; with it, an attacker could start the stream.

Design (do in this order, only when Ivan says go)
1. Prerequisite: Link gets a "Save replay" macro (SaveReplayBuffer request, read/write-safe, never StartStream) and whatever uses 4455 today switches to Link's macro. Check with `netstat -ano | findstr :4455` which processes connect.
2. Windows Defender Firewall inbound rule on the streaming PC: block TCP 4455 for Domain/Private/Public profiles. Loopback traffic is not filtered by Windows Firewall, so Link keeps working. Command (run as admin by Ivan, reversible by deleting the rule):
   `New-NetFirewallRule -DisplayName "Block OBS WebSocket (remote)" -Direction Inbound -Protocol TCP -LocalPort 4455 -Action Block`
   Tailscale traffic arrives on the Tailscale adapter, so this rule blocks it too (intended: remote devices go through Link on 7777, which has peer auth and the stream guards).
3. Add a Link pre-stream check "OBS port closed to the network": from this PC, connect to `<own LAN IP>:4455` and to `<tailnet IP>:4455`; both should fail while `127.0.0.1:4455` works. Report as warn (not fail) until the rule exists.
4. Optional later: move OBS to a non-default port with `obs.port` in the Link config, so scanners miss it. Low value after the firewall rule.
Rollback: `Remove-NetFirewallRule -DisplayName "Block OBS WebSocket (remote)"`.
macOS hub: the built-in firewall is application-based; use `pf` (`block in proto tcp to any port 4455` on non-loopback interfaces) or leave as is and rely on the password; document at macOS-pass time.

## 2. macOS pass: what I found by reading the code (nothing run on a Mac)
Works by design
- Node >= 22, no dependencies, loopback + Tailscale only. `tailscale.mjs` already lists the macOS app path `/Applications/Tailscale.app/Contents/MacOS/Tailscale` and Homebrew paths. Config goes to the Suite data dir, so no Windows-only location.
- Mesh, macros, OBS client, settings, page and all tests are platform-neutral (tests spawn `process.execPath`).
- The doctor's Tailscale restart has a non-Windows branch (`sudo tailscale down && up`; needs a terminal password prompt, so it will not work from the page).
Windows-only (will not work on a Mac as is)
1. `lite.mjs findLiteExe` uses `powershell.exe` and `%LOCALAPPDATA%\PinguinoLite\PinguinoLite.exe`; `applyupdate.mjs` uses `tasklist.exe`, installer `PinguinoLite-<v>-setup.exe /S`. The Lite self-update apply is Windows only. A Mac needs its own contract (.dmg or .pkg, `pgrep`, `open -a`) when Lite exists for macOS. Until then the apply route should answer "not supported on this OS" (today it fails with "cannot find the installed PinguinoLite.exe", which is harmless but unclear).
2. `SHARE_RE` and `checkLiteUpdate` only accept `PinguinoLite-<v>-setup.exe`; Mac installers would not be shared or fetched.
3. `lite.mjs` module start/stop/restart and `pack` are neutral (pure files/zip).
Fixed during this pass
- `tailscale.mjs:15` had its Windows fallback paths with single backslashes inside JS strings (`'C:\Program Files\Tailscale\tailscale.exe'` became `C:Program FilesTailscale<TAB>ailscale.exe`), so Link could not find Tailscale when it was not on PATH. Now doubled; verified with PATH stripped.
To prove on a real Mac (needs Ivan's MacBook, offline 23 days): run `node Suite/modules/link/src/selfcheck.mjs` and `meshcheck.mjs`, start Link, confirm Tailscale status shows, pair with the Windows PC (PAIRING_TEST.md), press a macro from the Mac.
Note for future editing: the shell tool that sessions use can silently halve backslashes in typed text. Windows paths in JS strings need `\\`; check with `node -e` after editing (this caused the INDEX.md and tailscale.mjs bugs).
