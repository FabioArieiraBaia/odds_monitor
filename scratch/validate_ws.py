import asyncio
import json
import websockets

async def validate():
    uri = "ws://127.0.0.1:8005/ws"
    async with websockets.connect(uri) as ws:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("type") == "update":
                matches = data.get("matches", [])
                stats = data.get("stats", {})
                if stats.get("bet365_count", 0) > 0 or len(matches) > 0:
                    print(f"B365 Count: {stats.get('bet365_count')} | Betano Count: {stats.get('betano_count')} | 1xBet Count: {stats.get('1xbet_count') or stats.get('xbet_count')}")
                    print(f"Partidas Ativas Pareadas: {len(matches)}\n")
                    for i, m in enumerate(matches, 1):
                        name = m.get("name")
                        src = m.get("sources", {})
                        b365 = src.get("bet365", {})
                        betano = src.get("betano", {})
                        xbet = src.get("1xbet") or src.get("betburger", {})
                        print(f"[{i}] {name}")
                        print(f"    - Bet365: Set {b365.get('set_score')} | Game {b365.get('game_score')}")
                        print(f"    - Betano: Set {betano.get('set_score')} | Game {betano.get('game_score')}")
                        print(f"    - 1xBet:  Set {xbet.get('set_score')} | Game {xbet.get('game_score')}")
                        print("-" * 50)
                    break

if __name__ == "__main__":
    asyncio.run(validate())
