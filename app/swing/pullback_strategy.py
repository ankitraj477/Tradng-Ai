"""
Swing Pullback Strategy.
Generates structured swing trade proposals with 2:1 to 3:1 Risk-to-Reward,
designed for 3-day to 20-day holding periods.
"""

class SwingPullbackStrategy:
    def __init__(self, provider=None, cfg=None):
        self.provider = provider
        self.cfg = cfg or {}

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

    def propose(self, candidate: dict, market_regime: str = "Bullish") -> dict | None:
        """
        Convert a swing candidate into an executable trade proposal.
        """
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
