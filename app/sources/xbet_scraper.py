import asyncio
import logging
import re
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
            
        user_data_dir = os.path.join(os.getcwd(), "chrome_data_1xbet")
        port = 9224
        
        args = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled"
        ]
        if self.headless:
            args.extend(["--headless=new", "--window-size=1920,1080"])
            
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
            self.context = await self.browser.new_context()
            
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()
            
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
            await self.page.goto("https://1xbet.com/br/live", timeout=60000, wait_until="domcontentloaded")
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

    async def fetch_live_events(self) -> list[NormalizedEvent]:
        if not self._is_running or not self.page:
            await self.start()
            if not self._is_running or not self.page:
                return []
            
        events = []
        try:
            html = await self.page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1xBet classes are usually .c-events__item
            items = soup.select(".c-events__item")
            for item in items:
                teams = item.select(".c-events__team")
                if len(teams) < 2:
                    continue
                team1 = teams[0].get_text(strip=True)
                team2 = teams[1].get_text(strip=True)
                match_name = f"{team1} v {team2}"
                
                scores = item.select(".c-events-scoreboard__line")
                if len(scores) < 2:
                    continue
                score1 = scores[0].get_text(separator=' ', strip=True)
                score2 = scores[1].get_text(separator=' ', strip=True)
                
                s1_parts = [p for p in score1.split() if p.isdigit()]
                s2_parts = [p for p in score2.split() if p.isdigit()]
                
                game_score = "0:0"
                set_score = "0:0"
                if len(s1_parts) >= 1 and len(s2_parts) >= 1:
                    game_score = f"{s1_parts[-1]}:{s2_parts[-1]}"
                if len(s1_parts) >= 2 and len(s2_parts) >= 2:
                    set_score = f"{s1_parts[0]}:{s2_parts[0]}"

                events.append(NormalizedEvent(
                    source="1xbet",
                    match_id=f"1x_{team1}_{team2}".replace(" ", "_"),
                    match_name=match_name,
                    sport="unknown",
                    set_score=set_score,
                    game_score=game_score,
                    point_score="0",
                    deep_link=self.page.url
                ))
            
        except Exception as e:
            logger.error(f"1xBet scrape error: {e}")
            
        return events
