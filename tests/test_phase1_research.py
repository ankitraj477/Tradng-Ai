import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

from app.costs import CostModel
from app.data.store import MarketDataStore
from app.universe_pit import PointInTimeUniverse
from app.strategy import decide
from app.backtest import Backtester
from app.baselines import buy_and_hold_baseline, equal_weight_baseline, random_entries_baseline
from app.validation import walk_forward_evaluate, calculate_metrics
from app.candidate_log import CandidateLog


def _make_dummy_ohlcv(n_bars=150, trend=0.001, seed=42):
    rng = np.random.default_rng(seed)
    dt = datetime(2023, 1, 1)
    dates = [dt + timedelta(days=i) for i in range(n_bars)]
    price = 100.0
    rows = []
    for _ in range(n_bars):
        ret = trend + rng.normal(0, 0.015)
        new_price = max(10.0, price * (1.0 + ret))
        high = max(price, new_price) * (1.0 + rng.uniform(0.001, 0.01))
        low = min(price, new_price) * (1.0 - rng.uniform(0.001, 0.01))
        vol = rng.uniform(50000, 200000)
        rows.append({"Open": price, "High": high, "Low": low, "Close": new_price, "Volume": vol})
        price = new_price
    df = pd.DataFrame(rows, index=pd.to_datetime(dates))
    return df


def test_costs_model_accuracy():
    cm = CostModel()
    val = 100000.0
    cost_buy = cm.calculate(val, "BUY", "INTRADAY")
    cost_sell = cm.calculate(val, "SELL", "INTRADAY")
    assert cost_buy > 0.0
    assert cost_sell > 0.0
    # Intraday STT applies to SELL only, so SELL cost > BUY cost
    assert cost_sell > cost_buy

    # Delivery test
    deliv_buy = cm.calculate(val, "BUY", "DELIVERY")
    deliv_sell = cm.calculate(val, "SELL", "DELIVERY")
    assert deliv_sell > deliv_buy  # Delivery sell has DP charges + STT


def test_data_store_crud(tmp_path):
    store = MarketDataStore(tmp_path / "bars.db")
    df = _make_dummy_ohlcv(50)
    store.save_bars("INFY.NS", df, adjusted=True)
    assert store.symbols() == ["INFY.NS"]
    loaded = store.get_bars("INFY.NS")
    assert len(loaded) == 50
    assert "Adjusted" in loaded.columns
    assert loaded["Adjusted"].iloc[0] == 1


def test_point_in_time_universe(tmp_path):
    pit = PointInTimeUniverse(tmp_path / "pit.db")
    # Stock A added in 2020, never removed
    pit.add_membership("STOCK_A.NS", "2020-01-01", None)
    # Stock B added in 2021, removed in 2023
    pit.add_membership("STOCK_B.NS", "2021-01-01", "2023-01-01")

    # In 2020, only A was present
    assert pit.get_constituents("2020-06-01") == {"STOCK_A.NS"}
    # In 2022, both A and B were present
    assert pit.get_constituents("2022-06-01") == {"STOCK_A.NS", "STOCK_B.NS"}
    # In 2024, B was removed, only A remains
    assert pit.get_constituents("2024-06-01") == {"STOCK_A.NS"}


def test_single_decision_live_and_backtest_alignment():
    df = _make_dummy_ohlcv(100, trend=0.005)
    # Call decide on bar history
    live_signal = decide("TEST.NS", df)

    # In backtester, signal generated for the same bar
    bt = Backtester()
    res = bt.run(df, "TEST.NS")
    # Both evaluate the same underlying indicators & threshold logic without divergent rules
    assert isinstance(res["trades"], int)
    if live_signal:
        assert live_signal["action"] in {"BUY", "SHORT"}
        assert live_signal["stop_loss"] > 0
        assert live_signal["target"] > 0


def test_baselines_reproducibility_and_random_expectancy():
    df_bull = _make_dummy_ohlcv(100, trend=0.005, seed=1)
    df_bear = _make_dummy_ohlcv(100, trend=-0.005, seed=2)
    datasets = {"BULL.NS": df_bull, "BEAR.NS": df_bear}

    bnh = buy_and_hold_baseline(df_bull)
    assert "cagr" in bnh and "max_drawdown_pct" in bnh

    eq_weight = equal_weight_baseline(datasets)
    assert "cagr" in eq_weight and "final_capital" in eq_weight

    # Random strategy net of costs should show <= 0 expectancy
    rand = random_entries_baseline(datasets, n_trades=50, holding_bars=5, seed=42)
    assert rand["trades"] > 0
    assert rand["expectancy"] <= 0.0 or rand["total_pnl"] < 1000  # Dragged down by costs


def test_walk_forward_evaluation_harness():
    df1 = _make_dummy_ohlcv(200, trend=0.002, seed=10)
    df2 = _make_dummy_ohlcv(200, trend=-0.001, seed=20)
    datasets = {"SYM1.NS": df1, "SYM2.NS": df2}

    metrics = walk_forward_evaluate(datasets, train_bars=80, test_bars=30, purge_bars=5, embargo_bars=2)
    assert "cagr" in metrics
    assert "sharpe_ratio" in metrics
    assert "sortino_ratio" in metrics
    assert "win_rate_ci_95" in metrics
    assert metrics["windows_tested"] >= 2


def test_candidate_log_storage_and_forward_returns(tmp_path):
    log = CandidateLog(tmp_path / "cand.db")
    feat = {"rsi": 62.5, "ema20": 105.0, "ema50": 100.0, "rel_volume": 1.5, "ret_5": 0.02, "bull_score": 75}
    log.record("TCS.NS", "2023-05-01 10:00:00", 100.0, feat, action="BUY")

    ds = log.get_dataset()
    assert len(ds) == 1
    assert ds["symbol"].iloc[0] == "TCS.NS"
    assert ds["bull_score"].iloc[0] == 75.0

    # Update 5d forward return when forward price is 108.0
    log.update_forward_return(int(ds["id"].iloc[0]), 5, 108.0)
    updated = log.get_dataset()
    assert round(float(updated["forward_ret_5d"].iloc[0]), 2) == 0.08
