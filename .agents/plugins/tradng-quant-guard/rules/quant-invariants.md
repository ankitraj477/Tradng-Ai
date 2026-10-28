# Tradng-Ai Quant & Regulatory Invariants

Every modification to the trading algorithms, execution pipelines, and backtesting harnesses must strictly respect the following quantitative principles:

## 1. Zero Look-Ahead Bias & Information Leakage
- **Bar Completion**: Trading signals and decision algorithms (`app.pattern_strategies.decide()`, `app.scanner.scan()`) must ONLY evaluate completed, closed bars. Never use the high, low, or close of a bar that has not finished forming.
- **Point-in-Time Constituent Masking**: Historical universe selection must use dated historical snapshots from `app/universe_pit.py` to prevent survivorship bias. Never evaluate an asset in 2023 based on whether it is a NIFTY 500 member in 2026.
- **Walk-Forward Embargoes**: When performing train/test splits (`app/walk_forward.py`), always apply an embargo window equal to or greater than the maximum holding period (`max_hold_days` or `max_hold_minutes`) to prevent trade spillover leakage across fold boundaries.

## 2. Indian National Stock Exchange (NSE) Market Conventions
- **Timezones & Calendar**: All market scheduling, bar indexing, and daily boundary rolls MUST use Indian Standard Time (`Asia/Kolkata` or `ZoneInfo("Asia/Kolkata")`). Do not rely on UTC for day roll-overs (BUG-047 fix).
- **Market Hours**: Cash equity trading hours are strictly 09:15:00 to 15:30:00 IST, Monday through Friday, excluding NSE exchange holidays (`app/market_calendar.py`).
- **Tick Size**: Indian equities trade in tick sizes of ₹0.05. Order prices, limit stops, and limit targets must be rounded to the nearest ₹0.05 multiple (`round(price * 20.0) / 20.0`).
- **Circuit Filters**: Stocks nearing upper or lower price circuit limits (5%, 10%, 20%) must be disqualified from entering new momentum breakouts (`app/eligibility.py`).

## 3. Statutory Regulatory Cost Model
- **No Frictionless Backtests**: Never backtest or simulate paper trades with 0% slippage or 0 fees. All trade calculations must route through `app.costs.calculate_costs()`.
- **Statutory Charges**:
  - Delivery (CNC): STT 0.1% on buy and sell, Stamp Duty 0.015%, Exchange fee 0.00297%, SEBI turnover fee 0.0001%, GST 18% on (brokerage + exchange fee + SEBI fee), DP charges ₹15.93 per scrip debit.
  - Intraday (MIS): STT 0.025% on sell only, Stamp Duty 0.003%, Exchange fee 0.00297%, SEBI fee 0.0001%, GST 18%.
  - Slippage: Minimum base slippage buffer of 5 to 8 bps.

## 4. Paper-Trading & Execution Isolation
- **Paper Execution by Default**: All desk runners (`run_intraday.py`, `run_swing.py`, `run_fno.py`) and unified execution threads must operate in paper simulation mode against virtual accounts unless an authenticated live broker session is explicitly configured.
- **Single Instance Guard**: Only one engine process can hold the database lock at any time (`SingleInstanceLock`). Do not bypass lock verification.
- **Emergency Kill Switch**: If portfolio drawdown crosses `emergency_drawdown_pct` (20%) or daily loss reaches `daily_loss_limit_pct` (5%), all active desks must halt new entries immediately.
