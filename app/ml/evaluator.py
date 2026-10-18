import numpy as np
import pandas as pd


def evaluate_meta_labeling_value_add(trades_df, feature_matrix, model, threshold=0.55, cost_pct=0.0012):
    """
    Directly tests whether ML meta-labeling improves performance over rule-only baseline.
    Computes out-of-sample Expectancy delta, Sharpe improvement, and 95% Bootstrap CI.
    """
    if trades_df.empty or len(trades_df) != len(feature_matrix):
        return {
            "accepted": False,
            "reason": "Mismatched or empty trade and feature samples"
        }

    raw_rets = trades_df["ret"].values
    rule_net_rets = raw_rets - cost_pct
    rule_expectancy = float(np.mean(rule_net_rets))

    # ML meta-labeling predictions
    probs = model.predict_proba(feature_matrix)
    takes = probs >= threshold
    sizes = np.clip(2.0 * (probs - 0.4), 0.2, 1.5)

    ml_net_rets = []
    for taken, size, ret in zip(takes, sizes, raw_rets):
        if taken:
            ml_net_rets.append(size * (ret - cost_pct))

    ml_taken_count = len(ml_net_rets)
    if ml_taken_count < 10:
        return {
            "accepted": False,
            "reason": f"Insufficient trades approved by ML model ({ml_taken_count} trades)",
            "rule_expectancy": round(rule_expectancy, 5),
            "ml_expectancy": 0.0
        }

    ml_net_arr = np.array(ml_net_rets)
    ml_expectancy = float(np.mean(ml_net_arr))
    delta_expectancy = ml_expectancy - rule_expectancy

    # 95% Bootstrap Confidence Interval on Delta Expectancy
    rng = np.random.default_rng(42)
    boot_deltas = []
    n_sample = len(raw_rets)
    for _ in range(500):
        b_idx = rng.choice(n_sample, size=n_sample, replace=True)
        b_rule_mean = np.mean(rule_net_rets[b_idx])
        b_ml_taken = [sizes[i] * (raw_rets[i] - cost_pct) for i in b_idx if takes[i]]
        b_ml_mean = np.mean(b_ml_taken) if len(b_ml_taken) > 0 else 0.0
        boot_deltas.append(b_ml_mean - b_rule_mean)

    ci_lower = float(np.percentile(boot_deltas, 2.5))
    ci_upper = float(np.percentile(boot_deltas, 97.5))

    # Statistical Acceptance: Out-of-sample improvement with CI lower bound > 0
    accepted = (delta_expectancy > 0.0) and (ci_lower > 0.0)

    # Sharpe ratio comparison
    rule_std = float(np.std(rule_net_rets)) or 1e-6
    ml_std = float(np.std(ml_net_arr)) or 1e-6
    rule_sharpe = float((rule_expectancy / rule_std) * np.sqrt(252))
    ml_sharpe = float((ml_expectancy / ml_std) * np.sqrt(252))

    return {
        "accepted": bool(accepted),
        "rule_expectancy": round(rule_expectancy, 5),
        "ml_expectancy": round(ml_expectancy, 5),
        "delta_expectancy": round(delta_expectancy, 5),
        "ci_95": (round(ci_lower, 5), round(ci_upper, 5)),
        "rule_sharpe": round(rule_sharpe, 2),
        "ml_sharpe": round(ml_sharpe, 2),
        "proposals_evaluated": len(raw_rets),
        "proposals_approved": ml_taken_count,
        "approval_rate_pct": round(ml_taken_count / len(raw_rets) * 100.0, 1),
        "feature_importance": model.get_feature_importance()
    }
