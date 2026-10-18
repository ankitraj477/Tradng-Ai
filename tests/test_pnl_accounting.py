import math
from app.config import load_config
from app.db import DB
from app.execution import PaperExecution

def test_closed_trades_pnl_matches_cash_delta():
    cfg = load_config()
    db = DB(":memory:")
    starting_cash = 10000.0
    db.ensure_account(starting_cash, 100000.0)
    e = PaperExecution(db, cfg)

    # Round trip LONG
    p_long = {"symbol": "LONG.NS", "price": 200.0, "stop_loss": 190.0, "target": 220.0, "strategy": "Test", "confidence": 80, "atr": 5.0}
    assert e.buy(p_long, 10, "Bullish")
    assert e.close("LONG.NS", 205.0, "target", "Bullish")

    # Round trip SHORT
    p_short = {"symbol": "SHORT.NS", "price": 300.0, "stop_loss": 315.0, "target": 285.0, "strategy": "Test", "confidence": 80, "atr": 5.0}
    assert e.short(p_short, 5, "Bearish")
    assert e.close("SHORT.NS", 290.0, "target", "Bearish")

    trades = db.trades(10)
    assert len(trades) == 2
    total_pnl = sum(t["pnl"] for t in trades)
    ending_cash = db.account()["cash"]
    cash_delta = ending_cash - starting_cash

    assert math.isclose(total_pnl, cash_delta, rel_tol=1e-5, abs_tol=1e-5)
