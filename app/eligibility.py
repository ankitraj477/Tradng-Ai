from datetime import datetime, timedelta
import pandas as pd


class EligibilityFilter:
    """
    Filters universe for institutional execution viability:
    - Minimum Average Daily Traded Value (ADTV in INR)
    - Regulatory Surveillance Lists (ASM/GSM)
    - F&O Ban Lists
    - Earnings/Results Blackout Window (skip candidates +-1 day from quarterly earnings)
    """
    def __init__(self, min_adtv_inr=50_000_000.0, asm_gsm_symbols=None, ban_symbols=None, earnings_dates=None):
        self.min_adtv = float(min_adtv_inr)
        self.asm_gsm = set(asm_gsm_symbols or [])
        self.ban_list = set(ban_symbols or [])
        # earnings_dates: dict mapping symbol -> set of date strings 'YYYY-MM-DD'
        self.earnings_dates = {s: {str(d)[:10] for d in dates} for s, dates in (earnings_dates or {}).items()}

    def check(self, symbol, df, current_date=None, target_results=False):
        # 1. Regulatory ASM / GSM Surveillance
        clean_sym = symbol.replace(".NS", "")
        if symbol in self.asm_gsm or clean_sym in self.asm_gsm:
            return False, "Under regulatory surveillance (ASM/GSM)"

        # 2. Ban List
        if symbol in self.ban_list or clean_sym in self.ban_list:
            return False, "Under exchange/F&O ban"

        # 3. Minimum Liquidity & Turnover (ADTV)
        if df is None or len(df) < 5:
            return False, "Insufficient price history"

        recent = df.tail(20)
        daily_turnover = recent["Close"] * recent["Volume"]
        adtv = float(daily_turnover.mean())
        if adtv < self.min_adtv:
            return False, f"ADTV {adtv:,.0f} below minimum threshold {self.min_adtv:,.0f}"

        # 4. Earnings / Results Blackout Window
        if not target_results and current_date is not None:
            c_date = pd.to_datetime(current_date).date()
            symbol_events = self.earnings_dates.get(symbol) or self.earnings_dates.get(clean_sym) or set()
            for ev_str in symbol_events:
                ev_date = pd.to_datetime(ev_str).date()
                if abs((c_date - ev_date).days) <= 1:
                    return False, f"Results blackout window (results on {ev_str})"

        return True, "Eligible"

    def filter_candidates(self, datasets, current_date=None, target_results=False):
        eligible = []
        for sym, df in datasets.items():
            ok, _ = self.check(sym, df, current_date, target_results)
            if ok: eligible.append(sym)
        return eligible
