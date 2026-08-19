"""
Odds Divergence Detector — Main Application
Real-time comparison of Bet365 and BetBurger live events using Playwright scrapers.
Zero mock data. Everything is real.
"""
import sys
print(f"[DEBUG_SYS] Python Executable: {sys.executable}")
print(f"[DEBUG_SYS] Python Version: {sys.version}")
print(f"[DEBUG_SYS] Python Path: {sys.path}")
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
from sources.betano_scraper import BetanoScraper
from sources.novibet_scraper import NovibetScraper
from sources.onexbet_scraper import OneXBetScraper


# ── Core Components ──
state_cache = StateCache(match_threshold=0.72)
detector = DivergenceDetector(
    state_cache=state_cache,
    freeze_threshold_seconds=settings.FREEZE_THRESHOLD_SECONDS,
    min_game_difference=settings.MIN_GAME_DIFFERENCE
)

# ── Real Scrapers (NO MOCKS) ──
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

_poller_task = None



def _emergency_kill_chrome():
    """Last-resort cleanup: kill any Chrome processes on scraper debug ports."""
    for port in [9222, 9223, 9226]:
        try:
            subprocess.run(
                f'for /f "tokens=5" %a in ("netstat -ano | findstr :{port}") do taskkill /PID %a /T /F',
                shell=True, capture_output=True, timeout=3
            )
        except Exception:
            pass



# Register emergency cleanup on interpreter exit (catches SIGTERM/force-kill)
atexit.register(_emergency_kill_chrome)

# ── Real-time Counts ──
_last_b365_count = 0
_last_burger_count = 0
_last_betano_count = 0
_last_novibet_count = 0


# ── Background Task Loops ──

async def bet365_loop():
    """Background task for Bet365 scraping."""
    global _last_b365_count
    logger.info("[Loop] Bet365 scraper loop started")
    try:
        await bet365_scraper.start()
    except Exception as e:
        logger.error(f"[Loop] Erro ao iniciar Bet365: {e}")

    while True:
        try:
            if settings.ENABLE_BET365:
                events = await bet365_scraper.fetch_live_events()
                events = [e for e in events if e.sport == "tabletennis"]
                _last_b365_count = len(events)
                
                # Update Cache
                current_ids = set()
                for ev in events:
                    state_cache.update(ev)
                    current_ids.add(ev.match_id)
                state_cache.purge_source_missing("bet365", current_ids)
            else:
                _last_b365_count = 0
        except Exception as e:
            logger.error(f"[Loop] Bet365 scraper loop error: {e}")
        
        await asyncio.sleep(max(1, settings.POLLING_INTERVAL_SECONDS))


async def onexbet_loop():
    """Background task for 1xBet scraping."""
    global _last_burger_count
    logger.info("[Loop] 1xBet scraper loop started")
    try:
        await onexbet_scraper.start()
    except Exception as e:
        logger.error(f"[Loop] Erro ao iniciar 1xBet: {e}")

    while True:
        try:
            if settings.ENABLE_ONEXBET:
                events = await onexbet_scraper.fetch_live_events()
                events = [e for e in events if e.sport == "tabletennis"]
                _last_burger_count = len(events)
                
                if events:
                    logger.info(f"[1xbet] Fetched {len(events)} live TT events")
                
                # Update Cache — IMPORTANT: state_cache.update() may remap
                # ev.match_id via fuzzy matching, so we must collect IDs AFTER update
                current_ids = set()
                for ev in events:
                    state_cache.update(ev)
                    # Use the (possibly remapped) match_id for purge tracking
                    current_ids.add(ev.match_id)
                state_cache.purge_source_missing("1xbet", current_ids)
                
                if events and len(current_ids) > 0:
                    # Log sample of paired matches
                    paired = [mid for mid in current_ids if state_cache.get_event(mid, "bet365")]
                    logger.info(f"[1xbet] {len(paired)}/{len(current_ids)} paired with Bet365")
            else:
                _last_burger_count = 0
        except Exception as e:
            logger.error(f"[Loop] 1xBet scraper loop error: {e}")
        
        await asyncio.sleep(max(1, settings.POLLING_INTERVAL_SECONDS))


