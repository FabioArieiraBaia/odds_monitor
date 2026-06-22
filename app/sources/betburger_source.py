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
BETBURGER_LIVE_URL = f"{BETBURGER_BASE}/events/live"


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
                user_data_dir = os.path.join(os.getcwd(), "chrome_data_betburger")
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
                self.browser = await self._pw.chromium.connect_over_cdp(f"http://localhost:{port}", timeout=60000)
                
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
            
            # Fill login form
            # BetBurger login form selectors
            email_selectors = [
                'input[name="user[email]"]',
                'input[type="email"]',
                '#user_email',
                'input[placeholder*="email" i]',
                'input[placeholder*="Email" i]',
            ]
            password_selectors = [
                'input[name="user[password]"]',
                'input[type="password"]',
                '#user_password',
                'input[placeholder*="senha" i]',
                'input[placeholder*="password" i]',
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
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
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

    def _normalize_name(self, name: str) -> str:
        """Normalize match name for consistent matching between sources."""
        cleaned = name.lower().strip()
        cleaned = re.sub(r'\s+v(?:s)?\.?\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s+x\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s*[-/]\s*', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\(.*?\)', '', cleaned).strip()
        return cleaned

    def _detect_sport(self, text: str) -> str:
        """Detect sport type from text/icons on the page."""
        text_lower = text.lower()
        sport_map = {
            "tennis": ["tennis", "tênis", "🎾"],
            "basketball": ["basketball", "basquete", "🏀", "nba", "euroleague"],
            "tabletennis": ["table tennis", "tênis de mesa", "ping pong", "🏓"],
            "volleyball": ["volleyball", "voleibol", "vôlei", "🏐"],
            "badminton": ["badminton", "🏸"],
            "icehockey": ["ice hockey", "hockey", "hóquei", "🏒", "nhl"],
            "soccer": ["soccer", "football", "futebol", "⚽"],
            "handball": ["handball", "handebol"],
            "baseball": ["baseball", "beisebol"],
            "esports": ["esports", "e-sports", "cs2", "dota", "league of legends"],
            "cricket": ["cricket", "críquete"],
            "futsal": ["futsal"],
        }
        for sport, keywords in sport_map.items():
            for kw in keywords:
                if kw in text_lower:
                    return sport
        return "unknown"

    async def _extract_surebets(self) -> List[NormalizedEvent]:
        """
        Extract live surebet data from BetBurger's page.
        BetBurger shows a table of surebets with bookmaker comparisons.
        """
        events = []
        now = datetime.now()
        
        try:
            # Dump the current HTML to see what the scraper is looking at
            try:
                html_content = await self.page.content()
                with open("debug_betburger.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info("Dumped BetBurger HTML to debug_betburger.html")
            except Exception as e:
                logger.error(f"Error dumping BetBurger HTML: {e}")
                
            # First check if the page is returning raw JSON (e.g. from /api/live)
            is_json = await self.page.evaluate("""
                () => {
                    try {
                        const text = document.body.innerText || document.documentElement.innerText;
                        if (text.trim().startsWith('{') || text.trim().startsWith('[')) {
                            JSON.parse(text.trim());
                            return true;
                        }
                    } catch (e) {}
                    return false;
                }
            """)
            
            if is_json:
                logger.info("BetBurger API JSON detectado!")
                json_data = await self.page.evaluate("() => JSON.parse(document.body.innerText || document.documentElement.innerText)")
                
                import json
                with open("debug_betburger.json", "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                # Basic JSON extraction (assuming it's a list of matches or surebets)
                # Since we don't know the exact structure, we'll try to find common fields
                events_list = json_data if isinstance(json_data, list) else json_data.get('surebets', json_data.get('events', []))
                
                for item in events_list:
                    try:
                        # Attempt to extract fields from JSON
                        match_name = item.get('event_name') or item.get('match') or item.get('name') or "Unknown Match"
                        sport = item.get('sport_name') or item.get('sport') or "unknown"
                        sport_norm = self._normalize_sport(sport)
                        
                        score = item.get('score', '0:0')
                        set_score, game_score, point_score = self._parse_scores([score], sport_norm)
                        
                        events.append(NormalizedEvent(
                            event_id=str(item.get('id', '')),
                            match_name=match_name,
                            sport=sport_norm,
                            home_team=match_name.split(' - ')[0] if ' - ' in match_name else match_name,
                            away_team=match_name.split(' - ')[1] if ' - ' in match_name else "",
                            set_score=set_score,
                            game_score=game_score,
                            point_score=point_score,
                            source=self.get_name(),
                            updated_at=now,
                            deep_link=f"{BETBURGER_BASE}/surebets/live",
                            extra_data=item
                        ))
                    except Exception as e:
                        logger.debug(f"Error parsing JSON item: {e}")
                
            # --- STRUCTURED DOM EXTRACTOR ---
            raw_data = await self.page.evaluate("""
                () => {
                    const results = [];
                    const rows = document.querySelectorAll('.surebet, .arb, [class*="arb-item"]');
                    
                    for (const row of rows) {
                        try {
                            const sportEl = row.querySelector('.sport-name');
                            const sport = sportEl ? sportEl.textContent.trim() : '';
                            
                            const percentEl = row.querySelector('.percent');
                            const percentText = percentEl ? percentEl.textContent.trim() : '';
                            
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
                            const betWrappers = row.querySelectorAll('.bet-wrapper');
                            for (const bet of betWrappers) {
                                const bookieEl = bet.querySelector('.bookmaker-name');
                                const scoreEl = bet.querySelector('.bookmaker-name .current-score, .current-score');
                                if (bookieEl) {
                                    let bookmaker = '';
                                    const linkSpan = bookieEl.querySelector('.link-span, span');
                                    if (linkSpan) {
                                        bookmaker = linkSpan.textContent.trim();
                                    } else {
                                        const clone = bookieEl.cloneNode(true);
                                        const scoreChild = clone.querySelector('.current-score');
                                        if (scoreChild) scoreChild.remove();
                                        bookmaker = clone.textContent.trim();
                                    }
                                    bets.push({
                                        bookmaker: bookmaker,
                                        score: scoreEl ? scoreEl.textContent.trim() : ''
                                    });
                                }
                            }
                            
                            if (bets.length > 0) {
                                results.push({
                                    sport: sport,
                                    match_name: match_name,
                                    percent_text: percentText,
                                    bets: bets,
                                    href: href,
                                    raw_text: row.textContent || row.innerText || ''
                                });
                            }
                        } catch (e) {}
                    }
                    
                    // Fallback to Events Live page table if no surebet rows were found
                    if (results.length === 0) {
                        const eventRows = document.querySelectorAll('tr.events-table-row');
                        for (const row of eventRows) {
                            try {
                                const tds = row.querySelectorAll('td');
                                if (tds.length === 0) continue;
                                
                                const rowText = row.textContent || row.innerText || '';
                                const sportText = tds[0].textContent.trim();
                                
                                let match_name = '';
                                let raw_match_cell = '';
                                
                                for (const td of tds) {
                                    const text = td.textContent.trim();
                                    // Find the TD that contains the teams (has " - " and is long enough to not be just a date)
                                    if (text.includes(' - ') && !match_name && text.length > 10 && !/^\d{2}\.\d{2}\.\d{4}/.test(text)) {
                                        raw_match_cell = text;
                                        // Clean scores from match name (e.g., "Player A - Player B 1:1 (1:2...)")
                                        match_name = text.replace(/\s+\d+:\d+.*/, '').trim();
                                    }
                                }
                                
                                if (match_name) {
                                    // Find scores from the raw cell text
                                    const scores = raw_match_cell.match(/\d+:\d+/g) || [];
                                    
                                    results.push({
                                        sport: sportText,
                                        match_name: match_name,
                                        percent_text: '0%',
                                        bets: [],
                                        href: '',
                                        scores: scores,
                                        raw_text: rowText
                                    });
                                }
                            } catch (e) {}
                        }
                    }
                    
                    return results;
                }
            """)
            
            import re
            
            logger.info(f"raw_data has {len(raw_data)} items")
            
            for item in raw_data:
                try:
                    # 1. Sport
                    sport_raw = item.get('sport', '')
                    sport = sport_raw.lower().replace(" ", "")
                    
                    # 2. Match Name
                    match_name = item.get('match_name', '').strip()
                    if not match_name:
                        continue
                    
                    scores_found = item.get('scores')
                    if scores_found is not None:
                        # Fallback event parser route
                        sport = self._detect_sport(item.get('raw_text', ''))
                        if sport == "unknown":
                            sport = self._detect_sport(match_name)
                        if sport == "unknown":
                            sport = "tennis"
                            
                        set_score, game_score, point_score = self._parse_scores(scores_found, sport)
                        surebet_perc = 0.0
                        bets = []
                    else:
                        # Original surebet parser route
                        # 3. Surebet Percentage
                        percent_text = item.get('percent_text', '')
                        surebet_perc = 0.0
                        perc_match = re.search(r'(\d+(?:\.\d+)?)%', percent_text)
                        if perc_match:
                            surebet_perc = float(perc_match.group(1))
                        
                        # 4. Extract scores of each bookmaker
                        bets = item.get('bets', [])
                        non_b365_scores = []
                        b365_scores = []
                        
                        for b in bets:
                            bookie = b.get('bookmaker', '').lower()
                            score_str = b.get('score', '')
                            if not score_str:
                                continue
                            if '365' in bookie:
                                b365_scores.append(score_str)
                            else:
                                non_b365_scores.append(score_str)
                                
                        # Select the reference score
                        selected_score_str = None
                        scores_to_evaluate = non_b365_scores if non_b365_scores else b365_scores
                        
                        if scores_to_evaluate:
                            best_score_str = scores_to_evaluate[0]
                            max_val = -1
                            for s_str in scores_to_evaluate:
                                scores_found_in_bet = re.findall(r'\d+:\d+', s_str)
                                temp_sets, temp_games, _ = self._parse_scores(scores_found_in_bet, sport)
                                s_h, s_a = self._parse_score_pair(temp_sets)
                                g_h, g_a = self._parse_score_pair(temp_games)
                                val = (s_h + s_a) * 10 + (g_h + g_a)
                                if val > max_val:
                                    max_val = val
                                    best_score_str = s_str
                            selected_score_str = best_score_str
                        else:
                            selected_score_str = "0:0"
                            
                        # Extract the selected scores
                        scores_found_in_bet = re.findall(r'\d+:\d+', selected_score_str)
                        set_score, game_score, point_score = self._parse_scores(scores_found_in_bet, sport)
                    
                    match_id = self._normalize_name(match_name)
                    href = item.get('href', '')
                    deep_link = f"https://www.betburger.com{href}" if href else BETBURGER_LIVE_URL
                    
                    events.append(NormalizedEvent(
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
                            "raw_text": item.get('raw_text', ''),
                            "surebet_percentage": surebet_perc,
                            "bets": bets
                        }
                    ))
                except Exception as e:
                    logger.error(f"Error parsing BetBurger structured item: {e} | Item: {item}")
            return events
        
        except Exception as e:
            logger.error(f"Error extracting BetBurger surebets: {e}")
        
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
        Main entry: fetch all live events from BetBurger.
        Launches browser if needed, logs in, navigates to live surebets, extracts data.
        """
        if not self._is_running or not self.page:
            if self._is_running and not self.page:
                logger.warning("Scraper is marked running but page is None. Recreating page...")
                await self._recreate_page()
            else:
                await self._launch_browser()
        
        try:
            current_url = self.page.url
            
            # Se o usuario estiver na tela de login, esperamos ele logar
            if "users/sign_in" in current_url or "login" in current_url:
                logger.info("Esperando você fazer o login manual no BetBurger...")
                await asyncio.sleep(5)
                return []
            
            # Automatic login if credentials exist
            if not self._is_logged_in and self.email and self.password:
                await self._login()
            
            # Se nao esta na pagina de eventos, navega para ela
            if "events/live" not in current_url:
                logger.info("Navegando para aba de Eventos do BetBurger...")
                try:
                    await self.page.goto(BETBURGER_LIVE_URL, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(4)
                except Exception as e:
                    logger.warning(f"Error navigating to BetBurger live URL: {e}. Retrying after recreating page...")
                    await self._recreate_page()
                    await self.page.goto(BETBURGER_LIVE_URL, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(4)
            else:
                # Reload para pegar dados frescos
                try:
                    logger.info("Recarregando página do BetBurger...")
                    await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(3)
                except Exception as e:
                    logger.warning(f"Error reloading BetBurger page: {e}. Falling back to goto...")
                    await asyncio.sleep(2)
                    try:
                        if "detached" in str(e).lower() or "closed" in str(e).lower() or "abort" in str(e).lower():
                            await self._recreate_page()
                        await self.page.goto(BETBURGER_LIVE_URL, wait_until="domcontentloaded", timeout=30000)
                        await asyncio.sleep(3)
                    except Exception as goto_err:
                        logger.error(f"Fallback goto failed: {goto_err}. Recreating page completely...")
                        await self._recreate_page()
                        await self.page.goto(BETBURGER_LIVE_URL, wait_until="domcontentloaded", timeout=30000)
                        await asyncio.sleep(4)
            
            events = await self._extract_surebets()
            logger.info(f"[BetBurger] {len(events)} events extracted")
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
                except:
                    pass
            
            return []
