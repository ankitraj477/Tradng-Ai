
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import DB
from app.risk import RiskManager
from app.accounting import portfolio_metrics

def test_stop_update_persists(tmp_path):
    db=DB(str(tmp_path/"t.db"))
    db.ensure_account(1000,100000)
    with db.conn() as c:
        c.execute("""INSERT INTO positions(symbol,side,qty,entry_price,current_price,stop_loss,target,
                     strategy,confidence,opened_at,sector)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  ("A","LONG",1,100,110,95,120,"Trend",80,"2026-09-14T08:00:00+00:00","IT"))
    db.update_stop("A",105)
    assert db.positions()[0]["stop_loss"]==105

def test_daily_loss_guard(tmp_path):
    db=DB(str(tmp_path/"t.db"))
    db.ensure_account(1000,100000)
    rm=RiskManager(db,{"risk":{"kill_switch":False,"max_drawdown_pct":1,"daily_loss_limit_pct":.05},
                       "execution":{"short_margin_pct":.25}})
    a=db.account()
    db.day_start_equity(1000)
    db.update_account(940,1000)
    ok,reason=rm.trading_allowed()
    assert not ok and reason=="daily loss limit reached"


def test_position_schema_has_atr(tmp_path):
    db=DB(str(tmp_path/"atr.db")); db.ensure_account(1000,100000)
    with db.conn() as c:
        cols={r[1] for r in c.execute("PRAGMA table_info(positions)").fetchall()}
    assert "atr" in cols


def test_execution_persists_atr():
    db=DB(":memory:"); db.ensure_account(1000,100000)
    e=__import__("app.execution",fromlist=["PaperExecution"]).PaperExecution(db,{"execution":{"slippage_bps":0,"brokerage":0,"sebi_turnover_fee_pct":0,"gst_pct":0,"stamp_duty_non_delivery_pct":0,"stt_intraday_sell_pct":0}})
    assert e.buy({"symbol":"ATR","price":100,"stop_loss":95,"target":110,"strategy":"Test","confidence":80,"atr":2.5},1,"Sideways")
    assert db.positions()[0]["atr"]==2.5


class _QuoteProvider:
    def __init__(self, price): self.price=price
    def quote(self, symbol): return {"symbol":symbol,"price":self.price}
    def history(self, *args, **kwargs): return None

def test_trailing_stop_ratchets_and_existing_stop_can_trigger():
    from app.execution import PaperExecution
    from app.position_manager import PositionManager
    cfg={"execution":{"slippage_bps":0,"brokerage":0,"sebi_turnover_fee_pct":0,"gst_pct":0,"stamp_duty_non_delivery_pct":0,"stt_intraday_sell_pct":0,"trailing_stop_atr":1,"max_hold_minutes":390}}
    db=DB(":memory:"); db.ensure_account(1000,100000)
    e=PaperExecution(db,cfg); p={"symbol":"TRAIL","price":100,"stop_loss":95,"target":120,"strategy":"Test","confidence":80,"atr":2}
    assert e.buy(p,1,"Bullish")
    pm=PositionManager(db,e,_QuoteProvider(105),cfg)
    assert pm.manage()==0
    assert db.positions()[0]["stop_loss"]==103
    pm.provider.price=104
    assert pm.manage()==0
    assert db.positions()[0]["stop_loss"]==103
    pm.provider.price=103
    assert pm.manage()==1
    assert not db.positions()
