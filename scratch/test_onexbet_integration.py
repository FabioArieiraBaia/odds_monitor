import asyncio
import sys
import os

# Add the 'app' directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

from sources.onexbet_scraper import OneXBetScraper

async def main():
    scraper = OneXBetScraper()
    events = await scraper.fetch_live_events()
    print(f"Fetched {len(events)} events.")
    for e in events[:5]:
        print(f"{e.match_name} | Set: {e.set_score} Game: {e.game_score} | {e.deep_link}")
    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(main())
