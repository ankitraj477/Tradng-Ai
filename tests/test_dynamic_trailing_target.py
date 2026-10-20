import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from app.db import DB
from app.execution import PaperExecution
from app.position_manager import PositionManager

IST = ZoneInfo("Asia/Kolkata")

class MutableQuoteProvider:
    def __init__(self, price=7.0):
        self.price = price
    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}


def test_user_scenario_dynamic_target_and_stop_expansion():
    """
    Test user's exact specification:
    Bought at 7rs, SL is 5, Target 10.
    When price reaches 10, SL ratchets to 9 and Target expands to 13.
    When price reaches 13, SL ratchets to 12 and Target expands to 16.
    When price pulls back to 12, SL triggers and locks in +5rs profit!
    """
    cfg = {
        "execution": {
            "slippage_bps": 0, "brokerage": 0, "sebi_turnover_fee_pct": 0,
            "gst_pct": 0, "stamp_duty_non_delivery_pct": 0, "stt_intraday_sell_pct": 0,
            "trailing_stop_atr": 1.5, "max_hold_minutes": 390,
            "dynamic_target_expansion": True,
            "breakeven_lock_ratio": 0.50,
            "trailing_buffer_ratio": 1.0 / 3.0
        }
    }
    db = DB(":memory:")
    db.ensure_account(1000.0, 100000.0)
    exec_engine = PaperExecution(db, cfg)

    # Buy at 7.0, SL 5.0, Target 10.0 (Step = 3.0, Buffer = 1.0)
    proposal = {
        "symbol": "PENNY.NS", "action": "BUY", "price": 7.0,
        "stop_loss": 5.0, "target": 10.0, "strategy": "Momentum", "confidence": 90, "atr": 0.0
    }
    assert exec_engine.buy(proposal, 10, "Bullish")

    pos = db.positions()[0]
    assert pos["entry_price"] == 7.0
    assert pos["stop_loss"] == 5.0
    assert pos["target"] == 10.0

    provider = MutableQuoteProvider(7.0)
    pm = PositionManager(db, exec_engine, provider, cfg)

    # 1. Price at 8.0: Position unchanged, neither target nor breakeven 8.5 hit
    provider.price = 8.0
    closed = pm.manage()
    assert closed == 0
    pos = db.positions()[0]
    assert pos["stop_loss"] == 5.0

    # 2. Price at 8.5: Breakeven lock triggers! (50% of 10 - 7 = 1.5)
    provider.price = 8.5
    closed = pm.manage()
    assert closed == 0
    pos = db.positions()[0]
    assert pos["stop_loss"] >= 7.0  # Ratcheted to breakeven!

    # 3. Price reaches 10.0: Target hit! Dynamic Target Expansion fires!
    provider.price = 10.0
    closed = pm.manage()
    assert closed == 0  # Position is NOT closed!
    pos = db.positions()[0]
    # Exact match to user request: SL becomes 9.0, Target becomes 13.0
    assert pos["stop_loss"] == 9.0
    assert pos["target"] == 13.0

    # 4. Price advances to 11.5: Position intact, SL remains at 9.0
    provider.price = 11.5
    closed = pm.manage()
    assert closed == 0
    pos = db.positions()[0]
    assert pos["stop_loss"] == 9.0
    assert pos["target"] == 13.0

    # 5. Price reaches 13.0: Next milestone!
    provider.price = 13.0
    closed = pm.manage()
    assert closed == 0
    pos = db.positions()[0]
    # Milestone 2: SL ratchets to 12.0, Target expands to 16.0!
    assert pos["stop_loss"] == 12.0
    assert pos["target"] == 16.0

    # 6. Price reverses and drops to 12.0: SL triggers!
    provider.price = 12.0
    closed = pm.manage()
    assert closed == 1
    assert len(db.positions()) == 0

    trades = db.trades(1)
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "Stop loss"
    assert trades[0]["exit_price"] == 12.0
    # Guaranteed profit locked: bought at 7.0, exited at 12.0 => +5.0 per share * 10 shares = +50.0!
    assert trades[0]["pnl"] > 49.0


