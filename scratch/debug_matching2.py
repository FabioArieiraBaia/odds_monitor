"""Debug: compare remaining unmatched Bet365 names vs 1xBet English names."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import asyncio, aiohttp
from sources.onexbet_scraper import OneXBetScraper
from core.state_cache import match_similarity

async def main():
    scraper = OneXBetScraper()
    await scraper.start()
    events = await scraper.fetch_live_events()
    await scraper.stop()
    
    xbet_names = [(e.match_id, e.match_name) for e in events if e.sport == "tabletennis"]
    
    # From the dashboard screenshot
    bet365_samples = [
        "Mateusz Rutkowski vs Kamil Rudomina",
        "Oleksii Mitla vs Mykyta Smyrnov",
        "Michal Guzik vs Mateusz Karpiuk",
        "Vitalii Khamurda vs Oleksandr Naida",
        "Oleksandr Budnikov vs Yurii Parahailo",
        "Oleg Vitrovyj vs Tomas Regner",
        "Ales Hlawatschke vs Richard Krejci",
        "Sebastian Kasnik vs Mark Robin Wagner",
    ]
    
    print(f"\n1xBet English names ({len(xbet_names)}):")
    for mid, mn in xbet_names:
        print(f"  {mn}")
    
    print(f"\n\nMatching (threshold=0.72):")
    for b365 in bet365_samples:
        best_score = 0
        best_match = ""
        for mid, mname in xbet_names:
            score = match_similarity(b365, mname)
            if score > best_score:
                best_score = score
                best_match = mname
        status = "OK" if best_score >= 0.72 else "FAIL"
        print(f"  [{status}] {b365}")
        print(f"         -> {best_match} ({best_score:.3f})")

asyncio.run(main())
