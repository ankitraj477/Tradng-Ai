"""
Shared pure simulation engine contract.
Enforces Section 4 & Section 10 (Test 11, Test 13):
- Deterministic Proposal & Fill dataclasses.
- Pure simulate_fill() with no wall-clock, no network, and no external state.
- Slippage: max(5 bps, 0.1 * order_value/ADTV * 10000 bps) capped at 50 bps.
- Rejection of orders above 2% of ADTV.
- Next trading day open execution.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, Any, Union
import math
from ..exchange_rules import round_to_tick
from .ledger import Fill


@dataclass
class Proposal:
    """Pure trade proposal generated at close of asof date."""
    sleeve: str
    symbol: str
    side: str  # "BUY" or "SELL"
    target_weight: Optional[float] = None
    qty: Optional[int] = None
    stop: Optional[float] = None
    reason: str = ""
    asof: Optional[Union[date, str]] = None


def simulate_fill(
    proposal: Proposal,
    next_bar: Dict[str, Any],
    adtv20: float,
    cost_model,
    asof_date: Optional[Union[date, str]] = None
) -> Fill:
    """
    Pure simulation fill function for both backtesting and live paper execution.
    Fills at the next trading day Open with exact slippage and statutory costs.
    """
    if proposal.qty is None or proposal.qty <= 0:
        raise ValueError(f"Proposal for {proposal.symbol} has invalid quantity: {proposal.qty}")

    open_price = float(next_bar.get("Open", next_bar.get("open", 0.0)))
    if open_price <= 0:
        raise ValueError(f"Invalid open price for {proposal.symbol}: {open_price}")

    order_value = proposal.qty * open_price

    # 1. Reject orders exceeding 2% of ADTV (Section 4)
    if adtv20 > 0 and order_value > 0.02 * adtv20:
        raise ValueError(
            f"Order rejected: order value ₹{order_value:.2f} exceeds 2% of ADTV20 (₹{0.02*adtv20:.2f})"
        )

    # 2. Slippage calculation: max(5 bps, 0.1 * order_value/ADTV * 10000 bps) capped at 50 bps
    if adtv20 > 0:
        participation = order_value / adtv20
        slippage_bps = max(5.0, 0.1 * participation * 10000.0)
    else:
        slippage_bps = 5.0

    slippage_bps = min(50.0, float(slippage_bps))
    slippage_rate = slippage_bps / 10000.0

    # 3. Fill price calculation
    side = proposal.side.upper()
    if side in ("BUY", "LONG"):
        fill_price = round_to_tick(open_price * (1.0 + slippage_rate))
    elif side in ("SELL", "SHORT"):
        fill_price = round_to_tick(open_price * (1.0 - slippage_rate))
    else:
        raise ValueError(f"Unknown proposal side: {proposal.side}")

    executed_value = proposal.qty * fill_price

    # 4. Statutory costs
    fill_date = next_bar.get("date", asof_date)
    costs = cost_model.calculate(
        value=executed_value,
        action=side,
        segment="DELIVERY",
        adtv=adtv20,
        asof=fill_date,
        qty=proposal.qty,
        include_slippage=False  # Slippage already captured in fill_price
    )

    return Fill(
        sleeve=proposal.sleeve,
        symbol=proposal.symbol,
        side=side,
        qty=proposal.qty,
        price=fill_price,
        costs=costs,
        slippage_bps=slippage_bps,
        asof=fill_date
    )
