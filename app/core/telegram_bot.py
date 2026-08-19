import asyncio
import time
import httpx
import logging
from typing import Optional, Dict, Any
from config import settings

logger = logging.getLogger("telegram_bot")

# Persistent HTTP client with keep-alive connection pool
_http_client: Optional[httpx.AsyncClient] = None
_alert_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_last_sent_time: float = 0.0
_min_interval_seconds: float = 1.0  # Telegram limit: ~1 msg/sec per chat

def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        _http_client = httpx.AsyncClient(timeout=6.0, limits=limits)
    return _http_client


async def _telegram_worker():
    """Worker task that processes telegram messages sequentially with strict rate limiting."""
    global _last_sent_time
    logger.info("[Telegram] Rate-limited dispatch worker active")
    
    while True:
        try:
            item = await _alert_queue.get()
            if item is None:
                _alert_queue.task_done()
                break

            token, chat_id, message, url_button = item
            
            # Enforce rate limit (minimum 1.0s between messages)
            elapsed = time.time() - _last_sent_time
            if elapsed < _min_interval_seconds:
                await asyncio.sleep(_min_interval_seconds - elapsed)

            api_url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload: Dict[str, Any] = {
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

            client = get_http_client()
            try:
                response = await client.post(api_url, json=payload)
                _last_sent_time = time.time()
                
                if response.status_code == 200:
                    logger.info("⚡ [TELEGRAM] Alerta entregue com sucesso!")
                elif response.status_code == 429:
                    retry_after = 2.0
                    try:
                        resp_json = response.json()
                        retry_after = resp_json.get("parameters", {}).get("retry_after", 2.0)
                    except Exception:
                        pass
                    logger.warning(f"[Telegram] Rate limit 429. Aguardando {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    # Re-enqueue item at top of queue
                    await client.post(api_url, json=payload)
                else:
                    logger.error(f"[Telegram] Erro na API Telegram ({response.status_code}): {response.text}")
            except Exception as req_err:
                logger.error(f"[Telegram] Exceção ao enviar notificação: {req_err}")

            _alert_queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Telegram] Erro no worker: {e}")
            await asyncio.sleep(0.5)


def _ensure_worker():
    global _alert_queue, _worker_task
    if _alert_queue is None:
        _alert_queue = asyncio.Queue(maxsize=100)
    if _worker_task is None or _worker_task.done():
        try:
            loop = asyncio.get_running_loop()
            _worker_task = loop.create_task(_telegram_worker())
        except RuntimeError:
            pass


async def send_telegram_alert(message: str, url_button: Optional[str] = None):
    import os
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or settings.TELEGRAM_BOT_TOKEN or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or settings.TELEGRAM_CHAT_ID or "").strip()
    if not token or not chat_id:
        logger.debug("[Telegram] Token ou Chat ID ausente, ignorando envio")
        return

    _ensure_worker()
    if _alert_queue is not None:
        try:
            _alert_queue.put_nowait((token, chat_id, message, url_button))
            logger.info(f"📨 [Telegram] Alerta enfileirado para entrega -> Chat ID: {chat_id}")
        except asyncio.QueueFull:
            logger.warning("[Telegram] Fila de alertas cheia, descartando mensagem mais antiga")
            try:
                _alert_queue.get_nowait()
                _alert_queue.task_done()
                _alert_queue.put_nowait((token, chat_id, message, url_button))
            except Exception:
                pass
                _alert_queue.put_nowait((token, chat_id, message, url_button))
            except Exception:
                pass
