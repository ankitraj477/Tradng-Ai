"""
Comprehensive Test Suite for Indian Exchange Microstructure Rules,
Bracket Orders (OCO Logic), and Broker Gateway Adapters.
"""

import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from app.db import DB
from app.exchange_rules import (
    round_to_tick,
    calculate_circuit_bands,
    is_circuit_locked,
    validate_order_microstructure
)
from app.bracket_orders import BracketOrderManager
from app.broker.base import AbstractBrokerAdapter
from app.broker.paper import PaperBrokerAdapter
from app.broker.zerodha import ZerodhaKiteAdapter
from app.broker.angel import AngelSmartApiAdapter
from app.broker.factory import get_broker_adapter
from app.execution import PaperExecution
from app.swing.execution import SwingExecution


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_trading.db")
    db = DB(db_path)
    db.ensure_account(100000.0, 200000.0)
    return db




# =====================================================================
# 1. Indian Exchange Microstructure Rules Tests
# =====================================================================

def test_round_to_tick_paise():
    """Validates 5-paise tick size rounding on Indian exchanges."""
    assert round_to_tick(1402.13) == 1402.15
    assert round_to_tick(1402.11) == 1402.10
    assert round_to_tick(1402.125) == 1402.15
    assert round_to_tick(1402.00) == 1402.00
    assert round_to_tick(1402.02) == 1402.00
    assert round_to_tick(1402.03) == 1402.05
    assert round_to_tick(100.04) == 100.05
    assert round_to_tick(0.0) == 0.0
    assert round_to_tick(-10.5) == 0.0
    assert round_to_tick(None) == 0.0


def test_circuit_bands_calculation():
    """Validates upper and lower daily price bands calculation."""
    prev_close = 1000.00
    lower_20, upper_20 = calculate_circuit_bands(prev_close, 0.20)
    assert lower_20 == 800.00
    assert upper_20 == 1200.00

    lower_10, upper_10 = calculate_circuit_bands(prev_close, 0.10)
    assert lower_10 == 900.00
    assert upper_10 == 1100.00

    lower_5, upper_5 = calculate_circuit_bands(prev_close, 0.05)
    assert lower_5 == 950.00
    assert upper_5 == 1050.00


def test_is_circuit_locked():
    """Detects upper and lower circuit locks accurately."""
    prev_close = 1000.00
    # Normal trading price
    res_normal = is_circuit_locked(1050.00, prev_close, band_pct=0.20)
    assert not res_normal["locked"]
    assert res_normal["circuit_type"] == "NONE"

    # Locked near Upper Circuit (1200)
    res_upper = is_circuit_locked(1198.50, prev_close, band_pct=0.20)
    assert res_upper["locked"]
    assert res_upper["circuit_type"] == "UPPER"
    assert "Upper Circuit" in res_upper["reason"]

    # Locked near Lower Circuit (800)
    res_lower = is_circuit_locked(801.00, prev_close, band_pct=0.20)
    assert res_lower["locked"]
    assert res_lower["circuit_type"] == "LOWER"
    assert "Lower Circuit" in res_lower["reason"]


def test_validate_order_microstructure():
    """Blocks buys at Upper Circuit and sells at Lower Circuit."""
    prev_close = 500.00
    # Normal buy succeeds
    val_ok = validate_order_microstructure("INFY.NS", "BUY", 510.123, stop_loss=495.12, target=530.44, prev_close=prev_close)
    assert val_ok["ok"]
    assert val_ok["price"] == 510.10
    assert val_ok["stop_loss"] == 495.10
    assert val_ok["target"] == 530.45

    # Buy at Upper Circuit (600) is rejected because no sellers exist
    val_upper = validate_order_microstructure("TATAMOTORS.NS", "BUY", 599.50, prev_close=prev_close)
    assert not val_upper["ok"]
    assert "Upper Circuit" in val_upper["reason"]

    # Short at Lower Circuit (400) is rejected because no buyers exist
    val_lower = validate_order_microstructure("TATAMOTORS.NS", "SHORT", 400.50, prev_close=prev_close)
    assert not val_lower["ok"]
    assert "Lower Circuit" in val_lower["reason"]


# =====================================================================
# 2. Bracket Order & OCO Logic Tests
# =====================================================================

