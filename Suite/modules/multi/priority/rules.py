"""Local, explainable priority engine. Weighted rules -> score + reason chips. No AI, no network.

Every rule returns (points, detail). The Decision lists each rule that fired so the UI can show
"why this score". A subscriber is NOT automatically important (weight 0 by default); spam and
repeated mentions are capped or penalised instead of rewarded.
"""
import json
import re
import time

import config
from models import Decision

DEFAULT_RULES = {
    "weights": {
        "reply_to_me": 40,        # replied to one of my messages
        "mention": 30,            # said my name / @me
        "question": 25,           # looks like a direct question
        "conversation": 20,       # I answered this viewer recently, they are following up
        "keyword": 15,            # configured keyword hit
        "first_time": 15,         # first message ever / first in channel
        "returning": 8,           # known regular (>= returning_min messages in history)
        "vip": 0,                 # sub / vip / mod badge: off by default
        "spam_repeat": -30,       # same text from same user within repeat_window_s
        "shouting": -15,          # ALL CAPS wall
        "emote_spam": -10,        # mostly symbols/emotes
        "too_short": -8,          # 1-2 chars, no question
        "link": -5,
    },
    "keywords": ["help", "how do i", "when", "giveaway", "lobby", "code", "join"],
    "sender_boost": {},           # {"login": +points}
    "muted": [],                  # logins whose messages never become cards
    "tiers": {"high": 50, "medium": 30, "low": 15},
    "repeat_window_s": 60,
    "returning_min": 5,
    "mention_decay": [1.0, 0.5, 0.0],   # 1st, 2nd, 3rd+ mention by same user inside mention_window_s
    "mention_window_s": 120,
    "conversation_window_s": 300,
    "question_min_len": 4,
}

INTERROGATIVES = ("who", "what", "when", "where", "why", "how", "which", "can you", "could you", "do you",
                  "did you", "are you", "is it", "will you", "would you", "does", "should", "have you")
_URL = re.compile(r"https?://|www\.", re.I)


def load_rules():
    rules = json.loads(json.dumps(DEFAULT_RULES))
    try:
        user = json.loads(config.RULES_FILE.read_text("utf-8"))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(rules.get(k), dict):
                rules[k].update(v)
            else:
                rules[k] = v
    except Exception:
        pass
    return rules


def save_rules(patch):
    cur = {}
    try:
        cur = json.loads(config.RULES_FILE.read_text("utf-8"))
    except Exception:
        pass
    for k, v in patch.items():
        if k not in DEFAULT_RULES:
            continue
        if isinstance(v, dict) and isinstance(DEFAULT_RULES[k], dict):
            cur.setdefault(k, {}).update(v)
        else:
            cur[k] = v
    config.RULES_FILE.write_text(json.dumps(cur, indent=2), "utf-8")
    return load_rules()


def reset_rules(key=None):
    """Reset one rule key (or everything) back to the defaults."""
    if key is None:
        if config.RULES_FILE.exists():
            config.RULES_FILE.unlink()
        return load_rules()
    try:
        cur = json.loads(config.RULES_FILE.read_text("utf-8"))
    except Exception:
        cur = {}
    cur.pop(key, None)
    config.RULES_FILE.write_text(json.dumps(cur, indent=2), "utf-8")
    return load_rules()


class Context:
    """What the engine may know about the past. Production wires it to the store; tests fill it by hand."""

    def __init__(self, recent_by_user=None, user_count=0, answered_recently=False, learned=None):
        self.recent_by_user = recent_by_user or []   # [(ts, text, was_mention)] oldest..newest, same user
        self.user_count = user_count
        self.answered_recently = answered_recently   # I replied to / acknowledged this viewer lately
        self.learned = learned or {}                 # bounded learned weight deltas {rule: delta}


