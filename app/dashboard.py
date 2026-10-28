import os
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template_string


from .accounting import portfolio_metrics
from .market_hours import market_phase, now_ist, holiday_name, market_open, IST
from .learning import LearningEngine
from .runtime import preflight


HTML = r"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
    <title>Tradng-Ai v3.0 · Institutional Terminal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #06090f;
            --bg-surface: #0c121e;
            --bg-card: #10192a;
            --bg-card-hover: #141f34;
            --border: rgba(255, 255, 255, 0.08);
            --border-subtle: rgba(255, 255, 255, 0.04);
            --border-hover: rgba(56, 189, 248, 0.3);
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

        /* Top Minimal Header */
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
            padding: 12px 18px;
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
            width: 30px;
            height: 30px;
            background: linear-gradient(135deg, var(--cyan), var(--indigo));
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-family: var(--font-mono);
            font-size: 13px;
            color: #fff;
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.3);
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
            gap: 10px;
        }
        .pulse-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 600;
            padding: 4px 9px;
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
        .auto-trade-btn {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            font-family: var(--font-sans);
            font-size: 11px;
            font-weight: 700;
            padding: 5px 12px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            border: 1px solid rgba(16, 185, 129, 0.35);
            background: rgba(16, 185, 129, 0.12);
            color: #34d399;
            white-space: nowrap;
        }
        .auto-trade-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 2px 10px rgba(16, 185, 129, 0.2);
        }
        .auto-trade-btn.paused {
            border: 1px solid rgba(245, 158, 11, 0.4);
            background: rgba(245, 158, 11, 0.12);
            color: #fbbf24;
        }
        .auto-trade-btn.paused:hover {
            box-shadow: 0 2px 10px rgba(245, 158, 11, 0.2);
        }
        .auto-trade-dot {
            width: 7px;
            height: 7px;
            background: #10b981;
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
            animation: pulse 2s infinite ease-in-out;
            flex-shrink: 0;
        }
        .auto-trade-btn.paused .auto-trade-dot {
            background: #f59e0b;
            box-shadow: 0 0 6px #f59e0b;
            animation: none;
        }

        /* Main Container */
        main {
            max-width: 1400px;
            margin: 0 auto;
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            gap: 14px;
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
            padding: 7px 15px;
            border-radius: 9px;
            cursor: pointer;
            transition: all 0.15s ease;
            white-space: nowrap;
        }
        .tab-btn:hover { color: var(--text-main); }
        .tab-btn.active {
            color: #fff;
            background: var(--bg-card);
            border: 1px solid var(--border);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
        }

        /* Sleek Hero Portfolio Card */
        .hero-card {
            background: linear-gradient(180deg, #111a2d 0%, var(--bg-card) 100%);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 22px;
            display: flex;
            flex-direction: column;
            gap: 18px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
            position: relative;
            overflow: hidden;
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
            font-size: clamp(30px, 5.5vw, 44px);
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
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
            padding-top: 16px;
            border-top: 1px solid var(--border-subtle);
        }
        .stat-item {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .stat-label {
            font-size: 10.5px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--text-faint);
        }
        .stat-val {
            font-family: var(--font-mono);
            font-size: 16px;
            font-weight: 700;
            color: var(--text-main);
        }
        .stat-sub {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--text-muted);
        }

        /* Secondary Exposure Strip */
        .exposure-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
        }
        .exposure-pill {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 8px 12px;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .exposure-pill .label {
            font-size: 9.5px;
            font-weight: 700;
            text-transform: uppercase;
            color: var(--text-faint);
            letter-spacing: 0.04em;
        }
        .exposure-pill .val {
            font-family: var(--font-mono);
            font-size: 14.5px;
            font-weight: 700;
        }

        /* Performance Sparkline Card */
        .chart-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .chart-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .chart-title {
            font-size: 13.5px;
            font-weight: 600;
            color: var(--text-main);
        }
        .progress-bar-bg {
            height: 5px;
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
            height: 125px;
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
            gap: 14px;
        }
        @media (max-width: 900px) {
            .two-col { grid-template-columns: 1fr; }
        }

        /* Panels */
        .panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .panel-title {
            font-size: 13.5px;
            font-weight: 600;
            color: var(--text-main);
        }

        /* Modern Position Cards (Mobile & Desktop) */
        .positions-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-height: 380px;
            overflow-y: auto;
        }
        .pos-card {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            transition: border-color 0.15s ease;
        }
        .pos-card:hover { border-color: var(--border-hover); }
        .pos-card-main {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }
        .pos-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .pos-symbol {
            font-family: var(--font-mono);
            font-size: 15px;
            font-weight: 700;
            color: #fff;
            letter-spacing: -0.01em;
        }
        .pos-meta {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
        }
        .pos-pricing {
            text-align: right;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .pos-current {
            font-family: var(--font-mono);
            font-size: 16px;
            font-weight: 700;
            color: #fff;
        }
        .pos-pnl {
            font-family: var(--font-mono);
            font-size: 12px;
            font-weight: 600;
        }
        .pos-card-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-top: 8px;
            border-top: 1px solid var(--border-subtle);
            font-size: 11px;
            font-family: var(--font-mono);
            color: var(--text-muted);
        }
        .pos-bound {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        /* Sleek Activity Rows for Trades */
        .trades-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: 380px;
            overflow-y: auto;
        }
        .activity-row {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 10px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }
        .activity-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .activity-icon {
            width: 24px;
            height: 24px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
            flex-shrink: 0;
        }
        .icon-win { background: var(--emerald-bg); color: var(--emerald); }
        .icon-loss { background: var(--rose-bg); color: var(--rose); }
        .activity-title {
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .activity-sub {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 2px;
        }
        .activity-right {
            text-align: right;
            font-family: var(--font-mono);
        }
        .activity-val { font-size: 14px; font-weight: 700; }

        /* AI Decisions Feed */
        .decisions-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: 380px;
            overflow-y: auto;
        }
        .decision-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .decision-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .decision-sym {
            font-family: var(--font-mono);
            font-weight: 700;
            font-size: 13px;
        }
        .decision-reason {
            font-size: 11.5px;
            color: var(--text-muted);
            line-height: 1.4;
        }

        /* Financial Badges & Utilities */
        .pill {
            display: inline-flex;
            align-items: center;
            font-family: var(--font-mono);
            font-size: 10.5px;
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 5px;
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
        .text-up { color: var(--emerald); }
        .text-down { color: var(--rose); }
        .faint { color: var(--text-faint); }

        /* Market Intel Mini Grid */
        .intel-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 8px;
        }
        .intel-item {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 9px 11px;
        }
        .intel-item .title {
            font-size: 9.5px;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-faint);
            margin-bottom: 3px;
            letter-spacing: 0.04em;
        }
        .intel-item .val {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-main);
        }

        .empty-state {
            padding: 24px 16px;
            text-align: center;
            color: var(--text-faint);
            font-size: 12px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }

        /* Capital Allocation Interactive Card */
        .alloc-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .alloc-bar {
            height: 10px;
            border-radius: 999px;
            display: flex;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.05);
            box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.4);
        }
        .alloc-seg-intra { background: var(--cyan); transition: width 0.3s ease; }
        .alloc-seg-swing { background: var(--emerald); transition: width 0.3s ease; }
        .alloc-seg-fno { background: var(--indigo); transition: width 0.3s ease; }
        .alloc-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
        }
        .alloc-item {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 10px 14px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .alloc-item-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .alloc-input-row {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .alloc-slider {
            flex: 1;
            accent-color: var(--cyan);
            cursor: pointer;
        }
        .alloc-num-input {
            width: 54px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: #fff;
            font-family: var(--font-mono);
            font-size: 13px;
            font-weight: 700;
            padding: 3px 6px;
            text-align: center;
        }
        .save-alloc-btn {
            background: linear-gradient(135deg, var(--cyan), var(--indigo));
            border: none;
            color: #fff;
            font-family: var(--font-sans);
            font-size: 12px;
            font-weight: 700;
            padding: 7px 16px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .save-alloc-btn:hover { opacity: 0.9; }

        /* Desk Alert Banners */
        .desk-banner {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 12px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
        }
        .banner-highlight {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            font-weight: 600;
        }
        .banner-tag {
            font-family: var(--font-mono);
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
        }

        /* Mobile Layout */
        @media (max-width: 640px) {
            header .header-inner { padding: 10px 14px; }
            main { padding: 12px 14px; gap: 12px; }
            .hero-card { padding: 16px 14px; gap: 14px; }
            .hero-stats-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
            .exposure-strip { grid-template-columns: 1fr 1fr; }
            .panel { padding: 14px; }
            .chart-card { padding: 14px; }
            .chart-box { height: 100px; }
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
                <h1>Tradng-Ai <span class="brand-badge">PRO v3.0</span></h1>
            </div>
        </div>
        <div class="header-meta">
            <button id="auto-trade-btn" class="auto-trade-btn active" onclick="toggleAutoTrading()" title="Click to Pause / Resume Auto-Trading">
                <span class="auto-trade-dot"></span>
                <span id="auto-trade-label">AUTO TRADING ON</span>
            </button>
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
            <button id="tab-main-btn" class="tab-btn active" onclick="switchTab('main')">Main Overview</button>
            <button id="tab-intraday-btn" class="tab-btn" onclick="switchTab('intraday')">⚡ Intraday (MIS)</button>
            <button id="tab-swing-btn" class="tab-btn" onclick="switchTab('swing')">📈 Stocks / Swing (CNC)</button>
            <button id="tab-fno-btn" class="tab-btn" onclick="switchTab('fno')">🎯 Futures & Options (F&O)</button>
            <button id="tab-research-btn" class="tab-btn" onclick="switchTab('research')">Quant Research</button>
        </div>
    </div>

    <!-- TAB 1: MAIN OVERVIEW (All Desks Aggregated) -->
    <div id="tab-main" style="display:flex; flex-direction:column; gap:14px;">
        <!-- Unified Hero Portfolio Card -->
        <div class="hero-card">
            <div class="hero-top">
                <div>
                    <div class="hero-equity-label">Portfolio Total Equity</div>
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
                    <span class="stat-label">Target Goal</span>
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

        <!-- Interactive Multi-Desk Capital Allocation Panel -->
        <div class="alloc-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                <div>
                    <div style="font-size:14px; font-weight:700; color:#fff;">Multi-Desk Capital Allocation</div>
                    <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">
                        Dynamically distribute capital across Intraday, Stocks/Swing, and F&O desks. Total must equal 100%.
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:10px;">
                    <span id="alloc-sum-badge" class="pill pill-cyan">TOTAL: 100%</span>
                    <button id="save-alloc-btn" class="save-alloc-btn" onclick="saveCapitalAllocation()">Save Allocation</button>
                </div>
            </div>

            <!-- 3-Color Segmented Allocation Bar -->
            <div class="alloc-bar" style="margin-top:12px;">
                <div id="bar-alloc-intra" style="background:var(--cyan); width:40%; display:flex; align-items:center; justify-content:center; color:#0f172a; font-size:10px; font-weight:800; font-family:var(--font-mono); overflow:hidden; transition:width 0.2s;">40%</div>
                <div id="bar-alloc-swing" style="background:var(--emerald); width:40%; display:flex; align-items:center; justify-content:center; color:#0f172a; font-size:10px; font-weight:800; font-family:var(--font-mono); overflow:hidden; transition:width 0.2s;">40%</div>
                <div id="bar-alloc-fno" style="background:var(--indigo); width:20%; display:flex; align-items:center; justify-content:center; color:#fff; font-size:10px; font-weight:800; font-family:var(--font-mono); overflow:hidden; transition:width 0.2s;">20%</div>
            </div>

            <!-- Desk Sliders and Value Inputs -->
            <div class="alloc-grid" style="margin-top:12px;">
                <div class="alloc-col" style="border-left:3px solid var(--cyan); padding-left:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:12px; font-weight:700; color:var(--cyan);">⚡ Intraday (MIS)</span>
                        <span id="alloc-intra-rupees" style="font-family:var(--font-mono); font-size:11px; color:var(--text-muted);">₹40,000</span>
                    </div>
                    <div class="alloc-slider-row" style="margin-top:6px;">
                        <input type="range" id="slider-alloc-intra" class="alloc-slider" min="0" max="100" value="40" oninput="onAllocSliderChange('intra')">
                        <input type="number" id="num-alloc-intra" class="alloc-num-input" min="0" max="100" value="40" onchange="onAllocNumChange('intra')">%
                    </div>
                </div>

                <div class="alloc-col" style="border-left:3px solid var(--emerald); padding-left:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:12px; font-weight:700; color:var(--emerald);">📈 Stocks / Swing (CNC)</span>
                        <span id="alloc-swing-rupees" style="font-family:var(--font-mono); font-size:11px; color:var(--text-muted);">₹40,000</span>
                    </div>
                    <div class="alloc-slider-row" style="margin-top:6px;">
                        <input type="range" id="slider-alloc-swing" class="alloc-slider" min="0" max="100" value="40" oninput="onAllocSliderChange('swing')">
                        <input type="number" id="num-alloc-swing" class="alloc-num-input" min="0" max="100" value="40" onchange="onAllocNumChange('swing')">%
                    </div>
                </div>

                <div class="alloc-col" style="border-left:3px solid var(--indigo); padding-left:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:12px; font-weight:700; color:var(--indigo);">🎯 F&O Spreads</span>
                        <span id="alloc-fno-rupees" style="font-family:var(--font-mono); font-size:11px; color:var(--text-muted);">₹20,000</span>
                    </div>
                    <div class="alloc-slider-row" style="margin-top:6px;">
                        <input type="range" id="slider-alloc-fno" class="alloc-slider" min="0" max="100" value="20" oninput="onAllocSliderChange('fno')">
                        <input type="number" id="num-alloc-fno" class="alloc-num-input" min="0" max="100" value="20" onchange="onAllocNumChange('fno')">%
                    </div>
                </div>
            </div>
            <div id="alloc-msg" style="font-size:11px; color:var(--emerald); margin-top:8px; display:none; font-weight:600;">✓ Capital allocation updated successfully!</div>
        </div>

        <!-- Performance Sparkline Card -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">Equity Growth Sparkline</div>
            </div>
            <div class="progress-bar-bg">
                <div id="progress-fill" class="progress-bar-fill" style="width:0%"></div>
            </div>
            <div class="chart-box">
                <svg id="equity-svg" class="equity-svg" viewBox="0 0 1000 125" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="#10b981" stop-opacity="0.25"/>
                            <stop offset="100%" stop-color="#10b981" stop-opacity="0.0"/>
                        </linearGradient>
                    </defs>
                    <path id="equity-area" fill="url(#eq-grad)" d=""/>
                    <path id="equity-line" fill="none" stroke="#10b981" stroke-width="2.2" d=""/>
                </svg>
            </div>
        </div>

        <!-- Pending Orders & AMOs (After-Market Orders) -->
        <div class="panel" id="orders-panel" style="border:1px solid rgba(234,179,8,0.3); background:linear-gradient(180deg, rgba(234,179,8,0.03) 0%, var(--bg-card) 100%);">
            <div class="panel-header">
                <div class="panel-title" style="display:flex; align-items:center; gap:8px;">
                    <span>📝 Pending Orders & AMOs (After-Market)</span>
                    <span style="font-size:11px; font-weight:400; color:var(--text-muted);">(Queued outside 09:15-15:30 IST market hours)</span>
                </div>
                <span id="order-count" class="brand-badge" style="background:rgba(234,179,8,0.15); color:#facc15; border:1px solid rgba(234,179,8,0.3);">0 PENDING</span>
            </div>
            <div id="orders-body" class="positions-list">
                <div class="empty-state">
                    <span style="font-size:20px;opacity:0.6;">📝</span>
                    <span>No pending orders queued</span>
                </div>
            </div>
        </div>

        <!-- Two Column Desk: Holdings & Executions -->
        <div class="two-col">
            <!-- Open Holdings as Sleek Mobile Cards -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Active Market Holdings (All Desks)</div>
                    <span id="pos-count" class="brand-badge">0 OPEN</span>
                </div>
                <div id="positions-body" class="positions-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">🛡️</span>
                        <span>No open positions currently held</span>
                    </div>
                </div>
            </div>

            <!-- Closed Trades as Activity Feed -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Recent Executions (All Desks)</div>
                    <span id="trade-count" class="brand-badge">LAST 20 TRADES</span>
                </div>
                <div id="trades-body" class="trades-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">📋</span>
                        <span>No execution records logged yet</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Two Column Desk: AI Decisions & Market Intel -->
        <div class="two-col">
            <!-- AI Proposer Stream as Feed -->
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">AI Decision Stream</div>
                    <span class="pill pill-cyan">AUDIT LOG</span>
                </div>
                <div id="decisions-body" class="decisions-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">⚡</span>
                        <span>Awaiting next decision cycle...</span>
                    </div>
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
                    <div class="intel-item">
                        <div class="title">Shorting Gate</div>
                        <div id="intel-shorting" class="val" style="color:var(--emerald);font-size:12px;">AUTO-OFF</div>
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

    <!-- TAB 2: INTRADAY DESK (MIS) -->
    <div id="tab-intraday" style="display:none; flex-direction:column; gap:14px;">
        <!-- Desk Alert Banner -->
        <div class="desk-banner" style="border-left:4px solid var(--cyan);">
            <div class="banner-highlight">
                <span style="font-size:18px;">⚡</span>
                <div>
                    <div>Intraday Day Trading Desk (MIS)</div>
                    <div style="font-size:11px; color:var(--text-muted); font-weight:400;">
                        Strict 15:10 IST EOD auto square-off • ORB + VWAP • Automated Regime Shorting Gate • Fast Breakeven Lock at +0.33R • Min ₹5,000 Notional
                    </div>
                </div>
            </div>
            <div style="display:flex; gap:8px;">
                <span class="banner-tag" style="background:rgba(6,182,212,0.15); color:var(--cyan); border:1px solid rgba(6,182,212,0.3);">MIS PRODUCT</span>
                <span class="banner-tag" style="background:rgba(16,185,129,0.15); color:var(--emerald); border:1px solid rgba(16,185,129,0.3);">AUTO-SHORT GATE</span>
                <span class="banner-tag" style="background:rgba(244,63,94,0.15); color:var(--rose); border:1px solid rgba(244,63,94,0.3);">SQUARE-OFF 15:10 IST</span>
            </div>
        </div>

        <!-- Desk KPI Strip -->
        <div class="hero-stats-grid">
            <div class="stat-item">
                <span class="stat-label">Allocated Capital</span>
                <span id="intra-alloc-val" class="stat-val" style="color:var(--cyan);">₹0.00</span>
                <span id="intra-alloc-pct" class="stat-sub">40% of Total</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Active MIS Positions</span>
                <span id="intra-open-count" class="stat-val">0</span>
                <span class="stat-sub">Max concurrent: 5</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">MIS Realized P&L</span>
                <span id="intra-pnl-val" class="stat-val">₹0.00</span>
                <span id="intra-trade-count" class="stat-sub">0 trades today</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">EOD Square-Off Countdown</span>
                <span id="intra-eod-countdown" class="stat-val" style="color:var(--amber);">Active</span>
                <span class="stat-sub">Auto-close remaining</span>
            </div>
        </div>

        <!-- Active Intraday Positions & Intraday Trades -->
        <div class="two-col">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Active Intraday Holdings (MIS)</div>
                    <span id="intra-pos-badge" class="brand-badge">0 OPEN</span>
                </div>
                <div id="positions-intraday-body" class="positions-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">⚡</span>
                        <span>No open intraday MIS positions</span>
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Today's Intraday Executions</div>
                    <span id="intra-trades-badge" class="brand-badge">TODAY</span>
                </div>
                <div id="trades-intraday-body" class="trades-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">📋</span>
                        <span>No intraday trades executed today</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 3: STOCKS / SWING DESK (CNC) -->
    <div id="tab-swing" style="display:none; flex-direction:column; gap:14px;">
        <!-- Desk Alert Banner -->
        <div class="desk-banner" style="border-left:4px solid var(--emerald);">
            <div class="banner-highlight">
                <span style="font-size:18px;">📈</span>
                <div>
                    <div>Stocks & Swing Trading Desk (CNC Delivery)</div>
                    <div style="font-size:11px; color:var(--text-muted); font-weight:400;">
                        Exempt from 15:10 EOD square-off • 3 to 20 days holding • Minervini Stage 2 Trend Template • 20 EMA Pullback with Volume Dry-Up
                    </div>
                </div>
            </div>
            <div style="display:flex; gap:8px;">
                <span class="banner-tag" style="background:rgba(16,185,129,0.15); color:var(--emerald); border:1px solid rgba(16,185,129,0.3);">CNC DELIVERY</span>
                <span class="banner-tag" style="background:rgba(16,185,129,0.15); color:var(--emerald); border:1px solid rgba(16,185,129,0.3);">OVERNIGHT HOLDING</span>
            </div>
        </div>

        <!-- Desk KPI Strip -->
        <div class="hero-stats-grid">
            <div class="stat-item">
                <span class="stat-label">Allocated Capital</span>
                <span id="swing-alloc-val" class="stat-val" style="color:var(--emerald);">₹0.00</span>
                <span id="swing-alloc-pct" class="stat-sub">40% of Total</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Active Swing Holdings</span>
                <span id="swing-open-count" class="stat-val">0</span>
                <span class="stat-sub">Max concurrent: 5</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Swing Realized P&L</span>
                <span id="swing-pnl-val" class="stat-val">₹0.00</span>
                <span id="swing-trade-count" class="stat-sub">Closed CNC trades</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Target Strategy</span>
                <span class="stat-val" style="color:var(--cyan);font-size:15px;">20 EMA Pullback</span>
                <span class="stat-sub">8%–14% Swing Target</span>
            </div>
        </div>

        <!-- Active Swing Holdings & Closed Swing Trades -->
        <div class="two-col">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Active Delivery Holdings (CNC)</div>
                    <span id="swing-pos-badge" class="brand-badge">0 HELD</span>
                </div>
                <div id="positions-swing-body" class="positions-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">📈</span>
                        <span>No swing delivery positions currently held</span>
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Swing Trade Executions</div>
                    <span id="swing-trades-badge" class="brand-badge">HISTORICAL</span>
                </div>
                <div id="trades-swing-body" class="trades-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">📋</span>
                        <span>No swing trades completed yet</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 4: FUTURES & OPTIONS DESK (F&O) -->
    <div id="tab-fno" style="display:none; flex-direction:column; gap:14px;">
        <!-- Desk Alert Banner -->
        <div class="desk-banner" style="border-left:4px solid var(--indigo);">
            <div class="banner-highlight">
                <span style="font-size:18px;">🎯</span>
                <div>
                    <div>Defined-Risk Futures & Options Desk (F&O)</div>
                    <div style="font-size:11px; color:var(--text-muted); font-weight:400;">
                        Nifty 50 & Bank Nifty Iron Condors / Credit Spreads • Delta 15-20 OTM Strikes • 50% Profit-Taking Rule (75%+ Win Rate)
                    </div>
                </div>
            </div>
            <div style="display:flex; gap:8px;">
                <span class="banner-tag" style="background:rgba(99,102,241,0.15); color:var(--indigo); border:1px solid rgba(99,102,241,0.3);">DEFINED RISK</span>
                <span id="fno-expiry-badge" class="banner-tag" style="background:rgba(6,182,212,0.15); color:var(--cyan); border:1px solid rgba(6,182,212,0.3);">EXPIRY: THURSDAY</span>
            </div>
        </div>

        <!-- Desk KPI Strip -->
        <div class="hero-stats-grid">
            <div class="stat-item">
                <span class="stat-label">Allocated Capital</span>
                <span id="fno-alloc-val" class="stat-val" style="color:var(--indigo);">₹0.00</span>
                <span id="fno-alloc-pct" class="stat-sub">20% of Total</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Active F&O Spreads</span>
                <span id="fno-open-count" class="stat-val">0</span>
                <span class="stat-sub">Multi-leg positions</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Nifty Put-Call Ratio (PCR)</span>
                <span id="fno-pcr-val" class="stat-val" style="color:var(--cyan);">1.00</span>
                <span id="fno-pcr-sentiment" class="stat-sub">Neutral</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">F&O Realized P&L</span>
                <span id="fno-pnl-val" class="stat-val">₹0.00</span>
                <span id="fno-trade-count" class="stat-sub">0 spreads closed</span>
            </div>
        </div>

        <!-- Active F&O Positions & Closed F&O Trades -->
        <div class="two-col">
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Active Index Spreads & Condors</div>
                    <span id="fno-pos-badge" class="brand-badge">0 SPREADS</span>
                </div>
                <div id="positions-fno-body" class="positions-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">🎯</span>
                        <span>No active F&O spreads or option positions</span>
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">F&O Trade Executions</div>
                    <span id="fno-trades-badge" class="brand-badge">CLOSED SPREADS</span>
                </div>
                <div id="trades-fno-body" class="trades-list">
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">📋</span>
                        <span>No F&O trades closed yet</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 5: QUANT RESEARCH & BASELINES -->
    <div id="tab-research" style="display:none; flex-direction:column; gap:14px;">
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">Institutional Quant Research Foundation</div>
                <span class="pill pill-long">VALIDATED</span>
            </div>
            <p style="font-size:13px; color:var(--text-muted); line-height:1.6;">
                Institutional research engine with survivorship-bias-free point-in-time universe, unified execution decision logic,
                realistic NSE regulatory cost deductions, and out-of-sample walk-forward validation across all 3 desks.
            </p>
        </div>

        <div class="exposure-strip">
            <div class="exposure-pill">
                <span class="label">Decision Alignment</span>
                <span class="val" style="color:var(--emerald);font-size:13.5px;">100% UNIFIED</span>
            </div>
            <div class="exposure-pill">
                <span class="label">NSE Cost Model</span>
                <span class="val" style="color:var(--cyan);font-size:13.5px;">EXACT CHARGES</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Data Store</span>
                <span class="val" style="color:var(--indigo);font-size:13.5px;">SPLIT-ADJUSTED</span>
            </div>
            <div class="exposure-pill">
                <span class="label">Constituent Tracking</span>
                <span class="val" style="color:var(--emerald);font-size:13.5px;">POINT-IN-TIME</span>
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
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

const formatMoney = val => '₹' + Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatPct = val => (Number(val || 0) >= 0 ? '+' : '') + Number(val || 0).toFixed(2) + '%';

function getAuthToken() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        const urlToken = urlParams.get('token');
        if (urlToken) {
            localStorage.setItem('dashboard_token', urlToken.trim());
            return urlToken.trim();
        }
        return (localStorage.getItem('dashboard_token') || 'tradng-pro-2026').trim();
    } catch (e) {
        return 'tradng-pro-2026';
    }
}

async function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    const token = getAuthToken();
    if (token) {
        options.headers['Authorization'] = 'Bearer ' + token;
        options.headers['X-API-Token'] = token;
    }
    let res = await fetch(url, options);
    if (res.status === 401) {
        const inputToken = prompt("Enter dashboard access token:");
        if (inputToken) {
            localStorage.setItem('dashboard_token', inputToken.trim());
            options.headers['Authorization'] = 'Bearer ' + inputToken.trim();
            options.headers['X-API-Token'] = inputToken.trim();
            res = await fetch(url, options);
        }
    }
    return res;
}

let autoTradingActive = true;

async function toggleAutoTrading() {
    const btn = document.getElementById('auto-trade-btn');
    const label = document.getElementById('auto-trade-label');
    const nextState = !autoTradingActive;
    autoTradingActive = nextState;
    if (btn && label) {
        btn.className = 'auto-trade-btn' + (autoTradingActive ? ' active' : ' paused');
        label.textContent = autoTradingActive ? 'AUTO TRADING ON' : 'AUTO TRADING OFF';
    }
    try {
        const res = await authFetch('/api/auto-trading/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: nextState })
        });
        if (res.ok) {
            const data = await res.json();
            autoTradingActive = !!data.auto_trading;
            if (btn && label) {
                btn.className = 'auto-trade-btn' + (autoTradingActive ? ' active' : ' paused');
                label.textContent = autoTradingActive ? 'AUTO TRADING ON' : 'AUTO TRADING OFF';
            }
        }
    } catch (e) {
        console.error('Failed to toggle auto-trading:', e);
    }
}

