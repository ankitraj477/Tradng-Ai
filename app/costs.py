import math


class CostModel:
    """
    Unified cost and market-impact model for NSE Cash Equity (Intraday and Delivery).
    Includes exact statutory fees (STT, GST, Exchange, SEBI, Stamp Duty, DP) and
    dynamic volume-weighted market impact slippage based on ADTV.
    """
    def __init__(self, cfg=None):
        if cfg is None:
            self.brokerage_pct = 0.0
            self.brokerage_flat = 0.0
            self.exchange_pct = 0.00297
            self.sebi_pct = 0.0001
            self.gst_pct = 0.18
            self.stamp_intraday_pct = 0.003
            self.stamp_delivery_pct = 0.015
            self.stt_intraday_sell_pct = 0.025
            self.stt_delivery_pct = 0.10
            self.dp_charges = 15.93
            self.base_slippage_bps = 5.0
            self.impact_coefficient = 0.10
        else:
            e = cfg.get('execution', {})
            self.brokerage_pct = float(e.get('brokerage_pct', e.get('brokerage', 0.0)))
            self.brokerage_flat = float(e.get('brokerage_flat', 0.0))
            self.exchange_pct = float(e.get('exchange_txn_fee_pct', 0.0))
            self.sebi_pct = float(e.get('sebi_turnover_fee_pct', 0.0))
            self.gst_pct = float(e.get('gst_pct', 0.0))
            self.stamp_intraday_pct = float(e.get('stamp_duty_non_delivery_pct', 0.0))
            self.stamp_delivery_pct = float(e.get('stamp_duty_delivery_pct', 0.0))
            self.stt_intraday_sell_pct = float(e.get('stt_intraday_sell_pct', 0.0))
            self.stt_delivery_pct = float(e.get('stt_delivery_pct', 0.0))
            self.dp_charges = float(e.get('dp_charges', 0.0))
            self.base_slippage_bps = float(e.get('base_slippage_bps', e.get('slippage_bps', 0.0)))
            self.impact_coefficient = float(e.get('slippage_impact_coefficient', 0.10))

    def calculate_slippage(self, value, adtv=None, base_bps=None):
        """
        Calculates dynamic slippage in currency (INR) using square-root market impact.
        slippage_pct = (base_bps / 10000) + impact_coef * sqrt(order_value / ADTV)
        """
        val = float(value)
        if val <= 0:
            return 0.0

        base = (self.base_slippage_bps if base_bps is None else float(base_bps)) / 10000.0
        impact = 0.0

        if adtv is not None and float(adtv) > 0:
            participation = min(1.0, val / float(adtv))
            impact = self.impact_coefficient * math.sqrt(participation)

        slippage_rate = base + impact
        return float(val * slippage_rate)

    def calculate(self, value, action, segment='INTRADAY', adtv=None, include_slippage=False):
        """
        Calculates total transaction costs for an NSE Cash Equity trade.
        Matches exact Indian statutory charges (STT, GST, Exchange, SEBI, Stamp Duty, DP).
        Optionally includes dynamic volume-weighted slippage.
        """
        act = action.upper()
        seg = segment.upper()
        val = float(value)
        if val <= 0:
            return 0.0

        brokerage = max(self.brokerage_flat, val * self.brokerage_pct / 100.0) if (self.brokerage_flat or self.brokerage_pct) else 0.0
        exchange = val * self.exchange_pct / 100.0
        sebi = val * self.sebi_pct / 100.0
        gst = (brokerage + exchange + sebi) * self.gst_pct

        if seg == 'DELIVERY':
            stamp = val * self.stamp_delivery_pct / 100.0 if act == 'BUY' else 0.0
            stt = val * self.stt_delivery_pct / 100.0
            dp = self.dp_charges if act == 'SELL' else 0.0
        else:
            stamp = val * self.stamp_intraday_pct / 100.0 if act == 'BUY' else 0.0
            stt = val * self.stt_intraday_sell_pct / 100.0 if act == 'SELL' else 0.0
            dp = 0.0

        statutory = brokerage + exchange + sebi + gst + stamp + stt + dp
        slippage = self.calculate_slippage(val, adtv=adtv) if include_slippage else 0.0

        return float(statutory + slippage)

