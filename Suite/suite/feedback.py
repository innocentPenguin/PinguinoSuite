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


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "page").lower()).strip("-")[:40] or "page"


def _ext(raw: bytes):
    for m, e in _MAGIC:
        if raw.startswith(m):
            return e
    return "webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None


def save(root: Path, note: str, page: str = "", route: str = "", url: str = "", version: str = "", images=None, now: float | None = None) -> dict:
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
    base = f"{stamp}-{_slug(route or page)}"
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
    meta = {"id": base, "time": datetime.fromtimestamp(t).isoformat(timespec="seconds"), "page": str(page)[:120], "route": str(route)[:120],
            "url": scrub(str(url))[:300], "version": str(version)[:40], "note": note, "screenshots": files}
    (root / (base + ".json")).write_text(json.dumps(meta, indent=2), "utf8")
    md = [f"# Problem report {meta['time']}", "", f"- Page: {meta['page']} ({meta['route']})", f"- URL: {meta['url']}", f"- Suite version: {meta['version'] or 'dev'}", "", note, ""]
    md += [f"![shot]({f})" for f in files]
    (root / (base + ".md")).write_text("\n".join(md), "utf8")
    return meta


def recent(root: Path, limit: int = 30) -> list:
    out = []
    for p in sorted(root.glob("*.json"), reverse=True)[:limit] if root.is_dir() else []:
        try:
            out.append(json.loads(p.read_text("utf8")))
        except Exception:
            pass
    return out
