import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
    ctx = browser.contexts[0]
    page = ctx.pages[0]
    print("URL", page.url)

    info = await page.evaluate(
        """() => {
      const allA = Array.from(document.querySelectorAll('a')).slice(0, 80).map(a => ({
        href: a.getAttribute('href'),
        text: (a.innerText || '').slice(0, 120)
      }));
      const liveA = Array.from(document.querySelectorAll('a[href*="live"]')).map(a => a.getAttribute('href'));
      const body = (document.body && document.body.innerText) || '';
      return {
        title: document.title,
        bodyLen: body.length,
        bodySample: body.slice(0, 2000),
        liveCount: liveA.length,
        liveHrefs: liveA.slice(0, 40),
        sampleLinks: allA.filter(x => x.href).slice(0, 40)
      };
    }"""
    )
    print(json.dumps(info, indent=2, ensure_ascii=False)[:12000])
    html = await page.content()
    with open("debug_betano_live.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("html length", len(html))
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
