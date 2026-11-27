"""
Institutional Candlestick Pattern Recognition & Price-Action Engine.
Zero look-ahead bias: evaluates only completed/current bar relative to prior completed bars.
Detects single-candle, two-candle, and three-candle reversal and continuation patterns
with ATR, relative volume (RVOL), EMA trend, and RSI context confirmation.
"""
from typing import Dict, Any, List
import numpy as np
import pandas as pd


class CandlestickAnalyzer:
    """
    Quantitative candlestick pattern detector for NSE equities and index derivatives.
    Supports both 5m/15m intraday charts and daily swing charts.
    """

    @staticmethod
    def _extract_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {}
        for col in df.columns:
            low = str(col).lower()
            if low == "open":
                rename_map[col] = "Open"
            elif low == "high":
                rename_map[col] = "High"
            elif low == "low":
                rename_map[col] = "Low"
            elif low == "close":
                rename_map[col] = "Close"
            elif low == "volume":
                rename_map[col] = "Volume"
        out = df.rename(columns=rename_map)
        return out

    @classmethod
    def analyze(cls, df: pd.DataFrame, min_bars: int = 5) -> Dict[str, Any]:
        """
        Analyze the latest bar and recent bars for institutional candlestick patterns.
        Returns bias ('BULLISH', 'BEARISH', 'NEUTRAL'), primary pattern, strength (0-100),
        all detected patterns, and technical context metrics.
        """
        neutral_result = {
            "pattern": "None",
            "patterns_detected": [],
            "bias": "NEUTRAL",
            "strength": 0.0,
            "candle_metrics": {},
            "reason": "Insufficient bar data for candlestick analysis",
        }
        if df is None or len(df) < min_bars:
            return neutral_result

        data = cls._extract_ohlcv(df)
        required = {"Open", "High", "Low", "Close"}
        if not required.issubset(set(data.columns)):
            return neutral_result

        o = data["Open"].astype(float)
        h = data["High"].astype(float)
        l = data["Low"].astype(float)
        c = data["Close"].astype(float)
        v = data["Volume"].astype(float) if "Volume" in data.columns else pd.Series(np.ones(len(data)), index=data.index)

        # Latest bar (bar 0 = -1, bar -1 = -2, bar -2 = -3)
        o0, h0, l0, c0 = float(o.iloc[-1]), float(h.iloc[-1]), float(l.iloc[-1]), float(c.iloc[-1])
        o1, h1, l1, c1 = float(o.iloc[-2]), float(h.iloc[-2]), float(l.iloc[-2]), float(c.iloc[-2])
        o2, h2, l2, c2 = float(o.iloc[-3]), float(h.iloc[-3]), float(l.iloc[-3]), float(c.iloc[-3])

        # Technical context
        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else max(float(tr.mean()), c0 * 0.005)
        atr = max(atr, c0 * 0.0005)

        avg_vol = float(v.iloc[:-1].tail(20).mean()) if len(v) > 2 else float(v.mean())
        cur_vol = float(v.iloc[-1])
        rvol = (cur_vol / avg_vol) if avg_vol > 0 else 1.0

        ema_fast = float(c.ewm(span=9, adjust=False).mean().iloc[-1])
        ema_slow = float(c.ewm(span=21, adjust=False).mean().iloc[-1])

        # RSI(14)
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(min(14, len(c) - 1)).mean()
        loss = (-delta.clip(upper=0)).rolling(min(14, len(c) - 1)).mean()
        last_gain = float(gain.iloc[-1]) if not pd.isna(gain.iloc[-1]) else 0.0
        last_loss = float(loss.iloc[-1]) if not pd.isna(loss.iloc[-1]) else 0.0
        if last_loss == 0.0:
            rsi = 100.0 if last_gain > 0 else 50.0
        else:
            rs = last_gain / last_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        # Candle anatomy for bar 0
        rng0 = max(h0 - l0, 1e-6)
        body0 = abs(c0 - o0)
        body_pct0 = body0 / rng0
        upper_wick0 = h0 - max(o0, c0)
        lower_wick0 = min(o0, c0) - l0
        upper_pct0 = upper_wick0 / rng0
        lower_pct0 = lower_wick0 / rng0
        is_green0 = c0 > o0
        is_red0 = c0 < o0

        # Candle anatomy for bar 1 & bar 2
        rng1 = max(h1 - l1, 1e-6)
        body1 = abs(c1 - o1)
        is_green1 = c1 > o1
        is_red1 = c1 < o1

        rng2 = max(h2 - l2, 1e-6)
        body2 = abs(c2 - o2)
        is_green2 = c2 > o2
        is_red2 = c2 < o2

        # Short-term trend context prior to current candle (5-bar move)
        lookback_idx = max(0, len(c) - 6)
        prior_move_pct = ((c1 - float(c.iloc[lookback_idx])) / max(1e-6, float(c.iloc[lookback_idx]))) * 100.0

        bullish_patterns: List[tuple[str, float]] = []
        bearish_patterns: List[tuple[str, float]] = []

        # 1. Bullish / Bearish Engulfing
        if is_red1 and is_green0 and c0 >= o1 and o0 <= c1 and body0 > body1 * 1.05 and rng0 >= atr * 0.55:
            score = 80.0 + (7.0 if rvol >= 1.2 else 0.0) + (5.0 if prior_move_pct < -0.15 else 0.0) + (4.0 if body_pct0 >= 0.70 else 0.0)
            bullish_patterns.append(("Bullish Engulfing", min(96.0, score)))

        if is_green1 and is_red0 and o0 >= c1 and c0 <= o1 and body0 > body1 * 1.05 and rng0 >= atr * 0.55:
            score = 80.0 + (7.0 if rvol >= 1.2 else 0.0) + (5.0 if prior_move_pct > 0.15 else 0.0) + (4.0 if body_pct0 >= 0.70 else 0.0)
            bearish_patterns.append(("Bearish Engulfing", min(96.0, score)))

        # 2. Hammer & Dragonfly Doji (Bullish Rejection Wick)
        if lower_wick0 >= max(2.0 * max(body0, rng0 * 0.05), rng0 * 0.55) and upper_pct0 <= 0.20 and rng0 >= atr * 0.45:
            if body_pct0 <= 0.08 and c0 >= o0:
                score = 72.0 + (6.0 if prior_move_pct < -0.1 else 0.0) + (5.0 if rvol >= 1.1 else 0.0)
                bullish_patterns.append(("Dragonfly Doji", min(90.0, score)))
            elif c0 >= l0 + rng0 * 0.60:
                score = 74.0 + (6.0 if is_green0 else 0.0) + (6.0 if prior_move_pct < -0.1 else 0.0) + (5.0 if rvol >= 1.1 else 0.0)
                bullish_patterns.append(("Hammer", min(92.0, score)))

        # 3. Shooting Star & Gravestone Doji (Bearish Rejection Wick)
        if upper_wick0 >= max(2.0 * max(body0, rng0 * 0.05), rng0 * 0.55) and lower_pct0 <= 0.20 and rng0 >= atr * 0.45:
            if body_pct0 <= 0.08 and c0 <= o0:
                score = 72.0 + (6.0 if prior_move_pct > 0.1 else 0.0) + (5.0 if rvol >= 1.1 else 0.0)
                bearish_patterns.append(("Gravestone Doji", min(90.0, score)))
            elif c0 <= h0 - rng0 * 0.60:
                score = 74.0 + (6.0 if is_red0 else 0.0) + (6.0 if prior_move_pct > 0.1 else 0.0) + (5.0 if rvol >= 1.1 else 0.0)
                bearish_patterns.append(("Shooting Star", min(92.0, score)))

        # 4. Bullish / Bearish Marubozu (Strong Momentum Candle)
        if is_green0 and body_pct0 >= 0.72 and rng0 >= atr * 0.85:
            score = 76.0 + (8.0 if rvol >= 1.25 else 0.0) + (4.0 if c0 > ema_fast else 0.0)
            bullish_patterns.append(("Bullish Marubozu", min(94.0, score)))

        if is_red0 and body_pct0 >= 0.72 and rng0 >= atr * 0.85:
            score = 76.0 + (8.0 if rvol >= 1.25 else 0.0) + (4.0 if c0 < ema_fast else 0.0)
            bearish_patterns.append(("Bearish Marubozu", min(94.0, score)))

        # 5. Morning Star & Evening Star (3-Candle Reversal)
        mid2 = (o2 + c2) / 2.0
        if is_red2 and (body2 / rng2) >= 0.45 and (body1 / rng1) <= 0.40 and is_green0 and c0 >= mid2 and c0 > o0:
            score = 84.0 + (6.0 if rvol >= 1.1 else 0.0)
            bullish_patterns.append(("Morning Star", min(96.0, score)))

        if is_green2 and (body2 / rng2) >= 0.45 and (body1 / rng1) <= 0.40 and is_red0 and c0 <= mid2 and c0 < o0:
            score = 84.0 + (6.0 if rvol >= 1.1 else 0.0)
            bearish_patterns.append(("Evening Star", min(96.0, score)))

        # 6. Piercing Line & Dark Cloud Cover
        if is_red1 and is_green0 and o0 < c1 and c0 > (o1 + c1) / 2.0 and c0 < o1 and (body1 / rng1) >= 0.45:
            bullish_patterns.append(("Piercing Line", 74.0 + (5.0 if rvol >= 1.15 else 0.0)))

        if is_green1 and is_red0 and o0 > c1 and c0 < (o1 + c1) / 2.0 and c0 > o1 and (body1 / rng1) >= 0.45:
            bearish_patterns.append(("Dark Cloud Cover", 74.0 + (5.0 if rvol >= 1.15 else 0.0)))

        # 7. Three White Soldiers & Three Black Crows (Trend Continuation)
        if (is_green2 and is_green1 and is_green0 and c0 > c1 > c2 and
                (body0 / rng0) >= 0.50 and (body1 / rng1) >= 0.50 and (body2 / rng2) >= 0.50):
            bullish_patterns.append(("Three White Soldiers", 82.0 + (5.0 if rvol >= 1.1 else 0.0)))

        if (is_red2 and is_red1 and is_red0 and c0 < c1 < c2 and
                (body0 / rng0) >= 0.50 and (body1 / rng1) >= 0.50 and (body2 / rng2) >= 0.50):
            bearish_patterns.append(("Three Black Crows", 82.0 + (5.0 if rvol >= 1.1 else 0.0)))

        bullish_patterns.sort(key=lambda x: x[1], reverse=True)
        bearish_patterns.sort(key=lambda x: x[1], reverse=True)

        top_bull = bullish_patterns[0] if bullish_patterns else None
        top_bear = bearish_patterns[0] if bearish_patterns else None

        if top_bull and (not top_bear or top_bull[1] >= top_bear[1]):
            bias = "BULLISH"
            primary_name, strength = top_bull
            all_names = [p[0] for p in bullish_patterns]
        elif top_bear:
            bias = "BEARISH"
            primary_name, strength = top_bear
            all_names = [p[0] for p in bearish_patterns]
        else:
            bias = "NEUTRAL"
            primary_name = "None"
            strength = 0.0
            all_names = []

        metrics = {
            "close": round(c0, 2),
            "body_pct": round(body_pct0 * 100.0, 1),
            "upper_wick_pct": round(upper_pct0 * 100.0, 1),
            "lower_wick_pct": round(lower_pct0 * 100.0, 1),
            "rvol": round(rvol, 2),
            "atr": round(atr, 2),
            "rsi": round(rsi, 1),
            "ema_9": round(ema_fast, 2),
            "ema_21": round(ema_slow, 2),
        }

        reason = (
            f"Candlestick [{primary_name}] ({bias}, Strength {strength:.0f}/100) | "
            f"RVOL={rvol:.2f}x, RSI={rsi:.1f}, EMA9/21={'Bullish' if ema_fast >= ema_slow else 'Bearish'}"
            if primary_name != "None"
            else f"No dominant candlestick pattern (RSI={rsi:.1f}, RVOL={rvol:.2f}x)"
        )

        return {
            "pattern": primary_name,
            "patterns_detected": all_names,
            "bias": bias,
            "strength": round(strength, 1),
            "candle_metrics": metrics,
            "reason": reason,
        }
