# Mock obs-websocket v5 server (real auth algorithm) to test PinguinoHost's OBS client without OBS. Usage: mock-obs.py PORT PASSWORD
import asyncio, base64, hashlib, json, struct, sys
PORT, PW = int(sys.argv[1]), sys.argv[2]
# no third-party packages: a minimal WebSocket server (handshake, masked client text frames, unmasked server text frames)
class WS:
    def __init__(self, r, w): self.r, self.w = r, w
    async def send(self, text):
        b = text.encode(); n = len(b)
        hdr = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x81, 127]) + struct.pack('>Q', n)
        self.w.write(hdr + b); await self.w.drain()
    async def recv(self):
        while True:
            h = await self.r.readexactly(2); op, n = h[0] & 15, h[1] & 127
            if n == 126: n = struct.unpack('>H', await self.r.readexactly(2))[0]
            elif n == 127: n = struct.unpack('>Q', await self.r.readexactly(8))[0]
            mask = await self.r.readexactly(4) if h[1] & 128 else b''
            data = await self.r.readexactly(n)
            if mask: data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if op == 8: raise EOFError()
            if op == 1: return data.decode()
    async def close(self, code=1000): self.w.close()
    def __aiter__(self): return self
    async def __anext__(self):
        try: return await self.recv()
        except (EOFError, asyncio.IncompleteReadError, ConnectionError): raise StopAsyncIteration
async def serve(handler, host, port):
    CRLF = chr(13) + chr(10)
    async def conn(r, w):
        head = (await r.readuntil((CRLF + CRLF).encode())).decode(); key = [l.split(":", 1)[1].strip() for l in head.split(CRLF) if l.lower().startswith("sec-websocket-key")][0]
        acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        proto = "Sec-WebSocket-Protocol: obswebsocket.json" + CRLF if "obswebsocket.json" in head else ""
        w.write(("HTTP/1.1 101 Switching Protocols" + CRLF + "Upgrade: websocket" + CRLF + "Connection: Upgrade" + CRLF + "Sec-WebSocket-Accept: " + acc + CRLF + proto + CRLF).encode()); await w.drain()
        try: await handler(WS(r, w))
        except (EOFError, asyncio.IncompleteReadError, ConnectionError): pass
        finally: w.close()
    return await asyncio.start_server(conn, host, port)

salt, chal = "c2FsdHNhbHQ=", "Y2hhbGxlbmdl"
def auth():
    sec = base64.b64encode(hashlib.sha256((PW + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((sec + chal).encode()).digest()).decode()
# scenes for the live tree test (OBS lists bottom-first, sceneIndex 0 = bottom); item ids are unique per scene, group members belong to the group
SCENES = ["Starting", "Games / Rocket League", "Games / Fortnite", "[RL] Main", "Chat - Talk", "Chat - Solo", "Just Me"]
CUR = ["Games / Rocket League"]
REC = {"active": False, "paused": False}; CLIENTS = []; CTRL = sys.argv[3] if len(sys.argv) > 3 else None
ITEMS = {"Games / Rocket League": [{"sceneItemId": 1, "sourceName": "Camera", "sceneItemEnabled": True, "isGroup": False, "inputKind": "dshow_input"},
                                   {"sceneItemId": 2, "sourceName": "Overlays", "sceneItemEnabled": True, "isGroup": True},
                                   {"sceneItemId": 3, "sourceName": "Game", "sceneItemEnabled": False, "isGroup": False, "inputKind": "game_capture"}],
         "Overlays": [{"sceneItemId": 11, "sourceName": "Alerts", "sceneItemEnabled": True, "isGroup": False, "inputKind": "browser_source"},
                      {"sceneItemId": 12, "sourceName": "Chat", "sceneItemEnabled": False, "isGroup": False, "inputKind": "browser_source"}]}
def items_of(name): return [dict(it, sceneItemIndex=i) for i, it in enumerate(ITEMS.get(name, []))]
async def h(ws):
    await ws.send(json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1, "authentication": {"salt": salt, "challenge": chal}}}))
    m = json.loads(await ws.recv())
    if m["d"].get("authentication") != auth(): print("AUTH FAIL", flush=True); await ws.close(4009); return
    CLIENTS.append(ws); print("AUTH OK", flush=True); await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
    async for raw in ws:
        m = json.loads(raw)
        if m["op"] == 6:
            d = m["d"]; print("REQ", d["requestType"], json.dumps(d.get("requestData")), flush=True)
            r = {"requestType": d["requestType"], "requestId": d["requestId"], "requestStatus": {"result": True, "code": 100}}
            t, rd = d["requestType"], d.get("requestData") or {}
            if t == "GetRecordStatus": r["responseData"] = {"outputActive": REC["active"], "outputPaused": REC["paused"]}
            elif t == "GetSceneItemId": r["responseData"] = {"sceneItemId": 7}
            elif t == "GetSceneList": r["responseData"] = {"currentProgramSceneName": CUR[0], "scenes": [{"sceneName": n, "sceneIndex": i} for i, n in enumerate(SCENES)]}
            elif t in ("GetSceneItemList", "GetGroupSceneItemList"): r["responseData"] = {"sceneItems": items_of(rd.get("sceneName"))}
            elif t == "SetCurrentProgramScene": CUR[0] = rd["sceneName"]
            elif t in ("GetSceneItemEnabled", "SetSceneItemEnabled") and rd.get("sceneName") in ITEMS:
                it = next((x for x in ITEMS[rd["sceneName"]] if x["sceneItemId"] == rd["sceneItemId"]), None)
                if it is None: r["requestStatus"] = {"result": False, "code": 600}
                elif t == "GetSceneItemEnabled": r["responseData"] = {"sceneItemEnabled": it["sceneItemEnabled"]}
                else: it["sceneItemEnabled"] = rd["sceneItemEnabled"]
            await ws.send(json.dumps({"op": 7, "d": r}))
async def ctrl():
    # test control: write start|stop|pause|resume|drop into the file named by argv[3]; the mock emits RecordStateChanged / closes sockets
    while True:
        await asyncio.sleep(0.2)
        if not CTRL: continue
        try: cmd = open(CTRL).read().strip(); open(CTRL, "w").write("")
        except OSError: continue
        if not cmd: continue
        st = {"start": ("OBS_WEBSOCKET_OUTPUT_STARTED", True, False), "stop": ("OBS_WEBSOCKET_OUTPUT_STOPPED", False, False), "pause": ("OBS_WEBSOCKET_OUTPUT_PAUSED", True, True), "resume": ("OBS_WEBSOCKET_OUTPUT_RESUMED", True, False)}.get(cmd)
        if cmd == "drop":
            REC["active"] = REC["paused"] = False
            for c in list(CLIENTS):
                try: c.w.close()
                except Exception: pass
            CLIENTS.clear(); continue
        if st:
            REC["active"], REC["paused"] = st[1], st[2]
            for c in list(CLIENTS):
                try: await c.send(json.dumps({"op": 5, "d": {"eventType": "RecordStateChanged", "eventIntent": 64, "eventData": {"outputActive": st[1] and not st[2] or st[2], "outputState": st[0]}}}))
                except Exception: pass
async def main():
    asyncio.ensure_future(ctrl())
    srv = await serve(h, "127.0.0.1", PORT)
    async with srv: await srv.serve_forever()
asyncio.run(main())
