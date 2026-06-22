import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        print("Navigating to br.1xbet.com/live...")
        try:
            await page.goto("https://1xbet.com/br/live", timeout=30000)
            await asyncio.sleep(5)
            html = await page.content()
            with open("1xbet_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
            
            events = await page.eval_on_selector_all('.c-events__item', '''els => els.map(el => {
                return el.innerText;
            })''')
            print(f"Found {len(events)} events.")
            if len(events) > 0:
                print(events[0])
            
            with open("1xbet_dump.txt", "w", encoding="utf-8") as f:
                for e in events:
                    f.write(e + "\n---\n")
        except Exception as e:
            print("Error:", e)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
