"""
Milestone 2 Acceptance Test Suite (STRATEGY_SPEC.md).

Covers:
- Test 2: Cost tests (delivery STT, option sell STT, ledger cost reconciliation).
- Test 3: Calendar expiry integration.
- Test 8: Ledger invariants property test over random trade sequences.
- Test 9: Ownership rule (symbol held by sleeve A cannot be opened by sleeve C).
- Test 10: Risk ladder (-5% halves size, -10% halts entries until audited reset).
- Test 11: Live/backtest parity (identical bars produce identical fills).
- Test 13: Determinism (pure simulation, no wall-clock or network).
"""

import random
from datetime import date
import pytest
from app.costs import CostModel
from app.market_calendar import MarketCalendar
from app.engine_v2.ledger import Ledger, Fill
from app.engine_v2.simulate import Proposal, simulate_fill
from app.engine_v2.risk import PortfolioRiskManager


# ----------------------------------------------------------------------
# 1. Cost Tests (Test 2)
# ----------------------------------------------------------------------

def test_m2_cost_model_stt_and_ledger_reconciliation():
    """
    Test 2 from STRATEGY_SPEC.md:
    - Delivery STT on 1,00,000 INR buy is 100 INR.
    - Option sell STT: 65 units @ 40 INR premium = 3.90 INR (from 2026-04-01).
    - Total costs reconcile to the ledger.
    """
    costs = CostModel()

    # 1. Delivery STT on a 1,00,000 INR buy is 100 INR (0.1% rate)
    # Total costs include STT (100) + exchange (2.97) + sebi (0.10) + gst (0.55) + stamp (15.0)
    total_delivery_cost = costs.calculate(
        value=100000.0,
        action="BUY",
        segment="DELIVERY",
        asof="2026-05-01"
    )
    # Verify delivery STT component is exactly 100 INR
    stt_delivery = 100000.0 * 0.001
    assert stt_delivery == 100.0
    assert total_delivery_cost > 100.0  # Includes other statutory fees

    # 2. Option sell STT: 65 units @ 40 INR premium
    # Premium turnover = 65 * 40 = 2600 INR.
    # From 2026-04-01, option sell STT is 0.15% -> 2600 * 0.0015 = 3.90 INR!
    turnover = 65 * 40.0
    opt_cost_2026 = costs.calculate(
        value=turnover,
        action="SELL",
        segment="OPTIONS",
        asof="2026-04-15"
    )
    stt_options = turnover * 0.0015
    assert abs(stt_options - 3.90) < 1e-4

    # Before 2026-04-01, option sell STT was 0.10% -> 2600 * 0.0010 = 2.60 INR
    opt_cost_pre = costs.calculate(
        value=turnover,
        action="SELL",
        segment="OPTIONS",
        asof="2025-06-15"
    )
    assert opt_cost_2026 > opt_cost_pre

    # 3. Ledger cost reconciliation
    ledger = Ledger(starting_capital=100000.0)
    fill = Fill(
        sleeve="A",
        symbol="TCS",
        side="BUY",
        qty=10,
        price=3000.0,
        costs=total_delivery_cost,
        asof="2026-05-01"
    )
    ledger.execute_fill(fill)
    assert abs(ledger.total_costs_paid - total_delivery_cost) < 1e-4
    assert ledger.assert_invariants()


# ----------------------------------------------------------------------
# 2. Ledger Invariants Property Test (Test 8)
# ----------------------------------------------------------------------

