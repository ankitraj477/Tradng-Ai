def detect(nifty_row=None):
    if not nifty_row:
        return {"regime":"Mixed/uncertain","sentiment":"Neutral","nifty":"Unknown"}
    r=nifty_row
    ret=float(r.get("ret_20",0) or 0)
    close=float(r.get("Close",0) or 0)
    ema=float(r.get("ema20",0) or 0)
    vol=float(r.get("volatility",0) or 0)
    if vol > 0.45:
        regime="High volatility"; sentiment="Mixed"
    elif ret > 0.03 and close > ema:
        regime="Strong bullish trend"; sentiment="Bullish"
    elif ret < -0.03 and close < ema:
        regime="Strong bearish trend"; sentiment="Bearish"
    elif ret > 0:
        regime="Weak bullish"; sentiment="Bullish"
    elif ret < 0:
        regime="Weak bearish"; sentiment="Bearish"
    else:
        regime="Sideways"; sentiment="Neutral"
    return {"regime":regime,"sentiment":sentiment,"nifty":f"Trend={regime}"}
