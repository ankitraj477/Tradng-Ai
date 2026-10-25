# STRATEGY_SPEC.md: Four-sleeve systematic strategy for Tradng-Ai (paper only)

Status date: 2026-10-23. Audience: a coding agent. Companion docs: `BUGS_v2.md` (R2-xxx), `BUGS.md` (BUG-xxx), `AUDIT_IMPROVEMENTS*.md`.
Goal: a validated, risk-budgeted multi-sleeve system. **No return target is promised.** Evidence first, capital never.

## 0. Rules for the agent
- Paper trading only. No broker order code, no credentials, no leverage above 1.0x equity, no naked short options.
- One milestone at a time (section 11). Stop and report at each acceptance gate. Do not skip gates.
- Every rate, lot size, expiry rule and threshold below lives in `config/strategy.json` with an `effective_from` date. Nothing hard-coded.
- Signals use only data available at the decision time (daily sleeves: decide after the close, fill at the next open).
- Every module ships with tests (section 10). Tests use temp paths and an injected clock.
- Never print or commit secrets. Do not touch `deploy.tar.gz`, `data/*.db` or the SSH key.

## 1. Gate 0: prerequisites (must be done before any sleeve work)
1. Auth fail-closed and no public bind without a token (R2-001). Remove the firewall-open rule or restrict it.
2. Disable `app/fno/`, `app/swing/`, `app/intraday/` desks behind `desks.enabled=false` (R2-002, R2-003, R2-004). Do not delete yet.
3. `.dockerignore` at repo root; remove `deploy.tar.gz` and DB files from git (R2-007, R2-008).
4. `ensure_account` must not reset silently (R2-009). Archive `data/trader.db`; start a clean paper account.
5. Positions keyed by `(sleeve, symbol)` with weighted average entry and cumulative entry cost (R2-006).
6. One risk path: every order proposal goes through `RiskManager.approve` (R2-005).

## 2. Verified market facts (web research, 2026-10-23; re-verify before use)
| Fact | Value | Config key |
|---|---|---|
| NIFTY lot size | 65 from the Jan 2026 series (was 75) | `contracts.NIFTY.lot` |
| BANKNIFTY lot size | 30, monthly expiry only (no weekly) | `contracts.BANKNIFTY.lot` |
| NIFTY expiry | Weekly on Tuesday (since 2025-09-01); monthly = last Tuesday; holiday moves expiry to the previous trading day | `contracts.NIFTY.expiry_weekday=TUE` |
| STT equity delivery | 0.1% both sides | `costs.stt.delivery` |
| STT equity intraday | 0.025% sell side | `costs.stt.intraday` |
| STT options | 0.15% of premium on the sell side (from 2026-04-01; was 0.1%) | `costs.stt.option_sell` |
| STT futures | 0.05% sell side (from 2026-04-01; was 0.02%) | `costs.stt.future_sell` |
| Other charges | brokerage, exchange transaction, SEBI, GST, stamp, DP: **load from broker/exchange schedules; `TODO_VERIFY`** | `costs.*` |
Context (SEBI FY26 studies): 87.7% of individual F&O traders lost money; only 0.5% of five-year traders were profitable every year; option sellers were the only group with positive median return but with fat-tail losses. Nifty200 Momentum 30 funds showed ~30% max drawdown. Treat consistency claims accordingly.

## 3. Data requirements
| Need | Spec | Used by |
|---|---|---|
| Daily OHLCV, split/bonus-adjusted, with `adjusted` flag and corporate-action log | NIFTY 200 members + Nifty 50 + NIFTYBEES (or index series), 2009-01 to date | A, B, C |
| Point-in-time constituents | Dated NIFTY 200 membership (monthly snapshots incl. removed names). **Refuse to seed from today's list.** | A, C |
| Liquidity | ADTV20 in INR, daily | A, C |
| India VIX daily | | A, D |
| Option chain snapshots | NIFTY, per day (EOD minimum): expiry, strike, type, bid, ask, last, IV, OI, volume, underlying | D |
| Event calendar | RBI MPC dates, Union Budget, index rebalance; config file | C, D |
| Holiday calendar | Official, multi-year; engine refuses to run if the year is not covered | all |
Storage: Parquet or DuckDB under `data/research/`. Validation tests: no gaps beyond holidays, no non-positive prices, monotonic dates, adjusted-close continuity across splits.