function switchTab(tab) {
    const tabs = ['main', 'intraday', 'swing', 'fno', 'research'];
    tabs.forEach(t => {
        const el = document.getElementById('tab-' + t);
        const btn = document.getElementById('tab-' + t + '-btn');
        if (el) el.style.display = (t === tab) ? 'flex' : 'none';
        if (btn) btn.className = 'tab-btn' + (t === tab ? ' active' : '');
    });
}

let currentAlloc = { intraday: 40, swing: 40, fno: 20 };
let isUserAdjustingAlloc = false;
let totalEquityCached = 100000;

function updateAllocDisplay() {
    const intra = Math.max(0, Math.min(100, Number(currentAlloc.intraday || 0)));
    const swing = Math.max(0, Math.min(100, Number(currentAlloc.swing || 0)));
    const fno = Math.max(0, Math.min(100, Number(currentAlloc.fno || 0)));
    const sum = intra + swing + fno;

    const sIntra = document.getElementById('slider-alloc-intra');
    const nIntra = document.getElementById('num-alloc-intra');
    const sSwing = document.getElementById('slider-alloc-swing');
    const nSwing = document.getElementById('num-alloc-swing');
    const sFno = document.getElementById('slider-alloc-fno');
    const nFno = document.getElementById('num-alloc-fno');

    if (sIntra) sIntra.value = intra;
    if (nIntra) nIntra.value = intra;
    if (sSwing) sSwing.value = swing;
    if (nSwing) nSwing.value = swing;
    if (sFno) sFno.value = fno;
    if (nFno) nFno.value = fno;

    const bIntra = document.getElementById('bar-alloc-intra');
    const bSwing = document.getElementById('bar-alloc-swing');
    const bFno = document.getElementById('bar-alloc-fno');
    if (bIntra) { bIntra.style.width = intra + '%'; bIntra.textContent = intra + '%'; }
    if (bSwing) { bSwing.style.width = swing + '%'; bSwing.textContent = swing + '%'; }
    if (bFno) { bFno.style.width = fno + '%'; bFno.textContent = fno + '%'; }

    const intraRupees = (totalEquityCached * (intra / 100));
    const swingRupees = (totalEquityCached * (swing / 100));
    const fnoRupees = (totalEquityCached * (fno / 100));

    const rIntra = document.getElementById('alloc-intra-rupees');
    const rSwing = document.getElementById('alloc-swing-rupees');
    const rFno = document.getElementById('alloc-fno-rupees');
    if (rIntra) rIntra.textContent = formatMoney(intraRupees);
    if (rSwing) rSwing.textContent = formatMoney(swingRupees);
    if (rFno) rFno.textContent = formatMoney(fnoRupees);

    const kiIntraVal = document.getElementById('intra-alloc-val');
    const kiIntraPct = document.getElementById('intra-alloc-pct');
    if (kiIntraVal) kiIntraVal.textContent = formatMoney(intraRupees);
    if (kiIntraPct) kiIntraPct.textContent = intra + '% of Total';

    const kiSwingVal = document.getElementById('swing-alloc-val');
    const kiSwingPct = document.getElementById('swing-alloc-pct');
    if (kiSwingVal) kiSwingVal.textContent = formatMoney(swingRupees);
    if (kiSwingPct) kiSwingPct.textContent = swing + '% of Total';

    const kiFnoVal = document.getElementById('fno-alloc-val');
    const kiFnoPct = document.getElementById('fno-alloc-pct');
    if (kiFnoVal) kiFnoVal.textContent = formatMoney(fnoRupees);
    if (kiFnoPct) kiFnoPct.textContent = fno + '% of Total';

    const badge = document.getElementById('alloc-sum-badge');
    if (badge) {
        badge.textContent = `TOTAL: ${sum.toFixed(0)}%`;
        badge.className = 'pill ' + (Math.abs(sum - 100) < 0.01 ? 'pill-long' : 'pill-short');
    }
}

