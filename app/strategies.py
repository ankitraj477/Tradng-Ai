def evaluate(c):
    signals=[]
    momentum=min(100,max(0,50+c["ret_5"]*500+c["rel_volume"]*10))
    breakout=75 if c["score"]>=70 and c["rel_volume"]>1.2 else 45
    trend=80 if c["ret_20"]>0 and c["rsi"]>50 else 40
    meanrev=70 if c["rsi"]<35 else 35
    news_score=c.get("news_bias",0)
    news=50+news_score*2
    signals += [
        ("Momentum",momentum),("Breakout",breakout),("Trend",trend),
        ("Mean Reversion",meanrev),("News/Event",max(0,min(100,news)))
    ]
    return signals
