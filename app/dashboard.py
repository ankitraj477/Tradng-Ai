from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string

from .accounting import portfolio_metrics
from .market_hours import market_phase, now_ist, holiday_name
from .learning import LearningEngine
from .runtime import preflight


HTML = r"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Tradng-Ai · Institutional Terminal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #06090f;
            --bg-surface: #0c121e;
            --bg-card: #10192a;
            --bg-card-subtle: rgba(16, 25, 42, 0.6);
            --border: rgba(255, 255, 255, 0.08);
            --border-subtle: rgba(255, 255, 255, 0.04);
            --border-active: rgba(56, 189, 248, 0.4);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-faint: #475569;
            --emerald: #10b981;
            --emerald-bg: rgba(16, 185, 129, 0.12);
            --rose: #f43f5e;
            --rose-bg: rgba(244, 63, 94, 0.12);
            --cyan: #38bdf8;
            --cyan-bg: rgba(56, 189, 248, 0.12);
            --indigo: #6366f1;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --radius-lg: 16px;
            --radius-md: 12px;
            --radius-sm: 8px;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: var(--font-sans);
            background: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
            padding-bottom: max(32px, env(safe-area-inset-bottom));
        }

        /* Top Header */
        header {
            background: rgba(12, 18, 30, 0.88);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 50;
        }
        .header-inner {
            max-width: 1400px;
            margin: 0 auto;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .logo-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, var(--cyan), var(--indigo));
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-family: var(--font-mono);
            font-size: 13px;
            color: #fff;
            box-shadow: 0 0 14px rgba(56, 189, 248, 0.3);
            flex-shrink: 0;
        }
        .brand-text h1 {
            font-size: 15px;
            font-weight: 700;
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .brand-badge {
            background: var(--cyan-bg);
            border: 1px solid rgba(56, 189, 248, 0.25);
            color: var(--cyan);
            font-size: 10px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: var(--font-mono);
        }
        .header-meta {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .pulse-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
            background: var(--emerald-bg);
            color: var(--emerald);
            border: 1px solid rgba(16, 185, 129, 0.25);
            white-space: nowrap;
        }
        .pulse-dot {
            width: 7px;
            height: 7px;
            background: var(--emerald);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--emerald);
            animation: pulse 2s infinite ease-in-out;
            flex-shrink: 0;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(0.9); opacity: 0.7; }
            50% { transform: scale(1.25); opacity: 1; }
        }

        /* Main Container */
        main {
            max-width: 1400px;
            margin: 0 auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        /* Segmented Navigation Tabs */
        .tabs-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
            padding-bottom: 2px;
        }
        .tabs-wrapper::-webkit-scrollbar { display: none; }
        .tabs {
            display: inline-flex;
            background: var(--bg-surface);
            padding: 3px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border);
            gap: 4px;
        }
        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-family: var(--font-sans);
            font-size: 13px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 9px;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }
        .tab-btn:hover { color: var(--text-main); }
        .tab-btn.active {
            color: #fff;
            background: var(--bg-card);
            border: 1px solid var(--border);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        }

        /* Hero Portfolio Summary Card */
        .hero-card {
            background: linear-gradient(180deg, #121c2e 0%, var(--bg-card) 100%);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
            position: relative;
            overflow: hidden;
        }
        .hero-card::after {
            content: '';
            position: absolute;
            top: 0; right: 0;
            width: 280px; height: 180px;
            background: radial-gradient(circle at top right, rgba(56, 189, 248, 0.08), transparent 70%);
            pointer-events: none;
        }
        .hero-top {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
        }
        .hero-equity-label {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        .hero-equity-val {
            font-family: var(--font-mono);
            font-size: clamp(28px, 5vw, 42px);
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }
        .hero-badges {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        /* Hero Key Metric Grid inside Card */
        .hero-stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 14px;
            padding-top: 16px;
            border-top: 1px solid var(--border-subtle);
        }
        .stat-item {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .stat-label {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-faint);
        }
        .stat-val {
            font-family: var(--font-mono);
            font-size: 17px;
            font-weight: 700;
            color: var(--text-main);
        }
        .stat-sub {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--text-muted);
        }

        /* Exposure Bar Strip */
        .exposure-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 10px;
        }
        .exposure-pill {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 10px 14px;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .exposure-pill .label {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-faint);
            letter-spacing: 0.04em;
        }
        .exposure-pill .val {
            font-family: var(--font-mono);
            font-size: 15px;
            font-weight: 700;
        }

        /* Target Progression & Equity Sparkline */
        .chart-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }
        .chart-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .chart-title {
            font-size: 14px;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .progress-bar-bg {
            height: 6px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 999px;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--cyan), var(--emerald));
            border-radius: 999px;
            transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .chart-box {
            width: 100%;
            height: 140px;
            position: relative;
        }
        svg.equity-svg {
            width: 100%;
            height: 100%;
            overflow: visible;
        }

        /* Two Column Desk Layout */
        .two-col {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }
        @media (max-width: 900px) {
            .two-col { grid-template-columns: 1fr; }
        }

        /* Panels */
        .panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }
        .panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .panel-title {
            font-size: 14px;
            font-weight: 600;
            letter-spacing: -0.01em;
            color: var(--text-main);
        }

        /* Responsive Scrollable Tables */
        .table-responsive {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            max-height: 340px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-subtle);
        }
        table.fin-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12.5px;
            min-width: 580px;
        }
        table.fin-table th {
            text-align: left;
            padding: 9px 12px;
            font-size: 10.5px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-faint);
            border-bottom: 1px solid var(--border);
            background: var(--bg-surface);
            position: sticky;
            top: 0;
            z-index: 5;
        }
        table.fin-table td {
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            white-space: nowrap;
            color: var(--text-muted);
        }
        table.fin-table tr:last-child td {
            border-bottom: none;
        }
        table.fin-table tr:hover td {
            background: rgba(255, 255, 255, 0.02);
            color: var(--text-main);
        }
        table.fin-table td.ticker {
            font-family: var(--font-mono);
            font-weight: 600;
            color: var(--text-main);
        }

        /* Financial Badges & Pills */
        .pill {
            display: inline-flex;
            align-items: center;
            font-family: var(--font-mono);
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 6px;
            letter-spacing: 0.02em;
            line-height: 1.2;
        }
        .pill-long {
            background: var(--emerald-bg);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .pill-short {
            background: var(--rose-bg);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.3);
        }
        .pill-win { color: var(--emerald); font-weight: 600; }
        .pill-loss { color: var(--rose); font-weight: 600; }
        .pill-cyan {
            background: var(--cyan-bg);
            color: var(--cyan);
            border: 1px solid rgba(56, 189, 248, 0.25);
        }
        .pill-muted {
            background: rgba(148, 163, 184, 0.08);
            color: var(--text-muted);
            border: 1px solid rgba(148, 163, 184, 0.18);
        }

        /* Market Intel Mini Grid */
        .intel-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 10px;
        }
        .intel-item {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 10px 12px;
        }
        .intel-item .title {
            font-size: 10px;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-faint);
            margin-bottom: 4px;
            letter-spacing: 0.04em;
        }
        .intel-item .val {
            font-size: 13.5px;
            font-weight: 600;
            color: var(--text-main);
        }

        .empty-state {
            padding: 28px 16px;
            text-align: center;
            color: var(--text-faint);
            font-size: 12.5px;
        }

        /* Mobile Adjustments */
        @media (max-width: 640px) {
            header .header-inner { padding: 10px 14px; }
            main { padding: 12px 14px; gap: 14px; }
            .hero-card { padding: 18px 16px; gap: 16px; }
            .hero-stats-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
            .exposure-strip { grid-template-columns: 1fr 1fr; }
            .panel { padding: 16px 14px; }
            .chart-card { padding: 16px 14px; }
            .chart-box { height: 110px; }
            #clock { display: none; }
        }
    </style>
