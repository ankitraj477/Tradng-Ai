"""
Sleeve B: Trend on the Index (~20% risk budget).
Enforces Section 6 & Section 12 requirements:
- Instrument: NIFTYBEES (or Nifty 50 series for research). Long-only.
- Entry: close > highest close of the previous 55 days (excluding today) -> buy next open.
- Exit: close < lowest close of the previous 20 days (excluding today) -> sell next open.
- Size: w = clamp(sigma_target / sigma20, 0, 1) with sigma_target = 10% annualized; recomputed weekly.
- Pure decide() contract: deterministic, no wall-clock, no network.
"""

from datetime import date
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
from ..engine_v2.simulate import Proposal


def compute_sigma20(close_series: pd.Series, lookback: int = 20) -> float:
    """Compute 20-day annualized realized volatility."""
    if len(close_series) < lookback + 1:
        return 0.15  # Default 15% vol fallback
    arr = close_series.iloc[-lookback - 1:].to_numpy()
    rets = (arr[1:] - arr[:-1]) / arr[:-1]
    std = float(np.std(rets, ddof=1))
    if np.isnan(std) or std <= 1e-6:
        return 0.15
    return float(std * np.sqrt(252))


def decide(
    sleeve_cfg: Dict[str, Any],
    history_asof: Dict[str, pd.DataFrame],
    portfolio_state: Dict[str, Any],
    calendar=None,
    is_rebalance_date: bool = True
) -> List[Proposal]:
    """
    Pure decision function for Sleeve B: Index Trend Following.
    Generates deterministic Proposals for next trading day open execution.
    """
    proposals: List[Proposal] = []
    asof_date = portfolio_state.get("asof")
    equity = float(portfolio_state.get("equity", 100000.0))
    current_positions = portfolio_state.get("positions", {})  # {sym: {"qty": int, "entry_price": float}}

    target_symbol = sleeve_cfg.get("instrument", "NIFTYBEES.NS")
    entry_lookback = int(sleeve_cfg.get("entry_high_lookback", 55))
    exit_lookback = int(sleeve_cfg.get("exit_low_lookback", 20))
    sigma_target = float(sleeve_cfg.get("sigma_target", 0.10))
    vol_lookback = int(sleeve_cfg.get("vol_lookback", 20))
    min_delta_w = float(sleeve_cfg.get("min_delta_w", 0.02))

    # Resolve index dataframe from candidate keys
    df = None
    resolved_symbol = target_symbol
    for sym_key in (target_symbol, "^NSEI", "NIFTY 50", "NIFTYBEES.NS", "NIFTYBEES"):
        if sym_key in history_asof:
            df = history_asof[sym_key]
            resolved_symbol = sym_key
            break

    if df is None or len(df) < entry_lookback + 1:
        return proposals

    close_series = df["Close"]
    today_close = float(close_series.iloc[-1])

    # Check previous 55 days excluding today
    prior_55_closes = close_series.iloc[-entry_lookback - 1 : -1]
    highest_55 = float(prior_55_closes.max())

    # Check previous 20 days excluding today
    prior_20_closes = close_series.iloc[-exit_lookback - 1 : -1]
    lowest_20 = float(prior_20_closes.min())

    # Realized vol and target weight
    sigma20 = compute_sigma20(close_series, lookback=vol_lookback)
    target_weight = min(1.0, max(0.0, sigma_target / max(1e-4, sigma20)))

    # Current position in sleeve B
    pos = current_positions.get(resolved_symbol) or current_positions.get(target_symbol)
    cur_qty = int(pos.get("qty", 0)) if pos else 0
    cur_val = cur_qty * today_close
    cur_w = (cur_val / equity) if equity > 0 else 0.0

    # 1. Exit Rule: close < lowest close of previous 20 days
    if today_close < lowest_20:
        if cur_qty > 0:
            proposals.append(Proposal(
                sleeve="B",
                symbol=resolved_symbol,
                side="SELL",
                target_weight=0.0,
                qty=cur_qty,
                stop=lowest_20,
                reason=f"Trend Exit: Close {today_close:.2f} < 20d Low {lowest_20:.2f}",
                asof=asof_date
            ))
        return proposals

    # 2. Entry Rule: close > highest close of previous 55 days
    if today_close > highest_55:
        if cur_qty == 0:
            target_value = equity * target_weight
            target_qty = int(target_value / today_close)
            if target_qty > 0:
                proposals.append(Proposal(
                    sleeve="B",
                    symbol=resolved_symbol,
                    side="BUY",
                    target_weight=target_weight,
                    qty=target_qty,
                    stop=lowest_20,
                    reason=f"Trend Breakout: Close {today_close:.2f} > 55d High {highest_55:.2f} (vol={sigma20*100:.1f}%, w={target_weight:.3f})",
                    asof=asof_date
                ))
        elif is_rebalance_date and abs(target_weight - cur_w) >= min_delta_w:
            # Weekly sizing rebalance
            target_value = equity * target_weight
            target_qty = int(target_value / today_close)
            delta_qty = target_qty - cur_qty
            if delta_qty > 0:
                proposals.append(Proposal(
                    sleeve="B",
                    symbol=resolved_symbol,
                    side="BUY",
                    target_weight=target_weight,
                    qty=delta_qty,
                    stop=lowest_20,
                    reason=f"Trend Sizing Rebalance w={target_weight:.3f}",
                    asof=asof_date
                ))
            elif delta_qty < 0:
                proposals.append(Proposal(
                    sleeve="B",
                    symbol=resolved_symbol,
                    side="SELL",
                    target_weight=target_weight,
                    qty=abs(delta_qty),
                    stop=lowest_20,
                    reason=f"Trend Sizing Trim w={target_weight:.3f}",
                    asof=asof_date
                ))

    return proposals
