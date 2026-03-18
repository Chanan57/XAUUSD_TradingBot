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

# --- 1. CONFIGURATION (V5.9.5 XAI) ---
SYMBOL = "XAUUSD.a"       # CHECK BROKER SYMBOL
TIMEFRAME = mt5.TIMEFRAME_M30
RISK_PERCENT = 0.02       # 2% Risk
MAGIC_NUMBER = 888010     # V5.9.5 Magic Number
MAX_SPREAD_NORMAL = 35    
MAX_SPREAD_HIGH_CONF = 60 

# --- AI & STRATEGY SETTINGS ---
CONFIDENCE_ENTRY = 0.55    
CONFIDENCE_REVERSAL = 0.60 
HIGH_CONFIDENCE_LVL = 0.65 
EMA_SECONDARY = 50        
TRAINING_SIZE = 15000      # 14.5 Months of Data

# --- ORACLE HORIZON SETTINGS ---
PREDICTION_HORIZON = 4      # Look 4 candles ahead
MIN_HORIZON_RETURN = 0.0015 

# --- 2. STARTUP ---
if not mt5.initialize():
    print("❌ MT5 Startup Failed.", flush=True); sys.exit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select {SYMBOL}.", flush=True)
    SYMBOL = "XAUUSD"
    mt5.symbol_select(SYMBOL, True)

# --- 3. ENHANCED LOGGING SYSTEM ---
def log_trade(action, symbol, price, sl, tp, volume, logic_note):
    filename = "Phoenix_Trades.csv"
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

def log_brain_activity(timestamp, price, prob_up, prob_down, brain_reason, trend, rsi, atr, spread, decision):
    """Logs EVERY analysis decision to CSV for auditing"""
    filename = "Phoenix_Brain_Log.csv"
    try:
        file_exists = os.path.isfile(filename)
        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Date", "Time", "Price", "Prob_UP", "Prob_DOWN", "Brain_Reason", "Trend", "RSI", "ATR", "Spread", "Decision"])
            d_str = timestamp.strftime("%Y-%m-%d")
            t_str = timestamp.strftime("%H:%M:%S")
            writer.writerow([d_str, t_str, price, f"{prob_up:.3f}", f"{prob_down:.3f}", brain_reason, trend, f"{rsi:.1f}", f"{atr:.2f}", spread, decision])
    except: pass

