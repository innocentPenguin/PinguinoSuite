# Nightly run (owner: 00 coordinator)

Trigger: Ivan says "done for the night", or the scheduled time (when Ivan sets one). Engine work routes through 02 (PenguinHost) and its forks; site/pages through 05. Public docs and the chatbot never explain internals.

## Phase 1: Learn from today (every night)
- 02's Tools\nightly-review.py reads the day's chat logs (recorder, Chatty, helper review log): feedback, mistakes (wrong/doubled/unwanted replies, moderation misfires, failed commands), experience (what worked), unanswered commands and new in-jokes.
- Output: Docs\nightly\YYYY-MM-DD.md. New commands/lore are proposed through the Teach inbox (mod-added commands already live; the rest need Ivan's approval).

## Phase 2: Compile, check, debug, repeat (loop until clean, max 3 rounds)
1. COMPILE: pull everything; build all (core, app, Host, modules); run every test suite (Host, Link, Multi, Spotify, Voice, site).
2. QUALITY CHECK: every bot engine (Helper, Chatty, B0t, Host commands): run each command, replies short/thankful/not doubled, cooldowns, opt-outs (!unping, Marsh), no secrets in logs or git.
3. BUG HUNT + FIX: full code read of changed engines, fix, add tests.
4. Repeat 1-3 until a round finds nothing. Record rounds in Docs\nightly\YYYY-MM-DD.md.

## Phase 3: Engine reports (only what changed)
Each engine (Helper, Chatty, B0t, Host, Link, Multi, Spotify, Voice, Site) sends 00: what was UPDATED since last run, new capabilities, known issues, future plans. 00 collects into Docs\nightly\reports\YYYY-MM-DD.md.

## Phase 4: Update the pages (from the reports)
- Ivan: Docs\GUIDE_IVAN.md (advanced + friendly, full detail).
- 00: Docs\INTERNAL.md (super advanced, internal).
- Mods: simple page on the website + chatbot knowledge (05); only commands/how-to-use.
- Viewers: simple FAQ + chatbot knowledge (05); only commands/how-to-use.
- 05 pushes the site batch after 00 approves.

## Phase 5: Housekeeping
APP_LOG.md current, commands-doc + profiles re-pushed, site batch pushed, memory notes updated, summary to Ivan (what changed, what needs him).
