import time
from .config import load_config
from .db import DB
from .market_hours import market_open, market_phase, holiday_name
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
from .market_intelligence import MarketIntelligence
from .position_manager import PositionManager
from .selection import CandidateSelector
from .accounting import portfolio_metrics
from .runtime import preflight

class TradingEngine:
    def __init__(self, live=False):
        self.cfg=load_config()
        self.cfg["live_data"]=live or self.cfg["live_data"]
        self.db=DB(self.cfg["database_path"])
        self.db.ensure_account(self.cfg["capital"]["starting"],self.cfg["capital"]["target"])
        self.provider=Nifty500Provider() if self.cfg["live_data"] else DemoProvider()
        self.universe_ready=True
        self.universe_reason="demo universe"
        if self.cfg["live_data"]:
            ok,count=self.provider.universe.validate(450) if hasattr(self.provider,"universe") else (False,0)
            self.universe_ready=ok
            self.universe_reason=f"{count} NIFTY 500 constituents loaded; need at least 450" if not ok else f"{count} constituents loaded"
        self.scanner=Scanner(self.cfg["market"]["max_candidates"],self.cfg["use_cpp_scanner"])
        self.learning=LearningEngine(self.db,self.cfg)
        self.news=NewsProvider()
        self.intel=MarketIntelligence(self.news)
        self.ai=AITrader(self.learning)
        self.pm=PortfolioManager(self.db,self.cfg)
        self.risk=RiskManager(self.db,self.cfg)
        self.exec=PaperExecution(self.db,self.cfg)
        self.positions=PositionManager(self.db,self.exec,self.provider,self.cfg)
        self.selector=CandidateSelector(self.learning,self.cfg["risk"].get("max_sector_exposure_pct",0.40))
        self.preflight=preflight(self.cfg,self.provider)

    def market_context(self):
        try:
            # Yahoo restricts intraday 5m history to a shorter lookback; 60d is safe.
            df=self.provider.history("^NSEI",period=self.cfg["market"].get("history_period","60d"),interval="5m")
            ok,msg=validate_history(df,self.cfg["market"]["data_max_age_seconds"])
            if not ok:return {"ok":False,"reason":msg,**detect(None),"news_items":[]}
            x=indicators(df)
            if x.empty:return {"ok":False,"reason":"insufficient indicator data",**detect(None),"news_items":[]}
            metadata=self.provider.metadata() if hasattr(self.provider,"metadata") else {}
            return {"ok":True,"reason":"ok",**self.intel.build(x.iloc[-1].to_dict(),metadata)}
        except Exception as e:
            return {"ok":False,"reason":repr(e),**detect(None),"news_items":[]}

    def cycle(self):
        ctx=self.market_context()
        self.db.set_market(ctx["regime"],ctx["sentiment"],ctx["nifty"],ctx["ok"])
        if self.cfg["live_data"] and not self.universe_ready:
            self.db.log("ERROR",f"UNIVERSE KILL SWITCH: {self.universe_reason}. Update data/nifty500.csv before live paper trading.")
            self.snapshot(); return
        if self.cfg["live_data"] and not market_open():
            phase=market_phase(); holiday=holiday_name()
            self.db.log("INFO",f"Indian market {phase.lower()}: analysis/preparation cycle." + (f" Holiday={holiday}" if holiday else ""))
            self.db.log("INFO",f"Learning snapshot: {self.learning.recommendation()}")
            self.db.log("INFO",f"News items available: {ctx.get('news_count',0)}")
            self.snapshot(); return
        if self.cfg["live_data"] and not ctx["ok"]:
            self.db.log("WARN",f"DATA KILL SWITCH: {ctx['reason']}")
            self.snapshot(); return

        allowed,why=self.risk.trading_allowed()
        self.positions.manage()
        if not allowed:
            self.db.log("WARN",f"TRADING BLOCKED: {why}")
            self.snapshot(); return
        a=self.db.account()
        candidates=self.scanner.scan(self.provider,a["cash"])
        metadata=self.provider.metadata() if hasattr(self.provider,"metadata") else {}
        enriched=[self.intel.enrich(c,ctx) for c in candidates]
        if not enriched:
            self.db.log("INFO","No candidates."); self.snapshot(); return

        proposals=[]
        for c in enriched[:min(20,len(enriched))]:
            p=self.ai.propose(c,ctx["regime"],ctx["sentiment"])
            p["score"]=c.get("score",0)
            decision="PENDING"; qty=0
            if p["action"] in {"BUY","SHORT"}:
                qty=self.pm.size(p)
                decision=self.risk.approve(p,qty)
                if decision=="APPROVE": proposals.append((p,qty))
            self.db.add_decision({**p,"risk_decision":decision})

        if proposals:
            ranked_inputs=[]
            for p,qty in proposals:
                ranked_inputs.append({**p,"best_strategy":p["strategy"],"qty":qty,"current_price":p["price"]})
            ranked=self.selector.rank(ranked_inputs,self.db.positions(),ctx["regime"],self.pm.metrics()["equity"])
            chosen=ranked[0]
            p,qty=next((x for x in proposals if x[0]["symbol"]==chosen["symbol"]),(None,0))
            if p:
                ok=(self.exec.buy(p,qty,ctx["regime"]) if p["action"]=="BUY" else self.exec.short(p,qty,ctx["regime"]))
                if ok:self.db.log("INFO",f"Selected paper trade: {p['symbol']} x{qty} strategy={p['strategy']}")

        self.positions.manage()
        self.snapshot()

    def snapshot(self):
        a=self.db.account(); positions=self.db.positions()
        m=portfolio_metrics(a,positions,self.cfg["execution"].get("short_margin_pct",0.25))
        peak=max(float(a.get("peak_value",0) or 0),m["equity"])
        self.db.update_account(a["cash"],peak)
        self.db.add_equity(m["equity"],m["equity"]-a["starting_capital"])

    def run_forever(self):
        decision_interval=max(60,int(self.cfg["market"]["decision_interval_minutes"]*60))
        protection_interval=max(10,int(self.cfg["market"].get("protection_interval_seconds",30)))
        next_decision=time.time()
        while True:
            now=time.time()
            if now>=next_decision:
                try:self.cycle()
                except Exception as e:self.db.log("ERROR",repr(e))
                next_decision=(int(time.time())//decision_interval+1)*decision_interval
            else:
                try:
                    if self.db.positions() and (not self.cfg["live_data"] or market_open()): self.positions.manage()
                except Exception as e:self.db.log("ERROR",f"Protection loop: {e!r}")
            time.sleep(min(protection_interval,max(1,next_decision-time.time())))

if __name__ == "__main__":
    engine = TradingEngine()
    engine.run_forever()