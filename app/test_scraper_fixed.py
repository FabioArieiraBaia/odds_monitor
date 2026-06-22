import asyncio
import logging
from sources.bet365_scraper import Bet365Scraper

logging.basicConfig(level=logging.INFO)

async def main():
    scraper = Bet365Scraper(sports=["soccer", "tennis"])
    print("Iniciando scraper...")
    try:
        events = await scraper.fetch_live_events()
        print(f"\nTotal de eventos encontrados: {len(events)}")
        for idx, e in enumerate(events):
            print(f"[{idx+1}] {e.match_name} ({e.sport}) -> {e.deep_link}")
    except Exception as e:
        print(f"Erro: {e}")
    finally:
        await scraper.stop()

if __name__ == "__main__":
    asyncio.run(main())
