import asyncio
import logging
import re
from typing import List
from datetime import datetime
import aiohttp

from sources.base_source import BaseSource
from core.normalizer import NormalizedEvent

logger = logging.getLogger("1xbet_scraper")

# 1xBet / 22Bet live API for Table Tennis (Sport ID 10)
ONEXBET_API_URL = "https://22bet.com/LiveFeed/Get1x2_VZip?sports=10&count=50&mode=4"


class OneXBetScraper(BaseSource):
    """
    Scraper for 1xBet / 22Bet live API.
    Very fast, returns JSON directly without needing a browser.
    """
    def __init__(self):
        super().__init__()
        self._session = None
        self._consecutive_errors = 0

    def get_name(self) -> str:
        return "1xbet"

    async def start(self):
        if not self._session or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=4, connect=2)
            connector = aiohttp.TCPConnector(
                keepalive_timeout=300,
                ttl_dns_cache=600,
                limit_per_host=10,
                enable_cleanup_closed=True,
                force_close=False
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                }
            )

    async def stop(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _normalize_name(self, name: str) -> str:
        """Normalize match name to match Bet365 cache key format."""
        cleaned = name.lower().strip()
        cleaned = re.sub(r"\s+v(?:s)?\.?\s+", " vs ", cleaned)
        cleaned = re.sub(r"\s+x\s+", " vs ", cleaned)
        cleaned = re.sub(r"\s*[-/]\s*", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
        return cleaned

    def _parse_scores(self, match_data: dict) -> tuple:
        """
        Extract Set and Game score from 1xBet SC.FS / SC.CPS block.
        Returns (set_score, game_score, point_score)
        """
        set_score = "0:0"
        game_score = "0:0"
        point_score = "0"
        
        try:
            sc = match_data.get("SC", {})
            fs = sc.get("FS", {})
            
            # Global sets score
            s1 = fs.get("S1", 0)
            s2 = fs.get("S2", 0)
            set_score = f"{s1}:{s2}"
            
            # Current game score
            ps = sc.get("PS", [])
            if ps:
                last_period = ps[-1]
                val = last_period.get("Value", {})
                p1 = val.get("S1", 0)
                p2 = val.get("S2", 0)
                game_score = f"{p1}:{p2}"
        except Exception as e:
            logger.debug(f"[1xbet] score parse error: {e}")
            
        return set_score, game_score, point_score

    async def fetch_live_events(self) -> List[NormalizedEvent]:
        if not self._session or self._session.closed:
            await self.start()
            
        events = []
        try:
            async with self._session.get(ONEXBET_API_URL) as response:
                if response.status != 200:
                    logger.warning(f"[1xbet] API error: HTTP {response.status}")
                    self._consecutive_errors += 1
                    return []
                
                data = await response.json()
                self._consecutive_errors = 0
                now = datetime.now()
                
                for item in data.get("Value", []):
                    # Use O1E/O2E (English names) instead of O1/O2 (Cyrillic/local)
                    player1 = item.get("O1E") or item.get("O1", "")
                    player2 = item.get("O2E") or item.get("O2", "")
                    if not player1 or not player2:
                        continue
                    
                    # Remove country suffix like "(Ros)" from English names
                    player1 = re.sub(r"\s*\(.*?\)\s*$", "", player1).strip()
                    player2 = re.sub(r"\s*\(.*?\)\s*$", "", player2).strip()
                        
                    match_name = f"{player1} vs {player2}"
                    match_id = self._normalize_name(match_name)
                    
                    set_score, game_score, point_score = self._parse_scores(item)
                    
                    event_id = item.get("I", "")
                    league = item.get("LE", "") or item.get("L", "")
                    
                    deep_link = f"https://22bet.com/live/table-tennis/{event_id}" if event_id else ""
                    
                    events.append(NormalizedEvent(
                        match_id=match_id,
                        match_name=match_name,
                        sport="tabletennis",
                        source="1xbet",
                        set_score=set_score,
                        game_score=game_score,
                        point_score=point_score,
                        deep_link=deep_link,
                        timestamp=now,
                        extra_data={
                            "league": league
                        }
                    ))
                    
        except asyncio.TimeoutError:
            self._consecutive_errors += 1
            if self._consecutive_errors >= 3:
                logger.warning("[1xbet] API timeout repetido - renovando sessão...")
                await self.stop()
                await self.start()
        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"[1xbet] Error fetching events: {e}")
            
        return events
