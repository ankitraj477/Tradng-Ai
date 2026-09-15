from collections import defaultdict
import math

class LearningEngine:
    """Controlled adaptation: weights change only from realized historical outcomes."""
    def __init__(self, db):
        self.db=db

    def strategy_stats(self):
        trades=self.db.all_trades()
        out=defaultdict(list)
        for t in trades:
            if t.get("strategy"):
                out[t["strategy"]].append(float(t.get("pnl") or 0))
        result={}
        for name, pnls in out.items():
            wins=[x for x in pnls if x>0]
            losses=[x for x in pnls if x<0]
            result[name]={
                "trades":len(pnls),
                "win_rate":len(wins)/len(pnls)*100,
                "avg_pnl":sum(pnls)/len(pnls),
                "profit_factor":sum(wins)/abs(sum(losses)) if losses else None
            }
        return result

    def weights(self, minimum_sample=20):
        stats=self.strategy_stats()
        weights={}
        for name,s in stats.items():
            # No adaptation until enough observations exist.
            if s["trades"] < minimum_sample:
                weights[name]=1.0
                continue
            pf=s["profit_factor"] or 0
            # Bounded multiplier: learning can influence selection, never risk limits.
            weights[name]=max(0.50,min(1.50,0.75+0.25*min(pf,3)))
        return weights

    def recommendation(self, minimum_sample=20):
        return {
            "strategy_weights":self.weights(minimum_sample),
            "stats":self.strategy_stats(),
            "policy":"Weights only; deterministic risk and execution rules cannot be modified."
        }
