from app.config import load_config
from app.db import DB
from app.portfolio import PortfolioManager
from app.risk import RiskManager

def test_sizing_capped_by_sector_headroom():
    cfg = load_config()
    db = DB(":memory:")
    # ₹1000 equity, 40% sector limit = ₹400
    db.ensure_account(1000.0, 100000.0)
    pm = PortfolioManager(db, cfg)
    risk = RiskManager(db, cfg)

    # ₹150 stock in IT sector
    proposal = {
        "symbol": "TCS.NS",
        "action": "BUY",
        "price": 150.0,
        "stop_loss": 147.0,  # risk per share = 3.0 -> risk cash 20 / 3 = 6 shares
        "target": 160.0,
        "confidence": 80,
        "risk_reward": 3.3,
        "sector": "IT",
    }

    qty = pm.size(proposal)
    # Headroom = ₹400 / 150 = 2 shares. Should NOT be 5 or 6 shares!
    assert qty == 2
    assert risk.approve(proposal, qty) == "APPROVE"

def test_max_open_positions_enforced():
    cfg = load_config()
    cfg["market"]["max_open_positions"] = 2
    db = DB(":memory:")
    db.ensure_account(10000.0, 100000.0)
    pm = PortfolioManager(db, cfg)
    risk = RiskManager(db, cfg)

    with db.conn() as c:
        c.execute("""INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,strategy,confidence,opened_at,sector)
                     VALUES('A','LONG',1,100,100,90,120,'T',80,'2026-01-01','IT'),
                           ('B','LONG',1,100,100,90,120,'T',80,'2026-01-01','Auto')""")

    proposal = {
        "symbol": "C", "action": "BUY", "price": 100.0, "stop_loss": 90.0, "target": 120.0,
        "confidence": 80, "risk_reward": 2.0, "sector": "Pharma"
    }
    assert pm.size(proposal) == 0
    assert risk.approve(proposal, 1) == "REJECT"
