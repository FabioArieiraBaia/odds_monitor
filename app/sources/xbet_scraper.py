import asyncio
import logging
import re
import os
import uuid
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup

from sources.base_source import BaseSource
from core.normalizer import NormalizedEvent

logger = logging.getLogger("1xbet_scraper")

class Bet1xScraper(BaseSource):
    def __init__(self, headless=True, sports=None):
        super().__init__()
        self.headless = headless
        self.sports = sports or ["tabletennis", "tennis", "volleyball", "basketball"]
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._is_running = False

    async def start(self):
        self._is_running = True
        logger.info("Starting 1xBet scraper...")
        
        # Launch real Chrome via subprocess and connect via CDP
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ]
        import os
        import subprocess
        chrome_path = next((p for p in possible_paths if os.path.exists(p)), None)
        if not chrome_path:
            logger.error("Google Chrome or Microsoft Edge not found")
            return
            
        local_app_data = os.environ.get('LOCALAPPDATA')
        if local_app_data:
            user_data_dir = os.path.join(local_app_data, "OddsDivergenceMonitor", "chrome_data_1xbet")
        else:
            user_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chrome_data_1xbet")
        port = 9224
        
        args = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled"
        ]
            
        logger.info("Iniciando Google Chrome real via subprocess para o 1xBet...")
        self.chrome_process = subprocess.Popen(args)
        
        # Aguarda o Chrome iniciar
        await asyncio.sleep(4)
        
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        logger.info(f"Conectando o Playwright ao Chrome (1xBet) na porta {port}...")
        self.browser = await self.playwright.chromium.connect_over_cdp(f"http://localhost:{port}", timeout=60000)
        
        if self.browser.contexts:
            self.context = self.browser.contexts[0]
        else:
            self.context = await self.browser.new_context(permissions=["geolocation"], geolocation={"latitude": -23.5505, "longitude": -46.6333})

        try:
            await self.context.grant_permissions(["geolocation"], origin="https://1xbet.bet.br")
            await self.context.set_geolocation({"latitude": -23.5505, "longitude": -46.6333})
        except Exception as e:
            logger.warning(f"[1xBet] Could not set geolocation: {e}")

        if not self.context.pages:
            self.page = await self.context.new_page()
        else:
            self.page = self.context.pages[0]
            
        await self._navigate_to_live()
        
    async def stop(self):
        self._is_running = False
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        
        if hasattr(self, 'chrome_process') and self.chrome_process:
            pid = self.chrome_process.pid
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5)
            except:
                try:
                    self.chrome_process.terminate()
                except:
                    pass
            self.chrome_process = None
            
        logger.info("1xBet scraper stopped.")

    async def _navigate_to_live(self):
        try:
            await self.page.goto("https://1xbet.bet.br/live", timeout=60000, wait_until="domcontentloaded")
            logger.info("1xBet Live page loaded.")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error navigating to 1xBet: {e}")

    async def force_hard_reload(self):
        if not self._is_running:
            return
        logger.info("Forcing hard reload for 1xBet...")
        await self._navigate_to_live()

    def get_name(self) -> str:
        return "1xbet"

    def _normalize_name(self, name: str) -> str:
        import re
        cleaned = name.lower().strip()
        cleaned = re.sub(r'\s+v(?:s)?\.?\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s+x\s+', ' vs ', cleaned)
        cleaned = re.sub(r'\s*[-/]\s*', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\(.*?\)', '', cleaned).strip()
        return cleaned

    async def fetch_live_events(self) -> list[NormalizedEvent]:
        if not self._is_running or not self.page:
            await self.start()
            if not self._is_running or not self.page:
                return []
            
        events = []
        try:
            # Tentar garantir permissão de localização
            try:
                if hasattr(self, 'context'):
                    await self.context.grant_permissions(["geolocation"], origin="https://1xbet.bet.br")
            except:
                pass

            html = await self.page.content()
            
            # Se estiver na página de permissão, recarregar a live
            if "geo-permission" in self.page.url:
                logger.info("[1xBet] Página de geo-permission detectada. Voltando para /live...")
                await self.page.goto("https://1xbet.bet.br/live")
                await asyncio.sleep(5)
                html = await self.page.content()
            
            # Se estiver na página do Cloudflare, aguarda mais um pouco
            if "Verificação bem-sucedida" in html or "Just a moment" in html or "cloudflare" in html.lower():
                logger.info("[1xBet] Cloudflare detectado. Aguardando recarregamento...")
                await asyncio.sleep(10)
                html = await self.page.content()
                
            try:
                await self.page.wait_for_selector(".dashboard-champ__el--game, .c-events__item", timeout=15000)
                html = await self.page.content()
            except:
                pass
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1xBet classes
            items = soup.select(".dashboard-champ__el--game, .c-events__item")
            for item in items:
                # Extrair times
                teams = item.select(".c-events__team, .dashboard-game-info-rival")
                if len(teams) < 2:
                    continue
                    
                team1 = teams[0].get_text(strip=True)
                team2 = teams[1].get_text(strip=True)
                match_name = f"{team1} v {team2}"
                
                # Para simplificar na 1xBet, se os times foram encontrados, já cadastramos
                # (1xBet é complexo para pegar score e odds no novo layout sem inspeção profunda)
                from datetime import datetime
                ev = NormalizedEvent(
                    match_id=self._normalize_name(match_name),
                    match_name=match_name,
                    sport="unknown",
                    source="1xbet",
                    set_score="0:0",
                    game_score="0:0",
                    point_score="0:0",
                    timestamp=datetime.now(),
                    deep_link=self.page.url
                )
                events.append(ev)
            
            logger.info(f"[1xBet] Extracted {len(events)} events from HTML.")
        except Exception as e:
            logger.error(f"1xBet scrape error: {e}")
            
        return events