## 4. Shared engine contract
```python
@dataclass
class Proposal: sleeve: str; symbol: str; side: str; target_weight: float|None; qty: int|None
                stop: float|None; reason: str; asof: date          # decided at close of `asof`
def decide(sleeve_cfg, history_asof, portfolio_state, calendar) -> list[Proposal]   # pure, no I/O, no clock
```
- Live and backtest call the same `decide()` and the same `simulate_fill()`.
- Fills: next trading day open. Slippage: `max(5 bps, 0.1 * order_value/ADTV * 10000 bps)` per side, capped; reject orders above 2% of ADTV. Costs from `CostModel` using section 2 rates.
- Ledger: cash updates are deltas inside one transaction. Invariant: `cash + marked positions == start + realized - open entry costs`.
- Ownership: a symbol held by sleeve A cannot be opened by sleeve C.

## 5. Sleeve A: cross-sectional momentum (core, ~40% risk budget)
- **Universe:** PIT NIFTY 200 at the rebalance date. Eligible if ADTV20 >= `min_adtv_cr` (default 10 crore INR), price >= 50, history >= 260 days.
- **Score:** `MOM = (P[t-21] / P[t-252] - 1) / sigma252`, where `sigma252` is annualised stdev of daily returns over 252 days. Higher is better.
- **Select:** top `N=20`. Existing holdings are kept while their rank <= `keep_rank=30`.
- **Weights:** `w_i proportional to 1/sigma126_i`, cap 8%, normalised so `sum(w) = E`.
- **Regime exposure E:** 1.0 if Nifty 50 close >= SMA200 else 0.5 (parameter `bear_exposure`).
- **Rebalance:** first trading day after month end, signals at the prior close, fills at the open. Skip trades with `|delta w| < 1%`.
- **Risk exit:** daily close below `highest_close_since_entry - 2.5 * ATR20` -> exit next open.
- **Grid for robustness (not for optimisation):** lookback 126/189/252, N 15/20/30, keep_rank 25/30/40, bear_exposure 0.25/0.5/0.75.

## 6. Sleeve B: trend on the index (~20% risk budget)
- **Instrument:** NIFTYBEES (or Nifty 50 series for research). Long-only.
- **Entry:** close > highest close of the previous 55 days (excluding today) -> buy next open.
- **Exit:** close < lowest close of the previous 20 days -> sell next open.
- **Size:** `w = clamp(sigma_target / sigma20, 0, 1)` with `sigma_target = 10%` annualised; recomputed weekly.
- **Role:** drawdown control, not alpha. Judged on risk reduction (section 9).

## 7. Sleeve C: short-term mean reversion in uptrends (~15% risk budget)
- **Universe:** same as A; excluded if an earnings or event date falls within +/-3 trading days (if no data, log `event_data_missing` and trade at half size).
- **RSI2:** Wilder RSI, period 2. Define `RSI = 100` when average loss is 0 and `0` when average gain is 0 (never NaN).
- **Entry:** `close > SMA200` and `RSI2 < 10` and `close < SMA5`. Rank by lowest RSI2; fill free slots only.
- **Exit:** `RSI2 > 60` or `close > SMA5` or 5 trading days elapsed, at next open.
- **Stop:** close below `entry - 2 * ATR14` -> exit next open.
- **Size:** risk 0.5% of equity per trade `= 0.005 * equity / (2 * ATR14)` shares, notional cap 8% of equity. Max 10 positions.
- **Grid:** RSI threshold 5/10/15, exit RSI 50/60/70, max hold 3/5/7.

