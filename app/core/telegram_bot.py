import httpx
import logging
from config import settings

logger = logging.getLogger("telegram_bot")

# Persistent HTTP client with keep-alive connection pool for minimum latency
_http_client: httpx.AsyncClient = None

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        _http_client = httpx.AsyncClient(timeout=4.0, limits=limits, http2=True)
    return _http_client

async def send_telegram_alert(message: str, url_button: str = None):
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    if url_button:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "⚡ ABRIR BET365 AGORA ⚡", "url": url_button}]
            ]
        }
    
    try:
        client = get_http_client()
        response = await client.post(api_url, json=payload)
        if response.status_code != 200:
            logger.error(f"Erro ao enviar Telegram: {response.text}")
        else:
            logger.info("⚡ [TELEGRAM] Alerta entregue com ultra-baixa latência!")
    except Exception as e:
        logger.error(f"Exceção ao enviar notificação Telegram: {e}")

