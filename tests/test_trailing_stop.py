from app.ai_trader import AITrader
from app.config import load_config
from app.db import DB
from app.execution import PaperExecution
from app.position_manager import PositionManager

class ConstantQuote:
    def __init__(self, price=100.0):
        self.price = price
    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}

def test_atr_stored_and_stop_unchanged_at_same_price():
    c = {
        "symbol": "ATRTEST.NS",
        "price": 100.0,
        "score": 85.0,
        "rsi": 65.0,
        "atr": 2.0,
        "rel_volume": 1.5,
        "ret_5": 0.02,
        "ret_20": 0.04,
        "volatility": 0.02,
        "sector": "IT",
    }
    proposal = AITrader().propose(c, "Bullish", "Bullish")
    assert proposal["action"] == "BUY"
    assert "atr" in proposal
    assert proposal["atr"] == 2.0
    assert proposal["stop_loss"] == 97.0  # 100 - 1.5 * 2.0

    cfg = load_config()
    db = DB(":memory:")
    db.ensure_account(10000.0, 100000.0)
    exec_engine = PaperExecution(db, cfg)
    assert exec_engine.buy(proposal, 1, "Bullish")

    pos = db.positions()[0]
    assert pos["atr"] == 2.0
    assert pos["stop_loss"] == 97.0

    pm = PositionManager(db, exec_engine, ConstantQuote(100.0), cfg)
    closed = pm.manage()
    assert closed == 0

    pos_after = db.positions()[0]
    # Stop loss must be unchanged at 97.0 after first pass at same price 100.0
    assert pos_after["stop_loss"] == 97.0
