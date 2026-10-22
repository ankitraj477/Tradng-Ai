import numpy as np
import pandas as pd


def get_atr(df, span=14):
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    # BUG-017: Avoid bfill() which leaks future ATR into historical bars; use causal expanding/rolling
    return tr.rolling(span, min_periods=1).mean()


def apply_triple_barrier(df, events, pt_mult=2.0, sl_mult=1.0, max_hold_bars=10):
    """
    Marcos Lopez de Prado's Triple-Barrier Labeling Method.
    Barriers:
    1. Upper barrier (Profit target): Entry + pt_mult * ATR
    2. Lower barrier (Stop loss): Entry - sl_mult * ATR
    3. Vertical barrier (Time limit): Entry + max_hold_bars
    Returns labels: 1 (Take/Profitable), 0 (Skip/Loss)
    """
    if df is None or df.empty or not events:
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "label", "ret", "barrier"])

    atr_series = get_atr(df)
    labeled = []

    for ev in events:
        t_idx = ev.get("index") or ev.get("timestamp")
        if t_idx not in df.index:
            continue
        loc = df.index.get_loc(t_idx)
        if isinstance(loc, (slice, np.ndarray)):
            loc = loc.start if isinstance(loc, slice) else loc[0]

        entry_px = float(df["Close"].iloc[loc])
        side = ev.get("side", "LONG").upper()
        atr = float(atr_series.iloc[loc])
        atr = max(atr, entry_px * 0.005)

        pt_dist = pt_mult * atr
        sl_dist = sl_mult * atr

        if side == "LONG":
            upper = entry_px + pt_dist
            lower = entry_px - sl_dist
        else:
            upper = entry_px - pt_dist  # Target for short is below
            lower = entry_px + sl_dist  # Stop for short is above

        end_loc = min(len(df) - 1, loc + max_hold_bars)
        horizon_df = df.iloc[loc + 1:end_loc + 1]

        label = 0
        barrier_hit = "time"
        exit_px = float(df["Close"].iloc[end_loc])

        for bar_idx, row in horizon_df.iterrows():
            high = float(row["High"])
            low = float(row["Low"])
            open_px = float(row["Open"])

            if side == "LONG":
                # Check stop loss first (conservative path)
                if low <= lower:
                    barrier_hit = "stop"
                    exit_px = min(lower, open_px)
                    label = 0
                    break
                elif high >= upper:
                    barrier_hit = "target"
                    exit_px = max(upper, open_px)
                    label = 1
                    break
            else:  # SHORT
                if high >= lower:
                    barrier_hit = "stop"
                    exit_px = max(lower, open_px)
                    label = 0
                    break
                elif low <= upper:
                    barrier_hit = "target"
                    exit_px = min(upper, open_px)
                    label = 1
                    break

        ret = ((exit_px - entry_px) / entry_px) if side == "LONG" else ((entry_px - exit_px) / entry_px)
        # If time expired, label is 1 only if return is positive
        if barrier_hit == "time":
            label = 1 if ret > 0 else 0

        labeled.append({
            "timestamp": t_idx,
            "symbol": ev.get("symbol", "TEST"),
            "side": side,
            "entry_price": entry_px,
            "exit_price": exit_px,
            "label": int(label),
            "ret": float(ret),
            "barrier": barrier_hit
        })

    return pd.DataFrame(labeled)
