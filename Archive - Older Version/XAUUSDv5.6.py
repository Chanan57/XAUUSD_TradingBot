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

# --- 1. CONFIGURATION (RECOVERY MODE) ---
SYMBOL = "XAUUSD.a"       # Gold (Retail)
TIMEFRAME = mt5.TIMEFRAME_M30
RISK_PERCENT = 0.02       # Baseline calculation (2%)
MAGIC_NUMBER = 777999
MAX_SPREAD_POINTS = 35    # Filter: If spread > 35 points (35 cents), DO NOT TRADE

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

def log_analysis(time_stamp, price, prob_up, prob_down, rsi, sma, ema, atr, trend_status, balance, equity):
    filename = "Gold_Strategy_Analysis_V5.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
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

# [UPDATED] Volatility Safety Guard (RECOVERY MODE)
def get_lot_size(balance, risk_pct, sl_dist, sym_info):
    risk_cash = balance * risk_pct
    contract_size = sym_info.trade_contract_size 
    if sl_dist == 0: sl_dist = 1.0 
    
    # --- VOLATILITY SAFETY GUARD (RECOVERY MODE) ---
    # Calculate the absolute dollar risk of the smallest possible trade (0.01 lots)
    min_trade_risk = 0.01 * contract_size * sl_dist
    
    # RECOVERY UPDATE: Increased tolerance from 1.5 to 5.0
    # Allows trading even if risk is high relative to small account
    if min_trade_risk > (risk_cash * 5.0):
        print(f"⚠️ SAFETY TRIGGER: Volatility CRITICAL.", flush=True)
        print(f"   Max Allowed (5x Risk): ${risk_cash * 5.0:.2f}", flush=True)
        print(f"   Required Risk:         ${min_trade_risk:.2f}", flush=True)
        print(f"   -> Trade SKIPPED. Market too dangerous for current balance.", flush=True)
        return 0.0, risk_cash
    # -----------------------------------------------

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
    # --- NEW SPREAD FILTER ---
    tick = mt5.symbol_info_tick(SYMBOL)
    symbol_info = mt5.symbol_info(SYMBOL)
    if tick is None or symbol_info is None: return

    # Calculate Spread in Points
    spread_points = (tick.ask - tick.bid) / symbol_info.point
    
    # If spread is crazy (Rollover), DO NOT TRADE.
    if spread_points > MAX_SPREAD_POINTS:
        print(f"🛑 HIGH SPREAD DETECTED: {spread_points:.1f} pts. Skipping Analysis.", flush=True)
        return

    # Normal Analysis Flow...
    live_rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 250)
    if live_rates is None: return

    acc = mt5.account_info()
    if acc is None: return

    live_df = prepare_data(pd.DataFrame(live_rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    last_row = live_df.iloc[-1]
    
    prob_up = model.predict_proba(pd.DataFrame([last_row[predictors]]))[0][1]
    prob_down = 1 - prob_up
    
    trend_up = (last_row['close'] > last_row['SMA_200']) and (last_row['close'] > last_row['EMA_50'])
    trend_down = (last_row['close'] < last_row['SMA_200']) and (last_row['close'] < last_row['EMA_50'])
    
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
            
            if acc and symbol_info:
                # RECOVERY UPDATE: Tightened SL to 1.2x ATR to reduce cost
                sl_d = max(1.2 * last_row['ATR'], 0.50)
                
                vol, cash = get_lot_size(acc.balance, RISK_PERCENT, sl_d, symbol_info)
                
                if vol > 0:
                    p = tick.ask if signal == "BUY" else tick.bid
                    sl = p - sl_d if signal == "BUY" else p + sl_d
                    tp = p + (4.0 * sl_d) if signal == "BUY" else p - (4.0 * sl_d)
                    
                    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": vol, "magic": MAGIC_NUMBER,
                           "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
                           "price": p, "sl": sl, "tp": tp, "comment": "AI V5.6 SpreadGuard", 
                           "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                    res = mt5.order_send(req)
                    if res.retcode == mt5.TRADE_RETCODE_DONE: 
                        log_trade(signal, SYMBOL, p, sl, tp, vol, f"V5.6 Entry AI:{max(prob_up, prob_down):.2f}")
                    else:
                        print(f"❌ Order Failed: {res.comment}", flush=True)

    if trend_up: trend_status = "✅ BULLISH"
    elif trend_down: trend_status = "✅ BEARISH"
    else:
        if last_row['close'] > last_row['SMA_200'] and last_row['close'] < last_row['EMA_50']: reason = "Below 50EMA (Dip)"
        elif last_row['close'] < last_row['SMA_200'] and last_row['close'] > last_row['EMA_50']: reason = "Above 50EMA (Rally)"
        else: reason = "Trapped"
        trend_status = f"⚠️ MIXED ({reason})"
        
    log_analysis(datetime.now(), last_row['close'], prob_up, prob_down, last_row['RSI'], 
                 last_row['SMA_200'], last_row['EMA_50'], last_row['ATR'], trend_status, 
                 acc.balance, acc.equity) 
    
    print("-" * 60, flush=True)
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')} | 💰 Price: {last_row['close']:.2f} | 🛡️ Spread: {spread_points:.1f}", flush=True)
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
perform_analysis(model, predictors)

rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
last_candle_time = rates[0]['time'] if rates is not None else None
last_training_day = datetime.now().day

print("⏳ Monitoring for next M30 candle...", flush=True)

while True:
    try:
        now = datetime.now()
        
        # SYDNEY SCHEDULE FIX: Retrain at 09:05 AM (Market Close / Data Static)
        if now.hour == 9 and now.minute == 5 and last_training_day != now.day:
            print("📅 Starting Daily Retraining (Market Close)...", flush=True)
            new_model, new_preds = train_model()
            if new_model:
                model, predictors = new_model, new_preds
                last_training_day = now.day
                print("✅ Retraining Success.", flush=True)

        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        if rates is not None and last_candle_time != rates[0]['time']:
            last_candle_time = rates[0]['time']
            # SPREAD FILTER REPLACED ROLLOVER FILTER
            perform_analysis(model, predictors)

        time.sleep(5)
        
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)
        time.sleep(10)