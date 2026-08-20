import asyncio
import aiohttp

async def test():
    urls = [
        "https://22bet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
        "https://1xbet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
        "https://betwinner.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
        "https://melbet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4",
    ]
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as s:
        for url in urls:
            try:
                async with s.get(url, timeout=5) as r:
                    text = await r.text()
                    print(f"{url} -> HTTP {r.status} | len={len(text)} | starts={text[:40]}")
            except Exception as e:
                print(f"{url} -> Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
