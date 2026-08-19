"""
Betano Real-Time Scraper using Playwright & CDP.
Scrapes live events from https://www.betano.bet.br/live/
(NOTE: /live/tenis-de-mesa/ returns 404 on Betano BR — always use /live/)
"""
import asyncio
import re
import logging
import subprocess
import os
import time
from typing import List, Optional, Tuple
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from sources.base_source import BaseSource
from core.normalizer import NormalizedEvent
from core.optical_reader import OpticalScoreboardReader

logger = logging.getLogger("betano_scraper")

# Betano live hub (sport filter applied in-page — /live/tenis-de-mesa/ returns 404)
BETANO_HOME_URL = "https://www.betano.bet.br/"
BETANO_LIVE_URL = "https://www.betano.bet.br/live/"
BETANO_LIVE_FALLBACK = "https://www.betano.bet.br/"
# Alternate entry points if /live/ is WAF-blocked
BETANO_URL_CANDIDATES = [
    "https://www.betano.bet.br/",
    "https://www.betano.bet.br/live/",
    "https://betano.bet.br/",
    "https://betano.bet.br/live/",
]
# After compliance block, cool down before hammering WAF again
BLOCK_COOLDOWN_SECONDS = 120  # 2 minutes (was 10 — too long when splash is transient)

# Labels that must never be treated as player names
IGNORE_LABELS = {
    "ao vivo", "live", "set", "game", "pts", "pontos", "games",
    "tênis de mesa", "tenis de mesa", "table tennis", "ping pong",
    "superodds", "super odds", "1º set", "2º set", "3º set", "4º set", "5º set",
    "1o set", "2o set", "3o set", "4o set", "5o set",
    "copa setka", "setka cup", "liga pro", "tt-cup", "tt cup", "tt cup.",
    "set 1", "set 2", "set 3", "set 4", "set 5",
    "1 set", "2 set", "3 set", "4 set", "5 set",
    "final", "semi", "quartas", "hoje", "amanhã", "amanha",
    "masculino", "feminino", "duplas", "singles", "doubles",
    "betano", "estatísticas", "estatisticas", "mercados", "ao-vivo",
}

IGNORE_EXACT_RE = re.compile(
    r"^(set\s*\d+|s\d+|g\s*\d+|pts?|ao\s*vivo|live|\d+\s*[ºo°]?\s*set)$",
    re.IGNORECASE,
)