async def betburger_loop():
    """Background task for BetBurger scraping (if credentials configured)."""
    global _last_burger_count
    logger.info("[Loop] BetBurger scraper loop started")
    
    # Defer startup to avoid startup race conditions
    await asyncio.sleep(6)
    _burger_started = False
    
    while True:
        try:
            if settings.ENABLE_BETBURGER and settings.BETBURGER_EMAIL:
                if not _burger_started:
                    logger.info("⏳ Iniciando BetBurger (deferred)...")
                    await betburger_scraper.start()
                    _burger_started = True
                    logger.info("✅ BetBurger iniciado")
                
                events = await betburger_scraper.fetch_live_events()
                events = [e for e in events if e.sport == "tabletennis"]
                if events:
                    _last_burger_count = len(events)
                    current_ids = set()
                    for ev in events:
                        state_cache.update(ev)
                        current_ids.add(ev.match_id)
                    state_cache.purge_source_missing("betburger", current_ids)
        except Exception as e:
            logger.error(f"[Loop] BetBurger scraper loop error: {e}")
        
        await asyncio.sleep(max(1, settings.POLLING_INTERVAL_SECONDS))


async def betano_loop():
    """Background task for Betano scraping."""
    global _last_betano_count
    logger.info("[Loop] Betano scraper loop started")
    
    # Defer startup to avoid server crash/overload on startup
    await asyncio.sleep(5)
    
    _betano_started = False
    while True:
        try:
            if settings.ENABLE_BETANO:
                if not _betano_started:
                    logger.info("⏳ Iniciando Betano (deferred, anti-crash)...")
                    await asyncio.wait_for(betano_scraper.start(), timeout=90)
                    _betano_started = True
                    logger.info("✅ Betano iniciado")
                
                events = await betano_scraper.fetch_live_events()
                events = [e for e in events if e.sport == "tabletennis"]
                _last_betano_count = len(events)
                
                # Update Cache
                current_ids = set()
                for ev in events:
                    state_cache.update(ev)
                    current_ids.add(ev.match_id)
                state_cache.purge_source_missing("betano", current_ids)
            else:
                _last_betano_count = 0
        except Exception as e:
            logger.error(f"[Loop] Betano scraper loop error: {e}")
        
        await asyncio.sleep(max(1, settings.POLLING_INTERVAL_SECONDS))


async def novibet_loop():
    """Background task for Novibet scraping."""
    global _last_novibet_count
    logger.info("[Loop] Novibet scraper loop started")
    
    # Defer startup to avoid server crash/overload on startup
    await asyncio.sleep(8)
    
    _novibet_started = False
    while True:
        try:
            if settings.ENABLE_NOVIBET:
                if not _novibet_started:
                    logger.info("⏳ Iniciando Novibet (deferred, anti-crash)...")
                    await asyncio.wait_for(novibet_scraper.start(), timeout=90)
                    _novibet_started = True
                    logger.info("✅ Novibet iniciado")
                
                events = await novibet_scraper.fetch_live_events()
                _last_novibet_count = len(events)
                
                # Update Cache
                current_ids = set()
                for ev in events:
                    state_cache.update(ev)
                    current_ids.add(ev.match_id)
                state_cache.purge_source_missing("novibet", current_ids)
            else:
                _last_novibet_count = 0
        except Exception as e:
            logger.error(f"[Loop] Novibet scraper loop error: {e}")
        
        await asyncio.sleep(max(1, settings.POLLING_INTERVAL_SECONDS))


