"""Small JSON persistence under <PINGUINO_DATA_DIR>/spotify/ (atomic replace, never raises on read)."""
import json
import os
import threading

import console_log

_lock = threading.Lock()


def folder():
    p = console_log.data_dir() / "spotify"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load(name, default):
    try:
        with open(folder() / name, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(name, data):
    p = folder() / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    with _lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        except OSError as e:
            console_log.warn("store", f"could not write {name}: {e}", dedupe_s=60)


def write_text(name, text):
    try:
        (folder() / name).write_text(text, encoding="utf-8")
    except OSError as e:
        console_log.warn("store", f"could not write {name}: {e}", dedupe_s=60)
