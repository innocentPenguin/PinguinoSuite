# INDEX: Text cleaning: scrub_secrets, clean_name, profanity mask, squash repeats, pronounce, clean_message, finish, templates (render), quiet hours. Related: brain.py.
"""Turn raw event/chat text into something safe and pleasant to say aloud.

Order: secrets -> links -> emoji -> repeats -> profanity -> pronunciation -> length. Secrets are NEVER read: anything that
looks like a token, key, password, oauth string, long random run, e-mail or IP address becomes "a secret" (or is dropped).
"""
import random
import re
import time
import unicodedata

import config as cfg

SECRET_PATTERNS = [
    re.compile(r"(?i)\boauth:[a-z0-9]{10,}"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[a-z0-9._~+/=-]{8,}"),
    # a keyword swallows the next few words too: a spoken passphrase has several ("password is correct horse battery staple")
    re.compile(r"(?i)\b(?:api[_ -]?key|token|secret|password|passwd|pwd|passphrase|pin|auth(?:orization)?|client[_ -]?secret|stream[_ -]?key)\b\s*(?:is|=|:)?\s*(?:\S+\s*){1,6}"),
    # the same keywords spelled out with separators between the letters ("p a s s w o r d", "t.o.k.e.n")
    re.compile(r"(?i)\b(?:" + "|".join(r"[\s._*-]*".join(w) for w in ("password", "passphrase", "token", "secret", "passwd")) + r")\b\s*(?:is|=|:)?\s*(?:\S+\s*){1,6}"),
    re.compile(r"\b[\w-]{24,26}\.[\w-]{6}\.[\w-]{25,}"),                  # Discord-style token: three dotted segments, none of them 28 long
    re.compile(r"\b\d{8,}\b|\b\d{3}[ .-]\d{3}[ .-]\d{4}\b"),               # long digit runs and phone numbers
    re.compile(r"\b(?:sk|pk|rk|xox[abp]|ghp|gho|AKIA|AIza)[-_A-Za-z0-9]{12,}"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9+/_-]{28,}={0,2}"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
]
URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|net|org|tv|gg|io|co|me|app|dev|ly|xyz)\b/?\S*")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍←-⇿⌀-⏿]+")
VARIABLE = re.compile(r"\{(\w+)\}")


def _fold(text):
    """Full-width / look-alike letters to plain ones (NFKC) and zero-width or other invisible format characters dropped, so
    "ｐａｓｓｗｏｒｄ" or "pass\u200bword" cannot slip past the patterns."""
    text = unicodedata.normalize("NFKC", str(text))
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def scrub_secrets(text):
    """Replace anything secret-looking. Returns (text, found)."""
    found = False
    text = _fold(text)
    for rx in SECRET_PATTERNS:
        def sub(m):
            nonlocal found
            found = True
            return "a secret"
        text = rx.sub(sub, text)
    return text, found