class BetanoScraper(BaseSource):
    """
    Real Playwright-based scraper for Betano live in-play events.
    Launches Chrome via CDP on port 9224, navigates to live table tennis,
    and extracts structured match and score data.
    """
    def __init__(self, headless: bool = True, sports: List[str] = None):
        super().__init__()
        self.headless = headless
        self.sports = sports or ["tabletennis"]
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.chrome_process: Optional[subprocess.Popen] = None
        self._uc_driver = None  # undetected_chromedriver handle
        self._is_running = False
        self._last_reload = datetime.now()
        self._launch_lock = asyncio.Lock()
        self._consecutive_errors = 0
        self._access_blocked = False
        self._last_block_retry = datetime.min
        self._profile_suffix = self._load_profile_suffix()
        self._in_recovery = False
        self._debug_port = 9224
        self._optical_reader = OpticalScoreboardReader()

    def get_name(self) -> str:
        return "betano"

    def _profile_state_path(self) -> str:
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", "."),
            "OddsDivergenceMonitor",
        )
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "betano_profile_suffix.txt")

    def _load_profile_suffix(self) -> str:
        """Reuse last known-good UC profile (avoids burned splash profiles)."""
        try:
            p = self._profile_state_path()
            if os.path.isfile(p):
                s = open(p, "r", encoding="utf-8").read().strip()
                if s and re.match(r"^betano_uc[\w\-]+$", s):
                    return s
        except Exception:
            pass
        return "betano_uc_stable"

    def _save_profile_suffix(self, suffix: str) -> None:
        try:
            with open(self._profile_state_path(), "w", encoding="utf-8") as f:
                f.write(suffix)
        except Exception:
            pass

    def _profile_dir(self) -> str:
        d = os.path.join(
            os.environ.get("LOCALAPPDATA", "."),
            "OddsDivergenceMonitor",
            f"chrome_data_{self._profile_suffix}",
        )
        os.makedirs(d, exist_ok=True)
        return d

    async def start(self):
        await self._launch_browser()

    def _kill_stale_uc_drivers(self):
        """Best-effort: free locked chromedriver / old UC chrome before relaunch."""
        try:
            # chromedriver orphans often crash the next UC launch hard
            subprocess.run(
                ["taskkill", "/IM", "chromedriver.exe", "/F"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        try:
            uc_home = os.path.join(os.environ.get("APPDATA", ""), "undetected_chromedriver")
            stale = os.path.join(uc_home, "undetected_chromedriver.exe")
            if os.path.exists(stale):
                try:
                    os.remove(stale)
                except Exception:
                    pass
        except Exception:
            pass

    def _launch_uc_chrome(self, user_data_dir: str):
        """
        Launch Chrome via undetected_chromedriver (best anti-bot on this machine).
        IMPORTANT: UC picks its own debugger port — read it from capabilities.
        NEVER pass --disable-blink-features=AutomationControlled (Betano WAF + yellow bar).
        """
        import undetected_chromedriver as uc

        self._kill_stale_uc_drivers()
        time.sleep(0.5)

        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--window-size=1366,1200")
        options.add_argument("--lang=pt-BR")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--mute-audio")

        logger.info("[Betano] Launch via undetected_chromedriver (anti-WAF)...")
        # Flush logs before native UC call (can hard-crash the process)
        for h in logging.root.handlers:
            try:
                h.flush()
            except Exception:
                pass
        chrome_major = 151
        try:
            import subprocess
            out = subprocess.check_output(r'powershell -Command "(Get-Item \'C:\Program Files\Google\Chrome\Application\chrome.exe\').VersionInfo.Major"', shell=True, text=True).strip()
            if out.isdigit():
                chrome_major = int(out)
        except Exception:
            pass

        driver = uc.Chrome(options=options, headless=False, use_subprocess=True, version_main=chrome_major)
        time.sleep(2)
        try:
            driver.get("about:blank")
        except Exception:
            pass
        dbg = (driver.capabilities.get("goog:chromeOptions") or {}).get("debuggerAddress")
        logger.info(f"[Betano] UC debuggerAddress={dbg}")
        return driver, dbg

    def _launch_clean_chrome_subprocess(self, chrome_path: str, port: int, user_data_dir: str):
        """Fallback: real Chrome with ZERO automation flags (no yellow bar)."""
        logger.info("[Betano] Launch Chrome limpo (sem flags de automação)...")
        return subprocess.Popen([
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1366,1200",
            "--lang=pt-BR",
            "about:blank",
        ])

    async def _launch_browser(self):
        """Launch stealth Chrome for Betano (undetected_chromedriver preferred)."""
        async with self._launch_lock:
            if self._is_running:
                return
            try:
                possible_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                ]
                chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
                if not chrome_path:
                    logger.error("[Betano] Chrome binary not found.")
                    return

                port = self._debug_port
                user_data_dir = self._profile_dir()
                cdp_url = f"http://127.0.0.1:{port}"

                launched = False
                # 1) Prefer undetected_chromedriver (proven to pass Betano WAF on this PC)
                try:
                    self._uc_driver, dbg = await asyncio.to_thread(
                        self._launch_uc_chrome, user_data_dir
                    )
                    if dbg:
                        cdp_url = f"http://{dbg}"
                        try:
                            self._debug_port = int(str(dbg).split(":")[-1])
                        except Exception:
                            pass
                    launched = True
                    logger.info(f"[Betano] undetected_chromedriver OK → {cdp_url}")
                except Exception as e:
                    logger.warning(f"[Betano] undetected_chromedriver falhou: {e} — fallback Chrome limpo")
                    self._uc_driver = None

                # CRITICAL path for UC:
                # Navigate with Selenium ONLY — NEVER attach Playwright CDP first.
                # Playwright connect_over_cdp re-triggers Betano "Splash Screen".
                if self._uc_driver is not None:
                    self._is_running = True
                    self._consecutive_errors = 0
                    self.page = None
                    self.context = None
                    self.browser = None
                    self._pw = None

                    ok = await asyncio.to_thread(self._selenium_open_live)
                    if not ok:
                        # One fresh-profile retry (splash often sticks to burned profile)
                        logger.warning("[Betano] Splash/vazio no perfil atual — tentando perfil fresco...")
                        try:
                            await asyncio.to_thread(self._uc_driver.quit)
                        except Exception:
                            pass
                        self._uc_driver = None
                        self._profile_suffix = f"betano_uc_{int(time.time())}"
                        user_data_dir = self._profile_dir()
                        try:
                            self._uc_driver, dbg = await asyncio.to_thread(
                                self._launch_uc_chrome, user_data_dir
                            )
                            if dbg:
                                try:
                                    self._debug_port = int(str(dbg).split(":")[-1])
                                except Exception:
                                    pass
                            ok = await asyncio.to_thread(self._selenium_open_live)
                        except Exception as e2:
                            logger.error(f"[Betano] retry UC falhou: {e2}")
                            ok = False

                    self._access_blocked = not ok
                    if ok:
                        self._save_profile_suffix(self._profile_suffix)
                        logger.info(
                            f"[Betano] UC Selenium live OK (anti-WAF, sem Playwright CDP) "
                            f"perfil={self._profile_suffix}"
                        )
                    else:
                        self._last_block_retry = datetime.now()
                        logger.error(
                            "[Betano] UC abriu mas live ainda bloqueado/vazio. "
                            "Confirme IP BR sem VPN e cookies na janela Chrome. "
                            f"Perfil: {user_data_dir}"
                        )
                    return

                # 2) Fallback clean Chrome + Playwright CDP (no UC)
                try:
                    subprocess.run(
                        f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{port}\') do taskkill /PID %a /T /F',
                        shell=True, capture_output=True, timeout=4,
                    )
                except Exception:
                    pass
                await asyncio.sleep(1)
                self.chrome_process = self._launch_clean_chrome_subprocess(
                    chrome_path, port, user_data_dir
                )
                await asyncio.sleep(5)
                cdp_url = f"http://127.0.0.1:{port}"

                self._pw = await async_playwright().start()
                logger.info(f"[Betano] Conectando Playwright CDP {cdp_url}...")
                self.browser = await self._pw.chromium.connect_over_cdp(cdp_url, timeout=60000)

                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                    self.page = (
                        self.context.pages[0]
                        if self.context.pages
                        else await self.context.new_page()
                    )
                else:
                    self.context = await self.browser.new_context(locale="pt-BR")
                    self.page = await self.context.new_page()

                try:
                    await self.page.set_viewport_size({"width": 1366, "height": 768})
                except Exception:
                    pass

                self._is_running = True
                self._consecutive_errors = 0

                await self._navigate_to_live()
                if await self._is_access_restricted():
                    self._access_blocked = True
                    self._last_block_retry = datetime.now()
                    logger.error("[Betano] BLOQUEIO compliance (fallback Chrome).")
                else:
                    self._access_blocked = False
                    logger.info("[Betano] Browser fallback acessível")

            except Exception as e:
                logger.error(f"[Betano] Error launching browser: {e}")
                await self._cleanup()

    async def _cleanup(self):
        """Cleanup browser resources."""
        self._is_running = False
        for attr, label in [("page", "page"), ("context", "context"), ("browser", "browser")]:
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                await obj.close()
            except Exception as e:
                logger.debug(f"[Betano] Error closing {label}: {e}")
            setattr(self, attr, None)

        try:
            if hasattr(self, "_pw") and self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self._pw = None

        # Close undetected driver
        if self._uc_driver is not None:
            try:
                await asyncio.to_thread(self._uc_driver.quit)
            except Exception:
                try:
                    self._uc_driver.quit()
                except Exception:
                    pass
            self._uc_driver = None

        if self.chrome_process:
            pid = self.chrome_process.pid
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5)
            except Exception:
                try:
                    self.chrome_process.terminate()
                except Exception:
                    pass
            self.chrome_process = None

        # Safety: free debug port
        try:
            subprocess.run(
                f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{self._debug_port}\') do taskkill /PID %a /T /F',
                shell=True, capture_output=True, timeout=3,
            )
        except Exception:
            pass

    async def stop(self):
        await self._cleanup()

    async def _is_splash_screen(self) -> bool:
        """Detect Betano anti-bot splash screen."""
        try:
            title = (await self.page.title() or "").lower()
            if "splash" in title or title == "":
                # Verify body is empty too
                link_count = await self.page.evaluate("() => document.querySelectorAll('a').length")
                if link_count < 3:
                    return True
        except Exception:
            pass
        return False

    async def _restart_browser(self):
        """Full restart with a fresh Chrome profile (helps after WAF block)."""
        import time
        logger.warning("[Betano] Full browser restart (fresh profile)...")
        self._is_running = False
        await self._cleanup()
        self._profile_suffix = f"betano_{int(time.time())}"
        await self._launch_browser()

    async def _page_body_sample(self) -> str:
        try:
            return await self.page.evaluate(
                "() => (document.body && document.body.innerText || '').slice(0, 800)"
            ) or ""
        except Exception:
            return ""

    async def _is_access_restricted(self) -> bool:
        """
        Detect Betano WAF / compliance block:
        'Access to this page is restricted due to security and compliance measures.'
        """
        try:
            title = (await self.page.title() or "").lower()
            body = (await self._page_body_sample()).lower()
            markers = (
                "access to this page is restricted",
                "security and compliance",
                "compliance measures",
                "acesso a esta página está restrito",
                "acesso a esta pagina esta restrito",
                "medidas de segurança e conformidade",
                "medidas de seguranca e conformidade",
                "access denied",
                "request blocked",
                "cf-error",  # cloudflare-ish
            )
            blob = f"{title}\n{body}"
            return any(m in blob for m in markers)
        except Exception:
            return False

    async def _is_404_page(self) -> bool:
        """Detect Betano real 404 page only (avoid false positives on normal pages)."""
        if await self._is_access_restricted():
            return False
        try:
            title = (await self.page.title() or "").lower()
            body = (await self._page_body_sample()).lower()
            # Real 404 titles / short error pages
            if "not found" in title or title.strip() in ("404", "error 404"):
                return True
            if "we are sorry" in body and "looking for" in body and len(body) < 600:
                return True
            if "doesn't exist" in body and "launch homepage" in body:
                return True
            # Do NOT flag normal home/live pages that mention words casually
        except Exception:
            pass
        return False

    async def _dismiss_cookie_banners(self):
        """Click common BR cookie/age consent buttons if present."""
        if not self.page:
            return
        try:
            await self.page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, a, div, span'));
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t === 'SIM' || t === 'Permitir Todos' || t === 'Aceitar' || t === 'ACEITAR' || t === 'Permitir todos') {
                        try {
                            b.click();
                        } catch(e) {}
                    }
                }
            }""")
            await asyncio.sleep(0.8)
        except Exception:
            pass

    async def _handle_access_restricted(self) -> bool:
        """
        Recover from compliance/WAF block — carefully, without ban-hammering.
        Returns True if page looks usable again.
        """
        if self._in_recovery:
            return False
        self._in_recovery = True
        try:
            logger.error(
                "[Betano] BLOQUEIO: 'Access restricted / security and compliance'. "
                "Causa comum: IP fora do BR, VPN, datacenter ou WAF anti-bot."
            )
            self._access_blocked = True
            self._last_block_retry = datetime.now()

            # Soft attempts only (no profile spam every cycle)
            if self.page:
                # 1) Homepage with Google referer, then live
                try:
                    await self.page.goto(
                        "https://www.google.com.br/",
                        wait_until="domcontentloaded",
                        timeout=20000,
                        referer="https://www.google.com.br/",
                    )
                    await asyncio.sleep(2)
                    await self.page.goto(
                        BETANO_HOME_URL,
                        wait_until="domcontentloaded",
                        timeout=25000,
                        referer="https://www.google.com.br/",
                    )
                    await asyncio.sleep(4)
                    await self._dismiss_cookie_banners()
                    if not await self._is_access_restricted():
                        # Try open live via click (more human than direct /live/)
                        try:
                            live = self.page.locator("a[href*='/live']").first
                            if await live.count() > 0:
                                await live.click(timeout=3000)
                                await asyncio.sleep(3)
                        except Exception:
                            await self.page.goto(
                                BETANO_LIVE_URL,
                                wait_until="domcontentloaded",
                                timeout=20000,
                                referer=BETANO_HOME_URL,
                            )
                            await asyncio.sleep(3)
                        if not await self._is_access_restricted():
                            self._access_blocked = False
                            logger.info("[Betano] Acesso OK após navegação humana (home→live)")
                            return True
                except Exception as e:
                    logger.debug(f"[Betano] human nav fail: {e}")

                # 2) Alternate URLs once
                for url in BETANO_URL_CANDIDATES:
                    try:
                        await self.page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=20000,
                            referer="https://www.google.com.br/",
                        )
                        await asyncio.sleep(3)
                        await self._dismiss_cookie_banners()
                        if not await self._is_access_restricted():
                            body = await self._page_body_sample()
                            if len(body) > 200:
                                self._access_blocked = False
                                logger.info(f"[Betano] Acesso OK em {url}")
                                return True
                    except Exception:
                        continue

            # Do NOT auto-rotate profiles in a loop — burns trust and re-triggers WAF.
            logger.error(
                f"[Betano] Ainda bloqueado por {BLOCK_COOLDOWN_SECONDS // 60} min. "
                "Ações manuais: 1) desligue VPN  2) use IP residencial BR  "
                "3) na janela Chrome da Betano, abra betano.bet.br, aceite cookies  "
                "4) se liberar, o scraper volta sozinho. "
                "Bet365 + BetBurger continuam normais."
            )
            return False
        finally:
            self._in_recovery = False

    async def _recover_from_404(self) -> bool:
        """If on 404, force back to the live hub."""
        if await self._is_access_restricted():
            return await self._handle_access_restricted()
        if not await self._is_404_page():
            return False
        logger.warning(f"[Betano] Página 404 detectada ({self.page.url}). Voltando para {BETANO_LIVE_URL}")
        try:
            await self.page.goto(BETANO_LIVE_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            if await self._is_access_restricted():
                return await self._handle_access_restricted()
            return True
        except Exception as e:
            logger.error(f"[Betano] Falha ao recuperar do 404: {e}")
            return False

    async def _click_table_tennis_filter(self):
        """
        Select 'Tênis de Mesa' in the live sports sidebar.
        Avoids links that navigate to /live/tenis-de-mesa/ (404 on Betano BR).
        """
        try:
            clicked = await self.page.evaluate(
                """() => {
                const nodes = Array.from(document.querySelectorAll('a, button, div, span, li'));
                for (const n of nodes) {
                  const t = (n.innerText || '').trim().replace(/\\s+/g, ' ');
                  if (!t || t.length > 48) continue;
                  if (!/t[eê]nis de mesa/i.test(t)) continue;

                  // Never follow broken deep-link routes
                  const href = (n.getAttribute && n.getAttribute('href')) ||
                               (n.closest && n.closest('a') && n.closest('a').getAttribute('href')) || '';
                  if (/tenis-de-mesa|table-tennis/i.test(href || '')) {
                    continue;
                  }

                  n.click();
                  return t;
                }
                return null;
            }"""
            )
            if clicked:
                logger.info(f"[Betano] Filtro esporte clicado: {clicked}")
                await asyncio.sleep(3)
                # If click caused 404, recover immediately
                if await self._is_404_page():
                    await self._recover_from_404()
                    return False
                return True
        except Exception as e:
            logger.debug(f"[Betano] Filter click failed: {e}")
            try:
                await self._recover_from_404()
            except Exception:
                pass
        return False

    async def _navigate_to_live(self):
        """Human-like navigation: home → cookies → live → TT filter."""
        try:
            await asyncio.sleep(1.0)
            # Step 1: home first (direct /live/ is more often WAF-blocked)
            logger.info(f"[Betano] Navegando home {BETANO_HOME_URL}...")
            try:
                await self.page.goto(
                    BETANO_HOME_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                    referer="https://www.google.com.br/",
                )
            except Exception:
                await self.page.goto(BETANO_HOME_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await self._dismiss_cookie_banners()

            if await self._is_access_restricted():
                self._access_blocked = True
                if not self._in_recovery:
                    await self._handle_access_restricted()
                return

            # Step 2: go to live (prefer click)
            clicked_live = False
            try:
                for sel in (
                    "a[href='/live/']",
                    "a[href*='/live']",
                    "a:has-text('AO VIVO')",
                    "a:has-text('Ao Vivo')",
                    "a:has-text('APOSTAS AO VIVO')",
                ):
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible(timeout=1000):
                        await loc.click(timeout=3000)
                        clicked_live = True
                        await asyncio.sleep(3)
                        break
            except Exception:
                pass
            if not clicked_live:
                logger.info(f"[Betano] Navegando live {BETANO_LIVE_URL}...")
                await self.page.goto(
                    BETANO_LIVE_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                    referer=BETANO_HOME_URL,
                )
                await asyncio.sleep(4)

            if await self._is_access_restricted():
                self._access_blocked = True
                if not self._in_recovery:
                    await self._handle_access_restricted()
                return

            if await self._is_404_page():
                await self.page.goto(BETANO_LIVE_FALLBACK, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                if await self._is_access_restricted():
                    self._access_blocked = True
                    if not self._in_recovery:
                        await self._handle_access_restricted()
                    return

            # Soft TT filter only if healthy
            if not self._access_blocked:
                await self._click_table_tennis_filter()
                if await self._is_access_restricted():
                    self._access_blocked = True
                    if not self._in_recovery:
                        await self._handle_access_restricted()
                elif await self._is_404_page():
                    await self._recover_from_404()
        except Exception as e:
            logger.warning(f"[Betano] Failed to navigate to live: {e}")
            try:
                await self.page.goto(BETANO_LIVE_FALLBACK, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
            except Exception:
                pass
        finally:
            await asyncio.sleep(1)
            self._last_reload = datetime.now()

    def _normalize_name(self, name: str) -> str:
        """Normalize match name to match Bet365 cache key format."""
        cleaned = name.lower().strip()
        cleaned = re.sub(r"\s+v(?:s)?\.?\s+", " vs ", cleaned)
        cleaned = re.sub(r"\s+x\s+", " vs ", cleaned)
        cleaned = re.sub(r"\s*[-/]\s*", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
        return cleaned

    def _selenium_click_tt_filter(self, d) -> bool:
        """
        Click live sport tab 'Tênis de Mesa' (data-qa=TABL).
        Betano sport chips: FOOT/TENN/BASK/TABL/... — text scan alone fails often.
        """
        from selenium.webdriver.common.by import By

        # 1) Preferred: stable data-qa / section id from Betano SPA
        for sel in (
            '[data-qa="TABL"]',
            '#section-wrapper-TABL',
            '[id="section-wrapper-TABL"]',
            '[data-qa="TABL"] p',
        ):
            try:
                els = d.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                els = []
            for el in els:
                try:
                    d.execute_script(
                        "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                        el,
                    )
                    time.sleep(0.25)
                    # Click the chip root if we hit the inner <p>
                    target = el
                    try:
                        root = d.execute_script(
                            """
                            const n = arguments[0];
                            return n.closest('[data-qa="TABL"]') || n.closest('#section-wrapper-TABL') || n;
                            """,
                            el,
                        )
                        if root is not None:
                            target = root
                    except Exception:
                        pass

                    # Check if already selected — DO NOT click if selected='true' to avoid unselecting!
                    is_selected = False
                    try:
                        is_selected = d.execute_script("""
                            const n = document.querySelector('[data-qa="TABL"]');
                            if (!n) return false;
                            const selAttr = n.getAttribute('data-qa-istabselected');
                            if (selAttr === 'true') return true;
                            if (n.classList.contains('selected') || n.classList.contains('active')) return true;
                            return false;
                        """)
                    except Exception:
                        pass

                    if is_selected:
                        return True

                    try:
                        target.click()
                    except Exception:
                        d.execute_script("arguments[0].click();", target)
                    time.sleep(1.5)
                    # Confirm selected if attribute exists
                    try:
                        selected = d.execute_script(
                            """
                            const n = document.querySelector('[data-qa="TABL"]');
                            return n ? (n.getAttribute('data-qa-istabselected') || '') : '';
                            """
                        )
                        logger.info(f"[Betano] Filtro TT clicado via {sel} selected={selected!r}")
                    except Exception:
                        logger.info(f"[Betano] Filtro TT clicado via {sel}")
                    return True
                except Exception as e:
                    logger.debug(f"[Betano] TABL click fail {sel}: {e}")
                    continue

        # 2) JS text fallback (swiper may virtualize off-DOM chips)
        try:
            clicked = d.execute_script(
                """
                const want = /t[eê]nis\\s*de\\s*mesa|table\\s*tennis/i;
                const nodes = Array.from(document.querySelectorAll(
                  '[data-qa], [id^="section-wrapper-"], a, button, div, span, p, li'
                ));
                for (const n of nodes) {
                  const t = (n.innerText || n.textContent || '').trim().replace(/\\s+/g, ' ');
                  if (!t || t.length > 40) continue;
                  if (!want.test(t)) continue;
                  const root = n.closest('[data-qa]') || n.closest('[id^="section-wrapper-"]') || n;
                  root.scrollIntoView({block:'center', inline:'center'});
                  root.click();
                  return t;
                }
                // Horizontal swiper: try nudge then search again
                const sw = document.querySelector('.swiper, .swiper-wrapper');
                if (sw) {
                  sw.scrollLeft = (sw.scrollLeft || 0) + 400;
                }
                return null;
                """
            )
            if clicked:
                time.sleep(2.8)
                logger.info(f"[Betano] Filtro TT JS-text: {clicked!r}")
                return True
        except Exception as e:
            logger.debug(f"[Betano] TT JS fallback: {e}")

        logger.warning("[Betano] Não achou chip TABL / 'Tênis de Mesa' na live")
        return False

    def _looks_like_team_sport(self, name: str, href: str = "") -> bool:
        """Reject football/basketball/esports-style names (we only want TT persons)."""
        blob = f"{name} {href}".lower()
        team_markers = (
            " fc", " cf", " sc", " afc", " united", " city", " real ", " junior",
            " women", " men ", " femenino", " masculino", " feminino",
            " u19", " u20", " u21", " u23", " reserve",
            "santa fe", "cordoba", "nublense", "guadalupe", "pitbulls",
            "audax", "paysandu", "flamengo", "america mg", "deportivo",
            "independiente", "universitario", "chorrera", "mineros",
            "basket", "nba", "wnba", "esports", "dota", "cs2", "lol",
            "dream women", "tempo women", "atlanta", "toronto",
            "maccabi", "olympiacos", "barcelona", "juventus", "chelsea",
            "manchester", "liverpool", "arsenal", "tottenham",
            "baseball", "mlb", "nfl", "nhl", "handball",
        )
        if any(m in blob for m in team_markers):
            return True
        # Club prefixes/suffixes: "Ca Independiente", "Cd Universitario", "AC Milan"
        if re.search(r"\b(ca|cd|ac|afc|sc|fc|cf|bk|kk|kk)\b", blob):
            return True
        # URL sport hubs that are not TT
        if re.search(
            r"/live/(futebol|basquete|tenis|voleibol|esports|beisebol|futsal|handebol)/",
            blob,
        ):
            return True
        # Long multi-word club names without person pattern
        parts = re.split(r"\s+vs\s+", name, flags=re.I)
        if len(parts) == 2:
            for side in parts:
                words = [w for w in side.split() if w]
                if len(words) >= 5:  # "Pitbulls Santa Barbara FC" style
                    return True
                # Club-ish: ends with FC/CF
                if words and words[-1].lower() in ("fc", "cf", "sc", "ac", "bk", "kk", "cd", "ca"):
                    return True
        return False

    def _looks_like_tt_person_match(self, name: str) -> bool:
        """True if both sides look like individual player names (table tennis)."""
        parts = re.split(r"\s+v(?:s)?\.?\s+|\s+x\s+", name or "", flags=re.I)
        if len(parts) != 2:
            return False
        for side in parts:
            side = side.strip()
            if not side or self._is_label(side):
                return False
            words = [w for w in re.split(r"\s+", side) if w]
            if not (1 <= len(words) <= 4):
                return False
            # Must have letters; reject pure numbers / odds
            letters = re.sub(r"[^a-zA-ZÀ-ÿ]", "", side)
            if len(letters) < 3:
                return False
            if re.search(r"\d{2,}", side):
                return False
        return not self._looks_like_team_sport(name)

    def _selenium_page_state(self, d) -> Tuple[str, str, int]:
        """Return (title, body_sample, body_len)."""
        title = ""
        body = ""
        try:
            title = d.title or ""
        except Exception:
            pass
        try:
            from selenium.webdriver.common.by import By
            body = d.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            try:
                body = d.execute_script(
                    "return (document.body && document.body.innerText) || ''"
                ) or ""
            except Exception:
                body = ""
        return title, body[:1200], len(body)

    def _selenium_is_blocked(self, title: str, body: str) -> bool:
        low_t = (title or "").lower()
        low_b = (body or "").lower()
        if "splash" in low_t and len(body or "") < 80:
            return True
        if "restricted" in low_b and "compliance" in low_b:
            return True
        markers = (
            "access to this page is restricted",
            "security and compliance",
            "acesso a esta página está restrito",
            "acesso a esta pagina esta restrito",
        )
        blob = f"{low_t}\n{low_b}"
        return any(m in blob for m in markers)

    def _selenium_dismiss_cookies(self, d) -> None:
        try:
            d.execute_script("""
                const buttons = Array.from(document.querySelectorAll('button, a, div, span'));
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t === 'SIM' || t === 'Permitir Todos' || t === 'Aceitar' || t === 'ACEITAR' || t === 'Permitir todos') {
                        try {
                            b.click();
                        } catch(e) {}
                    }
                }
            """)
            time.sleep(1.0)
        except Exception:
            pass

    def _selenium_open_live(self) -> bool:
        """
        Navigate to Betano live with UC Selenium only.
        Order: home → cookies → live → wait out splash → TT filter.
        Never use Playwright page.goto here.
        """
        d = self._uc_driver
        if not d:
            return False
        try:
            # Warm session on homepage first (direct /live/ is splash-prone)
            logger.info(f"[Betano] selenium home {BETANO_HOME_URL}")
            d.get(BETANO_HOME_URL)
            time.sleep(5)
            self._selenium_dismiss_cookies(d)
            title, body, blen = self._selenium_page_state(d)
            logger.info(f"[Betano] selenium home title={title!r} body_len={blen}")
            if self._selenium_is_blocked(title, body):
                # Wait and reload once — splash can be transient
                time.sleep(4)
                d.refresh()
                time.sleep(5)
                title, body, blen = self._selenium_page_state(d)
                logger.info(f"[Betano] selenium home retry title={title!r} body_len={blen}")
                if self._selenium_is_blocked(title, body):
                    logger.error("[Betano] Splash/compliance já na home")
                    return False

            logger.info(f"[Betano] selenium live {BETANO_LIVE_URL}")
            d.get(BETANO_LIVE_URL)
            time.sleep(7)
            self._selenium_dismiss_cookies(d)

            # Splash often resolves after a few seconds — poll up to ~20s
            for attempt in range(5):
                title, body, blen = self._selenium_page_state(d)
                logger.info(
                    f"[Betano] selenium live try={attempt+1} title={title!r} body_len={blen}"
                )
                if not self._selenium_is_blocked(title, body) and blen > 80:
                    break
                if "restricted" in (body or "").lower() and "compliance" in (body or "").lower():
                    logger.error("[Betano] Compliance block no Selenium")
                    return False
                time.sleep(3)
                if attempt == 1:
                    # Bounce via home again
                    d.get(BETANO_HOME_URL)
                    time.sleep(3)
                    d.get(BETANO_LIVE_URL)
                    time.sleep(5)
                elif attempt == 3:
                    try:
                        d.refresh()
                    except Exception:
                        pass
                    time.sleep(4)
            else:
                title, body, blen = self._selenium_page_state(d)
                if self._selenium_is_blocked(title, body) or blen < 50:
                    logger.error(
                        f"[Betano] Live ainda splash/vazio title={title!r} body_len={blen}"
                    )
                    return False

            title, body, blen = self._selenium_page_state(d)
            if self._selenium_is_blocked(title, body):
                logger.error("[Betano] Compliance/splash final no Selenium")
                return False

            self._selenium_click_tt_filter(d)
            ok = blen > 80 or "ao vivo" in (title or "").lower() or "betano" in (title or "").lower()
            return ok and not self._selenium_is_blocked(title, body)
        except Exception as e:
            logger.error(f"[Betano] selenium_open_live: {e}")
            return False

    def _selenium_extract_raw_links(self) -> list:
        """Extract live TT event links via UC selenium using Betano's data-qa DOM structure."""
        from selenium.webdriver.common.by import By

        d = self._uc_driver
        if not d:
            return []
        try:
            cur = d.current_url or ""
            body = ""
            try:
                body = d.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                pass
            if "restricted" in body.lower() and "compliance" in body.lower():
                logger.error("[Betano] Compliance block durante extract")
                return []
            if "/live" not in cur or len(body) < 80:
                if not self._selenium_open_live():
                    return []
            else:
                # Re-assert TT filter every extract (list defaults to football)
                self._selenium_click_tt_filter(d)
        except Exception as e:
            logger.debug(f"[Betano] selenium nav: {e}")

        results = []
        try:
            # Use JavaScript to extract structured data from Betano's data-qa DOM
            raw = d.execute_script(r"""
                var container = document.querySelector('.vue-recycle-scroller') || document;
                var anchors = container.querySelectorAll('a[href]');
                
                // Group all anchors by href (Betano splits names and scores into separate <a> tags)
                var byHref = {};
                for (var i = 0; i < anchors.length; i++) {
                    var a = anchors[i];
                    var href = (a.getAttribute('href') || '').split('?')[0].split('#')[0];
                    if (!/\/live\/.+\/\d{4,}/.test(href)) continue;
                    if (/\/live\/(futebol|basquete|tenis|esports)\/?$/.test(href)) continue;
                    var key = href.replace(/\/+$/, '');
                    if (!byHref[key]) byHref[key] = { href: key, names: [], scores: [] };
                    
                    // Extract participants from data-qa="participants"
                    var pDiv = a.querySelector('[data-qa="participants"]');
                    if (pDiv) {
                        var nameEls = pDiv.querySelectorAll('div');
                        for (var j = 0; j < nameEls.length; j++) {
                            var txt = (nameEls[j].innerText || '').trim();
                            if (txt && txt.length > 2 && txt.length < 60 && !/^\d+$/.test(txt)) {
                                if (byHref[key].names.indexOf(txt) === -1) {
                                    byHref[key].names.push(txt);
                                }
                            }
                        }
                    }
                    
                    // Extract score columns from data-qa="score"
                    var scoreDivs = a.querySelectorAll('[data-qa="score"]');
                    for (var s = 0; s < scoreDivs.length; s++) {
                        var spans = scoreDivs[s].querySelectorAll('span');
                        var col = [];
                        for (var k = 0; k < spans.length; k++) {
                            var v = (spans[k].innerText || '').trim();
                            if (/^\d+$/.test(v)) col.push(v);
                        }
                        // Each score div has exactly 2 values: [player1_value, player2_value]
                        if (col.length === 2) {
                            byHref[key].scores.push(col);
                        }
                    }
                    
                    // Fallback: if no data-qa, grab raw text lines
                    if (!pDiv && scoreDivs.length === 0) {
                        var rawText = (a.innerText || '').trim();
                        if (rawText) {
                            var lines = rawText.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);
                            if (!byHref[key].fallbackLines) byHref[key].fallbackLines = [];
                            byHref[key].fallbackLines = byHref[key].fallbackLines.concat(lines);
                        }
                    }
                }
                
                var out = [];
                var keys = Object.keys(byHref);
                for (var h = 0; h < keys.length; h++) {
                    var entry = byHref[keys[h]];
                    out.push(entry);
                }
                return out;
            """)

            if not raw:
                raw = []

            for item in raw:
                try:
                    href = item.get("href", "")
                    if not href:
                        continue
                    names = item.get("names", [])
                    scores = item.get("scores", [])  # [[p1_sets, p2_sets], [p1_pts, p2_pts]]
                    fallback_lines = item.get("fallbackLines", [])

                    # Build structured lines for the parser
                    lines = list(names)  # Player names first

                    if scores:
                        # Betano score columns: first = sets, second = current set points
                        for col in scores:
                            lines.extend(col)
                    elif fallback_lines:
                        lines.extend(fallback_lines)

                    path = href
                    if "betano.bet.br" in href:
                        path = "/" + href.split("betano.bet.br", 1)[-1].lstrip("/")

                    results.append({"href": path if path.startswith("/") else href, "lines": lines})
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"[Betano] selenium structured extract: {e}")

        if not results:
            try:
                body = d.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                body = ""
            logger.info(f"[Betano] 0 anchors; body_len={len(body)} title={d.title} url={d.current_url}")
        else:
            logger.info(f"[Betano] anchors brutos={len(results)} url={d.current_url}")
        return results

    def _normalize_deep_link(self, href: str) -> str:
        """
        Build a valid Betano EVENT deep link.
        Rejects sport hubs /live/, /live/tenis-de-mesa/, marketing pages, etc.
        Accepts only paths like /live/<slug>/<eventId>/ with numeric id.
        """
        if not href:
            return ""
        h = href.strip()
        # protocol-relative
        if h.startswith("//"):
            h = "https:" + h

        # Absolute URL → take path
        if h.startswith("http://") or h.startswith("https://"):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(h)
                path = parsed.path or ""
                # Force betano.bet.br host (avoid wrong regional redirect)
                host = "www.betano.bet.br"
            except Exception:
                return ""
        else:
            path = h if h.startswith("/") else f"/{h}"
            host = "www.betano.bet.br"

        path = path.split("?")[0].split("#")[0]
        # Normalize trailing slash
        if not path.endswith("/"):
            path = path + "/"

        # Must contain numeric event id (4+ digits)
        # Valid: /live/slug-name/89977912/  or  /live/tenis-de-mesa/slug/89977912/
        m = re.search(r"(/live/(?:[^/]+/)*[^/]+/(\d{5,})/)", path)
        if not m:
            # Some Betano paths: /evento/.../id
            m2 = re.search(r"((?:/live|/evento)/[^\s]+?/(\d{5,})/?)", path)
            if not m2:
                logger.debug(f"[Betano] Rejected non-event href: {href}")
                return ""
            path = m2.group(1)
            if not path.endswith("/"):
                path += "/"
        else:
            path = m.group(1)

        # Reject pure sport category (no real event slug + id already required)
        if re.fullmatch(r"/live/[^/]+/", path):
            return ""

        return f"https://{host}{path}"

    def _is_label(self, text: str) -> bool:
        t = (text or "").strip()
        if not t or len(t) < 2:
            return True
        low = t.lower()
        if low in IGNORE_LABELS:
            return True
        if IGNORE_EXACT_RE.match(low):
            return True
        if re.match(r"^\d+([.,]\d+)?$", t):
            return True
        if re.match(r"^\d+:\d+$", t):
            return True
        # Pure set / period markers
        if re.search(r"\bset\b", low) and len(low) <= 12:
            return True
        if re.search(r"\bao\s*vivo\b", low):
            return True
        return False

    def _looks_like_person(self, text: str) -> bool:
        """Heuristic: at least one alphabetic token of length >= 2."""
        if self._is_label(text):
            return False
        letters = re.sub(r"[^a-zA-ZÀ-ÿ]", "", text)
        if len(letters) < 2:
            return False
        # Reject if mostly digits
        digits = sum(c.isdigit() for c in text)
        if digits > len(text) / 2:
            return False
        return True

    def _parse_players_and_scores(self, lines: List[str], slug: str) -> Tuple[str, str, str, str]:
        """
        Returns (match_name, set_score, game_score, point_score).
        """
        text_lines = [l.strip() for l in lines if l and l.strip()]
        players: List[str] = []
        numbers: List[str] = []

        for l in text_lines:
            if re.match(r"^\d+$", l):
                numbers.append(l)
                continue
            if re.match(r"^\d+:\d+$", l):
                continue
            if self._looks_like_person(l):
                players.append(l)

        # Deduplicate consecutive duplicates
        deduped = []
        for p in players:
            if not deduped or deduped[-1].lower() != p.lower():
                deduped.append(p)
        players = deduped

        if len(players) >= 2:
            match_name = f"{players[0]} vs {players[1]}"
        elif slug and " vs " not in slug.lower():
            # slug like "daniel-tuma-martin-sobisek-12345" → try split
            parts = [p for p in slug.replace("-", " ").split() if not p.isdigit() and len(p) > 1]
            if len(parts) >= 2:
                mid = len(parts) // 2
                match_name = f"{' '.join(parts[:mid]).title()} vs {' '.join(parts[mid:]).title()}"
            else:
                match_name = slug.title()
        else:
            match_name = slug.title() if slug else "Unknown"

        set_score = "0:0"
        game_score = "0:0"
        point_score = "0"

        # Prefer explicit score pairs from original lines
        pairs = [l.strip() for l in text_lines if re.match(r"^\d+:\d+$", l.strip())]
        if len(pairs) >= 2:
            set_score = pairs[0]
            game_score = pairs[1]
            if len(pairs) >= 3:
                point_score = pairs[2]
        elif len(pairs) == 1:
            game_score = pairs[0]
        elif len(numbers) >= 4:
            # [setH, setA, gameH, gameA]
            set_score = f"{numbers[0]}:{numbers[1]}"
            game_score = f"{numbers[2]}:{numbers[3]}"
        elif len(numbers) >= 2:
            game_score = f"{numbers[0]}:{numbers[1]}"

        return match_name, set_score, game_score, point_score

    async def fetch_live_events(self) -> List[NormalizedEvent]:
        """Fetch live events — UC Selenium only (Playwright CDP triggers Splash)."""
        if not self._is_running or (not self._uc_driver and not self.page):
            await self.start()
            if not self._is_running:
                return []

        now = datetime.now()
        # Periodically reload live page (every 3 minutes) to refresh WebSockets and avoid silent freeze
        if (now - self._last_reload).total_seconds() > 180:
            logger.info("[Betano] Performing scheduled 3-minute fallback reload to prevent WebSocket freeze...")
            if self._uc_driver is not None:
                try:
                    await asyncio.to_thread(self._uc_driver.refresh)
                    await asyncio.sleep(4)
                except Exception as ref_err:
                    logger.warning(f"[Betano] Failed to refresh page: {ref_err}")
            self._last_reload = now

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
                        const container = document.querySelector('.vue-recycle-scroller, [class*="RecycleScroller"]');
                        const links = container ? container.querySelectorAll('a[href*="/live/"]') : document.querySelectorAll('a[href*="/live/"]');
                        for (const a of links) {
                          const bare=(a.getAttribute('href')||'').split('?')[0];
                          if (!/\\/live\\/.+\\/\\d{4,}/.test(bare) || seen.has(bare)) continue;
                          seen.add(bare);
                          const lines=(a.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
                          results.push({href:bare, lines});
                        }
                        return results;
                    }""")
                except Exception as pe:
                    logger.debug(f"[Betano] PW evaluate: {pe}")

            logger.info(f"[Betano] raw_links={len(raw_data or [])}")

            seen_ids = set()
            for item in raw_data or []:
                try:
                    href = item.get("href", "")
                    lines = item.get("lines", []) or []
                    if not href:
                        continue

                    # Table tennis events must contain at least 4 score digits or 2 score pairs (sets + game points)
                    num_digits = [l.strip() for l in lines if re.match(r"^\d+$", l.strip())]
                    num_pairs = [l.strip() for l in lines if re.match(r"^\d+:\d+$", l.strip())]
                    if len(num_digits) < 4 and len(num_pairs) < 2:
                        continue

                    # Build slug from path segments (skip numeric ids)
                    path = href.split("?")[0].strip("/")
                    segs = [s for s in path.split("/") if s and not s.isdigit() and s not in ("live", "evento")]
                    slug = segs[-1].replace("-", " ") if segs else ""

                    match_name, set_score, game_score, point_score = self._parse_players_and_scores(lines, slug)

                    # Reject label-like names (e.g. "Set 1 vs Daniel Tuma")
                    parts = re.split(r"\s+v(?:s)?\.?\s+|\s+x\s+", match_name, flags=re.IGNORECASE)
                    if len(parts) < 2 or not self._looks_like_person(parts[0]) or not self._looks_like_person(parts[1]):
                        # Try slug-only rebuild
                        if slug:
                            match_name, set_score2, game_score2, point_score2 = self._parse_players_and_scores([], slug)
                            parts2 = re.split(r"\s+v(?:s)?\.?\s+|\s+x\s+", match_name, flags=re.IGNORECASE)
                            if len(parts2) >= 2 and self._looks_like_person(parts2[0]) and self._looks_like_person(parts2[1]):
                                if set_score == "0:0" and game_score == "0:0":
                                    set_score, game_score, point_score = set_score2, game_score2, point_score2
                            else:
                                continue
                        else:
                            continue

                    if len(match_name) < 5:
                        continue

                    # Drop football/basketball/etc. when live list is unfiltered
                    if self._looks_like_team_sport(match_name, href):
                        continue
                    # Prefer real person-vs-person (table tennis); reject residual club pairs
                    if not self._looks_like_tt_person_match(match_name):
                        continue

                    deep_link = self._normalize_deep_link(href)
                    if not deep_link:
                        # No valid event URL — skip rather than open wrong hub page
                        logger.debug(f"[Betano] Sem deep link de evento para {match_name} href={href}")
                        continue

                    match_id = self._normalize_name(match_name)
                    if not match_id or match_id in seen_ids:
                        continue
                    seen_ids.add(match_id)

                    events.append(NormalizedEvent(
                        match_id=match_id,
                        match_name=match_name,
                        sport="tabletennis",
                        source="betano",
                        set_score=set_score,
                        game_score=game_score,
                        point_score=point_score,
                        deep_link=deep_link,
                        timestamp=datetime.now(),
                    ))
                except Exception as item_err:
                    logger.debug(f"[Betano] Item parse error: {item_err}")

            self._consecutive_errors = 0
            logger.info(f"[Betano] Extracted {len(events)} live TT events (from {len(raw_data or [])} raw links)")
            if events:
                sample = ", ".join(f"{e.match_name} [{e.set_score}/{e.game_score}] -> {e.deep_link}" for e in events[:3])
                logger.info(f"[Betano] Sample TT: {sample}")
            elif raw_data:
                logger.warning(
                    "[Betano] Links no live mas 0 TT após filtro TABL/heurística — "
                    "confira se o chip Tênis de Mesa está selecionado na janela Chrome"
                )

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"[Betano] Error fetching live events: {e}")
            if self._consecutive_errors >= 5:
                logger.warning("[Betano] Too many errors, hard reload...")
                await self._navigate_to_live()
                self._consecutive_errors = 0

        # Only mark blocked on real compliance/splash — not on empty TT list
        if not events and self._is_running:
            try:
                if self._uc_driver is not None:
                    def _chk():
                        t, b, _ = self._selenium_page_state(self._uc_driver)
                        return self._selenium_is_blocked(t, b)
                    if await asyncio.to_thread(_chk):
                        self._access_blocked = True
                        self._last_block_retry = datetime.now()
                        logger.warning("[Betano] Splash/compliance no extract — cooldown ativo")
                elif self.page and await self._is_access_restricted():
                    self._access_blocked = True
                    self._last_block_retry = datetime.now()
                    logger.warning("[Betano] Compliance block detectado no fetch — cooldown ativo")
            except Exception as e:
                logger.debug(f"[Betano] block check failed: {e}")

        return events
