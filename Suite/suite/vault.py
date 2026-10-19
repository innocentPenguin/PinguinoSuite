"""Key vault: one encrypted store for every API key / token the Suite's modules need.

* On disk: Data/vault.bin, never plaintext. Windows: DPAPI (current-user scope, via ctypes, no dependencies).
  macOS/Linux: a random master key kept in the OS keychain (keyring package) used with Fernet (cryptography).
  The backend sits behind a two-method interface so another store can be swapped in.
* Values never leave the core except to a module that declares the name in its manifest ("secrets": [...]),
  and never to the UI: the app only sees set / missing, dates and who read it last.
* Metadata (created, updated, last_used, used_by) lives inside the encrypted payload too.
"""
import base64
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

MAGIC = b"PGV1"
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")
SECRET_KEY = re.compile(r"(key|token|secret|password|passwd|credential)", re.I)


class VaultError(Exception):
    pass


# ------------------------------------------------------------------ backends
class DpapiBackend:
    id = 1
    ENTROPY = b"PinguinoSuite-vault-v1"

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        self.BLOB = BLOB
        self.crypt32, self.kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32

    def _blob(self, data):
        buf = self.ct.create_string_buffer(data, len(data))
        return self.BLOB(len(data), self.ct.cast(buf, self.ct.POINTER(self.ct.c_char))), buf

    def _run(self, fn, data):
        inp, keep = self._blob(data)
        ent, keep2 = self._blob(self.ENTROPY)
        out = self.BLOB()
        if not fn(self.ct.byref(inp), None, self.ct.byref(ent), None, None, 0, self.ct.byref(out)):
            raise VaultError("Windows DPAPI call failed (different Windows user, or the file is damaged)")
        try:
            return self.ct.string_at(out.pbData, out.cbData)
        finally:
            self.kernel32.LocalFree(out.pbData)

    def protect(self, data):
        return self._run(self.crypt32.CryptProtectData, data)

    def unprotect(self, data):
        return self._run(self.crypt32.CryptUnprotectData, data)


class KeyringBackend:
    id = 2
    SERVICE, USER = "PinguinoSuite", "vault-master-key"

    def __init__(self):
        import keyring
        from cryptography.fernet import Fernet
        self.keyring, self.Fernet = keyring, Fernet
        k = keyring.get_password(self.SERVICE, self.USER)
        if not k:
            k = Fernet.generate_key().decode()
            keyring.set_password(self.SERVICE, self.USER, k)
        self.f = Fernet(k.encode())

    def protect(self, data):
        return self.f.encrypt(data)

    def unprotect(self, data):
        try:
            return self.f.decrypt(data)
        except Exception as e:  # noqa: BLE001
            raise VaultError("could not decrypt the vault with the keychain key") from e


def default_backend():
    if sys.platform == "win32":
        return DpapiBackend()
    return KeyringBackend()


