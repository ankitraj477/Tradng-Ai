# Backtesting rules

V4 uses an event-driven bar-by-bar approach.

## Anti-lookahead rules
- Indicators are computed only from historical bars.
- A trade decision is made at the current bar using information available through that bar.
- No future close/high/low is used to generate the same-bar signal.
- Walk-forward testing keeps test windows separate from prior training windows.
- Results must include slippage and fees.

## What V4 does not claim
A backtest is not proof of future profitability. Free historical data may contain survivorship, corporate-action, timestamp, or completeness limitations. A serious experiment should record the data source and period for every run.

## Required validation
Before trusting a strategy:
1. Backtest.
2. Walk-forward test.
3. Compare with NIFTY 50 buy-and-hold.
4. Test multiple market regimes.
5. Paper trade prospectively.
6. Only compare strategies after transaction costs.