</head>
<body>

<header>
    <div class="header-inner">
        <div class="brand">
            <div class="logo-icon">AI</div>
            <div class="brand-text">
                <h1>Tradng-Ai <span class="brand-badge">PRO v10.2</span></h1>
            </div>
        </div>
        <div class="header-meta">
            <div id="pulse-box" class="pulse-indicator">
                <span class="pulse-dot"></span>
                <span id="market-phase-badge">MARKET CHECKING</span>
            </div>
            <div id="clock" class="stat-label" style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);">--:--:-- IST</div>
        </div>
    </div>
</header>

<main>
    <!-- Segmented Navigation Tabs -->
    <div class="tabs-wrapper">
        <div class="tabs">
            <button id="tab-live-btn" class="tab-btn active" onclick="switchTab('live')">Live Desk & Portfolio</button>
            <button id="tab-research-btn" class="tab-btn" onclick="switchTab('research')">Quant Research & Baselines</button>
        </div>
    </div>

    <!-- TAB 1: LIVE DESK -->
    <div id="tab-live" style="display:flex; flex-direction:column; gap:16px;">
        <!-- Unified Hero Portfolio Card -->
        <div class="hero-card">
            <div class="hero-top">
                <div>
                    <div class="hero-equity-label">Total Portfolio Equity</div>
                    <div id="val-portfolio" class="hero-equity-val">₹0.00</div>
                </div>
                <div class="hero-badges">
                    <span id="return-badge" class="pill pill-cyan">0.00%</span>
                    <span id="pnl-status-pill" class="pill pill-muted">NET</span>
                </div>
            </div>

            <!-- Vital Stats Row -->
            <div class="hero-stats-grid">
                <div class="stat-item">
                    <span class="stat-label">Available Cash</span>
                    <span id="val-cash" class="stat-val">₹0.00</span>
                    <span class="stat-sub">Margin: <span id="val-margin">₹0.00</span></span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Realized P&L</span>
                    <span id="val-pnl" class="stat-val">₹0.00</span>
                    <span class="stat-sub">Unrealized: <span id="val-unrealized">₹0.00</span></span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Current Drawdown</span>
                    <span id="val-dd" class="stat-val" style="color:var(--rose)">0.00%</span>
                    <span class="stat-sub">Peak: <span id="val-peak">₹0.00</span></span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Target Capital</span>
                    <span id="val-target" class="stat-val">₹1,00,000.00</span>
                    <span id="progress-percent" class="stat-sub" style="color:var(--cyan);font-weight:600;">0.00% of Goal</span>
                </div>
            </div>
        </div>

        <!-- Secondary Exposure Metric Strip -->
        <div class="exposure-strip">
            <div class="exposure-pill">
                <span class="label">Gross Exposure</span>
                <span id="val-gross" class="val">₹0.00</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Net Exposure</span>
                <span id="val-net" class="val">₹0.00</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Long Notional</span>
                <span id="val-long" class="val" style="color:var(--emerald)">₹0.00</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Short Notional</span>
                <span id="val-short" class="val" style="color:var(--rose)">₹0.00</span>
            </div>
        </div>

        <!-- Performance Sparkline Card -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">Equity Growth & Target Progression</div>
            </div>
            <div class="progress-bar-bg">
                <div id="progress-fill" class="progress-bar-fill" style="width:0%"></div>
            </div>
            <div class="chart-box">
                <svg id="equity-svg" class="equity-svg" viewBox="0 0 1000 140" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="#10b981" stop-opacity="0.28"/>
                            <stop offset="100%" stop-color="#10b981" stop-opacity="0.0"/>
                        </linearGradient>
                    </defs>
                    <path id="equity-area" fill="url(#eq-grad)" d=""/>
                    <path id="equity-line" fill="none" stroke="#10b981" stroke-width="2.2" d=""/>
                </svg>
            </div>
        </div>

        <!-- Two Column Desk: Holdings & Executions -->
        <div class="two-col">
            <!-- Open Holdings -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Active Market Holdings</div>
                    <span id="pos-count" class="brand-badge">0 OPEN</span>
                </div>
                <div class="table-responsive">
                    <table class="fin-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Qty</th>
                                <th>Entry</th>
                                <th>Current</th>
                                <th>Stop</th>
                                <th>Target</th>
                                <th>Age</th>
                            </tr>
                        </thead>
                        <tbody id="positions-body">
                            <tr><td colspan="8" class="empty-state">No open positions in active cycle.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Closed Trades -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Recent Executions</div>
                    <span id="trade-count" class="brand-badge">LAST 10 TRADES</span>
                </div>
                <div class="table-responsive">
                    <table class="fin-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Fill / Exit</th>
                                <th>Net P&L</th>
                                <th>Return</th>
                                <th>Time</th>
                                <th>Reason</th>
                            </tr>
                        </thead>
                        <tbody id="trades-body">
                            <tr><td colspan="7" class="empty-state">No execution records logged yet.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Two Column Desk: AI Decisions & Market Intel -->
        <div class="two-col">
            <!-- AI Proposer Stream -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">AI Decision Stream</div>
                    <span class="pill pill-cyan">AUDIT LOG</span>
                </div>
                <div class="table-responsive">
                    <table class="fin-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Action</th>
                                <th>Confidence</th>
                                <th>Strategy</th>
                                <th>Gate</th>
                                <th>Rationale</th>
                            </tr>
                        </thead>
                        <tbody id="decisions-body">
                            <tr><td colspan="6" class="empty-state">Awaiting next decision cycle...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Market Intelligence & Adaptive Weights -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Market Regime & System Health</div>
                    <span id="nifty-badge" class="brand-badge">NIFTY 50</span>
                </div>
                <div class="intel-grid">
                    <div class="intel-item">
                        <div class="title">Regime</div>
                        <div id="intel-regime" class="val">--</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">Sentiment</div>
                        <div id="intel-sentiment" class="val">--</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">Phase</div>
                        <div id="intel-phase" class="val">--</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">Pipeline</div>
                        <div id="intel-pipeline" class="val">--</div>
                    </div>
                </div>
                <div style="margin-top:6px;">
                    <div class="stat-label" style="margin-bottom:6px;">Strategy Calibration Weights</div>
                    <div id="learning-weights-container" style="display:flex;flex-wrap:wrap;gap:6px;">
                        <span class="pill pill-muted">Initializing adaptive weights...</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 2: QUANT RESEARCH & BASELINES -->
    <div id="tab-research" style="display:none; flex-direction:column; gap:16px;">
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">Phase 1 Quantitative Research Foundation</div>
                <span class="pill pill-long">VALIDATED</span>
            </div>
            <p style="font-size:13px; color:var(--text-muted); line-height:1.6;">
                Institutional research engine with survivorship-bias-free point-in-time universe, unified execution decision logic,
                realistic NSE regulatory cost deductions, and out-of-sample walk-forward validation.
            </p>
        </div>

        <div class="exposure-strip">
            <div class="exposure-pill">
                <span class="label">Decision Alignment</span>
                <span class="val" style="color:var(--emerald);font-size:14px;">100% UNIFIED</span>
            </div>
            <div class="exposure-pill">
                <span class="label">NSE Cost Model</span>
                <span class="val" style="color:var(--cyan);font-size:14px;">EXACT CHARGES</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Data Store</span>
                <span class="val" style="color:var(--indigo);font-size:14px;">SPLIT-ADJUSTED</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Constituent Tracking</span>
                <span class="val" style="color:var(--emerald);font-size:14px;">POINT-IN-TIME</span>
            </div>
        </div>

        <div class="two-col">
            <div class="panel">
                <div class="panel-title">Institutional Benchmarks</div>
                <div style="font-size:12.5px; color:var(--text-muted); line-height:1.5; margin-top:2px;">
                    Strategies are held to strict acceptance standards: they must beat all 3 baselines out-of-sample after real costs.
                </div>
                <div class="intel-grid" style="margin-top:10px;">
                    <div class="intel-item">
                        <div class="title">NIFTY 50 Benchmark</div>
                        <div class="val" style="color:var(--cyan);">Buy & Hold (Net)</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">NIFTY 500 Benchmark</div>
                        <div class="val" style="color:var(--indigo);">Equal-Weight</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">Random Baseline</div>
                        <div class="val" style="color:var(--rose);">Zero-Edge (≤0)</div>
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-title">Walk-Forward Validation Harness</div>
                <div style="font-size:12.5px; color:var(--text-muted); line-height:1.5; margin-top:2px;">
                    Purged & embargoed rolling windows eliminate lookahead bias and train/test leakage.
                </div>
                <div class="intel-grid" style="margin-top:10px;">
                    <div class="intel-item">
                        <div class="title">Annualized Sharpe</div>
                        <div class="val">√252 on Daily Returns</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">Downside Risk</div>
                        <div class="val">Sortino + Max Drawdown</div>
                    </div>
                    <div class="intel-item">
                        <div class="title">Confidence Interval</div>
                        <div class="val">95% Bootstrap CI</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</main>

