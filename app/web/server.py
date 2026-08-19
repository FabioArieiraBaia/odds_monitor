import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List

from pydantic import BaseModel

app = FastAPI(title="Odds Divergence Monitor")

# Get paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web", "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "web", "static")), name="static")

# Shared list of user-monitored custom URLs
USER_MONITORED_LINKS: List[str] = []


class LinkRequest(BaseModel):
    url: str


class RemoveLinkRequest(BaseModel):
    url: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})

class ConfigRequest(BaseModel):
    email: str
    password: str

class TelegramConfigRequest(BaseModel):
    token: str
    chat_id: str

class ScrapersConfigRequest(BaseModel):
    enable_bet365: bool
    enable_betburger: bool
    enable_betano: bool
    freeze_threshold_seconds: float = 5.0

@app.get("/api/config")
async def get_config():
    from config import settings
    masked_token = "********" if settings.TELEGRAM_BOT_TOKEN else ""
    return {
        "email": settings.BETBURGER_EMAIL,
        "telegram_token": masked_token,
        "telegram_chat_id": settings.TELEGRAM_CHAT_ID,
        "enable_bet365": settings.ENABLE_BET365,
        "enable_betburger": settings.ENABLE_BETBURGER,
        "enable_betano": settings.ENABLE_BETANO,
        "freeze_threshold_seconds": settings.FREEZE_THRESHOLD_SECONDS
    }

