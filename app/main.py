"""
Odds Divergence Detector — Main Application
Real-time comparison of Bet365, Betano, 1xBet, BetBurger and Novibet live events.
Zero mock data. Everything is real.
"""
import sys
import asyncio
import atexit
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any, List
import uvicorn
from config import settings

# ── Logging ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("main")

# ── Shared Singleton Instances ──
from core.instances import (
    state_cache,
    detector,
    bet365_scraper,
    onexbet_scraper,
    betburger_scraper,
    betano_scraper,
    novibet_scraper,
)

_poller_task = None


def _emergency_kill_chrome():
    """Last-resort cleanup: kill any Chrome processes on all scraper debug ports."""
    for port in [9222, 9223, 9224, 9226]:
        try:
            subprocess.run(
                f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{port}\') do taskkill /PID %a /T /F',
                shell=True, capture_output=True, timeout=3
            )
        except Exception:
            pass


# Register emergency cleanup on interpreter exit
atexit.register(_emergency_kill_chrome)

# ── Real-time Counts ──
_last_b365_count = 0
_last_burger_count = 0
_last_xbet_count = 0
_last_betano_count = 0
_last_novibet_count = 0


# ── State Serialization Helper ──

def build_active_matches_payload() -> List[Dict[str, Any]]:
    """Build standardized UI match list from state_cache."""
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
        novibet_link = ""
        
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
        has_other = (
            ("1xbet" in sources_data)
            or ("betburger" in sources_data)
            or ("betano" in sources_data)
            or ("novibet" in sources_data)
        )
        if settings.ENABLE_BET365 and not has_b365:
            continue
        if not has_other and len(sources_data) < 2:
            continue

        # Fallback for bet365 link if available from betburger
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
            "novibet_link": novibet_link,
        })
        
    return active_matches


def get_current_ui_snapshot() -> Dict[str, Any]:
    """Returns instant snapshot payload for new WebSocket connections."""
    matches = build_active_matches_payload()
    return {
        "type": "update",
        "matches": matches,
        "stats": {
            "bet365_count": _last_b365_count,
            "betburger_count": _last_burger_count,
            "xbet_count": _last_xbet_count,
            "betano_count": _last_betano_count,
            "novibet_count": _last_novibet_count,
            "total_monitored": len(matches),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    }


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
                
                if events:
                    current_ids = set()
                    for ev in events:
                        state_cache.update(ev)
                        current_ids.add(ev.match_id)
                    state_cache.purge_source_missing("bet365", current_ids)
            else:
                _last_b365_count = 0
        except Exception as e:
            logger.error(f"[Loop] Bet365 scraper loop error: {e}")
        
        await asyncio.sleep(0.8)


async def onexbet_loop():
    """Background task for 1xBet scraping."""
    global _last_xbet_count
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
                _last_xbet_count = len(events)
                
                if events:
                    current_ids = set()
                    for ev in events:
                        state_cache.update(ev)
                        current_ids.add(ev.match_id)
                    state_cache.purge_source_missing("1xbet", current_ids)
            else:
                _last_xbet_count = 0
        except Exception as e:
            logger.error(f"[Loop] 1xBet scraper loop error: {e}")
        
        await asyncio.sleep(1.0)


async def betburger_loop():
    """Background task for BetBurger scraping."""
    global _last_burger_count
    logger.info("[Loop] BetBurger scraper loop started")
    
    await asyncio.sleep(4)
    _burger_started = False
    
    while True:
        try:
            if settings.ENABLE_BETBURGER and settings.BETBURGER_EMAIL:
                if not _burger_started:
                    logger.info("⏳ Iniciando BetBurger (deferred)...")
                    await asyncio.wait_for(betburger_scraper.start(), timeout=45)
                    _burger_started = True
                    logger.info("✅ BetBurger iniciado com sucesso")
                
                events = await betburger_scraper.fetch_live_events()
                events = [e for e in events if e.sport == "tabletennis"]
                _last_burger_count = len(events)
                if events:
                    current_ids = set()
                    for ev in events:
                        state_cache.update(ev)
                        current_ids.add(ev.match_id)
                    state_cache.purge_source_missing("betburger", current_ids)
            else:
                _last_burger_count = 0
        except Exception as e:
            logger.error(f"[Loop] BetBurger scraper loop error: {e}")
            _burger_started = False
            await asyncio.sleep(5)
        
        await asyncio.sleep(1.5)


async def betano_loop():
    """Background task for Betano scraping."""
    global _last_betano_count
    logger.info("[Loop] Betano scraper loop started")
    
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
                
                if events:
                    current_ids = set()
                    for ev in events:
                        state_cache.update(ev)
                        current_ids.add(ev.match_id)
                    state_cache.purge_source_missing("betano", current_ids)
            else:
                _last_betano_count = 0
        except Exception as e:
            logger.error(f"[Loop] Betano scraper loop error: {e}")
        
        await asyncio.sleep(2.0)


async def novibet_loop():
    """Background task for Novibet scraping."""
    global _last_novibet_count
    logger.info("[Loop] Novibet scraper loop started")
    
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
                
                if events:
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
    from core.telegram_bot import send_telegram_alert
    
    logger.info("=" * 60)
    logger.info("🚀 Real-time Broadcast & Detector Loop STARTED")
    logger.info("=" * 60)
    
    while True:
        try:
            # Clear expired events (> 120s)
            state_cache.clear_stale(max_age_seconds=120)
            
            # Reconstruct UI active matches
            active_matches = build_active_matches_payload()
            
            # Broadcast matches and stats to WebSocket
            await manager.broadcast({
                "type": "update",
                "matches": active_matches,
                "stats": {
                    "bet365_count": _last_b365_count,
                    "betburger_count": _last_burger_count,
                    "xbet_count": _last_xbet_count,
                    "betano_count": _last_betano_count,
                    "novibet_count": _last_novibet_count,
                    "total_monitored": len(active_matches),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }
            })

            # Check for divergences
            raw_alerts = detector.check_divergences()
            verified_alerts = []
            
            for alert in raw_alerts:
                if alert.get("needs_deep_verification"):
                    asyncio.create_task(_run_deep_verification(alert))
                if alert.get("deep_verified") is True:
                    verified_alerts.append(alert)

            # Broadcast ONLY 100% verified alerts to frontend
            await manager.broadcast({
                "type": "alerts",
                "alerts": verified_alerts
            })

            # Dispatch telegram alerts
            if verified_alerts:
                for alert in verified_alerts:
                    if alert.get("notify"):
                        await format_and_send_telegram(alert)

        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}", exc_info=True)
            
        await asyncio.sleep(1.0)


