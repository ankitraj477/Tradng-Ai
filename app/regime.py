def detect(nifty_row=None, india_vix=None, breadth=None, fii_dii_flows=None, global_sentiment=None):
    """
    Market Regime Detector ingesting India VIX, NIFTY 50/200 DMA trend,
    market breadth (% above 50 DMA, Advance/Decline), institutional net flows,
    and international market sentiment.
    """
    if not nifty_row:
        return {
            "regime": "Mixed/uncertain", "sentiment": "Neutral", "nifty": "Unknown",
            "size_multiplier": 1.0, "allowed_sides": ["LONG", "SHORT"]
        }

    r = nifty_row
    ret = float(r.get("ret_day", r.get("ret_20", 0)) or 0)
    close = float(r.get("Close", 0) or 0)
    ema = float(r.get("ema20", 0) or 0)
    vol = float(r.get("volatility", 0) or 0)
    dma50 = float(r.get("dma50", ema) or ema)
    dma200 = float(r.get("dma200", dma50) or dma50)

    # VIX processing
    vix_val = float(india_vix.get("Close", india_vix) if isinstance(india_vix, dict) else (india_vix or 0.0))

    # Breadth processing
    pct_above_50 = None
    ad_ratio = None
    if isinstance(breadth, dict):
        if "pct_above_50dma" in breadth:
            pct_above_50 = float(breadth["pct_above_50dma"])
        if "advances" in breadth and "declines" in breadth and breadth["declines"] > 0:
            ad_ratio = float(breadth["advances"]) / float(breadth["declines"])

    # Baseline regime from trend and volatility
    is_high_vol = (vol > 0.45) or (vix_val >= 22.0)
    is_extreme_vol = (vix_val >= 30.0)

    size_multiplier = 1.0
    allowed_sides = ["LONG", "SHORT"]

    if is_extreme_vol:
        regime = "Extreme volatility"
        sentiment = "Risk-Off"
        size_multiplier = 0.0
        allowed_sides = []
    elif is_high_vol:
        regime = "High volatility"
        sentiment = "Mixed"
        size_multiplier = 0.5
        allowed_sides = ["LONG", "SHORT"]
    elif ret > 0.01 and close > dma50:
        # Confirm with breadth if available
        if pct_above_50 is not None and pct_above_50 < 40.0:
            regime = "Weak bullish"
            sentiment = "Neutral"
        else:
            regime = "Strong bullish trend"
            sentiment = "Bullish"
            allowed_sides = ["LONG"]
    elif ret < -0.01 and close < dma50:
        if pct_above_50 is not None and pct_above_50 > 60.0:
            regime = "Weak bearish"
            sentiment = "Neutral"
        else:
            regime = "Strong bearish trend"
            sentiment = "Bearish"
            allowed_sides = ["SHORT"]
    elif ret > 0:
        regime = "Weak bullish"
        sentiment = "Bullish"
        allowed_sides = ["LONG", "SHORT"]
    elif ret < 0:
        regime = "Weak bearish"
        sentiment = "Bearish"
        allowed_sides = ["LONG", "SHORT"]
    else:
        regime = "Sideways"
        sentiment = "Neutral"
        allowed_sides = ["LONG", "SHORT"]

    if global_sentiment:
        gs = str(global_sentiment).upper()
        if "CRASH" in gs or "HIGH RISK" in gs:
            size_multiplier = min(size_multiplier, 0.5)
            if regime not in ("Extreme volatility", "Strong bearish trend"):
                regime = "High volatility (Global Risk)"
                sentiment = "Risk-Off"
        elif "BEAR" in gs and sentiment == "Neutral":
            sentiment = "Bearish"
        elif "BULL" in gs and sentiment == "Neutral":
            sentiment = "Bullish"

    return {
        "regime": regime,
        "sentiment": sentiment,
        "nifty": f"Trend={regime}",
        "size_multiplier": size_multiplier,
        "allowed_sides": allowed_sides,
        "vix": vix_val if vix_val > 0 else None,
        "breadth_pct": pct_above_50,
        "ad_ratio": ad_ratio
    }
