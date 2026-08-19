import asyncio
import re
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
    p = b.contexts[0].pages[0]
    print("URL", p.url)

    hits = []

    def on_response(resp):
        try:
            u = resp.url
            if any(x in u.lower() for x in ("sports", "inplay", "fixture", "event", "coupon", "ip")):
                hits.append(u[:200])
        except Exception:
            pass

    p.on("response", on_response)

    # Click a few fixtures
    count = await p.locator(".ovm-Fixture").count()
    print("fixtures", count)
    for i in range(min(3, count)):
        try:
            fixt = p.locator(".ovm-Fixture").nth(i)
            name = (await fixt.inner_text())[:50].replace("\n", " ")
            await fixt.click(timeout=2000)
            await asyncio.sleep(1.5)
            print(f"clicked [{i}] {name!r} url={p.url}")
        except Exception as e:
            print("click err", e)

    await asyncio.sleep(2)
    print("network sample", len(hits))
    for u in hits[:30]:
        print(" ", u)

    # Evaluate internal Locator / tree for fixture ids
    internal = await p.evaluate(
        """() => {
        const res = {found: []};
        try {
          if (window.Locator && Locator.treeLookup) {
            res.hasLocator = true;
          }
        } catch(e) {}
        // Search all script text? too heavy
        // Walk DOM for react fiber props
        const fixtures = document.querySelectorAll('.ovm-Fixture');
        for (const f of fixtures) {
          const keys = Object.keys(f);
          const fiberKey = keys.find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
          let props = null;
          if (fiberKey) {
            let fiber = f[fiberKey];
            for (let i=0;i<12 && fiber;i++) {
              if (fiber.memoizedProps && (fiber.memoizedProps.fixture || fiber.memoizedProps.eventId || fiber.memoizedProps.id || fiber.memoizedProps.FI)) {
                props = fiber.memoizedProps;
                break;
              }
              fiber = fiber.return;
            }
          }
          const name = (f.innerText||'').replace(/\\s+/g,' ').slice(0,50);
          let dump = null;
          if (props) {
            dump = {};
            for (const [k,v] of Object.entries(props)) {
              if (v == null) continue;
              if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') dump[k]=v;
              else if (typeof v === 'object' && v.ID) dump[k]={ID:v.ID, NA:v.NA};
              if (Object.keys(dump).length > 20) break;
            }
          }
          res.found.push({name, fiberKey: !!fiberKey, props: dump});
          if (res.found.length >= 5) break;
        }
        return res;
    }"""
    )
    import json
    print(json.dumps(internal, indent=2, ensure_ascii=False)[:8000])
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