## 8. Sleeve D: defined-risk premium selling on NIFTY (<= 25% risk budget; chain data required)
- **Do not build until option-chain snapshots exist.** Without them, mark the sleeve `DISABLED` and fail closed.
- **Cycle:** choose the monthly expiry (last Tuesday) with 30-45 DTE. One iron condor per cycle, max 2 open.
- **Entry filters (all must pass):** IV rank over 252 days >= 50; ATM IV30 minus realised vol 20d > 0; India VIX 5-day change <= +20%; no event in the next 3 trading days; no open position in the same expiry.
- **Structure:** sell the call and put with absolute delta nearest 0.12 (allowed 0.10-0.16). Buy wings `W` points further out (`W` from config; try 50/100/150).
- **Risk rule:** `max_loss = (W - net_credit) * lot` must be <= 1% of the option sleeve's notional equity. Otherwise skip. Minimum `net_credit / W >= 0.15`.
- **Sleeve capital:** `option_notional_equity` in config (paper default 10,00,000 INR). With lot 65 and W=200, `max_loss` is about 10,000 INR, so 1% of equity requires about 10 lakh; at 1 lakh only very narrow wings fit.
- **Pricing/fills:** mark at mid; entry and exit fills cross half the quoted spread per leg.
- **Exits (first to trigger):** debit to close <= 50% of credit (take profit); debit >= 2x credit (stop); any short strike |delta| >= 0.30; DTE <= 3. No rolling, no adjustments, never hold into expiry day.
- **Costs per leg:** STT = `0.0015 * premium * qty` on every SELL transaction (shorts at entry, wings when closed); plus broker/exchange/GST/SEBI/stamp from config. Example: selling 65 units at a premium of 40 INR costs `0.0015 * 40 * 65 = 3.9 INR` STT.
- **Margin:** approximate as `max_loss`; compare against the broker margin calculator before any real use.
- **Never:** naked short, averaging down, selling more lots after a loss.

## 9. Portfolio and risk layer
| Control | Value |
|---|---|
| Gross equity exposure | <= 100% of equity; no leverage |
| Per-trade risk (to stop) | 0.5-1.0% equity (A uses weights; C uses 0.5%; D <= 1% of option notional) |
| Portfolio heat | <= 6% of equity |
| Sector cap | <= 25% of equity per sector |
| Daily loss | -2% -> no new entries for the rest of the day |
| Drawdown ladder | -5%: new position sizes x0.5; -10%: halt new entries until an audited manual reset |
| Sleeve drift switch | disable a sleeve if the last 30 closed trades' mean is below the backtest 5th-percentile bootstrap mean; log and alert |
| Data outage | stale or missing data for any held symbol > 15 minutes (intraday) or > 1 session (daily) -> alert; no new entries |
| Kill switch | `check_health` must be called each cycle; flatten uses explicit, logged prices |
Risk budgets are caps; unused budget stays in cash (or a configured liquid-fund yield).

## 10. Required tests (each must exist before a gate passes)
1. **No look-ahead:** shift every feature by +1 bar and assert signals change only as expected; include a deliberately leaky feature as a positive control that must be caught.
2. **Cost tests:** delivery STT on a 1,00,000 INR buy is 100 INR; option sell STT example in section 8; total costs reconcile to the ledger.
3. **Calendar tests:** last Tuesday of month; expiry moves to the previous trading day on a holiday; engine refuses uncovered years.
4. **Contract tests:** lot size lookup by effective date; BANKNIFTY weekly request raises.
5. **RSI2:** all-up and all-down series give 100 and 0; no NaN.
6. **Momentum:** hand-computed scores on a 5-stock fixture; rank buffer keeps holdings; weights respect the 8% cap and sum to `E`.
7. **PIT universe:** a removed stock appears before its removal date and not after.
8. **Ledger invariants:** property test over random trade sequences.
9. **Ownership:** two sleeves proposing the same symbol result in one position.
10. **Risk ladder:** drawdown -5% halves size; -10% blocks entries; reset requires an audited command.
11. **Live/backtest parity:** identical bars give identical proposals and fills through both paths.
12. **Sleeve D:** a condor violating the 1% rule is skipped; delta-breach and DTE exits fire; no expiry-day holding.
13. **Determinism:** same inputs, same outputs; no wall-clock or network in `decide()`.

