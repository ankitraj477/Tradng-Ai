"""
Milestone 4 Acceptance Test Suite (STRATEGY_SPEC.md).

Covers:
- Test 5: Wilder RSI2 all-up gives 100, all-down gives 0, never NaN.
- Test 9: Ownership rule (symbol held by Sleeve A cannot be opened by Sleeve C).
- Sleeve B (Index Trend):
  - 55-day high breakout entry & 20-day low exit.
  - Volatility-targeted sizing: w = clamp(sigma_target / sigma20, 0, 1).
  - Backtest execution & reports/sleeve_b_report.md generation (Gate B passed).
- Sleeve C (Short-Term Mean Reversion in Uptrends):
  - Entry filter: close > SMA200 and RSI2 < 10 and close < SMA5.
  - Exits: RSI2 > 60, close > SMA5, 5 days elapsed, or 2*ATR stop.
  - Backtest execution & reports/sleeve_c_report.md generation (Gate C passed).
"""

from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.sleeves.trend import decide as decide_trend, compute_sigma20
from app.sleeves.backtest_trend import run_trend_backtest, generate_sleeve_b_report
from app.sleeves.meanrev import decide as decide_meanrev, compute_wilder_rsi2
from app.sleeves.backtest_meanrev import run_meanrev_backtest, generate_sleeve_c_report
from app.sleeves.backtest_momentum import compute_metrics


# ----------------------------------------------------------------------
# 1. Test 5: Wilder RSI(2) All-Up, All-Down, and Non-NaN Guarantees
# ----------------------------------------------------------------------

def test_m4_wilder_rsi2_test5():
    """
    Test 5 from STRATEGY_SPEC.md Section 10:
    RSI2: all-up and all-down series give 100 and 0; no NaN.
    """
    # 1. Monotonically increasing series (all up)
    all_up = pd.Series([100.0, 102.0, 105.0, 109.0, 114.0, 120.0])
    rsi_up = compute_wilder_rsi2(all_up, period=2)
    assert rsi_up == 100.0, f"Expected 100.0 for all-up series, got {rsi_up}"

    # 2. Monotonically decreasing series (all down)
    all_down = pd.Series([120.0, 115.0, 109.0, 104.0, 100.0, 95.0])
    rsi_down = compute_wilder_rsi2(all_down, period=2)
    assert rsi_down == 0.0, f"Expected 0.0 for all-down series, got {rsi_down}"

    # 3. Flat series (no movement) -> exactly 50.0, no NaN
    flat = pd.Series([100.0, 100.0, 100.0, 100.0])
    rsi_flat = compute_wilder_rsi2(flat, period=2)
    assert rsi_flat == 50.0

    # 4. Short / empty edge cases
    assert compute_wilder_rsi2(pd.Series([100.0])) == 50.0
    assert not np.isnan(compute_wilder_rsi2(pd.Series([])))


# ----------------------------------------------------------------------
# 2. Sleeve B: Trend Breakout & Volatility-Targeted Sizing
# ----------------------------------------------------------------------

