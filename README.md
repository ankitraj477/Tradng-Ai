# AI Indian Stock Market Paper Trader — V10.1

A lightweight, paper-only Indian stock trading experiment targeting ₹1,000 → ₹1,00,000. This is an experiment, not a profit guarantee.

## V10.1 — Runtime Readiness & Adaptive Selection

V10 hardens the system for long-running public-data operation:

- paper trading only — no broker execution
- long + intraday short simulation
- canonical portfolio accounting
- reserved short margin without double counting
- 5-minute decision cycle during NSE regular hours
- NSE 2026 holiday awareness
- bounded public-data retries + local cache fallback
- OHLCV data-quality checks
- batch history scanning when supported
- live-mode NIFTY 500 universe readiness gate
- daily-loss + max-drawdown protection
- trailing stops, time exits and kill switch
- dashboard with P&L, exposure, margin, holdings, last trades and AI decisions
- persistent SQLite state and crash-friendly operation
- backtesting, walk-forward testing and benchmark utilities

## Quick start

Install dependencies:

`pip install -r requirements.txt`

Run tests:

`python -m pytest -q`

Run deterministic demo:

`python scripts/seed_demo.py`

Run backtest:

`python scripts/run_backtest.py`

Run dashboard + engine in demo mode:

`python -m app`

Run live-data paper mode:

`python -m app --live`

### Important before `--live`

The repository includes only a small starter universe so that tests/demo remain lightweight. The live engine intentionally refuses to trade until `data/nifty500.csv` contains at least 450 active constituents.

Get the current NIFTY 500 constituent file from the official Nifty Indices page, normalize it to:

`symbol, company, sector, industry`

and update it with:

`python scripts/update_universe.py path/to/nifty500.csv`

## Safety model

The AI can choose trade direction and sizing proposal, but the Risk Manager can veto every trade. Learning may adjust bounded strategy weights only; it cannot change hard risk or execution rules.

No real-money broker API, order endpoint, or credential is included.

## Project history

- V1: core paper-trading engine/dashboard
- V2: NIFTY universe loader + dashboard
- V3: controlled learning + news + long/short execution
- V4: backtesting + benchmarks + walk-forward
- V5: data layer + cache + manifest
- V6: market intelligence + regime/news-aware AI
- V6.1: short-path and accounting integration corrections
- V7: trailing protection + long-running execution
- V7.1: canonical accounting + exposure/margin + daily-loss/drawdown hardening
- V8: live readiness, market calendar, data resilience, batch scanning and accounting corrections
- V9: bounded regime-aware learning and portfolio-aware selection
- V10.1: fixed direct preflight invocation; runtime preflight, Yahoo 5m lookback correction, stable paths and end-to-end selection integration

### V10 startup preflight
The application validates required Python dependencies, database path, paper-only execution, and (in live mode) the NIFTY 500 universe before starting. Set `REQUIRE_PREFLIGHT=false` only for a controlled development environment.