async def _run_deep_verification(alert: dict):
    """
    Camada de Verificação Profunda:
    Ao atingir os 10s de travamento, abre uma nova página/aba no bot da Bet365
    para acessar diretamente os detalhes da partida e confirmar se o placar interno ainda está travado
    ANTES de enviar o alerta final para o Telegram e emitir áudio.
    """
    match_id = alert.get("match_id")
    b365_url = alert.get("bet365_link") or "https://www.bet365.bet.br/#/IP/B92"
    if not match_id or not getattr(bet365_scraper, "context", None):
        return

    b365_ev = state_cache.get_event(match_id, "bet365")
    burger_ev = state_cache.get_event(match_id, "betburger")
    if not b365_ev or not burger_ev:
        return

    delay_sec = alert.get("delay_seconds", 10.0)
    logger.info(f"🔍 [DEEP VERIFIER] Validando placar real para {alert['match_name']} ({delay_sec:.1f}s)...")

    from web.server import manager

    try:
        is_still_frozen = await bet365_scraper.verify_match_deep(b365_url, b365_ev, burger_ev)
        ev = detector.tracker._active_events.get(match_id)
        if not is_still_frozen:
            logger.info(f"❌ [DEEP VERIFIER] Falso positivo descartado pela nova página! Placar já atualizou. Cancelando alerta de {alert['match_name']}.")
            detector.tracker._active_events.pop(match_id, None)
            await manager.broadcast({
                "type": "alerts",
                "alerts": [a for a in detector.check_divergences() if a.get("match_id") != match_id]
            })
        else:
            logger.info(f"🎯 [DEEP VERIFIER] Travamento 100% REAL CONFIRMADO via página dedicada: {alert['match_name']} ({delay_sec:.1f}s)! Disparando alertas.")
            if ev:
                ev.deep_verified = True
                ev.deep_verification_pending = False
                from core.divergence_detector import EventStatus
                ev.status = EventStatus.ALERTA
                ev.alert_sent = True
                ev.last_notified_delay = delay_sec
                ev.alert_timestamp = datetime.now().strftime("%H:%M:%S")

            from core.native_sound import trigger_native_audio
            trigger_native_audio(alert.get("priority", "CRITICAL"))
            alert["deep_verified"] = True
            await format_and_send_telegram(alert)

            await manager.broadcast({
                "type": "alerts",
                "alerts": detector.check_divergences()
            })
    except Exception as e:
        logger.warning(f"[DEEP VERIFIER] Erro ao abrir nova página de verificação: {e}")


