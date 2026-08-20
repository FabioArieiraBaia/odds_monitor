"""Debug script to compare 1xBet vs Bet365 match names in the state_cache."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import asyncio
import aiohttp
from sources.onexbet_scraper import OneXBetScraper
from core.state_cache import match_similarity

async def main():
    scraper = OneXBetScraper()
    await scraper.start()
    events = await scraper.fetch_live_events()
    await scraper.stop()
    
    xbet_names = [(e.match_id, e.match_name) for e in events if e.sport == "tabletennis"]
    
    print(f"\n=== 1xBet names ({len(xbet_names)}) ===")
    for mid, mname in xbet_names[:10]:
        print(f"  ID: {mid}")
        print(f"  Name: {mname}")
        print()

    # Simulate what Bet365 names look like based on dashboard screenshot:
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
    
    print("\n=== Matching Test ===")
    for b365 in bet365_samples:
        best_score = 0
        best_match = ""
        for mid, mname in xbet_names:
            score = match_similarity(b365, mname)
            if score > best_score:
                best_score = score
                best_match = mname
        status = "MATCH" if best_score >= 0.72 else "NO MATCH"
        print(f"  B365: {b365}")
        print(f"  Best: {best_match} (score={best_score:.3f}) [{status}]")
        print()

asyncio.run(main())
