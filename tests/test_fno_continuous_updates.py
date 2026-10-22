import pytest
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db import DB
from app.fno.index_chain import IndexChainManager
from app.fno.iron_condor import IronCondorStrategy
from app.fno.execution import FNOExecution
from app.fno.position_manager import FNOPositionManager

IST = ZoneInfo("Asia/Kolkata")


def test_fno_legs_transparency_and_metadata():
    """Verify that every F&O proposal contains full leg transparency, strikes, and explicit symbol tags."""
    chain = IndexChainManager()
    strat = IronCondorStrategy(chain)
    prop = strat.propose("NIFTY")

    assert prop is not None
    assert prop["product_type"] == "FNO"
    assert "CONDOR" in prop["symbol"]
    assert "strikes" in prop
    assert "call_short" in prop["strikes"]
    assert "put_short" in prop["strikes"]
    assert "legs" in prop
    assert len(prop["legs"]) == 4

    # Check each leg has descriptive metadata
    for leg in prop["legs"]:
        assert leg["action"] in ("BUY", "SELL")
        assert leg["type"] in ("CE", "PE")
        assert leg["strike"] > 0
        assert "name" in leg
        assert leg["qty"] >= 25


def test_fno_continuous_rate_updates_across_cycles():
    """Verify that F&O current_price updates dynamically across consecutive cycles and does NOT freeze at entry."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    chain = IndexChainManager()
    strat = IronCondorStrategy(chain)
    prop = strat.propose("NIFTY")
    assert prop is not None

    fno_exec = FNOExecution(db)
    assert fno_exec.open_spread(prop)

    positions = db.positions_by_product("FNO")
    assert len(positions) == 1
    pos = positions[0]
    entry_credit = float(pos["entry_price"])
    assert entry_credit > 0

    # Verify legs_info was persisted in database
    assert pos.get("legs_info") is not None
    legs_data = json.loads(pos["legs_info"])
    assert len(legs_data) == 4

    fno_pm = FNOPositionManager(db, fno_exec, chain)

    # Cycle 1: Evaluation at entry day (0 days held)
    fno_pm.manage()
    pos_cycle1 = db.positions_by_product("FNO")[0]
    # Price was updated in cycle 1
    assert pos_cycle1["current_price"] is not None
    assert pos_cycle1["current_price"] > 0

    # Advance holding time by 2 days
    with db.conn() as c:
        c.execute("UPDATE positions SET days_held=2 WHERE symbol=?", (pos["symbol"],))

    # Cycle 2: Rate must update dynamically reflecting 2 days of theta decay
    fno_pm.manage()
    pos_cycle2 = db.positions_by_product("FNO")[0]
    assert pos_cycle2["current_price"] is not None
    # With 2 days decay, the premium should have decayed compared to entry
    assert pos_cycle2["current_price"] < entry_credit
    assert pos_cycle2["current_price"] != entry_credit  # NOT frozen!

    # Advance to 5 days held -> decay reaches >= 50% target
    with db.conn() as c:
        c.execute("UPDATE positions SET days_held=5 WHERE symbol=?", (pos["symbol"],))

    closed = fno_pm.manage()
    assert closed == 1
    # Position auto-closed into trade log!
    remaining = db.positions_by_product("FNO")
    assert len(remaining) == 0

    trades = db.trades_by_product("FNO")
    assert len(trades) == 1
    trade = trades[0]
    assert "50% Profit Target" in trade["exit_reason"]
    assert trade["pnl"] > 0
