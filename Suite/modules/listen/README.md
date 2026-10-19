# PinguinoBot Ears

Listen-only speech-to-text for the stream. It transcribes, flags what it's unsure about, and learns from your
corrections. It does NOT trigger anything in the bot (voice commands / "talk like me" come later and build on this).

Run: `run.bat` → http://127.0.0.1:8765   (faster-whisper large-v3-turbo on the GPU, falls back to CPU)

- **Live**: pick the mic, Start. Lines appear as you speak. Click a line to fix it (Enter saves).
- **Learn**: guided mode. Worst-sounding lines first, auto-plays the audio, Enter = right/save, Esc = skip.
- **VODs & Clips**: pulls your channel's VODs/clips (Twitch app creds from env, modules\listen\.env or D:\PinguinoSuite\PinguinoSite\.env),
  or add any URL / upload an audio or video file. "Auto-learn" queues new VODs/clips every 30 min.
- **Vocabulary**: words biasing Whisper + replacement rules learned from corrections (editable).

Colors: yellow = unsure, red = very unsure, green dashed = auto-fixed from what you taught it.
Thresholds: data/settings.json (`yellow` 0.75, `red` 0.45 word-confidence).

Data (all local, in `data/`): ears.db (transcripts, vocab, rules), audio/, gold.jsonl (verified audio+text pairs →
future Whisper fine-tune / voice-style data). Env: EARS_MODEL, EARS_LANG (`auto` to detect), EARS_PORT.
