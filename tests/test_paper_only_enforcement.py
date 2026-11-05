import pytest
import sys
from app.runtime import preflight
from app.db import DB
from app.execution import PaperExecution
from app.swing.execution import SwingExecution
from app.fno.execution import FNOExecution


def test_no_live_broker_sdks_present():
    """BUG-046: Assert no live broker SDKs or order routing modules are loaded into the process."""
    forbidden_brokers = [
        "kiteconnect",
        "smartapi",
        "breeze_connect",
        "fyers_api",
        "fyers_apiv3",
        "alice_blue",
        "shoonya",
        "finvasia"
    ]
    for broker in forbidden_brokers:
        assert broker not in sys.modules, f"Forbidden live broker SDK '{broker}' must not be loaded"


def test_preflight_paper_only_guarantee():
    """BUG-046: Preflight check must assert paper_only and pass broker_execution check."""
    status = preflight()
    broker_check = next((c for c in status["checks"] if c["name"] == "broker_execution"), None)
    assert broker_check is not None
    assert broker_check["ok"] is True
    assert "paper trading only" in broker_check["details"]


def test_execution_engines_purely_paper():
    """Verify PaperExecution, SwingExecution, and FNOExecution record to database without live broker dependencies."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    cfg = {"execution": {"brokerage": 0.0}}
    pe = PaperExecution(db, cfg)
    se = SwingExecution(db, cfg)
    fe = FNOExecution(db, cfg)

    # All engines should have paper/database references only
    assert hasattr(pe, "db")
    assert hasattr(se, "db")
    assert hasattr(fe, "db")
    assert not hasattr(pe, "kite")
    assert not hasattr(se, "smart_api")
    assert not hasattr(fe, "broker_client")
