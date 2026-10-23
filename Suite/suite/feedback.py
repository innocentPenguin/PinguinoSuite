"""'Report a problem' notes from the Suite UI: a markdown + json file per report (and the screenshots he attaches) under Data\feedback,
for 00 / the engines to read. Local only. Only what the user typed or attached is stored; token-looking strings are blanked."""
import base64
import json
import re
import time
from datetime import datetime
from pathlib import Path

MAX_NOTE = 8000
MAX_IMAGES = 6
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"))
_SECRET = re.compile(r"(oauth:[a-z0-9]{10,}|bearer\s+[a-z0-9._~+/=-]{16,}|(?:token|secret|password|api[_-]?key)\s*[:=]\s*\S{6,})", re.I)


def scrub(text: str) -> str:
    return _SECRET.sub("[removed]", text or "")


def _scrub_deep(v):
    if isinstance(v, str):
        return scrub(v)
    if isinstance(v, dict):
        return {str(k): _scrub_deep(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub_deep(x) for x in v]
    return v if isinstance(v, (int, float, bool)) or v is None else scrub(str(v))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "page").lower()).strip("-")[:40] or "page"


def _ext(raw: bytes):
    for m, e in _MAGIC:
        if raw.startswith(m):
            return e
    return "webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None


def save(root: Path, note: str, page: str = "", route: str = "", url: str = "", version: str = "", images=None, now: float | None = None, health: dict | None = None) -> dict:
    note = scrub(str(note or "")).strip()
    images = list(images or [])
    if not note and not images:
        raise ValueError("write a note or attach a screenshot")
    if len(note) > MAX_NOTE:
        raise ValueError(f"note too long (max {MAX_NOTE} characters)")
    if len(images) > MAX_IMAGES:
        raise ValueError(f"at most {MAX_IMAGES} screenshots")
    t = now if now is not None else time.time()
    stamp = datetime.fromtimestamp(t).strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{_slug(route or page)}"   # slug keeps a-z0-9 only: nothing token-like survives, scrubbed or not
    root.mkdir(parents=True, exist_ok=True)
    n = 1
    while (root / (base + ".json")).exists():
        n += 1
        base = f"{stamp}-{_slug(route or page)}-{n}"
    files = []
    if images:
        d = root / base
        d.mkdir()
        for i, im in enumerate(images, 1):
            try:
                raw = base64.b64decode(str(im.get("data", "")).split(",", 1)[-1], validate=False)
            except Exception:
                raise ValueError(f"screenshot {i} is not valid")
            ext = _ext(raw)
            if not ext or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError(f"screenshot {i} must be a png/jpg/gif/webp under 8 MB")
            (d / f"shot{i}.{ext}").write_bytes(raw)
            files.append(f"{base}/shot{i}.{ext}")
    meta = {"id": base, "time": datetime.fromtimestamp(t).isoformat(timespec="seconds"), "page": scrub(str(page))[:120], "route": scrub(str(route))[:120],
            "url": scrub(str(url))[:300], "version": str(version)[:40], "note": note, "screenshots": files}
    if health:   # the Suite's own selfcheck at the time of the report (module states, disk space); scrubbed again here
        meta["health"] = _scrub_deep(health)
    (root / (base + ".json")).write_text(json.dumps(meta, indent=2), "utf8")
    md = [f"# Problem report {meta['time']}", "", f"- Page: {meta['page']} ({meta['route']})", f"- URL: {meta['url']}", f"- Suite version: {meta['version'] or 'dev'}", "", note, ""]
    h = meta.get("health")
    if h:
        md += ["## Health at the time", "", "- " + ("all OK" if h.get("ok") else "; ".join(map(str, h.get("problems") or ["unknown"])))]
        md += [f"- {m.get('id')}: {m.get('state')}" + (f" ({m['last_error']})" if m.get("last_error") else "") for m in h.get("modules") or []]
        md += [f"- disk {d.get('drive')}: {d.get('free_gb')} GB free" for d in h.get("disks") or []]
        md += [""]
    md += [f"![shot]({f})" for f in files]
    (root / (base + ".md")).write_text("\n".join(md), "utf8")
    return meta


def _load(p: Path):
    """A report's dict, or None for a hand-edited / broken file (a list, a string, bad json)."""
    try:
        m = json.loads(p.read_text("utf8"))
    except Exception:
        return None
    return m if isinstance(m, dict) else None


def counts(root: Path) -> dict:
    """{'total': n, 'open': n} over ALL report files (the nav badge must not undercount when more than a page of reports exist)."""
    total = opened = 0
    for p in root.glob("*.json") if root.is_dir() else []:
        m = _load(p)
        if m is None:
            continue
        total += 1
        opened += 0 if m.get("handled") else 1
    return {"total": total, "open": opened}


def recent(root: Path, limit: int = 30) -> list:
    out = []
    for p in sorted(root.glob("*.json"), reverse=True) if root.is_dir() else []:
        if len(out) >= limit:
            break
        m = _load(p)
        if m is None:
            continue
        m["handled"] = bool(m.get("handled"))
        m["screenshots"] = m.get("screenshots") or []
        out.append(m)
    return out


def set_handled(root: Path, rid: str, handled: bool = True) -> dict:
    """Flip the handled flag stored in the report's .json. Only ids that look like our own file names are accepted."""
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-z0-9-]{1,80}", str(rid or "")):
        raise ValueError("bad id")
    p = root / (rid + ".json")
    if not p.is_file():
        raise KeyError(rid)
    m = _load(p)
    if m is None:
        raise ValueError("that report file is not readable")
    m["id"] = rid
    m["handled"] = bool(handled)
    m["handled_at"] = datetime.now().isoformat(timespec="seconds") if handled else ""
    p.write_text(json.dumps(m, indent=2), "utf8")
    return m
