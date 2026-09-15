from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import DB
from app.execution import PaperExecution

def cfg():
    return {"execution":{"slippage_bps":0,"brokerage":0,"sebi_turnover_fee_pct":0,"gst_pct":0,
                         "stamp_duty_non_delivery_pct":0,"stt_intraday_sell_pct":0}}
def test_buy_and_sell():
    db=DB(":memory:"); db.ensure_account(1000,100000)
    e=PaperExecution(db,cfg())
    p={"symbol":"TEST","price":100,"stop_loss":95,"target":110,"strategy":"Test","confidence":80}
    assert e.buy(p,2,"Sideways")
    assert len(db.positions())==1
    assert e.close("TEST",110,"target","Sideways")
    assert len(db.positions())==0
    assert db.trades(1)[0]["pnl"]==20
