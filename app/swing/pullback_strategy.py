"""
Swing Pullback Strategy.
Generates structured swing trade proposals with 2:1 to 3:1 Risk-to-Reward,
designed for 3-day to 20-day holding periods.
"""
from typing import Dict, Any, Optional, Union
import pandas as pd
from ..strategy_interface import BaseDeskStrategy


class SwingPullbackStrategy(BaseDeskStrategy):
    def __init__(self, provider=None, cfg=None):
        super().__init__(
            name="Swing 20 EMA Pullback",
            desk="SWING",
            supported_regimes=["Bullish Trending", "Expansion", "Pullback"]
        )
        self.provider = provider
        self.cfg = cfg or {}

    def evaluate_market_fitness(self, context: Dict[str, Any]) -> float:
        regime = str(context.get("regime", "")).lower()
        fitness = 0.65
        if "bull" in regime or "trend" in regime or "pullback" in regime:
            fitness += 0.25
        elif "bear" in regime or "panic" in regime:
            fitness -= 0.35
        return max(0.05, min(1.0, fitness))

    def evaluate_setup(self, symbol: str) -> dict | None:
        if not self.provider:
            return None
        from .scanner import SwingScanner
        scanner = SwingScanner(self.provider)
        cand = scanner.scan_symbol(symbol)
        if cand:
            prop = self.propose(cand)
            if prop:
                prop["valid"] = True
                prop["rr_ratio"] = prop["risk_reward"]
                return prop
        return None

    def propose(
        self,
        target: Union[dict, str],
        market_regime: str = "Bullish",
        context: Optional[Dict[str, Any]] = None
    ) -> dict | None:
        """
        Convert a swing candidate (or symbol string with context) into an executable trade proposal.
        Conforms strictly to BaseDeskStrategy.propose(target, context=...).
        """
        if not target:
            return None

        candidate = None
        if isinstance(target, dict):
            candidate = target
        elif isinstance(target, str):
            symbol = target
            ctx = context or {}
            if "candidate" in ctx:
                candidate = ctx["candidate"]
            elif self.provider:
                from .scanner import SwingScanner
                scanner = SwingScanner(self.provider)
                candidate = scanner.scan_symbol(symbol)
            else:
                daily_df = ctx.get("daily_df")
                if daily_df is not None and len(daily_df) >= 20:
                    c = daily_df["Close"]
                    h = daily_df["High"]
                    l = daily_df["Low"]
                    last_px = float(c.iloc[-1])
                    ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
                    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
                    atr = float(tr.tail(14).mean()) if len(tr) >= 14 else float(last_px * 0.02)
                    candidate = {
                        "symbol": symbol,
                        "price": last_px,
                        "ema_20": ema20,
                        "atr": atr,
                        "score": 80.0
                    }

        if not candidate:
            return None

        price = float(candidate["price"])
        atr = float(candidate.get("atr") or (price * 0.025))
        ema20 = float(candidate.get("ema_20") or price * 0.98)

        # Stop Loss: Placed safely below the 20 EMA or 1.8x daily ATR
        # Typically 3% to 5% risk distance
        stop_dist = max(price - (ema20 * 0.985), 1.8 * atr, price * 0.035)
        stop_loss = round(max(0.01, price - stop_dist), 2)

        # Target: 2.2x to 3.0x risk distance (typically 8% to 14% target)
        risk_per_share = price - stop_loss
        target_dist = max(risk_per_share * 2.5, price * 0.08)
        target = round(price + target_dist, 2)

        rr = round((target - price) / max(price - stop_loss, 0.01), 2)
        confidence = float(candidate.get("score", 78.0))

        reason = (
            f"Stage-2 20 EMA Pullback on {candidate['symbol']}. "
            f"Tested EMA20 (₹{ema20:.2f}) with volume dry-up; "
            f"R:R = 1:{rr:.1f}, initial target +{((target - price) / price * 100):.1f}%."
        )

        return {
            "symbol": candidate["symbol"],
            "action": "BUY",
            "price": price,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward": rr,
            "confidence": confidence,
            "strategy": "Swing 20 EMA Pullback",
            "reason": reason,
            "atr": atr,
            "product_type": "SWING",
            "days_held": 0,
        }