async def format_and_send_telegram(alert: dict):
    """Formats and dispatches full multi-house divergence alert to Telegram."""
    from core.telegram_bot import send_telegram_alert
    try:
        m_name = alert['match_name'].replace(" vs ", " x ").replace(" VS ", " x ")
        title = (
            "🔄 ATUALIZAÇÃO DA DIVERGÊNCIA"
            if alert.get("is_update")
            else "🚨 NOVA DIVERGÊNCIA DETECTADA"
        )
        league = (alert.get("league") or "").strip()
        league_line = f"🏆 <b>{league}</b>\n" if league else ""
        leading = alert.get("leading_houses") or []
        leading_line = (
            f"\n🔺 À frente da casa alvo: {', '.join(leading)}"
            if leading else ""
        )
        delay_sec = alert.get("delay_seconds", 10.0)
        delay_tag = f" <b>(travado há {delay_sec:.1f}s)</b>" if delay_sec else ""

        msg_scores = [
            f"🎯 <b>Bet365 (Alvo)</b>: {alert.get('bet365_score', 'não encontrado')}{delay_tag}",
            f"🍔 <b>BetBurger</b>: {alert.get('betburger_score', 'não encontrado')}",
            f"⚡ <b>1xBet</b>: {alert.get('xbet_score', 'não encontrado')}",
            f"🟠 <b>Betano</b>: {alert.get('betano_score', 'não encontrado')}",
        ]
        if alert.get("novibet_score") and alert.get("novibet_score") != "não encontrado":
            msg_scores.append(f"🔵 <b>Novibet</b>: {alert.get('novibet_score')}")

        delay_line = f"⏱️ <b>Tempo de Atraso na Bet365</b>: <b>{delay_sec:.1f}s</b>\n"

        msg = (
            f"{title}\n"
            f"🎯 <b>ENTRADA PARA BET365</b>\n"
            f"{delay_line}"
            f"{league_line}"
            f"🏓 <b>{m_name}</b>\n\n"
            + "\n".join(msg_scores)
            + f"{leading_line}"
        )
        b365_btn_link = alert.get('bet365_link') or "https://www.bet365.bet.br/#/IP/B92"
        if alert.get('bet365_link'):
            msg += f"\n\n🔗 <a href='{alert['bet365_link']}'>Acessar Bet365</a>"

        await send_telegram_alert(msg, url_button=b365_btn_link)
    except Exception as tg_err:
        logger.error(f"Erro ao enviar para o Telegram: {tg_err}")


# ── Global Task References for Lifecycle ──
_b365_task = None
_onex_task = None
_bb_task = None
_betano_task = None
_novibet_task = None
_broadcast_task = None


# ── Import the FastAPI app from server ──
from web.server import app


# ── Windows Kernel 1.0ms Timer Resolution ──
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
        logger.info("⚡ Windows kernel timer resolution configured to 1.0ms")
    except Exception:
        pass


def on_score_changed_reactive(match_id: str, source: str, event, old_ev):
    """
    Ultra-low latency reactive callback (< 50µs):
    Triggers immediate divergence evaluation on the affected match without waiting for the 1s loop.
    """
    from web.server import manager
    alerts = detector.evaluate_match_reactive(match_id)
    if alerts:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.broadcast({
                "type": "alerts",
                "alerts": alerts
            }))
            for a in alerts:
                if a.get("notify"):
                    loop.create_task(format_and_send_telegram(a))
        except RuntimeError:
            pass


# Register reactive callback directly on StateCache ingestion
state_cache.register_score_listener(on_score_changed_reactive)


# ── Lifespan events ──
@app.on_event("startup")
async def startup():
    global _b365_task, _onex_task, _bb_task, _betano_task, _novibet_task, _broadcast_task
    logger.info("🌐 Web server starting in Reactive Event-Driven mode...")
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
    uvicorn.run(app, host=settings.HOST, port=settings.PORT, reload=False)
