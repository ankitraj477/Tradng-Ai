"""
Acceptance Tests for Milestone 0 / Gate 0 Prerequisites (STRATEGY_SPEC.md).

All six Gate 0 requirements:
1. Auth fail-closed and token-authenticated control plane.
2. Legacy desks disabled behind desks.enabled=false.
3. .dockerignore at repo root; deploy.tar.gz and DB files not in git.
4. ensure_account must never reset silently; supports clean archive & restart.
5. Positions keyed by (sleeve, symbol) with weighted average entry & cumulative cost.
6. Unified risk path: every proposal routes through RiskManager.approve.
"""

import os
import subprocess
from pathlib import Path
import pytest
from app.db import DB
from app.dashboard import create_app
from app.risk import RiskManager


REPO_ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# 1. Auth Fail-Closed (R2-001)
# ----------------------------------------------------------------------

def test_gate0_auth_fail_closed_and_token(tmp_path):
    """Mutating endpoints reject unauthenticated calls (401) and accept valid token."""
    db = DB(str(tmp_path / "auth_test.db"))
    db.init()
    db.ensure_account(100000.0, 5000000.0)

    cfg = {
        "dashboard": {
            "token": "tradng-pro-2026",
            "fail_closed": True
        }
    }
    app = create_app(db=db, cfg=cfg)
    client = app.test_client()

    # 1. Unauthenticated mutation returns 401
    res = client.post("/api/auto-trading/toggle", json={"enabled": False})
    assert res.status_code == 401
    assert res.get_json()["error"] == "Unauthorized"

    # 2. Bearer token in Authorization header succeeds
    res_bearer = client.post(
        "/api/auto-trading/toggle",
        headers={"Authorization": "Bearer tradng-pro-2026"},
        json={"enabled": False}
    )
    assert res_bearer.status_code == 200
    assert res_bearer.get_json()["auto_trading"] is False

    # 3. X-API-Token header succeeds
    res_api_key = client.post(
        "/api/auto-trading/toggle",
        headers={"X-API-Token": "tradng-pro-2026"},
        json={"enabled": True}
    )
    assert res_api_key.status_code == 200
    assert res_api_key.get_json()["auto_trading"] is True

    # 4. Query parameter ?token=... succeeds (for global browser convenience)
    res_query = client.post(
        "/api/auto-trading/toggle?token=tradng-pro-2026",
        json={"enabled": False}
    )
    assert res_query.status_code == 200
    assert res_query.get_json()["auto_trading"] is False

    # 5. Fail-closed: if token is empty and fail_closed=True, request must be rejected
    cfg_empty = {"dashboard": {"token": "", "fail_closed": True}}
    app_empty = create_app(db=db, cfg=cfg_empty)
    client_empty = app_empty.test_client()
    res_empty = client_empty.post("/api/auto-trading/toggle")
    assert res_empty.status_code == 401


# ----------------------------------------------------------------------
# 2. Legacy Desks Disabled Behind desks.enabled=false (R2-002, R2-003, R2-004)
# ----------------------------------------------------------------------

def test_gate0_legacy_desks_disabled_behind_config():
    """Verify engine cycle does not invoke legacy desks when desks.enabled=false."""
    from unittest.mock import MagicMock
    from app.engine import TradingEngine

    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 5000000.0)
    db.set_auto_trading(True)

    cfg = {
        "capital": {"starting": 100000.0, "target": 5000000.0},
        "live_data": False,
        "desks": {
            "enabled": False,
            "intraday": False,
            "swing": False,
            "fno": False
        },
        "market": {"max_candidates": 5, "decision_interval_minutes": 1, "data_max_age_seconds": 900},
        "risk": {"min_risk_reward": 1.5, "max_drawdown_pct": 0.15, "daily_loss_limit_pct": 0.05, "kill_switch": False},
        "execution": {"short_margin_pct": 0.25}
    }

    engine = TradingEngine(cfg=cfg, db=db)
    engine.intraday_desk = MagicMock()
    engine.swing_desk = MagicMock()
    engine.fno_desk = MagicMock()
    engine.global_scanner = MagicMock()
    engine.global_scanner.scan_markets.return_value = {"sentiment": "NEUTRAL", "summary": "test"}
    engine.news = MagicMock()
    engine.news.recent.return_value = []

    # Run cycle with desks.enabled = False
    engine.cycle()

    # Assert legacy desks were NEVER called
    engine.intraday_desk.run_cycle.assert_not_called()
    engine.swing_desk.run_cycle.assert_not_called()
    engine.fno_desk.run_cycle.assert_not_called()


# ----------------------------------------------------------------------
# 3. .dockerignore & Git Tracking Invariants (R2-007, R2-008)
# ----------------------------------------------------------------------

