"""Tokens live in Windows Credential Manager (macOS Keychain later) via `keyring`; never in JSON or logs.
Falls back to an in-memory dict when no keyring backend works (tokens then last only for this run)."""
import json

import vault

SERVICE = "PinguinoMulti"
_mem = {}


def _kr():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def get(name, default=None):
    """Local store (Credential Manager) first: it holds what the user just set in Multi and rotated Twitch tokens.
    The Suite key vault is the fallback source (read-only for modules)."""
    v = _local(name)
    if v is None:
        raw = vault.get(name)
        if raw is not None:
            try:
                return json.loads(raw) if name == "twitch_tokens" else raw
            except Exception:
                return default
        return default
    return v


def source(name):
    """'local', 'vault' or None - which store currently supplies this secret (never the value)."""
    if _local(name) is not None:
        return "local"
    return "vault" if vault.get(name) is not None else None


def _local(name):
    kr = _kr()
    try:
        v = kr.get_password(SERVICE, name) if kr else _mem.get(name)
    except Exception:
        v = _mem.get(name)
    if v is None:
        return None
    try:
        return json.loads(v)
    except Exception:
        return None


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
