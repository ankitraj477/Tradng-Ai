class CostModel:
    """Unified cost model for NSE Cash Equity (Intraday and Delivery)."""
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

    def calculate(self, value, action, segment='INTRADAY'):
        act = action.upper()
        seg = segment.upper()
        val = float(value)
        if val <= 0: return 0.0

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

        return float(brokerage + exchange + sebi + gst + stamp + stt + dp)
