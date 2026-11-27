"""
Directional Call (CE) & Put (PE) Option Buying Strategy for NIFTY and BANKNIFTY.
Combines institutional Candlestick Pattern Analysis, VWAP/EMA momentum,
and dynamic Support/Resistance levels to capture asymmetric directional breakouts
and S/R reversals with wide ATR-based option stops and large R:R targets.
"""
import json
from typing import Dict, Any, Optional
import pandas as pd
from ..strategy_interface import BaseDeskStrategy
from ..candlestick_patterns import CandlestickAnalyzer
from ..intraday.vwap import calculate_session_vwap
from .index_chain import IndexChainManager, LOT_SIZES
from .sr_levels import IndexSRCalculator


class OptionBuyingStrategy(BaseDeskStrategy):
    """
    Institutional Directional Option Buying Strategy (Buy Call CE / Buy Put PE).
    - Uses Candlestick Patterns (Engulfing, Hammer, Shooting Star, Marubozu, Morning/Evening Star)
      paired with dynamic Support/Resistance (S1/R1/Pivot), EMA9/EMA21, RSI, and VWAP.
    - Selects ATM or near-ATM liquid weekly strikes for optimal delta expansion (0.50-0.55 delta).
    - Enforces wide stop loss (-28% on option premium) and large profit target (+65% on option premium)
      to prevent tick noise stop-outs while compounding asymmetric gains.
    """

    def __init__(self, chain_manager=None, cfg=None):
        super().__init__(
            name="Candlestick Option Buying (CE/PE)",
            desk="FNO",
            supported_regimes=[
                "Bullish Trending", "Bearish Trending", "Breakout", "Momentum",
                "Weak bullish", "Weak bearish", "Neutral", "Volatile",
            ],
        )
        self.chain = chain_manager or IndexChainManager()
        self.cfg = cfg or {}
        self.sr_calc = IndexSRCalculator(provider=getattr(self.chain, "provider", None))

    def evaluate_market_fitness(self, context: Dict[str, Any]) -> float:
        """
        Option buying thrives when directional conviction, candlestick clarity,
        or breakout momentum (ADX >= 20) is present.
        """
        regime = str(context.get("regime", "")).lower()
        adx = float(context.get("adx", 22.0))
        pattern_strength = float(context.get("pattern_strength", 0.0))

        fitness = 0.60
        if any(k in regime for k in ("trend", "breakout", "momentum", "bull", "bear")):
            fitness += 0.20
        elif "consolidation" in regime or "range" in regime:
            fitness -= 0.15

        if adx >= 22.0:
            fitness += 0.15
        if pattern_strength >= 70.0:
            fitness += 0.15

        return max(0.10, min(1.0, fitness))

    def _fetch_index_bars(self, index_name: str) -> Optional[pd.DataFrame]:
        provider = getattr(self.chain, "provider", None)
        if not provider or not hasattr(provider, "history"):
            return None
        sym = "^NSEI" if index_name.upper() == "NIFTY" else "^NSEBANK"
        for period, interval in (("5d", "5m"), ("1mo", "15m"), ("3mo", "1d")):
            try:
                df = provider.history(sym, period=period, interval=interval)
                if df is not None and len(df) >= 10:
                    return df
            except TypeError:
                try:
                    df = provider.history(sym, period)
                    if df is not None and len(df) >= 10:
                        return df
                except Exception:
                    continue
            except Exception:
                continue
        return None

    @staticmethod
    def _estimate_atm_option_premium(index_name: str, spot: float, atr_val: float, is_weekly_early: bool = True) -> float:
        """
        Estimate realistic liquid ATM / 1-OTM-edge option premium scaled for 10k+ accounts
        based on index price and volatility (ATR%).
        """
        vol_pct = (atr_val / spot) if spot > 0 else 0.004
        if index_name.upper() == "NIFTY":
            base = 58.0 + min(30.0, max(0.0, (vol_pct - 0.002) * 3500.0))
            return round(min(90.0, max(45.0, base)), 2)
        else:
            base = 115.0 + min(45.0, max(0.0, (vol_pct - 0.002) * 5500.0))
            return round(min(175.0, max(85.0, base)), 2)

    def propose(
        self,
        target: str = "NIFTY",
        market_regime: str = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze index candlestick structure, S/R boundaries, and momentum to propose
        a high-conviction Call (CE) or Put (PE) option buy.
        """
        context = context or {}
        index_name = target.upper()
        regime = str(market_regime or context.get("regime") or "Neutral")
        regime_lower = regime.lower()

        spot = float(context.get("spot") or self.chain.get_spot_price(index_name) or 0.0)
        if spot <= 0.0:
            return None

        bars = context.get("bars")
        if bars is None:
            bars = self._fetch_index_bars(index_name)
        if bars is None or len(bars) < 5:
            return None

        candle = CandlestickAnalyzer.analyze(bars, min_bars=5)
        pattern = candle["pattern"]
        bias = candle["bias"]
        strength = float(candle["strength"])
        metrics = candle["candle_metrics"]

        sr = self.sr_calc.calculate_levels(index_name, spot)
        s1 = float(sr.get("support_1", spot * 0.992))
        r1 = float(sr.get("resistance_1", spot * 1.008))
        pivot = float(sr.get("pivot", spot))
        structure = sr.get("structure", "CONSOLIDATION_BOX")

        # VWAP confirmation if intraday Volume exists
        vwap_val = spot
        try:
            vwap_df = calculate_session_vwap(bars)
            if vwap_df is not None and not vwap_df.empty and "vwap" in vwap_df.columns:
                vwap_val = float(vwap_df["vwap"].iloc[-1])
        except Exception:
            vwap_val = spot

        ema_fast = float(metrics.get("ema_9", spot))
        ema_slow = float(metrics.get("ema_21", spot))
        rsi = float(metrics.get("rsi", 50.0))
        atr_val = float(metrics.get("atr", spot * 0.004))

        # Check secondary momentum breakout even if classic named pattern didn't trigger
        body_pct = float(metrics.get("body_pct", 0.0))
        rvol = float(metrics.get("rvol", 1.0))
        momentum_bull = (
            bias == "NEUTRAL"
            and spot > pivot
            and spot > vwap_val
            and ema_fast > ema_slow
            and 52.0 <= rsi <= 75.0
            and body_pct >= 50.0
            and structure == "BULLISH_BREAKOUT"
        )
        momentum_bear = (
            bias == "NEUTRAL"
            and spot < pivot
            and spot < vwap_val
            and ema_fast < ema_slow
            and 25.0 <= rsi <= 48.0
            and body_pct >= 50.0
            and structure == "BEARISH_BREAKDOWN"
        )

        option_type = None
        setup_label = ""
        confidence = strength

        # Bullish Call (CE) Entry Qualification (strict trend + RSI confirmation to avoid falling-knife traps)
        if bias == "BULLISH" and strength >= 74.0:
            near_support = abs(spot - s1) / spot <= 0.004 or abs(spot - pivot) / spot <= 0.003
            trend_aligned = (ema_fast >= ema_slow) or (spot >= vwap_val and spot >= pivot) or (structure == "BULLISH_BREAKOUT")
            strong_reversal = near_support and strength >= 84.0 and rvol >= 1.25
            regime_ok = ("strong bear" not in regime_lower) or strong_reversal
            if regime_ok and (trend_aligned or strong_reversal) and 42.0 <= rsi <= 76.0:
                option_type = "CE"
                setup_label = f"Candlestick {pattern}"

        elif momentum_bull and "strong bear" not in regime_lower:
            option_type = "CE"
            pattern = "R1 Momentum Breakout"
            setup_label = "S/R Breakout + EMA9/VWAP"
            confidence = 78.0

        # Bearish Put (PE) Entry Qualification (strict trend + RSI confirmation)
        elif bias == "BEARISH" and strength >= 74.0:
            near_resistance = abs(spot - r1) / spot <= 0.004 or abs(spot - pivot) / spot <= 0.003
            trend_aligned = (ema_fast <= ema_slow) or (spot <= vwap_val and spot <= pivot) or (structure == "BEARISH_BREAKDOWN")
            strong_reversal = near_resistance and strength >= 84.0 and rvol >= 1.25
            regime_ok = ("strong bull" not in regime_lower) or strong_reversal
            if regime_ok and (trend_aligned or strong_reversal) and 24.0 <= rsi <= 58.0:
                option_type = "PE"
                setup_label = f"Candlestick {pattern}"

        elif momentum_bear and "strong bull" not in regime_lower:
            option_type = "PE"
            pattern = "S1 Momentum Breakdown"
            setup_label = "S/R Breakdown + EMA9/VWAP"
            confidence = 78.0

        if not option_type:
            return None

        atm = self.chain.round_strike(spot, index_name)
        expiry = self.chain.get_next_expiry()
        lot_size = LOT_SIZES.get(index_name, 25)

        # Select ATM strike for optimal ~0.52 delta responsiveness without OTM decay trap
        strike = atm
        est_premium = self._estimate_atm_option_premium(index_name, spot, atr_val)

        fno_cfg = self.cfg.get("fno", {})
        sl_ratio = float(fno_cfg.get("option_buy_sl_ratio", 0.72))      # -28% wide stop
        tp_ratio = float(fno_cfg.get("option_buy_target_ratio", 1.65))  # +65% asymmetric target

        stop_loss = round(max(1.0, est_premium * sl_ratio), 2)
        target_px = round(est_premium * tp_ratio, 2)
        total_cost = round(est_premium * lot_size, 2)

        legs = [
            {
                "action": "BUY",
                "type": option_type,
                "strike": strike,
                "qty": lot_size,
                "name": f"{index_name} {strike} {option_type}",
            }
        ]
        symbol = f"{index_name}-{expiry}-{strike}{option_type}"
        direction_word = "Call" if option_type == "CE" else "Put"
        strategy_name = f"{index_name} Long {direction_word} ({pattern})"

        reason = (
            f"{setup_label} on {index_name} (Spot: ₹{spot:.1f}, Pivot: ₹{pivot:.1f}, S1: ₹{s1:.1f}, R1: ₹{r1:.1f}). "
            f"RSI={rsi:.1f}, RVOL={rvol:.2f}x. Bought {strike} {option_type} @ ₹{est_premium:.2f} "
            f"(Cost: ₹{total_cost:.2f}, Target: ₹{target_px:.2f} [+65%], SL: ₹{stop_loss:.2f} [-28%])."
        )

        return {
            "symbol": symbol,
            "underlying": index_name,
            "action": "BUY",
            "side": "LONG",
            "price": est_premium,
            "current_price": est_premium,
            "stop_loss": stop_loss,
            "target": target_px,
            "margin_required": total_cost,
            "max_loss": round((est_premium - stop_loss) * lot_size, 2),
            "lot_size": lot_size,
            "strategy": strategy_name,
            "confidence": round(confidence, 1),
            "reason": reason,
            "product_type": "FNO",
            "expiry_date": expiry,
            "strike_price": float(strike),
            "option_type": option_type,
            "legs_info": json.dumps(legs),
            "legs": legs,
            "pattern": pattern,
            "pattern_bias": bias,
            "pattern_strength": confidence,
            "spot": spot,
            "sr_levels": sr,
        }
