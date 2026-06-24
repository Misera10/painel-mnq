def get_mnq_specs():
    """
    Return static specifications for the MNQ (Micro E-mini Nasdaq-100) contract.
    """
    return {
        "contract_name": "Micro E-mini Nasdaq-100",
        "ticker_prefix": "MNQ",
        "multiplier": 2.0,       # $2.00 per full index point
        "tick_size": 0.25,       # Minimum price fluctuation
        "tick_value": 0.50,      # Value of 1 tick ($2.00 * 0.25)
        "intraday_margin": 100.0, # Typical broker intraday margin per contract (e.g. NinjaTrader/AMP)
        "maintenance_margin": 2040.0 # Approximate Exchange maintenance margin (varies)
    }

def round_to_tick(value, tick_size=0.25):
    """
    Round a price or point value to the nearest tick size (default 0.25).
    """
    return round(value / tick_size) * tick_size

def calculate_position_size(account_balance, risk_percentage, stop_loss_points):
    """
    Calculate the number of MNQ contracts to trade based on account balance,
    risk tolerance percentage, and stop loss size in index points.
    """
    specs = get_mnq_specs()
    multiplier = specs["multiplier"]
    
    if stop_loss_points <= 0 or risk_percentage <= 0 or account_balance <= 0:
        return {
            "contracts_raw": 0.0,
            "contracts_rounded": 0,
            "max_risk_usd": 0.0,
            "actual_risk_usd": 0.0,
            "risk_per_contract_usd": 0.0,
            "required_intraday_margin": 0.0
        }
        
    max_risk_usd = account_balance * (risk_percentage / 100.0)
    risk_per_contract_usd = stop_loss_points * multiplier
    
    contracts_raw = max_risk_usd / risk_per_contract_usd
    contracts_rounded = int(contracts_raw)
    
    actual_risk_usd = contracts_rounded * risk_per_contract_usd
    required_intraday_margin = contracts_rounded * specs["intraday_margin"]
    
    return {
        "contracts_raw": contracts_raw,
        "contracts_rounded": contracts_rounded,
        "max_risk_usd": max_risk_usd,
        "actual_risk_usd": actual_risk_usd,
        "risk_per_contract_usd": risk_per_contract_usd,
        "required_intraday_margin": required_intraday_margin
    }

def suggest_stops_targets(current_price, atr_15m, atr_multiplier=1.5, rr_ratios=[1.5, 2.0, 3.0]):
    """
    Suggest Stop Loss and Take Profit levels based on ATR and current price.
    Calculates for both Buy (Long) and Sell (Short) trades.
    """
    if atr_15m <= 0 or current_price <= 0:
        return {}
        
    specs = get_mnq_specs()
    tick_size = specs["tick_size"]
    
    # Calculate stop loss in points and round to nearest tick
    stop_loss_points = round_to_tick(atr_15m * atr_multiplier, tick_size)
    stop_loss_usd = stop_loss_points * specs["multiplier"]
    
    suggestions = {
        "atr_15m": atr_15m,
        "stop_loss_points": stop_loss_points,
        "stop_loss_usd_per_contract": stop_loss_usd,
        "long": {
            "entry": current_price,
            "stop_loss": round_to_tick(current_price - stop_loss_points, tick_size),
            "targets": {}
        },
        "short": {
            "entry": current_price,
            "stop_loss": round_to_tick(current_price + stop_loss_points, tick_size),
            "targets": {}
        }
    }
    
    # Calculate take profit targets
    for rr in rr_ratios:
        target_points = round_to_tick(stop_loss_points * rr, tick_size)
        target_usd = target_points * specs["multiplier"]
        
        long_target = round_to_tick(current_price + target_points, tick_size)
        short_target = round_to_tick(current_price - target_points, tick_size)
        
        suggestions["long"]["targets"][f"1:{rr}"] = {
            "price": long_target,
            "points": target_points,
            "profit_usd_per_contract": target_usd
        }
        suggestions["short"]["targets"][f"1:{rr}"] = {
            "price": short_target,
            "points": target_points,
            "profit_usd_per_contract": target_usd
        }
        
    return suggestions
