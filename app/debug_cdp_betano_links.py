import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    b = await pw.chromium.connect_over_cdp("http://127.0.0.1:50576")
    # all pages
    for ctx in b.contexts:
        for i, p in enumerate(ctx.pages):
            print("PAGE", i, p.url, await p.title())
    page = b.contexts[0].pages[-1]
    try:
        await page.goto("https://www.betano.bet.br/live/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
    except Exception as e:
        print("goto", e)
    data = await page.evaluate(
        """() => {
        const all = Array.from(document.querySelectorAll('a[href]')).map(a => ({
          href: a.getAttribute('href'),
          text: (a.innerText||'').replace(/\\s+/g,' ').slice(0,50)
        }));
        const live = all.filter(x => (x.href||'').includes('live') || /\\d{5,}/.test(x.href||''));
        // also data-qa event cards
        const cards = Array.from(document.querySelectorAll('[data-qa], [class*=\"event\"], [class*=\"Event\"]'))
          .slice(0,30).map(el => ({
            qa: el.getAttribute('data-qa'),
            cls: String(el.className).slice(0,60),
            text: (el.innerText||'').replace(/\\s+/g,' ').slice(0,80),
            href: el.closest('a') && el.closest('a').getAttribute('href')
          }));
        return {
          url: location.href,
          title: document.title,
          bodyLen: (document.body.innerText||'').length,
          bodyHead: (document.body.innerText||'').slice(0,400),
          liveHrefs: live.slice(0,40),
          cards: cards.slice(0,20),
          totalA: all.length
        };
    }"""
    )
    print(json.dumps(data, indent=2, ensure_ascii=False)[:12000])
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