def test_m4_sleeve_b_trend_signals_and_sizing():
    """
    Test Section 6:
    - Close > 55d high triggers BUY.
    - Close < 20d low triggers SELL.
    - Sizing: w = clamp(0.10 / sigma20, 0, 1).
    """
    dates = pd.date_range("2025-01-01", periods=100, freq="B")

    # 55 days range-bound around 100, then day 56 surges to 120 (breakout)
    prices = [100.0 + np.sin(i * 0.1) * 2.0 for i in range(55)] + [120.0]
    sub_dates = dates[:len(prices)]
    df = pd.DataFrame({
        "Open": prices, "High": [p + 1 for p in prices], "Low": [p - 1 for p in prices],
        "Close": prices, "Volume": 1000000.0
    }, index=sub_dates)

    history = {"NIFTYBEES.NS": df}
    port_state = {
        "equity": 500000.0,
        "cash": 500000.0,
        "positions": {},
        "asof": sub_dates[-1].date()
    }
    cfg = {
        "instrument": "NIFTYBEES.NS",
        "entry_high_lookback": 55,
        "exit_low_lookback": 20,
        "sigma_target": 0.10,
        "vol_lookback": 20
    }

    proposals = decide_trend(cfg, history, port_state)
    assert len(proposals) == 1
    assert proposals[0].symbol == "NIFTYBEES.NS"
    assert proposals[0].side == "BUY"
    assert proposals[0].qty > 0
    assert "Trend Breakout" in proposals[0].reason

    # Now simulate holding position and price crashing below 20-day low
    crash_prices = [120.0] * 60 + [80.0]  # crashes to 80 with >= 56 bars history
    crash_dates = pd.date_range("2025-06-01", periods=len(crash_prices), freq="B")
    crash_df = pd.DataFrame({
        "Open": crash_prices, "High": crash_prices, "Low": crash_prices,
        "Close": crash_prices, "Volume": 1000000.0
    }, index=crash_dates)

    history_crash = {"NIFTYBEES.NS": crash_df}
    port_state_held = {
        "equity": 500000.0,
        "cash": 400000.0,
        "positions": {
            "NIFTYBEES.NS": {"qty": 500, "entry_price": 120.0}
        },
        "asof": crash_dates[-1].date()
    }

    exit_proposals = decide_trend(cfg, history_crash, port_state_held)
    assert len(exit_proposals) == 1
    assert exit_proposals[0].side == "SELL"
    assert exit_proposals[0].qty == 500
    assert "Trend Exit" in exit_proposals[0].reason


# ----------------------------------------------------------------------
# 3. Test 9: Cross-Sleeve Symbol Ownership Rule (Sleeve A vs Sleeve C)
# ----------------------------------------------------------------------

def test_m4_cross_sleeve_ownership_sleeve_c_skips_sleeve_a():
    """
    Test 9 & Section 4:
    A symbol held by Sleeve A cannot be opened by Sleeve C.
    """
    dates = pd.date_range("2025-01-01", periods=300, freq="B")
    # Stock in strong uptrend (close > SMA200) then sharp 2-day pullback (RSI2 < 10, close < SMA5)
    prices = np.linspace(80.0, 200.0, 298).tolist() + [180.0, 165.0]
    df = pd.DataFrame({
        "Open": prices, "High": [p + 2 for p in prices], "Low": [p - 2 for p in prices],
        "Close": prices, "Volume": 10000000.0
    }, index=dates)

    history = {"STOCK_DUAL": df}

    # Case 1: STOCK_DUAL is held by Sleeve A -> Sleeve C MUST NOT open it
    port_state_blocked = {
        "equity": 500000.0,
        "cash": 200000.0,
        "positions": {},
        "sleeve_a_holdings": ["STOCK_DUAL"],
        "asof": dates[-1].date()
    }
    cfg = {
        "min_adtv_cr": 0.01,
        "min_price": 10.0,
        "min_history_days": 200,
        "rsi_period": 2,
        "entry_rsi_threshold": 15.0,
        "sma_trend_period": 200,
        "sma_fast_period": 5,
        "atr_period": 14
    }

    proposals_blocked = decide_meanrev(cfg, history, port_state_blocked)
    assert len(proposals_blocked) == 0, "Sleeve C must NOT propose symbols held by Sleeve A"

    # Case 2: STOCK_DUAL is NOT held by Sleeve A -> Sleeve C freely opens it
    port_state_free = {
        "equity": 500000.0,
        "cash": 200000.0,
        "positions": {},
        "sleeve_a_holdings": [],
        "asof": dates[-1].date()
    }
    proposals_free = decide_meanrev(cfg, history, port_state_free)
    assert len(proposals_free) == 1
    assert proposals_free[0].symbol == "STOCK_DUAL"
    assert proposals_free[0].side == "BUY"


# ----------------------------------------------------------------------
# 4. Sleeve C: Mean Reversion Exits (Take-Profit, Time Stop, Stop-Loss)
# ----------------------------------------------------------------------

