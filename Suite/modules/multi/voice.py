"""Voice reply detection: match what the streamer just said (transcript text from Listen's ASR) to open cards.

Never auto-closes: returns suggestions with a confidence; the UI/API confirms with one click. Off by default
(setting voice_enabled). Transcript text is processed in memory only; nothing is stored.
"""
import re

STOP = set("the a an and or but to of in on for is are was be it this that you your i me my we do does did can could "
           "what when where why how with at as so if not no yes just have has had will would about they them there".split())


def words(t):
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if len(w) > 2 and w not in STOP}


def match(transcript, cards, min_conf=0.5, min_words=2):
    """cards: iterable of dicts with id/text/state/user. Returns [{card_id, confidence}] best first."""
    said = words(transcript)
    out = []
    for c in cards:
        if c.get("state") != "open":
            continue
        q = words(c["text"])
        if len(q) < min_words:
            continue
        hit = len(q & said)
        conf = round(hit / len(q) + (0.2 if c["user"].lower() in transcript.lower() else 0), 2)
        if hit >= min_words and conf >= min_conf:
            out.append({"card_id": c["id"], "confidence": min(conf, 1.0), "user": c["user"]})
    return sorted(out, key=lambda x: -x["confidence"])[:3]
