"""Saved settings templates, per settings area (e.g. the Wheel & Games tabs). Stored in <data dir>/templates.json as
{area: [{id, name, createdAt, values}]}. `values` is a flat object of scalars (what the settings page stages and saves). Everything coming
from the UI is bounded here: area ids, names, value types and counts, so a bad request can never grow or corrupt the file."""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

MAX_PER_AREA = 20
MAX_KEYS = 64
AREA = re.compile(r"^[a-z0-9_-]{1,32}$")
NAME = re.compile(r"^[^\x00-\x1f<>]{1,40}$")
KEY = re.compile(r"^[A-Za-z0-9_.-]{1,48}$")
_lock = threading.Lock()


class TemplateError(Exception):
    """Carries an HTTP-ish status: 400 bad input, 404 not found, 409 name taken, 413 too many."""

    def __init__(self, status, msg, **extra):
        super().__init__(msg)
        self.status, self.msg, self.extra = status, msg, extra


def _scalar(v):
    return v is None or isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 200)


def clean_values(v):
    if not isinstance(v, dict) or not v or len(v) > MAX_KEYS:
        raise TemplateError(400, f"values must be an object with 1 to {MAX_KEYS} settings")
    out = {}
    for k, x in v.items():
        if not isinstance(k, str) or not KEY.match(k) or not _scalar(x):
            raise TemplateError(400, f"bad setting '{str(k)[:30]}'")
        out[k] = x
    return out


def clean_name(n):
    n = " ".join(str(n or "").split())
    if not NAME.match(n):
        raise TemplateError(400, "the name needs 1 to 40 characters")
    return n


def _area(a):
    if not isinstance(a, str) or not AREA.match(a):
        raise TemplateError(400, "bad settings area")
    return a


class Templates:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf8"))
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def _write(self, d):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf8")
        os.replace(tmp, self.path)

    def list(self, area):
        a = _area(area)
        with _lock:
            L = self._read().get(a, [])
        return sorted((x for x in L if isinstance(x, dict)), key=lambda x: str(x.get("name", "")).lower())

    def save(self, area, name, values, overwrite=False):
        a, n, v = _area(area), clean_name(name), clean_values(values)
        with _lock:
            d = self._read()
            L = [x for x in d.get(a, []) if isinstance(x, dict)]
            same = next((x for x in L if str(x.get("name", "")).lower() == n.lower()), None)
            if same and not overwrite:
                raise TemplateError(409, f"'{n}' already exists", exists=True)
            if same:
                same.update(name=n, values=v, createdAt=int(time.time()))
                item = same
            else:
                if len(L) >= MAX_PER_AREA:
                    raise TemplateError(413, f"at most {MAX_PER_AREA} templates per page: delete one first")
                item = {"id": uuid.uuid4().hex[:10], "name": n, "createdAt": int(time.time()), "values": v}
                L.append(item)
            d[a] = L
            self._write(d)
        return item

    def rename(self, area, tid, name):
        a, n = _area(area), clean_name(name)
        with _lock:
            d = self._read()
            L = [x for x in d.get(a, []) if isinstance(x, dict)]
            it = next((x for x in L if x.get("id") == tid), None)
            if not it:
                raise TemplateError(404, "that template no longer exists")
            if any(x is not it and str(x.get("name", "")).lower() == n.lower() for x in L):
                raise TemplateError(409, f"'{n}' already exists", exists=True)
            it["name"] = n
            d[a] = L
            self._write(d)
        return it

    def delete(self, area, tid):
        a = _area(area)
        with _lock:
            d = self._read()
            L = [x for x in d.get(a, []) if isinstance(x, dict)]
            if not any(x.get("id") == tid for x in L):
                raise TemplateError(404, "that template no longer exists")
            d[a] = [x for x in L if x.get("id") != tid]
            self._write(d)
        return True
