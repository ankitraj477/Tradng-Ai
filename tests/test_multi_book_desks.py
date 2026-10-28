import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

from app.db import DB
from app.execution import PaperExecution
from app.position_manager import PositionManager
from app.swing.scanner import SwingScanner
from app.swing.pullback_strategy import SwingPullbackStrategy
from app.swing.execution import SwingExecution
from app.swing.position_manager import SwingPositionManager
from app.fno.index_chain import IndexChainManager
from app.fno.iron_condor import IronCondorStrategy
from app.fno.execution import FNOExecution
from app.fno.position_manager import FNOPositionManager

IST = ZoneInfo("Asia/Kolkata")

class MockProvider:
    def __init__(self, price=100.0):
        self.price = price

    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}

    def history(self, symbol, period="1y", interval="1d"):
        # Generate 220 bars of synthetic Stage-2 uptrending data
        dates = pd.date_range(end="2026-10-20", periods=220)
        # Rising price from 50 to 100
        close = np.linspace(50, 100, 220)
        # Add small pullback on the last 3 days to test 20 EMA
        close[-3:] = [98.0, 97.0, 97.5]
        df = pd.DataFrame({
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(220, 100000.0)
        }, index=dates)
        return df


def test_capital_allocation_settings():
    db = DB(":memory:")
    db.init()
    default_alloc = db.get_capital_allocation()
    assert default_alloc["intraday"] == 40.0
    assert default_alloc["swing"] == 40.0
    assert default_alloc["fno"] == 20.0

    # User adjusts allocation
    updated = db.set_capital_allocation(50, 30, 20)
    assert updated["intraday"] == 50.0
    assert updated["swing"] == 30.0
    assert updated["fno"] == 20.0

    retrieved = db.get_capital_allocation()
    assert retrieved["intraday"] == 50.0
    assert retrieved["swing"] == 30.0
    assert retrieved["fno"] == 20.0


def test_swing_scanner_and_pullback_strategy():
    provider = MockProvider(97.5)
    scanner = SwingScanner(provider)
    cand = scanner.scan_symbol("RELIANCE.NS")
    assert cand is not None
    assert cand["product_type"] == "SWING"
    assert cand["score"] >= 70.0

    strat = SwingPullbackStrategy()
    proposal = strat.propose(cand)
    assert proposal is not None
    assert proposal["action"] == "BUY"
    assert proposal["product_type"] == "SWING"
    assert proposal["target"] > proposal["price"]
    assert proposal["stop_loss"] < proposal["price"]
    assert proposal["risk_reward"] >= 2.0


def test_swing_position_exempt_from_intraday_eod_square_off():
    """Verify swing position is NOT closed during 15:10 EOD square-off."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(10000.0, 100000.0)

    cfg = {"execution": {"brokerage": 0.0, "stt_delivery_pct": 0.001, "trailing_stop_atr": 1.5, "max_hold_minutes": 390}}
    intra_exec = PaperExecution(db, cfg)
    swing_exec = SwingExecution(db, cfg)

    # 1. Buy an INTRADAY position
    p_intra = {
        "symbol": "INTRA.NS", "price": 100.0, "stop_loss": 98.0, "target": 104.0,
        "strategy": "ORB", "confidence": 80, "atr": 1.0, "product_type": "INTRADAY"
    }
    assert intra_exec.buy(p_intra, 10, "Bullish")

    # 2. Buy a SWING position
    p_swing = {
        "symbol": "SWING.NS", "price": 200.0, "stop_loss": 190.0, "target": 225.0,
        "strategy": "Swing Pullback", "confidence": 85, "atr": 4.0, "product_type": "SWING"
    }
    assert swing_exec.buy(p_swing, 5)

    all_pos = db.positions()
    assert len(all_pos) == 2

    # 3. Trigger Intraday EOD square-off at 15:20 IST
    intra_pm = PositionManager(db, intra_exec, MockProvider(101.0), cfg)
    eod_time = datetime.fromisoformat("2026-09-15T15:20:00").replace(tzinfo=IST)
    closed = intra_pm.manage(dt=eod_time)

    # Only 1 position (the INTRADAY one) closed!
    assert closed == 1
    remaining = db.positions()
    assert len(remaining) == 1
    assert remaining[0]["symbol"] == "SWING.NS"
    assert remaining[0]["product_type"] == "SWING"


def test_swing_position_manager_target_and_breakeven():
    """Verify swing position holds and manages multi-day profit taking."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(10000.0, 100000.0)

    cfg = {"execution": {"brokerage": 0.0, "stt_delivery_pct": 0.001}}
    swing_exec = SwingExecution(db, cfg)

    p_swing = {
        "symbol": "GROWTH.NS", "price": 100.0, "stop_loss": 95.0, "target": 110.0,
        "strategy": "Swing Pullback", "confidence": 85, "atr": 2.0
    }
    assert swing_exec.buy(p_swing, 10)

    provider = MockProvider(100.0)
    swing_pm = SwingPositionManager(db, swing_exec, provider, cfg)

    # Price moves to 105.0 (+50% to target) -> Breakeven lock triggers
    provider.price = 105.0
    closed = swing_pm.manage()
    assert closed == 0
    pos = db.positions_by_product("SWING")[0]
    assert pos["stop_loss"] >= 100.0  # Risk eliminated!

    # Price moves to 110.0 -> Dynamic Target Expansion triggers
    provider.price = 110.0
    closed = swing_pm.manage()
    assert closed == 0  # Allowed to run
    pos = db.positions_by_product("SWING")[0]
    assert pos["stop_loss"] >= 106.0  # Locked in profit!
    assert pos["target"] == 120.0     # Target expanded!

    # Reversal to 106.0 -> Exits in profit
    provider.price = 106.0
    closed = swing_pm.manage()
    assert closed == 1
    assert len(db.positions_by_product("SWING")) == 0
    trade = db.trades_by_product("SWING")[0]
    assert trade["pnl"] > 0