<script>
const formatMoney = val => '₹' + Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatPct = val => (Number(val || 0) >= 0 ? '+' : '') + Number(val || 0).toFixed(2) + '%';

function switchTab(tab) {
    document.getElementById('tab-live').style.display = (tab === 'live') ? 'flex' : 'none';
    document.getElementById('tab-research').style.display = (tab === 'research') ? 'flex' : 'none';
    document.getElementById('tab-live-btn').className = 'tab-btn' + (tab === 'live' ? ' active' : '');
    document.getElementById('tab-research-btn').className = 'tab-btn' + (tab === 'research' ? ' active' : '');
}

function renderEquityCurve(points) {
    if (!points || points.length < 2) return;
    const values = points.map(p => Number(p.value || p));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;
    const w = 1000;
    const h = 140;
    const pad = 8;

    const coords = values.map((v, i) => {
        const x = (i / (values.length - 1)) * w;
        const y = h - pad - ((v - min) / range) * (h - 2 * pad);
        return [x, y];
    });

    const pathData = coords.reduce((acc, [x, y], idx) => `${acc} ${idx === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`, '');
    const areaData = `${pathData} L ${w} ${h} L 0 ${h} Z`;

    const lineEl = document.getElementById('equity-line');
    const areaEl = document.getElementById('equity-area');
    if (lineEl && areaEl) {
        lineEl.setAttribute('d', pathData);
        areaEl.setAttribute('d', areaData);
        const lastVal = values[values.length - 1];
        const firstVal = values[0];
        const strokeColor = lastVal >= firstVal ? '#10b981' : '#f43f5e';
        lineEl.setAttribute('stroke', strokeColor);
    }
}

