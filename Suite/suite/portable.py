"""Config export / import bundle: move a Suite setup to another machine (or back it up) without copying folders by hand.

A bundle is a zip: manifest.json + the allow-listed config files. Secrets are NOT in it unless you ask for them, and then
only inside secrets.enc, encrypted with a passphrase (Fernet, key from scrypt). Machine identity (device.json, Link's
per-device config) is never exported, so an imported setup keeps its own device id.
Import is dry-run by default, only touches allow-listed paths, backs up what it replaces and keeps existing secrets when
the bundle has them blanked.
"""
import base64
import hashlib
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path

VERSION = 1
SECRET_KEY = re.compile(r"(key|token|secret|password|passwd|credential|auth)", re.I)
# (area, relative path, kind). kind: config = no secrets inside, mixed = config that also holds keys, secret = secrets only.
BUILTIN = [
    ("suite", "suite_settings.json", "config"),
    ("suite", "modules/listen/data/voice_commands.json", "config"),
    ("suite", "modules/listen/data/settings.json", "config"),
    ("data", "bots.json", "config"),
    ("data", "helper_settings.json", "config"),
    ("data", "chat_settings.json", "mixed"),
    ("data", "settings.json", "mixed"),
    ("data", "bots_secrets.json", "secret"),
    ("data", "host_secrets.json", "secret"),
]
NEVER = {"device.json", "link/config.json", "link/mesh.json", "config.json"}  # per-machine identity / per-machine Link setup


class ExportError(Exception):
    pass


def entries(module_specs=()):
    """Allow-list: builtin files plus whatever modules declare as "export": {"config": [...], "secrets": [...]} (relative to the data dir)."""
    out = list(BUILTIN)
    for spec in module_specs:
        ex = spec.get("export") or {}
        for kind, key in (("config", "config"), ("secret", "secrets")):
            for rel in ex.get(key, []):
                if _safe_rel(rel) and rel not in NEVER:
                    out.append(("data", rel, kind))
    return out


def _safe_rel(rel):
    return bool(re.fullmatch(r"[\w][\w.\- ]*(/[\w][\w.\- ]*)*", rel)) and ".." not in rel.split("/")


def _arc(area, rel):
    return f"{area}/{rel}"