def _norm(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def is_question(text, min_len=4):
    t = text.strip().lower()
    if len(t) < min_len:
        return False
    if "?" in t:
        return True
    return t.startswith(INTERROGATIVES)


def mentions_me(text, names):
    t = text.lower()
    for n in names:
        if re.search(r"(?<![a-z0-9_])@?" + re.escape(n.lower().rstrip("_")) + r"_?(?![a-z0-9_])", t):
            return True
    return False


def score(m, ctx=None, rules=None, settings=None, now=None):
    """Return a Decision for ChatMessage `m`. Pure function: same inputs, same output."""
    rules = rules or load_rules()
    st = settings or config.settings()
    ctx = ctx or Context()
    now = now or m.ts or time.time()
    W = rules["weights"]
    reasons = []

    def add(rule, pts, detail=""):
        pts = pts + ctx.learned.get(rule, 0)
        if pts:
            reasons.append({"rule": rule, "points": round(pts, 1), "detail": detail})

    if m.is_self or m.is_bot or m.user.lower() in [b.lower() for b in st["bot_accounts"]]:
        return Decision(0.0, "none", [{"rule": "ignored", "points": 0, "detail": "self/bot account"}])
    if m.user.lower() in [u.lower() for u in rules["muted"]]:
        return Decision(0.0, "none", [{"rule": "muted", "points": 0, "detail": "sender muted"}])

    text = m.text.strip()
    names = st["my_names"]

    if m.reply_to_user and m.reply_to_user.lower().rstrip("_") in [n.lower().rstrip("_") for n in names]:
        add("reply_to_me", W["reply_to_me"], "replied to your message")

    if mentions_me(text, names):
        win = rules["mention_window_s"]
        prior = sum(1 for ts, _t, men in ctx.recent_by_user if men and now - ts <= win)
        decay = rules["mention_decay"]
        factor = decay[min(prior, len(decay) - 1)]
        if factor > 0:
            add("mention", W["mention"] * factor, "mentioned you" + (" (repeat, reduced)" if prior else ""))
        else:
            reasons.append({"rule": "mention", "points": 0, "detail": "repeated mention, capped"})

    if is_question(text, rules["question_min_len"]):
        add("question", W["question"], "looks like a question")

    if ctx.answered_recently:
        add("conversation", W["conversation"], "you answered them recently")

    low = text.lower()
    hit = [k for k in rules["keywords"] if k.lower() in low]
    if hit:
        add("keyword", W["keyword"], "keyword: " + ", ".join(hit[:3]))

    if m.first_time or ctx.user_count == 0:
        add("first_time", W["first_time"], "first message")
    elif ctx.user_count >= rules["returning_min"]:
        add("returning", W["returning"], f"{ctx.user_count} past messages")

    if W.get("vip") and set(m.badges) & {"subscriber", "vip", "moderator"}:
        add("vip", W["vip"], "badge: " + ",".join(sorted(set(m.badges) & {"subscriber", "vip", "moderator"})))

    boost = rules["sender_boost"].get(m.user.lower())
    if boost:
        add("sender_boost", boost, "manual boost")

    # penalties --------------------------------------------------------
    n = _norm(text)
    rw = rules["repeat_window_s"]
    if n and any(now - ts <= rw and _norm(t) == n for ts, t, _ in ctx.recent_by_user):
        add("spam_repeat", W["spam_repeat"], "same text repeated")
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        add("shouting", W["shouting"], "all caps")
    if text and len(text) >= 6 and len(letters) / len(text) < 0.4:
        add("emote_spam", W["emote_spam"], "mostly symbols")
    if len(text) <= 2 and "?" not in text:
        add("too_short", W["too_short"], "very short")
    if _URL.search(text):
        add("link", W["link"], "contains a link")

    total = round(sum(r["points"] for r in reasons), 1)
    total = max(0.0, total)
    t = rules["tiers"]
    tier = "high" if total >= t["high"] else "medium" if total >= t["medium"] else "low" if total >= t["low"] else "none"
    return Decision(total, tier, reasons)
