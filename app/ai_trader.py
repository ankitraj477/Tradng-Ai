from .strategies import evaluate

class AITrader:
    def __init__(self, learning=None): self.learning=learning

    def propose(self,c,regime):
        sig=evaluate(c)
        weights=self.learning.weights() if self.learning else {}
        weighted=[(name,score*weights.get(name,1.0)) for name,score in sig]
        avg=sum(v for _,v in weighted)/len(weighted); best=max(weighted,key=lambda x:x[1])
        bearish=regime in {"Bearish","Strong Bearish"} and c.get("ret_5",0)<0 and c.get("rsi",50)<50
        if (avg>=65 and c["score"]>=60) or (bearish and c["score"]>=70 and avg>=45):
            action="SHORT" if bearish else "BUY"
            confidence=min(95,round(avg)); strategy=best[0]
            reason=(f"Quantitative confluence: {strategy} strongest; relative volume {c['rel_volume']:.2f}x, "
                    f"RSI {c['rsi']:.1f}, 5-bar return {c['ret_5']*100:.2f}%. Regime: {regime}.")
        else:
            action="WAIT"; confidence=round(avg); strategy=best[0]
            reason="Evidence is insufficient for a disciplined trade."
        atr=max(c["atr"],c["price"]*0.005)
        if action=="SHORT":
            stop=c["price"]+1.5*atr; target=max(0.01,c["price"]-3*atr)
        else:
            stop=max(0.01,c["price"]-1.5*atr); target=c["price"]+3*atr
        rr=abs(target-c["price"])/max(abs(c["price"]-stop),0.01)
        return {"symbol":c["symbol"],"action":action,"price":c["price"],"confidence":confidence,
                "strategy":strategy,"reason":reason,"stop_loss":stop,"target":target,"risk_reward":rr,
                "sector":c.get("sector","Unknown")}
