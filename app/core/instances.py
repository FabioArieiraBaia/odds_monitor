# app/core/instances.py
import logging
from config import settings
from core.state_cache import StateCache
from core.divergence_detector import DivergenceDetector
from sources.bet365_scraper import Bet365Scraper
from sources.betburger_source import BetBurgerScraper
from sources.betano_scraper import BetanoScraper
from sources.novibet_scraper import NovibetScraper
from sources.onexbet_scraper import OneXBetScraper

logger = logging.getLogger("instances")

state_cache = StateCache(match_threshold=0.72)
detector = DivergenceDetector(
    state_cache=state_cache,
    freeze_threshold_seconds=settings.FREEZE_THRESHOLD_SECONDS,
    min_game_difference=settings.MIN_GAME_DIFFERENCE
)

bet365_scraper = Bet365Scraper(
    headless=settings.BET365_HEADLESS,
    sports=settings.BET365_SPORTS
)

onexbet_scraper = OneXBetScraper()

betburger_scraper = BetBurgerScraper(
    email=settings.BETBURGER_EMAIL,
    password=settings.BETBURGER_PASSWORD,
    headless=settings.BETBURGER_HEADLESS
)

betano_scraper = BetanoScraper(
    headless=settings.BET365_HEADLESS,
    sports=settings.BET365_SPORTS
)

novibet_scraper = NovibetScraper(
    headless=settings.NOVIBET_HEADLESS
)
