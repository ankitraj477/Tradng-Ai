from datetime import datetime
from zoneinfo import ZoneInfo
from app.db import DB
from app.execution import PaperExecution
from app.position_manager import PositionManager

IST = ZoneInfo("Asia/Kolkata")

class FailingProvider:
    def quote(self, symbol):
        raise RuntimeError(f"no quote data available for {symbol}")
    def history(self, symbol, **kwargs):
        raise RuntimeError("offline")

class ConstantProvider:
    def __init__(self, price=100.0):
        self.price = price
    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}

def test_position_closes_at_eod_square_off():
    cfg = {"execution": {"slippage_bps": 0, "brokerage": 0, "sebi_turnover_fee_pct": 0, "gst_pct": 0,
                         "stamp_duty_non_delivery_pct": 0, "stt_intraday_sell_pct": 0, "trailing_stop_atr": 1,
                         "max_hold_minutes": 390}}
    db = DB(":memory:")
    db.ensure_account(10000, 100000)
    e = PaperExecution(db, cfg)
    p = {"symbol": "EOD.NS", "price": 100, "stop_loss": 90, "target": 120, "strategy": "Test", "confidence": 80, "atr": 2}
    assert e.buy(p, 1, "Bullish")

    pm = PositionManager(db, e, ConstantProvider(102.0), cfg)
    # Seeded at 15:10 IST, manage called at 15:20 IST (weekday)
    eval_time = datetime.fromisoformat("2026-09-15T15:20:00").replace(tzinfo=IST)
    closed = pm.manage(dt=eval_time)
    assert closed == 1
    assert not db.positions()
    trades = db.trades(1)
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "EOD square-off"

def test_quote_failure_does_not_spam_error_logs():
    cfg = {"execution": {"slippage_bps": 0, "brokerage": 0, "sebi_turnover_fee_pct": 0, "gst_pct": 0,
                         "stamp_duty_non_delivery_pct": 0, "stt_intraday_sell_pct": 0, "trailing_stop_atr": 1,
                         "max_hold_minutes": 390}}
    db = DB(":memory:")
    db.ensure_account(10000, 100000)
    e = PaperExecution(db, cfg)
    p = {"symbol": "FAIL.NS", "price": 100, "stop_loss": 90, "target": 120, "strategy": "Test", "confidence": 80, "atr": 2}
    assert e.buy(p, 1, "Bullish")

    pm = PositionManager(db, e, FailingProvider(), cfg)
    for _ in range(10):
        closed = pm.manage()
        assert closed == 0

    with db.conn() as c:
        errors = c.execute("SELECT * FROM events WHERE level='ERROR'").fetchall()
        warns = c.execute("SELECT * FROM events WHERE level='WARN'").fetchall()
    assert len(errors) == 0
    assert len(warns) == 1
