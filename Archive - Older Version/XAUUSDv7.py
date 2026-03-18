import sys
import io

# --- 0. WINDOWS CONSOLE FIX ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import MetaTrader5 as mt5
import pandas as pd
import ta 
import time
import csv
import os
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier

# --- 1. CONFIGURATION (V6.4 CONFIRMED EXITS) ---
SYMBOL = "XAUUSD.a"       # CHECK BROKER SYMBOL
TIMEFRAME = mt5.TIMEFRAME_M30
RISK_PERCENT = 0.02       # 2% Risk
MAGIC_NUMBER = 888064     # V6.4 Magic Number
MAX_SPREAD_NORMAL = 35    
MAX_SPREAD_HIGH_CONF = 60 

# --- STRATEGY SETTINGS ---
ADX_THRESHOLD = 20.0      # MINIMUM Trend Strength (Blocks Chop)
# NOTE: Profit Lock has been REMOVED to let trades breathe.

# --- RISK LIMITS ---
MAX_SURVIVABLE_LOSS_AUD = 40.00 # Iron Clad Cap (Max loss per trade)

# --- AI & STRATEGY SETTINGS ---
CONFIDENCE_ENTRY = 0.55    
CONFIDENCE_REVERSAL = 0.60 
HIGH_CONFIDENCE_LVL = 0.65 
EMA_SECONDARY = 50        
TRAINING_SIZE = 15000      

# --- ORACLE HORIZON SETTINGS ---
PREDICTION_HORIZON = 4      
MIN_HORIZON_RETURN = 0.0015 

# --- 2. STARTUP ---
if not mt5.initialize():
    print("❌ MT5 Startup Failed.", flush=True); sys.exit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select {SYMBOL}.", flush=True)
    SYMBOL = "XAUUSD"
    mt5.symbol_select(SYMBOL, True)

# --- 3. LOGGING SYSTEM ---
def log_trade(action, symbol, price, sl, tp, volume, logic_note):
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
    filename = "Phoenix_Brain_Log_V6.csv"
    try:
        file_exists = os.path.isfile(filename)
        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Date", "Time", "Price", "Prob_UP", "Prob_DOWN", "Brain_Reason", "Trend", "RSI", "ATR", "ADX", "Spread", "Decision"])
            d_str = timestamp.strftime("%Y-%m-%d")
            t_str = timestamp.strftime("%H:%M:%S")
            writer.writerow([d_str, t_str, price, f"{prob_up:.3f}", f"{prob_down:.3f}", brain_reason, trend, f"{rsi:.1f}", f"{atr:.2f}", f"{adx:.1f}", spread, decision])
    except: pass