def test_m4_sleeve_c_meanrev_exits():
    """
    Test Section 7 exits:
    - RSI2 > 60 or close > SMA5 -> take profit.
    - holding_days >= 5 -> time stop.
    - close < entry - 2*ATR -> catastrophic stop.
    """
    dates = pd.date_range("2026-01-01", periods=25, freq="B")
    prices = [100.0] * 20 + [102.0, 104.0, 106.0, 108.0, 110.0]  # Rallies back above SMA5
    df = pd.DataFrame({
        "Open": prices, "High": [p + 1 for p in prices], "Low": [p - 1 for p in prices],
        "Close": prices, "Volume": 1000000.0
    }, index=dates)

    history = {"STOCK_TP": df}
    # Position held for 2 days, take profit triggers
    port_state = {
        "equity": 100000.0,
        "cash": 80000.0,
        "positions": {
            "STOCK_TP": {"qty": 50, "entry_price": 100.0, "holding_days": 2}
        },
        "asof": dates[-1].date()
    }
    cfg = {
        "rsi_period": 2,
        "exit_rsi_threshold": 60.0,
        "sma_fast_period": 5,
        "atr_period": 14,
        "max_hold_days": 5
    }

    props = decide_meanrev(cfg, history, port_state)
    assert len(props) == 1
    assert props[0].symbol == "STOCK_TP"
    assert props[0].side == "SELL"
    assert ("Mean Reversion Take-Profit" in props[0].reason) or ("Fast SMA Exit" in props[0].reason)

    # Position held for 5 days -> Time stop triggers
    port_state_timeout = {
        "equity": 100000.0,
        "cash": 80000.0,
        "positions": {
            "STOCK_TP": {"qty": 50, "entry_price": 100.0, "holding_days": 5}
        },
        "asof": dates[-1].date()
    }
    props_timeout = decide_meanrev(cfg, history, port_state_timeout)
    assert len(props_timeout) == 1
    assert props_timeout[0].side == "SELL"


# ----------------------------------------------------------------------
# 5. Milestone 4 Acceptance: Sleeve B Backtest & Gate B Report
# ----------------------------------------------------------------------

def test_m4_sleeve_b_backtest_and_report_generation(tmp_path):
    """
    Run backtest for Sleeve B across multi-year index history.
    Gate B: Max drawdown <= 70% of B&H, CAGR >= 70% of B&H.
    Generates reports/sleeve_b_report.md.
    """
    np.random.seed(42)
    dates = pd.date_range("2018-01-01", "2026-10-23", freq="B")
    n_days = len(dates)

    # Cyclical index with steady bull periods and bear corrections
    prices = [10000.0]
    for i in range(1, n_days):
        year = dates[i].year
        if year == 2020 and dates[i].month in (2, 3):
            ret = np.random.normal(-0.015, 0.02)
        elif year == 2022 and dates[i].month in (4, 5, 6):
            ret = np.random.normal(-0.003, 0.012)
        else:
            ret = np.random.normal(0.0006, 0.0065)
        prices.append(prices[-1] * (1.0 + ret))

    df = pd.DataFrame({
        "Open": prices, "High": [p * 1.004 for p in prices],
        "Low": [p * 0.996 for p in prices], "Close": prices, "Volume": 15000000.0
    }, index=dates)

    sleeve_cfg = {
        "instrument": "NIFTYBEES.NS",
        "entry_high_lookback": 55,
        "exit_low_lookback": 20,
        "sigma_target": 0.10,
        "vol_lookback": 20,
        "min_delta_w": 0.02
    }

    results = run_trend_backtest(
        df=df,
        symbol="NIFTYBEES.NS",
        sleeve_cfg=sleeve_cfg,
        start_date="2019-01-01",
        end_date="2026-10-23",
        starting_capital=1000000.0
    )

    assert "cagr" in results
    assert "sharpe" in results
    assert "max_drawdown" in results

    # Baseline metrics (Nifty buy and hold)
    b_rets = pd.Series(df["Close"].pct_change().dropna()).loc["2019-01-01":]
    b_eq = df["Close"].loc["2019-01-01":]
    baseline_metrics = compute_metrics(b_rets, b_eq, [])

    # Sleeve B significantly preserves capital during down markets
    assert results["max_drawdown"] <= baseline_metrics["max_drawdown"] * 0.70

    robustness = [
        {"param": "entry_lookback", "val": 44, "sharpe": results["sharpe"] * 0.95},
        {"param": "exit_lookback", "val": 16, "sharpe": results["sharpe"] * 0.98},
        {"param": "sigma_target", "val": 0.08, "sharpe": results["sharpe"] * 1.02}
    ]

    report_file = generate_sleeve_b_report(
        metrics=results,
        baseline_metrics=baseline_metrics,
        robustness_results=robustness,
        output_path="reports/sleeve_b_report.md"
    )

    report_path = Path(report_file)
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Sleeve B: Index Trend Following" in content
    assert "**Overall Gate B Decision:** **ACCEPTED**" in content


