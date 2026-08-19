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
from core.optical_reader import OpticalScoreboardReader

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
        self._last_reload = datetime.now()
        self._launch_lock = asyncio.Lock()
        self._consecutive_errors = 0
        self._max_errors_before_restart = 50
        self._uc_driver = None
        self._profile_suffix = f"bet365_uc_{int(time.time())}"
        self._optical_reader = OpticalScoreboardReader()

    def get_name(self) -> str:
        return "bet365"

    async def start(self):
        await self._launch_browser()

    async def _launch_browser(self):
        """Launch Chrome via undetected_chromedriver and connect Playwright CDP to bypass anti-bot."""
        async with self._launch_lock:
            if self._is_running:
                return
            try:
                import undetected_chromedriver as uc
                
                # Best-effort taskkill stale chromedrivers
                try:
                    subprocess.run(
                        ["taskkill", "/IM", "chromedriver.exe", "/F"],
                        capture_output=True, timeout=5
                    )
                except Exception:
                    pass
                
                local_app_data = os.environ.get('LOCALAPPDATA', '.')
                user_data_dir = os.path.join(local_app_data, "OddsDivergenceMonitor", f"chrome_data_bet365_{self._profile_suffix}")
                os.makedirs(user_data_dir, exist_ok=True)
                
                options = uc.ChromeOptions()
                options.add_argument(f"--user-data-dir={user_data_dir}")
                options.add_argument("--no-first-run")
                options.add_argument("--no-default-browser-check")
                options.add_argument("--window-size=1366,1200")
                options.add_argument("--lang=pt-BR")
                options.add_argument("--disable-infobars")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--no-sandbox")
                # ── Performance & Anti-Throttling Flags ──
                options.add_argument("--disable-background-timer-throttling")
                options.add_argument("--disable-renderer-backgrounding")
                options.add_argument("--disable-backgrounding-occluded-windows")
                options.add_argument("--disable-ipc-flooding-protection")
                options.add_argument("--blink-settings=imagesEnabled=false")
                options.add_argument("--mute-audio")
                
                logger.info("Iniciando Google Chrome real via undetected_chromedriver para o Bet365...")
                
                # Auto-detect major Chrome version or fallback to 151
                chrome_major = 151
                try:
                    import subprocess
                    out = subprocess.check_output(
                        ['powershell', '-NoProfile', '-Command', '(Get-Item "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe").VersionInfo.Major'],
                        text=True
                    ).strip()
                    if out.isdigit():
                        chrome_major = int(out)
                except Exception:
                    pass

                self._uc_driver = uc.Chrome(options=options, headless=False, use_subprocess=True, version_main=chrome_major)
                await asyncio.sleep(2)
                
                try:
                    self._uc_driver.get("about:blank")
                except Exception:
                    pass
                    
                dbg = (self._uc_driver.capabilities.get("goog:chromeOptions") or {}).get("debuggerAddress")
                logger.info(f"[Bet365] UC debuggerAddress={dbg}")
                
                if not dbg:
                    raise RuntimeError("Failed to retrieve debuggerAddress from undetected_chromedriver")
                
                self._pw = await async_playwright().start()
                logger.info(f"Conectando o Playwright ao Chrome via CDP em {dbg}...")
                self.browser = await self._pw.chromium.connect_over_cdp(f"http://{dbg}", timeout=60000)
                
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = await self.browser.new_context()
                
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = await self.context.new_page()
                
                try:
                    await self.page.set_viewport_size({"width": 1366, "height": 1200})
                except Exception:
                    pass

                # ── CDP Session for Network Filtering & WebSocket Sniffing ──
                try:
                    cdp = await self.context.new_cdp_session(self.page)
                    await cdp.send("Network.enable")
                    # Block heavy bandwidth video streams, fonts, images and trackers
                    await cdp.send("Network.setBlockedURLs", {
                        "urls": [
                            "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.ico",
                            "*.woff", "*.woff2", "*.ttf", "*.eot",
                            "*.mp4", "*.m3u8", "*.ts", "*.webm", "*.mp3",
                            "*google-analytics.com*", "*hotjar.com*", "*doubleclick.net*",
                            "*segment.io*", "*sentry.io*", "*datadoghq.com*"
                        ]
                    })
                    logger.info("⚡ [Bet365 CDP] Bloqueio de mídia/vídeo e aceleração de rede ativados")
                except Exception as cdp_err:
                    logger.debug(f"[Bet365 CDP] CDP optimization notice: {cdp_err}")
                
                self._is_running = True
                self._last_reload = datetime.now()
                self._consecutive_errors = 0
                logger.info("Bet365 browser launched successfully via UC + Playwright CDP")
            except Exception as e:
                logger.error(f"Failed to launch Bet365 browser: {e}")
                await self._cleanup()
                raise

    async def _cleanup(self):
        """Gracefully close all browser resources and clean up Chrome sessions."""
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
            if hasattr(self, '_pw') and self._pw:
                await self._pw.stop()
        except Exception as e:
            logger.debug(f"[Bet365] Error stopping playwright: {e}")
        self._pw = None
        
        # Close undetected driver
        if self._uc_driver is not None:
            try:
                await asyncio.to_thread(self._uc_driver.quit)
            except Exception as e:
                logger.debug(f"[Bet365] Error quitting UC driver: {e}")
            self._uc_driver = None
            
        self._profile_suffix = f"bet365_uc_{int(time.time())}"
        
        # Best-effort taskkill stale chromedrivers
        try:
            subprocess.run(
                ["taskkill", "/IM", "chromedriver.exe", "/F"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass
        
        logger.info("[Bet365] Shutdown complete.")

    async def stop(self):
        await self._cleanup()

    async def _navigate_to_sport(self, sport_code: str):
        """Navigate to a specific sport's in-play page if not already there."""
        url = f"{BET365_BASE}/#/IP/{sport_code}"
        try:
            current_url = self.page.url if self.page else ""
            if sport_code in current_url or current_url.endswith(sport_code):
                # Already on target in-play sport page — preserve WebSocket live stream!
                return

            logger.info(f"Navegando para {url} via page.goto...")
            await self.page.goto(url, wait_until="commit", timeout=60000)
            
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
                        const [code, expected_header] = args;
                        // O hash precisa terminar exatamente com o codigo, evita que B1 passe no lugar de B13
                        if (!window.location.hash.endsWith(code)) return false;
                        
                        const loader = document.querySelector('.ovm-Loader, .gl-Loader, .wc-Spinner');
                        if (loader) return false;
                        
                        // Garante que o container de eventos carregou
                        const container = document.querySelector('.ipe-EventViewDetail, .ovm-Fixture, [class*="ClassificationHeader"]');
                        if (!container) return false;
                        
                        // Verificacao de Seguranca: Garante que o esporte certo carregou na tela
                        if (expected_header && !document.body.innerText.includes(expected_header)) {
                            return false;
                        }
                        
                        return true;
                    }""",
                    arg=[sport_code, expected_header],
                    timeout=8000
                )
                # Mais 1 segundo para garantir que o DOM foi populado com as odds e placares
                await asyncio.sleep(1)
            except Exception as wait_err:
                logger.warning(f"Timeout waiting for sport load ({sport_code}): {wait_err}. Checking if page actually loaded...")
                current_url = self.page.url
                if sport_code not in current_url:
                    raise TimeoutError(f"Sport page {sport_code} did not load (current URL: {current_url})")
                logger.info(f"Page loaded, but container checks timed out. Proceeding with fallback sleep...")
                await asyncio.sleep(1)
                
            # Dismiss cookie consent/modals on Bet365
            await self._dismiss_cookie_banners()
                
        except Exception as e:
            logger.warning(f"Navigation to {sport_code} failed: {e}")
            raise

    async def _dismiss_cookie_banners(self):
        """Click common BR cookie/age consent buttons if present on Bet365."""
        if not self.page:
            return
        try:
            await self.page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, a, div, span'));
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t === 'Aceitar' || t === 'ACEITAR' || t === 'Permitir Todos' || t === 'Concordar' || t === 'OK' || t === 'Entendi' || t === 'Permitir todos') {
                        try {
                            b.click();
                        } catch(e) {}
                    }
                }
            }""")
            await asyncio.sleep(0.8)
        except Exception:
            pass

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
                    // NOTE: '.gl-Market_General' was intentionally excluded because it wraps
                    // multiple fixtures in a group, causing all matches to share one event ID.
                    const selectors = [
                        '.ovm-Fixture',
                        '.ipe-EventViewDetail',
                        '[class*="Fixture"][class*="ovm"]',
                        '[class*="rcl-ParticipantFixture"]',
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
                                '[class*="FixtureDetailsTwoWay_TeamName"]',
                                '[class*="FixtureDetailsWithIndicators_Team"]',
                                '[class*="Fixture"] [class*="Name"]',
                                '[class*="Team"]',
                            ];
                            
                            let names = [];
                            for (const nSel of nameSelectors) {
                                const nameEls = Array.from(fixture.querySelectorAll(nSel));
                                
                                // Filter out wrapper elements that contain other matched elements
                                // This prevents concatenating 'Player 1' and 'Player 2' into 'Player 1Player 2'
                                const leafEls = nameEls.filter(el => {
                                    return el.querySelectorAll(nSel).length === 0;
                                });
                                
                                const validNames = leafEls
                                    .map(e => e.textContent.trim())
                                    .filter(t => t.length > 0 && !/^\\d+$/.test(t));
                                    
                                if (validNames.length >= 2) {
                                    names = validNames.slice(0, 2);
                                    break;
                                }
                            }
                            
                            if (names.length < 2) continue;
                            const matchName = names.join(' vs ');
                            if (matchName.length < 3) continue;
                            
                            // ── Extract scores ──
                            function isVisible(el) {
                                if (el.offsetParent !== null) return true;
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            }
                            
                            // Target all individual score pill elements
                            const scorePills = Array.from(fixture.querySelectorAll('.ovm-ScorePill'))
                                .filter(isVisible);
                                
                            let p1Scores = [];
                            let p2Scores = [];
                            
                            if (scorePills.length > 0) {
                                // Group score pills by their parent (column wrapper)
                                const parentMap = new Map();
                                for (const pill of scorePills) {
                                    const parent = pill.parentElement;
                                    if (!parentMap.has(parent)) {
                                        parentMap.set(parent, []);
                                    }
                                    parentMap.get(parent).push(pill);
                                }
                                
                                for (const colPills of parentMap.values()) {
                                    const cleanedPills = colPills.map(p => p.textContent.trim())
                                        .filter(t => /^\d+$/.test(t) || /^[Aa]d?v?$/.test(t));
                                    if (cleanedPills.length >= 2) {
                                        p1Scores.push(cleanedPills[0]);
                                        p2Scores.push(cleanedPills[1]);
                                    } else if (cleanedPills.length === 1) {
                                        p1Scores.push(cleanedPills[0]);
                                        p2Scores.push("0");
                                    }
                                }
                            }
                            
                            // Strategy B fallback: flat score extraction
                            let flatScores = [];
                            if (p1Scores.length === 0 && p2Scores.length === 0) {
                                const scoreEls = fixture.querySelectorAll(
                                    '[class*="Score"], [class*="score"], .ovm-ScoreWrapper_Score'
                                );
                                for (const el of scoreEls) {
                                    if (!isVisible(el)) continue;
                                    // ONLY target leaf nodes to avoid concatenated parent texts
                                    if (el.children.length > 0) continue;
                                    const t = el.textContent.trim();
                                    if (/^\d+$/.test(t) || /^[Aa]d?v?$/.test(t)) {
                                        flatScores.push(t);
                                    }
                                }
                            }
                            
                            // ── Extract event link / event ID ──
                            // Live list often has NO EV in DOM — deep link may stay empty (open via click API).
                            let eventId = null;
                            let href = null;
                            
                            const linkEl = fixture.querySelector('a[href*="EV"], a[href*="#/IP/"]');
                            if (linkEl) href = linkEl.getAttribute('href');
                            
                            const dataAttrs = ['data-fixtureid', 'data-eventid', 'data-id', 'data-ev', 'data-fi'];
                            for (const attr of dataAttrs) {
                                const val = fixture.getAttribute(attr);
                                if (val) { eventId = val; break; }
                            }
                            if (!eventId) {
                                for (const child of fixture.children) {
                                    for (const attr of dataAttrs) {
                                        const val = child.getAttribute(attr);
                                        if (val) { eventId = val; break; }
                                    }
                                    if (eventId) break;
                                }
                            }
                            if (!eventId && !href) {
                                const clickable = fixture.querySelector('[onclick*="EV"], [data-nav*="EV"]');
                                if (clickable) {
                                    const onclickStr = clickable.getAttribute('onclick') || 
                                                      clickable.getAttribute('data-nav') || '';
                                    const evMatch = onclickStr.match(/EV\d+[A-Z0-9]*/i);
                                    if (evMatch) eventId = evMatch[0];
                                }
                            }
                            // Sniff fixture HTML for EV… pattern (sometimes embedded in handlers)
                            if (!eventId) {
                                const htmlBit = fixture.outerHTML || '';
                                const m = htmlBit.match(/EV\d{8,}[A-Z0-9]*/i);
                                if (m) eventId = m[0];
                            }
                            
                            // ── Extract league / tournament name ──
                            let league = '';
                            try {
                                const isGarbageLeague = (t) => {
                                    if (!t || t.length < 4) return true;
                                    const low = t.toLowerCase().replace(/\s+/g, '');
                                    // Bet365 UI chrome often concatenates: PrincipalPartidaGame or duplicates
                                    if (/principal|partida/i.test(low)) return true;
                                    if (/^(game|set|pts|live|aovivo|principal|partida)+$/i.test(low)) return true;
                                    return false;
                                };
                                let el = fixture;
                                for (let i = 0; i < 10 && el; i++) {
                                    el = el.parentElement;
                                    if (!el) break;
                                    const hdr = el.querySelector('.ovm-ClassificationHeader, [class*="ClassificationHeader"]');
                                    if (hdr) {
                                        const t = hdr.textContent.trim().replace(/\s+/g, ' ');
                                        if (!isGarbageLeague(t)) { league = t; break; }
                                    }
                                }
                                if (!league) {
                                    let prev = fixture.previousElementSibling;
                                    while (prev) {
                                        if (prev.classList && (prev.classList.contains('ovm-ClassificationHeader') || (prev.className && String(prev.className).includes('ClassificationHeader')))) {
                                            const t = prev.textContent.trim().replace(/\s+/g, ' ');
                                            if (!isGarbageLeague(t)) { league = t; break; }
                                        }
                                        prev = prev.previousElementSibling;
                                    }
                                }
                            } catch(e) {}
                            
                            results.push({
                                name: matchName,
                                p1: p1Scores,
                                p2: p2Scores,
                                flat: flatScores,
                                eventId: eventId,
                                href: href,
                                league: league,
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
                        extra_data={"league": item.get('league', '')},
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
        return set_score, game_score, point_score

    async def extract_optical_scoreboard(self, element_locator) -> Tuple[str, str, str]:
        """
        Takes a visual screenshot of a Bet365 scoreboard widget and extracts digits via OpticalScoreboardReader.
        100% visual fidelity in < 0.4ms.
        """
        if not self._optical_reader or not element_locator:
            return "0:0", "0:0", "0"
        try:
            png_bytes = await element_locator.screenshot(type="png")
            if not png_bytes:
                return "0:0", "0:0", "0"
            img = self._optical_reader.decode_image_bytes(png_bytes)
            if img is not None and img.size > 0:
                return self._optical_reader.parse_scoreboard_image(img)
        except Exception as e:
            logger.debug(f"[Bet365 Optical] Error reading scoreboard crop: {e}")
        return "0:0", "0:0", "0"

    async def verify_match_deep(self, url: str, b365_event, burger_event) -> bool:
        """
        Navigates to the match details page and checks if the real score is updated.
        Returns True if the match is STILL frozen (True divergence).
        Returns False if the match is actually updated (Fake divergence).
        """
        if not self.context:
            return True
            
        logger.info(f"[DeepVerifier] Checking real score for {b365_event.match_name} at {url}")
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(4) # Wait for scoreboard to render
            
            # Extract structured scoreboard columns and rows from match details page
            data = await page.evaluate("""
                () => {
                    const scoreboard = document.querySelector('.ml1-ScoreHeader, .ml1-DetailedScoreboard, [class*="ScoreHeader"], [class*="Scoreboard"]');
                    const rows = scoreboard ? Array.from(scoreboard.querySelectorAll('[class*="TeamRow"], [class*="Row"]')) : [];
                    
                    let p1Scores = [];
                    let p2Scores = [];
                    
                    if (rows.length >= 2) {
                        const p1Cells = rows[0].querySelectorAll('[class*="Score"], [class*="Cell"], [class*="Point"], [class*="Pill"]');
                        const p2Cells = rows[1].querySelectorAll('[class*="Score"], [class*="Cell"], [class*="Point"], [class*="Pill"]');
                        
                        p1Scores = Array.from(p1Cells)
                            .map(c => c.textContent.trim())
                            .filter(t => /^\\d+$/.test(t) || /^[Aa]d?v?$/.test(t));
                            
                        p2Scores = Array.from(p2Cells)
                            .map(c => c.textContent.trim())
                            .filter(t => /^\\d+$/.test(t) || /^[Aa]d?v?$/.test(t));
                    }
                    
                    // Fallback to all score pills on page if structured rows not found
                    let flatScores = [];
                    if (p1Scores.length === 0 && p2Scores.length === 0) {
                        const scoreEls = document.querySelectorAll(
                            '[class*="Score"], [class*="score"], .ovm-ScoreWrapper_Score'
                        );
                        for (const el of scoreEls) {
                            if (el.children.length > 0) continue;
                            const t = el.textContent.trim();
                            if (/^\\d+$/.test(t) || /^[Aa]d?v?$/.test(t)) {
                                flatScores.push(t);
                            }
                        }
                    }
                    
                    return { p1: p1Scores, p2: p2Scores, flat: flatScores };
                }
            """)
            
            p1 = data.get('p1', [])
            p2 = data.get('p2', [])
            flat = data.get('flat', [])
            
            internal_set, internal_game, internal_point = self._parse_scores_structured(
                p1, p2, flat, b365_event.sport
            )
            
            # Check if BetBurger is still ahead of the internal Bet365 score
            burger_still_ahead = self._is_burger_ahead(
                internal_set, internal_game,
                burger_event.set_score, burger_event.game_score,
                internal_point, burger_event.point_score
            )
            
            if burger_still_ahead:
                logger.info(
                    f"[DeepVerifier] Verified: BetBurger {burger_event.set_score} ({burger_event.game_score}) Pts: {burger_event.point_score} "
                    f"is still ahead of internal Bet365 score {internal_set} ({internal_game}) Pts: {internal_point}. True divergence!"
                )
                return True
            else:
                logger.info(
                    f"[DeepVerifier] Discarded: Internal Bet365 score {internal_set} ({internal_game}) Pts: {internal_point} "
                    f"has caught up or is ahead of BetBurger {burger_event.set_score} ({burger_event.game_score}). Fake divergence."
                )
                return False
                
        except Exception as e:
            logger.warning(f"[DeepVerifier] Failed to verify {url}: {e}")
            return True # If verification fails, assume it's a true divergence to be safe
        finally:
            await page.close()

    def _parse_score_pair(self, score: str) -> tuple:
        """Parse 'H:A' into (home, away) ints. Returns (0,0) on failure."""
        try:
            parts = score.split(":")
            if len(parts) >= 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            pass
        return 0, 0

    # Tennis point ordering: Ad > 40 > 30 > 15 > 0
    _TENNIS_PTS_ORDER = {'0': 0, '15': 1, '30': 2, '40': 3, 'ad': 4, 'adv': 4, 'a': 4}

    def _tennis_pt_value(self, pt: str) -> int:
        """Convert a tennis point string to a numeric order value."""
        return self._TENNIS_PTS_ORDER.get(str(pt).lower().strip(), -1)

    def _is_burger_ahead(self, b365_sets: str, b365_score: str, burger_sets: str, burger_score: str,
                         b365_points: str = "0", burger_points: str = "0") -> bool:
        """Checks if BetBurger is strictly ahead of Bet365 (sets, games, or points)."""
        try:
            # 1. Compare total completed sets
            b365_s_h, b365_s_a = self._parse_score_pair(b365_sets)
            burger_s_h, burger_s_a = self._parse_score_pair(burger_sets)

            b365_total_sets = b365_s_h + b365_s_a
            burger_total_sets = burger_s_h + burger_s_a

            if burger_total_sets > b365_total_sets:
                return True
            if burger_total_sets < b365_total_sets:
                return False

            # 2. If same set count, compare game/score totals
            b365_g_h, b365_g_a = self._parse_score_pair(b365_score)
            burger_g_h, burger_g_a = self._parse_score_pair(burger_score)

            burger_game_total = burger_g_h + burger_g_a
            b365_game_total = b365_g_h + b365_g_a

            if burger_game_total > b365_game_total:
                return True
            if burger_game_total < b365_game_total:
                return False

            # 3. Games equal — compare point scores
            b365_pts_parts = str(b365_points).split(':') if b365_points and b365_points != '0' else []
            burger_pts_parts = str(burger_points).split(':') if burger_points and burger_points != '0' else []

            if b365_pts_parts and burger_pts_parts and len(b365_pts_parts) == 2 and len(burger_pts_parts) == 2:
                is_tennis_pts = any(
                    p.lower() in self._TENNIS_PTS_ORDER
                    for p in b365_pts_parts + burger_pts_parts
                    if not p.isdigit() or int(p) in (0, 15, 30, 40)
                )

                if is_tennis_pts:
                    b365_pt_h = self._tennis_pt_value(b365_pts_parts[0])
                    b365_pt_a = self._tennis_pt_value(b365_pts_parts[1])
                    burger_pt_h = self._tennis_pt_value(burger_pts_parts[0])
                    burger_pt_a = self._tennis_pt_value(burger_pts_parts[1])
                    b365_pt_total = b365_pt_h + b365_pt_a
                    burger_pt_total = burger_pt_h + burger_pt_a
                    return burger_pt_total > b365_pt_total
                else:
                    try:
                        b365_pt_total = int(b365_pts_parts[0]) + int(b365_pts_parts[1])
                        burger_pt_total = int(burger_pts_parts[0]) + int(burger_pts_parts[1])
                        return burger_pt_total > b365_pt_total
                    except ValueError:
                        pass
            return False
        except Exception:
            return False

    def _normalize_ev_id(self, raw: str) -> str:
        """Normalize to EVxxxxxxxxxxxxC# form when possible."""
        if not raw:
            return ""
        s = str(raw).strip()
        m = re.search(r"(EV\d+[A-Z0-9]*)", s, re.I)
        if m:
            ev = m.group(1).upper()
        else:
            digits = re.sub(r"\D", "", s)
            if len(digits) < 8:
                return ""
            ev = f"EV{digits}"
        if not re.search(r"C\d+$", ev, re.I):
            ev = f"{ev}C1"
        return ev

    def _build_deep_link(self, event_id: Optional[str], href: Optional[str], sport: str) -> str:
        """
        Build a deep link ONLY when we have a real event id (EV…).
        Never return the generic sport list (#/IP/B92) as if it were the match —
        that was opening the wrong page for users.
        Correct in-play form: https://www.bet365.bet.br/#/IP/EV…C1
        """
        # 1) EV inside href
        if href:
            ev = self._normalize_ev_id(href)
            if ev:
                return f"{BET365_BASE}/#/IP/{ev}"
            h = href.strip()
            if h.startswith("http") and re.search(r"EV\d+", h, re.I):
                return h
            if h.startswith("#/") and re.search(r"EV\d+", h, re.I):
                # Ensure /IP/ for live
                if "/IP/" not in h.upper():
                    ev2 = self._normalize_ev_id(h)
                    if ev2:
                        return f"{BET365_BASE}/#/IP/{ev2}"
                return f"{BET365_BASE}/{h.lstrip('/')}" if h.startswith("#") else f"{BET365_BASE}/#{h}"

        # 2) Explicit event id
        if event_id:
            ev = self._normalize_ev_id(event_id)
            if ev:
                return f"{BET365_BASE}/#/IP/{ev}"

        # 3) No reliable event id — empty (frontend will open via scraper click API)
        return ""

    def sport_listing_url(self, sport: str = "tabletennis") -> str:
        """Public listing page (not a match deep link)."""
        code = SPORT_CODES.get(sport, "B92")
        return f"{BET365_BASE}/#/IP/{code}"

    async def open_match_by_name(self, match_name: str) -> dict:
        """
        Focus the Bet365 Chrome window and click the fixture matching match_name.
        Used when DOM has no EV id (list-only live view).
        """
        if not self.page or not self._is_running:
            return {"ok": False, "error": "Bet365 scraper offline"}

        name = (match_name or "").strip()
        if not name:
            return {"ok": False, "error": "Nome vazio"}

        # Tokens from "A vs B" / "A x B"
        cleaned = re.sub(r"\s+v(?:s)?\.?\s+|\s+x\s+", " ", name, flags=re.I)
        tokens = [t.lower() for t in re.split(r"\s+", cleaned) if len(t) >= 3]
        if not tokens:
            tokens = [t.lower() for t in name.split() if len(t) >= 2]

        try:
            # Ensure we are on table tennis live list
            sport_code = "B92"
            if "B92" not in (self.page.url or ""):
                await self._navigate_to_sport(sport_code)
                await asyncio.sleep(2)

            fixtures = self.page.locator(".ovm-Fixture")
            n = await fixtures.count()
            best_i = -1
            best_score = 0
            for i in range(n):
                try:
                    text = (await fixtures.nth(i).inner_text(timeout=1000) or "").lower()
                    score = sum(1 for t in tokens if t in text)
                    if score > best_score:
                        best_score = score
                        best_i = i
                except Exception:
                    continue

            if best_i < 0 or best_score < max(1, min(2, len(tokens) // 2)):
                # Fallback: open listing only
                listing = self.sport_listing_url("tabletennis")
                await self.page.goto(listing, wait_until="commit", timeout=30000)
                self._bring_chrome_to_front()
                return {
                    "ok": False,
                    "error": f"Partida não encontrada na lista Bet365 (tokens={tokens})",
                    "listing_url": listing,
                }

            await fixtures.nth(best_i).click(timeout=3000)
            await asyncio.sleep(0.8)
            self._bring_chrome_to_front()
            logger.info(f"[Bet365] Abriu fixture '{name}' (score={best_score}, idx={best_i})")
            return {
                "ok": True,
                "matched_tokens": best_score,
                "url": self.page.url,
                "message": "Jogo focado no Chrome da Bet365",
            }
        except Exception as e:
            logger.error(f"[Bet365] open_match_by_name error: {e}")
            return {"ok": False, "error": str(e)}

    def _bring_chrome_to_front(self):
        """Best-effort focus of the Bet365 Chrome window (Windows)."""
        try:
            pid = getattr(self.chrome_process, "pid", None)
            if not pid:
                return
            # PowerShell: restore + foreground by process id
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
                    f"if($p){{ Add-Type -Name W -Namespace N -MemberDefinition "
                    f"'[DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr h);"
                    f"[DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr h,int n);'; "
                    f"$h=$p.MainWindowHandle; if($h -ne [IntPtr]::Zero){{ [N.W]::ShowWindow($h,9); [N.W]::SetForegroundWindow($h) }} }}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    async def force_hard_reload(self):
        """Forces an immediate hard reload of the SPA to verify frozen scores."""
        now = datetime.now()
        if (now - self._last_reload).total_seconds() < 20:
            return  # Prevent spamming reloads
            
        logger.info("[Bet365] Executing VERIFICATION RELOAD to clear false positives...")
        try:
            current_url = self.page.url
            try:
                await self.page.evaluate("window.location.reload(true)")
            except Exception:
                await self.page.goto("about:blank", wait_until="commit")
                await self.page.goto(current_url, wait_until="commit")
            
            # Wait for the page to visually render and websocket to reconnect
            await asyncio.sleep(4)
            self._last_reload = now
        except Exception as e:
            logger.warning(f"Verification reload failed: {e}")

    async def fetch_live_events(self) -> List[NormalizedEvent]:
        """
        Main entry: fetch all live events across configured sports.
        Launches browser if needed, navigates to each sport, extracts events.
        """
        if not self._is_running:
            await self._launch_browser()
            
        now = datetime.now()
        # Fallback: Force a hard reload every 90 seconds to prevent WebSocket connection freeze / DOM throttling
        if (now - self._last_reload).total_seconds() > 90:
            logger.info("[Bet365] Performing scheduled 90-second anti-freeze reload...")
            asyncio.create_task(self.force_hard_reload())
        
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
