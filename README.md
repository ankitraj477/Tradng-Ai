# Tradng-Ai: Institutional Quant Engine for Indian Equities

**Tradng-Ai** is an institutional-grade algorithmic research and paper-trading engine purpose-built for Indian National Stock Exchange (NSE) cash equities. Designed around rigorous quantitative finance principles, it eliminates survivorship and look-ahead biases, applies realistic regulatory transaction costs, and incorporates machine learning meta-labeling, event studies, and isolated risk management.

---

## Architecture Overview

```
                                      ┌─────────────────────────────────────────┐
                                      │        Data & Market Intelligence       │
                                      │   PIT Universe • Daily/Intraday Store   │
                                      │   Regimes (VIX/Breadth) • News Archive  │
                                      └────────────────────┬────────────────────┘
                                                           │
                                                           ▼
                                      ┌─────────────────────────────────────────┐
                                      │       Systematic Strategy Library       │
                                      │   Breakout • Pullback • Mean Reversion  │
                                      │      RS Momentum • Intraday ORB         │
                                      └────────────────────┬────────────────────┘
                                                           │
                                                           ▼
                                      ┌─────────────────────────────────────────┐
                                      │       ML Layer (Meta-Labeling)          │
                                      │    Triple-Barrier • Purged WF-CV        │
                                      │    Calibrated Probabilities (Take/Skip) │
                                      └────────────────────┬────────────────────┘
                                                           │
                                                           ▼
                                      ┌─────────────────────────────────────────┐
                                      │        Risk & Portfolio Engine          │
                                      │   Volatility Sizing • Heat Limiter      │
                                      │   Min Expected Move Gate • Kill Switch  │
                                      └────────────────────┬────────────────────┘
                                                           │
                                  ┌────────────────────────┴────────────────────────┐
                                  ▼                                                 ▼
               ┌─────────────────────────────────────┐           ┌─────────────────────────────────────┐
               │    Execution & Position Manager     │           │      Modern Fintech Dashboard       │
               │  Next-Bar Open • Gap-Aware Stops    │           │  Dark Terminal • Real-Time Metrics  │
               │  Isolated Worker • EOD Square-Off   │           │  SVG Equity Curve • Research Tabs   │
               └─────────────────────────────────────┘           └─────────────────────────────────────┘
```

---

## Core Quant Pillars (Phases 1–8)

### 1. Research Foundation
* **Point-in-Time Universe (`app/universe_pit.py`):** Uses dated index constituent snapshots to prevent survivorship bias in historical backtests.
* **Unified Decision Function (`app/pattern_strategies.py`):** The exact same `decide(symbol, bars)` pipeline governs both paper execution and walk-forward backtesting.
* **Realistic NSE Cost Model (`app/costs.py`):** Calculates exact delivery and intraday statutory charges: Brokerage, STT (0.1% delivery, 0.025% intraday sell), Exchange txn fee (0.00297%), SEBI turnover fee (0.0001%), GST (18%), Stamp duty, and DP charges.
* **Purged & Embargoed Walk-Forward Harness (`app/walk_forward.py`):** Evaluates rolling train/test splits with embargoes to prevent information leakage across trade horizons.
* **Baseline Benchmarks (`app/baselines.py`):** Every strategy is benchmarked against NIFTY 50 Buy-and-Hold, Equal-Weight NIFTY 500, and exposure-matched Random Entry baselines.

### 2. Market Analysis & Regimes
* **Macro Regime Engine (`app/regime.py`):** Classifies market climate using India VIX, NIFTY 50/200 DMA trend, market breadth (% of NIFTY 500 above 50 DMA, advance/decline ratio), and institutional net flow proxies.
* **Cross-Sectional Relative Strength (`app/relative_strength.py`):** Ranks candidate momentum vs NIFTY and sector indices over 20, 60, and 120-day windows.
* **Surveillance & Liquidity Filters (`app/eligibility.py`):** Excludes ASM/GSM surveillance list securities, illiquid symbols below minimum ADTV, and earnings-announcement dates.
* **Multi-Timeframe Bias (`app/multitimeframe.py`):** Macro daily structural levels dictate trade direction; lower timeframe bars only time entries.

### 3. Systematic Pattern Strategies
* **Donchian Breakout (`BreakoutStrategy`):** N-day channel breakout with volume confirmation and parameter plateau detection.
* **EMA Pullback (`EmaPullbackStrategy`):** Mean reversion to 20/50 EMAs within structural uptrends.
* **RSI-2 Mean Reversion (`RsiMeanReversionStrategy`):** Deep oversold pullbacks with ATR dynamic stops.
* **Relative Strength Momentum (`RelativeStrengthMomentumStrategy`):** Cross-sectional relative strength momentum rebalancing.
* **Parameter Stability (`app/grid_search.py`):** Optimization targets wide performance plateaus rather than overfitted peaks.

### 4. Machine Learning Layer (Meta-Labeling)
* **Triple-Barrier Labeling (`app/ml/labeling.py`):** Labels candidate setups with profit-taking, stop-loss, and holding horizon barriers.
* **Meta-Labeling Classifier (`app/ml/model.py`):** Rule-based strategies propose trades; the ML model predicts take/skip decisions and dynamic sizing multipliers.
* **Cross-Validation (`app/ml/cross_validation.py`):** Chronological `PurgedWalkForwardCV` with probability calibration.
* **Validation Evaluator (`app/ml/evaluator.py`):** Validates out-of-sample $\Delta \text{Expectancy}$ with 95% bootstrap confidence intervals.

