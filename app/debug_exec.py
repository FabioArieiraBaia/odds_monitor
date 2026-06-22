import asyncio
import os
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = os.path.join(os.getcwd(), "chrome_data2")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=chrome_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1920, "height": 1080},
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)
        
        print("Acessando Bet365 com executable_path...")
        await page.goto("https://www.bet365.bet.br/#/IP/B13", timeout=60000)
        await asyncio.sleep(10) # Timeout aumentado
        
        await page.screenshot(path="bet365_exec.png", full_page=True)
        print("Screenshot salvo: bet365_exec.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
