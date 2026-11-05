"""
Institutional Test Suite:
1. Intraday Breakeven & Fee-Covered Expectancy Invariant (Fix for ₹2-3 profit vs ₹20-30 loss bug).
2. Strategy Router & Meta-Decision Selector across F&O, Intraday, and Swing.
3. Directional Debit Spreads (Bull Call / Bear Put) for F&O.
"""
import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

from app.db import DB
from app.execution import PaperExecution
from app.intraday.position_manager import IntradayPositionManager
from app.strategy_router import DeskStrategyRouter
from app.fno.debit_spreads import DirectionalDebitSpreadStrategy
from app.fno.iron_condor import IronCondorStrategy
from app.intraday.vwap_pullback import VWAPPullbackStrategy
from app.swing.momentum_breakout import SwingMomentumBreakoutStrategy

IST = ZoneInfo("Asia/Kolkata")


class MockQuoteProvider:
    def __init__(self, price=1000.0):
        self.price = price

    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}


def test_intraday_breakeven_does_not_choke_on_minor_moves():
    """
    Verify that an intraday position does NOT move stop to breakeven on minor gains (+0.6%),
    allowing the trade to breathe through normal intraday market noise.
    """
    db = DB(":memory:")
    db.ensure_account(100000.0, 500000.0)
    cfg = {
        "execution": {
            "slippage_bps": 5, "trailing_stop_atr": 3.2,
            "breakeven_lock_ratio": 0.65, "dynamic_target_expansion": True
        }
    }
    exec_engine = PaperExecution(db, cfg)

    # Buy at 1000.0, Stop 980.0 (-2%), Target 1030.0 (+3%)
    proposal = {
        "symbol": "RUNNER.NS", "price": 1000.0, "stop_loss": 980.0,
        "target": 1030.0, "strategy": "Intraday ORB", "confidence": 80.0, "atr": 10.0
    }
    assert exec_engine.buy(proposal, 10, "Bullish")

    provider = MockQuoteProvider(1000.0)
    pm = IntradayPositionManager(db, exec_engine, provider, cfg)

    # Move price to 1006.0 (+0.6% gain).
    # Under old logic, this choked the trade to breakeven! Under institutional logic, SL stays at 980.0.
    provider.price = 1006.0
    closed = pm.manage()
    assert closed == 0

    pos = db.positions()[0]
    assert pos["stop_loss"] == 980.0, "Stop loss must not choke trade on minor +0.6% noise!"

    # Move price to 1020.0 (progress >= 65% of 30pt target step = 19.5pts).
    # NOW breakeven triggers, moving stop to entry * 1.0035 = 1003.50 (cost covered!).
    provider.price = 1020.0
    closed = pm.manage()
    assert closed == 0

    pos = db.positions()[0]
    assert pos["stop_loss"] >= 1003.50, "Cost-covering breakeven must cover statutory transaction costs and slippage!"


def test_intraday_cost_covering_stop_guarantees_positive_profit():
    """
    Verify that if a trade gets stopped out at the cost-covering breakeven stop,
    the net realized PnL is strictly positive and tagged accurately as 'Breakeven cost-cover'.
    """
    db = DB(":memory:")
    db.ensure_account(100000.0, 500000.0)
    cfg = {
        "execution": {
            "slippage_bps": 0, "trailing_stop_atr": 3.2,
            "breakeven_lock_ratio": 0.65
        }
    }
    exec_engine = PaperExecution(db, cfg)

    # Buy at 1000.0, Target 1030.0
    proposal = {
        "symbol": "WINNER.NS", "price": 1000.0, "stop_loss": 980.0,
        "target": 1030.0, "strategy": "Intraday ORB", "confidence": 80.0, "atr": 10.0
    }
    assert exec_engine.buy(proposal, 10, "Bullish")

    provider = MockQuoteProvider(1020.0)
    pm = IntradayPositionManager(db, exec_engine, provider, cfg)
    pm.manage()  # Moves stop to 1003.50

    pos = db.positions()[0]
    be_stop = pos["stop_loss"]
    assert be_stop >= 1003.50

    # Price pulls back and hits the cost-covering stop
    provider.price = be_stop
    closed = pm.manage()
    assert closed == 1

    trades = db.trades()
    assert len(trades) == 1
    t = trades[0]
    assert t["exit_reason"] == "Breakeven cost-cover"
    assert t["pnl"] > 0, "Realized PnL must be strictly positive at cost-covering stop!"


def test_fno_directional_debit_spreads():
    """
    Verify F&O Directional Debit Spread proposals (Bull Call & Bear Put).
    """
    strat = DirectionalDebitSpreadStrategy()

    # In trending bull regime
    context_bull = {"regime": "Bullish Trending", "adx": 30.0, "pcr": 1.35, "spot": 24000.0}
    fitness = strat.evaluate_market_fitness(context_bull)
    assert fitness >= 0.80, "Debit spreads must have high fitness in trending regimes!"

    prop_bull = strat.propose("NIFTY", context=context_bull)
    assert prop_bull is not None
    assert prop_bull["action"] == "BUY"
    assert "Bull Call Spread" in prop_bull["strategy"]
    assert prop_bull["spread_type"] == "DEBIT"
    assert len(prop_bull["legs"]) == 2
    assert prop_bull["legs"][0]["action"] == "BUY"
    assert prop_bull["legs"][1]["action"] == "SELL"

    # In trending bear regime
    context_bear = {"regime": "Bearish Trending", "adx": 32.0, "pcr": 0.65, "spot": 24000.0}
    prop_bear = strat.propose("NIFTY", context=context_bear)
    assert prop_bear is not None
    assert "Bear Put Spread" in prop_bear["strategy"]
    assert prop_bear["spread_type"] == "DEBIT"


def test_strategy_router_selection():
    """
    Verify Strategy Router dispatches optimal strategy according to regime & metrics.
    """
    router = DeskStrategyRouter()

    # 1. Low ADX / Range-bound market -> F&O should select Iron Condor / Credit Spreads (Decay)
    range_ctx = {"regime": "Consolidation Range", "adx": 16.0, "pcr": 1.0}
    best_fno_range = router.select_best_strategy("FNO", range_ctx)
    assert isinstance(best_fno_range, IronCondorStrategy)

    # 2. High ADX / Strong Breakout -> F&O should select Directional Debit Spreads
    trend_ctx = {"regime": "Bullish Trending", "adx": 35.0, "pcr": 1.4}
    best_fno_trend = router.select_best_strategy("FNO", trend_ctx)
    assert isinstance(best_fno_trend, DirectionalDebitSpreadStrategy)

    # 3. Swing selection
    swing_trend = router.select_best_strategy("SWING", trend_ctx)
    assert swing_trend is not None

    # 4. Verify route_swing conforms to BaseDeskStrategy.propose(symbol, context=...)
    pullback_ctx = {
        "regime": "Pullback", "adx": 20.0,
        "candidate": {"symbol": "TCS.NS", "price": 4000.0, "ema_20": 3950.0, "atr": 40.0, "score": 85.0}
    }
    swing_prop = router.route_swing("TCS.NS", context=pullback_ctx)
    assert swing_prop is not None
    assert swing_prop["symbol"] == "TCS.NS"
    assert swing_prop["action"] == "BUY"
    assert swing_prop["stop_loss"] < 4000.0
    assert swing_prop["target"] > 4000.0
