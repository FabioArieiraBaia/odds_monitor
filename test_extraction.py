import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        sports = {
            "tabletennis": "B92",
            "basketball": "B18",
            "soccer": "B1"
        }
        
        for sport, code in sports.items():
            print(f"\n--- Testing {sport} ---")
            await page.goto(f"https://www.bet365.bet.br/#/IP/{code}")
            await asyncio.sleep(6)
            
            raw_data = await page.evaluate("""
                () => {
                    const results = [];
                    const selectors = ['.ovm-Fixture', '.ipe-EventViewDetail', '[class*="Fixture"][class*="ovm"]', '[class*="rcl-ParticipantFixture"]', '.gl-Market_General'];
                    let fixtures = [];
                    for (const sel of selectors) {
                        fixtures = document.querySelectorAll(sel);
                        if (fixtures.length > 0) break;
                    }
                    
                    for (const fixture of fixtures) {
                        let matchName = '';
                        const nameEls = fixture.querySelectorAll('.ovm-FixtureName_Name, [class*="ParticipantName"], [class*="TeamName"]');
                        if (nameEls.length >= 2) {
                            matchName = Array.from(nameEls).map(e => e.textContent.trim()).join(' vs ');
                        } else if (nameEls.length === 1) {
                            matchName = nameEls[0].textContent.trim();
                        }
                        
                        let scores = [];
                        function getLeafText(node) {
                            let t = [];
                            if (node.nodeType === Node.TEXT_NODE) {
                                if (node.textContent.trim()) t.push(node.textContent.trim());
                            } else {
                                for (let child of node.childNodes) t = t.concat(getLeafText(child));
                            }
                            return t;
                        }
                        
                        const scoreEls = fixture.querySelectorAll('[class*="Score"], [class*="score"], .ovm-ScoreWrapper_Score');
                        if (scoreEls.length > 0) {
                            for (const el of scoreEls) {
                                scores = scores.concat(getLeafText(el));
                            }
                        }
                        
                        if (matchName && scores.length > 0) {
                            results.push({ name: matchName, scores: scores });
                        }
                    }
                    return results;
                }
            """)
            for item in raw_data[:5]:
                print(f"{item['name']} => {item['scores']}")
                
        await browser.close()

asyncio.run(main())
