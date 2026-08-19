from pathlib import Path
import ast

p = Path("sources/betano_scraper.py")
text = p.read_text(encoding="utf-8")
start = text.find("    async def fetch_live_events(self)")
mid = text.find("            seen_ids = set()", start)
assert start > 0 and mid > start, (start, mid)

new = '''    async def fetch_live_events(self) -> List[NormalizedEvent]:
        """Fetch live events — UC Selenium only (Playwright CDP triggers Splash)."""
        if not self._is_running or (not self._uc_driver and not self.page):
            await self.start()
            if not self._is_running:
                return []

        if self._access_blocked:
            since = (datetime.now() - self._last_block_retry).total_seconds()
            if since < BLOCK_COOLDOWN_SECONDS:
                if int(since) % 60 < 8:
                    logger.warning(
                        f"[Betano] BLOQUEADO — retry em {int(BLOCK_COOLDOWN_SECONDS - since)}s"
                    )
                return []
            if self._uc_driver is not None:
                ok = await asyncio.to_thread(self._selenium_open_live)
                self._access_blocked = not ok
                if not ok:
                    self._last_block_retry = datetime.now()
                    return []
            else:
                return []

        events: List[NormalizedEvent] = []
        try:
            raw_data = []
            if self._uc_driver is not None:
                raw_data = await asyncio.to_thread(self._selenium_extract_raw_links)
                logger.info(f"[Betano] Selenium extract: {len(raw_data or [])} links")
            elif self.page:
                try:
                    raw_data = await self.page.evaluate("""() => {
                        const results=[], seen=new Set();
                        for (const a of document.querySelectorAll('a[href*=\"/live/\"]')) {
                          const bare=(a.getAttribute('href')||'').split('?')[0];
                          if (!/\\\\/live\\\\/.+\\\\/\\\\d{4,}/.test(bare) || seen.has(bare)) continue;
                          seen.add(bare);
                          const lines=(a.innerText||'').split('\\\\n').map(s=>s.trim()).filter(Boolean);
                          results.push({href:bare, lines});
                        }
                        return results;
                    }""")
                except Exception as pe:
                    logger.debug(f"[Betano] PW evaluate: {pe}")

            logger.info(f"[Betano] raw_links={len(raw_data or [])}")

'''

p.write_text(text[:start] + new + text[mid:], encoding="utf-8")
ast.parse(p.read_text(encoding="utf-8"))
print("OK patched fetch")
