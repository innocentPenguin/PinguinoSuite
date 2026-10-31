"""Prefix every line Listen prints with its clock time, so listen.log (plain stdout capture) can be lined up with the core log."""
import sys
import time


class StampStream:
    def __init__(self, stream, clock=time.time):
        self._s = stream
        self._clock = clock
        self._bol = True

    def write(self, text):
        if not text:
            return 0
        out = []
        for part in text.splitlines(keepends=True):
            if self._bol:
                out.append(time.strftime("%H:%M:%S ", time.localtime(self._clock())))
            out.append(part)
            self._bol = part.endswith("\n")
        return self._s.write("".join(out))

    def writelines(self, lines):
        for ln in lines:
            self.write(ln)

    def __getattr__(self, name):
        return getattr(self._s, name)


def install():
    for n in ("stdout", "stderr"):
        st = getattr(sys, n, None)
        if st is not None and not isinstance(st, StampStream):
            setattr(sys, n, StampStream(st))