@app.post("/api/config/scrapers")
async def save_scrapers_config(payload: ScrapersConfigRequest):
    import os
    try:
        from dotenv import set_key
        env_path = os.path.join(BASE_DIR, ".env")
        if not os.path.exists(env_path):
            open(env_path, "a").close()
            
        set_key(env_path, "ENABLE_BET365", str(payload.enable_bet365))
        set_key(env_path, "ENABLE_BETBURGER", str(payload.enable_betburger))
        set_key(env_path, "ENABLE_BETANO", str(payload.enable_betano))
        set_key(env_path, "FREEZE_THRESHOLD_SECONDS", str(payload.freeze_threshold_seconds))
        
        from config import settings
        settings.ENABLE_BET365 = payload.enable_bet365
        settings.ENABLE_BETBURGER = payload.enable_betburger
        settings.ENABLE_BETANO = payload.enable_betano
        settings.FREEZE_THRESHOLD_SECONDS = payload.freeze_threshold_seconds

        # Keep running detector in sync with UI threshold
        try:
            from main import detector
            detector.freeze_threshold_seconds = float(payload.freeze_threshold_seconds)
        except Exception:
            pass
        
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/config")
async def save_config(payload: ConfigRequest):
    import os
    try:
        from dotenv import set_key
        env_path = os.path.join(BASE_DIR, ".env")
        if not os.path.exists(env_path):
            open(env_path, "a").close() # Create if not exists
            
        set_key(env_path, "BETBURGER_EMAIL", payload.email)
        
        # Only overwrite password if a new one was provided (not the placeholder)
        if payload.password and payload.password != "********":
            set_key(env_path, "BETBURGER_PASSWORD", payload.password)
            
        # Update current runtime settings (though it's best to restart the server)
        from config import settings
        settings.BETBURGER_EMAIL = payload.email
        if payload.password and payload.password != "********":
            settings.BETBURGER_PASSWORD = payload.password
            
        return {"status": "ok"}
    except ImportError:
        # If python-dotenv is not installed with cli/set_key support, we do manual replace
        return {"status": "error", "message": "python-dotenv não suporta escrita. Instale com pip install python-dotenv[cli]"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/config/telegram")
async def save_telegram_config(payload: TelegramConfigRequest):
    import os
    try:
        from dotenv import set_key
        env_path = os.path.join(BASE_DIR, ".env")
        if not os.path.exists(env_path):
            open(env_path, "a").close()
            
        if payload.token and payload.token != "********":
            set_key(env_path, "TELEGRAM_BOT_TOKEN", payload.token)
            from config import settings
            settings.TELEGRAM_BOT_TOKEN = payload.token
            
        set_key(env_path, "TELEGRAM_CHAT_ID", payload.chat_id)
        from config import settings
        settings.TELEGRAM_CHAT_ID = payload.chat_id
        
        return {"status": "ok"}
    except ImportError:
        return {"status": "error", "message": "python-dotenv não suporta escrita. Instale com pip install python-dotenv[cli]"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class OpenBet365Request(BaseModel):
    match_name: str
    match_id: str = ""


@app.post("/api/open-bet365")
async def open_bet365_match(payload: OpenBet365Request):
    """
    Open the correct Bet365 fixture in the scraper Chrome window.
    Needed because live list often has no EV id for external deep links.
    """
    try:
        from main import bet365_scraper, state_cache
        name = (payload.match_name or "").strip()
        # Prefer canonical name from cache
        if payload.match_id:
            ev = state_cache.get_event(payload.match_id, "bet365")
            if ev and ev.match_name:
                name = ev.match_name
            # If we already have a real EV deep link, return it for external open
            if ev and ev.deep_link and "EV" in ev.deep_link.upper():
                return {
                    "status": "ok",
                    "mode": "external",
                    "url": ev.deep_link,
                    "message": "Link direto do evento",
                }
        result = await bet365_scraper.open_match_by_name(name)
        if result.get("ok"):
            return {
                "status": "ok",
                "mode": "scraper_window",
                "message": result.get("message", "Aberto no Chrome Bet365"),
                "url": result.get("url", ""),
            }
        return {
            "status": "error",
            "mode": "scraper_window",
            "message": result.get("error", "Falha ao abrir"),
            "listing_url": result.get("listing_url") or "https://www.bet365.bet.br/#/IP/B92",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/links")
async def get_monitored_links():
    return {"links": USER_MONITORED_LINKS}


@app.post("/add-link")
async def add_monitored_link(payload: LinkRequest):
    url = payload.url.strip()
    if url and url not in USER_MONITORED_LINKS:
        USER_MONITORED_LINKS.append(url)
    return {"status": "ok", "links": USER_MONITORED_LINKS}


@app.post("/remove-link")
async def remove_monitored_link(payload: RemoveLinkRequest):
    url = payload.url.strip()
    if url in USER_MONITORED_LINKS:
        USER_MONITORED_LINKS.remove(url)
    return {"status": "ok", "links": USER_MONITORED_LINKS}


# WebSocket endpoint for real-time frontend updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        from main import state_cache
        from datetime import datetime
        
        match_ids = state_cache.get_all_active_match_ids()
        active_matches = []
        for m_id in match_ids:
            b365_ev = state_cache.get_event(m_id, "bet365")
            burger_ev = state_cache.get_event(m_id, "betburger")
            betano_ev = state_cache.get_event(m_id, "betano")
            
            ref_event = b365_ev or burger_ev or betano_ev
            if not ref_event:
                continue
            
            sources_data = {}
            if b365_ev:
                sources_data["bet365"] = {"set_score": b365_ev.set_score, "game_score": b365_ev.game_score, "point_score": b365_ev.point_score}
            if burger_ev:
                sources_data["betburger"] = {"set_score": burger_ev.set_score, "game_score": burger_ev.game_score, "point_score": burger_ev.point_score, "surebet_percentage": burger_ev.extra_data.get("surebet_percentage", 0.0)}
            if betano_ev:
                sources_data["betano"] = {"set_score": betano_ev.set_score, "game_score": betano_ev.game_score, "point_score": betano_ev.point_score}
                
            active_matches.append({
                "id": m_id,
                "name": ref_event.match_name,
                "sport": ref_event.sport,
                "sources": sources_data,
                "bet365_link": b365_ev.deep_link if b365_ev else "",
                "betburger_link": burger_ev.deep_link if burger_ev else "",
                "betano_link": betano_ev.deep_link if betano_ev else "",
            })
            
        await websocket.send_json({
            "type": "update",
            "matches": active_matches,
            "stats": {
                "bet365_count": len([m for m in active_matches if "bet365" in m["sources"]]),
                "betburger_count": len([m for m in active_matches if "betburger" in m["sources"]]),
                "betano_count": len([m for m in active_matches if "betano" in m["sources"]]),
                "total_monitored": len(active_matches),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
        })
    except Exception:
        pass

    try:
        while True:
            # Keep-alive loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/shutdown")
async def shutdown_endpoint():
    import os
    import signal
    import logging
    log = logging.getLogger("web.server")
    log.info("Recebido pedido de encerramento do backend via HTTP API")
    
    async def self_terminate():
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
        
    asyncio.create_task(self_terminate())
    return {"status": "shutting_down"}

