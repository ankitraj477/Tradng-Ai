from datetime import datetime, time
from zoneinfo import ZoneInfo
import numpy as np
import pytest

from app.db import DB
from app.costs import CostModel
from app.ml.cross_validation import PurgedWalkForwardCV
from app.position_manager import PositionManager
from app.ops.kill_switch import CentralKillSwitch
from app.market_hours import reload_holidays, holiday_name, IST
from app.dashboard import create_app


def test_costs_exact_statutory_and_dynamic_slippage():
    cm = CostModel()
    
    # Intraday: STT is 0.025% on sell only, 0 on buy
    cost_buy = cm.calculate(100_000.0, "BUY", "INTRADAY")
    cost_sell = cm.calculate(100_000.0, "SELL", "INTRADAY")
    
    # Stamp duty on BUY (0.003% = 3.0), STT on SELL (0.025% = 25.0)
    # Net difference is exactly STT - Stamp = 25.0 - 3.0 = 22.0
    assert pytest.approx(cost_sell - cost_buy, rel=1e-2) == 22.0

    # Dynamic Slippage with ADTV
    # Order of 100,000 in a stock with ADTV 10,000,000 vs ADTV 1,000,000
    slip_liquid = cm.calculate_slippage(100_000.0, adtv=50_000_000.0)
    slip_illiquid = cm.calculate_slippage(100_000.0, adtv=1_000_000.0)
    assert slip_illiquid > slip_liquid

    # Base slippage when ADTV is None
    slip_base = cm.calculate_slippage(100_000.0, adtv=None, base_bps=5.0)
    assert slip_base == 50.0  # 100,000 * 5 bps = 50.0


def test_purged_walk_forward_dynamic_embargo():
    # Base CV with default purge
    cv_base = PurgedWalkForwardCV(n_splits=3, purge_bars=5, embargo_bars=2)
    assert cv_base.purge_bars == 5

    # Dynamic CV with max_holding_bars = 15
    cv_dynamic = PurgedWalkForwardCV(n_splits=3, purge_bars=5, embargo_bars=2, max_holding_bars=15)
    # purge_bars must be scaled to max_holding_bars + embargo_bars = 17
    assert cv_dynamic.purge_bars == 17

    splits = list(cv_dynamic.split(100))
    for train_idx, test_idx in splits:
        # Check gap between train and test is at least purge_bars
        gap = test_idx[0] - train_idx[-1]
        assert gap > 16


def test_position_manager_eod_square_off():
    db = DB(":memory:")
    db.ensure_account(100000.0, 200000.0)

    class MockExecution:
        def __init__(self):
            self.closed = []
        def close(self, symbol, price, reason, comment=""):
            self.closed.append((symbol, price, reason))

    class MockProvider:
        def quote(self, symbol):
            return {"symbol": symbol, "price": 100.0}

    exec_mock = MockExecution()
    provider_mock = MockProvider()
    cfg = {"execution": {"trailing_stop_atr": 1.5, "max_hold_minutes": 390}, "live_data": True}
    pm = PositionManager(db, exec_mock, provider_mock, cfg)

    # Insert mock position with current timestamp so it does not trigger time exit
    opened_now = datetime.now(ZoneInfo("UTC")).isoformat()
    with db.conn() as conn:
        conn.execute(
            """INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence, opened_at, atr, entry_cost)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("RELIANCE.NS", "LONG", 10, 100.0, 100.0, 95.0, 110.0, "ORB", 80.0, opened_now, 2.0, 0.0)
        )

    # Mid-day IST: Wednesday 11:30 IST (regular trading day) -> should NOT trigger EOD square-off
    mid_day = datetime(2026, 10, 21, 11, 30, tzinfo=IST)
    pm.manage(dt=mid_day)
    assert len(exec_mock.closed) == 0

    # EOD square-off window: Wednesday 15:15 IST -> MUST trigger EOD square-off
    eod_time = datetime(2026, 10, 21, 15, 15, tzinfo=IST)
    pm.manage(dt=eod_time)
    assert len(exec_mock.closed) == 1
    assert exec_mock.closed[0][0] == "RELIANCE.NS"
    assert "EOD square-off" in exec_mock.closed[0][2]


def test_central_kill_switch_and_flatten():
    db = DB(":memory:")
    db.ensure_account(100000.0, 200000.0)

    class MockExecution:
        def __init__(self):
            self.closed = []
        def close(self, symbol, price, reason, comment=""):
            self.closed.append((symbol, price, reason))

    class MockProvider:
        def quote(self, symbol):
            return {"symbol": symbol, "price": 250.0}

    exec_mock = MockExecution()
    provider_mock = MockProvider()
    ks = CentralKillSwitch(db, exec_mock, provider_mock, cfg={"live_data": False})

    # Initially normal
    tripped, _ = ks.is_tripped()
    assert tripped is False

    # Insert position
    with db.conn() as conn:
        conn.execute(
            """INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence, opened_at, atr, entry_cost)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("TCS.NS", "LONG", 5, 250.0, 250.0, 240.0, 270.0, "BREAKOUT", 85.0, "2026-10-18T10:00:00+00:00", 3.0, 0.0)
        )

    # Trigger emergency flatten
    closed = ks.flatten_portfolio(reason="Test Panic Trigger")
    assert closed == 1
    assert len(exec_mock.closed) == 1
    assert "EMERGENCY FLATTEN" in exec_mock.closed[0][2]

    # Verify state is tripped
    tripped, reason = ks.is_tripped()
    assert tripped is True
    assert "Test Panic Trigger" in reason

    # Reset
    ks.reset()
    tripped, _ = ks.is_tripped()
    assert tripped is False


def test_dashboard_kill_switch_endpoints():
    db = DB(":memory:")
    db.ensure_account(100000.0, 200000.0)
    app = create_app(db=db)
    client = app.test_client()

    # Query initial status
    res = client.get("/api/kill-switch")
    assert res.status_code == 200
    assert res.json["tripped"] is False

    # Flatten via endpoint
    res_flatten = client.post("/api/kill-switch/flatten")
    assert res_flatten.status_code == 200
    assert res_flatten.json["status"] == "flattened"

    # Verify now tripped
    res2 = client.get("/api/kill-switch")
    assert res2.json["tripped"] is True

    # Reset via endpoint
    res_reset = client.post("/api/kill-switch/reset")
    assert res_reset.status_code == 200
    assert res_reset.json["status"] == "reset"

    res3 = client.get("/api/kill-switch")
    assert res3.json["tripped"] is False


def test_standardized_holiday_reloader():
    # Programmatically inject a test holiday
    reload_holidays(custom_holidays={"2026-12-31": "Special New Year Eve Closure"})
    
    test_dt = datetime(2026, 12, 31, 10, 0, tzinfo=IST)
    assert holiday_name(test_dt) == "Special New Year Eve Closure"

    # Reload from disk file restores standard calendar
    reload_holidays()
    assert holiday_name(datetime(2026, 1, 26, 10, 0, tzinfo=IST)) == "Republic Day"
