import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.regime import detect
from app.relative_strength import calculate_stock_rs, rank_cross_sectional_rs
from app.eligibility import EligibilityFilter
from app.multitimeframe import MultiTimeframeAnalyzer
from app.features import compute_information_coefficient, verify_no_lookahead, generate_feature_report


def _make_sample_df(n_bars=150, trend=0.001, seed=42):
    rng = np.random.default_rng(seed)
    dt = datetime(2023, 1, 1)
    dates = [dt + timedelta(days=i) for i in range(n_bars)]
    price = 100.0
    rows = []
    for _ in range(n_bars):
        ret = trend + rng.normal(0, 0.012)
        new_price = max(10.0, price * (1.0 + ret))
        high = max(price, new_price) * (1.0 + rng.uniform(0.001, 0.01))
        low = min(price, new_price) * (1.0 - rng.uniform(0.001, 0.01))
        vol = rng.uniform(50000, 200000)
        rows.append({"Open": price, "High": high, "Low": low, "Close": new_price, "Volume": vol})
        price = new_price
    return pd.DataFrame(rows, index=pd.to_datetime(dates))


def test_market_regime_vix_and_breadth():
    nifty_row = {"Close": 22000, "dma50": 21500, "ret_day": 0.015, "volatility": 0.12}

    # 1. Normal Bullish Trend with VIX < 18
    res1 = detect(nifty_row, india_vix=14.5, breadth={"pct_above_50dma": 72.0, "advances": 350, "declines": 150})
    assert res1["regime"] == "Strong bullish trend"
    assert res1["size_multiplier"] == 1.0
    assert res1["allowed_sides"] == ["LONG"]

    # 2. High Volatility (VIX = 24.0) -> Size halved
    res2 = detect(nifty_row, india_vix=24.0)
    assert res2["regime"] == "High volatility"
    assert res2["size_multiplier"] == 0.5
    assert "LONG" in res2["allowed_sides"] and "SHORT" in res2["allowed_sides"]

    # 3. Extreme Panic (VIX = 32.0) -> Trading paused (size 0.0)
    res3 = detect(nifty_row, india_vix=32.0)
    assert res3["regime"] == "Extreme volatility"
    assert res3["size_multiplier"] == 0.0
    assert res3["allowed_sides"] == []

    # 4. Bearish Breadth Divergence (NIFTY up but only 30% above 50 DMA)
    res4 = detect(nifty_row, india_vix=15.0, breadth={"pct_above_50dma": 30.0})
    assert res4["regime"] == "Weak bullish"


def test_relative_strength_cross_sectional_ranking():
    df_leader = _make_sample_df(130, trend=0.005, seed=1)
    df_laggard = _make_sample_df(130, trend=-0.003, seed=2)
    df_bmk = _make_sample_df(130, trend=0.001, seed=3)

    rs = calculate_stock_rs(df_leader, df_bmk, windows=(20, 60, 120))
    assert rs["rs_20"] > 0
    assert rs["rs_60"] > 0
    assert rs["rs_120"] > 0

    universe = {
        "LEADER.NS": df_leader,
        "LAGGARD.NS": df_laggard,
        "BENCHMARK.NS": df_bmk
    }
    ranked = rank_cross_sectional_rs(universe, benchmark_series=df_bmk["Close"])
    assert len(ranked) == 3
    assert ranked["symbol"].iloc[0] == "LEADER.NS"
    assert ranked["symbol"].iloc[-1] == "LAGGARD.NS"
    assert ranked["rank_pct"].iloc[0] > ranked["rank_pct"].iloc[-1]


def test_eligibility_filter_adtv_and_blackouts():
    flt = EligibilityFilter(
        min_adtv_inr=10_000_000.0,
        asm_gsm_symbols=["SURVEILLED.NS"],
        ban_symbols=["BANNED.NS"],
        earnings_dates={"EARNINGS_CO.NS": ["2023-05-15"]}
    )

    df_liquid = _make_sample_df(50)  # Close ~100 * Vol ~100,000 = ~10,000,000 turnover
    ok, _ = flt.check("GOOD.NS", df_liquid, current_date="2023-05-10")
    assert ok is True

    # ASM/GSM check
    ok_asm, reason_asm = flt.check("SURVEILLED.NS", df_liquid)
    assert ok_asm is False
    assert "ASM/GSM" in reason_asm

    # Ban check
    ok_ban, reason_ban = flt.check("BANNED.NS", df_liquid)
    assert ok_ban is False
    assert "ban" in reason_ban

    # Earnings blackout window (+-1 day)
    ok_earn, reason_earn = flt.check("EARNINGS_CO.NS", df_liquid, current_date="2023-05-15")
    assert ok_earn is False
    assert "blackout" in reason_earn

    # Outside blackout window
    ok_safe, _ = flt.check("EARNINGS_CO.NS", df_liquid, current_date="2023-05-20")
    assert ok_safe is True


def test_multitimeframe_trend_and_tod_volume():
    df_daily = _make_sample_df(100, trend=0.003)
    mtf = MultiTimeframeAnalyzer.daily_direction(df_daily)
    assert mtf["bias"] == "BULLISH"
    assert mtf["support"] is not None
    assert mtf["resistance"] is not None

    # Test time-of-day normalized volume
    idx = pd.date_range("2023-01-01 09:15", periods=30, freq="5min")
    intraday = pd.DataFrame({
        "Close": np.full(30, 100.0),
        "Volume": np.full(30, 1000.0)
    }, index=idx)
    norm = MultiTimeframeAnalyzer.normalize_tod_volume(intraday)
    assert len(norm) == 30
    assert norm.iloc[0] > 0


def test_information_coefficient_and_shift_test():
    df = _make_sample_df(100)

    # 1. Lookahead Shift Test
    def compute_last_ema(slice_df):
        return slice_df["Close"].ewm(span=20, adjust=False).mean().iloc[-1]

    # Verify that mutating future bars does NOT change EMA at bar 50
    no_lookahead = verify_no_lookahead(compute_last_ema, df, target_idx=50)
    assert no_lookahead is True

    # 2. Information Coefficient Calculation
    feat = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    fwd_ret = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10])
    ic_res = compute_information_coefficient(feat, fwd_ret)
    assert ic_res["ic"] == 1.0  # Perfect monotonic rank correlation

    # 3. Feature Report Generation
    feat_df = pd.DataFrame({"feat_a": feat, "feat_b": -feat})
    fwd_df = pd.DataFrame({"fwd_1d": fwd_ret, "fwd_5d": fwd_ret * 2})
    rep = generate_feature_report(feat_df, fwd_df)
    assert len(rep) == 2
    assert "ic_fwd_1d" in rep.columns
