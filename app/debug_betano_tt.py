import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9224")
    page = browser.contexts[0].pages[0]
    await page.goto("https://www.betano.bet.br/live/", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # Try click table tennis
    clicked = await page.evaluate(
        """() => {
        const nodes = Array.from(document.querySelectorAll('a,button,div,span'));
        for (const n of nodes) {
          const t = (n.innerText || '').trim();
          if (/t[eê]nis de mesa/i.test(t) && t.length < 40) {
            n.click();
            return t;
          }
        }
        return null;
    }"""
    )
    print("clicked:", clicked)
    await asyncio.sleep(4)
    print("url:", page.url)

    data = await page.evaluate(
        """() => {
        const links = Array.from(document.querySelectorAll('a[href*="/live/"]'));
        const results = [];
        const seen = new Set();
        for (const a of links) {
          const href = a.getAttribute('href') || '';
          if (!/\\/live\\/[^/]+\\/\\d+\\/?/.test(href)) continue;
          if (seen.has(href)) continue;
          seen.add(href);
          let root = a;
          for (let i = 0; i < 5 && root.parentElement; i++) {
            root = root.parentElement;
            if ((root.innerText || '').split('\\n').length >= 3) break;
          }
          const text = (root.innerText || a.innerText || '').trim();
          const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
          results.push({ href, lines: lines.slice(0, 20) });
        }
        return results;
    }"""
    )
    print("events:", len(data))
    print(json.dumps(data[:8], indent=2, ensure_ascii=False))
    with open("debug_betano_tt.html", "w", encoding="utf-8") as f:
        f.write(await page.content())
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
