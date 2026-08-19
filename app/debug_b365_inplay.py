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
        const out = {};
        try {
          const ip = Locator.inplayEvents;
          out.type = typeof ip;
          out.keys = ip ? Object.keys(ip).slice(0, 40) : [];
          out.proto = ip ? Object.getOwnPropertyNames(Object.getPrototypeOf(ip)||{}).slice(0,40) : [];
          // try dump internal
          const dump = (obj, depth=0) => {
            if (!obj || depth>3) return null;
            if (typeof obj !== 'object') return obj;
            if (Array.isArray(obj)) return obj.slice(0,5).map(x => dump(x, depth+1));
            const r = {};
            for (const k of Object.keys(obj).slice(0, 25)) {
              try {
                const v = obj[k];
                if (v == null) r[k]=null;
                else if (typeof v === 'function') r[k]='[fn]';
                else if (typeof v !== 'object') r[k]=v;
                else if (Array.isArray(v)) r[k]=`[array:${v.length}]`;
                else r[k]=`[obj keys=${Object.keys(v).slice(0,8).join(',')}]`;
              } catch(e) { r[k]='err'; }
            }
            return r;
          };
          out.dump = dump(ip);
          // Common method names
          for (const m of ['getEvents','getAll','getFixtures','getData','events','fixtures','getInPlayEvents','toArray']) {
            if (ip && typeof ip[m] === 'function') {
              try {
                const r = ip[m]();
                out['call_'+m] = dump(r, 0);
                if (Array.isArray(r)) {
                  out['call_'+m+'_sample'] = r.slice(0,3).map(x => {
                    if (!x || typeof x !== 'object') return x;
                    const o={};
                    for (const k of Object.keys(x).slice(0,20)) {
                      const v=x[k];
                      if (v==null || typeof v!=='object') o[k]=v;
                      else o[k]=String(v).slice(0,40);
                    }
                    return o;
                  });
                }
              } catch(e) { out['call_'+m+'_err']=e.message; }
            }
          }
          // Read private-ish fields
          for (const k of Object.keys(ip||{})) {
            try {
              const v = ip[k];
              if (Array.isArray(v) && v.length && v[0] && (v[0].NA || v[0].FI || v[0].ID)) {
                out['arr_'+k] = v.slice(0,5).map(x => ({NA:x.NA, FI:x.FI, ID:x.ID, IT:x.IT, EV:x.EV, CL:x.CL, keys:Object.keys(x).slice(0,15)}));
              }
              if (v && typeof v === 'object' && !Array.isArray(v) && (v.NA || v.FI)) {
                out['obj_'+k] = {NA:v.NA, FI:v.FI, keys:Object.keys(v).slice(0,20)};
              }
            } catch(e) {}
          }
        } catch(e) {
          out.error = String(e);
        }
        return out;
    }"""
    )
    print(json.dumps(data, indent=2, ensure_ascii=False)[:15000])
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
