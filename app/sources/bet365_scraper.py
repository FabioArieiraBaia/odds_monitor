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
        """Gracefully close all browser resources and kill Chrome process tree."""
        self._is_running = False
        logger.info("[Bet365] Shutting down browser...")
        
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
                logger.debug(f"[Bet365] Error closing {label}: {e}")
            setattr(self, attr, None)
        
        # Stop Playwright
        try:
            if hasattr(self, '_pw'):
                await self._pw.stop()
        except Exception as e:
            logger.debug(f"[Bet365] Error stopping playwright: {e}")
        
        # Kill Chrome process tree (Windows: taskkill /T kills all children)
        if self.chrome_process:
            pid = self.chrome_process.pid
            try:
                logger.info(f"[Bet365] Killing Chrome (PID {pid}) and its tree...")
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=5
                )
            except Exception as e:
                logger.debug(f"[Bet365] taskkill failed: {e} — trying terminate()")
                try:
                    self.chrome_process.terminate()
                    self.chrome_process.wait(timeout=3)
                except Exception:
                    try:
                        self.chrome_process.kill()
                    except Exception:
                        pass
            self.chrome_process = None
        
        # Kill any Chrome listening on port 9222 (safety net)
        try:
            subprocess.run(
                'for /f "tokens=5" %a in ("netstat -ano | findstr :9222") do taskkill /PID %a /T /F',
                shell=True, capture_output=True, timeout=3
            )
        except Exception:
            pass
        
        logger.info("[Bet365] Shutdown complete.")

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
        Uses a structure-aware JavaScript extractor that reads scores
        per participant row to avoid flat-array ambiguity.
        """
        events = []
        now = datetime.now()
        
        try:
            raw_data = await self.page.evaluate("""
                () => {
                    const results = [];
                    
                    // ── Find visible fixture containers ──
                    const selectors = [
                        '.ovm-Fixture',
                        '.ipe-EventViewDetail',
                        '[class*="Fixture"][class*="ovm"]',
                        '[class*="rcl-ParticipantFixture"]',
                        '.gl-Market_General',
                    ];
                    
                    let fixtures = [];
                    for (const sel of selectors) {
                        const els = Array.from(document.querySelectorAll(sel));
                        const visible = els.filter(el => {
                            if (el.offsetParent === null) return false;
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        });
                        if (visible.length > 0) {
                            fixtures = visible;
                            break;
                        }
                    }
                    
                    if (fixtures.length === 0) {
                        const allElements = document.querySelectorAll('[class*="Participant"], [class*="Team"]');
                        const parents = new Set();
                        allElements.forEach(el => {
                            if (el.parentElement && el.parentElement.offsetParent !== null) {
                                parents.add(el.parentElement);
                            }
                        });
                        fixtures = Array.from(parents);
                    }
                    
                    for (const fixture of fixtures) {
                        try {
                            // ── Extract participant names ──
                            const nameSelectors = [
                                '.ovm-FixtureName_Name',
                                '[class*="ParticipantName"]',
                                '[class*="TeamName"]',
                                '[class*="Fixture"] [class*="Name"]',
                            ];
                            
                            let names = [];
                            for (const nSel of nameSelectors) {
                                const nameEls = fixture.querySelectorAll(nSel);
                                if (nameEls.length >= 2) {
                                    names = Array.from(nameEls).map(e => e.textContent.trim());
                                    break;
                                }
                            }
                            
                            if (names.length < 2) continue;
                            const matchName = names.join(' vs ');
                            if (matchName.length < 3) continue;
                            
                            // ── Extract scores PER PARTICIPANT ROW ──
                            // Bet365 renders scores in participant rows. Each row has
                            // the participant name followed by score cells.
                            // We extract all numeric leaf-text from each row separately.
                            
                            const participantSelectors = [
                                '[class*="Participant"]',   // Common wrapper
                                '.ovm-ParticipantOddsOnly', // Odds-only view
                                '[class*="ScoreCouponRow"]', // Score row
                                '.ovm-FixtureDetailParticipant', // Detail view
                            ];
                            
                            let p1Scores = [];
                            let p2Scores = [];
                            
                            // Strategy A: find participant rows and extract scores from each
                            let participantRows = [];
                            for (const pSel of participantSelectors) {
                                participantRows = Array.from(fixture.querySelectorAll(pSel));
                                if (participantRows.length >= 2) break;
                            }
                            
                            function isVisible(el) {
                                if (el.offsetParent !== null) return true;
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            }

                            function extractNums(el) {
                                const nums = [];
                                // Get all score-like elements within this row
                                const scoreEls = el.querySelectorAll(
                                    '[class*="Score"], [class*="score"], .ovm-ScoreWrapper_Score'
                                );
                                if (scoreEls.length > 0) {
                                    for (const sEl of scoreEls) {
                                        if (!isVisible(sEl)) continue;
                                        const t = sEl.textContent.trim();
                                        if (/^\d+$/.test(t) || /^[Aa]d?v?$/.test(t)) {
                                            nums.push(t);
                                        }
                                    }
                                }
                                // Fallback: walk leaf nodes
                                if (nums.length === 0) {
                                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                                    let node;
                                    while (node = walker.nextNode()) {
                                        const t = node.textContent.trim();
                                        if (/^\d+$/.test(t)) nums.push(t);
                                    }
                                }
                                return nums;
                            }
                            
                            if (participantRows.length >= 2) {
                                p1Scores = extractNums(participantRows[0]);
                                p2Scores = extractNums(participantRows[1]);
                            }
                            
                            // Strategy B fallback: flat score extraction
                            let flatScores = [];
                            if (p1Scores.length === 0 && p2Scores.length === 0) {
                                const scoreEls = fixture.querySelectorAll(
                                    '[class*="Score"], [class*="score"], .ovm-ScoreWrapper_Score'
                                );
                                for (const el of scoreEls) {
                                    if (!isVisible(el)) continue;
                                    const t = el.textContent.trim();
                                    if (/^\d+$/.test(t) || /^[Aa]d?v?$/.test(t)) {
                                        flatScores.push(t);
                                    }
                                }
                            }
                            
                            // ── Extract event link / event ID ──
                            let eventId = null;
                            let href = null;
                            
                            const linkEl = fixture.querySelector('a[href*="EV"]');
                            if (linkEl) href = linkEl.getAttribute('href');
                            
                            const dataAttrs = ['data-fixtureid', 'data-eventid', 'data-id', 'data-ev'];
                            for (const attr of dataAttrs) {
                                const val = fixture.getAttribute(attr) || 
                                           fixture.closest('[' + attr + ']')?.getAttribute(attr);
                                if (val) {
                                    eventId = val;
                                    break;
                                }
                            }
                            
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
                                p1: p1Scores,
                                p2: p2Scores,
                                flat: flatScores,
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
                    
                    p1 = item.get('p1', [])
                    p2 = item.get('p2', [])
                    flat = item.get('flat', [])
                    event_id = item.get('eventId')
                    href = item.get('href')
                    
                    # Parse scores using structured per-row data
                    set_score, game_score, point_score = self._parse_scores_structured(
                        p1, p2, flat, sport
                    )
                    
                    # Log raw extraction for debugging (first 3 events per sport)
                    if len(events) < 3:
                        logger.debug(
                            f"[Bet365 RAW] {sport} | {match_name} | "
                            f"P1={p1} P2={p2} flat={flat} => "
                            f"set={set_score} game={game_score} pts={point_score}"
                        )
                    
                    deep_link = self._build_deep_link(event_id, href, sport)
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

    def _parse_scores_structured(self, p1: List[str], p2: List[str], flat: List[str], sport: str) -> tuple:
        """
        Parse structured score data into (set_score, game_score, point_score).
        
        p1/p2: scores extracted from participant row 1 and row 2 respectively.
        flat: fallback flat list if row extraction failed.
        
        Bet365 layout per sport:
        - Tennis:       P1 row = [Sets, Games, Points]  P2 row = [Sets, Games, Points]
        - Table Tennis:  P1 row = [Sets, CurrentSetScore] P2 row = [Sets, CurrentSetScore]
        - Basketball:   P1 row = [Total] or [Q1,Q2,Q3,Q4,Total]  P2 row = same
        - Soccer:       P1 row = [Goals]  P2 row = [Goals]
        """
        set_score = "0:0"
        game_score = "0:0"
        point_score = "0"
        
        # ── Structured extraction (per-row) ──
        if p1 and p2:
            # Clean to only numeric + tennis Ad
            p1 = [s.strip() for s in p1 if re.match(r'^(\d{1,3}|[Aa]|[Aa]d|[Aa]dv)$', s.strip())]
            p2 = [s.strip() for s in p2 if re.match(r'^(\d{1,3}|[Aa]|[Aa]d|[Aa]dv)$', s.strip())]
            
            if sport == "tennis":
                # Tennis: [Sets, Games, Points] per row
                if len(p1) >= 3 and len(p2) >= 3:
                    set_score = f"{p1[0]}:{p2[0]}"
                    game_score = f"{p1[1]}:{p2[1]}"
                    point_score = f"{p1[2]}:{p2[2]}"
                elif len(p1) >= 2 and len(p2) >= 2:
                    set_score = f"{p1[0]}:{p2[0]}"
                    game_score = f"{p1[1]}:{p2[1]}"
                elif len(p1) >= 1 and len(p2) >= 1:
                    game_score = f"{p1[0]}:{p2[0]}"
                    
            elif sport in ("tabletennis", "badminton", "volleyball", "beach_volley"):
                # Set-based sports: [Sets, CurrentSetScore] per row
                if len(p1) >= 2 and len(p2) >= 2:
                    set_score = f"{p1[0]}:{p2[0]}"
                    game_score = f"{p1[-1]}:{p2[-1]}"  # last number = current set score
                elif len(p1) >= 1 and len(p2) >= 1:
                    game_score = f"{p1[0]}:{p2[0]}"
                    
            elif sport in ("basketball", "icehockey", "handball"):
                # Team sports with periods: row may have [Q1, Q2, ..., Total]
                # The LAST number in the row is the total score
                if len(p1) >= 1 and len(p2) >= 1:
                    game_score = f"{p1[-1]}:{p2[-1]}"
                    
            elif sport in ("soccer", "futsal", "baseball", "esports"):
                # Simple score sports: row has [Score] (just 1 number)
                if len(p1) >= 1 and len(p2) >= 1:
                    game_score = f"{p1[-1]}:{p2[-1]}"
                    
            else:
                # Generic fallback
                if len(p1) >= 1 and len(p2) >= 1:
                    game_score = f"{p1[-1]}:{p2[-1]}"
                    
        # ── Flat fallback ──
        elif flat:
            flat = [s.strip() for s in flat if re.match(r'^(\d{1,3}|[Aa]|[Aa]d|[Aa]dv)$', s.strip())]
            if sport == "tennis" and len(flat) >= 6:
                set_score = f"{flat[0]}:{flat[1]}"
                game_score = f"{flat[2]}:{flat[3]}"
                point_score = f"{flat[4]}:{flat[5]}"
            elif len(flat) >= 4:
                set_score = f"{flat[0]}:{flat[1]}"
                game_score = f"{flat[2]}:{flat[3]}"
            elif len(flat) >= 2:
                game_score = f"{flat[0]}:{flat[1]}"
        
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
