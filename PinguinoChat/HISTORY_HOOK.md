# Long-term history: build + read hook

## Build it (Pipeline\build-summaries.mjs)
```
node Pipeline\build-summaries.mjs --dry-run      # plan + token estimate, sends nothing (full backfill today: ~247 daily, ~36 weekly, ~62 monthly batches, ~1.3M input tokens)
node Pipeline\build-summaries.mjs --limit 5      # a few calls first
node Pipeline\build-summaries.mjs                # everything that is missing (the first run is the big backfill; it can take a while, it is safe to stop and run again)
```
Output in `Data\history\`: `daily\<date>.json`, `weekly\<year>-W<nn>.json`, `monthly\<login>\<yyyy-MM>.json`, `INDEX.md`, `index.json`.
Runs are incremental: finished days/weeks/months are skipped; a day still growing (last 3 days) and the running month are redone when they grew. `--force` redoes everything selected. Keep it fresh by adding `node Pipeline\build-summaries.mjs` to the once-a-day rebuild in `update-logs.mjs` (not done yet: it costs AI calls, so you decide).

The AI is the same one the chat bot uses (`%AppData%\BVQ\chat_settings.json`: Provider, ApiKey, Model); default model for the claude provider is `claude-haiku-5-5`. The key is read at run time and never printed.

Privacy: viewers with `Privacy` = forget / anon in `chat_memory.json` get no monthly file and are called "someone" in everything; bots, !commands and heavy talk are never sent; every AI answer is filtered again (no ages, school, health, locations, contact details, politics, religion, sexuality, race).

## Read it from the bot (WIRED into PinguinoChat.cs on Oct 19; HistoryHook.cs.txt is the source of the pasted code)
`PinguinoChat\HistoryHook.cs.txt` has `HistoryDeepText(question, speaker, others, dir, todayCt)`; compile-checked as C# 7.3 with `Tests\history\run-hook-check.ps1` (10 checks). It returns up to 1,800 characters: the daily summary for a date / "yesterday" / "last stream", the weekly for "last week" / "this week", and the monthly highlights of the speaker and the people named, for a month name / "last month", or the latest two months when the question is about a person ("do you remember what I like?").

Wired: the code is inside `class CPHInline` of `PinguinoChat\PinguinoChat.cs`, the setting `HistoryDir` (default `D:\PinguinoSuite\Data\history`) points at the summaries, `BuildPrompt` adds a [LONG-TERM HISTORY] section (right after the [ABOUT ...] blocks; never for viewers who used !forgetme / !optmeout), and the system prompt has a LONG-TERM HISTORY rule. 5 chat tests cover it. Paste PinguinoChat.cs into Streamer.bot and compile to use it.
