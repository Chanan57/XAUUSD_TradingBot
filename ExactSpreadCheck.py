import MetaTrader5 as mt5
import time

SYMBOL = "XAUUSD.a"

if not mt5.initialize():
    print("❌ MT5 Init Failed")
    quit()

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ {SYMBOL} not found")
    quit()

print(f"--- Live Spread Monitor: {SYMBOL} ---")
print("(Press Ctrl+C to stop)")

try:
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick:
            # Calculate Spread
            spread_usd = tick.ask - tick.bid
            spread_points = spread_usd * 100  # Assuming 2 decimal places
            
            print(f"Bid: {tick.bid:.2f} | Ask: {tick.ask:.2f} | Spread: {spread_points:.1f} Points (${spread_usd:.2f})")
        
        time.sleep(1) # Update every second
except KeyboardInterrupt:
    print("\nStopped.")
    mt5.shutdown()