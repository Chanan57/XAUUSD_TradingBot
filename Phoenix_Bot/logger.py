import csv
import os
from datetime import datetime
import MetaTrader5 as mt5
from config import *

def log_trade(action, symbol, price, sl, tp, volume, logic_note):
    """Only logs actual trade executions to the CSV."""
    filename = "Phoenix_Trades_V6.csv"
    try:
        file_exists = os.path.isfile(filename)
        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Date", "Time", "Action", "Symbol", "Price", "SL", "TP", "Volume", "Balance", "Logic"])
            now = datetime.now()
            acc = mt5.account_info()
            writer.writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), action, symbol, price, sl, tp, volume, acc.balance, logic_note])
    except: pass

def log_brain_activity(timestamp, price, prob_up, prob_down, brain_reason, trend, rsi, atr, adx, spread, decision):
    """DISABLED: We are no longer flooding the CSV with every single candle's data."""
    pass

def print_log_block(timestamp, price, spread, balance, equity, prob_up, prob_down, brain_reason, trend_status, rsi, atr, adx, decision, risk_note=""):
    """Prints the live dashboard to the console. Updated for the $500 USD Target."""
    gap = 500.00 - equity  # Updated target to $500 USD
    gap_pct = (gap / 500.00) * 100

    print(f"\n{'='*65}", flush=True)
    print(f" 📅 LOG: {timestamp.strftime('%H:%M:%S')} | 🦅 PHOENIX V6.4 (CONFIRMED EXITS)", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 💰 Price:   {price:<10.2f}    🛡️ Spread: {spread:<5.1f}", flush=True)
    print(f" 💵 Equity:  ${equity:<10.2f}    🎯 To $500: ${gap:<8.2f} ({gap_pct:.1f}%)", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 🎯 ADX FILTER:     {adx:.1f} ({'✅ GO' if adx > ADX_THRESHOLD else '⛔ WAIT/CHOP'})", flush=True)
    print(f" 🧠 AI BRAIN:       🟢 UP: {prob_up:.1%}    🔴 DOWN: {prob_down:.1%}", flush=True)
    print(f"    👉 Reason:      {brain_reason}", flush=True)
    print(f" 🌊 TREND:          {trend_status}", flush=True)
    print(f" 📊 TECHS:          RSI: {rsi:.1f} | ATR: {atr:.2f}", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 🤖 DECISION:       {decision}", flush=True)
    if risk_note:
        print(f" ⚠️ RISK NOTE:      {risk_note}", flush=True)
    print(f"{'='*65}\n", flush=True)