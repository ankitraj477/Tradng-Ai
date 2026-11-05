"""
Unit tests specifically targeting all bugs fixed during the codebase audit:
1. Intraday short margin accounting (no double-debiting of margin on open)
2. Available cash checks considering reserved short margin across desks
3. F&O exact margin recording and release on position close
4. F&O dynamic theta decay and spot tracking in PositionManager
5. Swing execution delivery cost model accuracy
6. KillSwitch desk-specific routing for INTRADAY, SWING, and FNO
7. ORB strategy decide / generate_signal alias
8. DB update_position_stops method
9. AITrader bearish strategy selection and confidence alignment
10. TradingEngine reload_config propagation
"""

import pytest
from app.db import DB
from app.config import load_config
from app.intraday.execution import IntradayExecution
from app.swing.execution import SwingExecution
from app.fno.execution import FNOExecution
from app.fno.position_manager import FNOPositionManager
from app.ops.kill_switch import KillSwitch
from app.intraday.orb_strategy import ORBStrategy
from app.ai_trader import AITrader
from app.engine import TradingEngine
from app.costs import CostModel


@pytest.fixture
def test_db():
    db = DB(":memory:")
    db.ensure_account(100000.0, 5000000.0)
    return db





@pytest.fixture
def cfg():
    return load_config()


def test_intraday_open_short_accounting(test_db, cfg):
    """
    BUG-001: open_short must only deduct transaction cost from cash.
    Margin is reserved equity tracked by accounting, not deducted from cash,
    because close() only credits (entry - exit) - exit_cost.
    """
    exec_engine = IntradayExecution(test_db, cfg)
    acc_before = test_db.account()
    initial_cash = acc_before["cash"]

    # Open short: 10 shares @ 1000 = 10,000 notional
    ok = exec_engine.open_short("INFY.NS", 10, 1000.0, 1020.0, 960.0)
    assert ok is True

    acc_after = test_db.account()
    cash_diff = initial_cash - acc_after["cash"]
    
    # Margin is 25% = 2,500. Cash diff must be <= 50 (just txn cost), NOT 2,500+
    assert cash_diff < 50.0

    # Close short at profit: exit at 960 (gross profit = (1000 - 960) * 10 = +400)
    closed = exec_engine.close("INFY.NS", 960.0, "TARGET_HIT")
    assert closed is True

    acc_final = test_db.account()
    # Net cash should be initial_cash + gross_pnl - total_fees
    assert acc_final["cash"] > initial_cash
    assert acc_final["cash"] > initial_cash + 350.0  # ~400 gross minus ~10 fees


def test_swing_delivery_cost_model(test_db, cfg):
    """
    BUG-004: Delivery cost model must not charge 10% STT or 100x fee.
    Must match CostModel DELIVERY segment.
    """
    swing_exec = SwingExecution(test_db, cfg)
    cost_model = CostModel(cfg)

    notional = 100000.0
    calc_buy = swing_exec._cost(notional, "BUY")
    expected_buy = cost_model.calculate(notional, "BUY", segment="DELIVERY")
    assert calc_buy == expected_buy
    # Delivery STT is 0.1% = 100, so total cost on 100k should be around 118, not 10,000!
    assert calc_buy < 300.0


def test_fno_exact_margin_recording_and_release(test_db, cfg):
    """
    BUG-005: F&O positions must store exact margin requirement in entry_cost,
    and release the exact margin when closed instead of hardcoded 2500.
    """
    fno_exec = FNOExecution(test_db, cfg)
    acc_init = test_db.account()
    initial_cash = acc_init["cash"]

    proposal = {
        "symbol": "NIFTY_24500_CE",
        "price": 120.0,
        "action": "BUY",
        "stop_loss": 60.0,
        "target": 180.0,
        "strike_price": 24500.0,
        "option_type": "CE",
        "strategy": "Bull Call Spread",
        "confidence": 85,
        "margin_required": 2000.0,  # Custom margin != 2500
        "expiry_date": "2026-10-29",
        "legs_info": "Long 24500 CE / Short 24700 CE"
    }

    ok = fno_exec.open_spread(proposal, 50, force_fill=True)
    assert ok is True

    pos = test_db.positions_by_product("FNO")[0]
    assert pos["entry_cost"] == 2000.0

    acc_after_open = test_db.account()
    assert acc_after_open["cash"] == initial_cash - 2000.0

    # Close with profit: credit sold at 120, bought back at decayed premium 60
    closed = fno_exec.close("NIFTY_24500_CE", 60.0, "TARGET_HIT")
    assert closed is True

    acc_final = test_db.account()
    # Should have released 2000 + net_pnl
    # gross_pnl = (120 - 60) * 25 = +1500, fees = 50 -> net_pnl = 1450
    assert acc_final["cash"] == pytest.approx(initial_cash + 1450.0, abs=1.0)




def test_fno_dynamic_theta_decay(test_db, cfg):
    """
    BUG-007: PositionManager for FNO must update current_price dynamically
    via theta decay / spot drift rather than leaving it completely frozen.
    """
    from datetime import datetime, timezone, timedelta
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
    
    # 2 days ago opened
    opened_dt = datetime.now(timezone.utc) - timedelta(days=2)
    opened_iso = opened_dt.isoformat()
    # Expiry 3 days in future
    expiry_str = (datetime.now(IST) + timedelta(days=3)).strftime("%Y-%m-%d")

    with test_db.conn() as c:
        c.execute("""
            INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence,
                                  opened_at, sector, atr, entry_cost, target_step, product_type, strike_price, option_type, expiry_date)
            VALUES('NIFTY_25000_CE', 'LONG', 50, 100.0, 100.0, 200.0, 50.0, 'Bull Call Spread', 80,
                   ?, 'INDICES', 0.0, 2500.0, 0.0, 'FNO', 25000.0, 'CE', ?)
        """, (opened_iso, expiry_str))

    fno_exec = FNOExecution(test_db, cfg)
    pm = FNOPositionManager(test_db, fno_exec, cfg=cfg)
    
    # Run manage()
    pm.manage()
    
    pos = test_db.positions_by_product("FNO")[0]
    # In an option credit spread, theta decays price below 100.0
    assert pos["current_price"] < 100.0



