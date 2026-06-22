import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import os

async def main():
    user_data_dir = os.path.join(os.getcwd(), "browser_data")
    async with async_playwright() as p:
        # Use persistent context to save cookies/cache and bypass basic anti-bot
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        print("Acessando Bet365 (Tênis Ao Vivo) com Persistent Context...")
        await page.goto("https://www.bet365.bet.br/#/IP/B13", timeout=60000)
        await asyncio.sleep(10)
        
        await page.screenshot(path="bet365_persistent.png", full_page=True)
        print("Screenshot salvo: bet365_persistent.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
