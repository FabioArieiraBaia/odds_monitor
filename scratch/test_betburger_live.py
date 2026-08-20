import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from sources.betburger_source import BetBurgerScraper

async def test():
    print("Testing BetBurger Scraper standalone...")
    scraper = BetBurgerScraper()
    print("Starting scraper...")
    ok = await scraper.start()
    print("Start result:", ok)
    print("Fetching events...")
    events = await scraper.fetch_live_events()
    print(f"Events fetched: {len(events)}")
    for e in events[:5]:
        print(f"  - {e.match_name} [{e.set_score}/{e.game_score}] -> {e.source}")
    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(test())
