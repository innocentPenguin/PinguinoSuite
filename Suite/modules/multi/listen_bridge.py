"""Client of the Listen module's /ws: forwards finished speech segments to voice.match (suggest-only).

Does nothing unless setting voice_enabled is true. Listen is never modified; if it is not running we just retry.
Text is kept in a 30 s in-memory window and never stored.
"""
import asyncio
import json
import time

import websockets

import config
import voice

LISTEN_WS = "ws://127.0.0.1:8765/ws"
WINDOW_S = 30


class Window:
    def __init__(self, clock=time.time):
        self.items, self.clock = [], clock

    def add(self, text):
        now = self.clock()
        self.items = [(t, x) for t, x in self.items if now - t <= WINDOW_S] + [(now, text)]
        return " ".join(x for _t, x in self.items)


async def run(cards, emit, ws_url=LISTEN_WS):
    win = Window()
    while True:
        if not config.settings()["voice_enabled"]:
            await asyncio.sleep(5)
            continue
        try:
            async with websockets.connect(ws_url) as ws:
                async for raw in ws:
                    if not config.settings()["voice_enabled"]:
                        break
                    ev = json.loads(raw)
                    if ev.get("type") == "segment":
                        text = win.add(ev["segment"].get("text", ""))
                        for s in voice.match(text, cards.cards.values()):
                            emit({"type": "reply.suggested", **s})
        except Exception:
            await asyncio.sleep(10)
