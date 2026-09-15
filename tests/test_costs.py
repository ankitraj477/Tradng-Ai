from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import DB
from app.execution import PaperExecution

def test_intraday_cost_direction():
    db=DB(':memory:'); db.ensure_account(1000,100000)
    cfg={'execution':{'slippage_bps':0,'brokerage_pct':0,'sebi_turnover_fee_pct':0.0001,'gst_pct':0.18,'stamp_duty_non_delivery_pct':0.003,'stamp_duty_delivery_pct':0.015,'stt_intraday_sell_pct':0.025,'stt_delivery_pct':0.10}}
    e=PaperExecution(db,cfg)
    assert e.cost(10000,'SELL') > e.cost(10000,'BUY')