def test_bracket_order_creation_and_oco_target_hit(test_db):
    """Verifies that when Target hits, Target is FILLED and SL is CANCELLED_OCO."""
    bom = BracketOrderManager(test_db)
    bracket = bom.create_bracket(
        symbol="RELIANCE.NS",
        side="LONG",
        qty=10,
        entry_price=2500.00,
        stop_loss=2450.00,
        target=2600.00
    )
    assert bracket["status"] == "ACTIVE"

    active_legs = bom.get_active_brackets("RELIANCE.NS")
    assert len(active_legs) == 2

    # Simulate price reaches target
    res = bom.evaluate_bracket("RELIANCE.NS", "LONG", 2605.00)
    assert res is not None
    assert res["triggered"]
    assert res["reason"] == "TARGET_HIT"
    assert res["leg_type"] == "TARGET"
    assert res["canceled_leg_type"] == "SL"

    # Verify database state: no active legs remaining
    active_after = bom.get_active_brackets("RELIANCE.NS")
    assert len(active_after) == 0

    all_legs = bom.get_all_brackets("RELIANCE.NS")
    status_map = {leg["leg_type"]: leg["status"] for leg in all_legs}
    assert status_map["TARGET"] == "FILLED"
    assert status_map["SL"] == "CANCELLED_OCO"


def test_bracket_order_oco_stop_loss_hit(test_db):
    """Verifies that when Stop Loss hits, SL is FILLED and Target is CANCELLED_OCO."""
    bom = BracketOrderManager(test_db)
    bom.create_bracket(
        symbol="TCS.NS",
        side="SHORT",
        qty=5,
        entry_price=3500.00,
        stop_loss=3550.00,
        target=3400.00
    )

    # For SHORT, SL triggers if price >= 3550
    res = bom.evaluate_bracket("TCS.NS", "SHORT", 3552.00)
    assert res is not None
    assert res["triggered"]
    assert res["reason"] == "STOP_LOSS_HIT"
    assert res["leg_type"] == "SL"
    assert res["canceled_leg_type"] == "TARGET"

    all_legs = bom.get_all_brackets("TCS.NS")
    status_map = {leg["leg_type"]: leg["status"] for leg in all_legs}
    assert status_map["SL"] == "FILLED"
    assert status_map["TARGET"] == "CANCELLED_OCO"


def test_bracket_order_trailing_stop_update(test_db):
    """Verifies update_stop_loss updates trigger price with 5-paise tick rounding."""
    bom = BracketOrderManager(test_db)
    bom.create_bracket("SBIN.NS", "LONG", 20, 750.00, 740.00, 780.00)

    # Move SL to breakeven (750.12 -> 750.10)
    bom.update_stop_loss("SBIN.NS", 750.12)
    active = bom.get_active_brackets("SBIN.NS")
    sl_leg = [leg for leg in active if leg["leg_type"] == "SL"][0]
    assert sl_leg["trigger_price"] == 750.10


def test_bracket_order_cancel_bracket(test_db):
    """Verifies cancel_bracket cancels all active legs upon position exit."""
    bom = BracketOrderManager(test_db)
    bom.create_bracket("WIPRO.NS", "LONG", 100, 480.00, 470.00, 500.00)
    bom.cancel_bracket("WIPRO.NS", reason="MANUAL_CLOSE")

    active = bom.get_active_brackets("WIPRO.NS")
    assert len(active) == 0

    all_legs = bom.get_all_brackets("WIPRO.NS")
    for leg in all_legs:
        assert leg["status"] == "CANCELLED_MANUAL_CLOSE"


# =====================================================================
# 3. Broker Adapter Gateway Tests
# =====================================================================

def test_paper_broker_adapter_execution(test_db):
    """Verifies PaperBrokerAdapter executes trades against internal ledger with microstructure."""
    adapter = PaperBrokerAdapter(test_db)
    assert adapter.name == "PAPER_SIMULATOR"
    assert not adapter.is_live
    assert adapter.connect()

    funds = adapter.get_funds()
    assert funds["available_cash"] > 0

    # Place paper buy order
    res = adapter.place_order(
        symbol="HDFCBANK.NS",
        action="BUY",
        qty=15,
        price=1450.37,
        product_type="INTRADAY",
        order_type="MARKET"
    )
    assert res["success"]
    assert res["status"] == "FILLED"
    assert res["fill_price"] == 1450.35  # Tick-rounded

    # Orders query
    orders = adapter.get_orders()
    assert len(orders) >= 1
    assert orders[0]["symbol"] == "HDFCBANK.NS"


def test_zerodha_kite_adapter_safe_fallback():
    """Zerodha adapter gracefully fails connection if credentials are missing."""
    adapter = ZerodhaKiteAdapter(api_key="", access_token="")
    assert adapter.name == "ZERODHA_KITE"
    assert adapter.is_live
    assert not adapter.connect()

    # Reject order gracefully if not connected
    order = adapter.place_order("INFY.NS", "BUY", 10, 1500.00)
    assert not order["success"]
    assert order["status"] == "REJECTED"