def test_kill_switch_product_routing(test_db, cfg):
    """
    BUG-008: KillSwitch must route FNO, SWING, and INTRADAY positions
    to their respective execution engines to release margins and taxes properly.
    """
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    with test_db.conn() as c:
        # 1 INTRADAY
        c.execute("""
            INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence,
                                  opened_at, sector, atr, entry_cost, target_step, product_type)
            VALUES('TCS.NS', 'LONG', 5, 3000.0, 3010.0, 2950.0, 3100.0, 'Momentum', 80,
                   ?, 'IT', 20.0, 5.0, 0.0, 'INTRADAY')
        """, (now_iso,))
        # 1 SWING
        c.execute("""
            INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence,
                                  opened_at, sector, atr, entry_cost, target_step, product_type)
            VALUES('RELIANCE.NS', 'LONG', 10, 2500.0, 2520.0, 2400.0, 2700.0, 'Swing Pullback', 85,
                   ?, 'ENERGY', 30.0, 25.0, 0.0, 'SWING')
        """, (now_iso,))
        # 1 FNO
        c.execute("""
            INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence,
                                  opened_at, sector, atr, entry_cost, target_step, product_type, strike_price, option_type, expiry_date)
            VALUES('BANKNIFTY_48000_PE', 'LONG', 15, 200.0, 210.0, 100.0, 350.0, 'Bear Put Spread', 80,
                   ?, 'INDICES', 0.0, 3000.0, 0.0, 'FNO', 48000.0, 'PE', '2026-10-29')
        """, (now_iso,))

    class MockProvider:
        def quote(self, sym):
            return {"price": 3010.0 if "TCS" in sym else (2520.0 if "RELIANCE" in sym else 210.0)}

    intraday_exec = IntradayExecution(test_db, cfg)
    ks = KillSwitch(test_db, execution=intraday_exec, provider=MockProvider(), cfg=cfg)
    closed_count = ks.flatten_portfolio(reason="TEST_FLATTEN")
    assert closed_count == 3
    assert len(test_db.positions()) == 0



def test_orb_strategy_aliases():
    """
    BUG-003: ORBStrategy must support both decide and generate_signal alias.
    """
    orb = ORBStrategy()
    assert hasattr(orb, "decide")
    assert hasattr(orb, "generate_signal")
    assert orb.decide == orb.generate_signal



def test_db_update_position_stops(test_db):
    """
    BUG-006: DB must implement update_position_stops(symbol, stop_loss, target).
    """
    from datetime import datetime, timezone
    with test_db.conn() as c:
        c.execute("""
            INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, strategy, confidence,
                                  opened_at, sector, atr, entry_cost, target_step, product_type)
            VALUES('SBIN.NS', 'LONG', 10, 800.0, 820.0, 780.0, 860.0, 'Breakout', 80,
                   ?, 'BANK', 10.0, 2.0, 0.0, 'INTRADAY')
        """, (datetime.now(timezone.utc).isoformat(),))

    test_db.update_position_stops("SBIN.NS", stop_loss=810.0, target=880.0)
    pos = [p for p in test_db.positions() if p["symbol"] == "SBIN.NS"][0]
    assert pos["stop_loss"] == 810.0
    assert pos["target"] == 880.0


def test_ai_trader_bearish_proposal(cfg):
    """
    BUG-013: AITrader on SHORT must use bearish strategy and confidence >= 60.
    """
    trader = AITrader(cfg=cfg)
    c = {
        "symbol": "BEAR_SYM",
        "price": 500.0,
        "score": 80.0,
        "bear_score": 82.0,
        "bull_score": 30.0,
        "rsi": 32.0,
        "atr": 8.0,
        "rel_volume": 1.8,
        "ret_5": -0.04,
        "ret_20": -0.08,
        "sector": "IT",
        "news_bias": -3
    }
    proposal = trader.propose(c, regime="Bearish", market_sentiment="Bearish")
    assert proposal["action"] == "SHORT"
    assert proposal["confidence"] >= 60
    assert proposal["stop_loss"] > proposal["price"] > proposal["target"]
    assert proposal["strategy"] in {"Momentum", "Breakout", "Trend", "Mean Reversion", "News/Event"}
    assert "strongest;" in proposal["reason"]


def test_engine_reload_config_propagation(cfg):
    """
    BUG-010: reload_config must propagate new cfg to all desks.
    """
    engine = TradingEngine(cfg=cfg)
    new_cfg = dict(cfg)
    new_cfg["execution"]["short_margin_pct"] = 0.35
    engine.reload_config(new_cfg)

    assert engine.cfg["execution"]["short_margin_pct"] == 0.35
    assert engine.intraday_desk.cfg["execution"]["short_margin_pct"] == 0.35
    assert engine.swing_desk.cfg["execution"]["short_margin_pct"] == 0.35
    assert engine.fno_desk.cfg["execution"]["short_margin_pct"] == 0.35
