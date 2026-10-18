import pytest
from app.db import DB
from app.dashboard import create_app


def test_db_auto_trading_setting():
    db = DB(":memory:")
    # Default is enabled
    assert db.is_auto_trading_enabled() is True

    # Disable
    db.set_auto_trading(False)
    assert db.is_auto_trading_enabled() is False

    # Enable
    db.set_auto_trading(True)
    assert db.is_auto_trading_enabled() is True


def test_dashboard_auto_trading_toggle_endpoint():
    db = DB(":memory:")
    db.ensure_account(1000.0, 100000.0)
    app = create_app(db=db)
    client = app.test_client()

    # Initial state
    res = client.get("/api/auto-trading")
    assert res.status_code == 200
    assert res.json["auto_trading"] is True

    # Toggle to False
    res_toggle1 = client.post("/api/auto-trading/toggle")
    assert res_toggle1.status_code == 200
    assert res_toggle1.json["auto_trading"] is False
    assert db.is_auto_trading_enabled() is False

    # State endpoint reflects auto_trading
    res_state = client.get("/api/state")
    assert res_state.status_code == 200
    assert res_state.json["auto_trading"] is False

    # Toggle back to True
    res_toggle2 = client.post("/api/auto-trading/toggle")
    assert res_toggle2.status_code == 200
    assert res_toggle2.json["auto_trading"] is True
    assert db.is_auto_trading_enabled() is True
