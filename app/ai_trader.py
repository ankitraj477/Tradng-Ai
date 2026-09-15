from .strategies import evaluate

class AITrader:
    """Auditable V9 decision engine with bounded regime-aware learning."""
    def __init__(self, learning=None): self.learning=learning

    def propose(self,c,regime,market_sentiment="Neutral"):
        sig=evaluate(c)
        weighted=[]
        for name,score in sig:
            w=self.learning.weight_for(name,regime) if self.learning else 1.0
            weighted.append((name,score*w,w))
        avg=sum(v for _,v,_ in weighted)/len(weighted)
        best=max(weighted,key=lambda x:x[1])
        news_bias=c.get("news_bias",0)
        bullish=c.get("ret_5",0)>0 and c.get("ret_20",0)>0 and c.get("rsi",50)>=50
        bearish=c.get("ret_5",0)<0 and c.get("ret_20",0)<0 and c.get("rsi",50)<=50
        long_score=avg+max(0,news_bias)+(5 if market_sentiment=="Bullish" else 0)
        short_score=avg+max(0,-news_bias)+(5 if market_sentiment=="Bearish" else 0)
        if bullish and c["score"]>=60 and long_score>=65:
            action="BUY"; confidence=min(95,round(long_score))
        elif bearish and c["score"]>=65 and short_score>=45 and market_sentiment in {"Bearish","Neutral"}:
            action="SHORT"; confidence=min(95,round(max(60,short_score)))
        else:
            action="WAIT"; confidence=min(95,round(max(long_score,short_score)))
        atr=max(c["atr"],c["price"]*0.005)
        stop=c["price"]+1.5*atr if action=="SHORT" else max(0.01,c["price"]-1.5*atr)
        target=max(0.01,c["price"]-3*atr) if action=="SHORT" else c["price"]+3*atr
        rr=abs(target-c["price"])/max(abs(c["price"]-stop),0.01)
        reason=(f"{best[0]} strongest; score {c['score']:.0f}, RSI {c['rsi']:.1f}, "
                f"5-bar return {c['ret_5']*100:.2f}%, relative volume {c['rel_volume']:.2f}x; "
                f"market={regime}; news bias={news_bias:+d}; learned weight={best[2]:.2f}.")
        return {"symbol":c["symbol"],"action":action,"price":c["price"],"confidence":confidence,
                "strategy":best[0],"reason":reason,"stop_loss":stop,"target":target,
                "risk_reward":rr,"sector":c.get("sector","Unknown"),"regime":regime}