def test_fno_iron_condor_and_50pct_profit_rule():
    """Verify F&O Defined-Risk Iron Condor strategy and 50% profit-taking rule."""
    chain = IndexChainManager()
    expiry = chain.get_next_expiry()
    assert expiry != ""

    strat = IronCondorStrategy(chain)
    prop = strat.propose("NIFTY")
    assert prop is not None
    assert prop["product_type"] == "FNO"
    assert prop["price"] > 0        # Net credit collected
    assert prop["target"] == prop["price"] * 0.50  # 50% profit rule target

    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    fno_exec = FNOExecution(db)
    assert fno_exec.open_spread(prop)

    pos = db.positions_by_product("FNO")
    assert len(pos) == 1
    assert pos[0]["product_type"] == "FNO"

    # F&O Position Manager with 50% profit rule
    fno_pm = FNOPositionManager(db, fno_exec, chain)

    # Premium decays from entry (e.g. 45.0) down to 20.0 (< 50% target 22.5)
    entry_credit = float(pos[0]["entry_price"])
    decayed_premium = entry_credit * 0.40  # 60% decay
    # Update current premium
    with db.conn() as c:
        c.execute("UPDATE positions SET current_price=? WHERE symbol=?", (decayed_premium, pos[0]["symbol"]))

    closed = fno_pm.manage()
    assert closed == 1
    assert len(db.positions_by_product("FNO")) == 0

    trade = db.trades_by_product("FNO")[0]
    assert trade["exit_reason"] == "50% Profit Target (Theta Decayed)"
    assert trade["pnl"] > 0


def test_market_closed_amo_orders_flow():
    """Verify that when market is closed, orders are queued as AMO instead of immediate fills."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    cfg = {"execution": {"enforce_market_hours": True}}
    swing_exec = SwingExecution(db, cfg)

    # When market is closed (e.g. night hours), buy() queues an AMO
    p = {
        "symbol": "TCS.NS",
        "price": 3500.0,
        "stop_loss": 3400.0,
        "target": 3800.0,
        "strategy": "Swing Pullback",
        "product_type": "SWING"
    }

    # If currently not market open (night time / weekend):
    from app.market_hours import market_open
    if not market_open():
        assert swing_exec.buy(p, 2)
        # Positions must be 0 (no immediate fill at night!)
        assert len(db.positions()) == 0
        # Orders must have 1 pending AMO
        pending = db.pending_orders()
        assert len(pending) == 1
        assert pending[0]["symbol"] == "TCS.NS"
        assert pending[0]["order_type"] == "AMO"
        assert pending[0]["status"] == "PENDING"

        # F&O desk should also queue AMO off-market
        fno_exec = FNOExecution(db, cfg)
        chain = IndexChainManager(MockProvider(22000.0))
        strat = IronCondorStrategy(chain)
        fno_prop = strat.propose("NIFTY")
        assert fno_prop is not None
        assert fno_exec.open_spread(fno_prop, lots=1)
        assert len(db.positions_by_product("FNO")) == 0
        fno_pending = [o for o in db.pending_orders() if str(o.get("product_type", "")).upper() == "FNO"]
        assert len(fno_pending) == 1
        assert fno_pending[0]["order_type"] == "AMO"
        assert fno_pending[0]["status"] == "PENDING"

