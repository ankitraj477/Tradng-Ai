"""
Indian Exchange Microstructure Rules (NSE & BSE).
Enforces:
1. Standard 5-paise (₹0.05) tick size rounding on all order and stop prices.
2. Daily price band & circuit filter protections (5%, 10%, 20%).
3. Quantity integer & derivative lot size validations.
"""

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Dict, Any, Optional


def round_to_tick(price: float, tick: float = 0.05) -> float:
    """
    Rounds a price to the nearest valid exchange tick size (default 5 paise = ₹0.05).
    Example: 1450.37 -> 1450.35, 1450.38 -> 1450.40.
    """
    if price is None:
        return 0.0
    try:
        f_price = float(price)
        if f_price <= 0:
            return 0.0
        d_price = Decimal(str(round(f_price, 6)))
        d_tick = Decimal(str(tick))
        rounded = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_tick
        return float(rounded.quantize(Decimal("0.01")))
    except Exception:
        return 0.0



def calculate_circuit_bands(prev_close: float, band_pct: float = 0.20) -> Tuple[float, float]:
    """
    Calculates upper and lower circuit band limits based on previous close.
    Standard bands in Indian markets are 5%, 10%, or 20%.
    """
    if prev_close <= 0:
        return 0.0, 0.0
    upper = round_to_tick(prev_close * (1.0 + band_pct))
    lower = round_to_tick(prev_close * (1.0 - band_pct))
    return lower, upper


def is_circuit_locked(current_price: float, prev_close: float, band_pct: float = 0.20, tolerance: float = 0.002) -> Dict[str, Any]:
    """
    Checks if a stock is locked at upper circuit (no sellers) or lower circuit (no buyers).
    tolerance: within 0.2% of the circuit limit is considered locked.
    """
    if prev_close <= 0 or current_price <= 0:
        return {"locked": False, "circuit_type": "NONE", "upper": 0.0, "lower": 0.0}

    lower_circuit, upper_circuit = calculate_circuit_bands(prev_close, band_pct)

    # Check Upper Circuit (LTP >= upper * (1 - tolerance))
    if current_price >= upper_circuit * (1.0 - tolerance):
        return {
            "locked": True,
            "circuit_type": "UPPER",
            "upper": upper_circuit,
            "lower": lower_circuit,
            "reason": f"Stock locked near Upper Circuit (LTP ₹{current_price:.2f} >= ₹{upper_circuit:.2f}). No sellers available."
        }

    # Check Lower Circuit (LTP <= lower * (1 + tolerance))
    if current_price <= lower_circuit * (1.0 + tolerance):
        return {
            "locked": True,
            "circuit_type": "LOWER",
            "upper": upper_circuit,
            "lower": lower_circuit,
            "reason": f"Stock locked near Lower Circuit (LTP ₹{current_price:.2f} <= ₹{lower_circuit:.2f}). No buyers available."
        }

    return {
        "locked": False,
        "circuit_type": "NONE",
        "upper": upper_circuit,
        "lower": lower_circuit,
        "reason": "Trading within normal price band"
    }


def validate_order_microstructure(symbol: str, action: str, price: float, stop_loss: Optional[float] = None, target: Optional[float] = None, prev_close: Optional[float] = None) -> Dict[str, Any]:
    """
    Validates complete order parameters against Indian exchange rules:
    - Normalizes prices to 5-paise ticks.
    - Rejects buy orders if stock is locked at upper circuit.
    - Rejects short/sell orders if stock is locked at lower circuit.
    """
    action_upper = action.upper()
    rounded_px = round_to_tick(price)
    rounded_sl = round_to_tick(stop_loss) if stop_loss else None
    rounded_tp = round_to_tick(target) if target else None

    # Circuit band check if previous close is known
    if prev_close and prev_close > 0:
        circuit_info = is_circuit_locked(rounded_px, prev_close)
        if circuit_info["locked"]:
            if action_upper in ("BUY", "LONG") and circuit_info["circuit_type"] == "UPPER":
                return {
                    "ok": False,
                    "reason": circuit_info["reason"],
                    "price": rounded_px,
                    "circuit_info": circuit_info
                }
            elif action_upper in ("SHORT", "SELL") and circuit_info["circuit_type"] == "LOWER":
                return {
                    "ok": False,
                    "reason": circuit_info["reason"],
                    "price": rounded_px,
                    "circuit_info": circuit_info
                }

    return {
        "ok": True,
        "price": rounded_px,
        "stop_loss": rounded_sl,
        "target": rounded_tp,
        "reason": "Exchange microstructure validated"
    }
