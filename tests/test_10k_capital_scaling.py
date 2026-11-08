import json
import os
import pytest
from app.db import DB
from app.intraday.scanner import IntradayScanner
from app.portfolio import PortfolioManager
from app.risk import RiskManager

def test_config_10k_starting_and_50k_target():
    with open("config/default.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["capital"]["starting"] == 10000.0
    assert cfg["capital"]["target"] == 50000.0
    assert cfg["daily_target_pct"] == 0.05

def test_scanner_price_ceiling_for_10k():
    cfg = {"capital": {"starting": 10000.0, "target": 50000.0}, "micro_account": True}
    
    class DummyProvider:
        def quote(self, sym):
            prices = {
                "SBIN.NS": {"price": 820.0, "volume": 1000000, "change_pct": 2.5},
                "INFY.NS": {"price": 1750.0, "volume": 500000, "change_pct": 1.8},
                "TTML.NS": {"price": 75.0, "volume": 2000000, "change_pct": 4.0},
                "TCS.NS": {"price": 4100.0, "volume": 300000, "change_pct": 0.9},
                "PENNY.NS": {"price": 3.0, "volume": 50000, "change_pct": 5.0},
            }
            return prices.get(sym)

    scanner = IntradayScanner(provider=DummyProvider(), cfg=cfg)
    candidates = scanner.scan_opening_candidates(["SBIN.NS", "INFY.NS", "TTML.NS", "TCS.NS", "PENNY.NS"])
    symbols = [c["symbol"] for c in candidates]
    
    # SBIN (820), INFY (1750), and TTML (75) should be allowed
    assert "SBIN.NS" in symbols
    assert "INFY.NS" in symbols
    assert "TTML.NS" in symbols
    # TCS (4100 > 2500) and PENNY (3 < 10) must be excluded
    assert "TCS.NS" not in symbols
    assert "PENNY.NS" not in symbols

def test_portfolio_sizing_10k_capital():
    cfg = {
        "capital": {"starting": 10000.0, "target": 50000.0},
        "hyper_aggressive": True,
        "micro_account": True,
        "market": {"max_open_positions": 5},
        "execution": {"short_margin_pct": 0.25},
        "risk": {"max_sector_exposure_pct": 0.60, "max_position_risk_pct": 0.02}
    }
    
    class DummyDB:
        def account(self):
            return {"cash": 10000.0, "starting_capital": 10000.0, "target_capital": 50000.0}
        def positions(self):
            return []
        def get_capital_allocation(self):
            return {"intraday": 100.0, "swing": 0.0, "fno": 0.0}

    pm = PortfolioManager(db=DummyDB(), cfg=cfg)
    
    # Test sizing for SBIN at 800: should allocate ~4500 (10000 * 0.90 / 2) -> 5 shares = 4000
    proposal = {"symbol": "SBIN.NS", "price": 800.0, "stop_loss": 790.0, "sector": "Financial"}
    qty = pm.size(proposal)
    assert qty == 5  # 4500 // 800 = 5 shares
    assert qty * 800.0 <= 4500.0

def test_engine_dynamic_capital_tiers():
    from app.engine import TradingEngine
    
    class DummyDB:
        def __init__(self, cash):
            self._cash = cash
        def account(self):
            return {"cash": self._cash, "starting_capital": 10000.0, "target_capital": 50000.0}
        def positions(self):
            return []
        def log(self, *args, **kwargs):
            pass

    engine = TradingEngine.__new__(TradingEngine)
    
    # At 10,000 (starting): Tier 1 (< 20,000)
    engine.db = DummyDB(10000.0)
    assert engine.get_capital_tier() == 1
    
    # At 15,000: Tier 1
    engine.db = DummyDB(15000.0)
    assert engine.get_capital_tier() == 1
    
    # At 22,000: Tier 2 (20,000 to 35,000)
    engine.db = DummyDB(22000.0)
    assert engine.get_capital_tier() == 2
    
    # At 38,000: Tier 3 (> 35,000)
    engine.db = DummyDB(38000.0)
    assert engine.get_capital_tier() == 3

def test_database_ledger_state():
    db = DB("data/trader.db")
    acc = db.account()
    assert acc is not None
    assert acc["cash"] == 10000.0
    assert acc["starting_capital"] == 10000.0
    assert acc["target_capital"] == 50000.0
    assert len(db.positions()) == 0
