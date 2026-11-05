---
name: backtest-runner
description: Execute systematic strategy backtests, walk-forward cross-validation, and benchmark comparisons against NIFTY 50 in Tradng-Ai.
---

# Systematic Backtest & Walk-Forward Runner

Use this skill when running historical strategy simulations, evaluating new alphas, and generating quantitative performance tear-sheets for Tradng-Ai.

## Backtesting Workflow

### 1. Unified Decision Pipeline
Every backtest MUST execute the same decision logic that runs in paper execution:
```python
from app.pattern_strategies import decide
# decide(symbol, bars) returns a trade action, side, stop_loss, target, and confidence
```

### 2. Running Backtests via CLI
To test a strategy across the point-in-time universe:
```bash
python -m app.backtest --start-date 2023-01-01 --end-date 2026-01-01
```

Or run the walk-forward evaluation harness:
```bash
python -m pytest tests/test_walk_forward.py tests/test_backtest.py tests/test_phase1_research.py -v
```

### 3. Institutional Performance Metrics Checklist
When compiling results into an Antigravity artifact report, compute:
- **CAGR (%)**: Compound Annual Growth Rate over the test horizon.
- **Sharpe Ratio**: Annualized $(R_p - R_f) / \sigma_p$ (assume 6.5% Indian risk-free rate).
- **Sortino Ratio**: Annualized downside risk-adjusted return.
- **Max Drawdown (MDD %)**: Peak-to-trough decline of the equity curve.
- **Calmar Ratio**: $\text{CAGR} / |\text{Max Drawdown}|$.
- **Profit Factor**: Gross Profits / Gross Losses.
- **Win Rate (%)** and **Average Win / Average Loss Ratio**.
- **Statutory Costs Deducted**: Total STT, GST, Exchange txn fees, DP charges deducted.

### 4. Baseline Comparisons
Benchmark the strategy against:
1. `NIFTY 50 Buy & Hold` (`^NSEI`)
2. `Equal-Weight NIFTY 500`
3. `Random Entry Baseline` (same holding period and volatility sizing)
