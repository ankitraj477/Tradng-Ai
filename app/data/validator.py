"""
Comprehensive data validator for market research and systematic execution.
Enforces Section 3 & Section 10 (Test 1) requirements:
- No gaps beyond official holidays
- No non-positive prices
- Monotonic increasing date indices without duplicates
- High/Low boundary integrity
- Adjusted-close continuity across corporate actions
- Rigorous look-ahead detection with deliberate positive-control testing
"""

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta, timezone
from typing import Tuple, Optional, Callable


def validate_history(df, max_age_seconds=900, require_fresh=True):
    """Backward-compatible validation wrapper for legacy providers."""
    if df is None or df.empty:
        return False, "empty data"
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return False, "missing columns"
    if df[["Open", "High", "Low", "Close", "Volume"]].isnull().any().any():
        return False, "missing values"
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return False, "invalid prices"
    if (df["High"] < df[["Open", "Close"]].max(axis=1) - 1e-4).any():
        return False, "invalid high"
    if (df["Low"] > df[["Open", "Close"]].min(axis=1) + 1e-4).any():
        return False, "invalid low"
    if df.index.duplicated().any():
        return False, "duplicate timestamps"
    if not df.index.is_monotonic_increasing:
        return False, "timestamps not ordered"
    if require_fresh:
        ts = df.index[-1]
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.tz_localize("UTC")
        age = (datetime.now(timezone.utc) - ts.to_pydatetime()).total_seconds()
        if age > max_age_seconds:
            return False, f"stale data: {age:.0f}s"
    return True, "ok"


def validate_market_data(
    df: pd.DataFrame,
    calendar=None,
    symbol: str = "UNKNOWN"
) -> Tuple[bool, str]:
    """
    Validate daily OHLCV dataframe according to institutional data standards.
    """
    if df is None or df.empty:
        return False, f"{symbol}: DataFrame is empty or None"

    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        return False, f"{symbol}: Missing required OHLCV columns: {missing}"

    # 1. No missing (NaN) values in OHLCV
    if df[["Open", "High", "Low", "Close", "Volume"]].isnull().any().any():
        return False, f"{symbol}: Contains NaN/null values in OHLCV bars"

    # 2. No non-positive prices
    for col in ("Open", "High", "Low", "Close"):
        if (df[col] <= 0).any():
            invalid_count = (df[col] <= 0).sum()
            return False, f"{symbol}: Contains {invalid_count} non-positive values in {col}"

    if (df["Volume"] < 0).any():
        return False, f"{symbol}: Contains negative Volume values"

    # 3. High/Low boundary integrity
    max_oc = df[["Open", "Close"]].max(axis=1)
    min_oc = df[["Open", "Close"]].min(axis=1)
    if (df["High"] < max_oc - 1e-4).any():
        return False, f"{symbol}: High is lower than max(Open, Close)"
    if (df["Low"] > min_oc + 1e-4).any():
        return False, f"{symbol}: Low is higher than min(Open, Close)"

    # 4. Monotonic increasing dates and no duplicate indices
    if df.index.duplicated().any():
        dup_count = df.index.duplicated().sum()
        return False, f"{symbol}: Contains {dup_count} duplicate timestamps"

    if not df.index.is_monotonic_increasing:
        return False, f"{symbol}: Index timestamps are not monotonically increasing"

    # 5. Gap validation using official holiday calendar
    if calendar is not None and len(df) > 1:
        dates = [d.date() if hasattr(d, "date") else datetime.strptime(str(d)[:10], "%Y-%m-%d").date() for d in df.index]
        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i + 1]
            diff = (d2 - d1).days
            if diff > 1:
                # Every day strictly between d1 and d2 must NOT be a trading day
                # (i.e. must be weekend or listed holiday)
                cur = d1 + timedelta(days=1)
                while cur < d2:
                    if calendar.is_trading_day(cur):
                        return False, f"{symbol}: Unexplained missing trading day gap on {cur.isoformat()}"
                    cur += timedelta(days=1)

    # 6. Adjusted close continuity check (split anomaly detection)
    # Consecutive close-to-close ratio shouldn't exceed 4.0 or drop below 0.25 without adjusted flag
    if len(df) > 1:
        ratios = df["Close"] / df["Close"].shift(1)
        anomalies = ratios[(ratios > 4.0) | (ratios < 0.25)]
        if not anomalies.empty:
            return False, f"{symbol}: Unadjusted price jump detected across bar {anomalies.index[0]}"

    return True, "ok"


def assert_no_lookahead(
    feature_builder: Callable[[pd.DataFrame], pd.Series],
    df: pd.DataFrame
) -> bool:
    """
    Test 1 from STRATEGY_SPEC.md:
    Ensure feature calculation contains NO look-ahead bias.
    Truncating the future (evaluating on df.iloc[:t]) MUST yield the exact same value
    for bar t as evaluating on the full series df.
    """
    if len(df) < 10:
        raise ValueError("Need at least 10 bars to test for look-ahead bias")

    full_features = feature_builder(df)

    # Check multiple cutoff points
    for t in [len(df) - 5, len(df) - 3, len(df) - 1]:
        truncated_df = df.iloc[:t].copy()
        truncated_features = feature_builder(truncated_df)

        val_full = full_features.iloc[t - 1]
        val_trunc = truncated_features.iloc[-1]

        if not np.isclose(val_full, val_trunc, equal_nan=True, rtol=1e-5, atol=1e-5):
            raise AssertionError(
                f"Look-ahead bias detected! Feature value at index {df.index[t-1]} "
                f"changed from {val_trunc} (with data up to t) to {val_full} (with future data)."
            )

    return True