async def broadcast_loop():

    """Reads state cache, builds UI state, detects divergences and alerts every 1s."""
    from web.server import manager
    
    logger.info("=" * 60)
    logger.info("🚀 Real-time Real-Time Broadcast & Detector Loop STARTED")
    logger.info("=" * 60)
    
    while True:
        try:
            # Clear expired events
            state_cache.clear_stale(max_age_seconds=120)
            
            # Reconstruct UI active matches
            match_ids = state_cache.get_all_active_match_ids()
            active_matches = []
            
            for m_id in match_ids:
                b365_ev = state_cache.get_event(m_id, "bet365")
                xbet_ev = state_cache.get_event(m_id, "1xbet") or state_cache.get_event(m_id, "onexbet")
                burger_ev = state_cache.get_event(m_id, "betburger")
                betano_ev = state_cache.get_event(m_id, "betano")
                novibet_ev = state_cache.get_event(m_id, "novibet")
                
                ref_event = b365_ev or xbet_ev or burger_ev or betano_ev or novibet_ev
                if not ref_event:
                    continue

                sources_data = {}
                bet365_link = ""
                xbet_link = ""
                betburger_link = ""
                betano_link = ""
                
                if b365_ev:
                    sources_data["bet365"] = {
                        "set_score": b365_ev.set_score,
                        "game_score": b365_ev.game_score,
                        "point_score": b365_ev.point_score
                    }
                    bet365_link = b365_ev.deep_link or ""
                
                if xbet_ev:
                    sources_data["1xbet"] = {
                        "set_score": xbet_ev.set_score,
                        "game_score": xbet_ev.game_score,
                        "point_score": xbet_ev.point_score
                    }
                    xbet_link = xbet_ev.deep_link or ""

                if burger_ev:
                    sources_data["betburger"] = {
                        "set_score": burger_ev.set_score,
                        "game_score": burger_ev.game_score,
                        "point_score": burger_ev.point_score
                    }
                    betburger_link = burger_ev.deep_link or ""
                elif xbet_ev:
                    sources_data["betburger"] = sources_data["1xbet"]
                    betburger_link = xbet_link

                if betano_ev:
                    sources_data["betano"] = {
                        "set_score": betano_ev.set_score,
                        "game_score": betano_ev.game_score,
                        "point_score": betano_ev.point_score
                    }
                    betano_link = betano_ev.deep_link or ""

                if novibet_ev:
                    sources_data["novibet"] = {
                        "set_score": novibet_ev.set_score,
                        "game_score": novibet_ev.game_score,
                        "point_score": novibet_ev.point_score
                    }
                    novibet_link = novibet_ev.deep_link or ""

                # Filtering
                has_b365 = "bet365" in sources_data
                has_other = ("1xbet" in sources_data) or ("betburger" in sources_data) or ("betano" in sources_data) or ("novibet" in sources_data)
                if settings.ENABLE_BET365 and not has_b365:
                    continue
                if not has_other:
                    if len(sources_data) < 2:
                        continue

                # Apply Method B fallback for UI link
                if (not bet365_link or "EV" not in bet365_link) and burger_ev:
                    bb_b365_link = burger_ev.extra_data.get("bet365_link")
                    if bb_b365_link:
                        bet365_link = bb_b365_link
                
                active_matches.append({
                    "id": m_id,
                    "name": ref_event.match_name,
                    "sport": ref_event.sport,
                    "sources": sources_data,
                    "bet365_link": bet365_link,
                    "xbet_link": xbet_link,
                    "betburger_link": betburger_link,
                    "betano_link": betano_link,
                    "novibet_link": novibet_link if 'novibet_link' in locals() else "",
                })
            
            # Broadcast matches and stats to WebSocket
            await manager.broadcast({
                "type": "update",
                "matches": active_matches,
                "stats": {
                    "bet365_count": _last_b365_count,
                    "betburger_count": _last_burger_count,
                    "xbet_count": _last_burger_count,
                    "betano_count": _last_betano_count,
                    "novibet_count": _last_novibet_count,
                    "total_monitored": len(active_matches),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }
            })

            
            # Check for divergences
            raw_alerts = detector.check_divergences()
            verified_alerts = []
            needs_reload = False
            
            for alert in raw_alerts:
                freeze_seconds = alert.get("freeze_seconds", 0)
                if alert.get("needs_verification") and freeze_seconds >= 14.0:
                    time_since_reload = (datetime.now() - bet365_scraper._last_reload).total_seconds()
                    if time_since_reload > 20.0:
                        logger.warning(f"Suspected false positive for {alert['match_name']} (freeze {freeze_seconds}s). Suppressing alert and forcing reload.")
                        needs_reload = True
                        continue  # Suppress alert until verified
                        
                verified_alerts.append(alert)

            if needs_reload:
                asyncio.create_task(bet365_scraper.force_hard_reload())

            # Always broadcast alerts (even if empty) to allow frontend to clear resolved ones
            await manager.broadcast({
                "type": "alerts",
                "alerts": verified_alerts
            })
            
            if verified_alerts:
                # Send telegram alerts
                try:
                    from core.telegram_bot import send_telegram_alert
                    for alert in verified_alerts:
                        if not alert.get("notify"):
                            continue
                        m_name = alert['match_name'].replace(" vs ", " x ").replace(" VS ", " x ")
                        title = (
                            "🔄 ATUALIZAÇÃO DA DIVERGÊNCIA"
                            if alert.get("is_update")
                            else "🚨 NOVA DIVERGÊNCIA DETECTADA"
                        )
                        # Sanitize league: strip garbage UI chrome text
                        import re as _re
                        league = (alert.get("league") or "").strip()
                        if league and _re.search(r'(?i)principal|partida|^(game|set|pts|live|aovivo)+$', league.replace(' ', '')):
                            league = ""
                        league_line = f"🏆 <b>{league}</b>\n" if league else ""
                        leading = alert.get("leading_houses") or []
                        # Filter out Novibet from leading houses display
                        leading = [h for h in leading if h.lower() != 'novibet']
                        leading_line = (
                            f"\n🔺 À frente da casa alvo: {', '.join(leading)}"
                            if leading else ""
                        )
                        msg_scores = [
                            f"Bet365 agora: {alert.get('bet365_score', 'não encontrado')}",
                            f"Betano agora: {alert.get('betano_score', 'não encontrado')}",
                            f"1xBet agora: {alert.get('xbet_score', 'não encontrado')}",
                        ]
                        bb_score = alert.get('betburger_score')
                        if bb_score and bb_score != "não encontrado" and bb_score != alert.get('xbet_score'):
                            msg_scores.append(f"BetBurger agora: {bb_score}")

                        msg = (
                            f"{title}\n"
                            f"🎯 <b>ENTRADA PARA BET365</b>\n"
                            f"{league_line}"
                            f"🏓 <b>{m_name}</b>\n\n"
                            + "\n".join(msg_scores)
                            + f"{leading_line}"
                        )
                        b365_btn_link = alert.get('bet365_link') or "https://www.bet365.bet.br/#/IP/B92"
                        if alert.get('bet365_link'):
                            msg += f"\n\n🔗 <a href='{alert['bet365_link']}'>Acessar Bet365</a>"
                        
                        asyncio.create_task(send_telegram_alert(msg, url_button=b365_btn_link))
                except Exception as tg_err:
                    logger.error(f"Erro ao disparar envio para o Telegram: {tg_err}")

        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}", exc_info=True)
            
        await asyncio.sleep(1.0)


