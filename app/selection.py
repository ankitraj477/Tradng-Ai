class CandidateSelector:
    """Portfolio-aware ranking: quality plus learned regime fit, with concentration guardrails."""
    def __init__(self, learning=None, max_sector=0.40): self.learning=learning; self.max_sector=max_sector
    def rank(self,candidates, positions, regime, equity):
        sector_value={}
        for p in positions: sector_value[p.get("sector","Unknown")]=sector_value.get(p.get("sector","Unknown"),0)+p["qty"]*p["current_price"]
        ranked=[]
        for c in candidates:
            learned=self.learning.weight_for(c.get("best_strategy","Momentum"),regime) if self.learning else 1.0
            sector=c.get("sector","Unknown"); concentration=sector_value.get(sector,0)/max(equity,1)
            penalty=max(0,concentration-self.max_sector)*50
            score=float(c.get("score",0))*learned-penalty
            ranked.append((score,c))
        return [c for _,c in sorted(ranked,key=lambda x:x[0],reverse=True)]
