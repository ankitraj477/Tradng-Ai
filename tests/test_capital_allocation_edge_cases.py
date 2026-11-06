import json
import pytest
from app.dashboard import create_app
from app.db import DB

@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db = DB(db_path)
    db.init()
    return db

def test_zero_capital_allocation_values(test_db):
    """Test that 0% allocations are preserved and not clobbered."""
    res = test_db.set_capital_allocation(100, 0, 0)
    assert res["intraday"] == 100.0
    assert res["swing"] == 0.0
    assert res["fno"] == 0.0

    retrieved = test_db.get_capital_allocation()
    assert retrieved["intraday"] == 100.0
    assert retrieved["swing"] == 0.0
    assert retrieved["fno"] == 0.0

def test_api_capital_allocation_endpoints(test_db):
    """Test both /api/capital-allocation and /api/capital/allocation."""
    app = create_app(db=test_db, cfg={"dashboard": {"token": "test_tok"}})
    client = app.test_client()

    headers = {"Authorization": "Bearer test_tok"}

    # 1. Post to /api/capital-allocation with 0% values
    r1 = client.post("/api/capital-allocation", headers=headers, json={"intraday": 100, "swing": 0, "fno": 0})
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["capital_allocation"]["intraday"] == 100.0
    assert d1["capital_allocation"]["swing"] == 0.0
    assert d1["capital_allocation"]["fno"] == 0.0

    # 2. Post to /api/capital/allocation with 0% values
    r2 = client.post("/api/capital/allocation", headers=headers, json={"intraday": 80, "swing": 20, "fno": 0})
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert d2["capital_allocation"]["intraday"] == 80.0
    assert d2["capital_allocation"]["swing"] == 20.0
    assert d2["capital_allocation"]["fno"] == 0.0

    # 3. GET /api/capital-allocation returns current allocation
    r3 = client.get("/api/capital-allocation")
    assert r3.status_code == 200
    d3 = r3.get_json()
    assert d3["intraday"] == 80.0
    assert d3["swing"] == 20.0
    assert d3["fno"] == 0.0
