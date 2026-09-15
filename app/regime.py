def detect(nifty_row=None):
    if not nifty_row:
        return {"regime":"Mixed/uncertain","sentiment":"Neutral","nifty":"Unknown"}
    r=nifty_row
    ret=r.get("ret_20",0); close=r.get("Close",0); ema=r.get("ema20",0)
    vol=r.get("volatility",0)
    if vol > 0.45:
        regime="High volatility"; sentiment="Mixed"
    elif ret > 0.03 and close > ema:
        regime="Strong bullish trend"; sentiment="Bullish"
    elif ret < -0.03 and close < ema:
        regime="Strong bearish"; sentiment="Bearish"
    elif ret > 0:
        regime="Weak bullish"; sentiment="Bullish"
    elif ret < 0:
        regime="Weak bearish"; sentiment="Bearish"
    else:
        regime="Sideways"; sentiment="Neutral"
    return {"regime":regime,"sentiment":sentiment,"nifty":"Trend="+regime}
