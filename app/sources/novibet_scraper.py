import asyncio
import logging
import re
import os
import subprocess
from datetime import datetime
from typing import List, Optional

from sources.base_source import BaseSource
from core.normalizer import NormalizedEvent

logger = logging.getLogger("novibet_scraper")

class NovibetScraper(BaseSource):
    def __init__(self, headless: bool = False, sports: Optional[List[str]] = None):
        super().__init__()
        self.headless = headless
        self.sports = sports or ["tabletennis"]
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.chrome_process = None
        self._is_running = False
        self._last_reload = datetime.now()
        self._errors_count = 0
        self._max_errors_before_restart = 10
        self.port = 9226

    def get_name(self) -> str:
        return "novibet"

    async def start(self):
        """Starts the Chrome process in debug mode or attaches to an existing debug session."""
        self._is_running = True
        logger.info("[Novibet] Iniciando Novibet Scraper...")
        
        # 1. First attempt: try to attach to an already running Chrome debug session on port 9226
        try:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            logger.info(f"[Novibet] Tentando acoplar em Chrome já existente na porta {self.port}...")
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}", timeout=5000)
            logger.info(f"[Novibet] Acoplado com sucesso no Chrome externo na porta {self.port}!")
            
            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            
            # Just verify page state, navigate if needed
            if "novibet.bet.br" not in self.page.url:
                await self._navigate_to_source()
            self._last_reload = datetime.now()
            self._errors_count = 0
            return
        except Exception as attach_err:
            logger.info(f"[Novibet] Sem Chrome externo ativo na porta {self.port} ({attach_err}). Iniciando nova instância local...")
            # Clean up playwright instance before launching subprocess
            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass
                self.playwright = None

        # 2. Second attempt: Launch Chrome via undetected_chromedriver to bypass Cloudflare WAF
        try:
            import undetected_chromedriver as uc
            local_app_data = os.environ.get('LOCALAPPDATA')
            if local_app_data:
                user_data_dir = os.path.join(local_app_data, "OddsDivergenceMonitor", "chrome_data_novibet")
            else:
                user_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chrome_data_novibet")
            os.makedirs(user_data_dir, exist_ok=True)

            opts = uc.ChromeOptions()
            opts.add_argument(f"--user-data-dir={user_data_dir}")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--window-size=1366,3500")
            opts.add_argument("--lang=pt-BR")

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

            self._uc_driver = await asyncio.to_thread(
                lambda: uc.Chrome(options=opts, headless=False, use_subprocess=True, version_main=chrome_major)
            )
            await asyncio.sleep(3)

            dbg = (self._uc_driver.capabilities.get("goog:chromeOptions") or {}).get("debuggerAddress")
            logger.info(f"[Novibet] UC debuggerAddress={dbg}")

            if not dbg:
                raise RuntimeError("Failed to retrieve debuggerAddress from undetected_chromedriver for Novibet")

            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            logger.info(f"[Novibet] Conectando Playwright CDP em {dbg}...")
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://{dbg}", timeout=60000)

            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

            await self._navigate_to_source()
            self._last_reload = datetime.now()
            self._errors_count = 0

        except Exception as e:
            logger.error(f"[Novibet] Falha ao iniciar UC Chrome / conectar Playwright CDP: {e}")
            await self.stop()

    async def stop(self):
        """Stops the browser and kills the subprocess Chrome instance."""
        self._is_running = False
        logger.info("[Novibet] Parando Novibet scraper...")
        
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None
            
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
            self.playwright = None
            
        if self.chrome_process:
            pid = self.chrome_process.pid
            logger.info(f"[Novibet] Encerrando processo Chrome PID={pid}...")
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5)
            except Exception as e:
                logger.warning(f"[Novibet] Erro ao dar taskkill no Chrome PID {pid}: {e}")
                try:
                    self.chrome_process.terminate()
                except:
                    pass
            self.chrome_process = None
            
        logger.info("[Novibet] Novibet scraper paralisado.")

    async def _navigate_to_source(self):
        """Navigates to Table Tennis section directly on coupon tab and dismisses overlays."""
        if not self.page:
            return
        url = "https://www.novibet.bet.br/apostas-esportivas/tenis-de-mesas/4372722/coupon"
        logger.info(f"[Novibet] Navegando via page.goto para {url}...")
        try:
            await self.page.goto(url, timeout=50000, wait_until="domcontentloaded")
            await asyncio.sleep(6)
            
            logger.info("[Novibet] Aguardando e dispensando Cookiebot e verificação de idade (+18)...")
            for attempt in range(5):
                overlays_dismissed = await self.page.evaluate("""() => {
                    let clickedAny = false;
                    const cookieBtn = document.getElementById('CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll');
                    if (cookieBtn) {
                        cookieBtn.click();
                        clickedAny = true;
                    }
                    const buttons = Array.from(document.querySelectorAll('button, nds-button button, .button'));
                    const ageBtn = buttons.find(b => b.textContent.includes('Eu tenho mais de 18 anos'));
                    if (ageBtn) {
                        ageBtn.click();
                        clickedAny = true;
                    }
                    const closeBtn = document.querySelector('.close, [class*="close"], [class*="Close"], [aria-label="close"]');
                    if (closeBtn) {
                        closeBtn.click();
                        clickedAny = true;
                    }
                    return clickedAny;
                }""")
                if overlays_dismissed:
                    logger.info(f"[Novibet] Overlays clicados (tentativa {attempt + 1}). Aguardando fechamento...")
                await asyncio.sleep(2)
            
            logger.info("[Novibet] Verificando aba ativa...")
            clicked_tab = await self.page.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll('div, span, button, a'));
                const partidasTab = elements.find(el => el.textContent.trim() === 'Partidas');
                if (partidasTab) {
                    partidasTab.click();
                    return true;
                }
                return false;
            }""")
            logger.info(f"[Novibet] Clique alternativo na aba 'Partidas' retornado: {clicked_tab}")
            
            await asyncio.sleep(4)
            
        except Exception as e:
            logger.error(f"[Novibet] Erro durante a navegação e bypass de overlays: {e}")
            self._errors_count += 1

    async def force_hard_reload(self):
        """Forces page reload to clear WebSocket freeze."""
        if not self._is_running or not self.page:
            return
        logger.info("[Novibet] Realizando F5 periódico para atualizar WebSocket...")
        await self._navigate_to_source()
        self._last_reload = datetime.now()

    def _normalize_competitor(self, name: str) -> str:
        cleaned = name.lower().strip()
        cleaned = re.sub(r'\s+v(?:s)?\.?\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s+x\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s*[-/]\s*', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    async def fetch_live_events(self) -> List[NormalizedEvent]:
        """Extracts live Table Tennis events from the DOM."""
        if not self._is_running:
            await self.start()
            if not self._is_running:
                return []

        # 1. Periodic refresh check (every 3 minutes)
        time_since_reload = (datetime.now() - self._last_reload).total_seconds()
        if time_since_reload > 180.0:
            await self.force_hard_reload()

        # 2. Restart browser if error count is high
        if self._errors_count >= self._max_errors_before_restart:
            logger.warning(f"[Novibet] Erros consecutivos ({self._errors_count}) atingiram o limite. Reiniciando browser...")
            await self.stop()
            await self.start()
            if not self._is_running:
                return []

        events: List[NormalizedEvent] = []
        try:
            # 3. Read events from page DOM
            raw_matches = await self.page.evaluate("""() => {
                const results = [];
                const rows = Array.from(document.querySelectorAll('sb-event-row'));
                
                rows.forEach(row => {
                    const classList = Array.from(row.classList);
                    const isPrelive = classList.includes('prelive');
                    const isLive = classList.some(c => c.includes('live')) || row.querySelector('sb-event-row-scoreboard');
                    
                    if (isPrelive || !isLive) return;
                    
                    try {
                        const leagueEl = row.querySelector('sb-event-header span');
                        const league = leagueEl ? leagueEl.textContent.trim() : 'Tênis de Mesa';
                        
                        const leagueLow = league.toLowerCase();
                        const ttKeywords = ['tenis de mesa', 'tênis de mesa', 'table tennis', 'tt-', 'setka', 'liga pro', 'tt cup', 'elite series', 'setka cup', 'setka copa'];
                        const isTT = ttKeywords.some(kw => leagueLow.includes(kw));
                        if (!isTT) return;
                        
                        const homeEl = row.querySelector('.eventRow_home span.u-text-ellipsis');
                        const awayEl = row.querySelector('.eventRow_away span.u-text-ellipsis');
                        if (!homeEl || !awayEl) return;
                        
                        const home = homeEl.textContent.trim();
                        const away = awayEl.textContent.trim();
                        
                        const linkEl = row.querySelector('a.eventRow_teams');
                        const href = linkEl ? linkEl.getAttribute('href') : '';
                        const deepLink = href ? 'https://www.novibet.bet.br' + href : '';
                        
                        const scoreSpans = Array.from(row.querySelectorAll('.eventRowScoreboard_score'));
                        let setScore = '0:0';
                        let gameScore = '0:0';
                        
                        if (scoreSpans.length >= 4) {
                            const noBoldSpans = scoreSpans.filter(s => s.classList.contains('noBold'));
                            const setSpans = scoreSpans.filter(s => s.classList.contains('set'));
                            
                            if (setSpans.length >= 2) {
                                setScore = `${setSpans[0].textContent.trim()}:${setSpans[1].textContent.trim()}`;
                            }
                            if (noBoldSpans.length >= 2) {
                                gameScore = `${noBoldSpans[0].textContent.trim()}:${noBoldSpans[1].textContent.trim()}`;
                            } else {
                                gameScore = `${scoreSpans[0].textContent.trim()}:${scoreSpans[1].textContent.trim()}`;
                            }
                        } else if (scoreSpans.length >= 2) {
                            gameScore = `${scoreSpans[0].textContent.trim()}:${scoreSpans[1].textContent.trim()}`;
                        }
                        
                        results.push({
                            league: league,
                            home: home,
                            away: away,
                            set_score: setScore,
                            game_score: gameScore,
                            deep_link: deepLink
                        });
                    } catch (e) {
                    }
                });
                return results;
            }""")

            # 4. Standardize and normalize
            now = datetime.now()
            for item in raw_matches:
                home = item["home"]
                away = item["away"]
                match_name = f"{home} vs {away}"
                match_id = self._normalize_competitor(match_name)
                
                if item["game_score"] == "0:0" and item["set_score"] == "0:0":
                    continue
                    
                events.append(NormalizedEvent(
                    match_id=match_id,
                    match_name=match_name,
                    sport="tabletennis",
                    source="novibet",
                    set_score=item["set_score"],
                    game_score=item["game_score"],
                    point_score="0:0",
                    timestamp=now,
                    deep_link=item["deep_link"],
                    extra_data={"league": item["league"]}
                ))
                
            self._errors_count = 0
            logger.info(f"[Novibet] Extraídos {len(events)} jogos de Tênis de Mesa ao vivo.")
            
        except Exception as e:
            logger.error(f"[Novibet] Erro ao extrair partidas: {e}")
            self._errors_count += 1
            
        return events
