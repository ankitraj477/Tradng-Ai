import numpy as np
import pandas as pd


class PurgedWalkForwardCV:
    """
    Purged and Embargoed Walk-Forward Cross Validation.
    Prevents information leakage from overlapping trade holding horizons.
    Strictly chronological: no random splits.
    Dynamically scales the purge window based on the maximum holding period to ensure
    training labels do not bleed into out-of-sample evaluation sets.
    """
    def __init__(self, n_splits=4, purge_bars=5, embargo_bars=2, max_holding_bars=None):
        self.n_splits = int(n_splits)
        self.embargo_bars = int(embargo_bars)
        self.max_holding_bars = int(max_holding_bars) if max_holding_bars is not None else None
        
        # Dynamically scale purge window if max_holding_bars is configured
        if self.max_holding_bars and self.max_holding_bars > 0:
            self.purge_bars = max(int(purge_bars), self.max_holding_bars + self.embargo_bars)
        else:
            self.purge_bars = int(purge_bars)

    def split(self, n_samples, event_horizons=None):
        """
        Yields (train_indices, test_indices) splits.
        If event_horizons is provided (iterable of trade durations per event),
        dynamically adjusts the purge window to the maximum active horizon at the boundary.
        """
        if n_samples < 20:
            yield np.arange(int(n_samples * 0.7)), np.arange(int(n_samples * 0.7), n_samples)
            return

        test_size = n_samples // (self.n_splits + 1)
        min_train_size = test_size

        for i in range(self.n_splits):
            train_end = min_train_size + i * test_size
            
            # Dynamic purge window calculation
            purge = self.purge_bars
            if event_horizons is not None and len(event_horizons) >= train_end:
                recent_horizons = event_horizons[:train_end]
                if len(recent_horizons) > 0:
                    max_recent = int(np.max(recent_horizons[-min(len(recent_horizons), 20):]))
                    purge = max(purge, max_recent + self.embargo_bars)

            test_start = train_end + purge
            test_end = min(n_samples, test_start + test_size)

            if test_start >= n_samples or test_start >= test_end:
                break

            train_idx = np.arange(0, train_end)
            test_idx = np.arange(test_start, test_end)
            yield train_idx, test_idx


def evaluate_cv_performance(model_cls, X, y, cv=None):
    """Evaluates cross-validated out-of-sample metrics across purged folds."""
    X_mat = np.array(X, dtype=float)
    y_vec = np.array(y, dtype=float)
    splitter = cv or PurgedWalkForwardCV()

    fold_metrics = []
    all_test_preds = []
    all_test_trues = []

    for fold_idx, (train_idx, test_idx) in enumerate(splitter.split(len(X_mat))):
        if len(train_idx) < 10 or len(test_idx) < 5: continue
        X_tr, y_tr = X_mat[train_idx], y_vec[train_idx]
        X_te, y_te = X_mat[test_idx], y_vec[test_idx]

        model = model_cls()
        model.fit(X_tr, y_tr)
        probs = model.predict_proba(X_te)

        preds = (probs >= 0.50).astype(int)
        acc = float(np.mean(preds == y_te))
        brier = float(np.mean((probs - y_te) ** 2))

        all_test_preds.extend(probs)
        all_test_trues.extend(y_te)

        fold_metrics.append({
            "fold": fold_idx,
            "train_size": len(train_idx),
            "test_size": len(test_idx),
            "accuracy": round(acc, 4),
            "brier_score": round(brier, 4)
        })

    total_acc = float(np.mean((np.array(all_test_preds) >= 0.5) == np.array(all_test_trues))) if all_test_preds else 0.0
    return {
        "mean_accuracy": round(total_acc, 4),
        "folds": fold_metrics,
        "n_test_samples": len(all_test_preds)
    }
