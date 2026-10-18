import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.ml.labeling import apply_triple_barrier
from app.ml.model import MetaLabelingClassifier
from app.ml.cross_validation import PurgedWalkForwardCV, evaluate_cv_performance
from app.ml.evaluator import evaluate_meta_labeling_value_add


def _create_synthetic_ohlcv(n=60, trend=0.001):
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    px = 100.0
    rows = []
    for _ in range(n):
        high = px + 2.0
        low = px - 2.0
        close = px + 0.5
        rows.append({"Open": px, "High": high, "Low": low, "Close": close, "Volume": 10000})
        px = close
    return pd.DataFrame(rows, index=dates)


def test_triple_barrier_labeling():
    df = _create_synthetic_ohlcv(50)
    # 1. Target Hit Event: bar 10 price spikes up dramatically
    df.iloc[12, df.columns.get_loc("High")] = 120.0
    ev1 = [{"timestamp": df.index[10], "symbol": "TARGET_HIT.NS", "side": "LONG"}]
    res1 = apply_triple_barrier(df, ev1, pt_mult=1.5, sl_mult=1.5, max_hold_bars=10)
    assert len(res1) == 1
    assert res1["label"].iloc[0] == 1
    assert res1["barrier"].iloc[0] == "target"

    # 2. Stop Loss Event: bar 20 drops sharply
    df.iloc[22, df.columns.get_loc("Low")] = 80.0
    ev2 = [{"timestamp": df.index[20], "symbol": "STOP_HIT.NS", "side": "LONG"}]
    res2 = apply_triple_barrier(df, ev2, pt_mult=1.5, sl_mult=1.5, max_hold_bars=10)
    assert len(res2) == 1
    assert res2["label"].iloc[0] == 0
    assert res2["barrier"].iloc[0] == "stop"

    # 3. Short side test
    df.iloc[32, df.columns.get_loc("Low")] = 70.0  # Favorable for short
    ev3 = [{"timestamp": df.index[30], "symbol": "SHORT_WIN.NS", "side": "SHORT"}]
    res3 = apply_triple_barrier(df, ev3, pt_mult=1.5, sl_mult=1.5, max_hold_bars=10)
    assert len(res3) == 1
    assert res3["label"].iloc[0] == 1
    assert res3["barrier"].iloc[0] == "target"


def test_meta_labeling_model_fit_predict():
    rng = np.random.default_rng(42)
    n_samples = 150
    # Two informative features and one noise feature
    f1 = rng.normal(0, 1, n_samples)
    f2 = rng.normal(0, 1, n_samples)
    f3 = rng.normal(0, 1, n_samples)  # noise

    # True probability depends heavily on f1 and f2
    prob = 1.0 / (1.0 + np.exp(-(1.5 * f1 + 1.2 * f2)))
    y = (prob > 0.5).astype(int)
    X = np.column_stack([f1, f2, f3])

    model = MetaLabelingClassifier(l2_reg=0.5, n_epochs=150)
    model.fit(X, y, feature_names=["rs_rank", "volume_ratio", "noise"])

    # Predict probabilities
    preds = model.predict_proba(X)
    assert len(preds) == n_samples
    assert np.all((preds >= 0.0) & (preds <= 1.0))

    # Decision output
    dec = model.predict_decision(X[0], threshold=0.55)
    assert "take" in dec and "probability" in dec and "size_multiplier" in dec

    # Feature importance check: f1 and f2 should have higher importance than f3
    imp = model.get_feature_importance()
    assert imp["rs_rank"] > imp["noise"]


def test_purged_walk_forward_cv():
    n_samples = 100
    cv = PurgedWalkForwardCV(n_splits=3, purge_bars=4, embargo_bars=2)
    splits = list(cv.split(n_samples))
    assert len(splits) >= 2

    for train_idx, test_idx in splits:
        # Check chronological invariant: all training precedes testing
        assert train_idx[-1] < test_idx[0]
        # Check purge gap: test_start - train_end must be >= purge_bars
        assert (test_idx[0] - train_idx[-1]) >= 4

    # Performance evaluation
    rng = np.random.default_rng(10)
    X = rng.normal(size=(80, 4))
    y = rng.choice([0, 1], size=80)
    res = evaluate_cv_performance(MetaLabelingClassifier, X, y, cv)
    assert "mean_accuracy" in res
    assert len(res["folds"]) >= 2


def test_evaluator_value_add_and_bootstrap_ci():
    rng = np.random.default_rng(99)
    n = 100
    # Create trades where feature > 0 gives positive returns, feature < 0 gives losses
    feature = rng.normal(0, 1, n)
    returns = 0.03 * feature + rng.normal(0, 0.01, n)
    trades_df = pd.DataFrame({"ret": returns})
    X = feature.reshape(-1, 1)

    model = MetaLabelingClassifier(n_epochs=100)
    y = (returns > 0).astype(int)
    model.fit(X, y, feature_names=["feature_1"])

    eval_res = evaluate_meta_labeling_value_add(trades_df, X, model, threshold=0.50)
    assert "delta_expectancy" in eval_res
    assert "ci_95" in eval_res
    assert "approval_rate_pct" in eval_res
    # Model filters out negative-feature trades, improving expectancy
    assert eval_res["ml_expectancy"] > eval_res["rule_expectancy"]
