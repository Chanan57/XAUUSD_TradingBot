import MetaTrader5 as mt5
from config import *
import logger

def close_all(reason="Signal"):
    """Finds any open positions for this bot's Magic Number and closes them."""
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
                logger.log_trade("CLOSE", SYMBOL, price, 0, 0, pos.volume, reason)

def open_trade(signal, price, sl, tp, volume, max_prob):
    """Executes a new Buy or Sell order and logs the exact AI confidence."""
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": volume, "magic": MAGIC_NUMBER,
        "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price, "sl": sl, "tp": tp, "comment": "V6.4 Confirmed", 
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC
    }
    res = mt5.order_send(req)
    
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"🚀 SNIPER ENTRY: {signal} @ {price}", flush=True)
        logger.log_trade(signal, SYMBOL, price, sl, tp, volume, f"Entry AI:{max_prob:.2f}")
    else:
        err = res.comment if res else "Unknown Error"
        print(f"⚠️ ORDER REJECTED BY BROKER: {err}", flush=True)
        