import numpy as np
import pandas as pd


def calculate_session_vwap(df, include_bands=True):
    """
    Calculates per-session Volume-Weighted Average Price (VWAP) for intraday bars.
    Strictly resets cumulative metrics at each day's session start (09:15 IST),
    preventing multi-day statistical leakage.
    """
    if df is None or df.empty or not all(c in df.columns for c in ["High", "Low", "Close", "Volume"]):
        return pd.DataFrame() if include_bands else pd.Series(dtype=float)

    data = df.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        try:
            data.index = pd.to_datetime(data.index)
        except Exception:
            return pd.DataFrame() if include_bands else pd.Series(dtype=float)

    # Typical price = (High + Low + Close) / 3.0
    typ = (data["High"] + data["Low"] + data["Close"]) / 3.0
    pv = typ * data["Volume"]
    dates = data.index.date

    # Per-session cumulation
    cum_pv = pv.groupby(dates).cumsum()
    cum_vol = data["Volume"].groupby(dates).cumsum().clip(lower=1.0)
    vwap = cum_pv / cum_vol

    if not include_bands:
        return vwap

    # Calculate intra-session variance: E[P^2] - (E[P])^2
    pv2 = (typ ** 2) * data["Volume"]
    cum_pv2 = pv2.groupby(dates).cumsum()
    variance = (cum_pv2 / cum_vol) - (vwap ** 2)
    std = np.sqrt(np.maximum(0.0, variance))

    res = pd.DataFrame({
        "vwap": vwap,
        "upper_1": vwap + std,
        "lower_1": vwap - std,
        "upper_2": vwap + 2.0 * std,
        "lower_2": vwap - 2.0 * std
    }, index=data.index)
    return res
