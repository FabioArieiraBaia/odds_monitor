import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        print("Acessando Bet365 (Tênis Ao Vivo)...")
        await page.goto("https://www.bet365.bet.br/#/IP/B13", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(10)
        
        await page.screenshot(path="bet365_debug.png", full_page=True)
        print("Screenshot salvo: bet365_debug.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
