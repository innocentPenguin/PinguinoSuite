# PinguinoChat setup

## 1. Get an API key
**Claude (default):** https://console.anthropic.com -> sign up -> Billing: add a few dollars of credit (prepaid, it stops when it runs out) -> API Keys -> Create Key. Copy it once; it starts with `sk-ant-`.
A chat reply is about 1-2k tokens in and ~60 out, so on Haiku it costs a fraction of a cent. `MaxCallsPerHour` (default 300) is the spending safety net.

**Swap to something else** by editing `%AppData%\BVQ\chat_settings.json` (reloads within 10 s, no recompile):

| Want | Provider | Model | BaseUrl |
|---|---|---|---|
| Claude | `claude` | blank = claude-haiku-5-5 | blank |
| OpenAI | `openai` | blank = gpt-4o-mini | blank |
| Groq / OpenRouter / Together | `custom` | their model name | their OpenAI-compatible URL |
| Free local (Ollama on this PC) | `custom` | e.g. `llama3.1` | `http://localhost:11434/v1` (ApiKey: any text) |

## 2. Streamer.bot
1. New action named `PinguinoChat` -> Sub-Action: Core > C# > Execute C# Code -> paste `PinguinoChat.cs` -> Compile.
2. Trigger: Twitch > Chat > Message. Leave it with NO command filter (it must see every message). Make sure the bot account is the one set up for sending (the code sends with useBot = true).
3. Run it once (or send any chat message while live). It writes `chat_settings.json`; paste your key into `ApiKey`.
4. Set `BotAccount` to the bot's exact Twitch login (default `pinguinob0t`) and check `Names`.

Replies are decided by the AI, not by timers: it can answer, stay silent, or go quiet for a viewer for 5-30 min when told to chill. Only a tiny anti-flood guard remains (3 s per viewer, 1 s global, more than 6 pings a minute = ignored for 2 min).

It only talks/remembers while the stream is live. That is read from `WasLive` in PinguinoBotCore's `settings.json`, so PinguinoBotCore has to be running. Set `LiveOnly` to false to test offline (it is ON now). While offline, if someone pings the bot it answers one short line (`OfflineReply`, with `OfflineLink` = https://innocentpenguin.com; at most once per viewer per `OfflineReplyEverySec` = 15 min and once a minute overall) and nothing else.

## 3. Commands (no Streamer.bot command setup needed; they are read from chat)
| Command | Who | What |
|---|---|---|
| `!memory` | viewer | whispers them what the bot remembers about them (never public) |
| `!forgetme` | viewer | wipes what the bot knows about them and stops it keeping details. Their chat is still logged and still counts for the community |
| `!rememberme` / `!remember me` | viewer | undoes either one going forward (lines already made anonymous stay anonymous) |
| `!chatbot on/off` | mod | kill switch |

Tip: also create normal Streamer.bot commands for `!memory`, `!forgetme`, `!rememberme` pointing at nothing, or just leave them: with no command defined, Streamer.bot still passes the message to this action.

## 4. Community logs + "getting to know everyone"
- Twitch has no chat history a bot can download afterwards, so PinguinoChat **records chat itself while you're live** into `%AppData%\BVQ\chat_logs\YYYY-MM-DD.jsonl` (kept 30 days).
- When a stream starts (first chat message after you go live, at most every 3 h) or when a mod types `!chatbot study`, it reads everything new, learns facts about the 40 most active chatters, and updates a short "what the community is like" note that goes into every reply. It never re-reads old lines. Cap: 10 AI calls per study.
- Have older logs? Drop them in `chat_logs\import` (TwitchDownloader chat JSON, or text lines like `[12:30] name: message` / `name: message`). They're read at the next study and moved to `import\done`.
- Privacy: see the two opt-outs above. In studies, opted-out chatters are read as one unnamed group, so their chat shapes the community picture but nobody gets a profile.
- Roles: mods, VIPs and bots come from https://innocentpenguin.com/api/roles (hourly). Bots listed there are ignored; the mod/VIP list is shown to the AI.

## 5. Files
`chat_memory.json` (memory, by Twitch user id, survives renames) and `chat_settings.json` live in `%AppData%\BVQ`. The bot only reads the PinguinoBotCore files.

## 6. Tests
`powershell -ExecutionPolicy Bypass -File D:\PinguinoSuite\Tests\chat\run-chat-tests.ps1` (fake AI, no cost, throwaway data folder).
