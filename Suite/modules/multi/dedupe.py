"""Bounded seen-set so reconnect replays never produce duplicate messages."""
from collections import OrderedDict


class Seen:
    def __init__(self, cap=5000):
        self.cap, self.d = cap, OrderedDict()

    def add(self, key):
        """True if new, False if already seen."""
        if key in self.d:
            self.d.move_to_end(key)
            return False
        self.d[key] = 1
        if len(self.d) > self.cap:
            self.d.popitem(last=False)
        return True
