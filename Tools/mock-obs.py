# Mock obs-websocket v5 server (real auth algorithm) to test PinguinoHost's OBS client without OBS. Usage: mock-obs.py PORT PASSWORD
import asyncio, base64, hashlib, json, sys, websockets
PORT, PW = int(sys.argv[1]), sys.argv[2]
salt, chal = "c2FsdHNhbHQ=", "Y2hhbGxlbmdl"
def auth():
    sec = base64.b64encode(hashlib.sha256((PW + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((sec + chal).encode()).digest()).decode()
async def h(ws):
    await ws.send(json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1, "authentication": {"salt": salt, "challenge": chal}}}))
    m = json.loads(await ws.recv())
    if m["d"].get("authentication") != auth(): print("AUTH FAIL", flush=True); await ws.close(4009); return
    print("AUTH OK", flush=True); await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
    async for raw in ws:
        m = json.loads(raw)
        if m["op"] == 6:
            d = m["d"]; print("REQ", d["requestType"], json.dumps(d.get("requestData")), flush=True)
            r = {"requestType": d["requestType"], "requestId": d["requestId"], "requestStatus": {"result": True, "code": 100}}
            if d["requestType"] == "GetSceneItemId": r["responseData"] = {"sceneItemId": 7}
            await ws.send(json.dumps({"op": 7, "d": r}))
async def main():
    async with websockets.serve(h, "127.0.0.1", PORT): await asyncio.Future()
asyncio.run(main())
