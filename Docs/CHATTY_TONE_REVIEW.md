# Chatty tone review: welcome, welcome-back, daily, anniversary, recap

Reviewed 2026-10-23 (late evening). **Limit of this review:** Chatty's own lines are not in `chat_logs` (bot accounts are not logged there) and the bot-send log (commit 973d733) only starts writing after the next Host restart. So this compares the fixed line pools in `PinguinoChat.cs` with how chat actually talks tonight (2,692 lines in `chat_logs/2026-10-23.jsonl`). Redo it from `Data\logs\bot-sends-*.log` after the restart to judge what really went out.

## How chat talks tonight
Short and loud: "PINGUUUUU haiii:>", "first", "Second", "back from ads wasduppp penngggg", emotes and a lot of lowercase. The Firsts game turns the first minutes into a race of one-word messages. Nobody writes in full sentences with a trailing "Glad you stopped by."

## Findings and proposals

1. **Welcome (new viewer, `WelcomeLines`, 4 lines).**
   - Too long (95-120 characters), all four open with "welcome" and end in the same 🐧, and three of them push a second ask (HelperPinguino / Minecraft / !discord). Only 4 variants repeat quickly on a busy night.
   - Proposal: shorter, 8 variants, one idea each, e.g. "hey {n}, welcome in! 🐧", "{n}! first time here? make yourself at home", "oh a new face, hi {n} 🐧 say anything, we don't bite", "welcome {n}! chat's friendly, ask away". Keep the !discord / Helper pointer for only 1 variant in 4.
   - A new viewer whose first message is a Firsts-race word ("first", "second", "1st", ...) should get no welcome: the Host's Firsts line already answers them and a welcome next to it is the third bot line in 2 seconds. (Check that `GreetBlocked` / the welcome path skips these: today it only skips links, spam phrases and spam logins.)
2. **Daily greeting (`DailyLines`, 7 lines).** Warm but uniform: "Chat is better with you in it" is a little sugary, "look who showed up" can read as "you are late", "there you are!" is fine. Proposal: drop those two, add shorter ones ("hey {n} 🐧", "{n} is back!", "o/ {n}", "good to see you, {n}"), and add a lowercase flavour to match chat.
3. **Welcome-back (Host people-graph lines, banded by days away).** Not reviewed here (Host side, 14's pool); only note: no line should mention the number of days for someone away less than a week.
4. **Anniversary line.** "it was N year(s) ago today that X first said hi here! Happy anniversary." reads well; the only risk is the casing of the name and "1 years" (checked: singular handled). Keep.
5. **Recap (`RecapLine`).** Always says "tonight" and "See you next stream." even for an afternoon stream, and sums subs + gifted subs as "N subs". Proposal (already sketched in `Docs/CHATTY_RECAP_WORDING.md`): pick the greeting by local hour ("tonight" only after 17:00, otherwise "today"), keep gifted subs separate ("3 subs, 5 gifted"), 3 wording variants, and say nothing about numbers when the stream was short (under 20 min) to avoid "0 follows" style lines.
6. **Everywhere:** the 🐧 emoji ends nearly every fixed line. One line in three without it would sound less like a template.

## Not proposed
No change to games lines, canned commands, or AI replies in this pass.

## Status (2026-10-24): APPLIED, Ivan said yes to all (needs the Host restart to load)
- 1 Welcome: 8 short variants (3 end in the penguin, one in four points to !discord); no welcome when the first message is a Firsts race word (first / 2nd / third! / #4 ...).
- 2 Daily: "better with you in it" and "look who showed up" dropped; short lines added ("{n} is back!", "o/ {n}", "good to see you, {n}", "hey {n} 🐧").
- 3 Welcome-back: untouched (Host pool, 14).  4 Anniversary: kept.
- 5 Recap: "today" before 17:00 local, "tonight" after; gifted subs listed apart ("5 gifted"); 3 wordings each way; streams under 20 min name no numbers.
- 6 Penguin endings: welcome and daily and recap pools now mix lines with and without it.
- RxHeat swearing change: kept. Tests: chat 406/406 (10 new), run four times because the variants are random.

