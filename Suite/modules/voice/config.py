# INDEX: Defaults + validation: PERSONAS/EVENTS tables, HELP (one line per setting), defaults(), normalize() (clamps everything incl. review/control sections), load/save/backups, presets (preset_*), built-in presets (_cozy/_hype/_deadpan/_chaos). Related: server.py, brain.py.
"""Pinguino Voice settings: defaults, one-line help for every setting, validation, presets, backups.

Everything is data: personas, event rules, role/platform overrides, limits, queue rules, quiet hours, pronunciation,
theme. `normalize()` accepts anything (an import, a hand edit, an old file) and returns a safe complete config.
The master switch ships OFF; while it is off nothing is ever spoken or played on the stream PC.
"""
import copy
import json
import os
import re
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
_lock = threading.Lock()


def data_dir():
    d = os.environ.get("PINGUINO_DATA_DIR")
    return (Path(d) / "voice") if d else ROOT / "data"


def path(name):
    p = data_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p / name


REVIEW_CHECKS = ["talk_over", "complaints", "pronounce", "repeats", "drops", "silent_master", "console", "control"]
COMPLAINTS = ["too loud", "shut up", "stop talking", "turn it down", "be quiet", "so annoying", "annoying", "stop that", "mute it", "mute the bot", "too much", "too quiet", "can't hear", "cant hear", "wrong", "stop it", "turn that off"]
PRAISE = ["love that", "love the voice", "that was funny", "that was good", "nice one", "good one", "perfect", "i like that", "so good", "haha the bot", "lol the bot"]
EVENTS = ["follow", "sub", "resub", "gift", "cheer", "raid", "redeem", "command", "chat", "voice_cmd", "stream_online", "stream_offline", "test"]
ROLES = ["broadcaster", "mod", "vip", "sub", "viewer"]
PLATFORMS = ["twitch", "youtube", "tiktok", "kick", "discord", "other"]
EFFECTS = ["echo", "reverb", "robot", "radio", "distortion", "tremolo"]
STINGERS = ["none", "ding", "bloop", "fanfare", "airhorn", "sparkle", "drumroll", "sad"]

