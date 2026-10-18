import numpy as np
import pandas as pd


class EventStudy:
    """
    Event Study Module analyzing post-announcement drift (PEAD).
    Computes Average Abnormal Return (AAR) and Cumulative Abnormal Return (CAR)
    relative to market benchmark over 1, 3, and 5-day post-announcement horizons.
    """
    def __init__(self, cost_pct=0.0012):
        self.cost_pct = float(cost_pct)

    def compute_abnormal_returns(self, stock_df, benchmark_df, event_date, horizons=(1, 3, 5)):
        """Computes abnormal forward returns (Stock return - Benchmark return) for a single event."""
        if stock_df is None or benchmark_df is None:
            return {}

        s_close = stock_df["Close"]
        b_close = benchmark_df["Close"]

        # Find closest date >= event_date
        c_dates = s_close.index[s_close.index >= pd.to_datetime(event_date)]
        if len(c_dates) < max(horizons) + 1:
            return {}

        t0 = c_dates[0]
        t0_idx = s_close.index.get_loc(t0)
        t0_px = float(s_close.iloc[t0_idx])
        b0_px = float(b_close.loc[t0]) if t0 in b_close.index else float(b_close.iloc[0])

        res = {}
        for h in horizons:
            target_idx = t0_idx + h
            if target_idx < len(s_close):
                th_date = s_close.index[target_idx]
                stk_ret = (float(s_close.iloc[target_idx]) / t0_px) - 1.0
                bmk_ret = ((float(b_close.loc[th_date]) / b0_px) - 1.0) if th_date in b_close.index else 0.0
                ar = stk_ret - bmk_ret
                res[f"ar_{h}d"] = ar
        return res

    def analyze_events(self, events_list, stock_data_dict, benchmark_df, horizons=(1, 3, 5)):
        """
        Runs event study across an entire set of corporate events grouped by event_type.
        Returns AAR, CAR, and net post-cost profitability.
        """
        grouped = {}
        for ev in events_list:
            ev_type = ev.get("event_type", "GENERAL")
            sym = ev.get("symbol")
            date = ev.get("date") or ev.get("published_at")
            if not sym or not date or sym not in stock_data_dict:
                continue

            ar_dict = self.compute_abnormal_returns(stock_data_dict[sym], benchmark_df, date, horizons)
            if ar_dict:
                if ev_type not in grouped: grouped[ev_type] = []
                grouped[ev_type].append(ar_dict)

        report = []
        for ev_type, ar_list in grouped.items():
            n = len(ar_list)
            row = {"event_type": ev_type, "events_count": n}
            for h in horizons:
                key = f"ar_{h}d"
                vals = [x[key] for x in ar_list if key in x]
                aar = float(np.mean(vals)) if vals else 0.0
                car_net = aar - self.cost_pct
                row[f"aar_{h}d"] = round(aar * 100.0, 3)
                row[f"car_{h}d_net"] = round(car_net * 100.0, 3)
                row[f"profitable_{h}d"] = bool(car_net > 0)
            report.append(row)

        return pd.DataFrame(report)
