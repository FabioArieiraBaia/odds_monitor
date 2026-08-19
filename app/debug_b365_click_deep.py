import asyncio
import json
import re
from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
    p = b.contexts[0].pages[0]
    print("URL", p.url)

    # Capture websocket frames
    frames = []

    def on_frame(payload):
        try:
            s = payload if isinstance(payload, str) else str(payload)
            if "EV" in s or "FI" in s:
                frames.append(s[:300])
        except Exception:
            pass

    p.on("websocket", lambda ws: ws.on("framereceived", lambda payload: on_frame(payload)))

    fixt = p.locator(".ovm-Fixture").first
    name = (await fixt.inner_text())[:60].replace("\n", " ")
    print("fixture", name)

    # double click
    await fixt.dblclick(timeout=3000)
    await asyncio.sleep(2)
    print("after dblclick url", p.url)

    # Check for market / event header in DOM
    info = await p.evaluate(
        """() => {
        const html = document.documentElement.innerHTML;
        const evs = [...new Set([...html.matchAll(/EV\\d{8,}[A-Z0-9]*/g)].map(m=>m[0]))];
        // visible panels
        const panels = [];
        for (const el of document.querySelectorAll('[class*="Market"],[class*="Event"],[class*="Detail"],[class*="Splash"]')) {
          const t = (el.innerText||'').replace(/\\s+/g,' ').slice(0,80);
          if (t.length > 10) panels.push({cls: String(el.className).slice(0,60), t});
          if (panels.length >= 15) break;
        }
        return {evs: evs.slice(0,20), panels, hash: location.hash};
    }"""
    )
    print(json.dumps(info, indent=2, ensure_ascii=False)[:5000])
    print("ws frames", len(frames))
    for f in frames[:15]:
        print(" WS", f[:200])

    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
