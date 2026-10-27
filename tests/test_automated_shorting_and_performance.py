import pytest
import pandas as pd
from types import SimpleNamespace
from app.db import DB
from app.regime import detect
from app.intraday.runner import IntradayDeskRunner
from app.intraday.orb_strategy import ORBDeskStrategy
from app.intraday.position_manager import IntradayPositionManager


class MockProvider:
    def __init__(self, price=100.0):
        self.price = price

    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}

    def symbols(self):
        return ["RELIANCE.NS", "TCS.NS"]

    def history(self, symbol, period="5d", interval="5m"):
        dates = pd.date_range("2026-10-28 09:15", periods=50, freq="5min")
        return pd.DataFrame({
            "Open": [100.0] * 50,
            "High": [102.0] * 50,
            "Low": [99.0] * 50,
            "Close": [self.price] * 50,
            "Volume": [100000.0] * 50
        }, index=dates)


def test_regime_automatically_suppresses_shorting_in_bullish_and_sideways():
    """Verify that detect() disables shorting in Weak bullish, Sideways, and Uncertain regimes."""
    # Uncertain (no row) -> Long only
    r_unknown = detect(None)
    assert r_unknown["allowed_sides"] == ["LONG"]

    # Weak bullish (ret > 0) -> Long only
    row_bull = {"Close": 25000, "ema20": 24900, "ret_day": 0.005, "volatility": 0.01}
    r_bull = detect(row_bull)
    assert r_bull["allowed_sides"] == ["LONG"]

    # Sideways (ret == 0) -> Long only
    row_side = {"Close": 25000, "ema20": 25000, "ret_day": 0.0, "volatility": 0.01}
    r_side = detect(row_side)
    assert r_side["allowed_sides"] == ["LONG"]

    # Strong bearish (ret < -0.01 and close < dma50) -> Short only
    row_bear = {"Close": 24000, "dma50": 25000, "ret_day": -0.015, "volatility": 0.02}
    r_bear = detect(row_bear)
    assert r_bear["allowed_sides"] == ["SHORT"]


def test_intraday_runner_automated_shorting_gate():
    """Verify that IntradayDeskRunner automatically blocks SHORT when market is not bearish."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    provider = MockProvider(price=500.0)
    cfg = {
        "allow_shorts": "auto",
        "market": {"max_open_positions": 5},
        "risk": {"min_trade_notional": 5000.0},
        "execution": {"enforce_market_hours": False, "breakeven_lock_ratio": 0.33}
    }
    runner = IntradayDeskRunner(db, provider, cfg)

    # Mock market state as Bullish
    db.set_market("Strong bullish trend", "Bullish", "Trend=Strong bullish trend", True)

    # Mock candidate and strategy signal
    runner.scanner.scan_opening_candidates = lambda u: [{"symbol": "INFY.NS", "price": 500.0}]
    runner.strategy.evaluate = lambda sym, market_regime=None: SimpleNamespace(
        action="SHORT",
        stop_loss=510.0,
        target=480.0,
        atr=5.0
    )
    runner.timing.can_enter = lambda dt=None: True

    # Run cycle in bullish market
    runner.run_cycle()

    # Short must have been BLOCKED by the automated regime gate
    positions = [p for p in db.positions() if p["symbol"] == "INFY.NS"]
    assert len(positions) == 0

    # Now set market to Strong bearish trend
    db.set_market("Strong bearish trend", "Bearish", "Trend=Strong bearish trend", True)
    runner.run_cycle()

    # Now short MUST be executed
    positions_bear = [p for p in db.positions() if p["symbol"] == "INFY.NS"]
    assert len(positions_bear) == 1
    assert positions_bear[0]["side"] == "SHORT"
    assert positions_bear[0]["qty"] > 0
    assert (positions_bear[0]["qty"] * positions_bear[0]["entry_price"]) >= 5000.0


def test_intraday_runner_skips_micro_notional():
    """Verify that stocks with notional < min_trade_notional are skipped to prevent fee drag."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(1000.0, 1000.0)  # Very small account cash

    provider = MockProvider(price=42.0)
    cfg = {
        "allow_shorts": "auto",
        "market": {"max_open_positions": 5},
        "risk": {"min_trade_notional": 5000.0},
        "execution": {"enforce_market_hours": False, "breakeven_lock_ratio": 0.33}
    }
    runner = IntradayDeskRunner(db, provider, cfg)
    db.set_market("Weak bullish", "Bullish", "Trend=Weak bullish", True)

    runner.scanner.scan_opening_candidates = lambda u: [{"symbol": "PENNY.NS", "price": 42.0}]
    runner.strategy.evaluate = lambda sym, market_regime=None: SimpleNamespace(
        action="BUY",
        stop_loss=40.0,
        target=45.0,
        atr=1.0
    )
    runner.timing.can_enter = lambda dt=None: True

    runner.run_cycle()

    # Must be skipped because total allocated capital produces notional < ₹5,000
    positions = [p for p in db.positions() if p["symbol"] == "PENNY.NS"]
    assert len(positions) == 0


def test_earlier_breakeven_lock_ratio():
    """Verify that breakeven triggers at 33% move towards target rather than waiting for 50%."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    provider = MockProvider(price=101.5)  # Price moved from 100 to 101.5 (+1.5, target is 104)
    cfg = {
        "execution": {
            "breakeven_lock_ratio": 0.33,
            "trailing_stop_atr": 1.5,
            "max_hold_minutes": 390
        }
    }
    from app.intraday.execution import IntradayExecution
    exec_engine = IntradayExecution(db, cfg)
    pm = IntradayPositionManager(db, exec_engine, provider, cfg)

    # Open a long position: entry=100.0, SL=98.0, Target=104.0 (step = 4.0; 33% = 1.32; trigger = 101.32)
    exec_engine.open_long("TEST.NS", 50, 100.0, 98.0, 104.0, 1.0)
    pos = db.positions()[0]
    assert pos["stop_loss"] == 98.0

    # Manage position when price is 101.5 (> 101.32)
    pm.manage()

    # Stop loss must have moved to breakeven (100.10)
    updated_pos = db.positions()[0]
    assert updated_pos["stop_loss"] >= 100.0
