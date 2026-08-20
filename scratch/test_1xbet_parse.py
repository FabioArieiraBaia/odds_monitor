import asyncio
import aiohttp
import json

async def test():
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as s:
        async with s.get("https://22bet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4", timeout=aiohttp.ClientTimeout(total=8)) as r:
            data = await r.json()
            items = data.get("Value", [])
            print(f"Total live table tennis: {len(items)}")
            for item in items[:5]:
                p1 = item.get("O1")
                p2 = item.get("O2")
                sc = item.get("SC", {})
                fs = sc.get("FS", {})
                ps = sc.get("PS", [])
                last_p = ps[-1] if ps else {}
                print(f"Match: {p1} vs {p2} | Sets: {fs.get('S1')}:{fs.get('S2')} | Period: {last_p}")

if __name__ == "__main__":
    asyncio.run(test())
