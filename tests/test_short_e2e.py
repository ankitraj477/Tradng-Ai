import numpy as np
import pandas as pd
from app.scanner import Scanner
from app.ai_trader import AITrader
from app.risk import RiskManager
from app.db import DB
from app.config import load_config

class FallingProvider:
    def __init__(self):
        prices = np.linspace(150, 100, 80)
        self.df = pd.DataFrame({
            "Open": prices + 0.5,
            "High": prices + 1.0,
            "Low": prices - 1.0,
            "Close": prices,
            "Volume": np.full(80, 2000.0),
        }, index=pd.date_range("2026-01-01", periods=80, freq="5min"))

    def symbols(self):
        return ["FALL.NS"]

    def metadata(self):
        return {}

    def history(self, symbol):
        return self.df

    def history_many(self, symbols):
        return {s: self.df for s in symbols}

def test_synthetic_falling_stock_scanner_ai_risk_e2e():
    provider = FallingProvider()
    candidates = Scanner(10).scan(provider, 1000)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["symbol"] == "FALL.NS"
    assert c["bear_score"] >= 65

    proposal = AITrader().propose(c, "Weak bearish", "Neutral")
    assert proposal["action"] == "SHORT"
    assert proposal["stop_loss"] > proposal["price"]
    assert proposal["target"] < proposal["price"]

    db = DB(":memory:")
    db.ensure_account(10000.0, 100000.0)
    cfg = load_config()
    risk = RiskManager(db, cfg)
    assert risk.approve(proposal, 1) == "APPROVE"
