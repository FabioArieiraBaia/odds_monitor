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

@app.get("/api/config")
async def get_config():
    from config import settings
    return {"email": settings.BETBURGER_EMAIL}

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