# ------------------------------------------------------------------ one-line help for every setting (shown under each control)
HELP = {
    "master": "The big switch. OFF = completely silent and nothing is played, ever. Test buttons then only preview inside this page.",
    "mute_until": "Temporary mute: nothing is spoken until this time. Cleared by Unmute.",
    "engine": "Which voice engine speaks. 'sapi' = the Windows voices installed on this PC (free, offline).",
    "default_persona": "The persona used when an event or a person has no persona of their own.",
    "persona.name": "What this persona is called in the list and in {persona}.",
    "persona.emoji": "A little icon for the persona (cosmetic).",
    "persona.mood": "A label for the vibe (hype, calm, sassy...). Shown on the card; moods can have their own catchphrases.",
    "persona.voice": "Which Windows voice this persona uses. Install more in Windows Settings > Time & Language > Speech.",
    "persona.rate": "Speaking speed from -10 (slow) to +10 (fast).",
    "persona.pitch": "Pitch in semitones, -12 (deep) to +12 (squeaky). Applied after speaking, so it works with every voice.",
    "persona.volume": "How loud this persona is, 0-100 (on top of the master volume).",
    "persona.effects": "Sound effects mixed in, each 0-100: echo, reverb, robot, radio, distortion, tremolo. 0 = off.",
    "persona.catchphrases": "Signature lines, one per row. Use {catch} in a template to say one at random.",
    "persona.catch_chance": "How often a catchphrase is added when the template has no {catch}, 0-100 %.",
    "persona.intro": "Said before every announcement by this persona (leave empty for none).",
    "persona.outro": "Said after every announcement by this persona (leave empty for none).",
    "persona.stinger": "A short sound played before the voice speaks.",
    "persona.templates": "Wording this persona uses per event. Falls back to the event's own wording when empty.",
    "event.enabled": "Whether this kind of event is announced at all.",
    "event.persona": "Which persona announces this event ('default' = the default persona).",
    "event.templates": "What gets said, one variant per row, picked at random. Variables: {user} {amount} {tier} {viewers} {bits} {what} {message} {persona} {catch} {time}. Add 'min:N|' in front of a row to use it only from amount N up.",
    "event.min_amount": "Ignore the event below this amount (bits, viewers, gifted subs...). 0 = announce all.",
    "event.cooldown_s": "Minimum seconds between two announcements of this kind (stops spam in a raid or gift storm).",
    "event.priority": "1-9. Higher goes first in the queue and can interrupt lower ones.",
    "event.read_message": "Also read the viewer's own message (cheers, resub messages, redeems), after limits and profanity rules.",
    "event.stinger": "Sound before this event's announcement (overrides the persona's).",
    "event.only_live": "Only announce while the stream is live.",
    "roles": "Choose a persona per role. A moderator's !tts could sound different from a viewer's.",
    "platforms": "Choose a persona per chat platform so Twitch and YouTube viewers hear different voices.",
    "users": "Persona for specific people (by name). Highest priority after the event itself.",
    "limits.max_chars": "Longest text that will be spoken. Longer text is cut (or skipped, see below).",
    "limits.too_long": "What to do with text over the limit: 'cut' it short or 'skip' it.",
    "limits.rate_per_min": "At most this many announcements per minute across everything (0 = no limit).",
    "limits.user_cooldown_s": "Seconds a single person must wait between their own spoken messages.",
    "limits.profanity": "'mask' says 'beep' instead of the word, 'skip' drops the whole line, 'off' leaves it alone.",
    "limits.bad_words": "Your own words to treat as profanity, one per row (added to the built-in short list).",
    "limits.block_links": "Never read web links aloud (they become 'a link').",
    "limits.strip_emoji": "Remove emoji and odd symbols before speaking.",
    "limits.max_repeat": "Squash repeated letters/words (aaaaaa, spam spam spam) to this many. 0 = off.",
    "limits.blocked_users": "People whose text is never spoken. Their events (like a follow) can still be announced by name.",
    "limits.clean_names": "Read 'xX_ivan_Xx99' as 'ivan' (strip numbers/underscores/decoration).",
    "queue.mode": "'queue' = wait your turn, 'interrupt' = a higher priority cuts the current line, 'drop_new' = ignore new ones while speaking.",
    "queue.max_queue": "How many can wait. Extra ones are dropped (lowest priority first).",
    "queue.max_age_s": "Drop a waiting line that is older than this - a late 'thanks for the follow' sounds odd.",
    "queue.gap_ms": "Pause between two lines.",
    "queue.interrupt_min_priority": "Only a line with at least this priority may interrupt the current one.",
    "queue.merge_similar": "Merge a burst of the same event (5 follows in 10 s) into one line: 'thanks to A, B and 3 more'.",
    "quiet.enabled": "Quiet hours: a daily window when the voice stays down.",
    "quiet.start": "Quiet hours start (24 h, e.g. 23:00).",
    "quiet.end": "Quiet hours end (e.g. 07:00). May pass midnight.",
    "quiet.mode": "'mute' = silent, 'whisper' = still speak, but quiet (volume 25%).",
    "output.volume": "Master volume for everything Pinguino Voice plays, 0-100.",
    "output.normalize": "Even out loudness between voices and stingers.",
    "pronounce": "Say a word your way: 'Ivan' -> 'eye van'. One rule per row, left = written, right = spoken. Whole words only.",
    "theme.accent": "The accent colour of this page.",
    "theme.mode": "Dark or light look for this page.",
    "history.keep": "How many spoken lines to remember for the history list and 'say it again'.",
    "persona.engine": "Which engine speaks this persona: 'sapi' (Windows, offline), 'openai' or 'elevenlabs' (cloud, needs the switch under Cloud voices and a key in the vault).",
    "persona.cloud_voice": "The cloud voice: OpenAI name (alloy, ash, coral, echo, fable, nova, onyx, sage, shimmer) or an ElevenLabs voice id.",
    "persona.style": "OpenAI only: how to act, e.g. 'an excited pirate captain, loud and cheerful'. Gives the voice real attitude.",
    "cloud.allow": "Master permission for cloud voices. OFF = no text ever leaves this PC. ON = the (already cleaned, secret-free) sentence is sent to the engine you chose for that persona.",
    "cloud.fallback": "If a cloud voice fails (no key, offline, error) speak with the Windows voice instead of staying silent.",
    "cloud.openai_model": "OpenAI speech model. gpt-4o-mini-tts understands 'style'; tts-1 is cheaper.",
    "cloud.elevenlabs_model": "ElevenLabs model, e.g. eleven_turbo_v2_5 (fast) or eleven_multilingual_v2 (richer).",
    "cloud.stability": "ElevenLabs stability 0-100: low = expressive, high = steady.",
    "soundcheck": "Plays one short line on the real output so you can hear the volume and the device. Works even while the master switch is OFF, but only from this button.",
    "output.device": "Which speakers/virtual cable to play on. Empty = the Windows default. Type part of a device name (e.g. 'CABLE' or 'Voicemeeter').",
    "limits.dedupe_s": "Don't say the same text twice within this many seconds (stops chat copy-paste spam). 0 = off.",
    "nicknames": "How to say a person's name: 'xxdragon99' -> 'Dragon'. One per row, left = their name, right = how it is said.",
    "timers": "Spoken reminders on a schedule (hydrate, follow, socials). Each picks a persona and a random line, only while the master switch is on.",
    "timer.every_min": "Minutes between announcements.",
    "timer.jitter_pct": "Randomise the gap by up to this % so it never sounds like a clock.",
    "timer.lines": "What it says, one variant per row (random). {catch} and {time} work.",
    "timer.min_chat": "Only fires when at least this many events/lines were handled since the last one (0 = always).",
    "persona.stinger": "A short sound played before the voice speaks. Pick a built-in one or one of your own WAV files (Words > Sounds).",
    "time_rules": "Switch the default persona by time of day (e.g. Sleepy Seal after 22:00). Events and people with their own persona still win.",
    "time_rule.from": "Start time (24 h). The rule covers from here until 'until', passing midnight if needed.",
    "milestones": "Celebrate counts: every 10th follower, every 100 bits, every 5th raid. Counted all day even when silent.",
    "milestone.every": "Fires each time the count passes a multiple of this number.",
    "milestone.count_by": "'events' counts each follow/sub/raid; 'amount' adds up bits or viewers.",
    "milestone.scope": "'day' starts again at midnight, 'forever' never resets (until you press Reset counters).",
    "milestone.lines": "What it says, one per row. Variables: {count} {every} {event} {catch} {time}.",
    "sounds": "Your own WAV sounds (max 2 MB each, kept in the Speak data folder). Use them as a persona's or an event's sound.",
    "tts.enabled": "Lets people type !tts <text> in chat to have it spoken (the Host runs the command; set it up on Actions & Events). Off by default.",
    "tts.min_role": "Lowest role allowed to use !tts: viewer, sub, vip, mod or broadcaster.",
    "listen.confirm_commands": "When a voice command is heard and fires, say a tiny confirmation. Voice commands stay silent in chat either way.",
    "review.enabled": "Every hour of stream, compare what the bot said with what you said, what chat said and what the logs recorded, and write a report (Review tab). Local only; it never speaks.",
    "review.interval_min": "Minutes between reviews while the stream is live (a closing review also runs when the stream ends).",
    "review.only_when_live": "Only review while Twitch says you are live. Off = review on the clock all day.",
    "review.final_review": "Run one more review when the stream ends, covering the last stretch.",
    "review.keep": "How many reports to keep.",
    "review.use_transcript": "Read your live transcript from Listen (needs Listen running).",
    "review.use_chat": "Read today's chat log.",
    "review.use_console": "Read warnings and errors from the Console logs.",
    "review.talk_over_max": "Flag the hour when the bot talked over you at least this many times.",
    "review.repeat_max": "Flag a line the bot said at least this many times in the window.",
    "review.complaint_window_s": "A complaint counts when you say it within this many seconds after the bot spoke.",
    "review.complaint_phrases": "Words that mean the voice annoyed you or chat (one per line).",
    "review.praise_phrases": "Words that mean the voice went well (one per line).",
    "review.checks": "Switch individual checks on or off.",
    "control.enabled": "Spoken control: say 'pinguinobot change the game to ...', 'change the title to ...', 'timeout <name> for 5 minutes'. OFF by default; only you switch it on. It never changes with presets.",
    "control.wake_words": "What you say first. Close spellings from the transcript are accepted ('pinguino bot').",
    "control.require_confirm": "Ask back first ('I heard ... say pinguinobot confirm') or press Confirm on the page. Strongly recommended.",
    "control.expire_s": "Seconds you have to confirm before the request is forgotten.",
    "control.cooldown_s": "Minimum seconds between two actions of the same kind.",
    "control.max_unsure": "Ignore a line Listen is not sure it heard right (0 = sure, 1 = guess).",
    "control.readback": "Say the readback and result aloud (only when the master switch is ON; the page always shows them).",
    "control.title_case": "Capitalise each word of a spoken game/title.",
    "control.max_timeout_s": "The longest timeout the voice may give, in seconds.",
    "control.protected": "People who can never be timed out by voice (the broadcaster and mods are also refused by the Host).",
    "control.allow": "Which actions the voice may do at all.",
    "listen.confirm_text": "What to say when a voice command fired. {command} is its name.",
}

