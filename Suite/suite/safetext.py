"""Console-safe text: control characters (the terminal bell above all) never reach a console.

A visible console turns the bell character into an audible beep, and chat text, transcripts and test inputs can contain one.
clean() escapes every control character except tab/CR/LF (and ANSI colour codes like ESC[0m) as \backslash-x plus two hex digits, so the text stays readable and
a log file keeps exactly what was said. install() wraps sys.stdout/sys.stderr so every print, traceback and logging line is cleaned.
Same file lives in Suite/suite and Suite/modules/listen (a test keeps the copies identical).
"""
import re
import sys

_KEEP = "\t\r\n"
_TABLE = {c: "\\x%02x" % c for c in list(range(0x20)) + [0x7F] + list(range(0x80, 0xA0)) if chr(c) not in _KEEP}
_SGR = re.compile(r"\x1b\[[0-9;]*m")


def clean(text):
    """Return text with control characters escaped (bell first among them). Non-strings are converted with str()."""
    s = text if isinstance(text, str) else str(text)
    if s.isprintable() and "\n" not in s:  # fast path: nothing to do
        return s
    if "\x1b" in s:  # keep plain colour sequences, escape every other ESC
        return "".join(p if _SGR.fullmatch(p) else p.translate(_TABLE) for p in re.split(r"(\x1b\[[0-9;]*m)", s))
    return s.translate(_TABLE)


class SafeStream:
    """A text stream whose write() cleans first; everything else is the wrapped stream's."""

    def __init__(self, stream):
        self._s = stream

    def write(self, text):
        return self._s.write(clean(text))

    def writelines(self, lines):
        for ln in lines:
            self.write(ln)

    def __getattr__(self, name):
        return getattr(self._s, name)


def install():
    """Wrap stdout/stderr once (a stream that does not exist, as under pythonw, is left alone)."""
    for n in ("stdout", "stderr"):
        st = getattr(sys, n, None)
        if st is not None and not isinstance(st, SafeStream):
            setattr(sys, n, SafeStream(st))
