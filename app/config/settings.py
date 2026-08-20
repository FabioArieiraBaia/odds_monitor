# settings.py
import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Web server settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8005))

# ── Bet365 Settings ──
BET365_BASE_URL = os.getenv("BET365_BASE_URL", "https://www.bet365.com")
BET365_HEADLESS = os.getenv("BET365_HEADLESS", "True").lower() == "true"
# Comma-separated list of sports to monitor
BET365_SPORTS = [s.strip() for s in os.getenv("BET365_SPORTS", "tabletennis").split(",")]

# ── BetBurger Settings ──
BETBURGER_EMAIL = os.getenv("BETBURGER_EMAIL", "")
BETBURGER_PASSWORD = os.getenv("BETBURGER_PASSWORD", "")
BETBURGER_HEADLESS = os.getenv("BETBURGER_HEADLESS", "True").lower() == "true"

# ── Detection Thresholds ──
FREEZE_THRESHOLD_SECONDS = float(os.getenv("FREEZE_THRESHOLD_SECONDS", 20.0))
MIN_GAME_DIFFERENCE = int(os.getenv("MIN_GAME_DIFFERENCE", 2))

# ── Polling Settings ──
POLLING_INTERVAL_SECONDS = float(os.getenv("POLLING_INTERVAL_SECONDS", 5.0))

# ── Telegram Settings ──
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Scraper Toggles ──
ENABLE_BET365 = os.getenv("ENABLE_BET365", "True").lower() == "true"
ENABLE_BETBURGER = os.getenv("ENABLE_BETBURGER", "True").lower() == "true"
ENABLE_BETANO = os.getenv("ENABLE_BETANO", "True").lower() == "true"
ENABLE_NOVIBET = os.getenv("ENABLE_NOVIBET", "True").lower() == "true"
ENABLE_ONEXBET = os.getenv("ENABLE_ONEXBET", "True").lower() == "true"
NOVIBET_HEADLESS = os.getenv("NOVIBET_HEADLESS", "True").lower() == "true"


# ── Logging ──
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
