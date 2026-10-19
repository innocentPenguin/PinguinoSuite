"""Normalized objects shared by every connector, the API and the UI (see Docs/PinguinoMulti/CONTRACTS.md)."""
from dataclasses import dataclass, field, asdict


@dataclass
class ChatMessage:
    id: str                 # stable: "platform:channel:native_id"
    platform: str           # twitch | youtube | kick | discord | tiktok
    channel: str
    user_id: str
    user: str               # login
    display: str
    text: str
    ts: float               # epoch seconds
    badges: list = field(default_factory=list)   # e.g. ["moderator", "subscriber"]
    reply_to: str = ""      # id of the message being replied to (same scheme)
    reply_to_user: str = ""
    first_time: bool = False
    is_self: bool = False   # sent by the streamer / by Multi
    is_bot: bool = False
    raw_type: str = "text"
    color: str = ""         # name colour (#rrggbb) when the platform provides one
    emotes: list = field(default_factory=list)   # [{"id": "...", "text": "Kappa"}] (twitch)

    def to_dict(self):
        return asdict(self)


@dataclass
class Decision:
    score: float
    tier: str               # none | low | medium | high
    reasons: list           # [{"rule": str, "points": float, "detail": str}]

    def to_dict(self):
        return asdict(self)