def redact(o):
    if isinstance(o, dict):
        return {k: ("" if isinstance(v, str) and SECRET_KEY.search(k) else redact(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact(x) for x in o]
    return o


def keep_secrets(new, old):
    """Where the imported value is blank at a secret-looking key, keep what this machine already has."""
    if isinstance(new, dict) and isinstance(old, dict):
        out = {}
        for k, v in new.items():
            if isinstance(v, str) and v == "" and SECRET_KEY.search(k) and isinstance(old.get(k), str) and old.get(k):
                out[k] = old[k]
            else:
                out[k] = keep_secrets(v, old.get(k))
        return out
    return new


def _key(passphrase, salt):
    return base64.urlsafe_b64encode(hashlib.scrypt(passphrase.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32))


def _fernet(passphrase, salt):
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:  # noqa: BLE001
        raise ExportError("encryption needs the 'cryptography' package (pip install cryptography)") from e
    return Fernet(_key(passphrase, salt))


def _paths(roots, area, rel):
    return Path(roots[area]) / rel


def export_bundle(roots, module_specs, include_secrets=False, passphrase="", device=None, now=None):
    """roots = {"suite": Path, "data": Path}. Returns (zip bytes, manifest)."""
    if include_secrets and len(passphrase) < 8:
        raise ExportError("a passphrase of at least 8 characters is required to include secrets")
    plain, secret = {}, {}
    for area, rel, kind in entries(module_specs):
        p = _paths(roots, area, rel)
        if not p.is_file():
            continue
        raw = p.read_bytes()
        arc = _arc(area, rel)
        if kind == "secret":
            secret[arc] = raw
            continue
        if kind == "mixed":
            try:
                obj = json.loads(raw.decode("utf8"))
            except ValueError:
                continue
            plain[arc] = json.dumps(redact(obj), indent=2).encode()
            secret[arc] = raw
        else:
            plain[arc] = raw
    man = {"version": VERSION, "created": now or time.time(), "device": device or {}, "include_secrets": bool(include_secrets), "files": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, raw in sorted(plain.items()):
            z.writestr(arc, raw)
            man["files"].append({"arc": arc, "sha256": hashlib.sha256(raw).hexdigest(), "redacted": arc in secret})
        if include_secrets and secret:
            salt = os.urandom(16)
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as zi:
                for arc, raw in sorted(secret.items()):
                    zi.writestr(arc, raw)
            z.writestr("secrets.enc", _fernet(passphrase, salt).encrypt(inner.getvalue()))
            man["secrets"] = {"salt": base64.b64encode(salt).decode(), "files": sorted(secret)}
        z.writestr("manifest.json", json.dumps(man, indent=2))
    return buf.getvalue(), man


def import_bundle(roots, module_specs, data, passphrase="", apply=False, backup_dir=None):
    """Returns {"files": [{arc, status: new|changed|same|skipped, why}], "applied": bool, "needs_passphrase": bool}."""
    allowed = {_arc(a, r): (a, r, k) for a, r, k in entries(module_specs)}
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        man = json.loads(z.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise ExportError("not a Pinguino config bundle") from e
    if man.get("version") != VERSION:
        raise ExportError(f"bundle version {man.get('version')} is not supported")
    contents, needs_pass = {}, False
    for f in man.get("files", []):
        arc = f.get("arc", "")
        try:
            raw = z.read(arc)
        except KeyError:
            continue
        if hashlib.sha256(raw).hexdigest() != f.get("sha256"):
            raise ExportError(f"{arc} does not match its checksum (bundle damaged)")
        contents[arc] = raw
    if "secrets.enc" in z.namelist():
        if not passphrase:
            needs_pass = True
        else:
            try:
                salt = base64.b64decode(man["secrets"]["salt"])
                inner = zipfile.ZipFile(io.BytesIO(_fernet(passphrase, salt).decrypt(z.read("secrets.enc"))))
            except ExportError:
                raise
            except Exception as e:  # noqa: BLE001
                raise ExportError("wrong passphrase, or the secrets part is damaged") from e
            for arc in inner.namelist():
                contents[arc] = inner.read(arc)
    report, writes = [], []
    for arc, raw in sorted(contents.items()):
        ent = allowed.get(arc)
        if not ent or ent[1] in NEVER:
            report.append({"arc": arc, "status": "skipped", "why": "not an allowed config file"})
            continue
        area, rel, kind = ent
        dest = _paths(roots, area, rel)
        if kind != "secret" and rel.endswith(".json"):
            try:
                new = json.loads(raw.decode("utf8"))
                if dest.is_file():
                    new = keep_secrets(new, json.loads(dest.read_text("utf8")))
                raw = json.dumps(new, indent=2).encode()
            except ValueError:
                report.append({"arc": arc, "status": "skipped", "why": "not valid JSON"})
                continue
        cur = dest.read_bytes() if dest.is_file() else None
        status = "new" if cur is None else "same" if _same(cur, raw) else "changed"
        report.append({"arc": arc, "status": status})
        if status != "same":
            writes.append((dest, raw, arc))
    if apply:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bdir = Path(backup_dir or Path(roots["data"]) / "backups") / f"import-{stamp}"
        for dest, raw, arc in writes:
            if dest.is_file():
                (bdir / arc).parent.mkdir(parents=True, exist_ok=True)
                (bdir / arc).write_bytes(dest.read_bytes())
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".tmp")
            tmp.write_bytes(raw)
            os.replace(tmp, dest)
    return {"files": report, "applied": bool(apply), "needs_passphrase": needs_pass, "created": man.get("created"), "from": (man.get("device") or {}).get("name")}


def _same(a, b):
    try:
        return json.loads(a) == json.loads(b)
    except ValueError:
        return a == b
