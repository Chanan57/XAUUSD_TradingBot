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
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier

# --- 1. CONFIGURATION (STABILIZATION MODE) ---
SYMBOL = "XAUUSD.a"       # Gold (Retail)
TIMEFRAME = mt5.TIMEFRAME_M30
RISK_PERCENT = 0.02       # Standard 2% Risk
MAGIC_NUMBER = 888000     # V5.8 Magic Number
MAX_SPREAD_NORMAL = 35    # Standard Spread Limit
MAX_SPREAD_HIGH_CONF = 60 # High Confidence Limit

# --- HYSTERESIS & FILTERS ---
CONFIDENCE_ENTRY = 0.55    
CONFIDENCE_REVERSAL = 0.60 
HIGH_CONFIDENCE_LVL = 0.65 
EMA_SECONDARY = 50         
TRAINING_SIZE = 15000      

# --- GLOBAL STATE ---
ai_state = {
    "prob_up": 0.0,
    "prob_down": 0.0,
    "trend": "INITIALIZING...",
    "sma": 0.0,
    "ema": 0.0,
    "rsi": 0.0,
    "atr": 0.0
}

# --- 2. STARTUP ---
if not mt5.initialize():
    print("❌ MT5 Startup Failed.", flush=True)
    sys.exit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select {SYMBOL}.", flush=True)
    sys.exit()

# --- 3. LOGGING & DISPLAY ---
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

def log_analysis(time_stamp, price, prob_up, prob_down, rsi, sma, ema, atr, trend_status, balance, equity, spread):
    filename = "Gold_Strategy_Analysis_V5.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Date", "Time", "Price", "AI_UP", "AI_DOWN", "RSI", "SMA_200", "EMA_50", "ATR", "Trend_Status", "Balance", "Equity", "Spread"])
        
        d_str = time_stamp.strftime("%Y-%m-%d")
        t_str = time_stamp.strftime("%H:%M:%S")
        writer.writerow([d_str, t_str, price, f"{prob_up:.2f}", f"{prob_down:.2f}", 
                         f"{rsi:.1f}", f"{sma:.2f}", f"{ema:.2f}", f"{atr:.2f}", trend_status, f"{balance:.2f}", f"{equity:.2f}", f"{spread:.1f}"])

def print_dashboard():
    # Use Frameless Design to prevent alignment errors with emojis
    tick = mt5.symbol_info_tick(SYMBOL)
    acc = mt5.account_info()
    if tick is None or acc is None: return

    symbol_info = mt5.symbol_info(SYMBOL)
    spread = (tick.ask - tick.bid) / symbol_info.point
    
    current_conf = max(ai_state['prob_up'], ai_state['prob_down'])
    allowed = MAX_SPREAD_HIGH_CONF if current_conf >= HIGH_CONFIDENCE_LVL else MAX_SPREAD_NORMAL

    # Get Trade Status
    positions = mt5.positions_get(symbol=SYMBOL)
    trade_status = "[ NO TRADE ]"
    trade_details = "WAITING FOR SIGNAL..."
    
    if positions:
        pos = positions[0]
        pnl = pos.profit
        direction = "🟢 BUY" if pos.type == mt5.ORDER_TYPE_BUY else "🔴 SELL"
        trade_status = f"{direction} ACTIVE"
        trade_details = f"Entry: {pos.price_open:.2f} | PnL: ${pnl:.2f}"

    print(f"\n", flush=True)
    print("="*65, flush=True)
    print(f" 🚀 V5.8 TITANIUM (M30)            ⏰ {datetime.now().strftime('%H:%M:%S')}", flush=True)
    print("="*65, flush=True)
    print(f" 💰 PRICE:   {tick.ask:<10.2f}    🛡️ SPREAD: {spread:<5.1f} (Max: {allowed})", flush=True)
    print(f" 💵 BALANCE: ${acc.balance:<10.2f}    📉 EQUITY: ${acc.equity:<10.2f}", flush=True)
    print("-" * 65, flush=True)
    print(f" 🤖 STATUS: {trade_status}", flush=True)
    print(f"    {trade_details}", flush=True)
    print("-" * 65, flush=True)
    print(f" 🧠 AI BRAIN:             🌊 TREND:", flush=True)
    print(f"    🟢 UP:   {ai_state['prob_up']:<10.1%}       {ai_state['trend']}", flush=True)
    print(f"    🔴 DOWN: {ai_state['prob_down']:<10.1%}", flush=True)
    print("-" * 65, flush=True)
    print(f" 📊 TECHNICALS:", flush=True)
    print(f"    SMA(200): {ai_state['sma']:<10.2f}     EMA(50): {ai_state['ema']:<10.2f}", flush=True)
    print(f"    RSI:      {ai_state['rsi']:<10.1f}     ATR:     {ai_state['atr']:<10.2f}", flush=True)
    print("="*65, flush=True)

# --- 4. DATA & LOGIC ---
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

