"""
Swing Scanner for NSE Equities.
Applies Mark Minervini's Stage-2 Trend Template and 20 EMA Pullback filters
with Volume Dry-Up confirmation for high-probability swing setups.
"""
import pandas as pd
import numpy as np


class SwingScanner:
    def __init__(self, provider, cfg=None):
        self.provider = provider
        self.cfg = cfg or {}

    def scan_symbol(self, symbol: str, df: pd.DataFrame = None) -> dict | None:
        """
        Evaluate a single stock for a 20 EMA Pullback swing setup.
        Returns setup dict if qualified, or None.
        """
        try:
            if df is None:
                df = self.provider.history(symbol, period="1y", interval="1d")
            if df is None or len(df) < 60:
                return None

            close = df["Close"].astype(float)
            high = df["High"].astype(float)
            low = df["Low"].astype(float)
            volume = df["Volume"].astype(float)

            if len(close) < 200:
                # If less than 200 daily bars, use available length with 50 and 20 EMA
                ema_200 = close.ewm(span=min(200, len(close)), adjust=False).mean()
            else:
                ema_200 = close.rolling(200).mean()

            ema_50 = close.ewm(span=50, adjust=False).mean()
            ema_20 = close.ewm(span=20, adjust=False).mean()

            last_close = float(close.iloc[-1])
            last_low = float(low.iloc[-1])
            last_high = float(high.iloc[-1])
            last_open = float(df["Open"].iloc[-1])
            last_vol = float(volume.iloc[-1])

            e20 = float(ema_20.iloc[-1])
            e50 = float(ema_50.iloc[-1])
            e200 = float(ema_200.iloc[-1])

            # 1. Minervini Stage 2 Uptrend Template
            # Price > 50 EMA, and 50 EMA > 200 SMA (or trending up)
            if not (last_close > e50 and e50 > e200 * 0.98):
                return None

            # 2. Proximity to 52-week High (within 28% of 52w high)
            high_52w = float(high.rolling(min(252, len(high))).max().iloc[-1])
            if high_52w > 0 and (last_close < 0.72 * high_52w):
                return None

            # 3. 20 EMA Pullback Test:
            # Low came within 2% of 20 EMA, or close is within 2.5% of 20 EMA
            dist_to_ema20 = abs(last_close - e20) / e20
            tested_ema20 = (last_low <= e20 * 1.015) and (last_close >= e20 * 0.98)

            if not (dist_to_ema20 <= 0.035 or tested_ema20):
                return None

            # 4. Volume Behavior: Volume on pullback shouldn't be massive distribution
            avg_vol_20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else last_vol
            is_volume_dry = (last_vol <= avg_vol_20 * 1.5)  # No institutional dumping

            # 5. Bullish Price Action at Support:
            # Reversal candle (close near high, hammer tail, or green candle)
            body = abs(last_close - last_open)
            candle_range = max(last_high - last_low, 0.01)
            lower_wick = min(last_open, last_close) - last_low
            is_bullish_reaction = (last_close >= last_open) or (lower_wick >= 0.35 * candle_range)

            # ATR for risk sizing
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else last_close * 0.02

            # Scoring: 70 to 95 scale
            score = 70.0
            if last_close > e20: score += 5.0
            if is_bullish_reaction: score += 10.0
            if is_volume_dry: score += 5.0
            if last_close >= 0.85 * high_52w: score += 5.0

            return {
                "symbol": symbol,
                "price": last_close,
                "ema_20": round(e20, 2),
                "ema_50": round(e50, 2),
                "ema_200": round(e200, 2),
                "high_52w": round(high_52w, 2),
                "dist_to_ema20_pct": round(dist_to_ema20 * 100, 2),
                "atr": round(atr_14, 2),
                "score": round(score, 1),
                "is_bullish_reaction": is_bullish_reaction,
                "product_type": "SWING",
            }
        except Exception:
            return None

    def scan_universe(self, symbols: list[str]) -> list[dict]:
        """Scan a list of symbols and rank candidates by setup score."""
        candidates = []
        for s in symbols:
            cand = self.scan_symbol(s)
            if cand:
                candidates.append(cand)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    scan_stage2_candidates = scan_universe


Stage2SwingScanner = SwingScanner
