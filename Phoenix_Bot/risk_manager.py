import MetaTrader5 as mt5
from config import *

def get_lot_size(balance, risk_pct, sl_dist, sym_info):
    """
    Calculates the exact lot size for the trade.
    Returns 0.0 if the minimum lot size violates the MAX_SURVIVABLE_LOSS_USD limit.
    """
    contract_size = sym_info.trade_contract_size 
    acc_info = mt5.account_info()
    
    # 1. IRON CLAD CHECK: Is the absolute minimum trade too dangerous?
    # For XAUUSD on a USD account: 0.01 lot * 100 contract size * SL distance = Risk in USD
    min_lot_risk_usd = 0.01 * contract_size * sl_dist

    if min_lot_risk_usd > MAX_SURVIVABLE_LOSS_USD:
        return 0.0, 0.0, f"⛔ BLOCKED: Risk ${min_lot_risk_usd:.2f} > Limit ${MAX_SURVIVABLE_LOSS_USD:.2f}"

    # 2. STANDARD RISK CALCULATION
    # Balance is natively in USD, so risk is natively in USD
    risk_cash_usd = balance * risk_pct
    raw_lots = risk_cash_usd / (sl_dist * contract_size)
    
    # 3. MARGIN CHECK: Does the broker actually let us take this size?
    margin_check = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, SYMBOL, 1.0, sym_info.ask)
    max_lots = raw_lots
    if margin_check is not None: 
        max_lots = (acc_info.margin_free * 0.95) / margin_check
    
    # 4. FINAL APPROVAL
    final_lots = round(min(raw_lots, max_lots), 2)
    if final_lots < 0.01: 
        final_lots = 0.01
    
    actual_risk_usd = final_lots * contract_size * sl_dist
    return final_lots, risk_cash_usd, f"Risk: ${actual_risk_usd:.2f}"