function onAllocSliderChange(desk) {
    isUserAdjustingAlloc = true;
    const val = Number(document.getElementById('slider-alloc-' + desk).value);
    currentAlloc[desk === 'intra' ? 'intraday' : desk] = val;
    updateAllocDisplay();
}

function onAllocNumChange(desk) {
    isUserAdjustingAlloc = true;
    const val = Number(document.getElementById('num-alloc-' + desk).value);
    currentAlloc[desk === 'intra' ? 'intraday' : desk] = Math.max(0, Math.min(100, val));
    updateAllocDisplay();
}

async function saveCapitalAllocation() {
    const sum = Number(currentAlloc.intraday || 0) + Number(currentAlloc.swing || 0) + Number(currentAlloc.fno || 0);
    const msgEl = document.getElementById('alloc-msg');
    if (Math.abs(sum - 100) > 0.01) {
        if (msgEl) {
            msgEl.textContent = `⚠ Total must equal 100%. Current sum is ${sum}%.`;
            msgEl.style.color = 'var(--rose)';
            msgEl.style.display = 'block';
        }
        return;
    }
    try {
        const res = await authFetch('/api/capital-allocation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentAlloc)
        });
        if (res.ok) {
            const data = await res.json();
            if (data.capital_allocation) {
                currentAlloc = data.capital_allocation;
            }
            if (msgEl) {
                msgEl.textContent = '✓ Capital allocation saved and active across all desks!';
                msgEl.style.color = 'var(--emerald)';
                msgEl.style.display = 'block';
                setTimeout(() => { if (msgEl) msgEl.style.display = 'none'; }, 4000);
            }
            isUserAdjustingAlloc = false;
        }
    } catch (e) {
        console.error('Failed to save capital allocation:', e);
        if (msgEl) {
            msgEl.textContent = 'Failed to save allocation: ' + e;
            msgEl.style.color = 'var(--rose)';
            msgEl.style.display = 'block';
        }
    }
}