### 5. News & Event Engine
* **Raw Event Archive (`app/news_archive.py`):** SHA-256 deduplicated archive with microsecond ingestion timestamps.
* **Exact Symbol Resolver (`app/symbol_resolver.py`):** Maps announcements to equities using ISINs and corporate alias tables (no ambiguous regex substring matching).
* **Event Classification (`app/event_classifier.py`):** Classifies news into taxonomy (results, order wins, M&A, regulatory, probe/fraud, credit rating) with sentiment and materiality scores.
* **Risk Gating & Event Study (`app/event_study.py`):** Blocks entries on regulatory probes and measures cumulative abnormal returns (CAR).

### 6. Risk & Portfolio Engine
* **Volatility Sizing (`app/risk_engine.py`):** Targets fixed portfolio risk percentage based on ATR volatility, bounded by sector exposure and correlation limits.
* **Minimum Expected Move Gate:** Rejects trade setups unless projected move is $\ge k \times$ round-trip transaction costs.
* **Strategy Drift Kill Switch:** Automatically suspends execution if live rolling expectancy falls below out-of-sample backtest lower bounds.

### 7. Learning Loop & Operations
* **Throttled Alert Manager (`app/ops/alerts.py`):** Category-throttled operational alerts for data outages, kill switch triggers, and drawdown breaches.
* **Candidate Log Retrainer (`app/ops/retrainer.py`):** Replaces heuristic weight tweaks with reproducible weekly retraining from `CandidateLog`.
* **Champion / Challenger Model Governance (`app/ops/champion_challenger.py`):** Shadow paper trading promotes challenger models only upon statistically verified superiority.
* **Isolated Protection Loop (`app/ops/protection_worker.py`):** Stop-loss management runs on an isolated thread, decoupled from data scrapers or network delays.

### 8. Intraday Timing & Execution
* **Session Timing Windows (`app/intraday/timing.py`):** Strict entry gating: 09:15–09:30 opening range blocked, entries permitted 09:30–14:45, compulsory EOD square-off before 15:15 IST.
* **Per-Session VWAP (`app/intraday/vwap.py`):** Clean session boundary reset at 09:15 IST with standard deviation bands.
* **Opening Range Breakout (`app/intraday/orb_strategy.py`):** 15-minute ORB strategy with time-of-day normalized volume and daily bias alignment.
* **Gap & Halt Execution Engine (`app/intraday/execution.py`):** Gap-aware fills at bar open during slippage gaps, circuit halt handling, and compulsory 15:10 IST liquidations.

---

## Web Dashboard Terminal

Tradng-Ai features a modern, responsive fintech SaaS terminal (`app/dashboard.py`):
* **Typography & Palette:** Inter & JetBrains Mono fonts on deep navy backgrounds (`#0B0E14` / `#151B28`).
* **Visual Performance Tracking:** Dynamic, zero-dependency SVG equity curves with peak markers.
* **Live System Metrics:** Real-time capital, unrealized P&L, regime badges, and operational status pills.
* **Research & Audit Tabs:** Interactive tabs for Active Positions, Closed Trades, Machine Learning metrics, News Event risk scores, and System Health.

---

## Quickstart Guide

### 1. Setup Environment
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run Test Suite
The entire test suite runs on isolated temporary and in-memory databases, keeping `data/` completely untainted:
```powershell
.venv\Scripts\python.exe -m pytest -q
```
*Expected output:* **`109 passed`** across all units and integration tests.

### 3. Launch Paper Trading Engine
```powershell
.venv\Scripts\python.exe -m app.engine
```

### 4. Launch Modern Terminal Dashboard
```powershell
.venv\Scripts\python.exe -m app.dashboard
```
Open **`http://localhost:5000`** in any web browser.

---

## Project Structure

```
Tradng-Ai/
├── app/
│   ├── candidate_log.py          # Feature snapshot database for ML training
│   ├── costs.py                  # Statutory NSE delivery & intraday cost model
│   ├── dashboard.py              # Modern SaaS terminal web interface
│   ├── engine.py                 # Core paper trading execution loop
│   ├── multitimeframe.py         # Daily bias and time-of-day normalized volume
│   ├── pattern_strategies.py     # Rule-based Donchian, EMA, RSI, and RS strategies
│   ├── position_manager.py       # Trailing stop and exit management
│   ├── regime.py                 # India VIX and market breadth regime classifier
│   ├── relative_strength.py      # Cross-sectional relative strength rankings
│   ├── risk_engine.py            # Volatility sizing, cost gates, and kill switch
│   ├── intraday/                 # Phase 8: Intraday timing, VWAP, ORB & execution
│   ├── ml/                       # Phase 4: Triple barrier, meta-labeling & CV
│   └── ops/                      # Phase 7: Alerts, retrainer, champion/challenger
├── config/                       # Market holiday tables and default risk configs
├── tests/                        # 46 test modules (109 passing tests)
├── requirements.txt              # Pinned core dependencies
└── README.md                     # Technical architecture documentation
```

---

## Operational Safety & Risk Rules

1. **Strictly Paper Only:** Zero real-money broker order endpoints. All fills simulate real exchange mechanics (next-bar open, gap slippage, and circuit freeze handling).
2. **Deterministic Risk Budgeting:** Maximum position risk is capped at 2% of equity; total portfolio exposure is capped at 85%.
3. **Emergency Kill Switch:** Any drawdown exceeding 20% or persistent rolling strategy degradation immediately halts new orders.