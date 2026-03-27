import asyncio
import websockets

async def t():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    async with websockets.connect(uri) as ws:
        msg = await ws.recv()
        print(msg[:200])

asyncio.run(t())