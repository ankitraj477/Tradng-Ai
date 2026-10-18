from app.db import DB
from app.learning import LearningEngine

def seed(db, strategy, pnl_list):
    with db.conn() as c:
        for pnl in pnl_list:
            c.execute("""INSERT INTO trades(symbol,action,side,entry_price,exit_price,qty,capital,pnl,strategy,confidence,regime,created_at)
                         VALUES('X','SELL','LONG',10,10,1,10,?,?,'80','Bullish',datetime('now'))""",
                      (pnl, strategy))

def test_all_wins_gets_max_weight():
    db = DB(":memory:")
    seed(db, "AllWins", [10.0] * 20)
    le = LearningEngine(db, {"learning": {"min_trades": 20, "min_weight": 0.5, "max_weight": 1.5}})
    weights = le.weights()
    assert weights["AllWins"] == 1.5

def test_all_loss_gets_min_weight():
    db = DB(":memory:")
    seed(db, "AllLoss", [-10.0] * 20)
    le = LearningEngine(db, {"learning": {"min_trades": 20, "min_weight": 0.5, "max_weight": 1.5}})
    weights = le.weights()
    assert weights["AllLoss"] == 0.5
