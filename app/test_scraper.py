import asyncio
import logging
from sources.bet365_scraper import Bet365Scraper

logging.basicConfig(level=logging.INFO)

async def main():
    scraper = Bet365Scraper(sports=["tennis"])
    print("Iniciando scraper...")
    print("Buscando eventos de tênis...")
    events = await scraper.fetch_live_events()
    print(f"Total de eventos encontrados: {len(events)}")
    for e in events[:5]:
        print(f"{e.home_team} vs {e.away_team} - {e.score} (ID: {e.event_id}) -> {e.deep_link}")
        
    await scraper.page.screenshot(path="debug_bet365_final.png", full_page=True)
    html = await scraper.page.content()
    with open("debug_bet365_real.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(main())
