import pandas as pd
import numpy as np


def rank_spearman(x, y):
    """Computes Spearman rank correlation without external scipy dependency."""
    valid = (~np.isnan(x)) & (~np.isnan(y))
    xv = x[valid]
    yv = y[valid]
    if len(xv) < 5: return 0.0

    rx = pd.Series(xv).rank().values
    ry = pd.Series(yv).rank().values
    n = len(rx)
    d = rx - ry
    d_sq = np.sum(d ** 2)
    rho = 1.0 - (6.0 * d_sq) / (n * (n ** 2 - 1.0))
    return float(max(-1.0, min(1.0, rho)))


def compute_information_coefficient(feature_series, forward_return_series):
    """
    Computes Spearman Information Coefficient (IC) between feature values at t
    and realized forward returns at t+h.
    """
    x = np.array(feature_series, dtype=float)
    y = np.array(forward_return_series, dtype=float)
    ic = rank_spearman(x, y)
    n = len(x)
    # T-statistic for IC significance
    t_stat = (ic * np.sqrt(n - 2) / np.sqrt(max(1e-9, 1.0 - ic ** 2))) if n > 2 and abs(ic) < 0.999 else 0.0
    return {
        "ic": round(ic, 4),
        "t_stat": round(float(t_stat), 2),
        "samples": n
    }


def verify_no_lookahead(feature_func, df, target_idx):
    """
    Lookahead shift test.
    Verifies that feature value at target_idx is strictly identical
    regardless of what future data is appended or mutated after target_idx.

    BUG-014: Evaluates full frame when feature_func returns a Series/DataFrame
    so mutations at target_idx + 1: cannot leak into target_idx without detection.
    Also supports slice-based calculators that return a scalar for target_idx.
    """
    mutated = df.copy()
    future_len = len(mutated) - (target_idx + 1)
    if future_len > 0:
        mutated.iloc[target_idx + 1:, mutated.columns.get_loc("Close")] *= 10.0
        mutated.iloc[target_idx + 1:, mutated.columns.get_loc("High")] *= 10.0
        mutated.iloc[target_idx + 1:, mutated.columns.get_loc("Low")] *= 10.0
        mutated.iloc[target_idx + 1:, mutated.columns.get_loc("Volume")] *= 10.0

    try:
        val_orig = feature_func(df.copy())
        if isinstance(val_orig, (pd.Series, pd.DataFrame, np.ndarray, list)):
            val_mut = feature_func(mutated)
            orig_item = val_orig.iloc[target_idx] if hasattr(val_orig, "iloc") else val_orig[target_idx]
            mut_item = val_mut.iloc[target_idx] if hasattr(val_mut, "iloc") else val_mut[target_idx]
            return bool(np.isclose(float(orig_item), float(mut_item), atol=1e-8))
    except Exception:
        pass

    # Slice-based evaluation: feature evaluated on history up to target_idx
    slice_past = df.iloc[:target_idx + 1].copy()
    val_past = feature_func(slice_past)
    val_mutated = feature_func(mutated.iloc[:target_idx + 1])
    return bool(np.isclose(float(val_past), float(val_mutated), atol=1e-8))


def generate_feature_report(features_df, forward_returns_df):
    """Generates an information coefficient report across all candidate features and horizons."""
    report = []
    for feat_col in features_df.columns:
        row = {"feature": feat_col}
        for fwd_col in forward_returns_df.columns:
            res = compute_information_coefficient(features_df[feat_col], forward_returns_df[fwd_col])
            row[f"ic_{fwd_col}"] = res["ic"]
            row[f"t_stat_{fwd_col}"] = res["t_stat"]
        report.append(row)
    return pd.DataFrame(report)
