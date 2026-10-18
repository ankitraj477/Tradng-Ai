from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np

from app.db import DB
from app.execution import PaperExecution
from app.data.yfinance_provider import YFinanceProvider
from app.data.cache import MarketDataCache
from app.data.manifest import DatasetManifest
from app.engine import TradingEngine
from app.config import load_config


def test_events_and_equity_curve_bounded(tmp_path):
    db = DB(tmp_path / "test.db")
    # Insert 15 events with cap of 10
    for i in range(15):
        db.log("INFO", f"msg {i}", max_rows=10)
    with db.conn() as c:
        count = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 10
        latest = c.execute("SELECT message FROM events ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert latest == "msg 14"

    # Insert 15 equity rows with cap of 10
    for i in range(15):
        db.add_equity(1000 + i, float(i), max_rows=10)
    with db.conn() as c:
        count = c.execute("SELECT COUNT(*) FROM equity_curve").fetchone()[0]
        assert count == 10
        latest_val = c.execute("SELECT value FROM equity_curve ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert latest_val == 1014.0


def test_total_realized_pnl(tmp_path):
    db = DB(tmp_path / "test.db")
    db.ensure_account(1000, 100000)
    assert db.total_realized_pnl() == 0.0
    with db.conn() as c:
        c.execute("""INSERT INTO trades(symbol,action,side,entry_price,exit_price,qty,capital,stop_loss,target,holding_seconds,pnl,pnl_pct,strategy,confidence,regime,entry_reason,exit_reason,risk_decision,created_at)
                     VALUES('A.NS','SELL','LONG',100,110,1,100,95,115,100,10.0,10.0,'trend',70,'TREND_UP','test','test','APPROVED',?)""", (datetime.now(timezone.utc).isoformat(),))
        c.execute("""INSERT INTO trades(symbol,action,side,entry_price,exit_price,qty,capital,stop_loss,target,holding_seconds,pnl,pnl_pct,strategy,confidence,regime,entry_reason,exit_reason,risk_decision,created_at)
                     VALUES('B.NS','SELL','LONG',100,95,1,100,95,115,100,-5.0,-5.0,'trend',70,'TREND_UP','test','test','APPROVED',?)""", (datetime.now(timezone.utc).isoformat(),))
    assert db.total_realized_pnl() == 5.0


def test_exchange_txn_fee_cost(tmp_path):
    db = DB(tmp_path / "test.db")
    cfg = {
        'execution': {
            'slippage_bps': 0,
            'brokerage_pct': 0,
            'exchange_txn_fee_pct': 0.00297,
            'sebi_turnover_fee_pct': 0.0001,
            'gst_pct': 0.18,
            'stamp_duty_non_delivery_pct': 0.003,
            'stamp_duty_delivery_pct': 0.015,
            'stt_intraday_sell_pct': 0.025,
            'stt_delivery_pct': 0.10
        }
    }
    e = PaperExecution(db, cfg)
    val = 100000.0
    # exchange fee = 100000 * 0.00297% = 2.97
    # sebi = 100000 * 0.0001% = 0.10
    # gst = (0 + 2.97 + 0.10) * 0.18 = 0.5526
    # stamp for BUY = 100000 * 0.003% = 3.0
    # total buy cost = 2.97 + 0.10 + 0.5526 + 3.0 = 6.6226
    cost_buy = e.cost(val, 'BUY')
    assert round(cost_buy, 4) == 6.6226


def test_cache_fallback_in_history(tmp_path, monkeypatch):
    cache = MarketDataCache(tmp_path / "cache")
    manifest = DatasetManifest(tmp_path / "manifest.db")
    provider = YFinanceProvider(symbols=["FALLBACK.NS"], cache=cache, manifest=manifest, max_age_seconds=999999)

    now = datetime.now(timezone.utc)
    idx = pd.date_range(end=now, periods=30, freq="5min")
    df = pd.DataFrame({
        "Open": np.full(30, 100.0),
        "High": np.full(30, 105.0),
        "Low": np.full(30, 95.0),
        "Close": np.full(30, 102.0),
        "Volume": np.full(30, 1000.0)
    }, index=idx)
    # Save into cache
    cache.save("FALLBACK.NS", "5d", "5m", df)

    # Force download to fail
    monkeypatch.setattr(provider, "_download", lambda *args, **kwargs: None)
    loaded = provider.history("FALLBACK.NS", period="5d", interval="5m")
    assert loaded is not None
    assert len(loaded) == 30
