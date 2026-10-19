"""The queue we own. Pure logic, no network.

Items are dicts (JSON-friendly). Spotify's real queue can only be appended to, so at most ONE item (the head)
is ever `pushed` to Spotify, just in time. A pushed head is frozen: it can't be moved or removed, only flagged
`skip_on_play`. Streamer-placed / moved items are `locked`; viewer requests are fairly interleaved around them.
"""
import copy
import threading
import time
import uuid

UNDO_DEPTH = 30
HISTORY_MAX = 200


class QueueError(Exception):
    pass


def new_item(track, requester="", source="streamer", tier=0):
    return {"id": uuid.uuid4().hex[:10], "uri": track["uri"], "track_id": track.get("id", ""),
            "name": track.get("name", ""), "artists": list(track.get("artists", [])), "album": track.get("album", ""),
            "art": track.get("art", ""), "duration_ms": int(track.get("duration_ms", 0)), "explicit": bool(track.get("explicit")),
            "requester": requester, "source": source, "tier": int(tier), "added": time.time(),
            "locked": source != "viewer", "pushed": False, "skip_on_play": False, "key": None}


class Queue:
    def __init__(self, items=None, history=None):
        self.lock = threading.RLock()
        self.items = items or []
        self.history = history or []
        self._undo = []

    def frozen(self):
        return 1 if self.items and self.items[0]["pushed"] else 0

    def _snap(self):
        self._undo.append(copy.deepcopy(self.items))
        del self._undo[:-UNDO_DEPTH]

    def index(self, iid):
        for i, it in enumerate(self.items):
            if it["id"] == iid:
                return i
        return -1

    def pending_for(self, requester):
        r = (requester or "").lower()
        return sum(1 for it in self.items if it["source"] == "viewer" and it["requester"].lower() == r)

    def contains_uri(self, uri):
        return any(it["uri"] == uri for it in self.items)

    def add(self, item, where="end"):
        """where: 'end' | 'next'. Viewer items ignore `where` and are placed fairly."""
        with self.lock:
            self._snap()
            if item["source"] == "viewer":
                rnd = self.pending_for(item["requester"]) + 1
                key = [rnd, -item["tier"], item["added"]]
                item["key"] = key
                pos = len(self.items)
                for i in range(self.frozen(), len(self.items)):
                    o = self.items[i]
                    if o["source"] == "viewer" and not o["locked"] and o["key"] and o["key"] > key:
                        pos = i
                        break
                self.items.insert(pos, item)
            elif where == "next":
                item["locked"] = True
                self.items.insert(self.frozen(), item)
            else:
                item["locked"] = True
                self.items.append(item)
            return self.index(item["id"])

    def remove(self, iid):
        """'removed', or 'marked'/'unmarked' for an item already in Spotify's queue (skipped when it starts)."""
        with self.lock:
            i = self.index(iid)
            if i < 0:
                raise QueueError("not in queue")
            it = self.items[i]
            self._snap()
            if it["pushed"]:
                it["skip_on_play"] = not it["skip_on_play"]
                return "marked" if it["skip_on_play"] else "unmarked"
            del self.items[i]
            return "removed"

    def move(self, iid, new_index):
        with self.lock:
            i = self.index(iid)
            if i < 0:
                raise QueueError("not in queue")
            if self.items[i]["pushed"]:
                raise QueueError("already sent to Spotify")
            new_index = max(self.frozen(), min(int(new_index), len(self.items) - 1))
            if new_index == i:
                return i
            self._snap()
            it = self.items.pop(i)
            it["locked"] = True
            self.items.insert(new_index, it)
            return new_index

    def play_next(self, iid):
        return self.move(iid, self.frozen())

    def clear(self, only_viewers=False):
        with self.lock:
            self._snap()
            self.items = [it for it in self.items if it["pushed"] or (only_viewers and it["source"] != "viewer")]

    def remove_last_of(self, requester):
        """A viewer's own undo (!oops): their most recent not-yet-pushed request."""
        with self.lock:
            r = (requester or "").lower()
            for i in range(len(self.items) - 1, -1, -1):
                it = self.items[i]
                if it["source"] == "viewer" and it["requester"].lower() == r and not it["pushed"]:
                    self._snap()
                    return self.items.pop(i)
            return None

    def undo(self):
        with self.lock:
            if not self._undo:
                raise QueueError("nothing to undo")
            snap = self._undo.pop()
            pushed_now = {it["id"]: it for it in self.items if it["pushed"]}
            for it in snap:
                it["pushed"] = it["id"] in pushed_now
                if it["pushed"]:
                    it["skip_on_play"] = pushed_now[it["id"]]["skip_on_play"]
            ids = {it["id"] for it in snap}
            extra = [it for it in pushed_now.values() if it["id"] not in ids]
            self.items = extra + snap
            self.items.sort(key=lambda it: 0 if it["pushed"] else 1)   # stable: a pushed item is always the head

    def pop_playing(self, uri):
        """Spotify started `uri`: if it is our pushed head, take it out of the queue and return it."""
        with self.lock:
            for i, it in enumerate(self.items):
                if it["uri"] == uri and it["pushed"]:
                    return self.items.pop(i)
            return None

    def add_history(self, entry):
        with self.lock:
            self.history.insert(0, entry)
            del self.history[HISTORY_MAX:]

    def total_ms(self):
        return sum(it["duration_ms"] for it in self.items)

    def view(self):
        with self.lock:
            return {"items": copy.deepcopy(self.items), "history": copy.deepcopy(self.history[:100]),
                    "can_undo": bool(self._undo), "total_ms": self.total_ms()}
