import sys
import os
import time
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5

# --- DIRECTORY FIX ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import your exact live strategy parameters
from config import *
import data_engine
import ai_oracle

# --- VISUALIZATION IMPORTS ---
try:
    import plotly.graph_objects as go
    import webbrowser
    VISUALS_ENABLED = True
except ImportError:
    VISUALS_ENABLED = False
    print("⚠️ Plotly not found. Visual chart will be skipped. Run 'pip install plotly' to enable.")

def run_backtest():
    print("🚀 INITIALIZING PHOENIX V6.4 EXACT-MATCH BACKTESTER...", flush=True)
    if not mt5.initialize():
        print("❌ MT5 Startup Failed."); sys.exit()

    # 1. TRAIN THE AI ORACLE (Using your exact live settings)
    model, predictors = ai_oracle.train_model()
    if model is None: 
        print("❌ AI Training Failed."); sys.exit()

    # 2. FETCH HISTORICAL DATA
    start_date = datetime(2026, 1, 29)
    end_date = datetime.now()
    
    print(f"📥 Fetching {SYMBOL} from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...", flush=True)
    rates = mt5.copy_rates_range(SYMBOL, TIMEFRAME, start_date, end_date)
    if rates is None or len(rates) == 0:
        print("❌ Failed to fetch historical data."); sys.exit()

    # 3. PROCESS DATA THROUGH YOUR ENGINE
    raw_df = pd.DataFrame(rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s'))
    df = data_engine.prepare_data(raw_df)
    
    # 4. SIMULATION VARIABLES 
    starting_balance = 327.04
    balance = starting_balance
    peak_balance = starting_balance
    
    in_trade = False
    trade_type = None
    entry_price = 0.0
    sl = 0.0
    tp = 0.0
    current_lot_size = 0.0
    contract_size = 100
    
    # Advanced Metrics
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    total_commissions = 0.0
    buy_trades = 0
    sell_trades = 0
    max_dd_usd = 0.0

    # --- VISUAL TRACKING ARRAYS ---
    buy_times, buy_prices = [], []
    sell_times, sell_prices = [], []
    exit_times, exit_prices, exit_hover_text = [], [], []

    print(f"\n📈 STARTING BALANCE: ${balance:.2f} USD\n" + "="*65)

    # 5. THE TICK-BY-TICK LOOP
    for i in range(len(df) - 1):
        row = df.iloc[i]
        next_row = df.iloc[i+1]
        
        price = row['close']
        sma, ema, adx, rsi, atr = row['SMA_200'], row['EMA_50'], row['ADX'], row['RSI'], row['ATR']
        historical_spread = row['spread'] 
        
        trend_up = (price > sma) and (price > ema)
        trend_down = (price < sma) and (price < ema)

        # --- MANAGING AN OPEN TRADE ---
        if in_trade:
            prob_up = model.predict_proba(pd.DataFrame([row[predictors]]))[0][1]
            prob_down = 1 - prob_up
            
            reversal_exit = False
            if trade_type == "BUY" and prob_down > CONFIDENCE_REVERSAL and price < ema:
                reversal_exit = True
            elif trade_type == "SELL" and prob_up > CONFIDENCE_REVERSAL and price > ema:
                reversal_exit = True

            high, low = next_row['high'], next_row['low']
            closed = False
            gross_pnl = 0.0
            close_reason = ""
            actual_exit_price = 0.0
            
            if trade_type == "BUY":
                if low <= sl:
                    gross_pnl = (sl - entry_price) * current_lot_size * contract_size
                    closed, close_reason, actual_exit_price = True, "🛑 Hit SL", sl
                elif high >= tp:
                    gross_pnl = (tp - entry_price) * current_lot_size * contract_size
                    closed, close_reason, actual_exit_price = True, "🎯 Hit TP", tp
                elif reversal_exit:
                    gross_pnl = (price - entry_price) * current_lot_size * contract_size
                    closed, close_reason, actual_exit_price = True, "🔄 AI Reversal", price
                    
            elif trade_type == "SELL":
                if high >= sl:
                    gross_pnl = (entry_price - sl) * current_lot_size * contract_size
                    closed, close_reason, actual_exit_price = True, "🛑 Hit SL", sl
                elif low <= tp:
                    gross_pnl = (entry_price - tp) * current_lot_size * contract_size
                    closed, close_reason, actual_exit_price = True, "🎯 Hit TP", tp
                elif reversal_exit:
                    gross_pnl = (entry_price - price) * current_lot_size * contract_size
                    closed, close_reason, actual_exit_price = True, "🔄 AI Reversal", price
            
            if closed:
                commission_fee = current_lot_size * 7.00
                net_pnl = gross_pnl - commission_fee
                total_commissions += commission_fee
                balance += net_pnl
                
                if net_pnl > 0:
                    wins += 1; gross_profit += net_pnl
                else:
                    losses += 1; gross_loss += abs(net_pnl)
                
                if balance > peak_balance: peak_balance = balance
                else: max_dd_usd = max(max_dd_usd, peak_balance - balance)
                
                print(f"[{row['time']}] CLOSED {trade_type} ({current_lot_size} lots): {close_reason} | Net PnL: ${net_pnl:+.2f} | Bal: ${balance:.2f}")
                
                # Record visual exit data
                exit_times.append(row['time'])
                exit_prices.append(actual_exit_price)
                exit_hover_text.append(f"{trade_type} CLOSED<br>{close_reason}<br>Net PnL: ${net_pnl:+.2f}")
                
                in_trade = False
                continue

        # --- LOOKING FOR A NEW ENTRY ---
        if not in_trade:
            if adx < ADX_THRESHOLD:
                continue
                
            prob_up = model.predict_proba(pd.DataFrame([row[predictors]]))[0][1]
            prob_down = 1 - prob_up
            max_prob = max(prob_up, prob_down)

            allowed_spread = MAX_SPREAD_HIGH_CONF if max_prob >= HIGH_CONFIDENCE_LVL else MAX_SPREAD_NORMAL
            if historical_spread > allowed_spread:
                continue

            signal = None
            if prob_up > CONFIDENCE_ENTRY and trend_up and rsi < 70: signal = "BUY"
            elif prob_down > CONFIDENCE_ENTRY and trend_down and rsi > 30: signal = "SELL"
                
            if signal:
                sl_dist = max(1.2 * atr, 0.50)
                
                min_lot_risk_usd = 0.01 * contract_size * sl_dist
                if min_lot_risk_usd > MAX_SURVIVABLE_LOSS_USD:
                    continue 
                
                risk_cash_usd = balance * RISK_PERCENT
                raw_lots = risk_cash_usd / (sl_dist * contract_size)
                final_lots = round(raw_lots, 2)
                if final_lots < 0.01: final_lots = 0.01
                
                current_lot_size = final_lots
                trade_type = signal
                entry_price = price
                sl = entry_price - sl_dist if signal == "BUY" else entry_price + sl_dist
                tp = entry_price + (4.0 * sl_dist) if signal == "BUY" else entry_price - (4.0 * sl_dist)
                in_trade = True
                
                if signal == "BUY": 
                    buy_trades += 1
                    buy_times.append(row['time'])
                    buy_prices.append(entry_price)
                else: 
                    sell_trades += 1
                    sell_times.append(row['time'])
                    sell_prices.append(entry_price)
                
                actual_risk_usd = current_lot_size * contract_size * sl_dist
                print(f"[{row['time']}] 🚀 OPEN {trade_type} @ {entry_price:.2f} | Risk: ${actual_risk_usd:.2f} | Lots: {current_lot_size}")

    # 6. FINAL REPORT CALCULATION
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
    net_profit = balance - starting_balance

    print("\n" + "="*65)
    print("📊 PHOENIX V6.4 EXACT PARAMETER BACKTEST")
    print("="*65)
    print(f"Timeframe        : Jan 29, 2026 -> {end_date.strftime('%b %d, %Y')}")
    print(f"Starting Balance : ${starting_balance:.2f} USD")
    print(f"Final Balance    : ${balance:.2f} USD")
    print(f"Net Profit       : ${net_profit:+.2f} USD")
    print(f"Total Broker Fees: ${total_commissions:.2f} USD")
    print("-" * 65)
    print(f"Total Trades     : {total_trades} ({buy_trades} Buys | {sell_trades} Sells)")
    print(f"Win Rate         : {win_rate:.1f}% ({wins} Wins | {losses} Losses)")
    print(f"Profit Factor    : {profit_factor:.2f}")
    print(f"Max Drawdown     : ${max_dd_usd:.2f} ({(max_dd_usd/peak_balance*100):.1f}%)" if peak_balance > 0 else "Max Drawdown     : N/A")
    print("="*65)

    # 7. GENERATE INTERACTIVE VISUAL CHART
    if VISUALS_ENABLED:
        print("\n📈 Generating Interactive HTML Chart...", flush=True)
        fig = go.Figure()

        # Add Candlesticks
        fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='XAUUSD'))
        
        # Add Moving Averages
        fig.add_trace(go.Scatter(x=df['time'], y=df['SMA_200'], line=dict(color='yellow', width=1.5), name='200 SMA'))
        fig.add_trace(go.Scatter(x=df['time'], y=df['EMA_50'], line=dict(color='cyan', width=1.5), name='50 EMA'))

        # Add BUY markers
        fig.add_trace(go.Scatter(x=buy_times, y=buy_prices, mode='markers', 
                                 marker=dict(symbol='triangle-up', color='lime', size=14, line=dict(color='black', width=1)), 
                                 name='BUY Entry'))
        
        # Add SELL markers
        fig.add_trace(go.Scatter(x=sell_times, y=sell_prices, mode='markers', 
                                 marker=dict(symbol='triangle-down', color='red', size=14, line=dict(color='black', width=1)), 
                                 name='SELL Entry'))

        # Add EXIT markers with Hover Text
        fig.add_trace(go.Scatter(x=exit_times, y=exit_prices, mode='markers', 
                                 marker=dict(symbol='x', color='white', size=10, line=dict(color='black', width=1)), 
                                 name='TRADE EXIT', hovertext=exit_hover_text, hoverinfo="text"))

        # Configure dark institutional layout
        fig.update_layout(
            title="Phoenix V6.4 Quantitative Backtest Visualizer",
            yaxis_title="XAUUSD Price",
            template='plotly_dark',
            xaxis_rangeslider_visible=False,
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )

        # Save and open in browser
        chart_file = os.path.join(os.path.dirname(__file__), "backtest_chart.html")
        fig.write_html(chart_file)
        webbrowser.open(f"file://{chart_file}")
        print(f"✅ Chart opened in your web browser: {chart_file}")

if __name__ == "__main__":
    run_backtest()