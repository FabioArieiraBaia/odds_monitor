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
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()
        
        await self._navigate_to_live()
        
    async def stop(self):
        self._is_running = False
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
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
