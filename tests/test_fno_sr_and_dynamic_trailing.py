"""
Tests for F&O Dynamic Support & Resistance (S/R) Calculator,
regime gating, 2-second price tracking, and dynamic trailing stop loss.
"""
import pytest
from app.db import DB
from app.fno.index_chain import IndexChainManager
from app.fno.sr_levels import IndexSRCalculator
from app.fno.iron_condor import IronCondorStrategy
from app.fno.execution import FNOExecution
from app.fno.position_manager import FNOPositionManager


class MockProvider:
    def __init__(self, price: float = 24850.0):
        self.price = price

    def quote(self, symbol: str):
        return {"price": self.price, "symbol": symbol}


def test_index_sr_calculator_levels():
    """Verify S/R calculator generates accurate Classic and Fibonacci levels."""
    calc = IndexSRCalculator(MockProvider(24850.0))
    levels = calc.calculate_levels("NIFTY", 24850.0)

    assert levels["index"] == "NIFTY"
    assert levels["spot"] == 24850.0
    assert levels["resistance_1"] > levels["pivot"]
    assert levels["support_1"] < levels["pivot"]
    assert levels["resistance_2"] > levels["resistance_1"]
    assert levels["support_2"] < levels["support_1"]
    assert levels["structure"] in {"CONSOLIDATION_BOX", "BULLISH_BREAKOUT", "BEARISH_BREAKDOWN", "TESTING_BOUNDARY"}


def test_fno_regime_gating_rejects_strong_trend():
    """Verify IronCondorStrategy rejects strong trending regimes to avoid wing blowout."""
    chain = IndexChainManager(MockProvider(24850.0))
    strat = IronCondorStrategy(chain)

    # Strong trending markets must stand down
    prop_bear = strat.propose("NIFTY", market_regime="Strong Bearish")
    assert prop_bear is None

    prop_bull = strat.propose("NIFTY", market_regime="Strong Bullish Breakout")
    assert prop_bull is None

    # Neutral or sideways market proposes safe defined-risk spread
    prop_neutral = strat.propose("NIFTY", market_regime="Neutral")
    assert prop_neutral is not None
    assert "CONDOR" in prop_neutral["symbol"]
    assert prop_neutral["strike_price"] > 0


def test_fno_dynamic_trailing_stop_loss_tiers():
    """Verify dynamic trailing stop ratchets: Tier 1 at +25% profit (breakeven), Tier 2 at +40% (locks +20%)."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    chain = IndexChainManager(MockProvider(24850.0))
    fno_exec = FNOExecution(db)
    strat = IronCondorStrategy(chain)

    proposal = strat.propose("NIFTY", market_regime="Neutral")
    assert proposal is not None
    entry_credit = float(proposal["price"])  # e.g. 45.0
    initial_sl = float(proposal["stop_loss"]) # 2x credit = 90.0

    assert fno_exec.open_spread(proposal, lots=1, force_fill=True)
    pos = db.positions_by_product("FNO")[0]
    assert pos["stop_loss"] == initial_sl

    pm = FNOPositionManager(db, fno_exec, chain)

    # 1. Tier 1 Trailing: Premium decays by 25% (current_price <= 45 * 0.75 = 33.75)
    db.update_current_price(pos["symbol"], round(entry_credit * 0.74, 2))
    pm.manage()
    updated_pos = db.positions_by_product("FNO")[0]
    # Stop loss moved to entry credit (breakeven lock)
    assert updated_pos["stop_loss"] == entry_credit

    # 2. Tier 2 Trailing: Premium decays by 40% (current_price <= 45 * 0.60 = 27.0)
    db.update_current_price(pos["symbol"], round(entry_credit * 0.58, 2))
    pm.manage()
    updated_pos2 = db.positions_by_product("FNO")[0]
    # Stop loss moved to 80% of entry credit (locks in 20% profit)
    assert updated_pos2["stop_loss"] == round(entry_credit * 0.80, 2)

    # 3. Target Hit: Premium decays by 50% (current_price <= target = 22.5)
    db.update_current_price(pos["symbol"], round(entry_credit * 0.49, 2))
    closed = pm.manage()
    assert closed == 1
    assert len(db.positions_by_product("FNO")) == 0
    trade = db.trades_by_product("FNO")[0]
    assert "Profit Target" in trade["exit_reason"]
    assert trade["pnl"] > 0


def test_fno_dynamic_sr_defense_exit():
    """Verify early defense square-off triggers if spot severely violates S/R boundaries."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(50000.0, 100000.0)

    provider = MockProvider(24850.0)
    chain = IndexChainManager(provider)
    fno_exec = FNOExecution(db)
    strat = IronCondorStrategy(chain)

    proposal = strat.propose("NIFTY", market_regime="Neutral")
    assert proposal is not None
    assert fno_exec.open_spread(proposal, lots=1, force_fill=True)

    pm = FNOPositionManager(db, fno_exec, chain)

    # Market gap crashes spot down below S1 support by 1.5%
    sr = IndexSRCalculator(provider).calculate_levels("NIFTY", 24850.0)
    s1 = sr["support_1"]
    provider.price = s1 * 0.985  # Severe breakdown

    closed = pm.manage()
    assert closed == 1
    assert len(db.positions_by_product("FNO")) == 0
    trade = db.trades_by_product("FNO")[0]
    assert "Dynamic S/R Defense" in trade["exit_reason"]