STATUS_HELP = {
    "master_off": {"title": "Pinguino Voice is switched off", "summary": "This is the normal, safe state: nothing is spoken or played. Previews inside this page still work.",
                   "steps": ["Open the Voice page and pick the persona you like with the Preview buttons (these play inside the page only).",
                             "When ready, flip the big master switch to ON. The first test line goes to your normal Windows output.",
                             "Use Panic stop any time to silence the queue immediately."], "fix": {"label": "Open Voice", "route": "m:voice"}},
    "engine": {"title": "Voice engine", "summary": "The Windows speech engine that turns words into audio.",
               "steps": ["Needs Windows 10/11 with at least one installed voice (David and Zira come with Windows).",
                         "If it fails, open Windows Settings > Time & Language > Speech and add a voice.",
                         "Press Test engine on the Voice page; the result shows the voices found."], "fix": {"label": "Open Voice", "route": "m:voice"}},
    "events": {"title": "Event feed", "summary": "Where follows, subs, raids and cheers come from: the Host's Activity feed.",
               "steps": ["The Host module must be running (Bots / Host page).", "Sign the streamer in on the Host so Twitch events arrive.",
                         "Nothing arrives from here when the Host is down; typed !tts and test events still work."], "fix": {"label": "Open Host", "route": "m:host"}},
    "queue": {"title": "Speech queue", "summary": "Lines waiting to be spoken. Too many waiting means the stream is busy or limits are too loose.",
              "steps": ["Raise the rate limit and merge similar events in Limits & Queue.", "Panic stop empties the queue."], "fix": {"label": "Open Voice", "route": "m:voice"}},
    "quiet": {"title": "Quiet hours", "summary": "Voice is intentionally muted or whispering because of the daily quiet window or a temporary mute.",
              "steps": ["Change the window in Limits & Queue > Quiet hours.", "Press Unmute to cancel a temporary mute."], "fix": {"label": "Open Voice", "route": "m:voice"}},
    "cloud": {"title": "Cloud voices", "summary": "Optional realistic voices from OpenAI or ElevenLabs. Off by default: no text leaves this PC until you allow it.",
              "steps": ["Open Speak > Personas and set a persona's engine to openai or elevenlabs, with a cloud voice.",
                        "Add the key in Integrations > Key vault: VOICE_OPENAI_KEY or VOICE_ELEVENLABS_KEY, then press Test.",
                        "Turn on 'Allow cloud voices' in Speak > Limits & queue > Cloud voices.",
                        "Only the finished sentence (secrets already removed) is sent. If the cloud fails, the Windows voice speaks instead (can be turned off)."],
              "link": {"label": "OpenAI API keys", "url": "https://platform.openai.com/api-keys"}, "fix": {"label": "Enter the key", "route": "integrations", "focus": "VOICE_OPENAI_KEY"}},
    "voice-output": {"title": "Which voice and where it plays", "summary": "Shows the default persona's voice and the speakers it will use.",
                     "steps": ["Open PenguinComm > Speak > Limits & queue > Output and pick the device (empty = Windows default speakers).", "Press Sound check in the page header: you should hear one line.",
                               "If the device says 'not found', it is unplugged or renamed: pick it again.", "Keep the bot voice OFF your microphone: use headphones or a separate output so Listen does not hear it."],
                     "fix": {"label": "Open Speak", "route": "m:voice"}},
    "voice-loop": {"title": "Bot voice and the microphone", "summary": "Listen hears whatever your mic hears. If the bot speaks through speakers next to the mic, Listen transcribes the bot.",
                   "steps": ["Best: play the bot on headphones or on a different output device than your monitors (Speak > Limits & queue > Output).", "Speak publishes when it is talking: GET :8772/api/speech-intervals and the file Data\\runtime\\voice\\speaking.json, so Listen can ignore those moments.", "Voice commands are never answered in chat, so a loop cannot trigger bot replies; it can only add bot lines to the transcript."],
                   "fix": {"label": "Open Speak", "route": "m:voice"}},
    "_module": {"title": "PenguinComm Speak (Pinguino Voice)", "summary": "The bot's speaking voice (PenguinComm > Speak; Listen is the other half, it hears you). A talking co-host: named voice personas with catchphrases announce follows, subs, raids, cheers and chat commands. Silent unless you switch it on.",
                "steps": ["Open Voice. The master switch is OFF: nothing is spoken.", "Personas tab: tweak a persona (voice, speed, pitch, effects) and press Preview.",
                         "Events tab: choose who announces each event and what they say.", "Limits & Queue: set profanity, length and rate limits, quiet hours.",
                         "Presets: save your whole setup, restore it, share or import one.", "Flip the master switch ON when happy. Panic stop silences everything."],
                "fix": {"label": "Open Voice", "route": "m:voice"}},
}


