# 🦅 Phoenix V6.4 — Quantitative Trading Engine

An autonomous, AI-driven algorithmic trading engine built for the **XAUUSD (Gold)** market. Operating on the **M30 timeframe**, the system combines a Random Forest classifier with strict macroeconomic trend filters to execute high-probability swing trades at a **1:4 Risk-to-Reward ratio**.

---

## Table of Contents

- [Core Logic & Indicators](#core-logic--indicators)
- [Risk Management](#risk-management)
- [Emergency Protocols](#emergency-protocols)
- [Environment Setup](#environment-setup)
  - [Phase 1: Prerequisites](#phase-1-prerequisites)
  - [Phase 2: Terminal Configuration](#phase-2-terminal-configuration)
  - [Phase 3: Code Installation](#phase-3-code-installation)
  - [Phase 4: Dual-Terminal Architecture](#phase-4-dual-terminal-architecture)
  - [Phase 5: Execution](#phase-5-execution)

---

## Core Logic & Indicators

| Indicator | Config | Role |
|---|---|---|
| **SMA** | 200-period | Macro trend filter — buys only in uptrend, sells only in downtrend |
| **EMA** | 50-period | Micro trend / dynamic exit — triggers AI Reversal exits on trend break |
| **ADX** | 14-period, threshold `20` | Momentum shield — blocks trades in choppy, low-volume markets |
| **RSI** | 14-period | Sniper execution — hunts dips in trend direction (`< 70` for buys, `> 30` for sells) |

---

## Risk Management

- **Dynamic Position Sizing** — risk is strictly capped at `2.0%` of live account equity per trade.
- **Volatility-Adjusted Stop Loss** — stop distances are calculated as `1.2 × ATR(14)`. As volatility expands, the stop widens and lot size shrinks to maintain the exact 2% cap.
- **Dual-Frequency Heartbeat:**
  - *Hunting State* — evaluates the market every **30 minutes** to preserve CPU.
  - *Guardian State* — shifts to a high-frequency **5-second loop** when a trade is open, actively monitoring for AI Reversal exits.

---

## Emergency Protocols

The bot must be **immediately disconnected** from the live server if any of the following are triggered:

| # | Kill Switch | Condition |
|---|---|---|
| 1 | **The Hard Floor** | Live equity drops below `$200.00 USD` |
| 2 | **The Anomaly** | 6 consecutive full Stop Losses (signals total market regime shift) |
| 3 | **The 20-Trade Audit** | Live Profit Factor drops below `0.80` after 20 live trades |

---

## Environment Setup

> ⚠️ **Windows Only.** The MT5 Python library physically hooks into the trading terminal's memory. This bot must run on a **Windows machine or Windows VPS**.

### Phase 1: Prerequisites

Ensure the following are installed before proceeding:

1. **Windows 10/11** or **Windows Server**
2. **Python 3.9+** — add Python to your Windows PATH during installation
3. **MetaTrader 5 Terminal** — IC Markets recommended for raw spreads
4. **Git for Windows**

---

### Phase 2: Terminal Configuration

The Python engine requires MT5's internal API permissions to be enabled.

1. Open MetaTrader 5.
2. Navigate to **Tools → Options → Expert Advisors** (or press `Ctrl+O`).
3. Check **"Allow automated trading"**.
4. Check **"Allow WebRequest for listed URL"** (required for external news API connections).
5. Click **OK**.

Ensure the terminal is logged into your live or demo account and actively receiving price ticks before proceeding.

---

### Phase 3: Code Installation

Open **PowerShell** or **Command Prompt** and run the following:

**1. Clone the repository:**
```powershell
git clone https://github.com/Chanan57/XAUUSD_TradingBot.git
cd XAUUSD_TradingBot
```

**2. Create a virtual environment:**

> Never install algorithmic trading libraries globally. Always isolate them.
```powershell
python -m venv venv
```

**3. Activate the environment:**
```powershell
venv\Scripts\activate
```
You should see `(venv)` at the start of your terminal prompt.

**4. Install dependencies:**
```powershell
pip install -r requirements.txt
```

---

### Phase 4: Dual-Terminal Architecture

To prevent API collisions between live trading and historical backtesting, a **Dual-Terminal Setup** is strongly recommended.

| Terminal | Path | Purpose |
|---|---|---|
| **Production** | `C:\Program Files\MetaTrader 5` | Runs `main.py`, manages live risk |
| **Sandbox** | `C:\Program Files\MetaTrader 5 - Sandbox` | Logged into a Demo account, used for `Backtest.py` |

> Hardcode the Sandbox path into `Backtest.py` to ensure historical simulations never touch your live account.

---

### Phase 5: Execution

With the MT5 terminal open and the virtual environment active:

**Launch the live hunting engine:**
```powershell
python main.py
```
Verify the console prints:
```
Dual-Frequency Architecture Initialized
```

**Run the visual backtester (Sandbox only):**
```powershell
python Backtest.py
```
This crunches historical data and automatically opens an interactive HTML chart in your browser showing all AI entries and exits.