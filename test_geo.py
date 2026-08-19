import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        
        # Correto: grant para a origem especifica
        await context.grant_permissions(["geolocation"], origin="https://1xbet.bet.br")
        await context.set_geolocation({"latitude": -23.5505, "longitude": -46.6333})
        
        page = await context.new_page()
        await page.goto("https://1xbet.bet.br/live")
        await asyncio.sleep(10)
        print("URL after 10s:", page.url)
        await browser.close()

asyncio.run(main())
