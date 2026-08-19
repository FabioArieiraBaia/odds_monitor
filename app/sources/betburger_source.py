"""
BetBurger Real-Time Scraper using Playwright.
Scrapes live surebets/valuebets from betburger.com with login support.
Extracts match data, scores, and bookmaker comparisons.
"""
import asyncio
import re
import json
import logging
from typing import List, Optional, Dict
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from sources.base_source import BaseSource
from core.normalizer import NormalizedEvent

logger = logging.getLogger(__name__)

BETBURGER_BASE = "https://www.betburger.com"
# Events live = full live scoreboard (base for divergence). Arbs = surebets only.
BETBURGER_EVENTS_LIVE_URL = f"{BETBURGER_BASE}/events/live#sportIds=13"
BETBURGER_ARBS_LIVE_URL = f"{BETBURGER_BASE}/arbs/live"
BETBURGER_LIVE_URL = BETBURGER_EVENTS_LIVE_URL  # primary



class BetBurgerScraper(BaseSource):
    """
    Real Playwright-based scraper for BetBurger live surebets page.
    Logs into BetBurger, navigates to live surebets, and extracts
    match data with bookmaker scores for comparison.
    """
    def __init__(self, email: str = "", password: str = "", headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_running = False
        self._is_logged_in = False
        self._launch_lock = asyncio.Lock()
        self._consecutive_errors = 0
        self._max_errors_before_restart = 5

    def get_name(self) -> str:
        return "betburger"

    async def start(self):
        await self._launch_browser()

    async def _launch_browser(self):
        """Launch a real Chrome browser instance via CDP for BetBurger."""
        import subprocess
        import os
        async with self._launch_lock:
            if self._is_running:
                return
            try:
                possible_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                ]
                chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
                if not chrome_path:
                    raise FileNotFoundError("Google Chrome or Microsoft Edge not found")
                
                # Use a different port and user data dir than Bet365 to avoid conflicts
                local_app_data = os.environ.get('LOCALAPPDATA')
                if local_app_data:
                    user_data_dir = os.path.join(local_app_data, "OddsDivergenceMonitor", "chrome_data_betburger")
                else:
                    user_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chrome_data_betburger")
                port = 9223
                
                self.chrome_process = subprocess.Popen([
                    chrome_path,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={user_data_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ])
                
                # Aguarda o Chrome iniciar
                await asyncio.sleep(4)
                
                self._pw = await async_playwright().start()
                logger.info(f"Conectando o Playwright ao Chrome (BetBurger) na porta {port}...")
                self.browser = await self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=60000)
                
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = await self.browser.new_context()
                
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = await self.context.new_page()
                
                self._is_running = True
                self._is_logged_in = False
                self._consecutive_errors = 0
                logger.info("BetBurger browser launched successfully via CDP")
            except Exception as e:
                logger.error(f"Failed to launch BetBurger browser: {e}")
                await self._cleanup()
                raise

    async def _cleanup(self):
        """Gracefully close all browser resources and kill Chrome process tree."""
        import subprocess
        self._is_running = False
        self._is_logged_in = False
        logger.info("[BetBurger] Shutting down browser...")
        
        # Close Playwright objects first
        for attr, label in [('page', 'page'), ('context', 'context'), ('browser', 'browser')]:
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                if attr == 'page' and not obj.is_closed():
                    await obj.close()
                else:
                    await obj.close()
            except Exception as e:
                logger.debug(f"[BetBurger] Error closing {label}: {e}")
            setattr(self, attr, None)
        
        # Stop Playwright
        try:
            if hasattr(self, '_pw'):
                await self._pw.stop()
        except Exception as e:
            logger.debug(f"[BetBurger] Error stopping playwright: {e}")
        
        # Kill Chrome process tree (Windows: taskkill /T kills all children)
        chrome_process = getattr(self, 'chrome_process', None)
        if chrome_process:
            pid = chrome_process.pid
            try:
                logger.info(f"[BetBurger] Killing Chrome (PID {pid}) and its tree...")
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=5
                )
            except Exception as e:
                logger.debug(f"[BetBurger] taskkill failed: {e} — trying terminate()")
                try:
                    chrome_process.terminate()
                    chrome_process.wait(timeout=3)
                except Exception:
                    try:
                        chrome_process.kill()
                    except Exception:
                        pass
            self.chrome_process = None
        
        # Kill any Chrome listening on port 9223 (safety net)
        try:
            subprocess.run(
                'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :9223\') do taskkill /PID %a /T /F',
                shell=True, capture_output=True, timeout=3
            )
        except Exception:
            pass
        
        logger.info("[BetBurger] Shutdown complete.")

    async def stop(self):
        await self._cleanup()

    async def _login(self):
        """Log into BetBurger with email/password credentials."""
        if self._is_logged_in:
            return True
        
        if not self.email or not self.password:
            logger.warning("BetBurger credentials not configured — running without login")
            return False
        
        try:
            # Navigate to login page
            await self.page.goto(f"{BETBURGER_BASE}/users/sign_in", 
                               wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            # Dismiss cookie banner if present
            try:
                cookie_btn = self.page.locator('button:has-text("Accept All"), button:has-text("Aceitar"), button:has-text("OK")').first
                if await cookie_btn.is_visible(timeout=2000):
                    await cookie_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Fill login form with exact BetBurger field IDs
            email_selectors = [
                '#betburger_user_email',
                'input[name="betburger_user[email]"]',
                'input[name="user[email]"]',
                'input[type="email"]',
                '#user_email',
            ]
            password_selectors = [
                '#betburger_user_password',
                'input[name="betburger_user[password]"]',
                'input[name="user[password]"]',
                'input[type="password"]',
                '#user_password',
            ]
            
            email_filled = False
            for sel in email_selectors:
                try:
                    el = self.page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill(self.email)
                        email_filled = True
                        break
                except:
                    continue
            
            if not email_filled:
                logger.error("Could not find email field on BetBurger login page")
                return False
            
            password_filled = False
            for sel in password_selectors:
                try:
                    el = self.page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.fill(self.password)
                        password_filled = True
                        break
                except:
                    continue
            
            if not password_filled:
                logger.error("Could not find password field on BetBurger login page")
                return False
            
            # Click submit
            submit_selectors = [
                'button:has-text("SIGN IN TO MY ACCOUNT")',
                'button:has-text("Sign in")',
                'button[type="submit"]',
                'input[type="submit"]',
            ]
            
            for sel in submit_selectors:
                try:
                    btn = self.page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except:
                    continue
            
            # Wait for redirect / dashboard
            await asyncio.sleep(5)
            
            # Check if login was successful
            current_url = self.page.url
            if "sign_in" not in current_url:
                self._is_logged_in = True
                logger.info("BetBurger login successful")
                return True
            else:
                logger.error("BetBurger login failed — still on login page")
                return False
                
        except Exception as e:
            logger.error(f"BetBurger login error: {e}")
            return False

    def _flip_player(self, player: str) -> str:
        """'Last, First' → 'First Last' (BetBurger style → Bet365 style)."""
        p = (player or "").strip()
        if "," in p:
            last, first = p.split(",", 1)
            return f"{first.strip()} {last.strip()}".strip()
        return p

    def _canonical_match_name(self, raw: str) -> str:
        """
        Normalize BetBurger names to 'Player A vs Player B'.
        Examples:
          'Andrle, Tomas - Steffan, Jan' → 'Tomas Andrle vs Jan Steffan'
          'A vs B' stays as is
        """
        name = (raw or "").strip()
        # Strip trailing score noise if still present
        name = re.sub(r"\d+:\d+.*$", "", name).strip()
        name = re.sub(r"\s*[·•].*$", "", name).strip()
        if " - " in name:
            left, right = name.split(" - ", 1)
        elif re.search(r"\s+vs\.?\s+", name, re.I):
            parts = re.split(r"\s+vs\.?\s+", name, maxsplit=1, flags=re.I)
            left, right = parts[0], parts[1] if len(parts) > 1 else ""
        elif re.search(r"\s+x\s+", name, re.I):
            parts = re.split(r"\s+x\s+", name, maxsplit=1, flags=re.I)
            left, right = parts[0], parts[1] if len(parts) > 1 else ""
        else:
            return name
        return f"{self._flip_player(left)} vs {self._flip_player(right)}".strip()

    def _normalize_name(self, name: str) -> str:
        """Normalize match name for consistent matching between sources."""
        cleaned = self._canonical_match_name(name).lower().strip()
        cleaned = re.sub(r"\s+v(?:s)?\.?\s+", " vs ", cleaned)
        cleaned = re.sub(r"\s+x\s+", " vs ", cleaned)
        cleaned = re.sub(r"\s*[-/]\s*", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
        return cleaned

    def _normalize_sport(self, sport_raw: str) -> str:
        """Map BetBurger sport labels to internal keys."""
        s = (sport_raw or "").lower().strip()
        s = re.sub(r"\s+", " ", s)
        if not s:
            return "unknown"
        # Table tennis BEFORE plain tennis (avoid 'table tennis' → tennis)
        if "table tennis" in s or "tênis de mesa" in s or "tenis de mesa" in s or "ping pong" in s or s in ("tt", "🏓"):
            return "tabletennis"
        if s in ("tennis", "tênis", "tenis") or (s.endswith("tennis") and "table" not in s and "e-tennis" not in s):
            if "e-tennis" in s or "e tennis" in s:
                return "tennis"
            return "tennis"
        if "basket" in s or "basquete" in s:
            return "basketball"
        if "volley" in s or "vôlei" in s or "volei" in s:
            return "volleyball"
        if "soccer" in s or "football" in s or "futebol" in s:
            return "soccer"
        if "baseball" in s:
            return "baseball"
        if "hockey" in s:
            return "icehockey"
        if "badminton" in s:
            return "badminton"
        if "handball" in s:
            return "handball"
        compact = s.replace(" ", "")
        if compact == "tabletennis":
            return "tabletennis"
        return compact or "unknown"

    def _detect_sport(self, text: str) -> str:
        """Detect sport type from free text."""
        return self._normalize_sport(text)

    def _parse_name_and_scores(self, name_cell: str, sport: str) -> tuple:
        """
        Parse BetBurger name cell like:
          'Andrle, Tomas - Steffan, Jan1:2 (5:11, 11:7, 7:11, 0:2) · 4 set'
        → (match_name, set_score, game_score, point_score)
        """
        cell = (name_cell or "").strip()
        scores = re.findall(r"\d+:\d+", cell)
        # Match name = text before first score
        match_raw = re.split(r"\d+:\d+", cell, maxsplit=1)[0].strip()
        match_name = self._canonical_match_name(match_raw)
        set_score, game_score, point_score = self._parse_scores(scores, sport)
        return match_name, set_score, game_score, point_score

    async def _extract_surebets(self) -> List[NormalizedEvent]:
        """
        Extract live events from BetBurger Events Live table (primary base).
        Columns: Sport | Region | League | Date | Name+Score | Bookmakers
        """
        events: List[NormalizedEvent] = []
        now = datetime.now()

        try:
            try:
                html_content = await self.page.content()
                with open("debug_betburger.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info("Dumped BetBurger HTML to debug_betburger.html")
            except Exception as e:
                logger.debug(f"Error dumping BetBurger HTML: {e}")

            raw_data = await self.page.evaluate("""() => {
                // Auto-close obtrusive login/register popups
                const closeBtn = document.querySelector('button.close.closeBtn, .closeBtn');
                if (closeBtn && closeBtn.offsetParent !== null) {
                    closeBtn.click();
                }
                const cookieBtn = document.querySelector('.cky-btn-close');
                if (cookieBtn && cookieBtn.offsetParent !== null) {
                    cookieBtn.click();
                }

                const results = [];
                const eventRows = document.querySelectorAll('tr.events-table-row');
                for (const row of eventRows) {
                    try {
                        const tds = Array.from(row.querySelectorAll('td'));
                        if (tds.length < 5) continue;
                        const sportText = (tds[0].innerText || '').trim();
                        const region = (tds[1].innerText || '').trim();
                        const league = (tds[2].innerText || '').trim();
                        const dateText = (tds[3].innerText || '').trim();
                        const nameCell = (tds[4].innerText || '').trim();
                        if (!nameCell || nameCell.length < 5) continue;
                        results.push({
                            source: 'events_table',
                            sport: sportText,
                            region: region,
                            league: league,
                            date: dateText,
                            name_cell: nameCell,
                            raw_text: (row.innerText || '').trim()
                        });
                    } catch (e) {}
                }

                if (results.length === 0) {
                    const rows = document.querySelectorAll('.surebet, .arb, [class*="arb-item"]');
                    for (const row of rows) {
                        try {
                            const sportEl = row.querySelector('.sport-name');
                            const sport = sportEl ? sportEl.textContent.trim() : '';
                            let match_name = '';
                            let href = '';
                            const eventLink = row.querySelector('.event-name .name a, .event-name a');
                            if (eventLink) {
                                match_name = eventLink.textContent.trim();
                                href = eventLink.getAttribute('href') || '';
                            } else {
                                const nameEl = row.querySelector('.event-name .name');
                                if (nameEl) match_name = nameEl.textContent.trim();
                            }
                            const bets = [];
                            for (const bet of row.querySelectorAll('.bet-wrapper')) {
                                const bookieEl = bet.querySelector('.bookmaker-name');
                                const scoreEl = bet.querySelector('.bookmaker-name .current-score, .current-score');
                                let bookmaker = '';
                                if (bookieEl) {
                                    const linkSpan = bookieEl.querySelector('.link-span, span');
                                    bookmaker = linkSpan ? linkSpan.textContent.trim() : bookieEl.textContent.trim();
                                }
                                const betLinkEl = bet.querySelector('a');
                                bets.push({
                                    bookmaker: bookmaker,
                                    score: scoreEl ? scoreEl.textContent.trim() : '',
                                    href: betLinkEl ? (betLinkEl.getAttribute('href') || '') : ''
                                });
                            }
                            if (match_name) {
                                results.push({
                                    source: 'surebet',
                                    sport: sport,
                                    match_name: match_name,
                                    name_cell: match_name,
                                    league: '',
                                    bets: bets,
                                    href: href,
                                    raw_text: (row.innerText || '').trim()
                                });
                            }
                        } catch (e) {}
                    }
                }
                return results;
            }""")

            logger.info(f"[BetBurger] raw rows={len(raw_data or [])} url={self.page.url}")

            sport_counts: Dict[str, int] = {}
            for item in raw_data or []:
                try:
                    sport = self._normalize_sport(item.get("sport", "") or item.get("raw_text", ""))
                    sport_counts[sport] = sport_counts.get(sport, 0) + 1

                    league = (item.get("league") or "").strip()
                    name_cell = item.get("name_cell") or item.get("match_name") or ""
                    if not name_cell:
                        continue

                    if item.get("source") == "events_table" or item.get("name_cell"):
                        match_name, set_score, game_score, point_score = self._parse_name_and_scores(
                            name_cell, sport
                        )
                    else:
                        match_name = self._canonical_match_name(name_cell)
                        bets = item.get("bets") or []
                        scores_pool = []
                        for b in bets:
                            sc = b.get("score") or ""
                            scores_pool.extend(re.findall(r"\d+:\d+", sc))
                        if not scores_pool:
                            scores_pool = re.findall(r"\d+:\d+", item.get("raw_text", ""))
                        set_score, game_score, point_score = self._parse_scores(scores_pool, sport)

                    if not match_name or len(match_name) < 5:
                        continue

                    match_id = self._normalize_name(match_name)
                    href = item.get("href") or ""
                    if href.startswith("/"):
                        deep_link = f"https://www.betburger.com{href}"
                    elif href:
                        deep_link = href
                    else:
                        deep_link = BETBURGER_EVENTS_LIVE_URL

                    bet365_link = ""
                    for b in item.get("bets") or []:
                        if "365" in (b.get("bookmaker") or "").lower() and b.get("href"):
                            h = b["href"]
                            bet365_link = h if h.startswith("http") else f"https://www.betburger.com{h}"
                            break

                    events.append(
                        NormalizedEvent(
                            match_id=match_id,
                            match_name=match_name,
                            sport=sport,
                            source=self.get_name(),
                            set_score=set_score,
                            game_score=game_score,
                            point_score=point_score,
                            timestamp=now,
                            deep_link=deep_link,
                            extra_data={
                                "league": league,
                                "region": item.get("region", ""),
                                "bet365_link": bet365_link,
                                "raw_text": item.get("raw_text", ""),
                                "source_path": item.get("source", ""),
                            },
                        )
                    )
                except Exception as e:
                    logger.error(f"Error parsing BetBurger item: {e} | Item: {item}")

            logger.info(f"[BetBurger] sport breakdown: {sport_counts}")
            if events:
                sample = ", ".join(
                    f"{e.match_name} [{e.sport} {e.set_score}/{e.game_score}]" for e in events[:4]
                )
                logger.info(f"[BetBurger] sample: {sample}")
            return events

        except Exception as e:
            logger.error(f"Error extracting BetBurger events: {e}")

        return events

    def _parse_score_pair(self, score: str) -> tuple:
        """Parse 'H:A' into (home, away) ints. Returns (0,0) on failure."""
        try:
            parts = score.split(":")
            if len(parts) >= 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            pass
        return 0, 0

    def _parse_scores(self, scores: List[str], sport: str) -> tuple:
        """Parse score array of 'Home:Away' strings into (set_score, game_score, point_score)."""
        set_score = "0:0"
        game_score = "0:0"
        point_score = "0"
        
        if not scores:
            return set_score, game_score, point_score
        
        scores = [s.strip() for s in scores if s.strip()]
        
        if sport == "tennis":
            # scores[0] is sets (e.g. "1:0")
            set_score = scores[0]
            
            # Find how many sets are completed to get the active set index
            try:
                parts = list(map(int, set_score.split(":")))
                completed_sets = sum(parts)
            except Exception:
                completed_sets = 0
                
            active_set_idx = completed_sets + 1
            
            # The active set score is at scores[active_set_idx] if it exists
            if active_set_idx < len(scores):
                game_score = scores[active_set_idx]
            elif len(scores) > 1:
                # Fallback to the last available set score before points
                game_score = scores[-2] if len(scores) > 2 else scores[1]
                
            # If there's an element after the active set, it is likely the points score
            if len(scores) > active_set_idx + 1:
                point_score = scores[-1]
                
        elif sport in ("tabletennis", "badminton", "volleyball", "beach_volley"):
            # Set-based sports: scores[0] is sets score (e.g. "1:2")
            # The last element is the current set score (e.g. "5:6")
            set_score = scores[0]
            if len(scores) > 1:
                game_score = scores[-1]
            else:
                game_score = "0:0"
                
        else:
            # Team sports (soccer, basketball, etc.): scores[0] is the current game score (e.g. "1:3" or "38:40")
            game_score = scores[0]
            set_score = "0"
            
        # Normalize dashes to colons
        set_score = set_score.replace('-', ':')
        game_score = game_score.replace('-', ':')
        point_score = point_score.replace('-', ':')
        
        return set_score, game_score, point_score

    async def _recreate_page(self):
        """Recreate the page context if it becomes detached or closed."""
        logger.info("Recreating BetBurger page...")
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        self.page = None
        
        try:
            if not self.browser or not self.browser.is_connected():
                logger.warning("Browser disconnected or not running, attempting complete restart...")
                await self._cleanup()
                await self._launch_browser()
                return
            
            # Use existing context if valid, or create new context
            if not self.context or not self.browser.contexts:
                self.context = await self.browser.new_context()
            else:
                self.context = self.browser.contexts[0]
                
            self.page = await self.context.new_page()
            self._is_logged_in = False
            logger.info("Recreated BetBurger page successfully")
        except Exception as e:
            logger.error(f"Failed to recreate BetBurger page: {e}, restarting browser completely...")
            await self._cleanup()
            await self._launch_browser()

    async def fetch_live_events(self) -> List[NormalizedEvent]:
        """
        Main entry: fetch live events from BetBurger Events Live (score base).
        """
        if not self._is_running or not self.page:
            if self._is_running and not self.page:
                logger.warning("Scraper is marked running but page is None. Recreating page...")
                await self._recreate_page()
            else:
                await self._launch_browser()

        try:
            current_url = self.page.url or ""

            if "users/sign_in" in current_url or "login" in current_url:
                logger.info("Esperando login manual no BetBurger...")
                await asyncio.sleep(5)
                return []

            if not self._is_logged_in and self.email and self.password:
                await self._login()

            # Always prefer Events Live (full scoreboard), not Arbs
            if "events/live" not in current_url:
                logger.info(f"Navegando para Events Live: {BETBURGER_EVENTS_LIVE_URL}")
                try:
                    await self.page.goto(
                        BETBURGER_EVENTS_LIVE_URL, wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(4)
                except Exception as e:
                    logger.warning(f"Goto events/live failed: {e}. Recreating page...")
                    await self._recreate_page()
                    await self.page.goto(
                        BETBURGER_EVENTS_LIVE_URL, wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(4)
            else:
                # Soft refresh: re-goto is more reliable than reload on SPA
                try:
                    await self.page.goto(
                        BETBURGER_EVENTS_LIVE_URL, wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.warning(f"Refresh events/live failed: {e}")
                    try:
                        await self._recreate_page()
                        await self.page.goto(
                            BETBURGER_EVENTS_LIVE_URL, wait_until="domcontentloaded", timeout=30000
                        )
                        await asyncio.sleep(4)
                    except Exception as e2:
                        logger.error(f"BetBurger recovery failed: {e2}")
                        return []

            # Wait for table rows
            try:
                await self.page.wait_for_selector("tr.events-table-row", timeout=8000)
            except Exception:
                logger.warning("[BetBurger] Nenhuma tr.events-table-row ainda (login/filtro?)")

            events = await self._extract_surebets()
            tt = [e for e in events if e.sport == "tabletennis"]
            logger.info(
                f"[BetBurger] extracted={len(events)} tabletennis={len(tt)} url={self.page.url}"
            )
            self._consecutive_errors = 0
            return events

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"Error fetching BetBurger events: {e}")

            if self._consecutive_errors >= self._max_errors_before_restart:
                logger.warning("Too many BetBurger errors, restarting browser...")
                await self._cleanup()
                await asyncio.sleep(5)
                try:
                    await self._launch_browser()
                except Exception:
                    pass

            return []