def persona(name, emoji, mood, voice, rate, pitch, volume, effects, catch, chance, stinger="none", intro="", outro="", templates=None, style=""):
    return {"engine": "sapi", "cloud_voice": "", "style": style, "name": name, "emoji": emoji, "mood": mood, "voice": voice, "rate": rate, "pitch": pitch, "volume": volume,
            "effects": {k: effects.get(k, 0) for k in EFFECTS}, "catchphrases": catch, "catch_chance": chance,
            "stinger": stinger, "intro": intro, "outro": outro, "templates": templates or {}}


DEFAULT_PERSONAS = {
    "captain": persona("Captain Penguin", "🐧", "proud", "Microsoft David Desktop", -1, -2, 90, {"reverb": 18}, ["Waddle on!", "All hands on deck!", "The ice holds, crew."], 25, "ding",
                       templates={"follow": ["Ahoy {user}! Welcome aboard the ship.", "{user} joins the crew. {catch}"],
                                  "raid": ["Incoming fleet! {user} raids us with {viewers} sailors. {catch}"],
                                  "sub": ["{user} signs up for the long voyage. {catch}"]}),
    "robot": persona("Pingu-Bot 3000", "🤖", "deadpan", "Microsoft Zira Desktop", 0, -3, 85, {"robot": 70, "radio": 20}, ["Beep boop.", "Computing joy.", "Affirmative."], 30, "bloop",
                     templates={"follow": ["New follower detected. Designation: {user}.", "Hello {user}. Welcome. Please enjoy the stream."],
                                "cheer": ["{amount} bits received from {user}. Gratitude module engaged."]}),
    "hype": persona("Hype Penguin", "🔥", "hype", "Microsoft Zira Desktop", 3, 4, 100, {"echo": 20}, ["LET'S GOOO!", "Absolute scenes!", "Chat, we are so back!"], 40, "airhorn",
                    templates={"follow": ["Oh YES! {user} just followed! {catch}", "{user} is here! Welcome! {catch}"],
                               "raid": ["RAID INCOMING! {user} brings {viewers} legends! {catch}"],
                               "cheer": ["{user} drops {amount} bits! {catch}"],
                               "gift": ["{user} gifts {amount} subs! Unreal! {catch}"]}),
    "professor": persona("Professor Flipper", "🎓", "curious", "Microsoft David Desktop", -3, -1, 85, {}, ["Fascinating.", "Most illuminating.", "Quite so."], 30, "none",
                         templates={"follow": ["Ah, {user}. A new subject joins the study. {catch}"], "raid": ["A migration of {viewers}, led by {user}. {catch}"]}),
    "radio": persona("Radio Iceberg", "📻", "smooth", "Microsoft David Desktop", 0, -1, 90, {"radio": 85, "echo": 10}, ["You're listening to Radio Iceberg.", "Stay frosty."], 35, "sparkle",
                     intro="", outro="", templates={"follow": ["This just in: {user} has followed the channel."], "raid": ["Breaking news. {user} arrives with {viewers} listeners."]}),
    "sleepy": persona("Sleepy Seal", "😴", "calm", "Microsoft Zira Desktop", -5, -4, 60, {"reverb": 30}, ["Mmm... cozy.", "Nap time soon."], 30, "none",
                      templates={"follow": ["Oh... hi {user}. Welcome. Get comfy."], "raid": ["{user} is here with {viewers} friends. How cozy."]}),
    "narrator": persona("The Narrator", "📖", "dramatic", "Microsoft David Desktop", -2, -5, 95, {"reverb": 45, "echo": 15}, ["And so it was written.", "Thus the tale continues."], 40, "drumroll",
                        templates={"follow": ["And lo, {user} arrived at the stream.", "{user} stepped into the story."], "raid": ["From the horizon came {user}, leading {viewers} souls."],
                                   "sub": ["{user} pledged their loyalty. {catch}"]}),
}