function renderEquityCurve(points) {
    if (!points || points.length < 2) return;
    const values = points.map(p => Number(p.value || p));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;
    const w = 1000;
    const h = 125;
    const pad = 6;

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

function renderPositionCard(p, desk) {
    const isLong = (p.side === 'LONG');
    const entry = Number(p.entry_price || 0);
    const curr = Number(p.current_price || entry);
    const qty = Number(p.qty || 1);
    const pnl = isLong ? (curr - entry) * qty : (entry - curr) * qty;
    const pnlPct = entry > 0 ? ((pnl / (entry * qty)) * 100).toFixed(2) : '0.00';
    const ageMinutes = Number(p.holding_minutes || 0);
    const ageStr = ageMinutes > 60 ? (ageMinutes / 60).toFixed(1) + 'h' : Math.round(ageMinutes) + 'm';
    const pType = (p.product_type || 'INTRADAY').toUpperCase();

    let extraPill = `<span class="pill ${isLong ? 'pill-long' : 'pill-short'}">${escapeHtml(p.side)} · ${qty} QTY</span>`;
    let subMeta = `Avg ${formatMoney(entry)}`;
    let legsHtml = '';

    if (pType === 'SWING') {
        const days = p.days_held !== undefined ? p.days_held : 0;
        extraPill = `<span class="pill pill-long">CNC DELIVERY · ${qty} QTY</span>`;
        subMeta = `Entry ${formatMoney(entry)} · <span class="pill pill-cyan" style="font-size:10px;padding:2px 6px;">Held ${days}d</span>`;
    } else if (pType === 'FNO') {
        const oType = p.option_type || 'SPREAD';
        extraPill = `<span class="pill pill-cyan">${escapeHtml(oType)} · ${qty} LOTS</span>`;
        subMeta = `Net Credit ${formatMoney(entry)}/sh · Exp: ${escapeHtml(p.expiry_date || 'Weekly')}`;

        if (p.legs_info) {
            try {
                const legs = typeof p.legs_info === 'string' ? JSON.parse(p.legs_info) : p.legs_info;
                if (Array.isArray(legs) && legs.length > 0) {
                    legsHtml = `<div class="fno-legs-box" style="margin-top:10px; padding:8px 10px; background:rgba(255,255,255,0.02); border-radius:8px; border:1px solid var(--border-subtle); display:flex; flex-direction:column; gap:6px;">
                        <div style="font-size:10px; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em; display:flex; justify-content:space-between;">
                            <span>Option Spread Legs</span>
                            <span style="color:var(--cyan);">${escapeHtml(p.strategy || 'Defined Risk')}</span>
                        </div>` +
                        legs.map(l => {
                            const isSell = (l.action || '').toUpperCase() === 'SELL';
                            const actColor = isSell ? 'var(--rose)' : 'var(--emerald)';
                            const actBg = isSell ? 'var(--rose-bg)' : 'var(--emerald-bg)';
                            const legType = (l.type || '').toUpperCase();
                            const legName = l.name ? escapeHtml(l.name) : `${escapeHtml(l.strike)} ${escapeHtml(legType)}`;
                            return `<div style="display:flex; justify-content:space-between; align-items:center; font-size:11px;">
                                <span>
                                    <span style="font-weight:700; color:${actColor}; background:${actBg}; padding:2px 6px; border-radius:4px; font-size:10px; margin-right:6px;">${escapeHtml(l.action)}</span>
                                    <span style="font-family:var(--font-mono); font-weight:600;">${legName}</span>
                                </span>
                                <span class="faint" style="font-family:var(--font-mono); font-size:11px;">${l.qty || qty} QTY</span>
                            </div>`;
                        }).join('') +
                    `</div>`;
                } else if (typeof p.legs_info === 'string' && p.legs_info.trim()) {
                    legsHtml = `<div style="margin-top:8px; font-size:11px; color:var(--text-muted); background:rgba(255,255,255,0.02); padding:6px 8px; border-radius:6px; border:1px solid var(--border-subtle);"><strong>Legs:</strong> ${escapeHtml(p.legs_info)}</div>`;
                }
            } catch (e) {
                if (p.legs_info && String(p.legs_info).trim()) {
                    legsHtml = `<div style="margin-top:8px; font-size:11px; color:var(--text-muted); background:rgba(255,255,255,0.02); padding:6px 8px; border-radius:6px; border:1px solid var(--border-subtle);"><strong>Legs:</strong> ${escapeHtml(p.legs_info)}</div>`;
                }
            }
        }
    }

    return `
    <div class="pos-card">
        <div class="pos-card-main">
            <div class="pos-info">
                <div class="pos-symbol">${escapeHtml(p.symbol)}</div>
                <div class="pos-meta">
                    ${extraPill}
                    <span class="faint">${subMeta}</span>
                </div>
            </div>
            <div class="pos-pricing">
                <div class="pos-current">${formatMoney(curr)}${pType === 'FNO' ? '/sh' : ''}</div>
                <div class="pos-pnl ${pnl >= 0 ? 'text-up' : 'text-down'}">${pnl >= 0 ? '+' : ''}${formatMoney(pnl)} (${pnl >= 0 ? '+' : ''}${pnlPct}%)</div>
            </div>
        </div>
        ${legsHtml}
        <div class="pos-card-footer">
            <div class="pos-bound"><span class="faint">SL:</span> <span class="text-down">${formatMoney(p.stop_loss)}</span></div>
            <div class="pos-bound"><span class="faint">TP:</span> <span class="text-up">${formatMoney(p.target)}</span></div>
            <div class="pos-bound"><span class="faint">${pType === 'SWING' ? 'Holding:' : 'Age:'}</span> <span>${pType === 'SWING' ? (p.days_held || 0) + ' days' : escapeHtml(ageStr)}</span></div>
        </div>
    </div>`;
}

function renderOrderCard(o) {
    const qty = Number(o.qty || 1);
    const price = Number(o.price || 0);
    const pType = (o.product_type || 'INTRADAY').toUpperCase();
    const oType = (o.order_type || 'AMO').toUpperCase();
    const sl = o.stop_loss ? ` · SL ${formatMoney(o.stop_loss)}` : '';
    const tp = o.target ? ` · TP ${formatMoney(o.target)}` : '';
    return `
    <div class="pos-card" style="border-left:3px solid #facc15;">
        <div class="pos-card-main">
            <div class="pos-info">
                <div class="pos-symbol">${escapeHtml(o.symbol)}</div>
                <div class="pos-meta">
                    <span class="pill" style="background:rgba(234,179,8,0.15); color:#facc15; border:1px solid rgba(234,179,8,0.3);">${escapeHtml(oType)} PENDING</span>
                    <span class="pill pill-cyan">${escapeHtml(pType)} · ${qty} QTY</span>
                    <span class="faint">${tp}${sl}</span>
                </div>
            </div>
            <div class="pos-pricing">
                <div class="pos-current">${formatMoney(price)}</div>
                <div style="font-size:11px; color:#facc15; font-family:var(--font-mono); font-weight:600;">Scheduled for 09:15 AM Open</div>
            </div>
        </div>
    </div>`;
}

function renderTradeRow(t) {
    const pnl = Number(t.pnl || 0);
    const isWin = pnl >= 0;
    const pType = (t.product_type || 'INTRADAY').toUpperCase();
    const timing = t.timing_display || '';
    const holdSec = Number(t.holding_seconds || 0);
    let holdStr = '';
    if (holdSec >= 86400) {
        holdStr = (holdSec / 86400).toFixed(1) + 'd';
    } else if (holdSec >= 3600) {
        holdStr = (holdSec / 3600).toFixed(1) + 'h';
    } else if (holdSec >= 60) {
        holdStr = Math.round(holdSec / 60) + 'm';
    }
    return `
    <div class="activity-row">
        <div class="activity-left">
            <div class="activity-icon ${isWin ? 'icon-win' : 'icon-loss'}">${isWin ? '▲' : '▼'}</div>
            <div>
                <div class="activity-title">
                    <span>${escapeHtml(t.symbol)}</span>
                    <span class="pill ${t.side === 'LONG' ? 'pill-long' : 'pill-short'}">${escapeHtml(t.side)}</span>
                    <span class="pill pill-muted" style="font-size:10px;padding:1px 5px;">${escapeHtml(pType)}</span>
                    ${timing ? `<span class="pill pill-cyan" style="font-size:10px;padding:1px 6px;letter-spacing:0;"><i style="font-style:normal;opacity:0.8;">🕒</i> ${escapeHtml(timing)}</span>` : ''}
                </div>
                <div class="activity-sub">
                    ${formatMoney(t.entry_price)} → ${formatMoney(t.exit_price)} • <span class="faint">${escapeHtml(t.exit_reason || 'exit')}</span>
                    ${holdStr ? ` • <span class="faint">Held ${escapeHtml(holdStr)}</span>` : ''}
                </div>
            </div>
        </div>
        <div class="activity-right">
            <div class="activity-val ${isWin ? 'text-up' : 'text-down'}">${isWin ? '+' : ''}${formatMoney(pnl)}</div>
            <div class="activity-sub ${isWin ? 'text-up' : 'text-down'}">${formatPct(t.pnl_pct)}</div>
        </div>
    </div>`;
}


async function updateDashboard() {
    try {
        const res = await fetch('/api/state', { cache: 'no-store' });
        if (!res.ok) return;
        const data = await res.json();

        totalEquityCached = Number(data.portfolio || 100000);



        // Auto-trading Button Sync
        if (data.auto_trading !== undefined) {
            autoTradingActive = !!data.auto_trading;
            const btn = document.getElementById('auto-trade-btn');
            const label = document.getElementById('auto-trade-label');
            if (btn && label) {
                btn.className = 'auto-trade-btn' + (autoTradingActive ? ' active' : ' paused');
                label.textContent = autoTradingActive ? 'AUTO TRADING ON' : 'AUTO TRADING OFF';
            }
        }

        // Header and Clock
        const clockEl = document.getElementById('clock');
        if (clockEl) clockEl.textContent = new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST';
        const phase = data.market_phase || 'MARKET CLOSED';
        const isOpen = !!data.market_open;
        const phaseBadge = document.getElementById('market-phase-badge');
        const pulseBox = document.getElementById('pulse-box');
        if (phaseBadge) {
            if (isOpen) {
                phaseBadge.textContent = 'NSE OPEN (09:15-15:30)';
                if (pulseBox) pulseBox.style.borderColor = 'rgba(16,185,129,0.3)';
            } else {
                phaseBadge.innerHTML = '<span style="color:#fb7185;">NSE CLOSED</span> · NEXT 09:15 AM';
                if (pulseBox) pulseBox.style.borderColor = 'rgba(244,63,94,0.3)';
            }
        }

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

        // Secondary Exposure Metrics
        document.getElementById('val-gross').textContent = formatMoney(data.gross_exposure);
        document.getElementById('val-net').textContent = formatMoney(data.net_exposure);
        document.getElementById('val-long').textContent = formatMoney(data.long_value);
        document.getElementById('val-short').textContent = formatMoney(data.short_notional);

        // Target Progression
        const prog = Math.max(0, Math.min(100, Number(data.progress || 0)));
        document.getElementById('progress-fill').style.width = prog + '%';
        document.getElementById('progress-percent').textContent = prog.toFixed(2) + '% of Goal';

        // Synchronize Capital Allocation if not actively sliding
        totalEquityCached = Number(data.portfolio || 100000);
        if (!isUserAdjustingAlloc && data.capital_allocation) {
            currentAlloc = data.capital_allocation;
            updateAllocDisplay();
        }

        // Render Equity SVG
        if (data.equity_curve && data.equity_curve.length > 1) {
            renderEquityCurve(data.equity_curve);
        } else {
            renderEquityCurve([data.portfolio * 0.99, data.portfolio]);
        }

        // 1. All Desks Positions (Main Tab)
        const posBody = document.getElementById('positions-body');
        const positions = data.positions || [];
        document.getElementById('pos-count').textContent = positions.length + ' OPEN';
        if (positions.length === 0) {
            posBody.innerHTML = `
                <div class="empty-state">
                    <span style="font-size:20px;opacity:0.6;">🛡️</span>
                    <span>No open positions currently held</span>
                </div>`;
        } else {
            posBody.innerHTML = positions.map(p => renderPositionCard(p, 'main')).join('');
        }

        // Orders & AMOs (Main Tab)
        const ordersBody = document.getElementById('orders-body');
        const orders = data.pending_orders || [];
        const orderCountEl = document.getElementById('order-count');
        if (orderCountEl) orderCountEl.textContent = orders.length + ' PENDING';
        if (ordersBody) {
            if (orders.length === 0) {
                ordersBody.innerHTML = `
                    <div class="empty-state">
                        <span style="font-size:20px;opacity:0.6;">📝</span>
                        <span>No pending orders queued</span>
                    </div>`;
            } else {
                ordersBody.innerHTML = orders.map(o => renderOrderCard(o)).join('');
            }
        }

        // All Desks Trades (Main Tab)
        const tradeBody = document.getElementById('trades-body');
        const trades = data.trades || [];
        if (trades.length === 0) {
            tradeBody.innerHTML = `
                <div class="empty-state">
                    <span style="font-size:20px;opacity:0.6;">📋</span>
                    <span>No execution records logged yet</span>
                </div>`;
        } else {
            tradeBody.innerHTML = trades.map(t => renderTradeRow(t)).join('');
        }

        // 2. Desk 1: Intraday (MIS Tab)
        const posIntra = data.positions_intraday || [];
        const tradesIntra = data.trades_intraday || [];
        const pIntraBody = document.getElementById('positions-intraday-body');
        const tIntraBody = document.getElementById('trades-intraday-body');
        const intraBadge = document.getElementById('intra-pos-badge');
        const intraCount = document.getElementById('intra-open-count');
        if (intraBadge) intraBadge.textContent = posIntra.length + ' OPEN';
        if (intraCount) intraCount.textContent = posIntra.length;

        if (pIntraBody) {
            if (posIntra.length === 0) {
                pIntraBody.innerHTML = `<div class="empty-state"><span style="font-size:20px;opacity:0.6;">⚡</span><span>No open intraday MIS positions</span></div>`;
            } else {
                pIntraBody.innerHTML = posIntra.map(p => renderPositionCard(p, 'intraday')).join('');
            }
        }

        const intraPnl = tradesIntra.reduce((acc, t) => acc + Number(t.pnl || 0), 0);
        const intraPnlEl = document.getElementById('intra-pnl-val');
        if (intraPnlEl) {
            intraPnlEl.textContent = formatMoney(intraPnl);
            intraPnlEl.style.color = intraPnl >= 0 ? 'var(--emerald)' : 'var(--rose)';
        }
        const intraTradeCount = document.getElementById('intra-trade-count');
        if (intraTradeCount) intraTradeCount.textContent = `${tradesIntra.length} trades today`;

        if (tIntraBody) {
            if (tradesIntra.length === 0) {
                tIntraBody.innerHTML = `<div class="empty-state"><span style="font-size:20px;opacity:0.6;">📋</span><span>No intraday trades executed today</span></div>`;
            } else {
                tIntraBody.innerHTML = tradesIntra.map(t => renderTradeRow(t)).join('');
            }
        }

        // 3. Desk 2: Stocks / Swing (CNC Tab)
        const posSwing = data.positions_swing || [];
        const tradesSwing = data.trades_swing || [];
        const pSwingBody = document.getElementById('positions-swing-body');
        const tSwingBody = document.getElementById('trades-swing-body');
        const swingBadge = document.getElementById('swing-pos-badge');
        const swingCount = document.getElementById('swing-open-count');
        if (swingBadge) swingBadge.textContent = posSwing.length + ' HELD';
        if (swingCount) swingCount.textContent = posSwing.length;

        if (pSwingBody) {
            if (posSwing.length === 0) {
                pSwingBody.innerHTML = `<div class="empty-state"><span style="font-size:20px;opacity:0.6;">📈</span><span>No swing delivery positions currently held</span></div>`;
            } else {
                pSwingBody.innerHTML = posSwing.map(p => renderPositionCard(p, 'swing')).join('');
            }
        }

        const swingPnl = tradesSwing.reduce((acc, t) => acc + Number(t.pnl || 0), 0);
        const swingPnlEl = document.getElementById('swing-pnl-val');
        if (swingPnlEl) {
            swingPnlEl.textContent = formatMoney(swingPnl);
            swingPnlEl.style.color = swingPnl >= 0 ? 'var(--emerald)' : 'var(--rose)';
        }
        const swingTradeCount = document.getElementById('swing-trade-count');
        if (swingTradeCount) swingTradeCount.textContent = `${tradesSwing.length} closed CNC trades`;

        if (tSwingBody) {
            if (tradesSwing.length === 0) {
                tSwingBody.innerHTML = `<div class="empty-state"><span style="font-size:20px;opacity:0.6;">📋</span><span>No swing trades completed yet</span></div>`;
            } else {
                tSwingBody.innerHTML = tradesSwing.map(t => renderTradeRow(t)).join('');
            }
        }

        // 4. Desk 3: Futures & Options (F&O Tab)
        const posFno = data.positions_fno || [];
        const ordersFno = data.orders_fno || (data.pending_orders || []).filter(o => String(o.product_type || '').toUpperCase() === 'FNO');
        const tradesFno = data.trades_fno || [];
        const pFnoBody = document.getElementById('positions-fno-body');
        const tFnoBody = document.getElementById('trades-fno-body');
        const fnoBadge = document.getElementById('fno-pos-badge');
        const fnoCount = document.getElementById('fno-open-count');
        if (fnoBadge) {
            if (posFno.length > 0) {
                fnoBadge.textContent = posFno.length + ' SPREADS';
            } else if (ordersFno.length > 0) {
                fnoBadge.textContent = ordersFno.length + ' QUEUED';
            } else {
                fnoBadge.textContent = '0 SPREADS';
            }
        }
        if (fnoCount) fnoCount.textContent = posFno.length + ordersFno.length;

        if (pFnoBody) {
            if (posFno.length === 0 && ordersFno.length === 0) {
                pFnoBody.innerHTML = `<div class="empty-state"><span style="font-size:20px;opacity:0.6;">🎯</span><span>No active F&O spreads or option positions</span></div>`;
            } else {
                let html = '';
                if (posFno.length > 0) {
                    html += posFno.map(p => renderPositionCard(p, 'fno')).join('');
                }
                if (ordersFno.length > 0) {
                    html += ordersFno.map(o => renderOrderCard(o)).join('');
                }
                pFnoBody.innerHTML = html;
            }
        }

        const fnoPnl = tradesFno.reduce((acc, t) => acc + Number(t.pnl || 0), 0);
        const fnoPnlEl = document.getElementById('fno-pnl-val');
        if (fnoPnlEl) {
            fnoPnlEl.textContent = formatMoney(fnoPnl);
            fnoPnlEl.style.color = fnoPnl >= 0 ? 'var(--emerald)' : 'var(--rose)';
        }
        const fnoTradeCount = document.getElementById('fno-trade-count');
        if (fnoTradeCount) fnoTradeCount.textContent = `${tradesFno.length} spreads closed`;

        if (tFnoBody) {
            if (tradesFno.length === 0) {
                tFnoBody.innerHTML = `<div class="empty-state"><span style="font-size:20px;opacity:0.6;">📋</span><span>No F&O trades closed yet</span></div>`;
            } else {
                tFnoBody.innerHTML = tradesFno.map(t => renderTradeRow(t)).join('');
            }
        }

        if (data.fno_expiry) {
            const expEl = document.getElementById('fno-expiry-badge');
            if (expEl) expEl.textContent = 'EXPIRY: ' + data.fno_expiry;
        }

        if (data.fno_pcr !== undefined) {
            const pcrVal = Number(data.fno_pcr || 1.0);
            const pcrEl = document.getElementById('fno-pcr-val');
            const sentEl = document.getElementById('fno-pcr-sentiment');
            if (pcrEl) pcrEl.textContent = pcrVal.toFixed(2);
            if (sentEl) {
                if (pcrVal >= 1.2) {
                    sentEl.textContent = 'Bullish Bias';
                    sentEl.style.color = 'var(--emerald)';
                } else if (pcrVal <= 0.8) {
                    sentEl.textContent = 'Bearish Bias';
                    sentEl.style.color = 'var(--rose)';
                } else {
                    sentEl.textContent = 'Neutral Range';
                    sentEl.style.color = 'var(--cyan)';
                }
            }
        }

        // Decisions Rendered as Stream Cards
        const decBody = document.getElementById('decisions-body');
        const decisions = data.decisions || [];
        if (decisions.length === 0) {
            decBody.innerHTML = `
                <div class="empty-state">
                    <span style="font-size:20px;opacity:0.6;">⚡</span>
                    <span>Awaiting next decision cycle...</span>
                </div>`;
        } else {
            decBody.innerHTML = decisions.slice(0, 6).map(d => {
                const act = d.action || 'WAIT';
                let pillClass = 'pill-muted';
                if (act === 'BUY') pillClass = 'pill-long';
                else if (act === 'SHORT') pillClass = 'pill-short';
                return `
                <div class="decision-card">
                    <div class="decision-head">
                        <span class="decision-sym">${escapeHtml(d.symbol)}</span>
                        <div style="display:flex;align-items:center;gap:6px;">
                            <span class="pill ${pillClass}">${escapeHtml(act)}</span>
                            <span class="pill pill-cyan">${escapeHtml(d.strategy || 'Trend')}</span>
                            <span class="faint" style="font-family:var(--font-mono);font-size:11px;">${Math.round(d.confidence || 0)}%</span>
                        </div>
                    </div>
                    <div class="decision-reason">${escapeHtml(d.reason || 'Technical setup matched model policy')}</div>
                </div>`;
            }).join('');
        }

        // Market State & Automated Shorting Status
        const m = data.market || {};
        document.getElementById('intel-regime').textContent = m.regime || 'Neutral';
        document.getElementById('intel-sentiment').textContent = m.global_sentiment || 'Neutral';
        document.getElementById('intel-phase').textContent = data.market_phase || 'Active';
        document.getElementById('intel-pipeline').textContent = m.data_ok ? 'Healthy' : 'Live Polling';

        const shortingEl = document.getElementById('intel-shorting');
        if (shortingEl) {
            const regimeStr = String(m.regime || '').toLowerCase();
            const isBearish = regimeStr.includes('strong bearish') || regimeStr.includes('bearish trend');
            if (isBearish) {
                shortingEl.textContent = 'BEAR UNLOCKED';
                shortingEl.style.color = 'var(--rose)';
            } else {
                shortingEl.textContent = 'AUTO-OFF (PROTECTED)';
                shortingEl.style.color = 'var(--emerald)';
            }
        }

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


def _enrich_trade(t):
    """Enriches trade records with human-readable IST entry and exit timestamps."""
    if not t:
        return t
    t = dict(t)
    try:
        raw_created = str(t.get("created_at") or "")
        created_dt = datetime.fromisoformat(raw_created.replace("Z", "+00:00")).astimezone(IST)
        exit_time_str = created_dt.strftime("%I:%M %p")
        exit_date_str = created_dt.strftime("%d %b %Y")
        t["exit_time_ist"] = f"{exit_date_str}, {exit_time_str}"
        t["exit_time"] = exit_time_str
        t["exit_date"] = created_dt.strftime("%Y-%m-%d")

        holding_sec = float(t.get("holding_seconds") or 0.0)
        entry_dt = created_dt - timedelta(seconds=holding_sec)
        entry_time_str = entry_dt.strftime("%I:%M %p")
        entry_date_str = entry_dt.strftime("%d %b %Y")
        t["entry_time_ist"] = f"{entry_date_str}, {entry_time_str}"
        t["entry_time"] = entry_time_str
        t["entry_date"] = entry_dt.strftime("%Y-%m-%d")

        if t["entry_date"] == t["exit_date"]:
            t["timing_display"] = f"{created_dt.strftime('%d %b')} · {entry_time_str} → {exit_time_str}"
        else:
            t["timing_display"] = f"{entry_dt.strftime('%d %b')} {entry_time_str} → {created_dt.strftime('%d %b')} {exit_time_str}"
    except Exception:
        t["exit_time_ist"] = str(t.get("created_at", ""))
        t["entry_time_ist"] = ""
        t["timing_display"] = ""
    return t


def create_app(db, cfg=None, provider=None):
    import os
    from flask import request
    cfg = cfg or {}
    flask_app = Flask(__name__)
    short_margin = cfg.get("execution", {}).get("short_margin_pct", 0.25)
    learning = LearningEngine(db, cfg)

    # BUG-011: Token-based authentication for mutating dashboard endpoints
    dashboard_token = (
        cfg.get("dashboard", {}).get("token")
        or os.environ.get("TRADING_AI_DASHBOARD_TOKEN", "")
    ).strip()

    import hmac

    @flask_app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com data: blob:;"
        )
        return response

    def _is_authorized():
        # Gate 0 (R2-001): Fail-closed auth
        fail_closed = cfg.get("dashboard", {}).get("fail_closed", False)
        if not dashboard_token:
            return not fail_closed
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        else:
            token = request.headers.get("X-API-Token") or request.args.get("token", "")
        if not token:
            return False
        return hmac.compare_digest(token, dashboard_token)

    from .ops.kill_switch import CentralKillSwitch
    from .execution import PaperExecution
    exec_engine = PaperExecution(db, cfg)
    kill_switch = CentralKillSwitch(db, exec_engine, provider, cfg)

    @flask_app.get("/")
    def home():
        return render_template_string(HTML)

    @flask_app.get("/health")
    def health():
        """BUG-031: Expose engine liveness, cycle heartbeat, and trading readiness."""
        try:
            account = db.account()
            last_cycle = db.get_last_cycle() if hasattr(db, "get_last_cycle") else None
            exceptions = db.get_exception_counts() if hasattr(db, "get_exception_counts") else {}
            data_ok = getattr(db, "_data_ok", True)
            auto_trading = db.is_auto_trading_enabled()
            is_ready = bool(account and data_ok and auto_trading)

            return jsonify({
                "version": "3.0",
                "status": "ok" if account else "degraded",
                "ready": is_ready,
                "paper_only": True,
                "database": "ok" if account else "uninitialized",
                "last_cycle_at": last_cycle,
                "data_ok": data_ok,
                "auto_trading": auto_trading,
                "exceptions": exceptions,
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

    @flask_app.get("/api/auto-trading")
    def auto_trading_status():
        return jsonify({"auto_trading": db.is_auto_trading_enabled()})

    @flask_app.post("/api/auto-trading/toggle")
    def toggle_auto_trading():
        # BUG-011: Auth check for control plane endpoint
        if not _is_authorized():
            return jsonify({"error": "Unauthorized"}), 401

        # BUG-011: Idempotent toggle support if JSON payload specifies 'enabled'
        data = request.get_json(silent=True) or {}
        if "enabled" in data:
            new_state = bool(data["enabled"])
        else:
            current = db.is_auto_trading_enabled()
            new_state = not current

        db.set_auto_trading(new_state)
        db.log("INFO", f"Auto-trading {'resumed' if new_state else 'paused'} by user from dashboard.")
        return jsonify({"auto_trading": new_state})

    @flask_app.get("/api/kill-switch")
    def kill_switch_status():
        tripped, reason = kill_switch.is_tripped()
        return jsonify({"tripped": tripped, "reason": reason})

    @flask_app.post("/api/kill-switch/flatten")
    def emergency_flatten():
        if not _is_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        closed = kill_switch.flatten_portfolio(reason="Dashboard Emergency Flatten")
        return jsonify({"status": "flattened", "closed_positions": closed})

    @flask_app.post("/api/kill-switch/reset")
    def reset_kill_switch():
        if not _is_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        kill_switch.reset()
        return jsonify({"status": "reset"})

    @flask_app.get("/api/logs")
    def stream_logs():
        from .logger import read_recent_logs
        try:
            n = int(request.args.get("lines", 100))
        except (ValueError, TypeError):
            n = 100
        logs = read_recent_logs(max_lines=min(500, max(10, n)))
        return jsonify({"logs": logs, "count": len(logs)})

    @flask_app.route("/api/capital-allocation", methods=["GET", "POST"])
    def handle_capital_allocation():
        if request.method == "POST":
            if not _is_authorized():
                return jsonify({"error": "Unauthorized"}), 401
            data = request.get_json(silent=True) or {}
            try:
                intraday = max(0.0, float(data.get("intraday", 40.0)))
                swing = max(0.0, float(data.get("swing", 40.0)))
                fno = max(0.0, float(data.get("fno", 20.0)))
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid capital allocation numbers"}), 400
            updated = db.set_capital_allocation(intraday, swing, fno)
            db.log("INFO", f"Capital allocation updated: Intraday={updated['intraday']}%, Swing={updated['swing']}%, F&O={updated['fno']}%")
            return jsonify({"status": "ok", "capital_allocation": updated})
        return jsonify(db.get_capital_allocation())

    @flask_app.get("/api/state")
    def state():
        account = db.account()
        if not account:
            return jsonify({"error": "Trading account is not initialized."}), 503

        positions = db.positions()
        raw_trades = db.trades(30)
        trades = [_enrich_trade(t) for t in raw_trades]
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

        alloc = db.get_capital_allocation()
        positions_intra = [p for p in positions if str(p.get("product_type", "INTRADAY")).upper() == "INTRADAY"]
        positions_swing = [p for p in positions if str(p.get("product_type", "")).upper() == "SWING"]
        positions_fno = [p for p in positions if str(p.get("product_type", "")).upper() == "FNO"]

        # Today's trades strictly in Indian Standard Time (IST):
        today_raw = db.trades_today() if hasattr(db, "trades_today") else []
        trades_today = [_enrich_trade(t) for t in today_raw]
        trades_intra = [t for t in trades_today if str(t.get("product_type", "INTRADAY")).upper() == "INTRADAY"]

        # Desk trades (swing and fno history)
        trades_swing_raw = db.trades_by_product("SWING", 30) if hasattr(db, "trades_by_product") else [t for t in raw_trades if str(t.get("product_type", "")).upper() == "SWING"]
        trades_fno_raw = db.trades_by_product("FNO", 30) if hasattr(db, "trades_by_product") else [t for t in raw_trades if str(t.get("product_type", "")).upper() == "FNO"]
        trades_swing = [_enrich_trade(t) for t in trades_swing_raw]
        trades_fno = [_enrich_trade(t) for t in trades_fno_raw]

        from .fno.index_chain import IndexChainManager
        fno_chain = IndexChainManager(provider)
        fno_expiry = fno_chain.get_next_expiry()
        fno_pcr = fno_chain.estimate_pcr("NIFTY")

        pending_all = db.pending_orders() if hasattr(db, "pending_orders") else []
        orders_fno = [o for o in pending_all if str(o.get("product_type", "")).upper() == "FNO"]

        return jsonify({
            "version": "3.0",
            "paper_only": True,
            "auto_trading": db.is_auto_trading_enabled(),
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
            "capital_allocation": alloc,
            "positions": positions,
            "positions_intraday": positions_intra,
            "positions_swing": positions_swing,
            "positions_fno": positions_fno,
            "trades": trades,
            "trades_intraday": trades_intra,
            "trades_swing": trades_swing,
            "trades_fno": trades_fno,
            "decisions": decisions,
            "market": market,
            "learning": learning.recommendation(),
            "market_phase": market_phase(),
            "fno_expiry": fno_expiry,
            "fno_pcr": fno_pcr,
            "market_open": market_open(),
            "orders": db.orders(50),
            "pending_orders": pending_all,
            "orders_fno": orders_fno,
            "updated_at": now_ist().isoformat(),
            "equity_curve": db.equity()
        })

    @flask_app.get("/api/orders")
    def get_orders():
        return jsonify({
            "orders": db.orders(50),
            "pending": db.pending_orders(),
            "market_open": market_open()
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


def get_app():
    """BUG-032: Factory for lazy application loading without import-time side effects."""
    return _load_runtime()


def __getattr__(name):
    """BUG-032: Lazy attribute access so importing create_app does not open the database."""
    if name == "app":
        return _load_runtime()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

if __name__ == "__main__":
    app = _load_runtime()
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
