import math
import numpy as np
import pandas as pd
from app.indicators import indicators
from app.regime import detect

def test_vwap_resets_per_session():
    # Day 1: 30 bars at 100.0
    day1_idx = pd.date_range("2026-01-01 09:15", periods=30, freq="5min")
    # Day 2: 30 bars at 200.0
    day2_idx = pd.date_range("2026-01-02 09:15", periods=30, freq="5min")
    idx = day1_idx.append(day2_idx)

    prices = np.concatenate([np.full(30, 100.0), np.full(30, 200.0)])
    df = pd.DataFrame({
        "Open": prices,
        "High": prices + 1.0,
        "Low": prices - 1.0,
        "Close": prices,
        "Volume": np.full(60, 1000.0),
    }, index=idx)

    out = indicators(df)
    # Day 2's VWAP should be 200.0, resetting per session rather than averaging Day 1 and Day 2 (150.0)
    assert math.isclose(out.loc[day2_idx[-1], "vwap"], 200.0, abs_tol=1e-3)

def test_volatility_annualization_reaches_high_volatility():
    # 5-min return std of 0.4% (0.004) under sqrt(252 * 75) gives ~0.55 > 0.45 threshold
    r = {"volatility": 0.004 * math.sqrt(252 * 75)}
    res = detect(r)
    assert res["regime"] == "High volatility"

def test_strong_bullish_trend_reachable():
    r = {"ret_day": 0.015, "Close": 25000.0, "ema20": 24800.0, "volatility": 0.15}
    res = detect(r)
    assert res["regime"] == "Strong bullish trend"
    assert res["sentiment"] == "Bullish"
