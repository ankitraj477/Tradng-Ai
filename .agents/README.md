# Tradng-Ai Antigravity Customizations

This directory contains Antigravity plugins, rules, skills, MCP configurations, and lifecycle hooks purpose-built for the **Tradng-Ai** quantitative trading system.

## Installed Plugins

| Plugin Name | Type | Highlights & Capabilities |
| :--- | :--- | :--- |
| **`tradng-quant-guard`** | Rules, Hooks, Skills | Enforces zero look-ahead bias, statutory NSE transaction costs (`costs.py`), IST time boundaries, 0.05 tick size, and auto-runs safety tests. |
| **`sqlite-inspector`** | MCP Server, Skills | Connects `@modelcontextprotocol/server-sqlite` to `data/trader.db` for instant SQL inspection of paper trades, orders, and ledger. |
| **`quant-research-kit`** | Quant Skills | Runbooks for walk-forward cross-validation, Triple-Barrier ML meta-labeling, and benchmark comparisons against NIFTY 50. |
| **`multi-desk-ops`** | Rules, Ops Skills | Safe management of `run.py` (Intraday, Swing, F&O) with singleton lock adherence, heartbeat health checks, and exception counters. |
| **`cpp-scanner-toolchain`** | Build & Perf Skills | C++ build toolchain and latency benchmarking for `cpp/scanner.cpp` (<200ms screener). |
| **`dashboard-qa-tester`** | E2E Browser Skills | Browser subagent validation procedures for the real-time Flask multi-desk dashboard (`app/dashboard.py`). |

## Activation
These plugins are automatically discovered and active in both the **Antigravity IDE** and the **Antigravity App/CLI**.