def print_log_block(timestamp, price, spread, balance, equity, prob_up, prob_down, brain_reason, trend_status, trend_reason, rsi, atr, adx, decision, risk_note=""):
    """Prints the Dashboard"""
    
    # Calculate Gap to $1000
    gap = 1000.00 - equity
    gap_pct = (gap / 1000.00) * 100

    print(f"\n{'='*65}", flush=True)
    print(f" 📅 LOG: {timestamp.strftime('%H:%M:%S')} | 🦅 PHOENIX V6.4 (CONFIRMED EXITS)", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 💰 Price:   {price:<10.2f}    🛡️ Spread: {spread:<5.1f}", flush=True)
    print(f" 💵 Equity:  ${equity:<10.2f}    🎯 To $1k: ${gap:<8.2f} ({gap_pct:.1f}%)", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 🎯 ADX FILTER:     {adx:.1f} ({'✅ GO' if adx > ADX_THRESHOLD else '⛔ WAIT/CHOP'})", flush=True)
    print(f" 🧠 AI BRAIN:       🟢 UP: {prob_up:.1%}      🔴 DOWN: {prob_down:.1%}", flush=True)
    print(f"    👉 Reason:      {brain_reason}", flush=True)
    print(f" 🌊 TREND:          {trend_status}", flush=True)
    print(f" 📊 TECHS:          RSI: {rsi:.1f} | ATR: {atr:.2f}", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 🤖 DECISION:       {decision}", flush=True)
    if risk_note:
        print(f" ⚠️ RISK NOTE:      {risk_note}", flush=True)
    print(f"{'='*65}\n", flush=True)

# --- 4. DATA ENGINE (ORACLE) ---
def prepare_data(df):
    df.columns = [x.lower() for x in df.columns]
    df = df.copy() 
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    df['SMA_200'] = ta.trend.sma_indicator(df['close'], window=200)
    df['EMA_50'] = ta.trend.ema_indicator(df['close'], window=EMA_SECONDARY)
    df['dist_ema50'] = df['close'] - df['EMA_50']
    df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    
    # ADX for Filter
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    
    df['hour'] = df['time'].dt.hour
    df['return_1'] = df['close'].pct_change(1)
    df['rolling_return'] = df['close'].pct_change(PREDICTION_HORIZON)
    df.dropna(inplace=True)
    return df

def get_brain_reason(prob_up, prob_down, rsi, dist_ema, atr, adx):
    if adx < ADX_THRESHOLD: return "Market Chopping (Low ADX)"
    
    if prob_up > 0.55:
        if rsi < 40: return "Sniper Entry (Dip in Uptrend)"
        if rsi > 70: return "Overbought (Caution)"
        return "Bullish Momentum"
    elif prob_down > 0.55:
        if rsi > 60: return "Sniper Entry (Rally in Downtrend)"
        if rsi < 30: return "Oversold (Caution)"
        return "Bearish Momentum"
    else:
        return "Uncertain / Waiting"

# --- 5. RISK ENGINE ---
def get_exchange_rate(base_currency, target_currency):
    if base_currency == target_currency: return 1.0
    pair = f"{base_currency}{target_currency}"
    tick = mt5.symbol_info_tick(pair)
    if tick: return tick.bid 
    pair_inv = f"{target_currency}{base_currency}"
    tick_inv = mt5.symbol_info_tick(pair_inv)
    if tick_inv: return 1.0 / tick_inv.ask
    return 0.65 

def get_lot_size(balance, risk_pct, sl_dist, sym_info):
    contract_size = sym_info.trade_contract_size 
    acc_info = mt5.account_info()
    exchange_rate = get_exchange_rate(acc_info.currency, sym_info.currency_profit)
    
    # IRON CLAD CHECK
    min_lot_risk_usd = 0.01 * contract_size * sl_dist
    min_lot_risk_aud = min_lot_risk_usd / exchange_rate 

    if min_lot_risk_aud > MAX_SURVIVABLE_LOSS_AUD:
        return 0.0, 0.0, f"⛔ BLOCKED: Risk ${min_lot_risk_aud:.2f} > Limit"

    risk_cash_aud = balance * risk_pct
    risk_cash_usd = risk_cash_aud * exchange_rate
    raw_lots = risk_cash_usd / (sl_dist * contract_size)
    
    margin_check = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, sym_info.ask)
    max_lots = raw_lots
    if margin_check is not None: max_lots = (acc_info.margin_free * 0.95) / margin_check
    
    final_lots = round(min(raw_lots, max_lots), 2)
    if final_lots < 0.01: final_lots = 0.01
    
    actual_risk_aud = (final_lots * contract_size * sl_dist) / exchange_rate
    return final_lots, risk_cash_aud, f"Risk: ${actual_risk_aud:.2f}"

def close_all(reason="Signal"):
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for pos in positions:
            if pos.magic == MAGIC_NUMBER:
                tick = mt5.symbol_info_tick(SYMBOL)
                if tick is None: return 
                type_op = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if type_op == mt5.ORDER_TYPE_SELL else tick.ask
                req = {
                    "action": mt5.TRADE_ACTION_DEAL, "position": pos.ticket, "symbol": SYMBOL, 
                    "volume": pos.volume, "type": type_op, "price": price, "magic": MAGIC_NUMBER, 
                    "comment": f"V6.4:{reason}", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(req)
                print(f"🔄 TRADE CLOSED: {reason} @ {price}", flush=True)
                log_trade("CLOSE", SYMBOL, price, 0, 0, pos.volume, reason)

# --- 7. ANALYSIS ENGINE ---
def train_model():
    print(f"\n🧠 [ORACLE] Training on {TRAINING_SIZE} candles...", flush=True)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, TRAINING_SIZE)
    if rates is None or len(rates) < 100: return None, None
    df = prepare_data(pd.DataFrame(rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    
    future_close = df['close'].shift(-PREDICTION_HORIZON)
    future_return = (future_close - df['close']) / df['close']
    
    df['Target'] = -1
    df.loc[future_return > MIN_HORIZON_RETURN, 'Target'] = 1
    df.loc[future_return < -MIN_HORIZON_RETURN, 'Target'] = 0
    clean_df = df[df['Target'] != -1].copy()
    
    predictors = ['RSI', 'dist_ema50', 'ATR', 'hour', 'return_1', 'ADX']
    
    clf = RandomForestClassifier(n_estimators=200, min_samples_split=20, random_state=1)
    clf.fit(clean_df[predictors], clean_df['Target'])
    return clf, predictors

def perform_analysis(model, predictors):
    tick = mt5.symbol_info_tick(SYMBOL)
    symbol_info = mt5.symbol_info(SYMBOL)
    acc = mt5.account_info()
    if tick is None or symbol_info is None or acc is None: return

    spread_points = (tick.ask - tick.bid) / symbol_info.point
    live_rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 300)
    if live_rates is None: return

    live_df = prepare_data(pd.DataFrame(live_rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    last_row = live_df.iloc[-1]
    
    # ML Prediction
    prob_up = model.predict_proba(pd.DataFrame([last_row[predictors]]))[0][1]
    prob_down = 1 - prob_up
    
    brain_reason = get_brain_reason(prob_up, prob_down, last_row['RSI'], last_row['dist_ema50'], last_row['ATR'], last_row['ADX'])

    # Logic Variables
    price = last_row['close']
    sma = last_row['SMA_200']
    ema = last_row['EMA_50']
    adx = last_row['ADX']
    
    trend_up = (price > sma) and (price > ema)
    trend_down = (price < sma) and (price < ema)
    trend_status = "✅ BULLISH" if trend_up else "✅ BEARISH" if trend_down else "⚠️ MIXED"
    trend_reason = "Price > SMA & EMA" if trend_up else "Price < SMA & EMA" if trend_down else "Chop/Range"

    pos_obj = mt5.positions_get(symbol=SYMBOL)
    current_pos = "BUY" if (pos_obj and pos_obj[0].type == mt5.ORDER_TYPE_BUY) else "SELL" if pos_obj else None
    
    signal = None
    decision_text = "WAITING"
    risk_warning = ""
    
    # --- V6.4 DECISION LOGIC (CONFIRMED EXITS) ---
    if current_pos is None:
        # 1. ADX SHIELD: Block everything if choppy
        if adx < ADX_THRESHOLD:
            decision_text = f"WAITING (Choppy: ADX {adx:.1f} < {ADX_THRESHOLD})"
        else:
            # 2. SNIPER ENTRY: ML High Confidence + Trend + RSI Confirmation
            if prob_up > CONFIDENCE_ENTRY and trend_up:
                if last_row['RSI'] < 70: # Don't buy top
                    signal = "BUY"; decision_text = "SNIPER BUY SIGNAL"
                else: decision_text = "WAITING (Overbought)"
                    
            elif prob_down > CONFIDENCE_ENTRY and trend_down:
                if last_row['RSI'] > 30: # Don't sell bottom
                    signal = "SELL"; decision_text = "SNIPER SELL SIGNAL"
                else: decision_text = "WAITING (Oversold)"
            else:
                decision_text = f"HUNTING... (Conf: {max(prob_up, prob_down):.2f})"

    # 3. CONFIRMED EXIT: AI Predicts Reversal AND Price Breaks the 50 EMA
    elif current_pos == "BUY" and prob_down > CONFIDENCE_REVERSAL and price < ema: 
        signal = "CLOSE"; decision_text = "CONFIRMED EXIT (AI Fear + Trend Break)"
    elif current_pos == "SELL" and prob_up > CONFIDENCE_REVERSAL and price > ema: 
        signal = "CLOSE"; decision_text = "CONFIRMED EXIT (AI Fear + Trend Break)"
    else:
        decision_text = f"MANAGING POSITION ({current_pos})"

    # EXECUTION
    if signal == "CLOSE":
        if current_pos: close_all("Confirmed_Reversal_Exit")
        
    elif signal and signal != current_pos:
        allowed_spread = MAX_SPREAD_HIGH_CONF if max(prob_up, prob_down) >= HIGH_CONFIDENCE_LVL else MAX_SPREAD_NORMAL
        if spread_points <= allowed_spread:
            
            sl_d = max(1.2 * last_row['ATR'], 0.50)
            vol, cash, risk_warning = get_lot_size(acc.balance, RISK_PERCENT, sl_d, symbol_info)
            
            if vol > 0:
                p = tick.ask if signal == "BUY" else tick.bid
                sl = p - sl_d if signal == "BUY" else p + sl_d
                tp = p + (4.0 * sl_d) if signal == "BUY" else p - (4.0 * sl_d)
                
                req = {
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": vol, "magic": MAGIC_NUMBER,
                    "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
                    "price": p, "sl": sl, "tp": tp, "comment": "V6.4 Confirmed", 
                    "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(req)
                print(f"🚀 SNIPER ENTRY: {signal} @ {p}", flush=True)
                log_trade(signal, SYMBOL, p, sl, tp, vol, f"Entry AI:{max(prob_up, prob_down):.2f}")
            else:
                decision_text = f"SKIPPED (Risk > $40 AUD)"
        else:
            decision_text = f"BLOCKED (Spread {spread_points:.1f})"

    print_log_block(
        datetime.now(), tick.ask, spread_points, acc.balance, acc.equity, 
        prob_up, prob_down, brain_reason, trend_status, trend_reason,
        last_row['RSI'], last_row['ATR'], adx, decision_text, risk_warning
    )
    log_brain_activity(datetime.now(), tick.ask, prob_up, prob_down, brain_reason, trend_status, last_row['RSI'], last_row['ATR'], adx, spread_points, decision_text)

# --- 8. MAIN EXECUTION LOOP ---
model, predictors = train_model()
if model is None: sys.exit()
print("\n✅ PHOENIX VERSION 6.4 (CONFIRMED EXITS) INITIALIZED.", flush=True)
print("   - ADX Shield: ACTIVE (Filter < 20.0)")
print("   - Reversals: REQUIRE TREND BREAK (EMA 50 crossover)")
print("⏳ Waiting for next candle to print full analysis...", flush=True)

rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
last_candle_time = rates[0]['time'] if rates is not None else 0
last_day = datetime.now().day

# Force first analysis
perform_analysis(model, predictors)

while True:
    try:
        now = datetime.now()
        
        # 1. PERIODIC TASKS
        if now.day != last_day and now.hour == 9: 
            model, predictors = train_model(); last_day = now.day

        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        if rates is not None and rates[0]['time'] != last_candle_time:
            last_candle_time = rates[0]['time']
            perform_analysis(model, predictors) # Only prints log on new candle

        time.sleep(5) 
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True); time.sleep(10)