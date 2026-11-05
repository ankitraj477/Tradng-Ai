"""
Test suite for Shoonya (Finvasia NorenApi) Zero-Brokerage Adapter.
Validates zero-brokerage credentials, order placement, exchange routing,
and factory integration.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.db import DB
from app.broker.shoonya import ShoonyaBrokerAdapter
from app.broker.factory import get_broker_adapter


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_trading.db")
    db = DB(db_path)
    db.ensure_account(1000.0, 10000.0)
    return db


def test_shoonya_routing_and_order_placement():
    """Verifies Shoonya places orders with correct prd (I for MIS, C for CNC, M for FNO) and exchange."""
    adapter = ShoonyaBrokerAdapter(user_id="TESTUSER", password="secret_password", totp_key="123456", vendor_code="TEST_VC", api_secret="secret_key")
    adapter._connected = True

    placed_orders = []

    class DummyApi:
        def place_order(self, **kwargs):
            placed_orders.append(kwargs)
            return {"stat": "Ok", "norenordno": "SH123456"}

    adapter.api = DummyApi()

    # 1. Equity Intraday MIS
    res_intra = adapter.place_order("TATASTEEL.NS", "BUY", 10, 150.0, product_type="INTRADAY")
    assert res_intra["order_id"] == "SH123456"
    assert placed_orders[-1]["prd"] == "I"
    assert placed_orders[-1]["exch"] == "NSE"
    assert placed_orders[-1]["tsym"] == "TATASTEEL-EQ"

    # 2. Equity Swing CNC
    res_swing = adapter.place_order("ITC.NS", "BUY", 5, 420.0, product_type="SWING")
    assert res_swing["order_id"] == "SH123456"
    assert placed_orders[-1]["prd"] == "C"
    assert placed_orders[-1]["exch"] == "NSE"
    assert placed_orders[-1]["tsym"] == "ITC-EQ"

    # 3. FNO Options
    res_fno = adapter.place_order("NIFTY25000CE", "BUY", 25, 120.0, product_type="FNO")
    assert res_fno["order_id"] == "SH123456"
    assert placed_orders[-1]["prd"] == "M"
    assert placed_orders[-1]["exch"] == "NFO"


def test_shoonya_factory_integration(test_db):
    """Verifies factory instantiation of Shoonya adapter when configured."""
    cfg = {
        "broker": {
            "type": "shoonya",
            "shoonya_user_id": "FAKESTUDENT",
            "shoonya_password": "PASSWORD",
            "shoonya_totp_key": "TOTPKEY",
            "shoonya_vendor_code": "VC123",
            "shoonya_api_key": "APIKEY"
        },
        "runtime": {
            "paper_only": False
        }
    }
    with patch("app.broker.shoonya.ShoonyaBrokerAdapter.connect", return_value=True):
        adapter = get_broker_adapter(cfg, test_db)
        assert isinstance(adapter, ShoonyaBrokerAdapter)
