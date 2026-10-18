from .indicators import indicators


def decide(symbol, df, state=None):
    """
    Unified single decision function used identically by both live trading and backtesting.
    Takes price bars (OHLCV) and returns an actionable order proposal dict, or None.
    """
    if df is None or len(df) < 50:
        return None

    # Calculate indicators if not already prepared
    data = indicators(df) if "ema20" not in df.columns else df
    if data.empty:
        return None

    row = data.iloc[-1]
    close = float(row["Close"])
    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])
    rsi = float(row["rsi"])
    rel_vol = float(row.get("rel_volume", 1.0))
    atr = float(row.get("atr", close * 0.015))

    bull_score = 0
    bear_score = 0

    if close > ema20 > ema50: bull_score += 30
    elif close < ema20 < ema50: bear_score += 30

    if rsi > 55: bull_score += 15
    elif rsi < 45: bear_score += 15

    if rel_vol > 1.2:
        bull_score += 20
        bear_score += 20

    if float(row.get("ret_5", 0)) > 0: bull_score += 15
    elif float(row.get("ret_5", 0)) < 0: bear_score += 15

    if float(row.get("ret_20", 0)) > 0: bull_score += 10
    elif float(row.get("ret_20", 0)) < 0: bear_score += 10

    vwap = float(row.get("vwap", close))
    if close > vwap: bull_score += 10
    elif close < vwap: bear_score += 10

    # Minimum conviction threshold (65)
    risk_unit = max(atr * 1.5, close * 0.005)

    if bull_score >= 65 and bull_score > bear_score:
        return {
            "symbol": symbol,
            "action": "BUY",
            "side": "LONG",
            "price": close,
            "stop_loss": round(close - risk_unit, 2),
            "target": round(close + 3 * risk_unit, 2),
            "atr": atr,
            "confidence": float(bull_score),
            "strategy": "TrendFollower",
            "reason": f"Bullish alignment (score={bull_score})"
        }
    elif bear_score >= 65 and bear_score > bull_score:
        return {
            "symbol": symbol,
            "action": "SHORT",
            "side": "SHORT",
            "price": close,
            "stop_loss": round(close + risk_unit, 2),
            "target": round(close - 3 * risk_unit, 2),
            "atr": atr,
            "confidence": float(bear_score),
            "strategy": "TrendFollower",
            "reason": f"Bearish alignment (score={bear_score})"
        }

    return None
