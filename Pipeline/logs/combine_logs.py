"""Combines the Twitch chat export files (newest-first, '[ts] #channel user: msg') into ONE chronological file.

Output (importer format, one line per message):  [YYYY-MM-DD HH:MM:SS] user: message
Drops bots, duplicate lines and the bot's own replies. Run:  python combine_logs.py <in1.txt> <in2.txt> ...
"""
import re, sys, json, collections

BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "pinguinob0t", "pinguinb0t", "sery_bot",
        "synchrabot", "soundalerts", "commanderroot", "own3d", "botrix", "supibot"}
rx = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] #\S+ ([A-Za-z0-9_]{3,25}): (.*)$")

rows, seen, bad = [], set(), 0
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\r\n")
        m = rx.match(line)
        if not m:
            bad += 1
            continue
        ts, user, msg = m.group(1), m.group(2).lower(), m.group(3).strip()
        if user in BOTS or not msg:
            continue
        key = (ts, user, msg)
        if key in seen:
            continue
        seen.add(key)
        rows.append(key)

rows.sort()
out = r"D:\PinguinoSuite\Pipeline\logs\combined_chat_7days.txt"
with open(out, "w", encoding="utf-8") as f:
    for ts, user, msg in rows:
        f.write("[%s] %s: %s\n" % (ts, user, msg))
print("messages:", len(rows), "unparsed lines:", bad, "->", out)
print("range:", rows[0][0], "to", rows[-1][0])
c = collections.Counter(u for _, u, _ in rows)
print("chatters:", len(c))
print("top 25:", c.most_common(25))
