---
name: meta-labeling
description: Train and evaluate secondary machine learning meta-labeling models with Triple-Barrier labeling and Purged Walk-Forward Cross-Validation.
---

# ML Meta-Labeling & Purged Cross-Validation

Use this skill when developing or retraining the secondary machine learning classifier ([app/ml/](file:///c:/Users/KIIT/Desktop/projects/Tradng-Ai/app/ml/)) that filters out false-positive breakout and mean-reversion trades.

## Theoretical Foundation (De Prado Framework)

1. **Primary Model**: Generates the directional trade signal (+1 for Long, -1 for Short) based on rules or indicators.
2. **Secondary Model (Meta-Labeler)**: Predicts the binary probability $P(\text{Trade is profitable}) \in [0, 1]$.
   - If $P \ge \text{threshold}$ (e.g. 0.55), execute the trade.
   - If $P < \text{threshold}$, skip the trade.

## Triple-Barrier Method

Each trade entry sets three barriers:
- **Upper Barrier**: Take-profit limit (e.g. $+2 \times \text{ATR}$).
- **Lower Barrier**: Stop-loss limit (e.g. $-1 \times \text{ATR}$).
- **Vertical Barrier**: Maximum holding time horizon (e.g. 5 trading days or 390 minutes).
The label $y \in \{0, 1\}$ is 1 if the upper barrier was touched first before the lower or vertical barrier.

## Purged & Embargoed Cross-Validation

1. **Purging**: Remove training samples whose label window overlaps with any test sample's prediction window.
2. **Embargoing**: Drop an additional window of samples immediately following the test set to account for auto-correlation in equity returns.

## Verification Command
```bash
python -m pytest tests/test_phase4_ml_layer.py tests/test_learning.py -v
```
