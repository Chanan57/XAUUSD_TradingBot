import sys
import io

# --- 0. WINDOWS CONSOLE FIX ---
# Forces the console to handle Emojis (🧠, 🟢) and FLUSH output immediately
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import MetaTrader5 as mt5
import pandas as pd
import ta 
import time
import csv
import os
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier

# --- 1. CONFIGURATION (VERIFIED FOR PEPPERSTONE) ---
SYMBOL = "XAUUSD.a"       # Gold (Retail)
TIMEFRAME = mt5.TIMEFRAME_M30
RISK_PERCENT = 0.02       # Risk 2% of Equity per trade
MAGIC_NUMBER = 777999     

# --- HYSTERESIS & FILTERS ---
CONFIDENCE_ENTRY = 0.52    
CONFIDENCE_REVERSAL = 0.57 
EMA_SECONDARY = 50         
TRAINING_SIZE = 15000      

# --- 2. STARTUP & SAFETY CHECKS ---
if not mt5.initialize():
    print("❌ MT5 Startup Failed. Is MT5 Open?", flush=True)
    sys.exit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select {SYMBOL}. Is the suffix correct?", flush=True)
    sys.exit()

# --- 3. DUAL LOGGING FUNCTIONS ---
def log_trade(action, symbol, price, sl, tp, volume, logic_note):
    filename = "Gold_Strategy_Trades_V5.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Date", "Time", "Action", "Symbol", "Price", "SL", "TP", "Volume", "Balance", "Logic"])
        now = datetime.now()
        acc = mt5.account_info()
        writer.writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), action, symbol, price, sl, tp, volume, acc.balance, logic_note])

# [UPDATED] Added Balance and Equity to Analysis Log
def log_analysis(time_stamp, price, prob_up, prob_down, rsi, sma, ema, atr, trend_status, balance, equity):
    filename = "Gold_Strategy_Analysis_V5.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            # Header now includes Balance and Equity
            writer.writerow(["Date", "Time", "Price", "AI_UP", "AI_DOWN", "RSI", "SMA_200", "EMA_50", "ATR", "Trend_Status", "Balance", "Equity"])
        
        d_str = time_stamp.strftime("%Y-%m-%d")
        t_str = time_stamp.strftime("%H:%M:%S")
        writer.writerow([d_str, t_str, price, f"{prob_up:.2f}", f"{prob_down:.2f}", 
                         f"{rsi:.1f}", f"{sma:.2f}", f"{ema:.2f}", f"{atr:.2f}", trend_status, f"{balance:.2f}", f"{equity:.2f}"])

# --- 4. DATA & TRADING HELPERS ---
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
    df.dropna(inplace=True)
    return df

