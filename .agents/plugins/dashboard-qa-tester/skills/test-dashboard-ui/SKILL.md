---
name: test-dashboard-ui
description: Test and validate the Tradng-Ai real-time multi-desk dashboard (tabs, toggles, emergency kill switch, SSE streams) using browser automation.
---

# Dashboard E2E Testing & UI Verification

Use this skill when testing or refactoring the Flask dashboard ([app/dashboard.py](file:///c:/Users/KIIT/Desktop/projects/Tradng-Ai/app/dashboard.py)).

## Test Target
- **URL**: `http://127.0.0.1:5000` (or `APP_PORT` from `.env`)
- **Key Tabs**:
  1. `Intraday Desk` (MIS positions, day PnL, active bracket orders)
  2. `Swing Desk` (CNC positions, target trailing, holding days)
  3. `F&O Desk` (Options spreads, breakeven decay, max risk)
  4. `System & Accounting` (Cash ledger, statutory fees breakdown, capital utilization)

## Browser Subagent Verification Procedure

When testing the UI, launch Antigravity's `browser_subagent` to execute these checks:

1. **Start Dashboard Server** (if not already running):
   ```bash
   python run_dashboard.py
   ```
2. **Navigate**: Open `http://127.0.0.1:5000`.
3. **Verify Header Elements**:
   - Total Portfolio Equity counter
   - Today's PnL indicator (Green/Red styling)
   - Auto-Trading toggle button
   - Emergency Kill Switch button
4. **Interact with Desk Tabs**:
   - Click each tab and assert table headers and SVG charts render without JavaScript console errors.
5. **Verify Safety Invariant**:
   - Assert that triggering the Emergency Kill Switch triggers a confirmation modal before dispatching `/api/emergency_kill`.

## Unit Test Regression Command
```bash
python -m pytest tests/test_auto_trading_toggle.py tests/test_dashboard_accounting_v8.py -v
```