async function updateDashboard() {
    try {
        const res = await fetch('/api/state', { cache: 'no-store' });
        if (!res.ok) return;
        const data = await res.json();

        // Header and Clock
        const clockEl = document.getElementById('clock');
        if (clockEl) clockEl.textContent = new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST';
        const phase = data.market_phase || 'MARKET CLOSED';
        document.getElementById('market-phase-badge').textContent = phase.toUpperCase();

        // Hero Metric Cards
        document.getElementById('val-portfolio').textContent = formatMoney(data.portfolio);
        document.getElementById('val-target').textContent = formatMoney(data.target);
        document.getElementById('val-cash').textContent = formatMoney(data.available_cash);
        document.getElementById('val-margin').textContent = formatMoney(data.reserved_margin);
        document.getElementById('val-pnl').textContent = formatMoney(data.realized);
        document.getElementById('val-unrealized').textContent = formatMoney(data.unrealized);
        document.getElementById('val-dd').textContent = Number(data.drawdown || 0).toFixed(2) + '%';
        document.getElementById('val-peak').textContent = formatMoney(data.peak);

        const ret = Number(data.return_pct || 0);
        const retEl = document.getElementById('return-badge');
        retEl.textContent = formatPct(ret);
        retEl.className = 'pill ' + (ret >= 0 ? 'pill-long' : 'pill-short');

        const pnlStatus = document.getElementById('pnl-status-pill');
        const realizedPnl = Number(data.realized || 0);
        pnlStatus.textContent = realizedPnl >= 0 ? 'PROFIT' : 'LOSS';
        pnlStatus.className = 'pill ' + (realizedPnl >= 0 ? 'pill-long' : 'pill-short');

        // Secondary Metrics
        document.getElementById('val-gross').textContent = formatMoney(data.gross_exposure);
        document.getElementById('val-net').textContent = formatMoney(data.net_exposure);
        document.getElementById('val-long').textContent = formatMoney(data.long_value);
        document.getElementById('val-short').textContent = formatMoney(data.short_notional);

        // Target Progression
        const prog = Math.max(0, Math.min(100, Number(data.progress || 0)));
        document.getElementById('progress-fill').style.width = prog + '%';
        document.getElementById('progress-percent').textContent = prog.toFixed(2) + '% of Goal';

        // Render Equity SVG
        if (data.equity_curve && data.equity_curve.length > 1) {
            renderEquityCurve(data.equity_curve);
        } else {
            renderEquityCurve([data.portfolio * 0.99, data.portfolio]);
        }

        // Active Holdings Table
        const posBody = document.getElementById('positions-body');
        const positions = data.positions || [];
        document.getElementById('pos-count').textContent = positions.length + ' OPEN';
        if (positions.length === 0) {
            posBody.innerHTML = '<tr><td colspan="8" class="empty-state">No open positions currently held.</td></tr>';
        } else {
            posBody.innerHTML = positions.map(p => {
                const isLong = (p.side === 'LONG');
                return `<tr>
                    <td class="ticker">${p.symbol}</td>
                    <td><span class="pill ${isLong ? 'pill-long' : 'pill-short'}">${p.side}</span></td>
                    <td style="font-family:var(--font-mono)">${p.qty}</td>
                    <td style="font-family:var(--font-mono)">${formatMoney(p.entry_price)}</td>
                    <td style="font-family:var(--font-mono)">${formatMoney(p.current_price)}</td>
                    <td style="font-family:var(--font-mono);color:var(--rose)">${formatMoney(p.stop_loss)}</td>
                    <td style="font-family:var(--font-mono);color:var(--emerald)">${formatMoney(p.target)}</td>
                    <td>${Number(p.holding_minutes || 0).toFixed(0)}m</td>
                </tr>`;
            }).join('');
        }

        // Trades Table
        const tradeBody = document.getElementById('trades-body');
        const trades = data.trades || [];
        if (trades.length === 0) {
            tradeBody.innerHTML = '<tr><td colspan="7" class="empty-state">No execution records logged yet.</td></tr>';
        } else {
            tradeBody.innerHTML = trades.map(t => {
                const pnl = Number(t.pnl || 0);
                const isWin = pnl >= 0;
                return `<tr>
                    <td class="ticker">${t.symbol}</td>
                    <td><span class="pill ${t.side === 'LONG' ? 'pill-long' : 'pill-short'}">${t.side}</span></td>
                    <td style="font-family:var(--font-mono)">${formatMoney(t.entry_price)} → ${formatMoney(t.exit_price)}</td>
                    <td class="${isWin ? 'pill-win' : 'pill-loss'}" style="font-family:var(--font-mono)">${formatMoney(pnl)}</td>
                    <td class="${isWin ? 'pill-win' : 'pill-loss'}">${formatPct(t.pnl_pct)}</td>
                    <td>${Math.round(Number(t.holding_seconds || 0) / 60)}m</td>
                    <td><span class="pill pill-muted">${t.exit_reason || 'stop'}</span></td>
                </tr>`;
            }).join('');
        }

        // Decisions Table
        const decBody = document.getElementById('decisions-body');
        const decisions = data.decisions || [];
        if (decisions.length === 0) {
            decBody.innerHTML = '<tr><td colspan="6" class="empty-state">Awaiting next decision cycle...</td></tr>';
        } else {
            decBody.innerHTML = decisions.slice(0, 8).map(d => {
                const act = d.action || 'WAIT';
                let pillClass = 'pill-muted';
                if (act === 'BUY') pillClass = 'pill-long';
                else if (act === 'SHORT') pillClass = 'pill-short';
                return `<tr>
                    <td class="ticker">${d.symbol}</td>
                    <td><span class="pill ${pillClass}">${act}</span></td>
                    <td style="font-family:var(--font-mono)">${Math.round(d.confidence || 0)}%</td>
                    <td><span class="pill pill-cyan">${d.strategy || 'Trend'}</span></td>
                    <td><span class="pill pill-muted">${d.risk_decision || 'N/A'}</span></td>
                    <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;" title="${d.reason || ''}">${d.reason || '--'}</td>
                </tr>`;
            }).join('');
        }

        // Market State
        const m = data.market || {};
        document.getElementById('intel-regime').textContent = m.regime || 'Neutral';
        document.getElementById('intel-sentiment').textContent = m.global_sentiment || 'Neutral';
        document.getElementById('intel-phase').textContent = data.market_phase || 'Active';
        document.getElementById('intel-pipeline').textContent = m.data_ok ? 'Healthy' : 'Live Polling';

        // Learning Weights
        const learn = data.learning || {};
        const weights = learn.weights || {};
        const weightsBox = document.getElementById('learning-weights-container');
        if (Object.keys(weights).length > 0) {
            weightsBox.innerHTML = Object.entries(weights).map(([k, v]) => `
                <div class="pill pill-cyan">${k}: ${Number(v).toFixed(2)}x</div>
            `).join('');
        }
    } catch (e) {
        console.error('Dashboard refresh error:', e);
    }
}