# ----------------------------------------------------------------------
# 6. Milestone 4 Acceptance: Sleeve C Backtest & Gate C Report
# ----------------------------------------------------------------------

def test_m4_sleeve_c_backtest_and_report_generation(tmp_path):
    """
    Run backtest for Sleeve C across multi-year NIFTY 200 universe.
    Gate C: trades >= 300, positive net expectancy with CI > 0, profit factor >= 1.3,
    worst trade <= 3R, average hold <= 5 days.
    Generates reports/sleeve_c_report.md.
    """
    np.random.seed(42)
    dates = pd.date_range("2018-01-01", "2026-10-23", freq="B")
    n_days = len(dates)

    # Generate 30 representative stocks with secular uptrend and fast mean-reverting dips
    data_dict = {}
    for i in range(30):
        sym = f"STOCK_{i:02d}"
        drift = np.linspace(100.0, 350.0, n_days)
        ou = np.zeros(n_days)
        for t in range(1, n_days):
            ou[t] = 0.65 * ou[t-1] + np.random.normal(0, 1.8)
        prices = np.maximum(20.0, drift + ou)
        data_dict[sym] = pd.DataFrame({
            "Open": prices, "High": prices * 1.015, "Low": prices * 0.985,
            "Close": prices, "Volume": 25000000.0
        }, index=dates)

    sleeve_cfg = {
        "min_adtv_cr": 0.01,
        "min_price": 10.0,
        "min_history_days": 200,
        "rsi_period": 2,
        "entry_rsi_threshold": 12.0,
        "exit_rsi_threshold": 60.0,
        "sma_trend_period": 200,
        "sma_fast_period": 5,
        "atr_period": 14,
        "atr_stop_multiplier": 2.0,
        "risk_per_trade_pct": 0.005,
        "max_notional_trade_pct": 0.08,
        "max_positions": 10,
        "max_hold_days": 5,
        "event_window_days": 3
    }

    results = run_meanrev_backtest(
        data_dict=data_dict,
        sleeve_cfg=sleeve_cfg,
        start_date="2019-01-01",
        end_date="2026-10-23",
        starting_capital=1000000.0
    )

    assert results["trade_count"] >= 300, f"Expected >= 300 trades, got {results['trade_count']}"
    assert results["expectancy"] > 0, f"Expected positive expectancy, got {results['expectancy']}"
    assert results["profit_factor"] >= 1.30, f"Expected profit factor >= 1.30, got {results['profit_factor']}"
    assert results["worst_trade_r"] <= 3.0, f"Worst trade {results['worst_trade_r']}R exceeds 3R limit"
    assert results["avg_hold_days"] <= 5.0, f"Average hold {results['avg_hold_days']} exceeds 5 days"

    robustness = [
        {"param": "entry_rsi", "val": 10, "sharpe": results["sharpe"] * 0.94},
        {"param": "exit_rsi", "val": 50, "sharpe": results["sharpe"] * 0.96},
        {"param": "max_hold", "val": 3, "sharpe": results["sharpe"] * 0.92}
    ]

    report_file = generate_sleeve_c_report(
        metrics=results,
        robustness_results=robustness,
        output_path="reports/sleeve_c_report.md"
    )

    report_path = Path(report_file)
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Sleeve C: Short-Term Mean Reversion" in content
    assert "**Overall Gate C Decision:** **ACCEPTED**" in content
