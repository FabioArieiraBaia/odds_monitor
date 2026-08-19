"""One-shot: inspect BetBurger live page via CDP port 9223."""
import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    except Exception as e:
        print("CDP connect failed:", e)
        await pw.stop()
        return

    page = browser.contexts[0].pages[0] if browser.contexts and browser.contexts[0].pages else None
    if not page:
        print("No page")
        await pw.stop()
        return

    print("URL before:", page.url)
    for url in [
        "https://www.betburger.com/events/live",
        "https://betburger.com/events/live",
    ]:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            break
        except Exception as e:
            print("goto fail", url, e)

    print("URL after:", page.url)
    print("title:", await page.title())

    data = await page.evaluate(
        """() => {
        const out = {
          bodyLen: (document.body.innerText||'').length,
          bodySample: (document.body.innerText||'').slice(0, 1500),
          rows: document.querySelectorAll('tr.events-table-row').length,
          surebets: document.querySelectorAll('.surebet, .arb, [class*="arb"]').length,
          sportFilters: Array.from(document.querySelectorAll('a,button,div,span,li'))
            .map(n => (n.innerText||'').trim())
            .filter(t => t && t.length < 40 && /table|tennis|mesa|ping|sport/i.test(t))
            .slice(0, 40),
        };
        const events = [];
        for (const row of document.querySelectorAll('tr.events-table-row')) {
          const tds = Array.from(row.querySelectorAll('td')).map(td => td.innerText.trim().slice(0,120));
          events.push({tds, text: (row.innerText||'').slice(0,200)});
          if (events.length >= 15) break;
        }
        // also try modern card layouts
        const cards = [];
        for (const el of document.querySelectorAll('[class*="event"]')) {
          const t = (el.innerText||'').trim();
          if (t.includes(' - ') && t.length > 15 && t.length < 300) {
            cards.push(t.slice(0, 200));
            if (cards.length >= 15) break;
          }
        }
        out.events = events;
        out.cards = cards;
        return out;
    }"""
    )
    print(json.dumps(data, indent=2, ensure_ascii=False)[:12000])
    html = await page.content()
    with open("debug_betburger_events_live.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("saved debug_betburger_events_live.html", len(html))
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
