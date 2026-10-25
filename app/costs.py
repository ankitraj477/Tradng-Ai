"""
Unified institutional cost and market-impact model for NSE.
Enforces Section 2 & Section 10 (Test 2) requirements:
- Delivery STT: 0.1% both sides (1,00,000 INR buy -> 100 INR STT).
- Intraday STT: 0.025% sell side only.
- Options STT: 0.15% of premium on sell side (from 2026-04-01; 0.1% before).
- Futures STT: 0.05% of turnover on sell side (from 2026-04-01; 0.02% before).
- Brokerage, exchange transaction fee, SEBI fee, GST (18%), stamp duty, DP charges.
- Dynamic market impact slippage based on ADTV.
"""

import math
from datetime import date, datetime
from typing import Optional, Union, Dict, Any


class CostModel:
    """Unified cost and market impact model loading statutory rates from strategy config."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, strategy_cfg=None):
        self.strategy_cfg = strategy_cfg
        # If strategy_cfg is None but cfg has costs, or load default strategy config
        if self.strategy_cfg is None:
            try:
                from .strategy_config import load_strategy_config
                self.strategy_cfg = load_strategy_config()
            except Exception:
                self.strategy_cfg = None

        if self.strategy_cfg is not None:
            raw_costs = self.strategy_cfg.raw.get("costs", {})
            self.brokerage_pct = float(raw_costs.get("brokerage", 0.0))
            self.brokerage_flat = 0.0
            self.exchange_pct = float(raw_costs.get("exchange_txn", 0.0000297)) * 100.0  # converted to %
            self.sebi_pct = float(raw_costs.get("sebi_fee", 0.000001)) * 100.0
            self.gst_pct = float(raw_costs.get("gst_rate", 0.18))
            self.stamp_intraday_pct = float(raw_costs.get("stamp_duty_intraday", 0.00003)) * 100.0
            self.stamp_delivery_pct = float(raw_costs.get("stamp_duty_delivery", 0.00015)) * 100.0
            self.stamp_options_pct = float(raw_costs.get("stamp_duty_options", 0.00003)) * 100.0
            self.stt_delivery_pct = 0.10  # 0.1%
            self.stt_intraday_sell_pct = 0.025  # 0.025%
            self.dp_charges = float(raw_costs.get("dp_charges", 15.93))
            self.base_slippage_bps = float(raw_costs.get("base_slippage_bps", 5.0))
            self.impact_coefficient = float(raw_costs.get("slippage_impact_factor", 0.10))
            self.max_adtv_order_pct = float(raw_costs.get("max_adtv_order_pct", 0.02))
        else:
            e = (cfg or {}).get("execution", {})
            self.brokerage_pct = float(e.get("brokerage_pct", e.get("brokerage", 0.0)))
            self.brokerage_flat = float(e.get("brokerage_flat", 0.0))
            self.exchange_pct = float(e.get("exchange_txn_fee_pct", 0.00297))
            self.sebi_pct = float(e.get("sebi_turnover_fee_pct", 0.0001))
            self.gst_pct = float(e.get("gst_pct", 0.18))
            self.stamp_intraday_pct = float(e.get("stamp_duty_non_delivery_pct", 0.003))
            self.stamp_delivery_pct = float(e.get("stamp_duty_delivery_pct", 0.015))
            self.stamp_options_pct = 0.003
            self.stt_intraday_sell_pct = float(e.get("stt_intraday_sell_pct", 0.025))
            self.stt_delivery_pct = float(e.get("stt_delivery_pct", 0.10))
            self.dp_charges = float(e.get("dp_charges", 15.93))
            self.base_slippage_bps = float(e.get("base_slippage_bps", e.get("slippage_bps", 5.0)))
            self.impact_coefficient = float(e.get("slippage_impact_coefficient", 0.10))
            self.max_adtv_order_pct = 0.02

    def calculate_slippage_bps(self, value: float, adtv: Optional[float] = None) -> float:
        """
        Slippage formula per STRATEGY_SPEC.md Section 4:
        slippage: max(5 bps, 0.1 * order_value/ADTV * 10000 bps) per side, capped at 50 bps.
        Rejects orders above 2% of ADTV.
        """
        val = float(value)
        if val <= 0:
            return 0.0

        if adtv is not None and float(adtv) > 0:
            participation = val / float(adtv)
            if participation > self.max_adtv_order_pct:
                raise ValueError(
                    f"Order value {val:.2f} exceeds {self.max_adtv_order_pct*100:.1f}% of ADTV ({adtv:.2f})"
                )
            impact_bps = self.impact_coefficient * participation * 10000.0
            bps = max(self.base_slippage_bps, impact_bps)
        else:
            bps = self.base_slippage_bps

        return min(50.0, float(bps))

    def calculate(
        self,
        value: float,
        action: str,
        segment: str = "DELIVERY",
        adtv: Optional[float] = None,
        asof: Optional[Union[date, datetime, str]] = None,
        qty: int = 1,
        include_slippage: bool = False
    ) -> float:
        """
        Calculates exact total transaction costs in INR for an order.
        """
        val = float(value)
        if val <= 0:
            return 0.0

        act = action.upper()
        if act in ("SHORT", "SELL"):
            act = "SELL"
        elif act in ("BUY", "COVER"):
            act = "BUY"
        seg = segment.upper()

        # Brokerage & Exchange & SEBI fees
        brokerage = max(self.brokerage_flat, val * self.brokerage_pct / 100.0) if (self.brokerage_flat or self.brokerage_pct) else 0.0
        exchange = val * self.exchange_pct / 100.0
        sebi = val * self.sebi_pct / 100.0
        gst = (brokerage + exchange + sebi) * self.gst_pct

        target_date = str(asof)[:10] if asof else "2026-10-23"

        if seg in ("DELIVERY", "CNC"):
            stamp = val * self.stamp_delivery_pct / 100.0 if act == "BUY" else 0.0
            # 0.1% STT on both buy and sell
            stt = val * self.stt_delivery_pct / 100.0
            dp = self.dp_charges if act == "SELL" else 0.0
        elif seg in ("INTRADAY", "MIS"):
            stamp = val * self.stamp_intraday_pct / 100.0 if act == "BUY" else 0.0
            # 0.025% STT on sell side only
            stt = val * self.stt_intraday_sell_pct / 100.0 if act == "SELL" else 0.0
            dp = 0.0
        elif seg in ("OPTIONS", "OPTION"):
            stamp = val * self.stamp_options_pct / 100.0 if act == "BUY" else 0.0
            # Option sell STT: 0.1% before 2026-04-01; 0.15% from 2026-04-01
            if act == "SELL":
                stt_rate = 0.0015 if target_date >= "2026-04-01" else 0.0010
                stt = val * stt_rate
            else:
                stt = 0.0
            dp = 0.0
        elif seg in ("FUTURES", "FUTURE"):
            stamp = val * self.stamp_intraday_pct / 100.0 if act == "BUY" else 0.0
            # Future sell STT: 0.02% before 2026-04-01; 0.05% from 2026-04-01
            if act == "SELL":
                stt_rate = 0.0005 if target_date >= "2026-04-01" else 0.0002
                stt = val * stt_rate
            else:
                stt = 0.0
            dp = 0.0
        else:
            stamp = 0.0
            stt = 0.0
            dp = 0.0

        statutory = brokerage + exchange + sebi + gst + stamp + stt + dp
        slippage_cost = 0.0
        if include_slippage:
            bps = self.calculate_slippage_bps(val, adtv=adtv)
            slippage_cost = val * (bps / 10000.0)

        return float(statutory + slippage_cost)