# ── Global Task References for Lifecycle ──
_b365_task = None
_onex_task = None
_bb_task = None
_betano_task = None
_novibet_task = None
_broadcast_task = None



# ── Import the FastAPI app from server ──
from web.server import app


# ── Lifespan events ──
@app.on_event("startup")
async def startup():
    global _b365_task, _onex_task, _bb_task, _betano_task, _novibet_task, _broadcast_task
    logger.info("🌐 Web server starting...")
    _b365_task = asyncio.create_task(bet365_loop())
    _onex_task = asyncio.create_task(onexbet_loop())
    _bb_task = asyncio.create_task(betburger_loop())
    _betano_task = asyncio.create_task(betano_loop())
    _novibet_task = asyncio.create_task(novibet_loop())
    _broadcast_task = asyncio.create_task(broadcast_loop())



@app.on_event("shutdown")
async def shutdown():
    global _b365_task, _onex_task, _bb_task, _betano_task, _novibet_task, _broadcast_task
    logger.info("Shutting down background loops...")
    for t in [_b365_task, _onex_task, _bb_task, _betano_task, _novibet_task, _broadcast_task]:
        if t:
            t.cancel()
    await bet365_scraper.stop()
    await onexbet_scraper.stop()
    await betburger_scraper.stop()
    await betano_scraper.stop()
    await novibet_scraper.stop()
    logger.info("✅ Scrapers stopped.")



if __name__ == "__main__":
    # Pass the app object directly (NOT "main:app") to avoid double-importing
    # this module — which would start two poller loops and fight over Chrome ports.
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, reload=False)
