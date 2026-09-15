from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import DB
from app.execution import PaperExecution
def test_short_pnl():
    db=DB(":memory:"); db.ensure_account(1000,100000)
    cfg={"execution":{"slippage_bps":0,"brokerage":0,"sebi_turnover_fee_pct":0,"gst_pct":0,
    "stamp_duty_non_delivery_pct":0,"stt_intraday_sell_pct":0}}
    e=PaperExecution(db,cfg)
    p={"symbol":"TEST","price":100,"stop_loss":105,"target":90,"strategy":"Test","confidence":80}
    assert e.short(p,2,"Bearish")
    assert e.close("TEST",90,"target","Bearish")
    assert db.trades(1)[0]["pnl"]==20
