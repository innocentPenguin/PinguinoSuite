r"""safe_print: print text with control characters made visible, so a BEL (0x07) in chat text or test data can never ring the speaker.
Control chars 0x00-0x08, 0x0b, 0x0c, 0x0e-0x1f and 0x7f become \xNN (BEL becomes \x07); \t \r \n pass through.
    from safe_print import safe_print, clean; safe_print("chat:", text)      install() makes plain print() safe for the whole process."""
import builtins
import re
import sys

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(s):
    return _CTRL.sub(lambda m: "\\x%02x" % ord(m.group()), str(s))


def safe_print(*args, **kw):
    sep = kw.pop("sep", " ")
    builtins.print(clean(sep.join(str(a) for a in args)), **kw)


def install():
    """Make print() in this process sanitize control characters."""
    if getattr(builtins.print, "_safe", False):
        return
    real = builtins.print

    def p(*args, **kw):
        if kw.get("file") in (None, sys.stdout, sys.stderr):
            sep = kw.pop("sep", " ")
            args = (clean(sep.join(str(a) for a in args)),)
        real(*args, **kw)
    p._safe = True
    builtins.print = p
