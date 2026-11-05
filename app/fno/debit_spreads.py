"""
Directional Option Debit Spreads Strategy for NIFTY and BANKNIFTY.
Executes Bull Call Spreads and Bear Put Spreads during high-momentum / trending regimes.
Complements theta decay strategies by capturing rapid directional expansion with capped risk.
"""
from typing import Dict, Any, Optional
from ..strategy_interface import BaseDeskStrategy
from .index_chain import IndexChainManager, LOT_SIZES
from .sr_levels import IndexSRCalculator


class DirectionalDebitSpreadStrategy(BaseDeskStrategy):
    """
    Directional Debit Spread Strategy (Bull Call & Bear Put).
    - Bull Call Spread: Buy ATM CE + Sell OTM CE (trending up).
    - Bear Put Spread: Buy ATM PE + Sell OTM PE (trending down).
    - Defined maximum loss = Net Premium Paid.
    - Captures directional moves with positive delta while capping volatility & theta risk.
    """
    def __init__(self, chain_manager=None, cfg=None):
        super().__init__(
            name="Directional Debit Spreads",
            desk="FNO",
            supported_regimes=["Bullish Trending", "Bearish Trending", "Breakout", "Momentum"]
        )
        self.chain = chain_manager or IndexChainManager()
        self.cfg = cfg or {}
        self.sr_calc = IndexSRCalculator(provider=getattr(self.chain, "provider", None))

    def evaluate_market_fitness(self, context: Dict[str, Any]) -> float:
        """
        Debit spreads require strong directional conviction and momentum (ADX >= 22).
        In range-bound or low ADX regimes, fitness drops sharply.
        """
        regime = str(context.get("regime", "")).lower()
        adx = float(context.get("adx", 20.0))
        pcr = float(context.get("pcr", 1.0))

        fitness = 0.50

        # Strong trending momentum favours directional debit spreads
        if "trending" in regime or "breakout" in regime or "momentum" in regime:
            fitness += 0.30
        elif "range" in regime or "consolidation" in regime:
            fitness -= 0.30

        if adx >= 25.0:
            fitness += 0.20
        elif adx < 18.0:
            fitness -= 0.20

        # Strong directional sentiment
        if pcr > 1.30 or pcr < 0.70:
            fitness += 0.15

        return max(0.05, min(1.0, fitness))

    def propose(self, target: str = "NIFTY", context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        context = context or {}
        index_name = target.upper()
        regime = str(context.get("regime", "")).lower()
        pcr = float(context.get("pcr") or self.chain.estimate_pcr(index_name))
        spot = float(context.get("spot") or self.chain.get_spot_price(index_name))

        if spot <= 0.0:
            return None

        atm = self.chain.round_strike(spot, index_name)
        expiry = self.chain.get_next_expiry()
        lot_size = LOT_SIZES.get(index_name, 25)

        # Dynamic S/R check
        sr = self.sr_calc.calculate_levels(index_name, spot)
        structure = sr.get("structure", "RANGE_BOUND")

        wing_width = 150 if index_name == "NIFTY" else 300

        # Determine directional bias with explicit regime precedence
        is_bullish = ("bull" in regime) or (structure == "BULLISH_BREAKOUT" and "bear" not in regime) or (pcr > 1.25 and "bear" not in regime)
        is_bearish = ("bear" in regime) or (structure == "BEARISH_BREAKDOWN" and "bull" not in regime) or (pcr < 0.75 and "bull" not in regime)

        if is_bullish and not is_bearish:
            # Bull Call Spread: Buy ATM Call, Sell OTM Call
            long_call = atm
            short_call = atm + wing_width
            est_debit = 40.0 if index_name == "NIFTY" else 95.0
            max_profit = wing_width - est_debit

            legs = [
                {"action": "BUY", "type": "CE", "strike": long_call, "qty": lot_size, "name": f"{index_name} {long_call} CE"},
                {"action": "SELL", "type": "CE", "strike": short_call, "qty": lot_size, "name": f"{index_name} {short_call} CE (Hedge)"},
            ]
            symbol = f"{index_name}-{expiry}-BCALL-{long_call}C/{short_call}C"
            reason = f"Bullish momentum (Spot: {spot:.1f}, S1: {sr['support_1']:.1f}). Bought {long_call} CE / Sold {short_call} CE debit spread."

            return {
                "symbol": symbol,
                "underlying": index_name,
                "strategy": f"{index_name} Bull Call Spread",
                "action": "BUY",
                "price": est_debit,
                "legs": legs,
                "qty": lot_size,
                "confidence": 80.0,
                "stop_loss": round(est_debit * 0.50, 2),  # Exit if spread loses 50%
                "target": round(est_debit + max_profit * 0.60, 2),  # Target 60% of max potential profit
                "credit": -est_debit,  # Net debit
                "debit": est_debit,
                "max_profit": max_profit,
                "max_loss": est_debit,
                "expiry": expiry,
                "spot": spot,
                "strikes": {"long_call": long_call, "short_call": short_call},
                "pcr": pcr,
                "sr_levels": sr,
                "reason": reason,
                "product_type": "FNO",
                "spread_type": "DEBIT",
                "asset_type": "FNO"
            }

        elif is_bearish and not is_bullish:
            # Bear Put Spread: Buy ATM Put, Sell OTM Put
            long_put = atm
            short_put = atm - wing_width
            est_debit = 40.0 if index_name == "NIFTY" else 95.0
            max_profit = wing_width - est_debit

            legs = [
                {"action": "BUY", "type": "PE", "strike": long_put, "qty": lot_size, "name": f"{index_name} {long_put} PE"},
                {"action": "SELL", "type": "PE", "strike": short_put, "qty": lot_size, "name": f"{index_name} {short_put} PE (Hedge)"},
            ]
            symbol = f"{index_name}-{expiry}-BPUT-{long_put}P/{short_put}P"
            reason = f"Bearish momentum (Spot: {spot:.1f}, R1: {sr['resistance_1']:.1f}). Bought {long_put} PE / Sold {short_put} PE debit spread."

            return {
                "symbol": symbol,
                "underlying": index_name,
                "strategy": f"{index_name} Bear Put Spread",
                "action": "BUY",
                "price": est_debit,
                "legs": legs,
                "qty": lot_size,
                "confidence": 80.0,
                "stop_loss": round(est_debit * 0.50, 2),
                "target": round(est_debit + max_profit * 0.60, 2),
                "credit": -est_debit,
                "debit": est_debit,
                "max_profit": max_profit,
                "max_loss": est_debit,
                "expiry": expiry,
                "spot": spot,
                "strikes": {"long_put": long_put, "short_put": short_put},
                "pcr": pcr,
                "sr_levels": sr,
                "reason": reason,
                "product_type": "FNO",
                "spread_type": "DEBIT",
                "asset_type": "FNO"
            }

        return None

