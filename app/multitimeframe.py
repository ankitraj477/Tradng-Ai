import pandas as pd
import numpy as np


class MultiTimeframeAnalyzer:
    """
    Multi-timeframe hierarchy and time-of-day normalized volume analyzer.
    Daily trend and structural levels govern directional permission;
    intraday bars only provide execution entry timing.
    """
    @staticmethod
    def daily_direction(daily_df):
        """Determines macro directional bias from daily bars."""
        if daily_df is None or len(daily_df) < 50:
            return {"bias": "NEUTRAL", "support": None, "resistance": None}

        c = daily_df["Close"]
        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1])
        last_px = float(c.iloc[-1])

        # 20-day swing support and resistance
        support = float(daily_df["Low"].tail(20).min())
        resistance = float(daily_df["High"].tail(20).max())

        if last_px > ema20 > ema50:
            bias = "BULLISH"
        elif last_px < ema20 < ema50:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return {
            "bias": bias,
            "ema20": ema20,
            "ema50": ema50,
            "support": support,
            "resistance": resistance,
            "dist_to_resistance_pct": round((resistance - last_px) / last_px * 100.0, 2),
            "dist_to_support_pct": round((last_px - support) / last_px * 100.0, 2)
        }

    @staticmethod
    def normalize_tod_volume(intraday_df, lookback_days=10):
        """
        Normalizes volume against the same time-of-day historical median over prior N days.
        Removes the U-shaped opening/closing bar volume distortion.
        """
        if intraday_df is None or intraday_df.empty or "Volume" not in intraday_df.columns:
            return pd.Series(dtype=float)

        df = intraday_df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            return df["Volume"] / df["Volume"].rolling(20).mean()

        df["time_slot"] = df.index.time
        df["date"] = df.index.date

        unique_dates = sorted(df["date"].unique())
        # Use prior lookback_days dates for historical median
        hist_dates = unique_dates[-lookback_days-1:-1] if len(unique_dates) > lookback_days else unique_dates[:-1]
        hist_df = df[df["date"].isin(hist_dates)]

        if hist_df.empty:
            medians = df.groupby("time_slot")["Volume"].median()
        else:
            medians = hist_df.groupby("time_slot")["Volume"].median()

        norm = df.apply(lambda row: row["Volume"] / max(1.0, medians.get(row["time_slot"], 1.0)), axis=1)
        return norm
