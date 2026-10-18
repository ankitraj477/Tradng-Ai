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
        self._cache_len=-1; self._cache={}

    def _sync(self):
        trades=self.db.all_trades()
        if len(trades)==self._cache_len: return
        self._cache_len=len(trades)
        strat, reg, sr = defaultdict(list), defaultdict(list), defaultdict(list)
        for t in trades:
            pnl=t.get("pnl"); s=t.get("strategy"); r=t.get("regime")
            if pnl is not None:
                p=float(pnl)
                if s: strat[s].append(p)
                if r: reg[r].append(p)
                if s and r: sr[(s,r)].append(p)
        st_res={}
        for name,pnls in strat.items():
            wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
            st_res[name]={"trades":len(pnls),"win_rate":len(wins)/len(pnls)*100,"avg_pnl":sum(pnls)/len(pnls),
                          "profit_factor":sum(wins)/abs(sum(losses)) if losses else None}
        reg_res={name:{"trades":len(p),"win_rate":sum(x>0 for x in p)/len(p)*100,"avg_pnl":sum(p)/len(p),"total_pnl":sum(p)} for name,p in reg.items()}
        sr_res={f"{s}|{r}":{"trades":len(p),"win_rate":sum(x>0 for x in p)/len(p)*100,"avg_pnl":sum(p)/len(p)} for (s,r),p in sr.items()}
        self._cache={"strat":st_res,"reg":reg_res,"sr":sr_res}

    def strategy_stats(self):
        self._sync(); return dict(self._cache["strat"])

    def _weight(self, stats):
        if stats["trades"] < self.minimum_sample: return 1.0
        pf = stats.get("profit_factor")
        pf = 3.0 if pf is None and stats.get("win_rate", 0) > 0 else (pf or 0.0)
        norm = min(max(float(pf), 0.0), 3.0) / 3.0
        return self.min_weight + (self.max_weight - self.min_weight) * norm

    def weights(self, minimum_sample=None):
        old=self.minimum_sample
        if minimum_sample is not None: self.minimum_sample=int(minimum_sample)
        try: return {k:self._weight(v) for k,v in self.strategy_stats().items()}
        finally: self.minimum_sample=old

    def regime_stats(self):
        self._sync(); return dict(self._cache["reg"])

    def strategy_regime_stats(self):
        self._sync(); return dict(self._cache["sr"])

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
