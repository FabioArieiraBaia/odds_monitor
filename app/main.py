"""
Odds Divergence Detector — Main Application
Real-time comparison of Bet365 and BetBurger live events using Playwright scrapers.
Zero mock data. Everything is real.
"""
import asyncio
import atexit
import signal
import subprocess
import logging
from contextlib import asynccontextmanager
from datetime import datetime
import uvicorn
from config import settings

# ── Logging ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("main")

# ── Import core components ──
from core.state_cache import StateCache
from core.divergence_detector import DivergenceDetector
from sources.bet365_scraper import Bet365Scraper
from sources.betburger_source import BetBurgerScraper

# ── Core Components ──
state_cache = StateCache()
detector = DivergenceDetector(
    state_cache=state_cache,
    freeze_threshold_seconds=settings.FREEZE_THRESHOLD_SECONDS,
    min_game_difference=999
)

# ── Real Scrapers (NO MOCKS) ──
bet365_scraper = Bet365Scraper(
    headless=settings.BET365_HEADLESS,
    sports=settings.BET365_SPORTS
)

betburger_scraper = BetBurgerScraper(
    email=settings.BETBURGER_EMAIL,
    password=settings.BETBURGER_PASSWORD,
    headless=settings.BETBURGER_HEADLESS
)

_poller_task = None


def _emergency_kill_chrome():
    """Last-resort cleanup: kill any Chrome processes on scraper debug ports."""
    for port in [9222, 9223]:
        try:
            subprocess.run(
                f'for /f "tokens=5" %a in ("netstat -ano | findstr :{port}") do taskkill /PID %a /T /F',
                shell=True, capture_output=True, timeout=3
            )
        except Exception:
            pass


# Register emergency cleanup on interpreter exit (catches SIGTERM/force-kill)
atexit.register(_emergency_kill_chrome)