def test_gate0_dockerignore_and_git_clean():
    """.dockerignore exists and no .db or .tar.gz files are tracked in git."""
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist at repo root"

    content = dockerignore_path.read_text(encoding="utf-8")
    assert "data/*.db*" in content or "*.db" in content
    assert "deploy.tar.gz" in content or "*.tar.gz" in content
    assert "*.key" in content

    # Verify no tracked .db or .tar.gz in git
    res = subprocess.run(
        ["git", "ls-files", "*.db", "*.tar.gz"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True
    )
    tracked_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    assert tracked_files == [], f"Found forbidden tracked files in git: {tracked_files}"


# ----------------------------------------------------------------------
# 4. ensure_account Invariants (R2-009)
# ----------------------------------------------------------------------

def test_gate0_ensure_account_invariants(tmp_path):
    """ensure_account must never reset cash or peak_value unless force_reset=True."""
    db = DB(str(tmp_path / "account_test.db"))
    db.init()

    # Initial setup
    db.ensure_account(starting=100000.0, target=2000000.0)
    acc = db.account()
    assert acc["starting_capital"] == 100000.0
    assert acc["cash"] == 100000.0
    assert acc["peak_value"] == 100000.0

    # Simulate trading gains and cash reduction
    db.update_account(cash=85000.0, peak=120000.0)
    acc = db.account()
    assert acc["cash"] == 85000.0
    assert acc["peak_value"] == 120000.0

    # Re-running ensure_account (e.g. on server restart or target capital update)
    # MUST NOT reset cash or peak_value
    db.ensure_account(starting=100000.0, target=5000000.0, force_reset=False)
    acc = db.account()
    assert acc["target_capital"] == 5000000.0
    assert acc["cash"] == 85000.0, "Cash must NOT be reset by ensure_account"
    assert acc["peak_value"] == 120000.0, "Peak value must NOT be reset by ensure_account"

    # Only explicit force_reset=True resets cash and peak
    db.ensure_account(starting=100000.0, target=5000000.0, force_reset=True)
    acc = db.account()
    assert acc["cash"] == 100000.0
    assert acc["peak_value"] == 100000.0


# ----------------------------------------------------------------------
# 5. Positions Keyed by (sleeve, symbol) with Weighted Average & Cumulative Cost (R2-006)
# ----------------------------------------------------------------------

def test_gate0_positions_composite_key_and_weighted_average(tmp_path):
    """Positions keyed by (sleeve, symbol); computes weighted average price & cumulative cost."""
    db = DB(str(tmp_path / "positions_test.db"))
    db.init()
    db.ensure_account(100000.0, 5000000.0)

    # 1. Upsert initial position in sleeve 'momentum'
    p1 = {
        "symbol": "TCS",
        "side": "LONG",
        "qty": 10,
        "entry_price": 3000.0,
        "entry_cost": 30.0,
        "stop_loss": 2850.0,
        "target": 3300.0,
        "strategy": "MOMENTUM_A"
    }
    db.upsert_position(p1, sleeve="momentum")

    pos = db.get_position("TCS", sleeve="momentum")
    assert pos is not None
    assert pos["sleeve"] == "momentum"
    assert pos["symbol"] == "TCS"
    assert pos["qty"] == 10
    assert pos["entry_price"] == 3000.0
    assert pos["entry_cost"] == 30.0

    # 2. Upsert same symbol in a DIFFERENT sleeve ('meanrev') -> distinct position!
    p2 = {
        "symbol": "TCS",
        "side": "LONG",
        "qty": 5,
        "entry_price": 3100.0,
        "entry_cost": 15.0,
        "strategy": "MEANREV_C"
    }
    db.upsert_position(p2, sleeve="meanrev")

    pos_mom = db.get_position("TCS", sleeve="momentum")
    pos_rev = db.get_position("TCS", sleeve="meanrev")
    assert pos_mom["qty"] == 10
    assert pos_rev["qty"] == 5
    assert len(db.positions()) == 2

    # 3. Add to existing position in 'momentum': 10 shares @ 3300 (cost 35)
    # Expected weighted avg price: (10*3000 + 10*3300) / 20 = 3150.0
    # Expected cumulative entry cost: 30 + 35 = 65.0
    p3 = {
        "symbol": "TCS",
        "side": "LONG",
        "qty": 10,
        "entry_price": 3300.0,
        "entry_cost": 35.0,
        "strategy": "MOMENTUM_A"
    }
    db.upsert_position(p3, sleeve="momentum")

    updated_pos = db.get_position("TCS", sleeve="momentum")
    assert updated_pos["qty"] == 20
    assert updated_pos["entry_price"] == 3150.0
    assert updated_pos["entry_cost"] == 65.0

    # 4. Deleting one sleeve does not delete the other
    db.delete_position("TCS", sleeve="meanrev")
    assert db.get_position("TCS", sleeve="meanrev") is None
    assert db.get_position("TCS", sleeve="momentum") is not None


# ----------------------------------------------------------------------
# 6. Unified Risk Path (R2-005)
# ----------------------------------------------------------------------

def test_gate0_unified_risk_path(tmp_path):
    """Every order proposal routes through RiskManager.approve."""
    db = DB(str(tmp_path / "risk_test.db"))
    db.init()
    db.ensure_account(100000.0, 5000000.0)

    cfg = {
        "risk": {
            "min_risk_reward": 1.5,
            "max_drawdown_pct": 0.15,
            "daily_loss_limit_pct": 0.05,
            "max_portfolio_heat_pct": 0.06,
            "max_sector_exposure_pct": 0.40,
            "min_move_cost_multiplier": 1.5
        },
        "execution": {
            "short_margin_pct": 0.25,
            "slippage_bps": 5
        },
        "market": {
            "max_open_positions": 5
        }
    }

    risk = RiskManager(db, cfg)

    # Valid proposal
    valid_proposal = {
        "symbol": "INFY",
        "action": "BUY",
        "price": 1500.0,
        "stop_loss": 1450.0,
        "target": 1650.0,
        "risk_reward": 3.0,
        "confidence": 85,
        "strategy": "MOMENTUM"
    }
    decision = risk.approve(valid_proposal, qty=10)
    assert decision == "APPROVE"

    # Reject poor risk-reward (< min_risk_reward)
    poor_rr_proposal = dict(valid_proposal, risk_reward=1.0)
    assert risk.approve(poor_rr_proposal, qty=10) == "REJECT"

    # Reject zero / negative quantity
    assert risk.approve(valid_proposal, qty=0) == "REJECT"

    # Reject if symbol is already held
    db.upsert_position({
        "symbol": "INFY", "side": "LONG", "qty": 10, "entry_price": 1500.0
    }, sleeve="core")
    assert risk.approve(valid_proposal, qty=10) == "REJECT"
