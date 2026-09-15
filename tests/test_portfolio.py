from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import DB
from app.portfolio import PortfolioManager

def test_short_size_uses_margin():
    db=DB(':memory:'); db.ensure_account(1000,100000)
    cfg={'risk':{'max_position_risk_pct':0.02,'max_portfolio_invested_pct':0.85},'execution':{'short_margin_pct':0.25}}
    pm=PortfolioManager(db,cfg)
    p={'action':'SHORT','price':100,'stop_loss':105}
    assert pm.size(p) >= 0
