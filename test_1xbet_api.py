import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(permissions=["geolocation"])
        page = await context.new_page()
        
        async def handle_response(response):
            try:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    data = await response.json()
                    # 1xBet JSON often contains "Value"
                    if isinstance(data, dict) and "Value" in data:
                        print("FOUND 1XBET API RESPONSE:", response.url)
                        print("Items count:", len(data.get("Value", [])))
            except:
                pass
                    
        page.on("response", handle_response)
        await page.goto("https://1xbet.bet.br/live")
        await asyncio.sleep(20)
        await browser.close()

asyncio.run(main())
