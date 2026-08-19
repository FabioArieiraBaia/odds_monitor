"""Click Table Tennis on BetBurger events/live and dump rows."""
import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].pages[0]

    await page.goto("https://www.betburger.com/events/live", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Open sports multiselect if needed and select Table Tennis
    clicked = await page.evaluate(
        """() => {
        const nodes = Array.from(document.querySelectorAll('a,button,div,span,li,label'));
        const hits = [];
        for (const n of nodes) {
          const t = (n.innerText || '').trim().replace(/\\s+/g, ' ');
          if (!t || t.length > 40) continue;
          if (/^table tennis$/i.test(t) || t.toLowerCase() === 'table tennis') {
            n.click();
            hits.push(t);
          }
        }
        return hits;
    }"""
    )
    print("clicked:", clicked)
    await asyncio.sleep(4)

    # Also try checkbox by text
    try:
        loc = page.get_by_text("Table Tennis", exact=True)
        count = await loc.count()
        print("exact count", count)
        if count:
            await loc.first.click(timeout=3000)
            await asyncio.sleep(3)
    except Exception as e:
        print("locator click:", e)

    data = await page.evaluate(
        """() => {
        const rows = [];
        for (const row of document.querySelectorAll('tr.events-table-row, tr[class*="event"]')) {
          const tds = Array.from(row.querySelectorAll('td')).map(td => (td.innerText||'').trim());
          if (tds.length) rows.push(tds);
          if (rows.length >= 25) break;
        }
        return {
          url: location.href,
          bodyLen: (document.body.innerText||'').length,
          sample: (document.body.innerText||'').slice(0, 2000),
          rowCount: document.querySelectorAll('tr.events-table-row').length,
          rows,
        };
    }"""
    )
    print(json.dumps(data, indent=2, ensure_ascii=False)[:15000])
    with open("debug_betburger_tt.html", "w", encoding="utf-8") as f:
        f.write(await page.content())
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
