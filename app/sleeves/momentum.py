"""
Sleeve A: Cross-Sectional Momentum (~40% risk budget).
Enforces Section 5, Section 10 (Test 6) & Section 12 requirements:
- PIT NIFTY 200 universe eligibility: ADTV20 >= min_adtv_cr, price >= 50, history >= 260 days.
- Score: MOM = (P[t-21] / P[t-252] - 1) / sigma252.
- Selection: Top N=20 with hysteresis rank buffer keep_rank=30.
- Inverse volatility weights w_i proportional to 1/sigma126_i, capped at 8%, normalized to sum(w) = E.
- Regime exposure E = 1.0 if Nifty 50 >= SMA200 else 0.5 (bear_exposure).
- Skip trades with |delta w| < 1%.
- Daily close below (highest_close - 2.5 * ATR20) -> exit next open.
- Pure decide() contract: no wall-clock, no network, strictly deterministic.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Set, Any, Union
import numpy as np
import pandas as pd
from ..engine_v2.simulate import Proposal


def compute_momentum_score(close_series: pd.Series, lookback: int = 252, skip_recent: int = 21) -> float:
    """
    Compute 12-1 month cross-sectional momentum score normalized by annualized volatility:
    MOM = (P[t-skip_recent] / P[t-lookback] - 1.0) / sigma252
    """
    if len(close_series) < lookback:
        return -999999.0

    arr = close_series.iloc[-lookback - 1:].to_numpy()
    p_t_skip = float(arr[-skip_recent])
    p_t_lookback = float(arr[-lookback])

    if p_t_lookback <= 0:
        return -999999.0

    ret252 = (arr[1:] - arr[:-1]) / arr[:-1]
    std = float(np.std(ret252, ddof=1))
    if np.isnan(std) or std <= 1e-6:
        return -999999.0

    sigma252 = std * np.sqrt(252)
    mom_return = (p_t_skip / p_t_lookback) - 1.0
    return float(mom_return / sigma252)


def compute_annualized_vol(close_series: pd.Series, lookback: int = 126) -> float:
    """Compute annualized volatility over lookback daily returns."""
    if len(close_series) < lookback + 1:
        return 0.30  # Default 30% vol fallback
    arr = close_series.iloc[-lookback - 1:].to_numpy()
    ret = (arr[1:] - arr[:-1]) / arr[:-1]
    std = float(np.std(ret, ddof=1))
    if np.isnan(std) or std <= 1e-6:
        return 0.30
    return float(std * np.sqrt(252))


def compute_atr(df: pd.DataFrame, period: int = 20) -> float:
    """Compute Average True Range (ATR) over period bars."""
    if len(df) < period + 1:
        return float(df["Close"].iloc[-1] * 0.02)  # Default 2% ATR fallback
    h = df["High"].iloc[-period - 1:].to_numpy()
    l = df["Low"].iloc[-period - 1:].to_numpy()
    c = df["Close"].iloc[-period - 1:].to_numpy()

    tr1 = h[1:] - l[1:]
    tr2 = np.abs(h[1:] - c[:-1])
    tr3 = np.abs(l[1:] - c[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = float(np.mean(tr))
    return atr if not np.isnan(atr) and atr > 0 else float(c[-1] * 0.02)


def compute_capped_weights(
    vols: Dict[str, float],
    cap: float = 0.08,
    target_sum: float = 1.0
) -> Dict[str, float]:
    """
    Inverse-volatility weighting with strict 8% single-stock cap
    and iterative reallocation summing to target_sum (E).
    """
    if not vols or target_sum <= 0:
        return {}

    symbols = list(vols.keys())
    n = len(symbols)
    if n == 0:
        return {}

    # If equal cap * n < target_sum, clamp target_sum to maximum achievable
    effective_target = min(target_sum, cap * n)

    inv_vols = {s: 1.0 / max(1e-4, vols[s]) for s in symbols}
    weights = {}
    uncapped = set(symbols)
    remaining_target = effective_target

    # Iterative capping and reallocation
    for _ in range(10):
        if not uncapped:
            break
        sum_uncapped = sum(inv_vols[s] for s in uncapped)
        if sum_uncapped <= 0:
            for s in uncapped:
                weights[s] = remaining_target / len(uncapped)
            break

        newly_capped = set()
        for s in uncapped:
            trial_w = (inv_vols[s] / sum_uncapped) * remaining_target
            if trial_w >= cap:
                weights[s] = cap
                newly_capped.add(s)

        if not newly_capped:
            for s in uncapped:
                weights[s] = (inv_vols[s] / sum_uncapped) * remaining_target
            break

        for s in newly_capped:
            uncapped.remove(s)
            remaining_target -= cap

    return {s: round(weights.get(s, 0.0), 6) for s in symbols}


def decide(
    sleeve_cfg: Dict[str, Any],
    history_asof: Dict[str, pd.DataFrame],
    portfolio_state: Dict[str, Any],
    calendar=None,
    is_rebalance_date: bool = True
) -> List[Proposal]:
    """
    Pure decision function for Sleeve A: Cross-Sectional Momentum.
    Generates deterministic Proposals for next trading day open fill.
    """
    proposals: List[Proposal] = []
    asof_date = portfolio_state.get("asof")
    equity = float(portfolio_state.get("equity", 100000.0))
    current_positions = portfolio_state.get("positions", {})  # {sym: {"qty": int, "entry_price": float, "highest_close": float}}

    min_adtv = float(sleeve_cfg.get("min_adtv_cr", 10.0)) * 1e7
    min_price = float(sleeve_cfg.get("min_price", 50.0))
    min_history = int(sleeve_cfg.get("min_history_days", 260))
    top_n = int(sleeve_cfg.get("top_n", 20))
    keep_rank = int(sleeve_cfg.get("keep_rank", 30))
    max_single_weight = float(sleeve_cfg.get("max_single_weight", 0.08))
    bear_exposure = float(sleeve_cfg.get("bear_exposure", 0.5))
    min_delta_w = float(sleeve_cfg.get("min_delta_w", 0.01))
    atr_trail_mult = float(sleeve_cfg.get("atr_trail_mult", 2.5))
    atr_period = int(sleeve_cfg.get("atr_period", 20))
    mom_lookback = int(sleeve_cfg.get("mom_lookback", 252))
    mom_skip = int(sleeve_cfg.get("mom_skip_recent", 21))
    vol_lookback = int(sleeve_cfg.get("vol_lookback", 126))

    # 1. Regime Exposure E (Nifty 50 close vs SMA200)
    index_df = None
    for idx_key in ("^NSEI", "NIFTY 50", "NIFTYBEES.NS"):
        if idx_key in history_asof:
            index_df = history_asof[idx_key]
            break

    if index_df is not None and len(index_df) >= 200:
        nifty_close = float(index_df["Close"].iloc[-1])
        nifty_sma200 = float(index_df["Close"].rolling(200).mean().iloc[-1])
        E = 1.0 if nifty_close >= nifty_sma200 else bear_exposure
    else:
        E = 1.0

    # 2. Risk Exit: Daily close below highest_close_since_entry - 2.5 * ATR20
    stopped_out_symbols = set()
    for sym, pos in current_positions.items():
        sym_df = history_asof.get(sym)
        if sym_df is None or sym_df.empty:
            continue
        latest_close = float(sym_df["Close"].iloc[-1])
        highest_close = float(pos.get("highest_close", pos.get("entry_price", latest_close)))
        highest_close = max(highest_close, latest_close)
        pos["highest_close"] = highest_close

        atr = compute_atr(sym_df, period=atr_period)
        stop_level = highest_close - (atr_trail_mult * atr)

        if latest_close < stop_level:
            qty = int(pos.get("qty", 0))
            if qty > 0:
                proposals.append(Proposal(
                    sleeve="A",
                    symbol=sym,
                    side="SELL",
                    target_weight=0.0,
                    qty=qty,
                    stop=stop_level,
                    reason=f"ATR Trail Stop: Close {latest_close:.2f} < Stop {stop_level:.2f}",
                    asof=asof_date
                ))
                stopped_out_symbols.add(sym)

    # If not a monthly rebalance date, return ATR exits only
    if not is_rebalance_date:
        return proposals

    # 3. Universe Eligibility & Momentum Scoring
    scores: Dict[str, float] = {}
    vols: Dict[str, float] = {}
    latest_prices: Dict[str, float] = {}

    for sym, df in history_asof.items():
        if sym.startswith("^") or sym in ("NIFTY 50", "NIFTYBEES.NS"):
            continue
        if len(df) < min_history:
            continue

        close_series = df["Close"]
        latest_price = float(close_series.iloc[-1])
        if latest_price < min_price:
            continue

        # Liquidity filter: ADTV20 >= min_adtv
        if "Volume" in df.columns:
            turnover = df["Close"] * df["Volume"]
            adtv20 = float(turnover.iloc[-20:].mean()) if len(turnover) >= 20 else float(turnover.mean())
            if adtv20 < min_adtv:
                continue

        score = compute_momentum_score(close_series, lookback=mom_lookback, skip_recent=mom_skip)
        if score > -999990.0:
            scores[sym] = score
            vols[sym] = compute_annualized_vol(close_series, lookback=vol_lookback)
            latest_prices[sym] = latest_price

    if not scores:
        return proposals

    # 4. Rank Selection with Hysteresis Rank Buffer
    ranked_symbols = sorted(scores.keys(), key=lambda s: scores[s], reverse=True)
    rank_map = {sym: idx + 1 for idx, sym in enumerate(ranked_symbols)}

    active_held = {s for s in current_positions.keys() if s not in stopped_out_symbols}
    selected_symbols: List[str] = []

    # Keep existing holdings if rank <= keep_rank (30)
    for sym in active_held:
        r = rank_map.get(sym, 9999)
        if r <= keep_rank:
            selected_symbols.append(sym)
        else:
            # Dropped from rank buffer
            qty = int(current_positions[sym].get("qty", 0))
            if qty > 0 and sym not in stopped_out_symbols:
                proposals.append(Proposal(
                    sleeve="A",
                    symbol=sym,
                    side="SELL",
                    target_weight=0.0,
                    qty=qty,
                    reason=f"Rank Buffer Drop: Rank {r} > {keep_rank}",
                    asof=asof_date
                ))

    # Fill remaining slots up to top_n (20) with highest ranked candidates
    for sym in ranked_symbols:
        if len(selected_symbols) >= top_n:
            break
        if sym not in selected_symbols:
            selected_symbols.append(sym)

    # 5. Compute Capped Weights summing to E
    selected_vols = {s: vols[s] for s in selected_symbols if s in vols}
    target_weights = compute_capped_weights(selected_vols, cap=max_single_weight, target_sum=E)

    # 6. Generate Rebalance Proposals (skip |delta w| < 1%)
    for sym, target_w in target_weights.items():
        price = latest_prices[sym]
        held_qty = current_positions.get(sym, {}).get("qty", 0) if sym in active_held else 0
        current_w = (held_qty * price) / equity if equity > 0 else 0.0
        delta_w = target_w - current_w

        if abs(delta_w) < min_delta_w:
            continue

        if delta_w > 0:
            target_order_val = delta_w * equity
            qty_to_buy = int(target_order_val / price)
            if qty_to_buy > 0:
                proposals.append(Proposal(
                    sleeve="A",
                    symbol=sym,
                    side="BUY",
                    target_weight=target_w,
                    qty=qty_to_buy,
                    reason=f"Momentum Entry w={target_w:.3f}",
                    asof=asof_date
                ))
        elif delta_w < 0 and held_qty > 0:
            qty_to_sell = min(held_qty, int(abs(delta_w) * equity / price))
            if qty_to_sell > 0:
                proposals.append(Proposal(
                    sleeve="A",
                    symbol=sym,
                    side="SELL",
                    target_weight=target_w,
                    qty=qty_to_sell,
                    reason=f"Weight Trim w={target_w:.3f}",
                    asof=asof_date
                ))

    return proposals