# ------------------------------------------------------------------ the vault
class Vault:
    def __init__(self, path, backend=None, clock=time.time):
        self.path, self.clock, self.lock = Path(path), clock, threading.RLock()
        self.backend = backend or default_backend()
        self._d = None

    # ---- storage
    def _load(self):
        if self._d is not None:
            return self._d
        if not self.path.is_file():
            self._d = {"version": 1, "entries": {}}
            return self._d
        raw = self.path.read_bytes()
        if raw[:4] != MAGIC or len(raw) < 6:
            raise VaultError("vault file is not valid")
        if raw[4] != self.backend.id:
            raise VaultError("vault was written by a different key store (restore it from a backup export)")
        self._d = json.loads(self.backend.unprotect(raw[5:]).decode("utf8"))
        return self._d

    def _save(self):
        blob = MAGIC + bytes([self.backend.id]) + self.backend.protect(json.dumps(self._d).encode("utf8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_bytes(blob)
        if self.path.is_file():
            try:
                (self.path.with_name(self.path.name + ".bak")).write_bytes(self.path.read_bytes())
            except OSError:
                pass
        os.replace(tmp, self.path)

    # ---- API
    def names(self):
        with self.lock:
            return sorted(self._load()["entries"])

    def info(self, name):
        with self.lock:
            e = self._load()["entries"].get(name)
            return None if e is None else {k: e.get(k) for k in ("created", "updated", "last_used", "used_by", "rotations")}

    def set(self, name, value):
        if not NAME_RE.match(name or ""):
            raise VaultError("bad key name")
        if not isinstance(value, str) or not value.strip():
            raise VaultError("value is empty")
        if len(value) > 8192:
            raise VaultError("value is too long")
        with self.lock:
            ents, now = self._load()["entries"], self.clock()
            old = ents.get(name)
            ents[name] = {"v": value, "created": old["created"] if old else now, "updated": now, "last_used": old.get("last_used") if old else None,
                          "used_by": old.get("used_by") if old else None, "rotations": (old.get("rotations", 0) + 1) if old else 0}
            self._save()

    def get(self, name, by=None):
        """The only way to read a value. `by` = module id, recorded as last user."""
        with self.lock:
            e = self._load()["entries"].get(name)
            if e is None:
                return None
            e["last_used"], e["used_by"] = self.clock(), by
            try:
                self._save()
            except OSError:
                pass
            return e["v"]

    def peek(self, name):
        """Value without touching last_used (internal: tests, redaction)."""
        with self.lock:
            e = self._load()["entries"].get(name)
            return e["v"] if e else None

    def delete(self, name):
        with self.lock:
            ents = self._load()["entries"]
            if name in ents:
                del ents[name]
                self._save()
                return True
            return False

    def values(self, min_len=8):
        with self.lock:
            return [e["v"] for e in self._load()["entries"].values() if len(e["v"]) >= min_len]

    def redact(self, text):
        """Replace any stored secret that appears in text. Used on everything that reaches the Console."""
        try:
            for v in self.values():
                if v in text:
                    text = text.replace(v, "••••")
        except VaultError:
            pass
        return text

    # ---- backup (passphrase-encrypted, portable between machines)
    def export_backup(self, passphrase):
        import hashlib
        from cryptography.fernet import Fernet
        if len(passphrase) < 8:
            raise VaultError("passphrase must be at least 8 characters")
        with self.lock:
            payload = json.dumps(self._load()).encode("utf8")
        salt = os.urandom(16)
        key = base64.urlsafe_b64encode(hashlib.scrypt(passphrase.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32))
        return b"PGB1" + salt + Fernet(key).encrypt(payload)

    def restore_backup(self, data, passphrase, merge=True):
        import hashlib
        from cryptography.fernet import Fernet
        if data[:4] != b"PGB1" or len(data) < 21:
            raise VaultError("not a vault backup")
        key = base64.urlsafe_b64encode(hashlib.scrypt(passphrase.encode(), salt=data[4:20], n=2 ** 14, r=8, p=1, dklen=32))
        try:
            incoming = json.loads(Fernet(key).decrypt(data[20:]).decode("utf8"))["entries"]
        except Exception as e:  # noqa: BLE001
            raise VaultError("wrong passphrase, or the backup is damaged") from e
        with self.lock:
            ents = self._load()["entries"]
            n = 0
            for k, e in incoming.items():
                if NAME_RE.match(k) and (not merge or k not in ents):
                    ents[k] = e
                    n += 1
            self._save()
        return n


# ------------------------------------------------------------------ migration from plaintext files
KNOWN = {  # (file, key path) -> canonical vault name
    ("settings.json", "TrnApiKey"): "TRN_API_KEY",
    ("settings.json", "WebSyncKey"): "WEBSYNC_KEY",
    ("chat_settings.json", "ApiKey"): "CHAT_BOT_API_KEY",
}


def _walk(o, prefix=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                yield from _walk(v, f"{prefix}{k}.")
            elif isinstance(v, str) and v.strip() and SECRET_KEY.search(k):
                yield (prefix + k, v)
    elif isinstance(o, list):
        for i, v in enumerate(o[:50]):
            yield from _walk(v, f"{prefix}{i}.")


def vault_name(fname, keypath):
    if (fname, keypath) in KNOWN:
        return KNOWN[(fname, keypath)]
    stem = re.sub(r"[^A-Za-z0-9]+", "_", Path(fname).stem).strip("_").upper()
    return f"{stem}.{re.sub(r'[^A-Za-z0-9_.]+', '_', keypath)}"[:80]


def scan_plaintext(files):
    """files = [Path]. Returns [{file, path, name, in_vault_hint}] of secret-looking non-empty values. Values are never returned."""
    out = []
    for p in files:
        try:
            obj = json.loads(Path(p).read_text("utf8"))
        except (OSError, ValueError):
            continue
        for kp, _v in _walk(obj):
            out.append({"file": Path(p).name, "path": kp, "name": vault_name(Path(p).name, kp)})
    return out


def import_plaintext(vault, files, overwrite=False):
    """Copy every secret-looking value from the files into the vault (plaintext files are NOT changed). Returns count imported."""
    n = 0
    for p in files:
        try:
            obj = json.loads(Path(p).read_text("utf8"))
        except (OSError, ValueError):
            continue
        for kp, v in _walk(obj):
            name = vault_name(Path(p).name, kp)
            if overwrite or vault.peek(name) is None:
                vault.set(name, v)
                n += 1
    return n


def scrub_plaintext(vault, path, expected_names=None):
    """Blank the secret values in one JSON file, but ONLY those that the vault holds with the identical value. Returns number blanked."""
    p = Path(path)
    obj = json.loads(p.read_text("utf8"))
    n = 0

    def blank(o, prefix=""):
        nonlocal n
        if isinstance(o, dict):
            for k in list(o):
                v = o[k]
                if isinstance(v, (dict, list)):
                    blank(v, f"{prefix}{k}.")
                elif isinstance(v, str) and v.strip() and SECRET_KEY.search(k) and vault.peek(vault_name(p.name, prefix + k)) == v:
                    o[k] = ""
                    n += 1
        elif isinstance(o, list):
            for i, v in enumerate(o[:50]):
                blank(v, f"{prefix}{i}.")
    blank(obj)
    if n:
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2), "utf8")
        os.replace(tmp, p)
    return n