async def poller_loop():
    """Main background loop: fetch real events, update cache, detect divergences."""
    from web.server import manager
    
    logger.info("=" * 60)
    logger.info("🚀 Odds Divergence Detector STARTED — REAL MODE")
    logger.info(f"   Bet365 sports: {settings.BET365_SPORTS}")
    logger.info(f"   BetBurger login: {'configured' if settings.BETBURGER_EMAIL else 'NOT configured'}")
    logger.info(f"   Freeze threshold: {settings.FREEZE_THRESHOLD_SECONDS}s")
    logger.info(f"   Polling interval: {settings.POLLING_INTERVAL_SECONDS}s")
    logger.info("=" * 60)
    
    await asyncio.sleep(3)  # Warmup — let browsers launch
    
    while True:
        cycle_start = datetime.now()
        
        try:
            # ── Fetch from both sources in parallel ──
            b365_task = bet365_scraper.fetch_live_events()
            burger_task = betburger_scraper.fetch_live_events()
            
            results = await asyncio.gather(b365_task, burger_task, return_exceptions=True)
            
            b365_events = results[0] if not isinstance(results[0], Exception) else []
            burger_events = results[1] if not isinstance(results[1], Exception) else []
            
            if isinstance(results[0], Exception):
                logger.error(f"Bet365 scraper error: {results[0]}")
            if isinstance(results[1], Exception):
                logger.error(f"BetBurger scraper error: {results[1]}")
            
            logger.info(
                f"📊 Cycle: Bet365={len(b365_events)} | "
                f"BetBurger={len(burger_events)} | "
                f"Cache={len(state_cache.get_all_active_match_ids())}"
            )
            
            # ── Update Cache & Evict Missing Matches ──
            b365_ids_in_scrape = set()
            for event in b365_events:
                b365_ids_in_scrape.add(event.match_id)
                state_cache.update(event)
                
            # If the scrape was successful, immediately drop Bet365 matches that are no longer on the page
            if len(b365_events) > 0:
                for match_id in list(state_cache._cache.keys()):
                    if "bet365" in state_cache._cache[match_id] and match_id not in b365_ids_in_scrape:
                        state_cache._cache[match_id].pop("bet365", None)
                        if "bet365" in state_cache._last_changed.get(match_id, {}):
                            state_cache._last_changed[match_id].pop("bet365", None)
            
            for event in burger_events:
                state_cache.update(event)

            # ── Clean stale entries (BetBurger) ──
            state_cache.clear_stale(max_age_seconds=60.0)

            # ── Build update packet for UI ──
            active_matches = []
            match_ids = state_cache.get_all_active_match_ids()
            
            for m_id in match_ids:
                b365_ev = state_cache.get_event(m_id, "bet365")
                burger_ev = state_cache.get_event(m_id, "betburger")
                
                ref_event = b365_ev or burger_ev
                if not ref_event:
                    continue
                
                sources_data = {}
                bet365_link = ""
                betburger_link = ""
                
                if b365_ev:
                    sources_data["bet365"] = {
                        "set_score": b365_ev.set_score,
                        "game_score": b365_ev.game_score,
                        "point_score": b365_ev.point_score
                    }
                    bet365_link = b365_ev.deep_link or ""
                
                if burger_ev:
                    sources_data["betburger"] = {
                        "set_score": burger_ev.set_score,
                        "game_score": burger_ev.game_score,
                        "point_score": burger_ev.point_score,
                        "surebet_percentage": burger_ev.extra_data.get("surebet_percentage", 0.0)
                    }
                    betburger_link = burger_ev.deep_link or ""
                
                active_matches.append({
                    "id": m_id,
                    "name": ref_event.match_name,
                    "sport": ref_event.sport,
                    "sources": sources_data,
                    "bet365_link": bet365_link,
                    "betburger_link": betburger_link,
                })

            # ── Broadcast to WebSocket clients ──
            await manager.broadcast({
                "type": "update",
                "matches": active_matches,
                "stats": {
                    "bet365_count": len(b365_events),
                    "betburger_count": len(burger_events),
                    "total_monitored": len(match_ids),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }
            })

            # ── Check for divergences & verify them ──
            raw_alerts = detector.check_divergences()
            verified_alerts = []
            needs_reload = False
            
            for alert in raw_alerts:
                # If Bet365 seems frozen, verify it's not a false positive before alerting
                freeze_seconds = alert.get("freeze_seconds", 0)
                if alert.get("needs_verification") and freeze_seconds >= 14.0:
                    time_since_reload = (datetime.now() - bet365_scraper._last_reload).total_seconds()
                    if time_since_reload > 20.0:
                        logger.warning(f"Suspected false positive for {alert['match_name']} (freeze {freeze_seconds}s). Suppressing alert and forcing reload.")
                        needs_reload = True
                        continue  # Suppress alert until verified
                        
                verified_alerts.append(alert)

            if needs_reload:
                # Fire and forget a hard reload
                asyncio.create_task(bet365_scraper.force_hard_reload())

            # Always broadcast alerts (even if empty) to allow frontend to clear resolved ones
            await manager.broadcast({
                "type": "alerts",
                "alerts": verified_alerts
            })
            if verified_alerts:
                logger.warning(f"🚨 {len(verified_alerts)} real divergence(s) detected and broadcasted!")

        except Exception as e:
            logger.error(f"Error in poller loop: {e}", exc_info=True)
        
        # ── Pace the loop ──
        elapsed = (datetime.now() - cycle_start).total_seconds()
        sleep_time = max(1, settings.POLLING_INTERVAL_SECONDS - elapsed)
        await asyncio.sleep(sleep_time)


# ── Import the FastAPI app from server ──
from web.server import app


# ── Lifespan events (using deprecated on_event for compatibility with existing app) ──
@app.on_event("startup")
async def startup():
    global _poller_task
    logger.info("🌐 Web server starting...")
    _poller_task = asyncio.create_task(poller_loop())


@app.on_event("shutdown")
async def shutdown():
    global _poller_task
    logger.info("Shutting down scrapers...")
    if _poller_task:
        _poller_task.cancel()
    await bet365_scraper.stop()
    await betburger_scraper.stop()
    logger.info("✅ Scrapers stopped.")


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
