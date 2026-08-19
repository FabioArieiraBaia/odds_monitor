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
        const out = {topics: [], fixtures: [], errors: []};
        try {
          const L = window.Locator;
          if (!L) { out.errors.push('no Locator'); return out; }
          out.locatorKeys = Object.keys(L).slice(0, 40);
          if (L.treeLookup) {
            out.treeKeys = Object.keys(L.treeLookup).slice(0, 30);
            // Try common methods
            const tl = L.treeLookup;
            const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(tl)||{}).concat(Object.keys(tl));
            out.treeMethods = [...new Set(methods)].slice(0, 50);
          }
          // Scan global for EV-looking strings near table tennis
          const walk = (obj, path, depth, acc) => {
            if (depth > 4 || !obj || typeof obj !== 'object') return;
            if (acc.length > 40) return;
            try {
              if (Array.isArray(obj)) {
                for (let i=0;i<Math.min(obj.length,30);i++) walk(obj[i], path+'['+i+']', depth+1, acc);
                return;
              }
              const keys = Object.keys(obj);
              for (const k of keys.slice(0, 40)) {
                const v = obj[k];
                if (typeof v === 'string') {
                  if (/^EV\\d{6,}/.test(v) || (k.match(/FI|ID|EV|IT/i) && /\\d{6,}/.test(v))) {
                    acc.push({path: path+'.'+k, value: v.slice(0,80)});
                  }
                } else if (typeof v === 'object' && v) {
                  // fixture-like
                  if (v.NA && (v.FI || v.ID || v.IT || v.EV)) {
                    acc.push({path: path+'.'+k, NA: v.NA, FI: v.FI||v.ID||v.IT||v.EV, keys: Object.keys(v).slice(0,15)});
                  }
                  walk(v, path+'.'+k, depth+1, acc);
                }
              }
            } catch(e) {}
          };
          const acc = [];
          // Known globals
          for (const g of ['Locator', 'bet365', 'ns_gen5_data', 'ns_gen5_util']) {
            try { walk(window[g], g, 0, acc); } catch(e) { out.errors.push(g+':'+e.message); }
          }
          out.acc = acc.slice(0, 50);
        } catch(e) {
          out.errors.push(String(e));
        }
        return out;
    }"""
    )
    print(json.dumps(data, indent=2, ensure_ascii=False)[:12000])
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
