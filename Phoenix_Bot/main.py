import sys
import io
import time
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5

# --- IMPORT OUR CUSTOM MODULES ---
from config import *
import logger
import data_engine
import risk_manager
import ai_oracle
import execution
import news_filter

# --- 0. WINDOWS CONSOLE FIX ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') 

# --- 1. STARTUP ---
if not mt5.initialize():
    print("❌ MT5 Startup Failed.", flush=True); sys.exit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select {SYMBOL}.", flush=True)
    SYMBOL = "XAUUSD"
    mt5.symbol_select(SYMBOL, True)

# --- 2. THE PIPELINE (CORE LOGIC) ---
# ADDED: is_new_candle flag to control the logging frequency
def run_pipeline(model, predictors, is_new_candle=True):
    """The master sequence: Gather Data -> Predict -> Decide -> Execute -> Log""" 
    tick = mt5.symbol_info_tick(SYMBOL)
    symbol_info = mt5.symbol_info(SYMBOL)
    acc = mt5.account_info()
    if not tick or not symbol_info or not acc: return

    # A. GATHER DATA
    spread_points = (tick.ask - tick.bid) / symbol_info.point
    live_rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 300)
    if live_rates is None: return
    
    live_df = data_engine.prepare_data(pd.DataFrame(live_rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    last_row = live_df.iloc[-1]

    # B. AI PREDICTION
    prob_up = model.predict_proba(pd.DataFrame([last_row[predictors]]))[0][1]
    prob_down = 1 - prob_up
    brain_reason = ai_oracle.get_brain_reason(prob_up, prob_down, last_row['RSI'], last_row['dist_ema50'], last_row['ATR'], last_row['ADX'])

    # C. MARKET STATE
    price, sma, ema, adx = last_row['close'], last_row['SMA_200'], last_row['EMA_50'], last_row['ADX']
    trend_up = (price > sma) and (price > ema)
    trend_down = (price < sma) and (price < ema)
    trend_status = "✅ BULLISH" if trend_up else "✅ BEARISH" if trend_down else "⚠️ MIXED"
    
    pos_obj = mt5.positions_get(symbol=SYMBOL)
    current_pos = "BUY" if (pos_obj and pos_obj[0].type == mt5.ORDER_TYPE_BUY) else "SELL" if pos_obj else None
    
    signal = None
    decision_text = "WAITING"
    risk_warning = ""

    # D. THE V6.4 STRATEGY LOGIC (WITH NEWS SHIELD)
    is_embargo, news_title = news_filter.is_news_embargo()

    if current_pos is None:
        if is_embargo:
            decision_text = f"⛔ BLOCKED (News Embargo: {news_title})"
        elif adx < ADX_THRESHOLD:
            decision_text = f"WAITING (Choppy: ADX {adx:.1f} < {ADX_THRESHOLD})"
        else:
            if prob_up > CONFIDENCE_ENTRY and trend_up:
                if last_row['RSI'] < 70: signal = "BUY"; decision_text = "SNIPER BUY SIGNAL"
                else: decision_text = "WAITING (Overbought)"
            elif prob_down > CONFIDENCE_ENTRY and trend_down:
                if last_row['RSI'] > 30: signal = "SELL"; decision_text = "SNIPER SELL SIGNAL"
                else: decision_text = "WAITING (Oversold)"
            else:
                decision_text = f"HUNTING... (Conf: {max(prob_up, prob_down):.2f})"

    # THE V6.4 FIX: CONFIRMED EXITS
    elif current_pos == "BUY" and prob_down > CONFIDENCE_REVERSAL and price < ema: 
        signal = "CLOSE"; decision_text = "CONFIRMED EXIT (AI Fear + Trend Break)"
    elif current_pos == "SELL" and prob_up > CONFIDENCE_REVERSAL and price > ema: 
        signal = "CLOSE"; decision_text = "CONFIRMED EXIT (AI Fear + Trend Break)"
    else:
        decision_text = f"MANAGING POSITION ({current_pos})"

    # E. EXECUTION & RISK
    if signal == "CLOSE":
        if current_pos: execution.close_all("Confirmed_Reversal_Exit")
        
    elif signal and signal != current_pos:
        allowed_spread = MAX_SPREAD_HIGH_CONF if max(prob_up, prob_down) >= HIGH_CONFIDENCE_LVL else MAX_SPREAD_NORMAL
        
        if spread_points <= allowed_spread:
            sl_d = max(1.2 * last_row['ATR'], 0.50)
            vol, cash, risk_warning = risk_manager.get_lot_size(acc.balance, RISK_PERCENT, sl_d, symbol_info)
            
            if vol > 0:
                p = tick.ask if signal == "BUY" else tick.bid
                sl = p - sl_d if signal == "BUY" else p + sl_d
                tp = p + (4.0 * sl_d) if signal == "BUY" else p - (4.0 * sl_d)
                
                execution.open_trade(signal, p, sl, tp, vol, max(prob_up, prob_down))
            else:
                decision_text = f"SKIPPED (Risk > $25 USD)"
        else:
            decision_text = f"BLOCKED (Spread {spread_points:.1f})"

    # F. PRINT DASHBOARD & LOGS
    # ADDED: Only print to console if a new 30m candle prints OR if the bot is making a physical trade/exit
    if is_new_candle or signal:
        logger.print_log_block(
            datetime.now(), tick.ask, spread_points, acc.balance, acc.equity, 
            prob_up, prob_down, brain_reason, trend_status, last_row['RSI'], 
            last_row['ATR'], adx, decision_text, risk_warning
        )
        logger.log_brain_activity(
            datetime.now(), tick.ask, prob_up, prob_down, brain_reason, 
            trend_status, last_row['RSI'], last_row['ATR'], adx, spread_points, decision_text
        )

# --- 3. MASTER LOOP ---
model, predictors = ai_oracle.train_model()
if model is None: sys.exit()

print("\n✅ PHOENIX V6.4 DUAL-FREQUENCY ARCHITECTURE INITIALIZED.", flush=True)
print("   - Fundamental Shield (News Embargo): ACTIVE")
print("   - Exits: High-Frequency 5-Second Active Monitoring")
print("⏳ Waiting for next candle to print full analysis...", flush=True)

rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
last_candle_time = rates[0]['time'] if rates is not None else 0
last_day = datetime.now().day

run_pipeline(model, predictors, is_new_candle=True) # Force first run

while True:
    try:
        now = datetime.now()
        
        # Periodic AI Retraining
        if now.day != last_day and now.hour == 9: 
            model, predictors = ai_oracle.train_model()
            last_day = now.day

        # 1. Check if we currently hold an open trade
        pos_obj = mt5.positions_get(symbol=SYMBOL)
        in_trade = pos_obj is not None and len(pos_obj) > 0

        # 2. Check if a brand new 30-minute candle just opened
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        is_new_candle = (rates is not None and len(rates) > 0 and rates[0]['time'] != last_candle_time)

        # 3. The Dual-Frequency Routing
        if is_new_candle:
            # Low-Frequency: New candle prints, run full pipeline and print the dashboard
            last_candle_time = rates[0]['time']
            run_pipeline(model, predictors, is_new_candle=True) 
            
        elif in_trade:
            # High-Frequency: We are actively in a trade. Run silently every 5 seconds to check Reversals
            run_pipeline(model, predictors, is_new_candle=False)

        # The Institutional Heartbeat (Crucial 5-second pause)
        time.sleep(5) 
        
    except Exception as e:
        print(f"⚠️ Master Loop Error: {e}", flush=True)
        time.sleep(10)