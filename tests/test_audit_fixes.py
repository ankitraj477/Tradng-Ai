from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from app.db import DB
from app.config import load_config
from app.risk import RiskManager
from app.portfolio import PortfolioManager
from app.dashboard import create_app
from app.news_archive import NewsArchive
from app.market_hours import now_ist

IST = ZoneInfo("Asia/Kolkata")


def test_dashboard_token_auth_and_idempotent_toggle(tmp_path):
    db = DB(str(tmp_path / "test_auth.db"))
    db.init()
    db.ensure_account(10000.0, 100000.0)

    cfg = load_config()
    cfg["dashboard"] = {"token": "secret_token_123"}
    app = create_app(db, cfg)
    client = app.test_client()

    # 1. Unauthenticated mutation is rejected
    res = client.post("/api/auto-trading/toggle")
    assert res.status_code == 401

    # 2. Authenticated mutation with Bearer token succeeds
    res = client.post("/api/auto-trading/toggle", headers={"Authorization": "Bearer secret_token_123"})
    assert res.status_code == 200

    # 3. Idempotent toggle with explicit payload
    res = client.post(
        "/api/auto-trading/toggle",
        headers={"Authorization": "Bearer secret_token_123"},
        json={"enabled": False}
    )
    assert res.status_code == 200
    assert res.get_json()["auto_trading"] is False
    assert db.is_auto_trading_enabled() is False

    # Calling again with enabled: False keeps it False (idempotent)
    res = client.post(
        "/api/auto-trading/toggle",
        headers={"Authorization": "Bearer secret_token_123"},
        json={"enabled": False}
    )
    assert res.status_code == 200
    assert res.get_json()["auto_trading"] is False


def test_dashboard_health_endpoint_liveness_readiness(tmp_path):
    db = DB(str(tmp_path / "test_health.db"))
    db.init()
    db.ensure_account(10000.0, 100000.0)
    db.set_last_cycle()
    db.set_auto_trading(True)
    db.set_market("Bullish", "Neutral", None, data_ok=True)
    db.count_exception("scanner")

    cfg = load_config()
    app = create_app(db, cfg)
    client = app.test_client()

    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["ready"] is True
    assert data["last_cycle_at"] is not None
    assert data["exceptions"].get("scanner", 0) >= 1


def test_stop_updates_retention(tmp_path):
    db = DB(str(tmp_path / "test_retention.db"))
    db.init()
    db.ensure_account(10000.0, 100000.0)

    # Insert a dummy position
    with db.conn() as c:
        c.execute("""INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target, opened_at)
                     VALUES('TEST.NS', 'LONG', 10, 100.0, 102.0, 95.0, 110.0, datetime('now'))""")

    # Rapid stop updates with retention cap of 5
    for i in range(10):
        db.update_stop("TEST.NS", 95.0 + i, max_stop_updates=5)

    with db.conn() as c:
        count = c.execute("SELECT count(*) as c FROM stop_updates").fetchone()["c"]
    assert count <= 5


def test_regime_restrictions_in_risk_gate(tmp_path):
    db = DB(str(tmp_path / "test_regime.db"))
    db.init()
    db.ensure_account(10000.0, 100000.0)

    cfg = load_config()
    risk = RiskManager(db, cfg)

    # 1. Proposal with action BUY when regime only allows SHORT
    proposal_buy = {
        "symbol": "TEST.NS", "action": "BUY", "price": 100.0, "confidence": 75,
        "stop_loss": 95.0, "target": 110.0, "risk_reward": 2.0
    }
    regime_short_only = {"allowed_sides": ["SHORT"], "size_multiplier": 1.0}
    decision = risk.approve(proposal_buy, 10, regime_ctx=regime_short_only)
    assert decision == "REJECT"

    # 2. Extreme volatility with size_multiplier == 0
    regime_halt = {"allowed_sides": ["LONG", "SHORT"], "size_multiplier": 0.0}
    decision = risk.approve(proposal_buy, 10, regime_ctx=regime_halt)
    assert decision == "REJECT"


def test_news_archive_timestamp_normalization(tmp_path):
    archive = NewsArchive(str(tmp_path / "news.db"))
    rfc_date = "Mon, 19 Oct 2026 09:30:00 +0000"
    h = archive.archive_item(
        source="TestFeed",
        title="RBI issues new policy guidelines",
        url="https://example.com/news1",
        published_at=rfc_date,
        symbols=["HDFCBANK.NS"]
    )
    items = archive.get_recent(limit=5)
    assert len(items) == 1
    # Check normalized ISO timestamp
    assert "2026-10-19T09:30:00" in items[0]["published_at"]
