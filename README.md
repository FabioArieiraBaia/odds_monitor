<div align="center">

# ⚡ Odds Divergence & Live Score Freeze Monitor
### *Ultra-Low Latency Arbitrage & Bookmaker Delay Detection Engine*

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Playwright CDP](https://img.shields.io/badge/Playwright-CDP%20Sniffer-45ba4b.svg?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev/)
[![Telegram Alerts](https://img.shields.io/badge/Telegram-Instant%20Alerts-2CA5E0.svg?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/FabioArieiraBaia/odds_monitor?style=for-the-badge)](https://github.com/FabioArieiraBaia/odds_monitor/stargazers)

<p align="center">
  <a href="README.md"><b>English</b></a> •
  <a href="README.pt-BR.md"><b>Português (Brasil)</b></a> •
  <a href="README.es.md"><b>Español</b></a>
</p>

</div>

---

## 📌 Overview

**Odds Monitor** is a state-of-the-art, high-frequency live sports arbitrage engine designed to detect **delays, stuck scoreboards, and frozen live odds** on target bookmakers (such as **Bet365**) compared against real-time consensus from reference feeds (**BetBurger, 1xBet, Betano, Novibet**).

Built with **Python 3.11, FastAPI, Playwright CDP Sniffing**, and an ultra-reactive state machine, this system isolates real bookmaker freezes with **zero false positives**, instant sound cues, and millisecond-level Telegram alerts.

---

## 🖼️ Live Dashboard Preview

<div align="center">
  <img src="assets/dashboard_preview.png" alt="Live Odds Monitor Dashboard" width="95%" />
  <p><i>Live Multi-House Table Tennis Monitoring with Real-Time Score Sync & Divergence Cards</i></p>
</div>

<div align="center">
  <img src="assets/divergence_alert.png" alt="Divergence Alert Details" width="70%" />
  <p><i>High-Precision Freeze Alert with Progressive Delay Timer & Direct Bookmaker Links</i></p>
</div>

---

## 🚀 Key Features

* **⚡ Sub-500ms Scraping Loop:** Dedicated scraping engine operating at 500ms with Chrome Anti-Throttling flags (`--disable-background-timer-throttling`, native Windows occlusion bypass, and CDP focus emulation).
* **🧠 Multi-Source Consensus (The Golden Triad):** Requires BetBurger + at least one independent tier-1 sportsbook (1xBet, Betano, Novibet) to agree on points before qualifying a divergence.
* **🛡️ DeepVerifier™ Auto-Scroll Validation:** Eliminates virtual-scrolling hallucinations by actively scrolling the bookmaker's DOM, matching player identity tokens (>= 50%), and verifying the physical scoreboard before firing alerts.
* **🛑 Set-Break & Game Completion Shield:** Mathematically detects set boundaries (e.g. `0:0` vs `1:10`) and match completion states, preventing set-transition false alarms.
* **📲 Instant Telegram Dispatcher:** Async rate-limited push notifications to Telegram with one-click deep links directly to the in-play match.
* **🔊 Native Hardware Audio:** Zero-delay local sound triggers for immediate operator reaction.
* **💻 Cyberpunk Live Dashboard:** Reactive WebSocket UI built with Tailwind CSS, showing live paired matches, delay timers, and dynamic filters.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph DataSources [Live Data Ingestion Feeds]
        B365["Bet365 (Target) - UC + CDP Sniffer (0.5s)"]
        BB["BetBurger (Scout) - CDP Live Feed"]
        BX["1xBet (Scout) - Fast API Poller"]
        BA["Betano (Scout) - Anti-WAF Selenium"]
        BN["Novibet (Scout) - Live Headless Feed"]
    end

    subgraph StateCache [State Cache & Name Normalization]
        Norm[Fuzzy Name Matcher & Inversion Resolver]
        Mem[(In-Memory State Matrix)]
    end

    subgraph CoreEngine [Detection & Precision Verification]
        Triad[Golden Triad Consensus Barrier]
        Timer[Monotonic Kernel Timer >= 20.0s]
        Deep[DeepVerifier™ Auto-Scroll DOM Inspector]
    end

    subgraph Dispatch [Real-Time Notification Layer]
        WS[FastAPI WebSocket Broadcast]
        TG[Telegram Bot Async Worker]
        Audio[Native Audio Core]
    end

    DataSources --> Norm --> Mem --> Triad
    Triad -->|Divergence >= 2 pts & 20s| Deep
    Deep -->|100% Identity & Score Confirmed| Dispatch
    Deep -->|Identity Mismatch / Stale| Mem
```

---

## 🛠️ Quick Start

### 1. Prerequisites
* **Python 3.10+** (Python 3.11 recommended)
* **Google Chrome** (Latest stable version)
* **Git**

### 2. Clone the Repository
```bash
git clone https://github.com/FabioArieiraBaia/odds_monitor.git
cd odds_monitor
```

### 3. Setup Virtual Environment & Dependencies
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

### 4. Configuration (`.env`)
Create a `.env` file in the root directory:
```env
# Server
HOST=127.0.0.1
PORT=8005

# Scrapers
ENABLE_BET365=True
ENABLE_BETBURGER=True
ENABLE_BETANO=True
ENABLE_ONEXBET=True
ENABLE_NOVIBET=False

# Detection Thresholds
FREEZE_THRESHOLD_SECONDS=20.0
MIN_GAME_DIFFERENCE=2

# Telegram Alert Settings
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 5. Launch the Application
```bash
python app/main.py
```
Open your browser at **`http://localhost:8005`** to access the live dashboard!

---

## 🧪 Automated Testing

Run the full unit test suite:
```bash
python -m pytest app/test_pipeline.py -v
```

---

## 🔍 SEO & Keywords

`sports-betting` `arbitrage-betting` `odds-monitor` `bet365-delay` `betburger-scraper` `table-tennis-arbitrage` `live-betting-bot` `surebets` `valuebets` `in-play-trading` `fastapi` `playwright-python` `chrome-devtools-protocol` `sports-arbitrage` `sportsbook-scraper`

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
