import pytest
import numpy as np

from app.risk_engine import (
    VolatilityTargetedSizer,
    MinimumMoveGate,
    PortfolioHeatLimiter,
    StrategyDriftKillSwitch
)
from app.costs import CostModel


def test_volatility_targeted_sizing_grid():
    sizer = VolatilityTargetedSizer(target_risk_pct=0.02, atr_multiplier=1.5, max_position_pct=0.20)

    # 1. Micro Account: ₹1,000 equity, ₹100 stock, ATR = 2.0 (risk per share = 3.0)
    # Risk budget = 1000 * 0.02 = ₹20. Qty = 20 / 3 = 6 shares. Max position = 200 / 100 = 2 shares.
    qty_micro = sizer.size(equity=1000.0, price=100.0, atr=2.0)
    assert qty_micro == 2

    # 2. Institutional/Realistic Account: ₹2,00,000 equity, ₹500 stock, ATR = 10.0 (risk = 15.0)
    # Risk budget = 200,000 * 0.02 = ₹4,000. Qty = 4000 / 15 = 266 shares. Max position = 40000 / 500 = 80 shares.
    qty_real = sizer.size(equity=200000.0, price=500.0, atr=10.0)
    assert qty_real == 80

    # 3. High Volatility Stock (ATR doubles from 10 to 20) -> Position size must decrease!
    qty_high_vol = sizer.size(equity=200000.0, price=500.0, atr=20.0)
    # Risk = 30.0. Qty = 4000 / 30 = 133 shares. (vs 266)
    assert qty_high_vol <= qty_real


def test_minimum_move_vs_cost_gate():
    cm = CostModel()
    gate = MinimumMoveGate(cost_multiplier=3.0, cost_model=cm)

    # ₹100 stock with ₹0.05 expected move (cost will eat up entire profit)
    ok_tiny, reason_tiny = gate.check(price=100.0, target=100.05, stop_loss=99.5, action="BUY")
    assert ok_tiny is False
    assert "round-trip cost" in reason_tiny

    # ₹100 stock with ₹3.00 expected move (healthy 3% gain far exceeds ~₹0.05 charges)
    ok_good, _ = gate.check(price=100.0, target=103.0, stop_loss=98.5, action="BUY")
    assert ok_good is True


def test_portfolio_heat_limiter():
    limiter = PortfolioHeatLimiter(max_heat_pct=0.05, max_sector_pct=0.40)
    equity = 100000.0  # Max heat = 5000.0

    # Existing position with 200 at risk, 15000 notional in IT
    open_pos = [{
        "symbol": "INFY.NS", "side": "LONG", "qty": 10,
        "entry_price": 1500.0, "current_price": 1500.0, "stop_loss": 1480.0, "sector": "IT"
    }]

    # New proposal risking 250, 16000 notional in IT (total sector 31000 <= 40000, heat 450 <= 5000) -> Pass
    p1 = {"symbol": "TCS.NS", "price": 3200.0, "stop_loss": 3150.0, "sector": "IT"}
    ok1, _ = limiter.check(equity, open_pos, p1, new_qty=5)
    assert ok1 is True

    # New proposal risking 6000 (total heat 6200 > 5000, sector 30000 <= 40000) -> Rejection by heat
    p2 = {"symbol": "RELIANCE.NS", "price": 2500.0, "stop_loss": 2000.0, "sector": "Energy"}
    ok2, reason2 = limiter.check(equity, open_pos, p2, new_qty=12)
    assert ok2 is False
    assert "heat" in reason2


def test_strategy_drift_kill_switch_simulated_degradation():
    kill_switch = StrategyDriftKillSwitch(rolling_window=10, min_trades=5)
    strat = "TrendFollower"
    kill_switch.register_baseline(strat, lower_bound=0.0)

    # 1. Healthy performance (positive expectancy)
    for _ in range(8):
        kill_switch.record_trade(strat, pnl=150.0)
    paused, _ = kill_switch.is_paused(strat)
    assert paused is False

    # 2. Simulated performance degradation (consecutive losses dragging rolling expectancy below 0)
    for _ in range(10):
        kill_switch.record_trade(strat, pnl=-250.0)

    paused_deg, reason_deg = kill_switch.is_paused(strat)
    assert paused_deg is True
    assert "performance drift" in reason_deg
