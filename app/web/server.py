import asyncio
import os
import signal
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("web.server")

app = FastAPI(title="Odds Divergence Monitor")

# Get paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web", "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "web", "static")), name="static")

# Shared list of user-monitored custom URLs
USER_MONITORED_LINKS: List[str] = []


class LinkRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=1000)


class RemoveLinkRequest(BaseModel):
    url: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if websocket not in self.active_connections:
                self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        except Exception:
            pass

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return

        async def _safe_send(ws: WebSocket):
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=1.5)
                return None
            except Exception:
                return ws

        # Run concurrent non-blocking sends across all active sockets
        current_conns = list(self.active_connections)
        results = await asyncio.gather(*[_safe_send(ws) for ws in current_conns], return_exceptions=True)
        
        for res in results:
            if isinstance(res, WebSocket):
                self.disconnect(res)


manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})


class ConfigRequest(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class TelegramConfigRequest(BaseModel):
    token: str = Field(..., max_length=200)
    chat_id: str = Field(..., max_length=100)


class ScrapersConfigRequest(BaseModel):
    enable_bet365: bool
    enable_betburger: bool
    enable_betano: bool
    freeze_threshold_seconds: float = Field(default=5.0, ge=1.0, le=60.0)


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


def _sync_set_env_keys(env_path: str, updates: dict):
    from dotenv import set_key
    if not os.path.exists(env_path):
        open(env_path, "a", encoding="utf-8").close()
    for k, v in updates.items():
        set_key(env_path, k, str(v))


@app.post("/api/config/scrapers")
async def save_scrapers_config(payload: ScrapersConfigRequest):
    try:
        env_path = os.path.join(BASE_DIR, ".env")
        updates = {
            "ENABLE_BET365": payload.enable_bet365,
            "ENABLE_BETBURGER": payload.enable_betburger,
            "ENABLE_BETANO": payload.enable_betano,
            "FREEZE_THRESHOLD_SECONDS": payload.freeze_threshold_seconds,
        }
        await asyncio.to_thread(_sync_set_env_keys, env_path, updates)
        
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
        logger.error(f"Erro ao salvar scrapers config: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/config")
async def save_config(payload: ConfigRequest):
    try:
        env_path = os.path.join(BASE_DIR, ".env")
        updates = {"BETBURGER_EMAIL": payload.email}
        if payload.password and payload.password != "********":
            updates["BETBURGER_PASSWORD"] = payload.password

        await asyncio.to_thread(_sync_set_env_keys, env_path, updates)
            
        from config import settings
        settings.BETBURGER_EMAIL = payload.email
        if payload.password and payload.password != "********":
            settings.BETBURGER_PASSWORD = payload.password
            
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao salvar config: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/config/telegram")
async def save_telegram_config(payload: TelegramConfigRequest):
    try:
        env_path = os.path.join(BASE_DIR, ".env")
        updates = {"TELEGRAM_CHAT_ID": payload.chat_id}
        if payload.token and payload.token != "********":
            updates["TELEGRAM_BOT_TOKEN"] = payload.token

        await asyncio.to_thread(_sync_set_env_keys, env_path, updates)

        from config import settings
        if payload.token and payload.token != "********":
            settings.TELEGRAM_BOT_TOKEN = payload.token
        settings.TELEGRAM_CHAT_ID = payload.chat_id
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao salvar telegram config: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/config/telegram")
async def get_telegram_config():
    from config import settings
    return {
        "status": "ok",
        "chat_id": settings.TELEGRAM_CHAT_ID or "",
        "token": settings.TELEGRAM_BOT_TOKEN or ""
    }


@app.get("/api/config")
async def get_general_config():
    from config import settings
    return {
        "status": "ok",
        "email": settings.BETBURGER_EMAIL or "",
        "password_set": bool(settings.BETBURGER_PASSWORD)
    }


@app.get("/api/status")
async def get_system_status():
    try:
        from main import state_cache, detector
        by_source = {}
        for m_id, sources in state_cache._cache.items():
            for src_name in sources.keys():
                by_source[src_name] = by_source.get(src_name, 0) + 1
        
        divergences = detector.check_divergences()
        return {
            "status": "ok",
            "total_matches": len(state_cache._cache),
            "by_source": by_source,
            "active_divergences": len(divergences),
            "divergences": divergences
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


class OpenBet365Request(BaseModel):
    match_name: str
    match_id: str = ""


@app.post("/api/open-bet365")
async def open_bet365_match(payload: OpenBet365Request):
    """
    Open the correct Bet365 fixture in the scraper Chrome window.
    """
    try:
        from main import bet365_scraper, state_cache
        name = (payload.match_name or "").strip()
        if payload.match_id:
            ev = state_cache.get_event(payload.match_id, "bet365")
            if ev and ev.match_name:
                name = ev.match_name
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
        from main import get_current_ui_snapshot
        snapshot = get_current_ui_snapshot()
        if snapshot:
            await websocket.send_json(snapshot)
    except Exception as e:
        logger.debug(f"[WS] Erro ao enviar snapshot inicial: {e}")

    try:
        while True:
            # Keep-alive loop
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect(websocket)


@app.post("/shutdown")
async def shutdown_endpoint(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "localhost", "::1"):
        return JSONResponse(status_code=403, content={"error": "Acesso não autorizado"})

    logger.info("Recebido pedido de encerramento do backend via HTTP API localhost")
    
    async def self_terminate():
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
        
    asyncio.create_task(self_terminate())
    return {"status": "shutting_down"}
