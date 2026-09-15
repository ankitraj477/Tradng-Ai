
Run demo:
`python scripts/seed_demo.py`

Run backtest:
`python scripts/run_backtest.py`

Run tests:
`python -m pytest`

The system remains paper-trading-only. No broker execution exists.



## Stabilization audit result

The stabilization pass and second correction pass have been completed. The repository now has:
- deterministic demo data with stable quotes/history,
- persistent SQLite in-memory test handling,
- lazy optional yfinance import,
- corrected NIFTY 500 provider wiring,
- compounding-aware portfolio sizing,
- enforced basic risk vetoes,
- correct long/short stop-direction handling,
- duplicate-position protection,
- next-bar-open backtest entries,
- conservative same-bar stop/target handling,
- and a passing automated test suite.

Validation:
`python -m compileall -q app scripts tests`
`python -m pytest -q` → 7 passed

Validation after correction pass: `python -m pytest -q` → 10 passed.
