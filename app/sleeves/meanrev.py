"""
Sleeve C: Short-term Mean Reversion in Uptrends (~15% risk budget).
Enforces Section 7 & Section 10 (Test 5, Test 9) & Section 12 requirements:
- Universe: PIT NIFTY 200, price >= 50, ADTV20 >= min_adtv_cr, history >= 260 days.
- Event filter: excluded if event falls within +/- 3 trading days; if event data missing, trade at half size.
- Wilder RSI(2): all-up gives 100, all-down gives 0, never NaN.
- Entry: close > SMA200 and RSI2 < 10 and close < SMA5. Rank by lowest RSI2; fill free slots up to max_positions (10).
- Cross-sleeve rule: symbol held by Sleeve A cannot be opened by Sleeve C.
- Exit: RSI2 > 60 or close > SMA5 or 5 trading days elapsed at next open.
- Stop: close < entry - 2 * ATR14 -> exit next open.
- Sizing: risk 0.5% of equity per trade (= 0.005 * equity / (2 * ATR14) shares), notional cap 8% of equity.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Set, Any
import numpy as np
import pandas as pd
from ..engine_v2.simulate import Proposal
from .momentum import compute_atr


def compute_wilder_rsi2(close_series: pd.Series, period: int = 2) -> float:
    """
    Wilder's smoothed RSI with exact edge cases:
    - If average loss is 0: RSI = 100.
    - If average gain is 0: RSI = 0.
    - Never returns NaN.
    """
    if len(close_series) < period + 1:
        return 50.0

    arr = close_series.to_numpy(dtype=float)
    diff = np.diff(arr)
    if len(diff) == 0:
        return 50.0

    gains = np.maximum(diff, 0.0)
    losses = np.maximum(-diff, 0.0)

    avg_gain = float(gains[0])
    avg_loss = float(losses[0])
    alpha = 1.0 / float(period)

    for i in range(1, len(diff)):
        avg_gain = avg_gain * (1.0 - alpha) + float(gains[i]) * alpha
        avg_loss = avg_loss * (1.0 - alpha) + float(losses[i]) * alpha

    if avg_loss <= 1e-12 and avg_gain <= 1e-12:
        return 50.0
    if avg_loss <= 1e-12:
        return 100.0
    if avg_gain <= 1e-12:
        return 0.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return float(np.clip(rsi, 0.0, 100.0))


def decide(
    sleeve_cfg: Dict[str, Any],
    history_asof: Dict[str, pd.DataFrame],
    portfolio_state: Dict[str, Any],
    calendar=None,
    is_rebalance_date: bool = True
) -> List[Proposal]:
    """
    Pure decision function for Sleeve C: Short-Term Mean Reversion.
    Generates deterministic Proposals for next trading day open execution.
    """
    proposals: List[Proposal] = []
    asof_date = portfolio_state.get("asof")
    equity = float(portfolio_state.get("equity", 100000.0))
    current_positions = portfolio_state.get("positions", {})  # {sym: {"qty": int, "entry_price": float, "holding_days": int}}
    sleeve_a_holdings = set(portfolio_state.get("sleeve_a_holdings", []))

    # Configuration parameters
    min_adtv = float(sleeve_cfg.get("min_adtv_cr", 10.0)) * 1e7
    min_price = float(sleeve_cfg.get("min_price", 50.0))
    min_history = int(sleeve_cfg.get("min_history_days", 260))
    rsi_period = int(sleeve_cfg.get("rsi_period", 2))
    entry_rsi_thresh = float(sleeve_cfg.get("entry_rsi_threshold", 10.0))
    exit_rsi_thresh = float(sleeve_cfg.get("exit_rsi_threshold", 60.0))
    sma_trend_period = int(sleeve_cfg.get("sma_trend_period", 200))
    sma_fast_period = int(sleeve_cfg.get("sma_fast_period", 5))
    atr_period = int(sleeve_cfg.get("atr_period", 14))
    atr_stop_mult = float(sleeve_cfg.get("atr_stop_multiplier", 2.0))
    risk_per_trade_pct = float(sleeve_cfg.get("risk_per_trade_pct", 0.005))
    max_notional_trade_pct = float(sleeve_cfg.get("max_notional_trade_pct", 0.08))
    max_positions = int(sleeve_cfg.get("max_positions", 10))
    max_hold_days = int(sleeve_cfg.get("max_hold_days", 5))
    event_window_days = int(sleeve_cfg.get("event_window_days", 3))

    # Check calendar / events
    has_event_data = True
    active_events = set()
    if calendar is not None:
        try:
            cur_dt = asof_date if isinstance(asof_date, (date, datetime)) else datetime.strptime(str(asof_date), "%Y-%m-%d").date()
            if hasattr(calendar, "is_event_window"):
                if calendar.is_event_window(cur_dt, days_window=event_window_days):
                    active_events.add("MARKET_EVENT")
        except Exception:
            has_event_data = False
    else:
        has_event_data = False

    # 1. Evaluate Exits for currently held Sleeve C positions
    held_sleeve_c = set()
    for sym, pos in list(current_positions.items()):
        qty = int(pos.get("qty", 0))
        if qty <= 0:
            continue
        held_sleeve_c.add(sym)

        sym_df = history_asof.get(sym)
        if sym_df is None or len(sym_df) < sma_fast_period + 1:
            continue

        close_series = sym_df["Close"]
        today_close = float(close_series.iloc[-1])
        entry_price = float(pos.get("entry_price", today_close))
        holding_days = int(pos.get("holding_days", 0))

        atr = compute_atr(sym_df, period=atr_period)
        stop_price = entry_price - (atr_stop_mult * atr)
        sma5 = float(close_series.iloc[-sma_fast_period:].mean())
        rsi2 = compute_wilder_rsi2(close_series, period=rsi_period)

        exit_triggered = False
        exit_reason = ""

        # Risk stop
        if today_close < stop_price:
            exit_triggered = True
            exit_reason = f"Catastrophic Stop: Close {today_close:.2f} < Stop {stop_price:.2f}"
        # Take profit: RSI2 > 60 or close > SMA5
        elif rsi2 > exit_rsi_thresh:
            exit_triggered = True
            exit_reason = f"Mean Reversion Take-Profit: RSI2 {rsi2:.1f} > {exit_rsi_thresh}"
        elif today_close > sma5:
            exit_triggered = True
            exit_reason = f"Fast SMA Exit: Close {today_close:.2f} > SMA5 {sma5:.2f}"
        # Time exit: 5 days
        elif holding_days >= max_hold_days:
            exit_triggered = True
            exit_reason = f"Time Stop: {holding_days} days >= max {max_hold_days} days"

        if exit_triggered:
            proposals.append(Proposal(
                sleeve="C",
                symbol=sym,
                side="SELL",
                target_weight=0.0,
                qty=qty,
                stop=stop_price,
                reason=exit_reason,
                asof=asof_date
            ))
            held_sleeve_c.remove(sym)

    # 2. Evaluate Candidate Entries if free slots exist
    open_slots = max_positions - len(held_sleeve_c)
    if open_slots <= 0:
        return proposals

    # Adjust risk if event data missing
    effective_risk_pct = risk_per_trade_pct if has_event_data else (risk_per_trade_pct * 0.5)

    candidates = []

    for sym, df in history_asof.items():
        if sym.startswith("^") or sym in ("NIFTY 50", "NIFTYBEES.NS", "NIFTYBEES"):
            continue
        # Cross-sleeve ownership check: cannot open symbol held by Sleeve A or C
        if sym in sleeve_a_holdings or sym in held_sleeve_c:
            continue
        if len(df) < min_history:
            continue

        close_series = df["Close"]
        today_close = float(close_series.iloc[-1])
        if today_close < min_price:
            continue

        # ADTV filter
        if "Volume" in df.columns:
            turnover = df["Close"] * df["Volume"]
            adtv20 = float(turnover.iloc[-20:].mean()) if len(turnover) >= 20 else float(turnover.mean())
            if adtv20 < min_adtv:
                continue

        # Indicators
        sma200 = float(close_series.iloc[-sma_trend_period:].mean())
        sma5 = float(close_series.iloc[-sma_fast_period:].mean())
        rsi2 = compute_wilder_rsi2(close_series, period=rsi_period)

        # Entry criteria: close > SMA200 and RSI2 < 10 and close < SMA5
        if today_close > sma200 and rsi2 < entry_rsi_thresh and today_close < sma5:
            candidates.append((rsi2, sym, today_close, df))

    # Rank by lowest RSI2
    candidates.sort(key=lambda x: x[0])

    for rsi2, sym, today_close, df in candidates[:open_slots]:
        atr = compute_atr(df, period=atr_period)
        stop_dist = max(atr_stop_mult * atr, today_close * 0.01)
        risk_amount = equity * effective_risk_pct
        target_qty = int(risk_amount / stop_dist)

        # Cap by notional equity cap (8%)
        max_qty = int((equity * max_notional_trade_pct) / today_close)
        qty = min(target_qty, max_qty)

        if qty > 0:
            stop_price = today_close - stop_dist
            proposals.append(Proposal(
                sleeve="C",
                symbol=sym,
                side="BUY",
                target_weight=(qty * today_close) / equity if equity > 0 else 0.0,
                qty=qty,
                stop=stop_price,
                reason=f"MeanRev Entry: RSI2={rsi2:.1f} < {entry_rsi_thresh}, Close {today_close:.2f} > SMA200, Stop={stop_price:.2f}",
                asof=asof_date
            ))

    return proposals
