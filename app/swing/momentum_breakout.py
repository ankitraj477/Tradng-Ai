"""
Swing Desk Stage-2 Momentum Breakout Strategy.
Identifies high-relative-strength equities breaking out of consolidation / 20-day highs
with institutional volume expansion, designed for 3-15 day swing holding periods.
"""
from typing import Dict, Any, Optional
import pandas as pd
from ..strategy_interface import BaseDeskStrategy


class SwingMomentumBreakoutStrategy(BaseDeskStrategy):
    """
    Swing Momentum Breakout Strategy.
    - Focuses on stocks in established Stage-2 uptrends (Price > 50 SMA > 200 SMA).
    - Requires breakout above 20-day consolidation high on >= 1.5x average 20-day volume.
    - Sets initial trailing stop at breakout candle low or 2x ATR.
    """
    def __init__(self, breakout_lookback: int = 20, volume_mult: float = 1.3):
        super().__init__(
            name="Swing Momentum Breakout",
            desk="SWING",
            supported_regimes=["Bullish Trending", "Expansion", "Strong Trend", "Stage 2"]
        )
        self.lookback = breakout_lookback
        self.vol_mult = volume_mult

    def evaluate_market_fitness(self, context: Dict[str, Any]) -> float:
        regime = str(context.get("regime", "")).lower()
        adx = float(context.get("adx", 20.0))

        fitness = 0.50

        if "bull" in regime or "trend" in regime or "expansion" in regime:
            fitness += 0.35
        elif "bear" in regime or "panic" in regime:
            fitness -= 0.40

        if adx >= 24.0:
            fitness += 0.15
        elif adx < 18.0:
            fitness -= 0.15

        return max(0.05, min(1.0, fitness))

    def propose(self, target: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        context = context or {}
        daily_df = context.get("daily_df")
        if daily_df is None or len(daily_df) < max(self.lookback + 5, 50):
            return None

        df = daily_df.copy()
        c = df["Close"]
        h = df["High"]
        l = df["Low"]
        v = df["Volume"]

        latest_c = float(c.iloc[-1])
        latest_h = float(h.iloc[-1])
        latest_v = float(v.iloc[-1])

        # Prior 20-day resistance high (excluding current bar)
        prior_high = float(h.iloc[-(self.lookback + 1):-1].max())
        avg_vol = float(v.iloc[-(self.lookback + 1):-1].mean()) if len(v) >= self.lookback else 1.0

        # Trend filter: 50 SMA
        sma50 = float(c.rolling(50).mean().iloc[-1]) if len(c) >= 50 else latest_c

        # Breakout condition: Close > Prior 20-day High, Volume >= 1.3x 20-day average, Close > 50 SMA
        if latest_c > prior_high and latest_v >= (avg_vol * self.vol_mult) and latest_c > sma50:
            # ATR
            tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(latest_c * 0.015)

            stop_px = max(latest_c - (2.0 * atr), float(l.iloc[-1]))
            risk = latest_c - stop_px
            if risk <= 0: risk = latest_c * 0.015
            target_px = round(latest_c + (2.5 * risk), 2)

            return {
                "symbol": target,
                "action": "BUY",
                "side": "LONG",
                "price": latest_c,
                "stop_loss": round(stop_px, 2),
                "target": target_px,
                "atr": round(atr, 2),
                "strategy": self.name,
                "confidence": 85.0,
                "product_type": "CNC",
                "reason": f"Stage-2 Breakout above {self.lookback}-day high ({prior_high:.2f}) on {latest_v/avg_vol:.1f}x volume"
            }

        return None

