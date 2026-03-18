# 🦅 Phoenix V6.4 - Quantitative Trading Engine

## Architecture Overview
An autonomous, AI-driven algorithmic trading engine built for the XAUUSD (Gold) market. Operating on the M30 timeframe, the system utilizes a Random Forest classifier combined with strict macroeconomic trend filters to execute high-probability swing trades with a 1:4 Risk-to-Reward ratio.

## 🧠 Core Logic & Indicators
* **Macro Trend Filter:** 200 SMA (Simple Moving Average). The bot strictly only buys in a macro uptrend and sells in a macro downtrend.
* **Micro Trend / Dynamic Exit:** 50 EMA (Exponential Moving Average). Used to trigger AI Reversal exits if the trend breaks mid-trade.
* **Momentum Shield:** 14-period ADX (Average Directional Index). Hard-coded `ADX_THRESHOLD = 20`. The bot refuses to trade in low-volume, choppy markets.
* **Sniper Execution:** 14-period RSI (Relative Strength Index). The AI Oracle hunts for localized dips (RSI < 70 for Buys, RSI > 30 for Sells) in the direction of the macro trend.

## 🛡️ Risk Management (The Iron Shield)
* **Dynamic Sizing:** Risk is strictly capped at `2.0%` of live account equity per trade.
* **Volatility Adjustment:** Stop Loss distances are dynamically calculated using `1.2 * ATR(14)`. As market volatility expands, the Stop Loss widens and the lot size automatically shrinks to maintain the exact 2.0% risk cap.
* **Dual-Frequency Heartbeat:** * *Hunting State:* Evaluates the market every 30 minutes to preserve CPU.
  * *Guardian State:* Shifts to a high-frequency 5-second loop when a trade is open to actively monitor for AI Reversal exits.

## 🛑 Emergency Protocols (Kill Switches)
If any of these conditions are met, the bot must be immediately disconnected from the live server:
1. **The Hard Floor:** Live equity drops below the `$200.00 USD` Uncle Point.
2. **The Anomaly:** The system suffers 6 consecutive full Stop Losses (a mathematical anomaly for a 1:4 architecture, signaling a total market regime shift).
3. **The 20-Trade Audit:** Live Profit Factor drops below `0.80` after a full 20-trade live sample size.