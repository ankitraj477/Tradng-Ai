import math
import pandas as pd
from app.backtest import Backtester

def test_backtest_stop_fills_at_gap_open():
    bt = Backtester(starting_cash=10000, fee_bps=0, slippage_bps=0)
    # Construct bars: bar 0 generates LONG, bar 1 opens position at 100 with stop ~97,
    # bar 2 gaps down opening at 90
    dates = pd.date_range("2026-01-01", periods=3, freq="5min")
    pos = {
        "side": "LONG",
        "entry": 100.0,
        "qty": 10,
        "stop": 97.0,
        "target": 110.0,
        "margin": 0,
        "entry_i": dates[0],
        "entry_fee": 0.0,
        "atr": 2.0,
    }

    # Simulate close on a gapping bar
    gap_row = pd.Series({"Open": 90.0, "High": 91.0, "Low": 88.0, "Close": 89.0}, name=dates[1])
    fill_px = min(pos["stop"], float(gap_row["Open"]))
    bt._close("GAP.NS", pos, fill_px, "stop")

    trade = bt.trades[-1]
    # Fill must be 90.0 (the gap open), NOT 97.0 (the optimistic stop)!
    assert trade["exit"] == 90.0
    assert trade["pnl"] == (90.0 - 100.0) * 10

def test_backtest_pnl_matches_cash_change():
    bt = Backtester(starting_cash=10000, fee_bps=10, slippage_bps=0)
    pos = {
        "side": "LONG",
        "entry": 100.0,
        "qty": 10,
        "stop": 95.0,
        "target": 110.0,
        "margin": 0,
        "entry_i": "t0",
        "entry_fee": 1.0,  # 1000 * 10 / 10000 = 1.0
        "atr": 2.0,
    }
    bt.cash = 10000 - 1000 - 1.0  # after buy cash
    bt._close("COST.NS", pos, 105.0, "target")
    trade = bt.trades[-1]
    # Gross = +50, entry_fee = 1.0, exit_fee = 1050 * 0.001 = 1.05
    # Total PnL = 50 - 2.05 = 47.95
    assert math.isclose(trade["pnl"], 47.95, abs_tol=1e-4)
    assert math.isclose(bt.cash - 10000, 47.95, abs_tol=1e-4)