def get_lot_size(balance, risk_pct, sl_dist, sym_info):
    risk_cash = balance * risk_pct
    contract_size = sym_info.trade_contract_size 
    if sl_dist == 0: sl_dist = 1.0 
    
    # SAFETY: 3x Risk Limit (Stabilization Mode)
    min_trade_risk = 0.01 * contract_size * sl_dist
    if min_trade_risk > (risk_cash * 3.0):
        print(f"⚠️ SAFETY: Volatility too high. Skipped.", flush=True)
        return 0.0, risk_cash

    raw_lots = risk_cash / (sl_dist * contract_size)
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
                       "type": type_op, "price": price, "magic": MAGIC_NUMBER, "comment": f"V5.8:{reason}",
                       "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                mt5.order_send(req)
                print(f"🔄 Closing {pos.ticket} ({reason})", flush=True)

def train_model():
    print(f"🧠 Training AI...", flush=True)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, TRAINING_SIZE)
    if rates is None or len(rates) < 100: return None, None
    df = prepare_data(pd.DataFrame(rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)
    predictors = ['RSI', 'dist_ema50', 'ATR', 'hour', 'return_1']
    clf = RandomForestClassifier(n_estimators=200, min_samples_split=20, random_state=1)
    clf.fit(df[predictors], df['Target'])
    return clf, predictors

def perform_analysis(model, predictors):
    tick = mt5.symbol_info_tick(SYMBOL)
    symbol_info = mt5.symbol_info(SYMBOL)
    if tick is None or symbol_info is None: return

    spread_points = (tick.ask - tick.bid) / symbol_info.point
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
    
    current_confidence = max(prob_up, prob_down)
    allowed_spread = MAX_SPREAD_HIGH_CONF if current_confidence >= HIGH_CONFIDENCE_LVL else MAX_SPREAD_NORMAL

    # UPDATE GLOBAL AI STATE
    global ai_state
    if trend_up: t_status = "✅ BULLISH"
    elif trend_down: t_status = "✅ BEARISH"
    else: t_status = "⚠️ MIXED"

    ai_state.update({
        "prob_up": prob_up,
        "prob_down": prob_down,
        "trend": t_status,
        "sma": last_row['SMA_200'],
        "ema": last_row['EMA_50'],
        "rsi": last_row['RSI'],
        "atr": last_row['ATR']
    })

    # LOGIC AND EXECUTION
    pos_obj = mt5.positions_get(symbol=SYMBOL)
    current_pos = "BUY" if (pos_obj and pos_obj[0].type == mt5.ORDER_TYPE_BUY) else "SELL" if pos_obj else None
    
    signal = None
    if current_pos is None:
        if prob_up > CONFIDENCE_ENTRY and trend_up: signal = "BUY"
        elif prob_down > CONFIDENCE_ENTRY and trend_down: signal = "SELL"
    elif current_pos == "BUY" and prob_down > CONFIDENCE_REVERSAL: signal = "SELL"
    elif current_pos == "SELL" and prob_up > CONFIDENCE_REVERSAL: signal = "BUY"

    if signal and signal != current_pos:
        if spread_points > allowed_spread:
             print(f"🛑 Skipped: Spread {spread_points:.1f} > {allowed_spread:.1f}", flush=True)
        else:
            if (signal == "BUY" and trend_up) or (signal == "SELL" and trend_down):
                close_all("SignalFlip")
                sl_d = max(1.2 * last_row['ATR'], 0.50)
                vol, cash = get_lot_size(acc.balance, RISK_PERCENT, sl_d, symbol_info)
                if vol > 0:
                    p = tick.ask if signal == "BUY" else tick.bid
                    sl = p - sl_d if signal == "BUY" else p + sl_d
                    tp = p + (4.0 * sl_d) if signal == "BUY" else p - (4.0 * sl_d)
                    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": vol, "magic": MAGIC_NUMBER,
                           "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
                           "price": p, "sl": sl, "tp": tp, "comment": "AI V5.8 Vis", 
                           "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
                    mt5.order_send(req)
                    log_trade(signal, SYMBOL, p, sl, tp, vol, f"V5.8 Entry AI:{current_confidence:.2f}")

    # LOG ANALYSIS TO CSV
    log_analysis(datetime.now(), last_row['close'], prob_up, prob_down, last_row['RSI'], 
                 last_row['SMA_200'], last_row['EMA_50'], last_row['ATR'], t_status, 
                 acc.balance, acc.equity, spread_points) 
    
    # PRINT DASHBOARD (Once per 30 mins)
    print_dashboard()

# --- 6. RUN ---
model, predictors = train_model()
if model is None: sys.exit()
print("✅ V5.8 Visual ACTIVE.", flush=True)
perform_analysis(model, predictors)

rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
last_candle_time = rates[0]['time'] if rates is not None else None
last_training_day = datetime.now().day

print("⏳ Monitoring for next M30 candle...", flush=True)

# MAIN LOOP: Updates Dashboard Only When Candle Closes
while True:
    try:
        now = datetime.now()
        
        # 1. RETRAIN (Daily at 09:05)
        if now.hour == 9 and now.minute == 5 and last_training_day != now.day:
            new_model, new_preds = train_model()
            if new_model:
                model, predictors = new_model, new_preds
                last_training_day = now.day

        # 2. CHECK FOR NEW CANDLE (Run AI)
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        if rates is not None and last_candle_time != rates[0]['time']:
            last_candle_time = rates[0]['time']
            perform_analysis(model, predictors)

        time.sleep(5) 
        
    except Exception as e:
        print(f"⚠️ Error: {e}", flush=True)
        time.sleep(10)