import MetaTrader5 as mt5
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from config import *
from data_engine import prepare_data

def train_model():
    """
    Downloads historical data and trains the Random Forest model.
    """
    print(f"\n🧠 [ORACLE] Training on {TRAINING_SIZE} candles...", flush=True)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, TRAINING_SIZE)
    if rates is None or len(rates) < 100: return None, None
    
    # Format and prepare the data using our data engine
    df = prepare_data(pd.DataFrame(rates).assign(time=lambda x: pd.to_datetime(x['time'], unit='s')))
    
    # Define what the AI is trying to predict (Target)
    future_close = df['close'].shift(-PREDICTION_HORIZON)
    future_return = (future_close - df['close']) / df['close']
    
    df['Target'] = -1
    df.loc[future_return > MIN_HORIZON_RETURN, 'Target'] = 1
    df.loc[future_return < -MIN_HORIZON_RETURN, 'Target'] = 0
    clean_df = df[df['Target'] != -1].copy()
    
    # The metrics the AI looks at to make its decision
    predictors = ['RSI', 'dist_ema50', 'ATR', 'hour', 'return_1', 'ADX']
    
    # Build and train the 200 decision trees
    clf = RandomForestClassifier(n_estimators=200, min_samples_split=20, random_state=1)
    clf.fit(clean_df[predictors], clean_df['Target'])
    
    return clf, predictors

def get_brain_reason(prob_up, prob_down, rsi, dist_ema, atr, adx):
    """Translates the raw AI probabilities into plain English for the dashboard."""
    if adx < ADX_THRESHOLD: return "Market Chopping (Low ADX)"
    
    if prob_up >= CONFIDENCE_ENTRY:
        if rsi < 40: return "Sniper Entry (Dip in Uptrend)"
        if rsi > 70: return "Overbought (Caution)"
        return "Bullish Momentum"
    elif prob_down >= CONFIDENCE_ENTRY:
        if rsi > 60: return "Sniper Entry (Rally in Downtrend)"
        if rsi < 30: return "Oversold (Caution)"
        return "Bearish Momentum"
    else:
        return "Uncertain / Waiting"