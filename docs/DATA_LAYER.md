# V5 data layer

The current official NIFTY 500 page provides a downloadable constituent CSV.
NIFTY 500 represents the top 500 companies based on full market capitalisation
from the eligible universe. The index is reviewed periodically, so the system
does not hard-code a permanent list.

## Workflow

1. Download the current NIFTY 500 constituent CSV from the official NSE/Nifty
   Indices page.
2. Run:
   `python scripts/update_universe.py <file>`
3. The provider loads symbols from `data/nifty500.csv`.
4. Market history is cached under `data/cache`.
5. If fresh data cannot be obtained, the live engine validates the data and
   refuses to trade rather than silently using stale prices.

## Historical data and corporate actions

V5 uses `auto_adjust=False` so raw OHLC data is not silently transformed.
Corporate-action-aware research must explicitly document whether adjusted or
unadjusted prices are used. Do not mix the two in a backtest.

A future data-quality phase should ingest split/bonus/dividend events into a
separate corporate-actions table and normalize historical datasets explicitly.

## Survivorship warning

The current constituent file is the current universe. It must NOT be used as
the historical universe for old backtests, because that creates survivorship
bias. Historical backtests need date-effective constituent snapshots.

## Current NIFTY 500 source

The official Nifty 500 page exposes an `Index Constituent` download and states
that the index represents the top 500 companies based on full market
capitalisation and average daily turnover from the eligible universe. The
repository's small CSV remains a development fixture; production/live mode
should use an officially downloaded constituent file and record its effective
 date in the dataset manifest.
