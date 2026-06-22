"""
Bet365 Real-Time Scraper using Playwright.
Scrapes live in-play events from bet365.bet.br with stealth mode.
Extracts real event IDs for deep linking directly to specific matches.
"""
import asyncio
import re
import json
import logging
import subprocess
import os
import time
from typing import List, Optional, Dict
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from sources.base_source import BaseSource
from core.normalizer import NormalizedEvent

logger = logging.getLogger(__name__)

# Bet365 BR sport codes for in-play navigation
SPORT_CODES = {
    "tennis":       "B13",
    "basketball":   "B18",
    "tabletennis":  "B92",
    "volleyball":   "B91",
    "badminton":    "B94",
    "icehockey":    "B17",
    "soccer":       "B1",
    "esports":      "B151",
    "handball":     "B78",
    "baseball":     "B63",
    "cricket":      "B3",
    "snooker":      "B14",
    "darts":        "B15",
    "futsal":       "B83",
    "beach_volley": "B95",
}

# Base URL for bet365 Brazil
BET365_BASE = "https://www.bet365.bet.br"


class Bet365Scraper(BaseSource):
    """
    Real Playwright-based scraper for Bet365 in-play events.
    Opens a stealth browser instance, navigates to each sport's in-play page,
    extracts match names, live scores, and event IDs for deep linking.
    """
    def __init__(self, headless: bool = True, sports: List[str] = None):
        self.headless = headless
        self.sports = sports or list(SPORT_CODES.keys())
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.chrome_process: Optional[subprocess.Popen] = None
        self._is_running = False
        self._launch_lock = asyncio.Lock()
        self._consecutive_errors = 0
        self._max_errors_before_restart = 5

    def get_name(self) -> str:
        return "bet365"

    async def _launch_browser(self):
        """Launch a stealth Chromium browser instance using CDP to bypass anti-bot."""
        async with self._launch_lock:
            if self._is_running:
                return
            try:
                # Local Chrome/Edge CDP setup
                possible_paths = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                ]
                chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
                if not chrome_path:
                    raise FileNotFoundError("Google Chrome or Microsoft Edge not found")
                    
                user_data_dir = os.path.join(os.getcwd(), "chrome_data")
                port = 9222
                
                logger.info("Iniciando Google Chrome real via subprocess para o Bet365...")
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
                logger.info(f"Conectando o Playwright ao Chrome na porta {port}...")
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
                self._consecutive_errors = 0
                logger.info("Bet365 browser launched successfully via CDP")
            except Exception as e:
                logger.error(f"Failed to launch Bet365 browser: {e}")
                await self._cleanup()
                raise

    async def _cleanup(self):
        """Gracefully close all browser resources."""
        self._is_running = False
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except:
            pass
        try:
            if self.context:
                await self.context.close()
        except:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except:
            pass
        try:
            if hasattr(self, '_pw'):
                await self._pw.stop()
        except:
            pass
        try:
            if self.chrome_process:
                self.chrome_process.terminate()
                self.chrome_process = None
        except:
            pass
        self.page = None
        self.context = None
        self.browser = None

    async def stop(self):
        await self._cleanup()

    async def _navigate_to_sport(self, sport_code: str):
        """Navigate to a specific sport's in-play page and wait for it to load."""
        url = f"{BET365_BASE}/#/IP/{sport_code}"
        try:
            current_url = self.page.url
            if sport_code not in current_url:
                try:
                    await self.page.goto(url, wait_until="commit", timeout=60000)
                except Exception as e:
                    if "ERR_ABORTED" not in str(e):
                        raise
            else:
                try:
                    await self.page.goto(url, wait_until="commit", timeout=60000)
                except Exception as e:
                    if "ERR_ABORTED" not in str(e):
                        raise
            
            # Map sport codes to Portuguese headers shown on bet365.bet.br
            SPORT_HEADERS = {
                "B13": "Tênis",
                "B18": "Basquete",
                "B92": "Tênis de Mesa",
                "B91": "Vôlei",
                "B94": "Badminton",
                "B17": "Hóquei no Gelo",
                "B1": "Futebol",
            }
            expected_header = SPORT_HEADERS.get(sport_code, "")
            
            # Aguarda um pouco para o React da Bet365 detectar a mudança de hash e exibir o loader
            await asyncio.sleep(2)
            
            try:
                # Wait until the URL hash matches the sport and the loader is gone
                await self.page.wait_for_function(
                    """(args) => {
                        const [code] = args;
                        if (!window.location.hash.includes(code)) return false;
                        
                        const loader = document.querySelector('.ovm-Loader, .gl-Loader');
                        if (loader) return false;
                        
                        // Garante que o container de eventos carregou
                        const container = document.querySelector('.ipe-EventViewDetail, .ovm-Fixture, [class*="ClassificationHeader"]');
                        if (!container) return false;
                        
                        return true;
                    }""",
                    arg=[sport_code],
                    timeout=8000
                )
                # Mais 1 segundo para garantir que o DOM foi populado com as odds e placares
                await asyncio.sleep(1)
            except Exception as wait_err:
                logger.warning(f"Timeout waiting for sport load ({sport_code}): {wait_err}. Using fallback sleep...")
                await asyncio.sleep(3)
                
        except Exception as e:
            logger.warning(f"Navigation to {sport_code} failed: {e}")
            raise

    def _normalize_name(self, name: str) -> str:
        """Normalize match name for consistent matching between sources."""
        cleaned = name.lower().strip()
        # Normalize separators
        cleaned = re.sub(r'\s+v(?:s)?\.?\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s+x\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s*[-/]\s*', ' ', cleaned)
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # Remove common prefixes/suffixes
        cleaned = re.sub(r'\(.*?\)', '', cleaned).strip()
        return cleaned

    async def _extract_events_from_page(self, sport: str) -> List[NormalizedEvent]:
        """
        Extract live events from the current Bet365 in-play page.
        Uses multiple extraction strategies for robustness.
        """
        events = []
        now = datetime.now()
        
        try:
            # Strategy: Use JavaScript evaluation to extract structured data
            # Bet365's in-play page renders fixtures with identifiable patterns
            raw_data = await self.page.evaluate("""
                () => {
                    const results = [];
                    
                    // Strategy 1: Look for fixture containers by common patterns
                    // Bet365 uses class prefixes like 'ovm-', 'rcl-', 'sgl-', 'ipe-'
                    const selectors = [
                        '.ovm-Fixture',
                        '.ipe-EventViewDetail',
                        '[class*="Fixture"][class*="ovm"]',
                        '[class*="rcl-ParticipantFixture"]',
                        '.gl-Market_General',
                    ];
                    
                    let fixtures = [];
                    for (const sel of selectors) {
                        fixtures = document.querySelectorAll(sel);
                        if (fixtures.length > 0) break;
                    }
                    
                    if (fixtures.length === 0) {
                        // Strategy 2: Find fixtures by structure
                        // Look for elements containing team names followed by scores
                        const allElements = document.querySelectorAll('[class*="Participant"], [class*="Team"]');
                        // Group by parent
                        const parents = new Set();
                        allElements.forEach(el => {
                            if (el.parentElement) parents.add(el.parentElement);
                        });
                        fixtures = Array.from(parents);
                    }
                    
                    for (const fixture of fixtures) {
                        try {
                            // Extract team/player names
                            const nameSelectors = [
                                '.ovm-FixtureName_Name',
                                '[class*="ParticipantName"]',
                                '[class*="TeamName"]',
                                '[class*="Fixture"] [class*="Name"]',
                            ];
                            
                            let matchName = '';
                            for (const nSel of nameSelectors) {
                                const nameEls = fixture.querySelectorAll(nSel);
                                if (nameEls.length >= 2) {
                                    matchName = Array.from(nameEls).map(e => e.textContent.trim()).join(' vs ');
                                    break;
                                } else if (nameEls.length === 1) {
                                    matchName = nameEls[0].textContent.trim();
                                    break;
                                }
                            }
                            
                            if (!matchName) {
                                // Try to get all text content and parse
                                const text = fixture.textContent.trim();
                                if (text.length < 5 || text.length > 200) continue;
                                matchName = text.split('\\n')[0].trim();
                            }
                            
                            if (!matchName || matchName.length < 3) continue;
                            
                            // Extract scores
                            const scoreSelectors = [
                                '[class*="Score"]',
                                '[class*="score"]',
                                '.ovm-ScoreWrapper_Score',
                            ];
                            
                            let scores = [];
                            function getLeafText(node) {
                                let t = [];
                                if (node.nodeType === Node.TEXT_NODE) {
                                    if (node.textContent.trim()) t.push(node.textContent.trim());
                                } else {
                                    for (let child of node.childNodes) t = t.concat(getLeafText(child));
                                }
                                return t;
                            }
                            
                            for (const sSel of scoreSelectors) {
                                const scoreEls = fixture.querySelectorAll(sSel);
                                if (scoreEls.length > 0) {
                                    let allScores = [];
                                    for (const el of scoreEls) {
                                        allScores = allScores.concat(getLeafText(el));
                                    }
                                    if (allScores.length > 0) {
                                        scores = allScores;
                                        break;
                                    }
                                }
                            }
                            
                            // Extract event link / event ID
                            let eventId = null;
                            let href = null;
                            
                            // Look for links or clickable elements with event data
                            const linkEl = fixture.querySelector('a[href*="EV"]');
                            if (linkEl) {
                                href = linkEl.getAttribute('href');
                            }
                            
                            // Look for data attributes
                            const dataAttrs = ['data-fixtureid', 'data-eventid', 'data-id', 'data-ev'];
                            for (const attr of dataAttrs) {
                                const val = fixture.getAttribute(attr) || 
                                           fixture.closest('[' + attr + ']')?.getAttribute(attr);
                                if (val) {
                                    eventId = val;
                                    break;
                                }
                            }
                            
                            // Extract from onclick or parent navigation context
                            if (!eventId && !href) {
                                const clickable = fixture.querySelector('[onclick*="EV"], [data-nav*="EV"]');
                                if (clickable) {
                                    const onclickStr = clickable.getAttribute('onclick') || 
                                                      clickable.getAttribute('data-nav') || '';
                                    const evMatch = onclickStr.match(/EV(\d+[A-Z0-9]*)/);
                                    if (evMatch) eventId = evMatch[0];
                                }
                            }
                            
                            results.push({
                                name: matchName,
                                scores: scores,
                                eventId: eventId,
                                href: href,
                            });
                        } catch (e) {
                            // Skip this fixture on error
                        }
                    }
                    
                    return results;
                }
            """)
            
            for item in raw_data:
                try:
                    match_name = item.get('name', '').strip()
                    if not match_name or len(match_name) < 3:
                        continue
                    
                    scores = item.get('scores', [])
                    event_id = item.get('eventId')
                    href = item.get('href')
                    
                    # Parse scores based on sport
                    set_score, game_score, point_score = self._parse_scores(scores, sport)
                    
                    # Build deep link
                    deep_link = self._build_deep_link(event_id, href, sport)
                    
                    # Normalize match ID for cross-source matching
                    match_id = self._normalize_name(match_name)
                    
                    events.append(NormalizedEvent(
                        match_id=match_id,
                        match_name=match_name,
                        sport=sport,
                        source="bet365",
                        set_score=set_score,
                        game_score=game_score,
                        point_score=point_score,
                        timestamp=now,
                        deep_link=deep_link,
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing fixture: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error extracting events for {sport}: {e}")
        
        return events

    def _parse_scores(self, scores: List[str], sport: str) -> tuple:
        """Parse score array into (set_score, game_score, point_score) based on sport."""
        set_score = "0:0"
        game_score = "0:0"
        point_score = "0"
        
        if not scores:
            return set_score, game_score, point_score
        
        # Clean scores — remove empty/whitespace entries and filter out team names/garbage
        # Only keep values that are digits, tennis 'A'/'Ad', or formatted scores like '0:0'
        valid_scores = []
        for s in scores:
            s = s.strip()
            if not s: continue
            if re.match(r'^(\d{1,3}|[Aa]|[Aa]d|[Aa]dv|\d+\s*[-:]\s*\d+)$', s):
                valid_scores.append(s)
        scores = valid_scores
        
        if sport == "tennis":
            # Tennis: typically [sets_p1, sets_p2, games_p1, games_p2, points_p1, points_p2]
            if len(scores) >= 6:
                set_score = f"{scores[0]}:{scores[1]}"
                game_score = f"{scores[2]}:{scores[3]}"
                point_score = f"{scores[4]}:{scores[5]}"
            elif len(scores) >= 4:
                set_score = f"{scores[0]}:{scores[1]}"
                game_score = f"{scores[2]}:{scores[3]}"
            elif len(scores) >= 2:
                game_score = f"{scores[0]}:{scores[1]}"
        elif sport in ("basketball", "soccer", "icehockey", "handball", "futsal"):
            # Team sports: [score_home, score_away]
            # Ignore period/quarter to avoid displaying "23 (23:51)" instead of "0:0 (23:51)"
            if len(scores) >= 2:
                game_score = f"{scores[0]}:{scores[1]}"
        elif sport in ("tabletennis", "badminton", "volleyball", "beach_volley"):
            # Set-based sports: [sets_p1, sets_p2, current_set_score_p1, current_set_score_p2]
            if len(scores) >= 4:
                set_score = f"{scores[0]}:{scores[1]}"
                game_score = f"{scores[2]}:{scores[3]}"
            elif len(scores) >= 2:
                game_score = f"{scores[0]}:{scores[1]}"
        else:
            # Generic fallback
            if len(scores) >= 2:
                game_score = f"{scores[0]}:{scores[1]}"
        
        # Normalize dashes to colons
        set_score = set_score.replace('-', ':')
        game_score = game_score.replace('-', ':')
        point_score = point_score.replace('-', ':')
        
        return set_score, game_score, point_score

    def _build_deep_link(self, event_id: Optional[str], href: Optional[str], sport: str) -> str:
        """Build a deep link URL for the specific Bet365 event."""
        # If we have a direct href, use it
        if href:
            if href.startswith('http'):
                return href
            return f"{BET365_BASE}/{href.lstrip('/')}"
        
        # If we have an event ID, construct the deep link
        if event_id:
            # Clean the event ID
            ev = event_id.strip()
            if not ev.startswith('EV'):
                ev = f"EV{ev}"
            # Add sport class suffix if not present
            if not re.search(r'C\d+$', ev):
                ev += "C1"
            return f"{BET365_BASE}/#/IP/{ev}"
        
        # Fallback to sport listing page
        sport_code = SPORT_CODES.get(sport, "B13")
        return f"{BET365_BASE}/#/IP/{sport_code}"

    async def fetch_live_events(self) -> List[NormalizedEvent]:
        """
        Main entry: fetch all live events across configured sports.
        Launches browser if needed, navigates to each sport, extracts events.
        """
        if not self._is_running:
            await self._launch_browser()
        
        all_events = []
        
        for sport in self.sports:
            sport_code = SPORT_CODES.get(sport)
            if not sport_code:
                logger.warning(f"Unknown sport code for: {sport}")
                continue
            
            try:
                await self._navigate_to_sport(sport_code)
                events = await self._extract_events_from_page(sport)
                all_events.extend(events)
                logger.info(f"[Bet365] {sport}: {len(events)} events found")
                
                # Small delay between sport navigations to avoid rate limits
                await asyncio.sleep(1)
                
                self._consecutive_errors = 0
                
            except Exception as e:
                self._consecutive_errors += 1
                logger.error(f"Error scraping {sport} from Bet365: {e}")
                
                if self._consecutive_errors >= self._max_errors_before_restart:
                    logger.warning("Too many consecutive errors, restarting browser...")
                    await self._cleanup()
                    await asyncio.sleep(5)
                    try:
                        await self._launch_browser()
                    except:
                        pass
                    break
        
        return all_events