def print_log_block(timestamp, price, spread, balance, equity, prob_up, prob_down, brain_reason, trend_status, trend_reason, rsi, atr, sma, ema, decision):
    """Prints a detailed block including BRAIN REASON"""
    print(f"\n{'='*65}", flush=True)
    print(f" 📅 LOG ENTRY: {timestamp} | 🦅 PHOENIX V5.9.5 (XAI)", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 💰 Price:   {price:<10.2f}    🛡️ Spread: {spread:<5.1f}", flush=True)
    print(f" 💵 Equity:  ${equity:<10.2f}    📉 DD:     {((566.15 - equity)/566.15)*100:.2f}%", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 🧠 AI BRAIN:       🟢 UP: {prob_up:.1%}      🔴 DOWN: {prob_down:.1%}", flush=True)
    print(f"    👉 Reason:      {brain_reason}", flush=True)
    print(f" 🌊 TREND:          {trend_status}", flush=True)
    print(f"    👉 Reason:      {trend_reason}", flush=True)
    print(f" 📊 TECHS:          RSI: {rsi:.1f} | ATR: {atr:.2f}", flush=True)
    print(f" 📈 INDS:           SMA200: {sma:.2f} | EMA50: {ema:.2f}", flush=True)
    print(f"{'-'*65}", flush=True)
    print(f" 🤖 DECISION:       {decision}", flush=True)
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
    df['hour'] = df['time'].dt.hour
    df['return_1'] = df['close'].pct_change(1)
    # Rolling Return (Momentum over horizon)
    df['rolling_return'] = df['close'].pct_change(PREDICTION_HORIZON)
    df.dropna(inplace=True)
    return df

def get_brain_reason(prob_up, prob_down, rsi, dist_ema, atr, rolling_return):
    """Heuristic function to explain WHY the AI made a choice"""
    if prob_up > 0.55:
        if rsi < 35: return "Oversold Bounce (RSI < 35)"
        if rolling_return > 0.002: return "Strong Upside Momentum"
        if 0 < dist_ema < atr: return "Perfect Trend Pullback"
        return "Pattern Match (Hidden)"
    elif prob_down > 0.55:
        if rsi > 65: return "Overbought Rejection (RSI > 65)"
        if rolling_return < -0.002: return "Strong Downside Momentum"
        if -atr < dist_ema < 0: return "Bearish Trend Continuation"
        return "Pattern Match (Hidden)"
    else:
        return "Uncertain / Low Confidence"

def get_lot_size(balance, risk_pct, sl_dist, sym_info):
    risk_cash = balance * risk_pct
    contract_size = sym_info.trade_contract_size 
    if sl_dist == 0: sl_dist = 1.0 
    
    min_trade_risk = 0.01 * contract_size * sl_dist
    if min_trade_risk > (risk_cash * 2.5): return 0.0, 0.0

    raw_lots = risk_cash / (sl_dist * contract_size)
    acc = mt5.account_info()
    margin_check = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, sym_info.ask)
    max_lots = raw_lots
    if margin_check is not None: max_lots = (acc.margin_free * 0.95) / margin_check
    
    return max(0.01, round(min(raw_lots, max_lots), 2)), risk_cash

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
                    "comment": f"V5.9.5:{reason}", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(req)
                print(f"🔄 TRADE CLOSED: {reason} @ {price}", flush=True)
                log_trade("CLOSE", SYMBOL, price, 0, 0, pos.volume, reason)

def train_model():
    print(f"\n🧠 [ORACLE] Training on {TRAINING_SIZE} candles...", flush=True)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, TRAINING_SIZE)
    if rates is None or len(rates) < 100: return None, None
    df = prepare_data(pd.DataFrame(rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    
    # --- ORACLE TARGET LOGIC ---
    future_close = df['close'].shift(-PREDICTION_HORIZON)
    future_return = (future_close - df['close']) / df['close']
    
    # 1 (Buy) if price > +0.15% later, 0 (Sell) if price < -0.15% later
    df['Target'] = -1
    df.loc[future_return > MIN_HORIZON_RETURN, 'Target'] = 1
    df.loc[future_return < -MIN_HORIZON_RETURN, 'Target'] = 0
    
    # Only train on clean signals
    clean_df = df[df['Target'] != -1].copy()
    
    predictors = ['RSI', 'dist_ema50', 'ATR', 'hour', 'return_1', 'rolling_return']
    
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
    
    # Make Prediction
    prob_up = model.predict_proba(pd.DataFrame([last_row[predictors]]))[0][1]
    prob_down = 1 - prob_up
    
    # --- GET BRAIN REASON ---
    brain_reason = get_brain_reason(prob_up, prob_down, last_row['RSI'], last_row['dist_ema50'], last_row['ATR'], last_row['rolling_return'])

    # --- DETAILED TREND LOGIC ---
    price = last_row['close']
    sma = last_row['SMA_200']
    ema = last_row['EMA_50']
    
    trend_up = (price > sma) and (price > ema)
    trend_down = (price < sma) and (price < ema)
    
    trend_status = ""
    trend_reason = ""
    
    if trend_up:
        trend_status = "✅ BULLISH"
        trend_reason = "Price is ABOVE both SMA(200) & EMA(50)"
    elif trend_down:
        trend_status = "✅ BEARISH"
        trend_reason = "Price is BELOW both SMA(200) & EMA(50)"
    else:
        trend_status = "⚠️ MIXED"
        if price > sma:
            trend_reason = "Price > SMA(200) but < EMA(50) (Pullback?)"
        else:
            trend_reason = "Price < SMA(200) but > EMA(50) (Rally?)"

    # DECISION LOGIC
    pos_obj = mt5.positions_get(symbol=SYMBOL)
    current_pos = "BUY" if (pos_obj and pos_obj[0].type == mt5.ORDER_TYPE_BUY) else "SELL" if pos_obj else None
    
    signal = None
    decision_text = "WAITING"
    
    if current_pos is None:
        if prob_up > CONFIDENCE_ENTRY and trend_up: 
            signal = "BUY"
            decision_text = "ENTRY SIGNAL (BUY)"
        elif prob_down > CONFIDENCE_ENTRY and trend_down: 
            signal = "SELL"
            decision_text = "ENTRY SIGNAL (SELL)"
        else:
            decision_text = f"HOLD (Conf: {max(prob_up, prob_down):.2f} < {CONFIDENCE_ENTRY})"
    elif current_pos == "BUY" and prob_down > CONFIDENCE_REVERSAL: 
        signal = "SELL"
        decision_text = "REVERSAL SIGNAL (Flip to SELL)"
    elif current_pos == "SELL" and prob_up > CONFIDENCE_REVERSAL: 
        signal = "BUY"
        decision_text = "REVERSAL SIGNAL (Flip to BUY)"
    else:
        decision_text = f"MANAGING POSITION ({current_pos})"

    # EXECUTION
    if signal and signal != current_pos:
        allowed_spread = MAX_SPREAD_HIGH_CONF if max(prob_up, prob_down) >= HIGH_CONFIDENCE_LVL else MAX_SPREAD_NORMAL
        if spread_points <= allowed_spread:
            if current_pos: close_all("SignalFlip")
            
            sl_d = max(1.2 * last_row['ATR'], 0.50)
            vol, cash = get_lot_size(acc.balance, RISK_PERCENT, sl_d, symbol_info)
            
            if vol > 0:
                p = tick.ask if signal == "BUY" else tick.bid
                sl = p - sl_d if signal == "BUY" else p + sl_d
                tp = p + (4.0 * sl_d) if signal == "BUY" else p - (4.0 * sl_d)
                
                req = {
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": vol, "magic": MAGIC_NUMBER,
                    "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
                    "price": p, "sl": sl, "tp": tp, "comment": "V5.9.5 XAI", 
                    "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC
                }
                result = mt5.order_send(req)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"🚀 TRADE EXECUTED: {signal} @ {p}", flush=True)
                    log_trade(signal, SYMBOL, p, sl, tp, vol, f"Entry AI:{max(prob_up, prob_down):.2f}")
        else:
            decision_text = f"SIGNAL BLOCKED (Spread {spread_points:.1f} > {allowed_spread})"

    # PRINT LOG BLOCK
    print_log_block(
        datetime.now(), tick.ask, spread_points, acc.balance, acc.equity, 
        prob_up, prob_down, brain_reason, trend_status, trend_reason,
        last_row['RSI'], last_row['ATR'], 
        sma, ema, 
        decision_text
    )
    
    # SAVE BRAIN LOG
    log_brain_activity(datetime.now(), tick.ask, prob_up, prob_down, brain_reason, trend_status, last_row['RSI'], last_row['ATR'], spread_points, decision_text)

# --- 5. RUN ---
model, predictors = train_model()
if model is None: sys.exit()
print("\n✅ V5.9.5 PHOENIX (EXPLAINABLE AI) INITIALIZED.", flush=True)
print("⏳ Waiting for next candle to print full analysis...", flush=True)

rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
last_candle_time = rates[0]['time'] if rates is not None else 0
last_day = datetime.now().day

# Force first print
perform_analysis(model, predictors)

while True:
    try:
        now = datetime.now()
        if now.day != last_day and now.hour == 9: 
            model, predictors = train_model()
            last_day = now.day

        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        if rates is not None and rates[0]['time'] != last_candle_time:
            last_candle_time = rates[0]['time']
            perform_analysis(model, predictors) # Prints the block

        time.sleep(5) 
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)
        time.sleep(10)