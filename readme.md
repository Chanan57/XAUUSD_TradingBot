🦅 Phoenix V6.4 - Quantitative Trading Engine
Architecture Overview
An autonomous, AI-driven algorithmic trading engine built for the XAUUSD (Gold) market. Operating on the M30 timeframe, the system utilizes a Random Forest classifier combined with strict macroeconomic trend filters to execute high-probability swing trades with a 1:4 Risk-to-Reward ratio.

🧠 Core Logic & Indicators
Macro Trend Filter: 200 SMA (Simple Moving Average). The bot strictly only buys in a macro uptrend and sells in a macro downtrend.

Micro Trend / Dynamic Exit: 50 EMA (Exponential Moving Average). Used to trigger AI Reversal exits if the trend breaks mid-trade.

Momentum Shield: 14-period ADX (Average Directional Index). Hard-coded ADX_THRESHOLD = 20. The bot refuses to trade in low-volume, choppy markets.

Sniper Execution: 14-period RSI (Relative Strength Index). The AI Oracle hunts for localized dips (RSI < 70 for Buys, RSI > 30 for Sells) in the direction of the macro trend.

🛡️ Risk Management (The Iron Shield)
Dynamic Sizing: Risk is strictly capped at 2.0% of live account equity per trade.

Volatility Adjustment: Stop Loss distances are dynamically calculated using 1.2 * ATR(14). As market volatility expands, the Stop Loss widens and the lot size automatically shrinks to maintain the exact 2.0% risk cap.

Dual-Frequency Heartbeat: * Hunting State: Evaluates the market every 30 minutes to preserve CPU.

Guardian State: Shifts to a high-frequency 5-second loop when a trade is open to actively monitor for AI Reversal exits.

🛑 Emergency Protocols (Kill Switches)
If any of these conditions are met, the bot must be immediately disconnected from the live server:

The Hard Floor: Live equity drops below the $200.00 USD Uncle Point.

The Anomaly: The system suffers 6 consecutive full Stop Losses (a mathematical anomaly for a 1:4 architecture, signaling a total market regime shift).

The 20-Trade Audit: Live Profit Factor drops below 0.80 after a full 20-trade live sample size.

⚙️ Environment Setup & Installation Guide
This quantitative trading engine relies on the official MetaTrader 5 Python integration. Because the MT5 library physically hooks into the trading terminal's memory, this bot must be run on a Windows machine or a Windows VPS.

Phase 1: Prerequisites
Before cloning the engine, ensure your system has the following installed:

Windows 10/11 or Windows Server (Required for MT5).

Python 3.9+ (Ensure Python is added to your Windows PATH during installation).

MetaTrader 5 Terminal (IC Markets recommended for raw spreads).

Git for Windows.

Phase 2: Terminal Configuration
The Python engine cannot communicate with MT5 unless the terminal's internal firewalls are lowered.

Open your MetaTrader 5 terminal.

Navigate to Tools > Options > Expert Advisors (or press Ctrl+O).

Check the box for "Allow automated trading".

Check the box for "Allow WebRequest for listed URL" (if connecting to external news APIs).

Click OK. Ensure your terminal is logged into your live or demo account and actively receiving price ticks.

Phase 3: The Code Installation
Open your PowerShell or Command Prompt and run the following commands to clone the architecture and isolate the environment.

1. Clone the repository:

PowerShell
git clone https://github.com/Chanan57/XAUUSD_TradingBot.git
cd XAUUSD_TradingBot
2. Build the Iron Shield (Virtual Environment):
Never install algorithmic trading libraries globally. Isolate them.

PowerShell
python -m venv venv
3. Activate the Environment:

PowerShell
venv\Scripts\activate
(You should now see (venv) at the start of your terminal line).

4. Install Quantitative Dependencies:

PowerShell
pip install -r requirements.txt
Phase 4: The Dual-Terminal Architecture (Best Practice)
To prevent API collisions between live trading and historical data mining, it is highly recommended to use a Dual-Terminal Setup:

Terminal 1 (Live Production): Installed in C:\Program Files\MetaTrader 5. This runs main.py and actively manages your risk.

Terminal 2 (Sandbox/Backtesting): Installed in a separate folder (e.g., C:\Program Files\MetaTrader 5 - Sandbox). Logged into a Demo account. You must hardcode this path into Backtest.py to run historical simulations safely.

Phase 5: Execution Protocols
With the terminal open and the virtual environment active, you are ready to deploy.

To launch the Live Hunting Engine:

PowerShell
python main.py
Verify the console prints the Dual-Frequency Architecture Initialized success message.

To run the Visual Backtester (Sandbox Only):

PowerShell
python Backtest.py
This will crunch historical data and automatically open an interactive HTML chart in your web browser showing all AI entries and exits.