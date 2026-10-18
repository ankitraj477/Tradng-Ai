import numpy as np
import pandas as pd


def compute_return(series, window):
    if len(series) <= window: return 0.0
    p_end = float(series.iloc[-1])
    p_start = float(series.iloc[-window - 1])
    return (p_end / p_start - 1.0) if p_start > 0 else 0.0


def calculate_stock_rs(stock_df, benchmark_df, sector_df=None, windows=(20, 60, 120)):
    """Computes relative strength of a stock vs benchmark and sector over multiple horizons."""
    res = {}
    if stock_df is None or benchmark_df is None or len(stock_df) < 25 or len(benchmark_df) < 25:
        return {f"rs_{w}": 0.0 for w in windows}

    stk_close = stock_df["Close"]
    bmk_close = benchmark_df["Close"]

    for w in windows:
        stk_ret = compute_return(stk_close, w)
        bmk_ret = compute_return(bmk_close, w)
        res[f"rs_{w}"] = round(float(stk_ret - bmk_ret), 4)

        if sector_df is not None and len(sector_df) > w:
            sec_ret = compute_return(sector_df["Close"], w)
            res[f"rs_sector_{w}"] = round(float(stk_ret - sec_ret), 4)

    return res


def rank_cross_sectional_rs(universe_data, benchmark_series=None, windows=(20, 60, 120)):
    """
    Ranks an entire constituent universe cross-sectionally based on multi-horizon relative strength.
    Assigns percentile ranks (0-100) and identifies top decile market leadership.
    """
    rows = []
    # If benchmark not explicitly supplied, use equal-weight composite
    if benchmark_series is None:
        closes = pd.DataFrame({s: df["Close"] for s, df in universe_data.items() if df is not None and not df.empty})
        bmk = closes.pct_change().mean(axis=1).fillna(0.0)
        bmk_cum = (1.0 + bmk).cumprod()
    else:
        bmk_cum = benchmark_series

    for sym, df in universe_data.items():
        if df is None or len(df) < min(windows) + 1: continue
        c = df["Close"]
        metrics = {"symbol": sym}
        for w in windows:
            stk_r = compute_return(c, w)
            bmk_r = compute_return(bmk_cum, w) if bmk_cum is not None else 0.0
            metrics[f"rs_{w}"] = stk_r - bmk_r
            metrics[f"ret_{w}"] = stk_r

        # Weighted composite score: 40% 20d, 35% 60d, 25% 120d
        metrics["rs_composite"] = (
            metrics.get("rs_20", 0.0) * 0.40 +
            metrics.get("rs_60", 0.0) * 0.35 +
            metrics.get("rs_120", 0.0) * 0.25
        )
        rows.append(metrics)

    if not rows:
        return pd.DataFrame(columns=["symbol", "rs_composite", "rank_pct", "top_decile"])

    df_rank = pd.DataFrame(rows)
    df_rank["rank_pct"] = df_rank["rs_composite"].rank(pct=True) * 100.0
    df_rank["top_decile"] = df_rank["rank_pct"] >= 90.0
    df_rank.sort_values(by="rank_pct", ascending=False, inplace=True)
    df_rank.reset_index(drop=True, inplace=True)
    return df_rank
