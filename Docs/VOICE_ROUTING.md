# Speak (bot voice) routing: stream and headphones with separate volumes (2026-10-23, 50 - Tools)

Speak already plays on one named output: Voice page > Limits & queue > **Output > Play on** (`output.device`). Everything else is done in Windows and OBS. This PC already has what is needed: VB-Cable ("CABLE Input") and Voicemeeter (Voicemeeter Input, AUX Input, VAIO3 Input, In 1-5), all visible to Speak.

Plan: music -> VB-Cable (see Docs\SPOTIFY_CONNECT.md section 8); voice -> a Voicemeeter input, so the two get their own OBS faders and Listen's mic never hears either.

## Steps for Ivan
1. Voice page > Output > Play on = **Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)**. Save. (Any other Voicemeeter input works too, just not the one the music uses. If Voicemeeter is not running, use "CABLE In 16ch" instead; the music then stays on "CABLE Input".)
2. Press **Sound check** (top of the Voice page). It plays one line on that output even while the master switch is OFF, and shows the device it used. You will not hear it yet; that is expected.
3. OBS: Sources > + > **Audio Output Capture** > name "Bot voice" > Device = **Voicemeeter Aux Output** (the playback side of the input you picked; for CABLE In 16ch it is "CABLE Output"). Its fader is the stream's voice volume.
4. OBS: Audio Mixer > gear on "Bot voice" > Advanced Audio Properties > Audio Monitoring = **Monitor and Output**; Settings > Audio > Advanced > Monitoring Device = your headphones (same device as for the music).
5. Press Sound check again: now you hear it in the headphones and the OBS meter moves.
6. Your own level: Windows volume mixer for the headphones (or the Voicemeeter strip), the stream level: the OBS "Bot voice" fader, the bot's overall loudness: Voice page master volume (default 60 %).
7. Check that OBS "Desktop Audio" is your speakers and not a cable, or the voice is doubled on stream.

## Fallback without cables
Leave **Play on** empty: Speak plays on the Windows default device and OBS "Desktop Audio" carries it. You hear it directly; one shared volume. Listen's mic may pick it up (Speak publishes its speaking intervals so Listen can ignore those moments).

## Notes for the module (53 - Voice)
- `engine.find_device` matches a case-insensitive substring of the first device whose name matches; sounddevice lists every device three times (MME, DirectSound, WASAPI). MME names are cut at 31 characters, so "Voicemeeter AUX Input (VB-Audio" is what the dropdown shows. Prefer the WASAPI entry when several match (better latency, full name) and keep the dropdown names de-duplicated.
- If the device disappears Speak logs "output device ... not found, using the default" once per 5 min and keeps talking on the default.
- Nothing in Speak needs a second simultaneous output: OBS monitoring gives the headphones copy.
