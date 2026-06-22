# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Web server settings
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8000))

# ── Bet365 Settings ──
BET365_BASE_URL = os.getenv("BET365_BASE_URL", "https://www.bet365.bet.br")
BET365_HEADLESS = os.getenv("BET365_HEADLESS", "True").lower() == "true"
# Comma-separated list of sports to monitor
BET365_SPORTS = [s.strip() for s in os.getenv("BET365_SPORTS", 
    "tennis,basketball,tabletennis,volleyball,badminton,icehockey,soccer").split(",")]

# ── BetBurger Settings ──
BETBURGER_EMAIL = os.getenv("BETBURGER_EMAIL", "")
BETBURGER_PASSWORD = os.getenv("BETBURGER_PASSWORD", "")
BETBURGER_HEADLESS = os.getenv("BETBURGER_HEADLESS", "True").lower() == "true"

# ── Detection Thresholds ──
FREEZE_THRESHOLD_SECONDS = float(os.getenv("FREEZE_THRESHOLD_SECONDS", 8.0))
MIN_GAME_DIFFERENCE = int(os.getenv("MIN_GAME_DIFFERENCE", 1))

# ── Polling Settings ──
POLLING_INTERVAL_SECONDS = float(os.getenv("POLLING_INTERVAL_SECONDS", 5.0))

# ── Logging ──
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