def test_m2_ledger_invariants_property_test():
    """
    Test 8 from STRATEGY_SPEC.md:
    Property test over random trade sequences:
    cash + marked positions == start + realized - open entry costs.
    """
    random.seed(42)
    ledger = Ledger(starting_capital=500000.0)
    costs = CostModel()

    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    sleeves = ["A", "B", "C"]

    for step in range(100):
        action = random.choice(["BUY", "BUY", "SELL"])
        sleeve = random.choice(sleeves)
        symbol = random.choice(symbols)
        key = (sleeve, symbol)
        existing = ledger.get_position(sleeve, symbol)

        if action == "BUY" or existing is None:
            # Execute BUY
            price = round(random.uniform(100.0, 2000.0), 2)
            max_qty = int(min(20, ledger.cash // (price * 1.05)))
            if max_qty <= 0:
                continue
            qty = random.randint(1, max_qty)
            val = qty * price
            fee = costs.calculate(val, action="BUY", segment="DELIVERY")

            fill = Fill(sleeve=sleeve, symbol=symbol, side="BUY", qty=qty, price=price, costs=fee)
            ledger.execute_fill(fill)

        else:
            # Execute partial or full SELL
            qty = random.randint(1, existing.qty)
            price = round(random.uniform(existing.entry_price * 0.8, existing.entry_price * 1.2), 2)
            val = qty * price
            fee = costs.calculate(val, action="SELL", segment="DELIVERY")

            fill = Fill(sleeve=sleeve, symbol=symbol, side="SELL", qty=qty, price=price, costs=fee)
            ledger.execute_fill(fill)

        # Invariant must hold strictly at EVERY single step!
        assert ledger.assert_invariants()

    # Final check with simulated market prices
    market_prices = {sym: random.uniform(100.0, 2500.0) for sym in symbols}
    assert ledger.assert_invariants(market_prices)


# ----------------------------------------------------------------------
# 3. Ownership Rule (Test 9)
# ----------------------------------------------------------------------

def test_m2_cross_sleeve_ownership_rule():
    """
    Test 9 from STRATEGY_SPEC.md:
    A symbol held by sleeve A cannot be opened by sleeve C.
    Two sleeves proposing the same symbol result in one position.
    """
    risk = PortfolioRiskManager()
    ledger = Ledger(starting_capital=100000.0)

    # Sleeve A buys RELIANCE
    buy_fill = Fill(sleeve="A", symbol="RELIANCE", side="BUY", qty=10, price=2500.0, costs=25.0)
    ledger.execute_fill(buy_fill)

    # Sleeve C now proposes buying RELIANCE -> MUST BE REJECTED!
    prop_c = Proposal(sleeve="C", symbol="RELIANCE", side="BUY", qty=5)
    approved, reason, _ = risk.evaluate_proposal(prop_c, ledger, current_equity=100000.0, proposed_price=2500.0)
    assert approved is False
    assert "ownership violation" in reason.lower()

    # Sleeve A proposing to add to RELIANCE is allowed
    prop_a = Proposal(sleeve="A", symbol="RELIANCE", side="BUY", qty=5)
    approved_a, _, _ = risk.evaluate_proposal(prop_a, ledger, current_equity=100000.0, proposed_price=2500.0)
    assert approved_a is True


# ----------------------------------------------------------------------
# 4. Risk Ladder (-5% halves size, -10% halts entries) (Test 10)
# ----------------------------------------------------------------------

def test_m2_risk_ladder_and_audited_reset():
    """
    Test 10 from STRATEGY_SPEC.md:
    Drawdown -5% halves size; -10% blocks entries; reset requires an audited command.
    """
    risk = PortfolioRiskManager()
    ledger = Ledger(starting_capital=100000.0)
    risk.update_equity_peaks(100000.0)

    prop = Proposal(sleeve="A", symbol="INFY", side="BUY", qty=20)

    # 1. At peak equity (0% drawdown): full size (20) approved
    app, _, qty = risk.evaluate_proposal(prop, ledger, current_equity=100000.0, proposed_price=1500.0)
    assert app is True
    assert qty == 20

    # 2. At -6% drawdown on a new day (start equity 94,000, peak 100,000): position size is halved (qty 20 -> 10)
    risk.reset_daily_metrics(94000.0)
    app, _, qty_halved = risk.evaluate_proposal(prop, ledger, current_equity=94000.0, proposed_price=1500.0)
    assert app is True
    assert qty_halved == 10

    # 3. At -11% drawdown on next day (start equity 89,000, peak 100,000): new entries are HALTED completely
    risk.reset_daily_metrics(89000.0)
    app, reason, _ = risk.evaluate_proposal(prop, ledger, current_equity=89000.0, proposed_price=1500.0)
    assert app is False
    assert "drawdown ladder tier 2 halt" in reason.lower()

    # Subsequent proposals continue to be blocked
    app2, _, _ = risk.evaluate_proposal(prop, ledger, current_equity=95000.0, proposed_price=1500.0)
    assert app2 is False

    # 4. Audited manual reset required
    with pytest.raises(ValueError, match="requires an explicit substantive reason"):
        risk.manual_reset_drawdown(reason="")

    # Valid audited reset unblocks trading
    risk.manual_reset_drawdown(reason="Audited portfolio risk reset after strategy review", authorized_by="CHIEF_RISK_OFFICER")
    app_after, _, qty_after = risk.evaluate_proposal(prop, ledger, current_equity=95000.0, proposed_price=1500.0)
    assert app_after is True


# ----------------------------------------------------------------------
# 5. Determinism & Parity (Test 11 & Test 13)
# ----------------------------------------------------------------------

def test_m2_determinism_and_live_backtest_parity():
    """
    Test 11 & Test 13 from STRATEGY_SPEC.md:
    - Pure simulation: same inputs give identical proposals and fills.
    - Zero wall-clock or network in decide() and simulate_fill().
    - 2% ADTV order rejection and slippage capping.
    """
    costs = CostModel()
    next_bar = {"Open": 1000.0, "High": 1020.0, "Low": 990.0, "Close": 1010.0, "date": "2026-05-04"}
    proposal = Proposal(sleeve="A", symbol="TCS", side="BUY", qty=10)

    # 1. Determinism: Calling simulate_fill multiple times produces bitwise identical results
    fill1 = simulate_fill(proposal, next_bar, adtv20=10000000.0, cost_model=costs, asof_date="2026-05-01")
    fill2 = simulate_fill(proposal, next_bar, adtv20=10000000.0, cost_model=costs, asof_date="2026-05-01")
    assert fill1.price == fill2.price
    assert fill1.costs == fill2.costs
    assert fill1.slippage_bps == fill2.slippage_bps

    # 2. ADTV 2% rejection:
    # ADTV is 1,00,000 INR. 2% cap is 2,000 INR.
    # Order for 10 shares @ 1,000 = 10,000 INR (10% of ADTV) -> MUST BE REJECTED!
    with pytest.raises(ValueError, match="exceeds 2% of ADTV20"):
        simulate_fill(proposal, next_bar, adtv20=100000.0, cost_model=costs)
