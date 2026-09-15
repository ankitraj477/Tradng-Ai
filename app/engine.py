import time
from datetime import datetime, timezone
from .config import load_config
from .db import DB
from .market_hours import market_open
from .data.demo_provider import DemoProvider
from .data.nifty500_provider import Nifty500Provider
from .data.validator import validate_history
from .indicators import indicators
from .scanner import Scanner
from .ai_trader import AITrader
from .portfolio import PortfolioManager
from .risk import RiskManager
from .execution import PaperExecution
from .regime import detect
from .learning import LearningEngine
from .news import NewsProvider

class TradingEngine:
    def __init__(self, live=False):
        self.cfg=load_config()
        self.cfg["live_data"]=live or self.cfg["live_data"]
        self.db=DB(self.cfg["database_path"])
        self.db.ensure_account(self.cfg["capital"]["starting"],self.cfg["capital"]["target"])
        self.provider=Nifty500Provider() if self.cfg["live_data"] else DemoProvider()
        self.scanner=Scanner(self.cfg["market"]["max_candidates"],self.cfg["use_cpp_scanner"])
        self.learning=LearningEngine(self.db)
        self.news=NewsProvider()
        self.ai=AITrader(self.learning)
        self.pm=PortfolioManager(self.db,self.cfg)
        self.risk=RiskManager(self.db,self.cfg)
        self.exec=PaperExecution(self.db,self.cfg)

    def market_context(self):
        try:
            df=self.provider.history("^NSEI",period="3mo",interval="5m")
            ok,msg=validate_history(df,self.cfg["market"]["data_max_age_seconds"])
            if not ok: return {"ok":False,"reason":msg,**detect(None)}
            x=indicators(df)
            if x.empty: return {"ok":False,"reason":"insufficient indicator data",**detect(None)}
            ctx=detect(x.iloc[-1].to_dict())
            return {"ok":True,"reason":"ok",**ctx}
        except Exception as e:
            return {"ok":False,"reason":repr(e),**detect(None)}

    def cycle(self):
        ctx=self.market_context()
        self.db.set_market(ctx["regime"],ctx["sentiment"],ctx["nifty"],ctx["ok"])
        if self.cfg["live_data"] and not market_open():
            self.db.log("INFO","Indian market closed: monitoring/preparation cycle.")
            self.db.log("INFO",f"Learning snapshot: {self.learning.recommendation()}")
            self.db.log("INFO",f"News items available: {len(self.news.recent(10))}")
            self.snapshot()
            return
        if self.cfg["live_data"] and not ctx["ok"]:
            self.db.log("WARN",f"DATA KILL SWITCH: {ctx['reason']}")
            return

        a=self.db.account()
        self.manage_positions()
        candidates=self.scanner.scan(self.provider,a["cash"])
        if not candidates:
            self.db.log("INFO","No affordable candidates.")
            self.snapshot()
            return

        proposals=[]
        for c in candidates[:min(10,len(candidates))]:
            p=self.ai.propose(c,ctx["regime"])
            decision="PENDING"
            qty=0
            if p["action"] in {"BUY","SHORT"}:
                qty=self.pm.size(p)
                decision=self.risk.approve(p,qty)
                if decision=="APPROVE":
                    proposals.append((p,qty))
            self.db.add_decision({**p,"risk_decision":decision})

        if proposals:
            proposals=proposals[:self.cfg["market"].get("max_open_positions",5)]
            p,qty=max(proposals,key=lambda x:x[0]["confidence"])
            if (self.exec.buy(p,qty,ctx["regime"]) if p["action"]=="BUY" else self.exec.short(p,qty,ctx["regime"])):
                self.db.log("INFO",f"Approved paper trade: {p['symbol']} x{qty}")

        self.manage_positions()
        self.snapshot()

    def manage_positions(self):
        for p in self.db.positions():
            try:
                q=self.provider.quote(p["symbol"])
                if not q: continue
                price=q["price"]
                if p["side"]=="LONG":
                    if price <= p["stop_loss"]:
                        self.exec.close(p["symbol"],price,"Stop loss","")
                    elif price >= p["target"]:
                        self.exec.close(p["symbol"],price,"Target reached","")
                else:
                    if price >= p["stop_loss"]:
                        self.exec.close(p["symbol"],price,"Short stop loss","")
                    elif price <= p["target"]:
                        self.exec.close(p["symbol"],price,"Short target reached","")
            except Exception as e:
                self.db.log("ERROR",f"Position management {p['symbol']}: {e!r}")

    def snapshot(self):
        a=self.db.account()
        positions=self.db.positions()
        value=a["cash"]+sum(p["qty"]*p["current_price"] for p in positions if p["side"]=="LONG")+sum((p["entry_price"]-p["current_price"])*p["qty"] for p in positions if p["side"]=="SHORT")
        peak=max(a["peak_value"],value)
        self.db.update_account(a["cash"],peak)
        self.db.add_equity(value,value-a["starting_capital"])

    def run_forever(self):
        while True:
            try:
                self.cycle()
            except Exception as e:
                self.db.log("ERROR",repr(e))
            time.sleep(self.cfg["market"]["decision_interval_minutes"]*60)