DEFAULT_EVENT_TEMPLATES = {
    "follow": ["Thanks for the follow {user}!", "Welcome {user}, glad you are here."],
    "sub": ["{user} just subscribed. Thank you!", "min:2|{user} subscribed at tier {tier}. Wow, thank you!"],
    "resub": ["{user} is back for {amount} months. Thank you!", "{user} resubscribed. {catch}"],
    "gift": ["{user} gifted {amount} subs. Thank you!", "min:10|{user} gifted {amount} subs. That is huge!"],
    "cheer": ["{user} cheered {amount} bits. Thank you!", "min:1000|{user} cheered {amount} bits. Incredible!"],
    "raid": ["{user} is raiding with {viewers} viewers. Welcome raiders!", "min:50|Big raid! {viewers} viewers from {user}. Welcome everyone!"],
    "redeem": ["{user} redeemed {what}."],
    "command": ["{message}"],
    "chat": ["{user} says {message}"],
    "voice_cmd": ["Done: {what}."],
    "stream_online": ["We are live. Let's go!"],
    "stream_offline": ["Stream is over. Thanks for hanging out."],
    "test": ["This is a test of the {persona} voice. {catch}"],
}
EVENT_DEFAULTS = {
    "follow": dict(enabled=True, priority=3, cooldown_s=4, min_amount=0, read_message=False),
    "sub": dict(enabled=True, priority=6, cooldown_s=0, min_amount=0, read_message=True),
    "resub": dict(enabled=True, priority=6, cooldown_s=0, min_amount=0, read_message=True),
    "gift": dict(enabled=True, priority=7, cooldown_s=0, min_amount=1, read_message=False),
    "cheer": dict(enabled=True, priority=6, cooldown_s=2, min_amount=100, read_message=True),
    "raid": dict(enabled=True, priority=9, cooldown_s=0, min_amount=5, read_message=False),
    "redeem": dict(enabled=False, priority=4, cooldown_s=2, min_amount=0, read_message=True),
    "command": dict(enabled=False, priority=4, cooldown_s=2, min_amount=0, read_message=True),
    "chat": dict(enabled=False, priority=2, cooldown_s=3, min_amount=0, read_message=True),
    "voice_cmd": dict(enabled=False, priority=2, cooldown_s=3, min_amount=0, read_message=False),
    "stream_online": dict(enabled=False, priority=5, cooldown_s=60, min_amount=0, read_message=False),
    "stream_offline": dict(enabled=False, priority=5, cooldown_s=60, min_amount=0, read_message=False),
    "test": dict(enabled=True, priority=5, cooldown_s=0, min_amount=0, read_message=False),
}

BAD_WORDS = ["fuck", "shit", "bitch", "asshole", "cunt", "dick", "nigger", "nigga", "faggot", "retard", "whore", "slut"]


def defaults():
    ev = {}
    for k in EVENTS:
        ev[k] = {**EVENT_DEFAULTS[k], "persona": "default", "templates": list(DEFAULT_EVENT_TEMPLATES[k]), "stinger": "", "only_live": k in ("chat", "command")}
    return {
        "version": 1,
        "master": False,
        "mute_until": 0,
        "engine": "sapi",
        "default_persona": "captain",
        "personas": copy.deepcopy(DEFAULT_PERSONAS),
        "events": ev,
        "roles": {r: "" for r in ROLES},
        "platforms": {p: "" for p in PLATFORMS},
        "users": {},
        "nicknames": {},
        "time_rules": [],
        "milestones": [],
        "cloud": {"allow": False, "fallback": True, "openai_model": "gpt-4o-mini-tts", "elevenlabs_model": "eleven_turbo_v2_5", "stability": 50},
        "timers": [],
        "limits": {"max_chars": 160, "too_long": "cut", "rate_per_min": 12, "user_cooldown_s": 20, "profanity": "mask", "bad_words": [], "block_links": True,
                   "strip_emoji": True, "max_repeat": 3, "blocked_users": [], "clean_names": True, "dedupe_s": 20},
        "queue": {"mode": "queue", "max_queue": 8, "max_age_s": 45, "gap_ms": 350, "interrupt_min_priority": 8, "merge_similar": True},
        "quiet": {"enabled": False, "start": "23:00", "end": "07:00", "mode": "mute"},
        "output": {"volume": 60, "normalize": True, "device": ""},
        "pronounce": {"innocentpenguin": "innocent penguin", "pinguino": "ping win o"},
        "theme": {"accent": "#ff8a1f", "mode": "dark"},
        "history": {"keep": 50},
        "tts": {"enabled": False, "min_role": "mod"},
        "listen": {"confirm_commands": False, "confirm_text": "Done."},
        "review": {"enabled": True, "interval_min": 60, "only_when_live": True, "final_review": True, "keep": 48, "use_transcript": True, "use_chat": True, "use_console": True,
                   "talk_over_max": 3, "repeat_max": 3, "complaint_window_s": 45, "checks": {k: True for k in REVIEW_CHECKS},
                   "complaint_phrases": list(COMPLAINTS), "praise_phrases": list(PRAISE)},
        "control": {"enabled": False, "wake_words": ["pinguinobot", "pinguino bot", "penguino bot", "penguin bot"], "require_confirm": True, "expire_s": 25, "cooldown_s": 5,
                    "max_unsure": 0.6, "readback": True, "title_case": True, "max_timeout_s": 600, "protected": [],
                    "allow": {"game": True, "title": True, "timeout": True}},
    }


def _sting(v, blank):
    v = _s(v, 80)
    if v in STINGERS:
        return v
    if re.fullmatch(r"file:[\w .()-]{1,60}\.wav", v, re.I):
        return v
    return blank


