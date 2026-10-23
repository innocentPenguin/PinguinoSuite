"""Small JSON persistence under <PINGUINO_DATA_DIR>/spotify/ (atomic replace, never raises on read)."""
import json
import os
import shutil
import threading
import time

import console_log

_lock = threading.Lock()


def folder():
    p = console_log.data_dir() / "spotify"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load(name, default):
    """Parsed file, or `default` when missing / wrong type. A corrupt file is kept as <name>.bad-<ts> (never silently overwritten);
    a locked file (Windows: antivirus, a replace in flight) is retried before giving up."""
    p = folder() / name
    for attempt in range(4):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if type(data) is type(default) else default
        except FileNotFoundError:
            return default
        except PermissionError:
            time.sleep(0.05)
        except ValueError:
            try:
                shutil.copyfile(p, p.with_name(f"{name}.bad-{int(time.time())}"))
                for old in sorted(p.parent.glob(name + ".bad-*"))[:-5]:          # keep the newest 5
                    old.unlink(missing_ok=True)
                console_log.warn("store", f"{name} was unreadable; kept a copy as {name}.bad-*", dedupe_s=60)
            except OSError:
                pass
            return default
        except OSError:
            return default
    return default


def save(name, data):
    p = folder() / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    with _lock:
        for attempt in (1, 2):
            try:
                text = json.dumps(data, ensure_ascii=False, indent=1)     # a dict another thread is changing raises RuntimeError: retry once
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, p)
                return
            except (OSError, TypeError, ValueError, RuntimeError) as e:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                if attempt == 2:
                    console_log.warn("store", f"could not write {name}: {type(e).__name__}: {e}", dedupe_s=60)
                else:
                    time.sleep(0.05)


def write_text(name, text):
    try:
        (folder() / name).write_text(text, encoding="utf-8")
    except OSError as e:
        console_log.warn("store", f"could not write {name}: {e}", dedupe_s=60)
