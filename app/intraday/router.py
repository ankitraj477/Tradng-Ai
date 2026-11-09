"""
Intraday Multi-Strategy Router & Dispatcher.
Orchestrates Opening Range Breakout (ORB), VWAP Bounce/Rejection,
20-Candle Momentum Breakouts, and Afternoon RSI-2 Mean-Reversion.
"""
from typing import Dict, Any, Optional, List
from types import SimpleNamespace
import pandas as pd
import numpy as np

from .timing import IntradayTimingManager
from .orb_strategy import OpeningRangeBreakoutStrategy
from .vwap_pullback import VWAPPullbackStrategy
from ..multitimeframe import MultiTimeframeAnalyzer
from .vwap import calculate_session_vwap


class IntradayMomentumBreakoutStrategy:
    """
    Intraday 20-Candle Momentum Breakout.
    Active throughout market hours (09:30 - 14:45 IST).
    Captures trend continuation when price breaks 20-period 5m highs with RVOL >= 1.2x.
    """
    def __init__(self, target_mult: float = 3.0, atr_stop_mult: float = 1.3):
        self.name = "Intraday Momentum Breakout"
        self.target_mult = target_mult
        self.atr_stop_mult = atr_stop_mult
        self.timing = IntradayTimingManager()

    def evaluate(self, symbol: str, intraday_df: pd.DataFrame, daily_bias: str = "NEUTRAL") -> Optional[Dict[str, Any]]:
        if intraday_df is None or len(intraday_df) < 25:
            return None

        current_time = intraday_df.index[-1]
        if not self.timing.can_enter(current_time, allow_midday=True):
            return None

        h, l, c, v = intraday_df["High"], intraday_df["Low"], intraday_df["Close"], intraday_df["Volume"]
        current_bar = intraday_df.iloc[-1]
        close = float(current_bar["Close"])
        high = float(current_bar["High"])
        low = float(current_bar["Low"])

        # 20-period lookback (excluding current bar)
        prior_high_20 = float(h.iloc[-21:-1].max())
        prior_low_20 = float(l.iloc[-21:-1].min())
        avg_vol_20 = float(v.iloc[-21:-1].mean()) or 1.0
        cur_vol = float(current_bar["Volume"])
        rvol = cur_vol / avg_vol_20

        # ATR calculation
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(close * 0.005)

        # VWAP
        vwap_df = calculate_session_vwap(intraday_df)
        vwap = float(vwap_df["vwap"].iloc[-1]) if not vwap_df.empty and "vwap" in vwap_df.columns else close

        # Bullish Breakout: 20-candle high break, Close > VWAP, RVOL >= 1.2, not bearish daily bias
        if close > prior_high_20 and close > vwap and rvol >= 1.15 and daily_bias != "BEARISH":
            stop_dist = max(close * 0.008, self.atr_stop_mult * atr)
            stop_px = min(prior_low_20, close - stop_dist)
            risk = max(close - stop_px, close * 0.008)
            target_px = max(close + (self.target_mult * risk), round(close * 1.025, 2))
            rr = round(abs(target_px - close) / max(0.01, abs(close - stop_px)), 2)

            return {
                "symbol": symbol,
                "action": "BUY",
                "side": "LONG",
                "price": close,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "risk_reward": rr,
                "atr": round(atr, 2),
                "vwap": round(vwap, 2),
                "confidence": min(90.0, 72.0 + (rvol * 5.0)),
                "strategy": self.name,
                "reason": f"20-candle high breakout above {prior_high_20:.2f} with {rvol:.1f}x RVOL & VWAP support (RR {rr}:1)"
            }

        # Bearish Breakdown: 20-candle low break, Close < VWAP, RVOL >= 1.2, not bullish daily bias
        elif close < prior_low_20 and close < vwap and rvol >= 1.15 and daily_bias != "BULLISH":
            stop_dist = max(close * 0.008, self.atr_stop_mult * atr)
            stop_px = max(prior_high_20, close + stop_dist)
            risk = max(stop_px - close, close * 0.008)
            target_px = min(close - (self.target_mult * risk), round(close * 0.975, 2))
            rr = round(abs(close - target_px) / max(0.01, abs(stop_px - close)), 2)

            return {
                "symbol": symbol,
                "action": "SHORT",
                "side": "SHORT",
                "price": close,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "risk_reward": rr,
                "atr": round(atr, 2),
                "vwap": round(vwap, 2),
                "confidence": min(90.0, 72.0 + (rvol * 5.0)),
                "strategy": self.name,
                "reason": f"20-candle low breakdown below {prior_low_20:.2f} with {rvol:.1f}x RVOL & VWAP resistance (RR {rr}:1)"
            }

        return None