updateDashboard();
setInterval(updateDashboard, 3000);
</script>
</body>
</html>
"""


def _holding_minutes(opened_at):
    try:
        opened = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - opened).total_seconds() / 60, 1)
    except Exception:
        return 0.0


def create_app(db, cfg=None, provider=None):
    cfg = cfg or {}
    flask_app = Flask(__name__)
    short_margin = cfg.get("execution", {}).get("short_margin_pct", 0.25)
    learning = LearningEngine(db, cfg)

    @flask_app.get("/")
    def home():
        return render_template_string(HTML)

    @flask_app.get("/health")
    def health():
        try:
            account = db.account()
            return jsonify({
                "status": "ok",
                "paper_only": True,
                "database": "ok" if account else "uninitialized",
                "market_phase": market_phase(),
                "holiday": holiday_name()
            })
        except Exception as error:
            return jsonify({"status": "error", "paper_only": True, "error": repr(error)}), 500

    @flask_app.get("/api/runtime")
    def runtime_state():
        return jsonify(preflight(cfg, provider))

    @flask_app.get("/api/learning")
    def learning_state():
        return jsonify(learning.recommendation())

    @flask_app.get("/api/state")
    def state():
        account = db.account()
        if not account:
            return jsonify({"error": "Trading account is not initialized."}), 503

        positions = db.positions()
        trades = db.trades(10)
        metrics = portfolio_metrics(account, positions, short_margin)
        realized = db.total_realized_pnl()
        pnl = metrics["equity"] - account["starting_capital"]

        drawdown = 0.0
        if account["peak_value"]:
            drawdown = ((account["peak_value"] - metrics["equity"]) / account["peak_value"]) * 100

        for position in positions:
            position["holding_minutes"] = _holding_minutes(position.get("opened_at"))

        decisions = db.decisions(10)
        market = db.market()
        market["market_phase"] = market_phase()
        market["holiday"] = holiday_name()

        return jsonify({
            "paper_only": True,
            "portfolio": metrics["equity"],
            "cash": metrics["cash"],
            "available_cash": metrics["available_cash"],
            "long_value": metrics["long_value"],
            "short_notional": metrics["short_notional"],
            "reserved_margin": metrics["reserved_margin"],
            "gross_exposure": metrics["gross_exposure"],
            "net_exposure": metrics["net_exposure"],
            "realized": realized,
            "unrealized": (metrics["long_unrealized"] + metrics["short_unrealized"]),
            "pnl": pnl,
            "return_pct": (pnl / account["starting_capital"] * 100),
            "target": account["target_capital"],
            "progress": (metrics["equity"] / account["target_capital"] * 100),
            "peak": account["peak_value"],
            "drawdown": drawdown,
            "positions": positions,
            "trades": trades,
            "decisions": decisions,
            "market": market,
            "learning": learning.recommendation(),
            "market_phase": market_phase(),
            "updated_at": now_ist().isoformat(),
            "equity_curve": db.equity()
        })

    return flask_app


def _load_runtime():
    import json
    from pathlib import Path
    from .db import DB

    root = Path(__file__).resolve().parent.parent
    config_path = root / "config" / "default.json"
    with open(config_path, "r", encoding="utf-8") as file:
        cfg = json.load(file)

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = DB(str(data_dir / "trader.db"))
    db.ensure_account(cfg["capital"]["starting"], cfg["capital"]["target"])
    return create_app(db=db, cfg=cfg)


app = _load_runtime()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)