from collections import defaultdict

class LearningEngine:
    """Bounded, outcome-only adaptation. Never changes hard risk/execution policy."""
    def __init__(self, db, cfg=None):
        self.db=db
        self.cfg=cfg or {}
        lcfg=self.cfg.get("learning",{})
        self.minimum_sample=int(lcfg.get("min_trades",20))
        self.min_weight=float(lcfg.get("min_weight",0.5))
        self.max_weight=float(lcfg.get("max_weight",1.5))

    def strategy_stats(self):
        trades=self.db.all_trades(); out=defaultdict(list)
        for t in trades:
            if t.get("strategy") and t.get("pnl") is not None: out[t["strategy"]].append(float(t["pnl"]))
        result={}
        for name,pnls in out.items():
            wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
            result[name]={"trades":len(pnls),"win_rate":len(wins)/len(pnls)*100,
                          "avg_pnl":sum(pnls)/len(pnls),
                          "profit_factor":sum(wins)/abs(sum(losses)) if losses else None}
        return result

    def _weight(self, stats):
        if stats["trades"] < self.minimum_sample: return 1.0
        pf=stats["profit_factor"] or 0
        return max(self.min_weight,min(self.max_weight,0.75+0.25*min(pf,3)))

    def weights(self, minimum_sample=None):
        old=self.minimum_sample
        if minimum_sample is not None: self.minimum_sample=int(minimum_sample)
        try: return {k:self._weight(v) for k,v in self.strategy_stats().items()}
        finally: self.minimum_sample=old

    def regime_stats(self):
        out=defaultdict(list)
        for t in self.db.all_trades():
            if t.get("regime") and t.get("pnl") is not None: out[t["regime"]].append(float(t["pnl"]))
        result={}
        for name,p in out.items():
            result[name]={"trades":len(p),"win_rate":sum(x>0 for x in p)/len(p)*100,
                          "avg_pnl":sum(p)/len(p),"total_pnl":sum(p)}
        return result

    def strategy_regime_stats(self):
        out=defaultdict(list)
        for t in self.db.all_trades():
            if t.get("strategy") and t.get("regime") and t.get("pnl") is not None:
                out[(t["strategy"],t["regime"])].append(float(t["pnl"]))
        return {f"{s}|{r}":{"trades":len(p),"win_rate":sum(x>0 for x in p)/len(p)*100,
                              "avg_pnl":sum(p)/len(p)} for (s,r),p in out.items()}

    def weight_for(self,strategy,regime=None):
        base=self.weights().get(strategy,1.0)
        if not regime: return base
        s=self.strategy_regime_stats().get(f"{strategy}|{regime}")
        if not s or s["trades"] < self.minimum_sample: return base
        # Small regime adjustment, bounded and intentionally weaker than strategy learning.
        adj=0.9 + min(0.2,max(0.0,s["win_rate"]/100*0.2))
        return max(self.min_weight,min(self.max_weight,base*adj))

    def recommendation(self):
        return {"strategy_weights":self.weights(),"regime_stats":self.regime_stats(),
                "strategy_regime_stats":self.strategy_regime_stats(),
                "policy":"Outcome-only bounded weights; hard risk, stops and execution remain immutable."}