def test_short_scenario_dynamic_target_expansion():
    """
    Test symmetrical SHORT dynamic target expansion and breakeven lock.
    """
    cfg = {
        "execution": {
            "slippage_bps": 0, "brokerage": 0, "sebi_turnover_fee_pct": 0,
            "gst_pct": 0, "stamp_duty_non_delivery_pct": 0, "stt_intraday_sell_pct": 0,
            "trailing_stop_atr": 1.5, "max_hold_minutes": 390,
            "dynamic_target_expansion": True,
            "breakeven_lock_ratio": 0.50,
            "trailing_buffer_ratio": 1.0 / 3.0
        }
    }
    db = DB(":memory:")
    db.ensure_account(10000.0, 100000.0)
    exec_engine = PaperExecution(db, cfg)

    # Short sell at 100.0, SL 105.0, Target 90.0 (Step = 10.0, Buffer = 3.33)
    proposal = {
        "symbol": "SHORT1.NS", "action": "SHORT", "price": 100.0,
        "stop_loss": 105.0, "target": 90.0, "strategy": "Breakdown", "confidence": 85, "atr": 0.0
    }
    assert exec_engine.short(proposal, 5, "Bearish")

    provider = MutableQuoteProvider(100.0)
    pm = PositionManager(db, exec_engine, provider, cfg)

    # 1. Price drops to 95.0: Breakeven lock triggers (50% to target)
    provider.price = 95.0
    closed = pm.manage()
    assert closed == 0
    pos = db.positions()[0]
    assert pos["stop_loss"] <= 100.0  # Protected at breakeven

    # 2. Price drops to 90.0: Target hit! Dynamic Expansion fires!
    provider.price = 90.0
    closed = pm.manage()
    assert closed == 0  # Still open
    pos = db.positions()[0]
    assert pos["stop_loss"] == 93.33  # Locked in profit: 100 - 93.33 = +6.67/sh
    assert pos["target"] == 80.0

    # 3. Price drops to 80.0: Milestone 2 hit!
    provider.price = 80.0
    closed = pm.manage()
    assert closed == 0
    pos = db.positions()[0]
    assert pos["stop_loss"] == 83.33  # Locked in profit: 100 - 83.33 = +16.67/sh
    assert pos["target"] == 70.0

    # 4. Pullback to 83.33: Short stop loss triggers!
    provider.price = 83.33
    closed = pm.manage()
    assert closed == 1
    assert len(db.positions()) == 0

    trades = db.trades(1)
    assert trades[0]["exit_reason"] == "Short stop loss"
    assert trades[0]["pnl"] > 0


def test_disabled_dynamic_target_expansion_closes_at_target():
    """
    When dynamic_target_expansion is False, it closes immediately at target.
    """
    cfg = {
        "execution": {
            "slippage_bps": 0, "brokerage": 0, "sebi_turnover_fee_pct": 0,
            "gst_pct": 0, "stamp_duty_non_delivery_pct": 0, "stt_intraday_sell_pct": 0,
            "trailing_stop_atr": 1.5, "max_hold_minutes": 390,
            "dynamic_target_expansion": False,
        }
    }
    db = DB(":memory:")
    db.ensure_account(10000.0, 100000.0)
    exec_engine = PaperExecution(db, cfg)

    proposal = {
        "symbol": "CLASSIC.NS", "action": "BUY", "price": 100.0,
        "stop_loss": 95.0, "target": 110.0, "strategy": "Value", "confidence": 80, "atr": 2.0
    }
    assert exec_engine.buy(proposal, 5, "Bullish")

    provider = MutableQuoteProvider(110.0)
    pm = PositionManager(db, exec_engine, provider, cfg)
    closed = pm.manage()
    assert closed == 1
    assert len(db.positions()) == 0
    assert db.trades(1)[0]["exit_reason"] == "Target reached"


def test_near_market_close_closes_at_target_instead_of_expanding():
    """
    At 15:05 IST (near close), reaching target closes the position rather than expanding.
    """
    cfg = {
        "execution": {
            "slippage_bps": 0, "brokerage": 0, "sebi_turnover_fee_pct": 0,
            "gst_pct": 0, "stamp_duty_non_delivery_pct": 0, "stt_intraday_sell_pct": 0,
            "trailing_stop_atr": 1.5, "max_hold_minutes": 390,
            "dynamic_target_expansion": True,
        }
    }
    db = DB(":memory:")
    db.ensure_account(10000.0, 100000.0)
    exec_engine = PaperExecution(db, cfg)

    proposal = {
        "symbol": "LATE.NS", "action": "BUY", "price": 100.0,
        "stop_loss": 95.0, "target": 105.0, "strategy": "Scalp", "confidence": 80, "atr": 1.0
    }
    assert exec_engine.buy(proposal, 5, "Bullish")

    provider = MutableQuoteProvider(105.0)
    pm = PositionManager(db, exec_engine, provider, cfg)
    dt_1505 = datetime.fromisoformat("2026-10-20T15:05:00").replace(tzinfo=IST)
    closed = pm.manage(dt=dt_1505)
    assert closed == 1
    assert len(db.positions()) == 0
    assert db.trades(1)[0]["exit_reason"] == "Target reached"
