import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    try:
        b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
        p = b.contexts[0].pages[0]
        print("URL", p.url)
        data = await p.evaluate(
            """() => {
            const out = [];
            const sels = [
              'a[href*="EV"]',
              '[onclick*="EV"]',
              '[data-nav*="EV"]',
              '[data-fixtureid]',
              '[data-eventid]',
              '[class*="Fixture"]',
              '[class*="ovm-Fixture"]',
            ];
            for (const sel of sels) {
              for (const el of document.querySelectorAll(sel)) {
                const href = el.getAttribute('href');
                const oc = el.getAttribute('onclick') || el.getAttribute('data-nav') || '';
                const attrs = {};
                for (const a of el.attributes || []) {
                  if (/ev|id|nav|fixture|event|ip/i.test(a.name)) attrs[a.name] = (a.value||'').slice(0,100);
                }
                const text = (el.innerText || '').replace(/\\s+/g,' ').slice(0,60);
                if (href || oc.includes('EV') || Object.keys(attrs).length) {
                  out.push({sel, tag: el.tagName, cls: String(el.className).slice(0,70), href, oc: oc.slice(0,120), attrs, text});
                }
                if (out.length >= 30) break;
              }
              if (out.length >= 30) break;
            }
            const html = document.documentElement.innerHTML;
            const evs = [...html.matchAll(/EV\\d{8,}[A-Z0-9]*/g)].map(m => m[0]);
            const uniq = [...new Set(evs)];
            // Find fixture-like containers near EV
            const fixtures = [];
            for (const el of document.querySelectorAll('[class*="ovm-Fixture"], [class*="FixtureDetails"]')) {
              const t = (el.innerText||'').replace(/\\s+/g,' ').slice(0,80);
              const htmlBit = el.outerHTML.slice(0,500);
              const m = htmlBit.match(/EV\\d{6,}[A-Z0-9]*/);
              fixtures.push({text: t, ev: m ? m[0] : null, cls: String(el.className).slice(0,60)});
              if (fixtures.length >= 12) break;
            }
            return {samples: out.slice(0,25), evUnique: uniq.slice(0,25), fixtures};
        }"""
        )
        print(json.dumps(data, indent=2, ensure_ascii=False)[:8000])
    except Exception as e:
        print("FAIL", e)
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