## 11. Milestones and acceptance gates
| ID | Deliverable | Gate |
|---|---|---|
| M0 | Gate 0 prerequisites | all six items done; tests pass |
| M1 | Data layer + PIT universe + calendar + `config/strategy.json` | data validation tests pass; PIT test passes |
| M2 | Shared engine, cost model, ledger, risk layer | tests 2, 3, 8, 9, 10, 11, 13 pass |
| M3 | Sleeve A backtest + report | section 12 gates for A |
| M4 | Sleeves B and C backtests + reports | gates for B, C |
| M5 | Combined portfolio backtest | portfolio gates; sleeve return correlation matrix reported |
| M6 | Paper-forward run (>= 60 trading days for A/B/C) | live-vs-backtest drift within bands |
| M7 | Sleeve D (only with chain history/snapshots) | gates for D; >= 6 paper cycles |

## 12. Validation protocol and acceptance gates
- **Period:** 2010-01-01 to latest, with warm-up before. Costs and slippage always on. Parameters fixed before testing; grids only for robustness.
- **Baselines:** Nifty 50 buy-and-hold net (NIFTYBEES adjusted), equal-weight NIFTY 200 rebalanced monthly with costs, Nifty200 Momentum 30 (if data), random entries matched on turnover and holding period.
- **Report (per sleeve and combined):** net CAGR, annualised vol, Sharpe, Sortino, Calmar, max drawdown and duration, worst month, hit rate, average win/loss, profit factor, expectancy per trade, turnover, cost as % of gross, exposure, trade count, return by sub-period (2010-14, 2015-19, 2020-26) and by regime (Nifty above/below SMA200).
- **Statistics:** block bootstrap (block 20 days) 95% CIs for Sharpe and expectancy; log the number of configurations tried and report a deflated Sharpe or equivalent.
- **Robustness:** every parameter perturbed by +/-20% must keep net Sharpe >= 70% of the base and positive.

| Sleeve | Gate |
|---|---|
| A | Net Sharpe >= Nifty 50 buy-and-hold Sharpe + 0.15, or net CAGR >= +2%/yr over it; max drawdown <= 35%; positive net expectancy in at least 2 of 3 sub-periods; turnover and cost % reported; robustness passes |
| B | Max drawdown <= 70% of buy-and-hold's; CAGR >= 70% of buy-and-hold's; judged on risk reduction (small trade count is expected; report it) |
| C | >= 300 trades; expectancy per trade net of costs > 0 with bootstrap CI lower bound > 0; profit factor >= 1.3; worst trade <= 3R; average hold <= 5 days; robustness passes |
| D | >= 60 monthly-cycle equivalents of chain history (or state clearly that it is unaccepted); net expectancy per cycle > 0 with CI; largest single-cycle loss <= 1.2% of option notional; all exits and cost tests pass; paper-forward >= 6 cycles |
| Combined | Max drawdown <= 20% (target, reported honestly if missed); every sleeve individually accepted; no sleeve > 50% of total risk; costs under 30% of gross profit |
A failed gate means the sleeve is rejected or redesigned. Do not loosen a gate to pass it.

## 13. Repo mapping
| Task | Location |
|---|---|
| Config | `config/strategy.json` (new), loaded by one validated loader (reject missing keys) |
| Sleeves | `app/sleeves/{momentum,trend,meanrev,premium}.py` each exporting `decide()` |
| Engine | `app/engine_v2/{simulate,ledger,risk}.py`; reuse and fix `app/costs.py` rates |
| Data | `app/data/store.py` (extend), `app/universe_pit.py` (replace the CSV seeding with dated snapshots) |
| Reports | `reports/<sleeve>_<date>.md` generated by one script |
| Legacy | `app/fno/`, `app/swing/`, `app/intraday/` stay disabled until removed |

## 14. Out of scope
ML meta-labeling, news/event classifiers, intraday ORB, F&O futures/naked options, shorting stocks, any live execution. Revisit only after M5 passes and only with the same gates.

## 15. Open items to verify before go-live
Current charges schedule (brokerage, exchange, SEBI, GST, stamp, DP); NIFTY/BANKNIFTY lot sizes and expiry rules at the time of use; margin for defined-risk spreads; availability and licensing of option-chain history; ASM/GSM and event data sources.
