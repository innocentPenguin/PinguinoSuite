# Ivan's live checklist (at the PC, nothing here needs you to be live)
Written 2026-10-23 by 53 for 50. Plain steps; each says what you should see. If something looks different, stop and tell the Coordinator. **Do not press Go Live in OBS for any of this** (see part 5).

## 1. Spotify Connect, first run (the Suite becomes a speaker called "PinguinoSuite")
1. Open the Spotify page in the Suite, tab **Setup**. Find the card **Connect Spotify**. If it already says connected, skip to step 3.
2. Follow its four numbered steps (developer dashboard, add the redirect address, paste the Client ID, press **Connect to Spotify**). You should see Spotify's approval page in your browser, then come back to the Suite with the card showing connected.
3. Find the card **PinguinoSuite device (Spotify Connect)**. Tick **use the PinguinoSuite device**.
4. In its output list pick **CABLE Input (VB-Audio Virtual Cable)**, then press **Start** (Restart if it was already running).
5. Wait. The status shows a short code. Press **Open spotify.com/pair**, enter the code, approve. The status should change to **ready**.
6. **Scope warning:** if instead you get a login *link* (no code), the card warns that this sign-in asks for wide Spotify permissions (email, birthdate, library and playlist changes). Only approve it on your own account. This is normal for the fallback sign-in.
7. In the Spotify app on your phone or PC, choose the device **PinguinoSuite** once. You hear nothing: the music goes into the cable. That is expected.
8. OBS: Sources, **+**, **Audio Output Capture**, name it "Music", device = **CABLE Output (VB-Audio Virtual Cable)**. You should see its meter move when a song plays.
9. OBS: Audio Mixer, gear on "Music", **Advanced Audio Properties**, Audio Monitoring = **Monitor and Output**. OBS Settings, Audio, Advanced, Monitoring Device = your headphones. Now you hear the song too.
10. Check OBS "Desktop Audio" is your speakers, not the cable (otherwise the song is doubled on stream).
Your own volume = Windows volume mixer for the headphones. The stream's volume = the OBS "Music" fader.

## 2. Voice (bot talking) routing
1. Voice page, card **Output**: **Play on** = **Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)**. (If Voicemeeter is not running, use "CABLE In 16ch".) Save.
2. Press **Routing check** (Output card). It plays nothing; you should see plain lines saying whether voice and music go to different places and whether "Play on" was found.
3. Press **Sound check** at the top of the page. It plays one line even with the master switch off. You should see a toast "Sound check played on: <device>".
4. OBS: **Audio Output Capture** named "Bot voice", device = **Voicemeeter Aux Output**; Audio Monitoring = **Monitor and Output**. Press Sound check again: you hear it in the headphones and the OBS meter moves.
5. Leave the Speak master switch OFF until you decide to test it (part 5 says how).

## 3. Link (two PCs and OBS)
1. Morning check: open the Link page (Modules, Link, or http://127.0.0.1:7777) and click **Run the morning check** in the card at the top. It only looks, it changes nothing. A good result: a green headline sentence on top and one line per check, each with a green tick (✔). A grey dot (•) is a note worth reading; a red ✘ with a red headline is a problem, and its line tells you the one thing to fix.
2. OBS password: in OBS, Tools, WebSocket Server Settings, enable it (port 4455) and read the password. In the Suite, Integrations, **Key vault**, add **OBS_WS_PASSWORD** and type it yourself. Press **Test**: it should say OK. Nobody else types this.
3. Real scene names: the macros use guessed names (scene `BRB`, scene `Main`, input `Mic/Aux`). On the Link page open **Edit macros** and use the names that really exist in OBS (or rename the scenes in OBS). The Check button must not say "missing: ...". These names live in the `obsNames` part of `Data\runtime\link\config.json`.
4. Pairing (only if you want the second PC): follow Docs\PinguinoLink\PAIRING_TEST.md part A (**Show a pairing code**, then **Pair** on the other PC, then **Allow**). You should see a green dot next to the other PC.
5. Update sharing: Link Settings has **Share update files with my paired PCs** and **Fetch update files from my paired PCs**. Only tick or untick them if you want that; nothing installs by itself, you always click Update in Lite.
6. Leave **Let paired devices start/stop my stream** and **Allow Start Stream** OFF.

## 4. Spotify manual tests (use your own account, no chat messages needed)
1. **Channel playlist:** Spotify page, Setup tab, **Channel playlist**: pick one of your playlists. You should see "Channel playlist saved". Then, from the site's mod page, use **Add to stream playlist** while a song plays; open the playlist in Spotify and the song is there.
2. **YouTube link:** setting **Accept YouTube links** is on by default. Send a request that is a YouTube link of a normal song, through the request path you normally use (a test request from the site, or a mod's `!sr <YouTube link>`; the Spotify page's Search box is for Spotify links). You should see the matching Spotify song queued (nothing plays from YouTube). A bad link should say song not found.
3. **Lyrics toggle:** setting **Show lyrics**. Open http://127.0.0.1:8771/overlay/lyrics (also usable as an OBS browser source) while a song plays: lines appear. Switch **Show lyrics** off (or use the mod lyrics button on the site): the overlay goes blank; on again: lines return.

## 5. What NOT to do
- **Do not go live in OBS to test anything here.** Everything above works with OBS open and the stream stopped.
- **Do not turn on Allow Start Stream** or "Let paired devices start/stop my stream". Stream-start stays blocked.
- Do not type the OBS or Spotify passwords anywhere except the OBS box, the Spotify page and the key vault.
- Do not turn the Speak master switch ON while live. For its one supervised test, do it with the stream stopped.
- Do not install anything from a link someone sends you; updates only come from your own paired PCs.