class IntradayMeanReversionStrategy:
    """
    Intraday RSI-2 Pullback Strategy.
    Active particularly during afternoon sessions (12:00 - 15:00 IST).
    Buys temporary exhaustion pullbacks (RSI2 < 18) in established intraday uptrends (> 50 EMA).
    """
    def __init__(self, target_mult: float = 2.5, atr_stop_mult: float = 1.2):
        self.name = "Intraday RSI-2 Mean Reversion"
        self.target_mult = target_mult
        self.atr_stop_mult = atr_stop_mult
        self.timing = IntradayTimingManager()

    def evaluate(self, symbol: str, intraday_df: pd.DataFrame, daily_bias: str = "NEUTRAL") -> Optional[Dict[str, Any]]:
        if intraday_df is None or len(intraday_df) < 55:
            return None

        current_time = intraday_df.index[-1]
        if not self.timing.can_enter(current_time, allow_midday=True):
            return None

        c = intraday_df["Close"]
        h = intraday_df["High"]
        l = intraday_df["Low"]
        close = float(c.iloc[-1])

        # Trend filter: 50 EMA on 5m chart
        ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1])

        # 2-period RSI calculation
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(2).mean()
        loss = (-delta.clip(upper=0)).rolling(2).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi2_series = 100.0 - (100.0 / (1.0 + rs))
        rsi2 = float(rsi2_series.iloc[-1]) if not pd.isna(rsi2_series.iloc[-1]) else 50.0

        # ATR calculation
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(close * 0.005)

        # Bullish Pullback: Price > 50 EMA, RSI(2) < 18, Daily bias not bearish
        if close > ema50 and rsi2 <= 18.0 and daily_bias != "BEARISH":
            stop_dist = max(close * 0.008, self.atr_stop_mult * atr)
            stop_px = min(float(l.tail(5).min()), close - stop_dist)
            risk = max(close - stop_px, close * 0.008)
            target_px = max(close + (self.target_mult * risk), round(close * 1.020, 2))
            rr = round(abs(target_px - close) / max(0.01, abs(close - stop_px)), 2)

            return {
                "symbol": symbol,
                "action": "BUY",
                "side": "LONG",
                "price": close,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "risk_reward": rr,
                "atr": round(atr, 2),
                "rsi2": round(rsi2, 1),
                "confidence": 76.0,
                "strategy": self.name,
                "reason": f"RSI-2 oversold bounce ({rsi2:.1f} <= 18) above 50-EMA ({ema50:.2f}) (RR {rr}:1)"
            }

        return None


class IntradayMultiStrategyRouter:
    """
    Multi-Strategy Dispatcher for Intraday Desk.
    Evaluates:
      1. Opening Range Breakout (ORB)
      2. Session VWAP Bounce / Rejection
      3. 20-Candle Momentum Breakout
      4. Afternoon RSI-2 Mean Reversion
    Selects the setup with highest conviction and returns SimpleNamespace.
    """
    def __init__(self, provider, cfg=None):
        self.provider = provider
        self.cfg = cfg or {}
        self.orb_strat = OpeningRangeBreakoutStrategy()
        self.vwap_strat = VWAPPullbackStrategy()
        self.breakout_strat = IntradayMomentumBreakoutStrategy()
        self.meanrev_strat = IntradayMeanReversionStrategy()

    def evaluate(self, symbol: str, market_regime: str = None) -> Optional[SimpleNamespace]:
        try:
            intraday_df = self.provider.history(symbol, period="5d", interval="5m")
            if intraday_df is None or intraday_df.empty:
                return None

            daily_df = self.provider.history(symbol, period="60d", interval="1d")
            daily_bias = "NEUTRAL"
            if daily_df is not None and len(daily_df) >= 50:
                analysis = MultiTimeframeAnalyzer.daily_direction(daily_df)
                daily_bias = analysis.get("bias", "NEUTRAL")

            proposals: List[Dict[str, Any]] = []

            # 1. Opening Range Breakout
            orb_sig = self.orb_strat.decide(symbol, intraday_df, daily_df=daily_df)
            if orb_sig:
                orb_sig["confidence"] = orb_sig.get("confidence", 80.0)
                proposals.append(orb_sig)

            # 2. VWAP Pullback / Bounce
            vwap_sig = self.vwap_strat.propose(symbol, context={"intraday_df": intraday_df, "regime": market_regime})
            if vwap_sig:
                proposals.append(vwap_sig)

            # 3. 20-Candle Momentum Breakout
            mom_sig = self.breakout_strat.evaluate(symbol, intraday_df, daily_bias=daily_bias)
            if mom_sig:
                proposals.append(mom_sig)

            # 4. Afternoon RSI-2 Mean Reversion
            mr_sig = self.meanrev_strat.evaluate(symbol, intraday_df, daily_bias=daily_bias)
            if mr_sig:
                proposals.append(mr_sig)

            if not proposals:
                return None

            # Filter by market regime
            regime_lower = str(market_regime or "").lower()
            valid = []
            for p in proposals:
                if p["action"] == "SHORT" and not any(k in regime_lower for k in ("strong bearish", "bearish trend", "downtrend")):
                    continue
                if p["action"] == "BUY" and "strong bearish" in regime_lower:
                    continue
                valid.append(p)

            if not valid:
                return None

            # Rank by (confidence * risk_reward)
            valid.sort(key=lambda x: float(x.get("confidence", 70.0)) * float(x.get("risk_reward", 2.0)), reverse=True)
            best = valid[0]

            return SimpleNamespace(**best)

        except Exception:
            return None

