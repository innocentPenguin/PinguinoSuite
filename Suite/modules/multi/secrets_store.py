"""Tokens live in Windows Credential Manager (macOS Keychain later) via `keyring`; never in JSON or logs.
Falls back to an in-memory dict when no keyring backend works (tokens then last only for this run)."""
import json

SERVICE = "PinguinoMulti"
_mem = {}


def _kr():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def get(name, default=None):
    kr = _kr()
    try:
        v = kr.get_password(SERVICE, name) if kr else _mem.get(name)
    except Exception:
        v = _mem.get(name)
    if v is None:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def put(name, value):
    v = json.dumps(value)
    kr = _kr()
    try:
        if kr:
            kr.set_password(SERVICE, name, v)
            return
    except Exception:
        pass
    _mem[name] = v


def delete(name):
    _mem.pop(name, None)
    kr = _kr()
    try:
        if kr:
            kr.delete_password(SERVICE, name)
    except Exception:
        pass
