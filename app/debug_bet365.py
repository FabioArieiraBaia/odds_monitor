import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        print("Acessando Bet365 (Tênis Ao Vivo)...")
        await page.goto("https://www.bet365.bet.br/#/IP/B13", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)
        
        # Test the same JS evaluate from our scraper
        raw_data = await page.evaluate("""
            () => {
                const results = [];
                const selectors = ['.ovm-Fixture', '.ipe-EventViewDetail', '[class*="Fixture"][class*="ovm"]', '[class*="rcl-ParticipantFixture"]', '.gl-Market_General'];
                
                let fixtures = [];
                for (const sel of selectors) {
                    fixtures = document.querySelectorAll(sel);
                    if (fixtures.length > 0) break;
                }
                
                if (fixtures.length === 0) {
                    const allElements = document.querySelectorAll('[class*="Participant"], [class*="Team"]');
                    const parents = new Set();
                    allElements.forEach(el => {
                        if (el.parentElement) parents.add(el.parentElement);
                    });
                    fixtures = Array.from(parents);
                }
                
                return {
                    count: fixtures.length,
                    html: fixtures.length > 0 ? fixtures[0].outerHTML.substring(0, 500) : "No fixtures found"
                };
            }
        """)
        
        print(f"Resultado do evaluate: {raw_data}")
        
        # Get full body HTML for debugging just in case
        body = await page.content()
        with open("debug_bet365.html", "w", encoding="utf-8") as f:
            f.write(body)
            
        print("HTML salvo em debug_bet365.html")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
