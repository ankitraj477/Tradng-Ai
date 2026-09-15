from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import DB
from app.config import load_config
from app.risk import RiskManager

def test_risk_rejects_zero():
    db=DB(":memory:")
    db.ensure_account(1000,100000)
    r=RiskManager(db,load_config())
    p={"risk_reward":2,"price":100,"confidence":80}
    assert r.approve(p,0)=="REJECT"