def test_zerodha_kite_adapter_mocked_execution():
    """Verifies Zerodha Kite adapter formats orders and product types accurately."""
    adapter = ZerodhaKiteAdapter(api_key="mock_key", access_token="mock_token")
    mock_kite = MagicMock()
    mock_kite.place_order.return_value = "23102300012345"
    mock_kite.margins.return_value = {
        "equity": {
            "available": {"live_balance": 500000.0, "collateral": 0.0},
            "utilised": {"debits": 25000.0},
            "net": 475000.0
        }
    }
    mock_kite.VARIETY_REGULAR = "regular"
    adapter.kite = mock_kite
    adapter._connected = True

    funds = adapter.get_funds()
    assert funds["available_cash"] == 500000.0
    assert funds["total_balance"] == 475000.0

    res = adapter.place_order(
        symbol="RELIANCE.NS",
        action="BUY",
        qty=25,
        price=2400.00,
        product_type="SWING",
        order_type="LIMIT"
    )
    assert res["success"]
    assert res["order_id"] == "23102300012345"
    assert res["product_type"] == "CNC"
    mock_kite.place_order.assert_called_once()


def test_angel_smart_api_adapter_safe_fallback():
    """Angel One adapter gracefully fails connection if credentials are missing."""
    adapter = AngelSmartApiAdapter(api_key="", client_code="", password="")
    assert adapter.name == "ANGEL_ONE"
    assert adapter.is_live
    assert not adapter.connect()

    order = adapter.place_order("TCS.NS", "BUY", 5, 3500.00)
    assert not order["success"]
    assert order["status"] == "REJECTED"


def test_broker_factory_paper_first_security(test_db):
    """Factory must return PaperBrokerAdapter by default to ensure complete paper safety."""
    # Empty cfg -> Paper
    adapter = get_broker_adapter({}, test_db)
    assert isinstance(adapter, PaperBrokerAdapter)
    assert not adapter.is_live

    # Explicit paper config -> Paper
    adapter_paper = get_broker_adapter({"broker": {"type": "paper"}}, test_db)
    assert isinstance(adapter_paper, PaperBrokerAdapter)

    # Failed live broker fallback -> Paper
    adapter_failed_live = get_broker_adapter({"broker": {"type": "zerodha"}, "runtime": {"paper_only": False}}, test_db)
    assert isinstance(adapter_failed_live, PaperBrokerAdapter)


# =====================================================================
# 4. End-to-End Execution & Bracket Integration Tests
# =====================================================================

def test_paper_execution_registers_and_cancels_brackets(test_db):
    """Verifies PaperExecution registers OCO bracket on buy, and cancels on close."""
    pe = PaperExecution(test_db, {"execution": {"slippage_bps": 0, "short_margin_pct": 0.25}})

    proposal = {
        "symbol": "INFY.NS",
        "price": 1400.13,  # Will round to 1400.15
        "stop_loss": 1380.07,  # Will round to 1380.05
        "target": 1440.23,  # Will round to 1440.25
        "strategy": "ORB",
        "confidence": 85,
        "product_type": "INTRADAY"
    }

    ok = pe.buy(proposal, 10, "BULLISH")
    assert ok

    # Check active bracket in db
    active = pe.bracket_manager.get_active_brackets("INFY.NS")
    assert len(active) == 2
    sl_leg = [l for l in active if l["leg_type"] == "SL"][0]
    tp_leg = [l for l in active if l["leg_type"] == "TARGET"][0]
    assert sl_leg["trigger_price"] == 1380.05
    assert tp_leg["trigger_price"] == 1440.25

    # Close position
    pe.close("INFY.NS", 1440.25, "Target reached", "BULLISH")

    # Brackets must be cancelled
    active_after = pe.bracket_manager.get_active_brackets("INFY.NS")
    assert len(active_after) == 0


def test_swing_execution_registers_and_cancels_brackets(test_db):
    """Verifies SwingExecution registers OCO bracket on swing buy, and cancels on close."""
    se = SwingExecution(test_db, {"execution": {"slippage_bps": 0}})

    proposal = {
        "symbol": "ITC.NS",
        "price": 420.33,  # Rounds to 420.35
        "stop_loss": 405.11,  # Rounds to 405.10
        "target": 450.77,  # Rounds to 450.75
        "strategy": "Swing Pullback",
        "confidence": 80
    }

    ok = se.buy(proposal, 50, force_fill=True)
    assert ok

    # Verify bracket registered
    active = se.bracket_manager.get_active_brackets("ITC.NS")
    assert len(active) == 2

    # Close swing position
    se.close("ITC.NS", 450.75, "Target reached")

    # Verify bracket cancelled
    active_after = se.bracket_manager.get_active_brackets("ITC.NS")
    assert len(active_after) == 0
