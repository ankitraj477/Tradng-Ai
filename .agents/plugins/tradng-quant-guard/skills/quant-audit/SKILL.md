---
name: quant-audit
description: Run an institutional audit on trading strategies, backtests, and execution components for look-ahead bias, cost accuracy, and accounting invariants.
---

# Quant Strategy & Invariant Audit Runbook

Use this skill when auditing any new trading strategy, modifying execution logic, or running compliance checks on Tradng-Ai components.

## Audit Checklist

### 1. Look-Ahead & Survivorship Bias Verification
1. Ensure the candidate selection uses historical date-indexed constituents from `app.universe_pit.PointInTimeUniverse`.
2. Inspect the signal generation method:
   - Check that `bars.iloc[-1]` represents a closed candle, or signals execute on `next_bar.open`.
   - Verify that indicators (e.g. 50 DMA, RSI, ATR) never calculate using future price indices (`shift(-1)` is strictly prohibited).
3. If walk-forward evaluation is used, verify an embargo window of at least `max_hold_days` or `max_hold_minutes` between training and testing sets.

### 2. NSE Cost Model Validation
1. Verify that all net returns subtract statutory charges via `app.costs.calculate_costs()`.
2. Ensure minimum base slippage (default: 5 to 8 bps) is incorporated.
3. Check both entry and exit legs:
   - Delivery trades must include STT on both buy and sell legs + DP charges (₹15.93) on sell.
   - Intraday trades must include STT on sell leg only.

### 3. Execution Invariant Testing
Execute the core safety and invariant test suite:
```bash
# Works on Windows and Linux / Oracle VM:
python -m pytest tests/test_audit_security_and_invariants.py tests/test_costs.py tests/test_exchange_rules_and_broker.py -v
```

### 4. Risk Gate Verification
Verify the following thresholds from `config/default.json` are respected:
- `max_position_risk_pct <= 0.02` (2% risk per position)
- `max_portfolio_heat_pct <= 0.06` (6% total open risk)
- `emergency_drawdown_pct <= 0.20` (kill switch trigger)
- `daily_loss_limit_pct <= 0.05` (daily circuit breaker)
