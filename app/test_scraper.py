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
        print(f"{e.match_name} - Sets: {e.set_score}, Games: {e.game_score}, Pts: {e.point_score} -> {e.deep_link}")
        
    # Let's search all global JS namespaces for EV event IDs
    fiber_results = await scraper.page.evaluate("""
        () => {
            const matches = [];
            const seen = new Set();
            
            function search(obj, path = '', depth = 0) {
                if (!obj || depth > 4 || seen.has(obj)) return;
                seen.add(obj);
                
                for (const k in obj) {
                    try {
                        const val = obj[k];
                        const currentPath = path ? `${path}.${k}` : k;
                        
                        if (typeof val === 'string' && /^EV\d+/.test(val) && val.length > 5) {
                            matches.push({ path: currentPath, val: val });
                        } else if (typeof val === 'object' && val !== null) {
                            search(val, currentPath, depth + 1);
                        }
                    } catch(e) {}
                }
            }
            
            // Search interesting global namespaces
            for (const key in window) {
                if (key.startsWith('ns_') || key.includes('Lib') || key.includes('Module') || key === 'Locator') {
                    search(window[key], key);
                }
            }
            
            return matches.slice(0, 100);
        }
    """)
    print("\n--- Eventos Encontrados na Memória Global JS ---")
    print(f"Total matches found in JS memory: {len(fiber_results)}")
    for idx, item in enumerate(fiber_results[:20]):
        print(f"  [{idx+1}] Path: {item['path']} | Value: {item['val']}")
    print("------------------------------------------------\n")
    
    await scraper.page.screenshot(path="debug_bet365_final.png", full_page=True)
    html = await scraper.page.content()
    with open("debug_bet365_real.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    await scraper.stop()

if __name__ == "__main__":
    asyncio.run(main())