# [UPDATED] Volatility Safety Guard Added Here
def get_lot_size(balance, risk_pct, sl_dist, sym_info):
    risk_cash = balance * risk_pct
    contract_size = sym_info.trade_contract_size # Auto-detects 100 for XAUUSD.a
    if sl_dist == 0: sl_dist = 1.0 
    
    # --- VOLATILITY SAFETY GUARD ---
    # Calculate the absolute dollar risk of the smallest possible trade (0.01 lots)
    min_trade_risk = 0.01 * contract_size * sl_dist
    
    # If the minimum trade is 50% riskier than our budget, SKIP IT.
    # Example: Budget is $15. Min Trade risks $80. -> SKIP.
    if min_trade_risk > (risk_cash * 1.5):
        print(f"⚠️ SAFETY TRIGGER: Volatility too high.", flush=True)
        print(f"   Required Risk Limit: ${risk_cash:.2f}", flush=True)
        print(f"   Min Possible Risk:   ${min_trade_risk:.2f}", flush=True)
        print(f"   -> Trade SKIPPED to protect account.", flush=True)
        return 0.0, risk_cash
    # -------------------------------

    raw_lots = risk_cash / (sl_dist * contract_size)
    
    # Margin Check
    acc = mt5.account_info()
    margin_check = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, sym_info.ask)
    if margin_check is None: max_lots = raw_lots
    else: max_lots = (acc.margin_free * 0.9) / margin_check
    
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
                req = {"action": mt5.TRADE_ACTION_DEAL, "position": pos.ticket, "symbol": SYMBOL, "volume": pos.volume,
                       "type": type_op, "price": price, "magic": MAGIC_NUMBER, "comment": f"V5:{reason}",
                       "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                mt5.order_send(req)
                print(f"🔄 Closing {pos.ticket} ({reason})", flush=True)

def train_model():
    print(f"🧠 Training AI Model on last {TRAINING_SIZE} candles...", flush=True)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, TRAINING_SIZE)
    if rates is None or len(rates) < 100:
        print("❌ Not enough data to train. Retrying...", flush=True)
        return None, None
    df = prepare_data(pd.DataFrame(rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)
    predictors = ['RSI', 'dist_ema50', 'ATR', 'hour', 'return_1']
    clf = RandomForestClassifier(n_estimators=200, min_samples_split=20, random_state=1)
    clf.fit(df[predictors], df['Target'])
    return clf, predictors

# --- 5. CORE ANALYSIS FUNCTION ---
def perform_analysis(model, predictors):
    """Runs the full AI check, Trade Logic, and Dashboard Print"""
    # 1. Check Data
    live_rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 250)
    if live_rates is None: return
    
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None: return

    # 2. Get Account Info (For Logging)
    acc = mt5.account_info()
    if acc is None: return

    # 3. Prepare Data
    live_df = prepare_data(pd.DataFrame(live_rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    last_row = live_df.iloc[-1]
    
    # 4. AI Prediction
    prob_up = model.predict_proba(pd.DataFrame([last_row[predictors]]))[0][1]
    prob_down = 1 - prob_up
    
    # 5. Trends
    trend_up = (last_row['close'] > last_row['SMA_200']) and (last_row['close'] > last_row['EMA_50'])
    trend_down = (last_row['close'] < last_row['SMA_200']) and (last_row['close'] < last_row['EMA_50'])
    
    # 6. Trade Execution Logic
    pos_obj = mt5.positions_get(symbol=SYMBOL)
    current_pos = "BUY" if (pos_obj and pos_obj[0].type == mt5.ORDER_TYPE_BUY) else "SELL" if pos_obj else None
    
    signal = None
    if current_pos is None:
        if prob_up > CONFIDENCE_ENTRY and trend_up: signal = "BUY"
        elif prob_down > CONFIDENCE_ENTRY and trend_down: signal = "SELL"
    elif current_pos == "BUY" and prob_down > CONFIDENCE_REVERSAL: signal = "SELL"
    elif current_pos == "SELL" and prob_up > CONFIDENCE_REVERSAL: signal = "BUY"

    if signal and signal != current_pos:
        if (signal == "BUY" and trend_up) or (signal == "SELL" and trend_down):
            close_all("SignalFlip")
            sym_info = mt5.symbol_info(SYMBOL)
            
            if acc and sym_info:
                sl_d = max(1.5 * last_row['ATR'], 0.50)
                
                # CALL THE SAFER LOT SIZE FUNCTION
                vol, cash = get_lot_size(acc.balance, RISK_PERCENT, sl_d, sym_info)
                
                # Only trade if volume > 0 (Safety Guard passed)
                if vol > 0:
                    p = tick.ask if signal == "BUY" else tick.bid
                    sl = p - sl_d if signal == "BUY" else p + sl_d
                    tp = p + (4.0 * sl_d) if signal == "BUY" else p - (4.0 * sl_d)
                    
                    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": vol, "magic": MAGIC_NUMBER,
                           "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
                           "price": p, "sl": sl, "tp": tp, "comment": "AI V5.3 Live", 
                           "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                    res = mt5.order_send(req)
                    if res.retcode == mt5.TRADE_RETCODE_DONE: 
                        log_trade(signal, SYMBOL, p, sl, tp, vol, f"V5.3 Entry AI:{max(prob_up, prob_down):.2f}")
                    else:
                        print(f"❌ Order Failed: {res.comment}", flush=True)

    # 7. Dashboard & Logging (UPDATED with Balance/Equity)
    if trend_up: trend_status = "✅ BULLISH"
    elif trend_down: trend_status = "✅ BEARISH"
    else:
        if last_row['close'] > last_row['SMA_200'] and last_row['close'] < last_row['EMA_50']: reason = "Below 50EMA (Dip)"
        elif last_row['close'] < last_row['SMA_200'] and last_row['close'] > last_row['EMA_50']: reason = "Above 50EMA (Rally)"
        else: reason = "Trapped"
        trend_status = f"⚠️ MIXED ({reason})"
        
    log_analysis(datetime.now(), last_row['close'], prob_up, prob_down, last_row['RSI'], 
                 last_row['SMA_200'], last_row['EMA_50'], last_row['ATR'], trend_status, 
                 acc.balance, acc.equity) # <-- PASSING BAL/EQ HERE
    
    print("-" * 60, flush=True)
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')} | 💰 Price: {last_row['close']:.2f}", flush=True)
    print(f"💵 Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f}", flush=True)
    print(f"🧠 AI Brain:   🟢 UP {prob_up:.1%}  |  🔴 DOWN {prob_down:.1%}", flush=True) 
    print(f"🌊 Trend Check: {trend_status}", flush=True)
    print(f"      Levels: SMA(200)= {last_row['SMA_200']:.2f} | EMA(50)= {last_row['EMA_50']:.2f}", flush=True)
    print(f"📊 Indicators: RSI={last_row['RSI']:.1f} | ATR={last_row['ATR']:.2f}", flush=True)
    print("-" * 60, flush=True)


# --- 6. INITIALIZATION & MAIN LOOP ---
model, predictors = train_model()
if model is None: sys.exit()

print("✅ Initial Training Complete.", flush=True)

# 1. RUN ANALYSIS IMMEDIATELY (First Run)
perform_analysis(model, predictors)

# 2. Initialize Candle Tracker

rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
last_candle_time = rates[0]['time'] if rates is not None else None

# 3. Initialize Retraining Tracker
last_training_day = datetime.now().day

print("⏳ Monitoring for next M30 candle...", flush=True)

while True:
    try:
        now = datetime.now()
        
        # Automatic Retraining (Daily at 23:01)
        if now.hour == 23 and now.minute == 1 and last_training_day != now.day:
            print("📅 Starting Daily Retraining...", flush=True)
            new_model, new_preds = train_model()
            if new_model:
                model, predictors = new_model, new_preds
                last_training_day = now.day
                print("✅ Retraining Success.", flush=True)

        # New Candle Check
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        if rates is not None and last_candle_time != rates[0]['time']:
            last_candle_time = rates[0]['time']
            
            # Rollover Filter (23:00 - 01:00 Server Time)
            if 23 <= now.hour or now.hour < 1:
                print(f"💤 Rollover Hours. Skipping.", flush=True)
            else:
                perform_analysis(model, predictors)

        time.sleep(5)
        
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)
        time.sleep(10)