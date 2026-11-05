"""
Institutional Execution Guardrail Tests.
Guarantees:
1. Zero off-market executions across all desks (F&O, Swing, Intraday).
2. Opening settlement freeze (09:15-09:17 IST) shields positions from opening tick noise.
3. Realistic stop-loss slippage cap prevents unbounded 3x mark-to-market penalties.
4. Catch-up close specifically permits EOD clearing while general executions remain barred.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from app.db import DB
from app.fno.execution import FNOExecution
from app.swing.execution import SwingExecution
from app.execution import PaperExecution
from app.fno.position_manager import FNOPositionManager
from app.fno.index_chain import IndexChainManager

IST = ZoneInfo("Asia/Kolkata")


class MockChain:
    def __init__(self, spot: float = 24000.0):
        self.spot = spot

    def get_spot_price(self, index_name="NIFTY"):
        return self.spot

    def round_strike(self, spot, index_name="NIFTY"):
        return int(round(spot / 50) * 50)


def test_fno_execution_rejects_off_market_close(monkeypatch):
    """F&O Execution engine must refuse to close positions when exchange is closed."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    cfg = {"execution": {"enforce_market_hours": True}}
    fno_exec = FNOExecution(db, cfg)

    # Insert a dummy FNO position
    with db.conn() as c:
        c.execute("""
            INSERT INTO positions(sleeve, symbol, side, qty, entry_price, current_price,
                                 product_type, entry_cost, opened_at)
            VALUES('core', 'NIFTY-TEST-CONDOR', 'SELL', 25, 45.0, 45.0, 'FNO', 2500.0, '2026-11-05T04:00:00+00:00')
        """)

    # Mock market as CLOSED
    import app.market_hours as mh
    monkeypatch.setattr(mh, "market_open", lambda dt=None: False)

    # Attempt to close off-market -> MUST BE REJECTED
    success = fno_exec.close("NIFTY-TEST-CONDOR", 50.0, "Test Close", force=False)
    assert success is False

    # Position must still exist in DB
    positions = db.positions_by_product("FNO")
    assert len(positions) == 1

    # Force override (admin / catchup) is allowed
    success_forced = fno_exec.close("NIFTY-TEST-CONDOR", 50.0, "Forced Close", force=True)
    assert success_forced is True
    assert len(db.positions_by_product("FNO")) == 0


def test_swing_execution_rejects_off_market_close(monkeypatch):
    """Swing Execution engine must refuse to close delivery positions when exchange is closed."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    cfg = {"execution": {"enforce_market_hours": True}}
    swing_exec = SwingExecution(db, cfg)

    with db.conn() as c:
        c.execute("""
            INSERT INTO positions(sleeve, symbol, side, qty, entry_price, current_price,
                                 product_type, entry_cost, opened_at)
            VALUES('core', 'RELIANCE.NS', 'LONG', 10, 2500.0, 2500.0, 'SWING', 25.0, '2026-11-05T04:00:00+00:00')
        """)

    import app.market_hours as mh
    monkeypatch.setattr(mh, "market_open", lambda dt=None: False)

    success = swing_exec.close("RELIANCE.NS", 2480.0, "Stop Loss", force=False)
    assert success is False
    assert len(db.positions_by_product("SWING")) == 1

    # Forced exit succeeds
    assert swing_exec.close("RELIANCE.NS", 2480.0, "Forced Stop Loss", force=True) is True
    assert len(db.positions_by_product("SWING")) == 0


def test_paper_execution_rejects_off_market_close(monkeypatch):
    """Core Paper Execution engine must refuse to close positions when exchange is closed."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    cfg = {"execution": {"enforce_market_hours": True}}
    paper_exec = PaperExecution(db, cfg)

    with db.conn() as c:
        c.execute("""
            INSERT INTO positions(sleeve, symbol, side, qty, entry_price, current_price,
                                 product_type, entry_cost, opened_at)
            VALUES('core', 'TCS.NS', 'LONG', 5, 4000.0, 4000.0, 'INTRADAY', 20.0, '2026-11-05T04:00:00+00:00')
        """)

    import app.market_hours as mh
    monkeypatch.setattr(mh, "market_open", lambda dt=None: False)

    success = paper_exec.close("TCS.NS", 3980.0, "Stop Loss", "INTRADAY", force=False)
    assert success is False
    assert len(db.positions()) == 1

    # Catchup / force close succeeds
    assert paper_exec.close("TCS.NS", 3980.0, "Catchup close", "INTRADAY", force=True) is True
    assert len(db.positions()) == 0


def test_fno_opening_settlement_protects_against_gap_spikes():
    """Verify that during 09:15-09:17 IST opening settlement, option stops do NOT fire prematurely."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    fno_exec = FNOExecution(db)
    chain = MockChain(24000.0)

    # Insert position with 45.0 entry, 90.0 stop loss
    with db.conn() as c:
        c.execute("""
            INSERT INTO positions(sleeve, symbol, side, qty, entry_price, current_price,
                                 stop_loss, target, product_type, entry_cost, opened_at, expiry_date)
            VALUES('core', 'NIFTY-OPEN-TEST', 'SELL', 25, 45.0, 110.0,
                   90.0, 22.5, 'FNO', 2625.0, '2026-11-04T08:00:00+00:00', '2026-11-12')
        """)

    pm = FNOPositionManager(db, fno_exec, chain)

    # Evaluate at 09:16:00 IST (during opening settlement)
    open_dt = datetime(2026, 11, 5, 9, 16, 0, tzinfo=IST)
    closed = pm.manage(dt=open_dt)

    # MUST NOT CLOSE: Protected by opening settlement window
    assert closed == 0
    assert len(db.positions_by_product("FNO")) == 1

    # Evaluate after opening settlement at 09:18:00 IST -> Now evaluates and exits
    post_open_dt = datetime(2026, 11, 5, 9, 18, 0, tzinfo=IST)
    closed_after = pm.manage(dt=post_open_dt)
    assert closed_after == 1
    assert len(db.positions_by_product("FNO")) == 0


def test_fno_stop_loss_slippage_is_capped_at_ten_percent():
    """Verify that stop loss exit fills near contractual stop price with slippage capped at 10%."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    fno_exec = FNOExecution(db)
    chain = MockChain(24000.0)

    # Current premium has expanded to 135.0 (3x credit), but stop loss is 90.0
    with db.conn() as c:
        c.execute("""
            INSERT INTO positions(sleeve, symbol, side, qty, entry_price, current_price,
                                 stop_loss, target, product_type, entry_cost, opened_at, expiry_date)
            VALUES('core', 'NIFTY-SLIP-TEST', 'SELL', 25, 45.0, 135.0,
                   90.0, 22.5, 'FNO', 2625.0, '2026-11-04T08:00:00+00:00', '2026-11-12')
        """)

    pm = FNOPositionManager(db, fno_exec, chain)

    # Evaluate at 10:00:00 IST
    dt = datetime(2026, 11, 5, 10, 0, 0, tzinfo=IST)
    closed = pm.manage(dt=dt)
    assert closed == 1

    # Verify recorded trade exit price is capped at 90.0 * 1.10 = 99.0, NOT 135.0
    trades = db.trades_by_product("FNO")
    assert len(trades) == 1
    trade = trades[0]
    assert trade["exit_price"] == 99.0
    assert trade["pnl"] == -1400.0  # (45 - 99) * 25 - 50 fee = -1400.0
