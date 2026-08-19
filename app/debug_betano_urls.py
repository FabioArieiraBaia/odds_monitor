import asyncio
import json
from playwright.async_api import async_playwright

URLS = [
    "https://www.betano.bet.br/live/",
    "https://www.betano.bet.br/sport/ao-vivo/",
    "https://br.betano.com/live/",
    "https://www.betano.bet.br/odds/live/",
    "https://www.betano.bet.br/live/tennis/",
    "https://www.betano.bet.br/live/table-tennis/",
    "https://www.betano.bet.br/live/tenis/",
]


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
    page = browser.contexts[0].pages[0]

    for url in URLS:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(5)
            title = await page.title()
            data = await page.evaluate(
                """() => {
                const body = (document.body && document.body.innerText) || '';
                const hrefs = Array.from(document.querySelectorAll('a'))
                  .map(a => a.getAttribute('href'))
                  .filter(Boolean)
                  .filter(h => /live|ao-vivo|tenis|mesa|table|sport/i.test(h));
                const uniq = [...new Set(hrefs)].slice(0, 50);
                return { body: body.slice(0, 500), hrefs: uniq, bodyLen: body.length };
            }"""
            )
            print("===", url, "===")
            print("final:", page.url)
            print("title:", title)
            print("bodyLen:", data["bodyLen"])
            print("body:", data["body"][:250].replace("\n", " | "))
            print("hrefs:", json.dumps(data["hrefs"][:30], ensure_ascii=False))
            print()
            if data["bodyLen"] > 300 and "not found" not in title.lower():
                with open("debug_betano_live.html", "w", encoding="utf-8") as f:
                    f.write(await page.content())
                print("SAVED HTML from", page.url)
                break
        except Exception as e:
            print("FAIL", url, e)

    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
