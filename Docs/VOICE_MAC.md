# Speak (bot voice) on a Mac: voices and routing (2026-10-23, 53 - Voice)

Same module, same page. On macOS Speak talks through the built-in `say` command instead of Windows SAPI, and plays through the Mac's audio output. The Voice page shows **Voices come from: macOS say** under the Voice picker. Nothing to install for the voice itself.

## 1. Voices
- Voices are the ones macOS has. Add more in **System Settings > Accessibility > Spoken Content > System Voice > Manage Voices** (download a Premium/Enhanced voice for the best sound), then press **Refresh** next to the Voice picker.
- A persona whose voice is a Windows name (for example "Microsoft David Desktop") is not found on the Mac: Speak then uses the Mac's system voice. Pick a Mac voice per persona on the Voice page.
- If the page says "No voice is available yet", download a voice as above.
- Speed (the persona's rate slider) maps to `say -r`. Pitch and whisper effects are applied by Speak after the voice is made, so they work the same as on Windows.

## 2. Routing with BlackHole (the Mac stand-in for Voicemeeter / VB-Cable)
Free virtual audio device: **BlackHole** (existential.audio/blackhole; or `brew install blackhole-2ch` / `blackhole-16ch`). Install it, restart the Mac when asked. Same idea as Docs\VOICE_ROUTING.md: music on one cable, the bot's voice on another, each with its own OBS fader.

1. Install **BlackHole 2ch** for the music and **BlackHole 16ch** for the voice (two different devices so the faders stay separate).
2. Voice page > Output > **Play on** = **BlackHole 16ch**. Save.
3. Press **Sound check**. It plays one line on that device even while the master switch is OFF. You will not hear it yet; that is expected.
4. OBS (Mac): Sources > + > **Audio Input Capture** > name "Bot voice" > Device = **BlackHole 16ch**. Its fader is the stream's voice volume. (Music: same with BlackHole 2ch, see Docs\SPOTIFY_CONNECT.md.)
5. To hear it yourself: OBS Audio Mixer > gear on "Bot voice" > Advanced Audio Properties > Audio Monitoring = **Monitor and Output**; OBS Settings > Audio > Advanced > Monitoring Device = your headphones.
6. Press Sound check again: you hear it in the headphones and the OBS meter moves.
7. Levels: your own = macOS output volume; the stream's = the OBS "Bot voice" fader; the bot's loudness = Voice page master volume.
8. Make sure OBS "Desktop Audio" is not also capturing BlackHole, or the voice is doubled on stream.

### Fallback without cables
Leave **Play on** empty (shows "System default"): Speak plays on the Mac's current output; OBS Desktop Audio (needs macOS 13+ in OBS) carries it. One shared volume, and Listen's mic may hear it (Speak publishes its speaking intervals so Listen can ignore those moments).

## 3. If something is wrong
- **No sound in Sound check:** the Output card lists the devices Speak sees. BlackHole missing means it was not installed or the Mac was not restarted. Speak falls back to the default output and logs "output device ... not found" once per 5 minutes.
- **"No audio output device was found":** nothing is enabled in System Settings > Sound > Output.
- **Mic permission:** Speak itself never uses the mic. Listen does and macOS asks once.

## Linux (bonus)
If `espeak-ng` is installed (`sudo apt install espeak-ng`), Speak uses it; the page says "Voices come from: espeak". Routing there is PulseAudio/PipeWire null sinks instead of BlackHole.

## For developers
Backends live in `Suite\modules\voice\engine.py` (`Sapi`, `MacSay`, `Espeak`, picked by `make_backend()` from `sys.platform`). The text is passed to `say` on stdin, never on the command line. Tests use a fake runner (`tests\test_backends.py`); nothing real is spoken. Untested on a real Mac so far: the first live check there should be Sound check, then one Preview.
