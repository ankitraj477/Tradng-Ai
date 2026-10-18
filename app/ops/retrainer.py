from datetime import datetime, timezone
import numpy as np
import pandas as pd
from ..ml.model import MetaLabelingClassifier
from ..ml.cross_validation import PurgedWalkForwardCV, evaluate_cv_performance


class OfflineRetrainer:
    """
    Offline model retraining pipeline.
    Replaces real-time heuristic weight tweaking with reproducible, weekly
    retraining directly from the persistent candidate feature log.
    """
    DEFAULT_FEATURES = [
        "rsi", "rel_volume", "volatility", "ret_5", "ret_20", "bull_score", "bear_score"
    ]

    def __init__(self, target_horizon="forward_ret_5d", cost_hurdle=0.0012):
        self.target_horizon = target_horizon
        self.cost_hurdle = float(cost_hurdle)

    def prepare_dataset(self, log_df, feature_cols=None):
        cols = feature_cols or self.DEFAULT_FEATURES
        if log_df.empty or self.target_horizon not in log_df.columns:
            return None, None, []

        valid = log_df.dropna(subset=[self.target_horizon] + [c for c in cols if c in log_df.columns]).copy()
        if len(valid) < 20:
            return None, None, []

        used_features = [c for c in cols if c in valid.columns]
        X = valid[used_features].values
        # Target label: 1 if forward return exceeds round-trip transaction hurdle, else 0
        y = (valid[self.target_horizon].values > self.cost_hurdle).astype(int)
        return X, y, used_features

    def retrain(self, log_df, feature_cols=None, l2_reg=1.0):
        X, y, features = self.prepare_dataset(log_df, feature_cols)
        if X is None or len(X) < 20:
            return {
                "success": False,
                "reason": "Insufficient labeled candidate history for retraining"
            }

        # 1. Evaluate cross-validation accuracy on chronological folds
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=5)
        cv_res = evaluate_cv_performance(MetaLabelingClassifier, X, y, cv)

        # 2. Train final model on full historical dataset
        model = MetaLabelingClassifier(l2_reg=l2_reg, n_epochs=200)
        model.fit(X, y, feature_names=features)

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "samples": len(X),
            "features": features,
            "cv_accuracy": cv_res.get("mean_accuracy", 0.0),
            "feature_importances": model.get_feature_importance(),
            "model": model
        }
