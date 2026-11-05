"""
Regression tests for Audit Security, Concurrency, and Invariant Fixes:
- AUDIT-001: Defensive account handling with None account rows
- AUDIT-002: hmac.compare_digest for dashboard authorization
- AUDIT-003: HTTP security headers on all responses
- AUDIT-004: 5-paise tick size rounding and microstructure validation across execution engines
- AUDIT-005: Capital allocation non-negative clamping and validation
"""

import pytest
import sqlite3
from app.db import DB
from app.config import load_config
from app.accounting import portfolio_metrics
from app.risk import RiskManager
from app.intraday.execution import IntradayExecution
from app.fno.execution import FNOExecution
from app.dashboard import create_app


@pytest.fixture
def test_db():
    db = DB(":memory:")
    db.ensure_account(100000.0, 5000000.0)
    return db


@pytest.fixture
def cfg():
    return load_config()


def test_accounting_with_none_account():
    """Verify portfolio_metrics does not crash if account is None or empty dict."""
    metrics_none = portfolio_metrics(None, [])
    assert metrics_none["cash"] == 0.0
    assert metrics_none["equity"] == 0.0

    metrics_empty = portfolio_metrics({}, [])
    assert metrics_empty["cash"] == 0.0
    assert metrics_empty["equity"] == 0.0


def test_risk_manager_with_empty_account(cfg):
    """Verify RiskManager.trading_allowed does not crash if DB account is uninitialized."""
    db = DB(":memory:")  # empty db without ensure_account
    # Create tables
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, side TEXT, qty INTEGER, entry_price REAL, current_price REAL, stop_loss REAL, target REAL, strategy TEXT, confidence REAL, opened_at TEXT, sector TEXT, atr REAL, entry_cost REAL, target_step REAL, product_type TEXT, days_held INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, starting_capital REAL, cash REAL, target_capital REAL, peak_value REAL, updated_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT, message TEXT, timestamp TEXT)")

    risk = RiskManager(db, cfg)
    allowed, reason = risk.trading_allowed()
    assert isinstance(allowed, bool)


def test_intraday_execution_tick_rounding_and_defensive_account(cfg):
    """Verify IntradayExecution rounds prices to 0.05 ticks and handles missing account row."""
    db = DB(":memory:")
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, side TEXT, qty INTEGER, entry_price REAL, current_price REAL, stop_loss REAL, target REAL, strategy TEXT, confidence REAL, opened_at TEXT, sector TEXT, atr REAL, entry_cost REAL, target_step REAL, product_type TEXT, days_held INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, starting_capital REAL, cash REAL, target_capital REAL, peak_value REAL, updated_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT, message TEXT, timestamp TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, action TEXT, side TEXT, entry_price REAL, exit_price REAL, qty INTEGER, capital REAL, stop_loss REAL, target REAL, holding_seconds REAL, pnl REAL, pnl_pct REAL, strategy TEXT, confidence REAL, regime TEXT, entry_reason TEXT, exit_reason TEXT, risk_decision TEXT, created_at TEXT, product_type TEXT, strike_price REAL, option_type TEXT, expiry_date TEXT)")

    exec_engine = IntradayExecution(db, cfg)
    # Price 1000.13 should round to 1000.15
    ok = exec_engine.open_long("TCS.NS", 1, 1000.13, 980.12, 1050.48)
    assert ok is True

    positions = db.positions()
    assert len(positions) == 1
    pos = positions[0]
    assert pos["entry_price"] == 1000.15
    assert pos["stop_loss"] == 980.10
    assert pos["target"] == 1050.50


def test_fno_execution_tick_rounding_and_defensive_account(cfg):
    """Verify FNOExecution rounds prices to 0.05 ticks and creates defensive account row if needed."""
    db = DB(":memory:")
    with db.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, side TEXT, qty INTEGER, entry_price REAL, current_price REAL, stop_loss REAL, target REAL, strategy TEXT, confidence REAL, opened_at TEXT, sector TEXT, atr REAL, entry_cost REAL, target_step REAL, product_type TEXT, strike_price REAL, option_type TEXT, expiry_date TEXT, legs_info TEXT, days_held INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, starting_capital REAL, cash REAL, target_capital REAL, peak_value REAL, updated_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, level TEXT, message TEXT, timestamp TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, action TEXT, side TEXT, entry_price REAL, exit_price REAL, qty INTEGER, capital REAL, stop_loss REAL, target REAL, holding_seconds REAL, pnl REAL, pnl_pct REAL, strategy TEXT, confidence REAL, regime TEXT, entry_reason TEXT, exit_reason TEXT, risk_decision TEXT, created_at TEXT, product_type TEXT, strike_price REAL, option_type TEXT, expiry_date TEXT)")

    fno_exec = FNOExecution(db, cfg)
    proposal = {
        "symbol": "NIFTY_CONDOR_TEST",
        "price": 42.13,
        "stop_loss": 84.28,
        "target": 15.02,
        "lot_size": 25,
        "margin_required": 2500.0,
        "strategy": "Iron Condor"
    }
    ok = fno_exec.open_spread(proposal, force_fill=True)
    assert ok is True

    positions = db.positions()
    assert len(positions) == 1
    pos = positions[0]
    assert pos["entry_price"] == 42.15
    assert pos["stop_loss"] == 84.30
    assert pos["target"] == 15.00


def test_capital_allocation_negative_clamping(test_db):
    """Verify db.set_capital_allocation clamps negative numbers to 0.0 and normalizes to 100%."""
    # Negative values should be clamped to 0.0
    res = test_db.set_capital_allocation(-10, 50, 50)
    assert res["intraday"] == 0.0
    assert res["swing"] == 50.0
    assert res["fno"] == 50.0

    # All zeros or negative should fall back to defaults (40, 40, 20)
    res_zero = test_db.set_capital_allocation(0, 0, 0)
    assert res_zero["intraday"] == 40.0
    assert res_zero["swing"] == 40.0
    assert res_zero["fno"] == 20.0


def test_dashboard_security_headers_and_token(test_db, cfg):
    """Verify HTTP security headers and token auth with hmac.compare_digest."""
    cfg_with_token = dict(cfg)
    cfg_with_token["dashboard"] = {"token": "secret_vault_token_123"}

    app = create_app(db=test_db, cfg=cfg_with_token)
    client = app.test_client()

    # 1. Health check includes security headers
    res = client.get("/health")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "default-src" in res.headers.get("Content-Security-Policy", "")

    # 2. Unauthorized request to protected endpoint
    post_unauth = client.post("/api/capital-allocation", json={"intraday": 50, "swing": 30, "fno": 20})
    assert post_unauth.status_code == 401

    # 3. Authorized request using Bearer token
    post_auth = client.post(
        "/api/capital-allocation",
        headers={"Authorization": "Bearer secret_vault_token_123"},
        json={"intraday": 50, "swing": 30, "fno": 20}
    )
    assert post_auth.status_code == 200
    data = post_auth.get_json()
    assert data["status"] == "ok"
    assert data["capital_allocation"]["intraday"] == 50.0

    # 4. Invalid numbers to capital allocation returns 400
    post_invalid = client.post(
        "/api/capital-allocation",
        headers={"Authorization": "Bearer secret_vault_token_123"},
        json={"intraday": "invalid_number"}
    )
    assert post_invalid.status_code == 400