def clean_name(name, on=True):
    """How a display name is said: emoji and symbols dropped, _ - . become spaces, xX..Xx decoration and trailing digits removed,
    CamelCase split ("DragonSlayer" -> "Dragon Slayer"). A name with nothing sayable left becomes "someone"."""
    n = str(name or "").strip()
    if not on:
        return n
    n = scrub_secrets(n)[0]                                    # before any symbol is stripped: "oauth:abc..." must still be recognised
    n = re.sub(r"[^\w\s'.\-]|_", " ", n)         # emoji / symbols; \w keeps letters of any language and digits
    n = re.sub(r"[\-.]+", " ", n)
    n = re.sub(r"(?i)^\s*xx+\s*|\s*xx+\s*$", " ", n) if len(n) > 6 else n
    n = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", n)
    n = re.sub(r"\d{3,}\s*$", "", n.strip())
    n = re.sub(r"(?<=[A-Za-z])\d+$", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n if re.search(r"[^\W_]", n) else "someone"


def profane(text, extra):
    words = set(cfg.BAD_WORDS) | set(extra)
    return [w for w in re.findall(r"[a-zA-Z']+", text.lower()) if w in words or any(len(b) > 4 and b in w for b in words)]


def mask_profanity(text, extra):
    words = sorted(set(cfg.BAD_WORDS) | set(extra), key=len, reverse=True)
    for w in words:
        text = re.sub(r"(?i)\b\w*" + re.escape(w) + r"\w*\b" if len(w) > 4 else r"(?i)\b" + re.escape(w) + r"\w{0,3}\b", "beep", text)
    return text


def squash(text, n):
    if not n:
        return text
    text = re.sub(r"(.)\1{%d,}" % n, lambda m: m.group(1) * n, text)
    text = re.sub(r"(?i)\b(\w+)(?:\s+\1\b){%d,}" % n, lambda m: " ".join([m.group(1)] * n), text)
    return text


def pronounce(text, table):
    for k, v in sorted(table.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(r"(?i)\b" + re.escape(k) + r"\b", lambda _m, v=v: v, text)
    return text


def clean_message(text, c):
    """User-written text (chat/messages). Returns (text or None, reasons list)."""
    L, why = c["limits"], []
    text = str(text or "")[:2000]
    text, secret = scrub_secrets(text)
    if secret:
        why.append("secret")
    if L["block_links"]:
        text = URL.sub("a link", text)
    if L["strip_emoji"]:
        text = EMOJI.sub(" ", text)
    text = squash(text, L["max_repeat"])
    if L["profanity"] != "off" and profane(text, L["bad_words"]):
        if L["profanity"] == "skip":
            return None, why + ["profanity"]
        text = mask_profanity(text, L["bad_words"])
        why.append("masked")
    text = re.sub(r"\s+", " ", text).strip()
    return text, why


def safe_name(name, c):
    """A display name that may be spoken: secrets, links and profanity removed (names come from any platform). Empty when nothing is left."""
    n, _ = scrub_secrets(str(name or "")[:60])
    n = URL.sub("", n)
    L = c["limits"]
    if L["profanity"] != "off" and profane(n, L["bad_words"]):
        n = "" if L["profanity"] == "skip" else mask_profanity(n, L["bad_words"])
    return n.strip()


def finish(text, c):
    """Pronunciation + length limit for the final sentence. Returns (text or None, reasons)."""
    text = pronounce(text, c["pronounce"])
    text = re.sub(r"\s+", " ", text).strip()
    n = c["limits"]["max_chars"]
    if len(text) > n:
        if c["limits"]["too_long"] == "skip":
            return None, ["too_long"]
        cut = text[:n].rsplit(" ", 1)[0] or text[:n]
        return cut.rstrip(",;:- ") + ".", ["cut"]
    return text, []


def pick_template(options, amount, rng=random):
    """options: rows, optionally 'min:N|text'. Chooses randomly among the rows with the highest eligible N."""
    rows = []
    for o in options:
        m = re.match(r"^min:(\d+)\|(.*)$", o)
        rows.append((int(m.group(1)), m.group(2)) if m else (0, o))
    ok = [r for r in rows if r[0] <= amount]
    if not ok:
        return ""
    top = max(r[0] for r in ok)
    return rng.choice([r[1] for r in ok if r[0] == top])


def render(tpl, vars_, persona, rng=random):
    """Fill {variables}. Unknown variables are left out. {catch} = a random catchphrase of the persona."""
    catches = persona.get("catchphrases") or []

    def sub(m):
        k = m.group(1)
        if k == "catch":
            return rng.choice(catches) if catches else ""
        if k == "time":
            return time.strftime("%H:%M")
        if k == "persona":
            return persona.get("name", "")
        return str(vars_.get(k, "") if vars_.get(k) is not None else "")
    out = VARIABLE.sub(sub, tpl)
    return re.sub(r"\s+([.,!?])", r"\1", re.sub(r"\s+", " ", out)).strip()


def in_quiet(c, now=None):
    z = c["quiet"]
    if not z["enabled"]:
        return False
    t = time.localtime(now or time.time())
    cur = t.tm_hour * 60 + t.tm_min
    a = int(z["start"][:2]) * 60 + int(z["start"][3:])
    b = int(z["end"][:2]) * 60 + int(z["end"][3:])
    if a == b:
        return False
    return (a <= cur < b) if a < b else (cur >= a or cur < b)
