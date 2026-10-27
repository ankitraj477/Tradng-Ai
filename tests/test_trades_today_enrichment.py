from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.db import DB
from app.dashboard import _enrich_trade

IST = ZoneInfo("Asia/Kolkata")


def test_trades_today_and_enrichment(tmp_path):
    db_path = str(tmp_path / "test_trades.db")
    db = DB(db_path)
    db.init()

    # Insert a trade from today (in UTC)
    now_ist = datetime.now(IST)
    now_utc = datetime.now(timezone.utc)
    today_created_at = now_utc.isoformat()

    # Insert a trade from yesterday in UTC
    yesterday_created_at = "2026-09-01T10:00:00+00:00"

    with db.conn() as c:
        # Today's intraday trade
        c.execute("""
            INSERT INTO trades(symbol, action, side, entry_price, exit_price, qty, capital, stop_loss, target,
                               holding_seconds, pnl, pnl_pct, strategy, confidence, regime, entry_reason,
                               exit_reason, risk_decision, created_at, product_type)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "CDSL.NS", "SELL", "LONG", 1200.0, 1220.0, 10, 12000.0, 1180.0, 1240.0,
            1800.0, 200.0, 1.67, "Trend", 80.0, "BULLISH", "Signal", "Target", "APPROVED",
            today_created_at, "INTRADAY"
        ))

        # Yesterday's trade
        c.execute("""
            INSERT INTO trades(symbol, action, side, entry_price, exit_price, qty, capital, stop_loss, target,
                               holding_seconds, pnl, pnl_pct, strategy, confidence, regime, entry_reason,
                               exit_reason, risk_decision, created_at, product_type)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "RELIANCE.NS", "SELL", "LONG", 2500.0, 2480.0, 5, 12500.0, 2450.0, 2550.0,
            3600.0, -100.0, -0.80, "Trend", 75.0, "BULLISH", "Signal", "Stop", "APPROVED",
            yesterday_created_at, "INTRADAY"
        ))

    # 1. Test db.trades_today() only returns today's trade!
    today_trades = db.trades_today()
    assert len(today_trades) == 1
    assert today_trades[0]["symbol"] == "CDSL.NS"

    # 2. Test db.trades() returns both trades (all history)
    all_trades = db.trades(10)
    assert len(all_trades) == 2

    # 3. Test _enrich_trade calculates clean IST timestamps
    enriched = _enrich_trade(today_trades[0])
    assert "exit_time_ist" in enriched
    assert "entry_time_ist" in enriched
    assert "timing_display" in enriched
    assert ("\u2192" in enriched["timing_display"] or "->" in enriched["timing_display"])
    assert enriched["exit_date"] == now_ist.strftime("%Y-%m-%d")
