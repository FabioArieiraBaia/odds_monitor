import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
    p = b.contexts[0].pages[0]
    print("URL", p.url)

    data = await p.evaluate(
        """() => {
        const fixtures = Array.from(document.querySelectorAll('.ovm-Fixture'));
        const out = [];
        for (const f of fixtures.slice(0, 8)) {
          const name = (f.innerText||'').replace(/\\s+/g,' ').slice(0,80);
          // all attributes on fixture and descendants depth 3
          const attrHits = [];
          const walk = (el, depth) => {
            if (!el || depth > 4) return;
            if (el.attributes) {
              for (const a of el.attributes) {
                const v = a.value || '';
                if (/EV\\d|fixture|event|\\d{8,}/i.test(a.name+' '+v)) {
                  attrHits.push({tag: el.tagName, name: a.name, value: v.slice(0,120), cls: String(el.className).slice(0,50)});
                }
              }
            }
            for (const c of el.children || []) walk(c, depth+1);
          };
          walk(f, 0);
          // outerHTML sniff for IDs
          const html = f.outerHTML;
          const evs = [...html.matchAll(/EV\\d{6,}[A-Z0-9]*/g)].map(m=>m[0]);
          const nums = [...html.matchAll(/\\b\\d{9,}\\b/g)].map(m=>m[0]);
          out.push({name, attrHits: attrHits.slice(0,15), evs: [...new Set(evs)], nums: [...new Set(nums)].slice(0,10), htmlLen: html.length});
        }
        // Also check window/__INITIAL or similar
        const keys = Object.keys(window).filter(k => /bet|fixture|sport|app|ns_/i.test(k)).slice(0,40);
        return {out, windowKeys: keys};
    }"""
    )
    print(json.dumps(data, indent=2, ensure_ascii=False)[:10000])

    # Try click first fixture and capture URL change
    try:
        before = p.url
        box = await p.locator(".ovm-Fixture").first.bounding_box()
        if box:
            await p.locator(".ovm-Fixture").first.click(timeout=3000)
            await asyncio.sleep(2)
            after = p.url
            print("CLICK before", before)
            print("CLICK after", after)
            # go back to list
            await p.goto("https://www.bet365.bet.br/#/IP/B92", wait_until="commit")
            await asyncio.sleep(3)
    except Exception as e:
        print("click fail", e)

    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
