"""
Intraday VWAP Pullback & Mean-Reversion Strategy.
Active primarily during midday range-bound or moderate trend regimes (11:30 - 14:00 IST).
Trades high-probability tests of the Volume-Weighted Average Price with confirmation.
"""
from typing import Dict, Any, Optional
import pandas as pd
from ..strategy_interface import BaseDeskStrategy
from .timing import IntradayTimingManager
from .vwap import calculate_session_vwap


class VWAPPullbackStrategy(BaseDeskStrategy):
    """
    Intraday VWAP Pullback Strategy.
    - Triggers when price pulls back to test session VWAP within 0.25% tolerance.
    - Requires rejection confirmation (wick bounce off VWAP).
    - Avoids early opening volatility (activates post-10:30 IST) and ends before square-off.
    """
    def __init__(self, atr_stop_mult: float = 1.2, target_mult: float = 3.0):
        super().__init__(
            name="Intraday VWAP Pullback",
            desk="INTRADAY",
            supported_regimes=["Consolidation", "Moderate Trend", "Mean Reversion", "Range Bound"]
        )
        self.atr_stop_mult = atr_stop_mult
        self.target_mult = target_mult
        self.timing = IntradayTimingManager()

    def evaluate_market_fitness(self, context: Dict[str, Any]) -> float:
        """
        VWAP pullbacks excel in stable or range-bound markets (ADX 15-28).
        In extreme gap-and-go momentum or extreme market chaos, fitness is reduced.
        """
        regime = str(context.get("regime", "")).lower()
        adx = float(context.get("adx", 20.0))

        fitness = 0.65

        if "range" in regime or "consolidation" in regime or "pullback" in regime:
            fitness += 0.25
        elif "panic" in regime or "volatile" in regime:
            fitness -= 0.30

        if 15.0 <= adx <= 28.0:
            fitness += 0.15
        elif adx > 35.0:
            fitness -= 0.15

        return max(0.05, min(1.0, fitness))

    def propose(self, target: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        context = context or {}
        intraday_df = context.get("intraday_df")
        if intraday_df is None or len(intraday_df) < 15:
            return None

        current_time = intraday_df.index[-1]
        # Must be within trading hours and before 14:45 cutoff
        if not self.timing.can_enter(current_time, allow_midday=True):
            return None

        # Calculate session VWAP
        vwap_df = calculate_session_vwap(intraday_df)
        if vwap_df.empty or "vwap" not in vwap_df.columns:
            return None

        current_bar = intraday_df.iloc[-1]
        close = float(current_bar["Close"])
        high = float(current_bar["High"])
        low = float(current_bar["Low"])
        vwap = float(vwap_df["vwap"].iloc[-1])

        # ATR calculation
        h, l, c = intraday_df["High"], intraday_df["Low"], intraday_df["Close"]
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(close * 0.005)

        # Tolerance band for VWAP touch: 0.3% of price or 0.5x ATR
        tolerance = max(close * 0.003, 0.5 * atr)

        # Bullish VWAP Bounce: Low touched VWAP, Close finished above VWAP
        if (low <= vwap + tolerance) and (close > vwap) and (close >= low + (high - low) * 0.5):
            stop_dist = max(close * 0.008, self.atr_stop_mult * atr)
            stop_px = min(low - stop_dist, vwap - stop_dist)
            risk = max(close - stop_px, close * 0.008)
            target_px = max(close + (self.target_mult * risk), round(close * 1.025, 2))

            rr = round(abs(target_px - close) / max(0.01, abs(close - stop_px)), 2)
            return {
                "symbol": target,
                "action": "BUY",
                "side": "LONG",
                "price": close,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "risk_reward": rr,
                "atr": round(atr, 2),
                "vwap": round(vwap, 2),
                "strategy": self.name,
                "confidence": 75.0,
                "product_type": "INTRADAY",
                "reason": f"Bullish VWAP bounce at {vwap:.2f} (Low: {low:.2f}, Close: {close:.2f}, RR {rr}:1)"
            }

        # Bearish VWAP Rejection: High touched VWAP, Close finished below VWAP
        elif (high >= vwap - tolerance) and (close < vwap) and (close <= high - (high - low) * 0.5):
            stop_dist = max(close * 0.008, self.atr_stop_mult * atr)
            stop_px = max(high + stop_dist, vwap + stop_dist)
            risk = max(stop_px - close, close * 0.008)
            target_px = min(close - (self.target_mult * risk), round(close * 0.975, 2))

            rr = round(abs(close - target_px) / max(0.01, abs(stop_px - close)), 2)
            return {
                "symbol": target,
                "action": "SHORT",
                "side": "SHORT",
                "price": close,
                "stop_loss": round(stop_px, 2),
                "target": round(target_px, 2),
                "risk_reward": rr,
                "atr": round(atr, 2),
                "vwap": round(vwap, 2),
                "strategy": self.name,
                "confidence": 75.0,
                "product_type": "INTRADAY",
                "reason": f"Bearish VWAP rejection at {vwap:.2f} (High: {high:.2f}, Close: {close:.2f}, RR {rr}:1)"
            }

        return None