def _clip(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _i(v, lo, hi, default):
    return int(_clip(v, lo, hi, default))


def _s(v, n=200):
    return str(v if v is not None else "").replace("\x00", "").strip()[:n]


def _list(v, n=40, w=200):
    if isinstance(v, str):
        v = v.splitlines()
    return [_s(x, w) for x in (v if isinstance(v, list) else []) if _s(x, w)][:n]


def _hhmm(v, d):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", _s(v, 5))
    return f"{int(m.group(1)) % 24:02d}:{int(m.group(2)) % 60:02d}" if m else d


def _color(v, d):
    return v if re.fullmatch(r"#[0-9a-fA-F]{6}", _s(v, 7)) else d


def _pid(v):
    return re.sub(r"[^a-z0-9_-]", "", _s(v, 30).lower().replace(" ", "-"))[:30]


def normalize_persona(p, base=None):
    b = base or DEFAULT_PERSONAS["captain"]
    p = p if isinstance(p, dict) else {}
    eff = p.get("effects") if isinstance(p.get("effects"), dict) else {}
    tpl = p.get("templates") if isinstance(p.get("templates"), dict) else {}
    return {
        "name": _s(p.get("name", b["name"]), 40) or "Unnamed", "emoji": _s(p.get("emoji", b["emoji"]), 8), "mood": _s(p.get("mood", b["mood"]), 24),
        "voice": _s(p.get("voice", b["voice"]), 80), "rate": _i(p.get("rate", b["rate"]), -10, 10, 0), "pitch": _i(p.get("pitch", b["pitch"]), -12, 12, 0),
        "volume": _i(p.get("volume", b["volume"]), 0, 100, 90),
        "effects": {k: _i(eff.get(k, b["effects"].get(k, 0)), 0, 100, 0) for k in EFFECTS},
        "catchphrases": _list(p.get("catchphrases", b["catchphrases"]), 30, 100), "catch_chance": _i(p.get("catch_chance", b["catch_chance"]), 0, 100, 0),
        "engine": p.get("engine") if p.get("engine") in ("sapi", "openai", "elevenlabs") else "sapi", "cloud_voice": _s(p.get("cloud_voice", ""), 80), "style": _s(p.get("style", ""), 200),
        "stinger": _sting(p.get("stinger"), "none"), "intro": _s(p.get("intro", ""), 100), "outro": _s(p.get("outro", ""), 100),
        "templates": {k: _list(v, 20, 240) for k, v in tpl.items() if k in EVENTS},
    }


def normalize(raw):
    d = defaults()
    raw = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(d)
    out["master"] = bool(raw.get("master", False))
    out["mute_until"] = _clip(raw.get("mute_until", 0), 0, 4e9, 0)
    out["engine"] = "sapi"
    ps = raw.get("personas")
    if isinstance(ps, dict) and ps:
        out["personas"] = {}
        for k, v in list(ps.items())[:40]:
            if _pid(k):
                out["personas"][_pid(k)] = normalize_persona(v, DEFAULT_PERSONAS.get(_pid(k)))
    if not out["personas"]:
        out["personas"] = copy.deepcopy(DEFAULT_PERSONAS)
    dp = _pid(raw.get("default_persona", d["default_persona"]))
    out["default_persona"] = dp if dp in out["personas"] else next(iter(out["personas"]))
    revs = raw.get("events") if isinstance(raw.get("events"), dict) else {}
    for k in EVENTS:
        e, r = out["events"][k], revs.get(k) if isinstance(revs.get(k), dict) else {}
        e["enabled"] = bool(r.get("enabled", e["enabled"]))
        pe = _pid(r.get("persona", "default")) if r.get("persona") else "default"
        e["persona"] = pe if pe in out["personas"] else "default"
        e["templates"] = _list(r.get("templates", e["templates"]), 30, 240) or list(DEFAULT_EVENT_TEMPLATES[k])
        e["min_amount"] = _i(r.get("min_amount", e["min_amount"]), 0, 10**7, 0)
        e["cooldown_s"] = _i(r.get("cooldown_s", e["cooldown_s"]), 0, 3600, 0)
        e["priority"] = _i(r.get("priority", e["priority"]), 1, 9, 5)
        e["read_message"] = bool(r.get("read_message", e["read_message"]))
        e["only_live"] = bool(r.get("only_live", e["only_live"]))
        e["stinger"] = _sting(r.get("stinger"), "")
    for sec, keys in (("roles", ROLES), ("platforms", PLATFORMS)):
        src = raw.get(sec) if isinstance(raw.get(sec), dict) else {}
        for k in keys:
            v = _pid(src.get(k, ""))
            out[sec][k] = v if v in out["personas"] else ""
    out["users"] = {}
    if isinstance(raw.get("users"), dict):
        for k, v in list(raw["users"].items())[:200]:
            if _s(k, 40) and _pid(v) in out["personas"]:
                out["users"][_s(k, 40).lower()] = _pid(v)
    L, rl = out["limits"], raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
    L["max_chars"] = _i(rl.get("max_chars", L["max_chars"]), 10, 1000, 160)
    L["too_long"] = rl.get("too_long") if rl.get("too_long") in ("cut", "skip") else "cut"
    L["rate_per_min"] = _i(rl.get("rate_per_min", L["rate_per_min"]), 0, 120, 12)
    L["user_cooldown_s"] = _i(rl.get("user_cooldown_s", L["user_cooldown_s"]), 0, 3600, 20)
    L["profanity"] = rl.get("profanity") if rl.get("profanity") in ("off", "mask", "skip") else "mask"
    L["bad_words"] = [w.lower() for w in _list(rl.get("bad_words", []), 200, 40)]
    L["block_links"] = bool(rl.get("block_links", True))
    L["strip_emoji"] = bool(rl.get("strip_emoji", True))
    L["max_repeat"] = _i(rl.get("max_repeat", L["max_repeat"]), 0, 20, 3)
    L["blocked_users"] = [w.lower() for w in _list(rl.get("blocked_users", []), 500, 40)]
    L["clean_names"] = bool(rl.get("clean_names", True))
    L["dedupe_s"] = _i(rl.get("dedupe_s", L["dedupe_s"]), 0, 3600, 20)
    Q, rq = out["queue"], raw.get("queue") if isinstance(raw.get("queue"), dict) else {}
    Q["mode"] = rq.get("mode") if rq.get("mode") in ("queue", "interrupt", "drop_new") else "queue"
    Q["max_queue"] = _i(rq.get("max_queue", Q["max_queue"]), 1, 100, 8)
    Q["max_age_s"] = _i(rq.get("max_age_s", Q["max_age_s"]), 3, 3600, 45)
    Q["gap_ms"] = _i(rq.get("gap_ms", Q["gap_ms"]), 0, 5000, 350)
    Q["interrupt_min_priority"] = _i(rq.get("interrupt_min_priority", Q["interrupt_min_priority"]), 1, 9, 8)
    Q["merge_similar"] = bool(rq.get("merge_similar", True))
    z, rz = out["quiet"], raw.get("quiet") if isinstance(raw.get("quiet"), dict) else {}
    z["enabled"] = bool(rz.get("enabled", False))
    z["start"], z["end"] = _hhmm(rz.get("start"), "23:00"), _hhmm(rz.get("end"), "07:00")
    z["mode"] = rz.get("mode") if rz.get("mode") in ("mute", "whisper") else "mute"
    o, ro = out["output"], raw.get("output") if isinstance(raw.get("output"), dict) else {}
    o["volume"] = _i(ro.get("volume", o["volume"]), 0, 100, 60)
    o["normalize"] = bool(ro.get("normalize", True))
    o["device"] = _s(ro.get("device", ""), 80)
    rc = raw.get("cloud") if isinstance(raw.get("cloud"), dict) else {}
    out["cloud"] = {"allow": bool(rc.get("allow", False)), "fallback": bool(rc.get("fallback", True)), "openai_model": _s(rc.get("openai_model", "gpt-4o-mini-tts"), 40) or "gpt-4o-mini-tts",
                    "elevenlabs_model": _s(rc.get("elevenlabs_model", "eleven_turbo_v2_5"), 40) or "eleven_turbo_v2_5", "stability": _i(rc.get("stability", 50), 0, 100, 50)}
    if isinstance(raw.get("nicknames"), dict):
        out["nicknames"] = {_s(k, 40).lower(): _s(v, 40) for k, v in list(raw["nicknames"].items())[:300] if _s(k, 40) and _s(v, 40)}
    out["time_rules"] = []
    for i, t in enumerate((raw.get("time_rules") if isinstance(raw.get("time_rules"), list) else [])[:20]):
        if isinstance(t, dict) and _pid(t.get("persona", "")) in out["personas"]:
            out["time_rules"].append({"id": _pid(t.get("id") or f"r{i}") or f"r{i}", "from": _hhmm(t.get("from"), "22:00"), "to": _hhmm(t.get("to"), "07:00"), "persona": _pid(t["persona"])})
    out["milestones"] = []
    for i, t in enumerate((raw.get("milestones") if isinstance(raw.get("milestones"), list) else [])[:30]):
        if not isinstance(t, dict):
            continue
        pt = _pid(t.get("persona", ""))
        out["milestones"].append({"id": _pid(t.get("id") or f"m{i}") or f"m{i}", "enabled": bool(t.get("enabled", True)), "event": t.get("event") if t.get("event") in ("follow", "sub", "resub", "gift", "cheer", "raid", "redeem") else "follow",
                                  "every": _i(t.get("every", 10), 1, 10**7, 10), "count_by": t.get("count_by") if t.get("count_by") in ("events", "amount") else "events",
                                  "scope": t.get("scope") if t.get("scope") in ("day", "forever") else "day", "persona": pt if pt in out["personas"] else "default", "lines": _list(t.get("lines", []), 20, 240)})
    out["timers"] = []
    for i, t in enumerate((raw.get("timers") if isinstance(raw.get("timers"), list) else [])[:30]):
        if not isinstance(t, dict):
            continue
        pt = _pid(t.get("persona", ""))
        out["timers"].append({"id": _pid(t.get("id") or f"t{i}") or f"t{i}", "name": _s(t.get("name", "Reminder"), 40) or "Reminder", "enabled": bool(t.get("enabled", False)),
                              "every_min": _i(t.get("every_min", 30), 1, 1440, 30), "jitter_pct": _i(t.get("jitter_pct", 20), 0, 90, 20), "min_chat": _i(t.get("min_chat", 0), 0, 10**6, 0),
                              "persona": pt if pt in out["personas"] else "default", "priority": _i(t.get("priority", 3), 1, 9, 3), "lines": _list(t.get("lines", []), 30, 240)})
    if isinstance(raw.get("pronounce"), dict):
        out["pronounce"] = {_s(k, 40).lower(): _s(v, 60) for k, v in list(raw["pronounce"].items())[:200] if _s(k, 40) and _s(v, 60)}
    t, rt = out["theme"], raw.get("theme") if isinstance(raw.get("theme"), dict) else {}
    t["accent"] = _color(rt.get("accent"), t["accent"])
    t["mode"] = rt.get("mode") if rt.get("mode") in ("dark", "light") else "dark"
    out["history"]["keep"] = _i((raw.get("history") or {}).get("keep", 50) if isinstance(raw.get("history"), dict) else 50, 5, 500, 50)
    rt2 = raw.get("tts") if isinstance(raw.get("tts"), dict) else {}
    out["tts"] = {"enabled": bool(rt2.get("enabled", False)), "min_role": rt2.get("min_role") if rt2.get("min_role") in ("viewer", "sub", "vip", "mod", "broadcaster") else "mod"}
    rl2 = raw.get("listen") if isinstance(raw.get("listen"), dict) else {}
    rv = raw.get("review") if isinstance(raw.get("review"), dict) else {}
    dv = d["review"]
    rc = rv.get("checks") if isinstance(rv.get("checks"), dict) else {}
    out["review"] = {"enabled": bool(rv.get("enabled", True)), "interval_min": _i(rv.get("interval_min", 60), 5, 720, 60), "only_when_live": bool(rv.get("only_when_live", True)),
                     "final_review": bool(rv.get("final_review", True)), "keep": _i(rv.get("keep", 48), 5, 500, 48), "use_transcript": bool(rv.get("use_transcript", True)),
                     "use_chat": bool(rv.get("use_chat", True)), "use_console": bool(rv.get("use_console", True)), "talk_over_max": _i(rv.get("talk_over_max", 3), 1, 100, 3),
                     "repeat_max": _i(rv.get("repeat_max", 3), 2, 100, 3), "complaint_window_s": _i(rv.get("complaint_window_s", 45), 5, 300, 45),
                     "checks": {k: bool(rc.get(k, True)) for k in REVIEW_CHECKS},
                     "complaint_phrases": _list(rv.get("complaint_phrases", dv["complaint_phrases"]), 60, 60), "praise_phrases": _list(rv.get("praise_phrases", dv["praise_phrases"]), 60, 60)}
    cv = raw.get("control") if isinstance(raw.get("control"), dict) else {}
    ca = cv.get("allow") if isinstance(cv.get("allow"), dict) else {}
    out["control"] = {"enabled": bool(cv.get("enabled", False)), "wake_words": [w.lower() for w in _list(cv.get("wake_words", d["control"]["wake_words"]), 10, 30)] or d["control"]["wake_words"],
                      "require_confirm": bool(cv.get("require_confirm", True)), "expire_s": _i(cv.get("expire_s", 25), 5, 120, 25), "cooldown_s": _i(cv.get("cooldown_s", 5), 0, 600, 5),
                      "max_unsure": _clip(cv.get("max_unsure", 0.6), 0, 1, 0.6), "readback": bool(cv.get("readback", True)), "title_case": bool(cv.get("title_case", True)),
                      "max_timeout_s": _i(cv.get("max_timeout_s", 600), 1, 86400, 600), "protected": [p.lower() for p in _list(cv.get("protected", []), 50, 40)],
                      "allow": {k: bool(ca.get(k, True)) for k in ("game", "title", "timeout")}}
    out["listen"] = {"confirm_commands": bool(rl2.get("confirm_commands", False)), "confirm_text": _s(rl2.get("confirm_text", "Done."), 100) or "Done."}
    return out


# ------------------------------------------------------------------ persistence, backups, presets
def load():
    try:
        return normalize(json.loads(path("config.json").read_text("utf8")))
    except (OSError, ValueError):
        return normalize({})


def save(cfg, backup=True):
    cfg = normalize(cfg)
    with _lock:
        p = path("config.json")
        if backup and p.exists():
            bd = path("backups")
            bd.mkdir(exist_ok=True)
            (bd / f"config-{time.strftime('%Y%m%d-%H%M%S')}.json").write_bytes(p.read_bytes())
            for old in sorted(bd.glob("config-*.json"))[:-15]:
                old.unlink(missing_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf8")
        os.replace(tmp, p)
    return cfg


def backups():
    bd = path("backups")
    return sorted((f.name for f in bd.glob("config-*.json")), reverse=True) if bd.exists() else []


def restore_backup(name):
    f = path("backups") / re.sub(r"[^\w.-]", "", name)
    if not f.exists():
        raise ValueError("no such backup")
    return save(json.loads(f.read_text("utf8")))


def _preset_dir():
    d = path("presets")
    d.mkdir(exist_ok=True)
    return d


def _pname(n):
    return re.sub(r"[^\w -]", "", _s(n, 40)).strip() or "preset"


def preset_list():
    out = [{"name": k, "builtin": True, "about": v[0]} for k, v in BUILTIN_PRESETS.items()]
    out += [{"name": f.stem, "builtin": False, "about": "your preset"} for f in sorted(_preset_dir().glob("*.json"))]
    return out


def preset_save(name, cfg):
    n = _pname(name)
    data = normalize(cfg)
    data["master"] = False                       # a preset never carries the master switch
    data["mute_until"] = 0
    (_preset_dir() / f"{n}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf8")
    return n


def preset_get(name):
    if name in BUILTIN_PRESETS:
        return normalize(BUILTIN_PRESETS[name][1](defaults()))
    f = _preset_dir() / f"{_pname(name)}.json"
    if not f.exists():
        raise ValueError("no such preset")
    return normalize(json.loads(f.read_text("utf8")))


def preset_delete(name):
    if name in BUILTIN_PRESETS:
        raise ValueError("built-in presets cannot be deleted")
    (_preset_dir() / f"{_pname(name)}.json").unlink(missing_ok=True)


def _cozy(c):
    c["default_persona"] = "sleepy"
    c["output"]["volume"] = 50
    c["limits"].update(rate_per_min=6, max_chars=100)
    c["queue"]["gap_ms"] = 900
    for k in ("cheer", "gift", "raid"):
        c["events"][k]["persona"] = "sleepy"
    return c


def _hype(c):
    c["default_persona"] = "hype"
    c["output"]["volume"] = 90
    c["limits"].update(rate_per_min=20)
    c["queue"].update(gap_ms=150, interrupt_min_priority=7)
    c["events"]["follow"]["persona"] = "hype"
    c["events"]["chat"]["enabled"] = False
    return c


def _deadpan(c):
    c["default_persona"] = "robot"
    for k in c["events"]:
        c["events"][k]["persona"] = "robot"
    c["events"]["follow"]["templates"] = ["Follower acknowledged: {user}."]
    return c


def _chaos(c):
    c["default_persona"] = "hype"
    c["roles"].update(mod="robot", sub="narrator", vip="radio", viewer="professor")
    c["events"]["follow"]["persona"] = "narrator"
    c["events"]["cheer"]["persona"] = "radio"
    c["events"]["raid"]["persona"] = "hype"
    c["limits"]["rate_per_min"] = 30
    return c


BUILTIN_PRESETS = {
    "Factory (Captain)": ("The out-of-the-box setup.", lambda c: c),
    "Cozy night": ("Quiet, slow, sleepy; low volume, few lines.", _cozy),
    "Hype stream": ("Loud and fast, short gaps, hype penguin everywhere.", _hype),
    "Deadpan robot": ("One flat robot voice for everything.", _deadpan),
    "Chaos cast": ("A different persona per role and event.", _chaos),
}
