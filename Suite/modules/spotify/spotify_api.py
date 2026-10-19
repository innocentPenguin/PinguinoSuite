"""Spotify Web API: OAuth (Authorization Code + PKCE, no client secret) and a thin client.

`http` is injectable (tests): http(method, url, headers, body_bytes) -> (status, headers_dict, parsed_json_or_None).
Tokens live in <DATA>/spotify/tokens.json; access tokens refresh automatically.
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import console_log
import store

_ACC = os.environ.get("SPOTIFY_ACCOUNTS_BASE", "https://accounts.spotify.com")      # overridable for the offline e2e test
AUTH_URL = _ACC + "/authorize"
TOKEN_URL = _ACC + "/api/token"
API = os.environ.get("SPOTIFY_API_BASE", "https://api.spotify.com/v1")
SCOPES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-private "
          "user-read-recently-played playlist-read-private playlist-read-collaborative")


class ApiError(Exception):
    def __init__(self, status, message="", reason=""):
        super().__init__(f"{status} {reason or message}")
        self.status, self.message, self.reason = status, message, reason


class RateLimited(ApiError):
    def __init__(self, retry_after):
        super().__init__(429, "rate limited")
        self.retry_after = retry_after


class NotConnected(ApiError):
    def __init__(self, msg="not connected to Spotify"):
        super().__init__(401, msg, "NOT_CONNECTED")


def default_http(method, url, headers, body):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, dict(r.headers), (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return e.code, dict(e.headers), parsed
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ApiError(0, f"network error: {e}", "NETWORK")


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Auth:
    def __init__(self, http=default_http, clock=time.time):
        self.http, self.clock = http, clock
        self.lock = threading.RLock()
        self.pending = {}                      # state -> (verifier, ts)
        self.tokens = store.load("tokens.json", {})
        self.last_error = ""

    @property
    def client_id(self):
        return store.load("config.json", {}).get("client_id", "")

    def connected(self):
        return bool(self.tokens.get("refresh_token"))

    def begin(self, redirect_uri):
        cid = self.client_id
        if not cid:
            raise ApiError(400, "set the Client ID first", "NO_CLIENT_ID")
        verifier = b64url(secrets.token_bytes(64))
        state = secrets.token_urlsafe(16)
        now = self.clock()
        self.pending = {k: v for k, v in self.pending.items() if now - v[1] < 600}
        self.pending[state] = (verifier, now)
        q = urllib.parse.urlencode({"client_id": cid, "response_type": "code", "redirect_uri": redirect_uri, "state": state,
                                    "scope": SCOPES, "code_challenge_method": "S256",
                                    "code_challenge": b64url(hashlib.sha256(verifier.encode()).digest())})
        return AUTH_URL + "?" + q

    def finish(self, code, state, redirect_uri):
        ent = self.pending.pop(state, None)
        if not ent or self.clock() - ent[1] > 600:
            raise ApiError(400, "login expired or unknown state, start again", "BAD_STATE")
        self._token_call({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                          "client_id": self.client_id, "code_verifier": ent[0]})

    def _token_call(self, form):
        body = urllib.parse.urlencode(form).encode()
        st, _, js = self.http("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if st != 200 or not js or "access_token" not in js:
            err = (js or {}).get("error_description") or (js or {}).get("error") or f"HTTP {st}"
            self.last_error = str(err)
            if st == 400 and (js or {}).get("error") == "invalid_grant":     # refresh token revoked/expired
                with self.lock:
                    self.tokens.pop("refresh_token", None)
                    self.tokens.pop("access_token", None)
                    store.save("tokens.json", self.tokens)
                console_log.error("auth", "Spotify refresh token rejected; reconnect needed")
            raise ApiError(st, str(err), "AUTH")
        with self.lock:
            self.tokens["access_token"] = js["access_token"]
            self.tokens["expires_at"] = self.clock() + int(js.get("expires_in", 3600))
            if js.get("refresh_token"):
                self.tokens["refresh_token"] = js["refresh_token"]
            self.tokens["scope"] = js.get("scope", self.tokens.get("scope", ""))
            store.save("tokens.json", self.tokens)
        self.last_error = ""
        console_log.info("auth", "Spotify token refreshed" if form["grant_type"] == "refresh_token" else "Spotify connected")

    def access_token(self):
        with self.lock:
            if not self.connected():
                raise NotConnected()
            if self.tokens.get("access_token") and self.tokens.get("expires_at", 0) - 60 > self.clock():
                return self.tokens["access_token"]
            self._token_call({"grant_type": "refresh_token", "refresh_token": self.tokens["refresh_token"], "client_id": self.client_id})
            return self.tokens["access_token"]

    def force_refresh(self):
        with self.lock:
            self.tokens["expires_at"] = 0
        return self.access_token()

    def disconnect(self):
        with self.lock:
            self.tokens = {}
            store.save("tokens.json", {})

    def seconds_left(self):
        return max(0, int(self.tokens.get("expires_at", 0) - self.clock()))


class Client:
    def __init__(self, auth, http=default_http):
        self.auth, self.http = auth, http

    def connected(self):
        return self.auth.connected()

    def _req(self, method, path, params=None, body=None, retry=True):
        url = API + path + ("?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.auth.access_token()}
        if data is not None:
            headers["Content-Type"] = "application/json"
        st, hd, js = self.http(method, url, headers, data)
        if st == 401 and retry:
            self.auth.force_refresh()
            return self._req(method, path, params, body, retry=False)
        if st == 429:
            ra = {k.lower(): v for k, v in hd.items()}.get("retry-after", "5")
            raise RateLimited(int(float(ra)) if str(ra).replace(".", "").isdigit() else 5)
        if st >= 400:
            err = (js or {}).get("error", {}) if isinstance(js, dict) else {}
            raise ApiError(st, err.get("message", "") if isinstance(err, dict) else str(err), err.get("reason", "") if isinstance(err, dict) else "")
        return js

    # reads
    def me(self):
        return self._req("GET", "/me")

    def playback(self):
        return self._req("GET", "/me/player", {"additional_types": "track"})

    def queue(self):
        return self._req("GET", "/me/player/queue")

    def devices(self):
        return (self._req("GET", "/me/player/devices") or {}).get("devices", [])

    def search(self, q, limit=8):
        js = self._req("GET", "/search", {"q": q, "type": "track", "limit": limit, "market": "from_token"})
        return [norm_track(t) for t in (js or {}).get("tracks", {}).get("items", []) if t]

    def artists(self, ids):
        js = self._req("GET", "/artists", {"ids": ",".join(ids[:50])})
        return {a["id"]: [g.lower() for g in a.get("genres", [])] for a in (js or {}).get("artists", []) if a}

    def context_tracks(self, kind, cid, limit=100):
        """Tracks of a playlist or album (public, or private with the playlist scopes)."""
        out, offset = [], 0
        while len(out) < limit:
            js = self._req("GET", f"/{kind}s/{cid}/tracks", {"limit": 50, "offset": offset, "market": "from_token"})
            items = (js or {}).get("items", [])
            for it in items:
                t = it.get("track") if kind == "playlist" else it
                if t and t.get("uri", "").startswith("spotify:track:") and not t.get("is_local"):
                    if kind == "album":
                        t = {**t, "album": {"name": "", "images": []}}
                    out.append(norm_track(t))
            offset += 50
            if len(items) < 50 or not (js or {}).get("next"):
                break
        return [t for t in out if t][:limit]

    def track(self, tid):
        return norm_track(self._req("GET", "/tracks/" + tid, {"market": "from_token"}))

    # control
    def add_to_queue(self, uri, device_id=None):
        self._req("POST", "/me/player/queue", {"uri": uri, "device_id": device_id})

    def next(self):
        self._req("POST", "/me/player/next")

    def previous(self):
        self._req("POST", "/me/player/previous")

    def pause(self):
        self._req("PUT", "/me/player/pause")

    def resume(self):
        self._req("PUT", "/me/player/play")

    def play_uris(self, uris, device_id=None):
        self._req("PUT", "/me/player/play", {"device_id": device_id}, {"uris": uris})

    def play_context(self, context_uri, device_id=None):
        self._req("PUT", "/me/player/play", {"device_id": device_id}, {"context_uri": context_uri})

    def shuffle(self, on):
        self._req("PUT", "/me/player/shuffle", {"state": "true" if on else "false"})

    def seek(self, ms):
        self._req("PUT", "/me/player/seek", {"position_ms": int(ms)})

    def volume(self, pct):
        self._req("PUT", "/me/player/volume", {"volume_percent": max(0, min(100, int(pct)))})

    def transfer(self, device_id, play=False):
        self._req("PUT", "/me/player", None, {"device_ids": [device_id], "play": bool(play)})


def norm_track(t):
    if not t or not t.get("uri"):
        return None
    imgs = (t.get("album") or {}).get("images") or []
    art = (imgs[1] if len(imgs) > 1 else imgs[0])["url"] if imgs else ""
    return {"id": t.get("id", ""), "uri": t["uri"], "name": t.get("name", ""), "artists": [a.get("name", "") for a in t.get("artists", [])],
            "artist_ids": [a.get("id", "") for a in t.get("artists", []) if a.get("id")],
            "album": (t.get("album") or {}).get("name", ""), "art": art, "duration_ms": int(t.get("duration_ms") or 0),
            "explicit": bool(t.get("explicit"))}


def norm_playback(j):
    """Spotify /me/player JSON -> {is_playing, track|None, progress_ms, device, shuffle, repeat}."""
    if not j:
        return None
    dev = j.get("device") or {}
    return {"is_playing": bool(j.get("is_playing")), "track": norm_track(j.get("item")) if j.get("item") else None,
            "progress_ms": int(j.get("progress_ms") or 0), "shuffle": bool(j.get("shuffle_state")), "repeat": j.get("repeat_state", "off"),
            "device": {"id": dev.get("id"), "name": dev.get("name", ""), "volume": dev.get("volume_percent")} if dev else None}
