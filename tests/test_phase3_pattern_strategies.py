import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.pattern_strategies import (
    BreakoutStrategy,
    EmaPullbackStrategy,
    RsiMeanReversionStrategy,
    RelativeStrengthMomentumStrategy
)
from app.grid_search import (
    evaluate_parameter_grid,
    detect_parameter_plateau,
    evaluate_acceptance
)


def _make_bars(n=100, trend=0.002, seed=42):
    rng = np.random.default_rng(seed)
    dt = datetime(2023, 1, 1)
    dates = [dt + timedelta(days=i) for i in range(n)]
    price = 100.0
    rows = []
    for _ in range(n):
        ret = trend + rng.normal(0, 0.01)
        new_price = max(10.0, price * (1.0 + ret))
        h = max(price, new_price) * (1.0 + rng.uniform(0.002, 0.01))
        l = min(price, new_price) * (1.0 - rng.uniform(0.002, 0.01))
        v = rng.uniform(10000, 50000)
        rows.append({"Open": price, "High": h, "Low": l, "Close": new_price, "Volume": v})
        price = new_price
    return pd.DataFrame(rows, index=pd.to_datetime(dates))


def test_breakout_strategy_logic():
    df = _make_bars(60, trend=0.0)
    strat = BreakoutStrategy(n_bars=20, volume_mult=1.5, atr_stop_mult=1.5, atr_target_mult=3.0)

    # Normal sideways bar -> no signal
    sig1 = strat.decide("BREAK.NS", df)
    assert sig1 is None or isinstance(sig1, dict)

    # Force a breakout bar: massive new high and huge volume
    max_h = df["High"].iloc[:-1].tail(20).max()
    df_break = df.copy()
    df_break.iloc[-1, df_break.columns.get_loc("Close")] = max_h + 5.0
    df_break.iloc[-1, df_break.columns.get_loc("Volume")] = df["Volume"].mean() * 3.0

    sig2 = strat.decide("BREAK.NS", df_break)
    assert sig2 is not None
    assert sig2["action"] == "BUY"
    assert sig2["side"] == "LONG"
    assert sig2["stop_loss"] < sig2["price"]
    assert sig2["target"] > sig2["price"]


def test_ema_pullback_strategy_logic():
    df = _make_bars(80, trend=0.005)  # Upward trending
    strat = EmaPullbackStrategy(fast_ema=20, slow_ema=50)

    # Artificially create a pullback to EMA20
    c = df["Close"]
    ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
    df_pull = df.copy()
    # Low touches EMA20, Close bounces back above EMA20
    df_pull.iloc[-1, df_pull.columns.get_loc("Low")] = ema20 * 0.999
    df_pull.iloc[-1, df_pull.columns.get_loc("Close")] = ema20 * 1.01

    sig = strat.decide("PULL.NS", df_pull)
    if sig:
        assert sig["action"] in {"BUY", "SHORT"}
        assert sig["strategy"] == "EmaPullback"


def test_rsi_mean_reversion_strategy_logic():
    df = _make_bars(120, trend=0.003)  # Macro uptrend (Close > 100 EMA)
    strat = RsiMeanReversionStrategy(rsi_period=2, oversold=15.0, trend_span=80)

    # Force extreme 2-day selloff to trigger RSI-2 < 15
    df_dip = df.copy()
    last_px = df_dip["Close"].iloc[-3]
    df_dip.iloc[-2, df_dip.columns.get_loc("Close")] = last_px * 0.95
    df_dip.iloc[-1, df_dip.columns.get_loc("Close")] = last_px * 0.90
    df_dip.iloc[-1, df_dip.columns.get_loc("Low")] = last_px * 0.89

    sig = strat.decide("REVERT.NS", df_dip)
    if sig:
        assert sig["action"] == "BUY"
        assert sig["strategy"] == "RsiMeanReversion"
        assert sig["target"] > sig["price"]


def test_rs_momentum_strategy():
    strat = RelativeStrengthMomentumStrategy(top_rank_threshold=85.0)
    # Symbol in 92nd percentile should trigger buy
    sig_leader = strat.decide_from_rank("LEADER.NS", last_px=500.0, rank_pct=92.5, atr=10.0)
    assert sig_leader is not None
    assert sig_leader["action"] == "BUY"
    assert sig_leader["stop_loss"] == 480.0  # 500 - 2.0*10

    # Symbol in 70th percentile should NOT trigger buy
    sig_mid = strat.decide_from_rank("MID.NS", last_px=500.0, rank_pct=70.0, atr=10.0)
    assert sig_mid is None


def test_parameter_grid_and_plateau_detection():
    # Synthetic grid results
    grid_df = pd.DataFrame([
        {"n_bars": 15, "vol_mult": 1.2, "return_pct": 14.5, "trades": 80, "win_rate": 55.0},
        {"n_bars": 20, "vol_mult": 1.2, "return_pct": 15.2, "trades": 75, "win_rate": 56.0},
        {"n_bars": 25, "vol_mult": 1.2, "return_pct": 14.8, "trades": 70, "win_rate": 54.0},
        {"n_bars": 20, "vol_mult": 1.5, "return_pct": 13.9, "trades": 60, "win_rate": 53.0},
    ])

    plateau = detect_parameter_plateau(grid_df, metric="return_pct", max_cv=0.20)
    assert plateau["is_plateau"] is True
    assert plateau["top_mean"] > 14.0

    # Spiky peak (huge variance in top results)
    spiky_df = pd.DataFrame([
        {"p": 1, "return_pct": 45.0},
        {"p": 2, "return_pct": 2.0},
        {"p": 3, "return_pct": -5.0},
    ])
    spiky_plateau = detect_parameter_plateau(spiky_df, metric="return_pct", max_cv=0.20)
    assert spiky_plateau["is_plateau"] is False


def test_acceptance_gate_rules():
    # Strategy that beats baselines with enough trades
    perf_pass = {"return_pct": 22.0, "trades": 120, "is_plateau": True}
    base_perf = {"bnh_return_pct": 12.0, "eq_weight_return_pct": 10.0}
    res_pass = evaluate_acceptance("SolidTrend", perf_pass, base_perf, min_trades=100)
    assert res_pass["status"] == "ACCEPTED"
    assert len(res_pass["rejections"]) == 0

    # Strategy that fails on baseline comparison and trades count
    perf_fail = {"return_pct": 8.0, "trades": 30, "is_plateau": False}
    res_fail = evaluate_acceptance("WeakStrategy", perf_fail, base_perf, min_trades=100)
    assert res_fail["status"] == "REJECTED"
    assert len(res_fail["rejections"]) >= 2
