import pandas as pd
import ta
from config import *

def prepare_data(df):
    """
    Takes raw MT5 candlestick data and calculates all technical indicators.
    Returns a clean, formatted Pandas DataFrame ready for the AI to read.
    """
    # Standardize column names
    df.columns = [x.lower() for x in df.columns]
    df = df.copy() 
    
    # Calculate Momentum & Trend Indicators
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    df['SMA_200'] = ta.trend.sma_indicator(df['close'], window=200)
    df['EMA_50'] = ta.trend.ema_indicator(df['close'], window=EMA_SECONDARY)
    df['dist_ema50'] = df['close'] - df['EMA_50']
    df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    
    # Calculate the Volatility Filter (ADX)
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    
    # Calculate Time and Returns for the AI Brain
    df['hour'] = df['time'].dt.hour
    df['return_1'] = df['close'].pct_change(1)
    df['rolling_return'] = df['close'].pct_change(PREDICTION_HORIZON)
    
    # Drop rows with incomplete data (NaN) created by moving averages
    df.dropna(inplace=True)
    
    return df