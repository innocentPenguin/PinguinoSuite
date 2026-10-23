# Pairing test: two PCs over Tailscale
Written 2026-10-23 by session 52. Nothing here goes live; no step touches the stream button.

## Where things stand (checked 2026-10-23 ~08:30, read-only `tailscale status`)
- Tailscale is running on this PC (`ivansserver`, 100.74.117.87).
- Only one other device is on the tailnet: `ivans-macbook-pro` (100.87.218.35, macOS), offline, last seen 23 days ago.
- There is no second Windows PC on the tailnet yet. Install Tailscale on the second PC and sign in with the same account first (Link only talks to devices on your tailnet).
- This PC's Link role is still `client`, hub name `streaming-pc`. I did not change role or macros.

## A. Pair the two PCs
Call them PC1 (the streaming PC, will be the hub) and PC2 (the other PC, with PinguinoLite).
1. On both PCs: Tailscale running, PinguinoSuite running, Link module green (port 7777). In the Suite open **Modules > Link**, or go to http://127.0.0.1:7777 on that PC.
2. On PC1, on the Link page find the **Devices** card. Click **Show a pairing code**. A 6-digit code appears (valid 5 minutes, Tailscale devices only).
3. On PC2, open its Link page, **Devices** card. In the first box type PC1's Tailscale name (for example `ivansserver`) or its 100.x address. In the second box type the 6-digit code. Click **Pair**. The button waits: PC1 has to approve.
4. On PC1 a **Pairing requests** line appears: "<PC2 name> wants to pair". Check the name is PC2, then click **Allow**. (Deny cancels it. It times out after 90 seconds.)
5. Both Devices cards now list the other PC with a green dot. If PC2 shows a grey dot, wait 12 seconds or check Tailscale on PC2.
6. If anything fails, the message under the Pair button says why. Wrong code three times cancels the code: click **Show a pairing code** again.

## B. Make PC1 the hub (one deliberate click)
Only the PC that runs OBS is the hub.
1. On PC1: Link page > **Settings** > **Role** > choose **hub**.
2. A line appears: "Switch this PC to hub? It will run OBS macros itself." with a confirm button. Click it. Nothing changes until you do.
3. On PC2 leave Role = **client** and set **Hub device** to PC1's Tailscale name.
4. Leave "Let paired devices start/stop my stream" OFF and "Allow Start Stream" OFF.

## C. Confirm a macro forward (safe macro only)
1. In OBS on PC1 make sure the scene names exist (see section E). OBS WebSocket password must be in the Suite key vault (Integrations > Key vault > OBS_WS_PASSWORD) and the **Test** button next to it must say OK.
2. On PC2's Link page press the **BRB** button, then **Main** (scene switches only; they never start or stop the stream).
3. Expected: OBS on PC1 switches scene; on PC2 the Activity list shows a green tick; on PC1 the Activity list shows "BRB ... from <PC2 name>".
4. If PC2 says "remote macros are turned off", turn on **Let paired devices run my OBS macros** on PC1 (Settings > Devices).

## D. Confirm the update fetch (PinguinoLite)
1. On PC1 (update host) put a package in `Data\lite\packages` with `node Suite/modules/link/src/cli.mjs pack <module id>` (module.json needs a version). Settings > Devices > **Share update files with my paired PCs** is on by default.
2. On PC2 open PinguinoLite and click **Check for updates** (it also checks every 5 minutes). Setting **Fetch update files from my paired PCs** is on by default.
3. Expected: within a few seconds the Link console log on PC2 says `fetched <name> from <PC1 name> (hash verified)` and the file appears in PC2's `Data\lite\packages` (or `staging` for an installer). A hash mismatch shows "failed the hash check; discarded" and nothing is installed.
4. Nothing installs by itself: you still click Install/Update in Lite.

## E. Names I guessed: replace with your real OBS names
The default macros in this PC's Link config (`Data\runtime\link\config.json`) use names I made up. Rename the scenes in OBS to match, or edit the macros (Link page > Macros):
| Macro | What it does | Guessed name you must replace |
|---|---|---|
| brb | switch scene | scene `BRB` |
| live | switch scene | scene `Main` |
| mute | toggle mute | input `Mic/Aux` |
| start | StartStream | none, and it stays blocked while "Allow Start Stream" is off |
| stop | StopStream | none |
Check: in the Macros editor the Check button says "missing: ..." for any name OBS does not have. The Link readiness list also shows "macro targets" as pass/fail once the hub is connected to OBS.

## F. Undo
Link page > Devices > **Unpair** (click twice to confirm) on either PC removes the pairing on both sides. Role can be switched back to client the same way as in B.
