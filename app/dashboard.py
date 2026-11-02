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
    <title>Tradng-Ai v4.2 · Kid-Friendly & Mobile-First Terminal</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
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
            --amber: #f59e0b;
            --amber-bg: rgba(245, 158, 11, 0.12);
            --indigo: #6366f1;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --radius-lg: 18px;
            --radius-md: 12px;
            --radius-sm: 8px;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: var(--font-sans);
            background: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            -webkit-font-smoothing: antialiased;
        }

        /* Top Header */
        header {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(12, 18, 30, 0.88);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border);
            padding: 10px 16px;
        }
        .header-inner {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .logo-icon {
            width: 36px;
            height: 36px;
            border-radius: 10px;
            background: linear-gradient(135deg, #0284c7, #38bdf8);
            color: #0f172a;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: 900;
            box-shadow: 0 0 16px rgba(56, 189, 248, 0.35);
        }
        .brand-text h1 {
            font-size: 17px;
            font-weight: 800;
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .brand-badge {
            font-size: 10px;
            padding: 2px 7px;
            border-radius: 6px;
            background: rgba(56, 189, 248, 0.15);
            color: var(--cyan);
            border: 1px solid rgba(56, 189, 248, 0.25);
            font-family: var(--font-mono);
            font-weight: 700;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        /* View Mode Switcher (Kid vs Pro) */
        .mode-toggle {
            display: inline-flex;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 3px;
        }
        .mode-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 5px 11px;
            border-radius: 16px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .mode-btn.active {
            background: var(--cyan);
            color: #070d18;
            box-shadow: 0 2px 8px rgba(56, 189, 248, 0.3);
        }

        /* Auto-Trade Button */
        .auto-trade-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            border: 1px solid transparent;
            transition: all 0.2s ease;
        }
        .auto-trade-btn.active {
            background: rgba(16, 185, 129, 0.15);
            border-color: rgba(16, 185, 129, 0.35);
            color: var(--emerald);
        }
        .auto-trade-btn.paused {
            background: rgba(244, 63, 94, 0.15);
            border-color: rgba(244, 63, 94, 0.35);
            color: var(--rose);
        }
        .auto-trade-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: currentColor;
            box-shadow: 0 0 8px currentColor;
        }

        .pulse-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 600;
            padding: 5px 10px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            border: 1px solid var(--border-subtle);
        }
        .pulse-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--emerald);
            animation: pulse-ring 2s infinite ease-out;
        }
        @keyframes pulse-ring {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        /* Main Container */
        main {
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
            padding: 16px 16px 90px 16px;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        /* Desktop Segmented Navigation Tabs */
        .tabs-wrapper {
            overflow-x: auto;
            scrollbar-width: none;
            -ms-overflow-style: none;
            margin-bottom: 2px;
        }
        .tabs-wrapper::-webkit-scrollbar { display: none; }
        .tabs {
            display: flex;
            gap: 6px;
            background: rgba(12, 18, 30, 0.6);
            padding: 4px;
            border-radius: 12px;
            border: 1px solid var(--border);
            width: max-content;
        }
        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 13px;
            font-weight: 600;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }
        .tab-btn:hover { color: var(--text-main); background: rgba(255, 255, 255, 0.04); }
        .tab-btn.active {
            background: var(--cyan);
            color: #070d18;
            font-weight: 700;
            box-shadow: 0 2px 8px rgba(56, 189, 248, 0.25);
        }

        /* Hero Piggy Bank Card (Kid-Friendly & Clear) */
        .hero-card {
            background: linear-gradient(135deg, rgba(16, 25, 42, 0.95) 0%, rgba(12, 18, 30, 0.98) 100%);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 22px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
            position: relative;
            overflow: hidden;
        }
        .hero-card::after {
            content: '';
            position: absolute;
            top: 0; right: 0;
            width: 250px; height: 250px;
            background: radial-gradient(circle, rgba(56, 189, 248, 0.08) 0%, transparent 70%);
            pointer-events: none;
        }
        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 18px;
        }
        .hero-equity-label {
            font-size: 13px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .hero-equity-val {
            font-size: clamp(30px, 5vw, 44px);
            font-weight: 800;
            font-family: var(--font-mono);
            letter-spacing: -0.03em;
            color: #fff;
            margin: 4px 0 2px 0;
        }
        .hero-kid-explainer {
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.5;
            background: rgba(56, 189, 248, 0.06);
            border: 1px solid rgba(56, 189, 248, 0.15);
            padding: 8px 12px;
            border-radius: 10px;
            margin-top: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .hero-badges {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }

        /* 4 Friendly Money Jars (Responsive Grid) */
        .hero-stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }
        .stat-item {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 14px 16px;
            transition: transform 0.15s ease, border-color 0.15s ease;
        }
        .stat-item:hover {
            border-color: var(--border-hover);
            transform: translateY(-2px);
        }
        .stat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .stat-label {
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .stat-val {
            font-size: 20px;
            font-weight: 800;
            font-family: var(--font-mono);
            color: var(--text-main);
            letter-spacing: -0.02em;
        }
        .stat-desc {
            font-size: 11px;
            color: var(--text-faint);
            margin-top: 4px;
            line-height: 1.4;
        }

        /* Pill Badges */
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 9px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 700;
            font-family: var(--font-mono);
            letter-spacing: 0.02em;
        }
        .pill-long { background: var(--emerald-bg); color: var(--emerald); border: 1px solid rgba(16, 185, 129, 0.25); }
        .pill-short { background: var(--rose-bg); color: var(--rose); border: 1px solid rgba(244, 63, 94, 0.25); }
        .pill-cyan { background: var(--cyan-bg); color: var(--cyan); border: 1px solid rgba(56, 189, 248, 0.25); }
        .pill-amber { background: var(--amber-bg); color: var(--amber); border: 1px solid rgba(245, 158, 11, 0.25); }

        /* Kid-Friendly Game Cards for Active Trades */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .section-title {
            font-size: 16px;
            font-weight: 800;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section-sub {
            font-size: 12px;
            color: var(--text-muted);
        }

        .cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 14px;
        }

        .trade-game-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 18px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
            display: flex;
            flex-direction: column;
            gap: 12px;
            transition: all 0.2s ease;
        }
        .trade-game-card:hover {
            border-color: var(--cyan);
            background: var(--bg-card-hover);
        }
        .card-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 10px;
        }
        .card-title-box h3 {
            font-size: 16px;
            font-weight: 800;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .card-meta-line {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 3px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .card-pnl-box {
            text-align: right;
        }
        .card-pnl-val {
            font-size: 18px;
            font-weight: 800;
            font-family: var(--font-mono);
        }
        .card-pnl-sub {
            font-size: 11px;
            font-weight: 700;
        }

        /* Kid Explainer Callout Box inside Card */
        .kid-story-box {
            background: rgba(56, 189, 248, 0.05);
            border: 1px solid rgba(56, 189, 248, 0.15);
            border-radius: 10px;
            padding: 10px 12px;
            font-size: 12px;
            line-height: 1.45;
            color: #e2e8f0;
        }
        .kid-story-box strong { color: var(--cyan); }

        /* Progress Meter for Theta Decay */
        .decay-meter-container {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 10px 12px;
        }
        .decay-meter-header {
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .decay-meter-bar {
            height: 8px;
            width: 100%;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            overflow: hidden;
            position: relative;
        }
        .decay-meter-fill {
            height: 100%;
            border-radius: 4px;
            background: linear-gradient(90deg, var(--cyan), var(--emerald));
            transition: width 0.4s ease;
        }
        .decay-meter-footer {
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 5px;
            font-family: var(--font-mono);
        }

        /* Safety Boundaries Bar */
        .safety-strip {
            display: flex;
            gap: 8px;
            font-size: 11px;
            padding: 8px 10px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 8px;
            border: 1px solid var(--border-subtle);
            flex-wrap: wrap;
            justify-content: space-between;
        }

        /* Legs Collapse Box */
        .legs-accordion {
            border-top: 1px solid var(--border-subtle);
            padding-top: 10px;
        }
        .legs-toggle-btn {
            background: none;
            border: none;
            color: var(--cyan);
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 0;
        }
        .legs-details {
            margin-top: 8px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 11px;
            font-family: var(--font-mono);
        }
        .leg-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.02);
            padding: 4px 8px;
            border-radius: 6px;
        }

        /* AI Activity Feed (Plain English) */
        .activity-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 16px;
        }
        .activity-item {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid var(--border-subtle);
        }
        .activity-item:last-child { border-bottom: none; }
        .activity-icon-badge {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 15px;
            flex-shrink: 0;
        }
        .activity-content { flex: 1; }
        .activity-headline {
            font-size: 13px;
            font-weight: 700;
            color: var(--text-main);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .activity-desc {
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 2px;
            line-height: 1.4;
        }
        .activity-time {
            font-size: 11px;
            color: var(--text-faint);
            font-family: var(--font-mono);
            margin-top: 4px;
        }

        /* Quantitative Exposure & Allocation (Visible in Pro Mode) */
        .pro-section {
            display: none;
            flex-direction: column;
            gap: 14px;
        }
        body.pro-mode .pro-section { display: flex; }

        .exposure-strip {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
        }
        .exposure-box {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 14px;
        }
        .exposure-box .lbl { font-size: 11px; color: var(--text-muted); }
        .exposure-box .val { font-size: 16px; font-weight: 800; font-family: var(--font-mono); margin-top: 2px; }

        /* Allocation Sliders */
        .alloc-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 16px;
        }
        .alloc-bar {
            height: 14px;
            border-radius: 7px;
            display: flex;
            overflow: hidden;
            background: rgba(255, 255, 255, 0.05);
            margin: 10px 0;
        }
        .alloc-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
        }
        .alloc-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 10px;
        }
        .alloc-slider {
            width: 100%;
            accent-color: var(--cyan);
            margin-top: 6px;
        }

        /* Mobile Bottom Sticky Navigation */
        .mobile-bottom-nav {
            display: none;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 64px;
            background: rgba(12, 18, 30, 0.94);
            backdrop-filter: blur(20px);
            border-top: 1px solid var(--border);
            z-index: 200;
            padding: 6px 12px;
            justify-content: space-around;
            align-items: center;
        }
        .mob-nav-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            font-size: 11px;
            font-weight: 700;
            cursor: pointer;
            padding: 6px 16px;
            border-radius: 12px;
            transition: all 0.2s ease;
            touch-action: manipulation;
        }
        .mob-nav-btn.active {
            color: var(--cyan);
            background: rgba(56, 189, 248, 0.12);
        }
        .mob-nav-btn:active { transform: scale(0.94); }
        .mob-icon { font-size: 18px; }

        /* Mobile Breakpoints */
        @media (max-width: 768px) {
            .mobile-bottom-nav { display: flex; }
            .tabs-wrapper { display: none; }
            main { padding: 10px 10px 84px 10px; }
            .hero-card { padding: 16px; }
            .hero-equity-val { font-size: 30px !important; }
            .hero-stats-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
            .stat-item { padding: 10px; }
            .stat-val { font-size: 16px !important; }
            .cards-grid { grid-template-columns: 1fr; }
            .trade-game-card { padding: 14px; }
            #clock { display: none; }
        }

        .text-up { color: var(--emerald) !important; }
        .text-down { color: var(--rose) !important; }
        .text-cyan { color: var(--cyan) !important; }
        .faint { color: var(--text-faint) !important; }
    </style>
</head>
<body>

<header>
    <div class="header-inner">
        <div class="brand">
            <div class="logo-icon">AI</div>
            <div class="brand-text">
                <h1>Tradng-Ai <span class="brand-badge">PRO v4.2</span></h1>
            </div>
        </div>
        <div class="header-controls">
            <!-- Mode Toggle: Kid-Simple vs Pro Trader -->
            <div class="mode-toggle">
                <button id="btn-mode-simple" class="mode-btn active" onclick="switchMode('simple')">
                    <span>🧒</span> Simple View
                </button>
                <button id="btn-mode-pro" class="mode-btn" onclick="switchMode('pro')">
                    <span>🔬</span> Pro Trader
                </button>
            </div>

            <!-- Auto-Trading Live Switch -->
            <button id="auto-trade-btn" class="auto-trade-btn active" onclick="toggleAutoTrading()" title="Click to Pause / Resume Auto-Trading">
                <span class="auto-trade-dot"></span>
                <span id="auto-trade-label">AUTO TRADING ON</span>
            </button>

            <!-- Market Phase Indicator -->
            <div id="pulse-box" class="pulse-indicator">
                <span class="pulse-dot"></span>
                <span id="market-phase-badge">CHECKING...</span>
            </div>
            <div id="clock" class="stat-label" style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);">--:--:-- IST</div>
        </div>
    </div>
</header>

<main>
    <!-- Desktop Navigation Tabs -->
    <div class="tabs-wrapper">
        <div class="tabs">
            <button id="tab-overview-btn" class="tab-btn active" onclick="switchDeskTab('overview')">🏠 Simple Overview</button>
            <button id="tab-fno-btn" class="tab-btn" onclick="switchDeskTab('fno')">🎯 Options Safe Spreads (F&O)</button>
            <button id="tab-intraday-btn" class="tab-btn" onclick="switchDeskTab('intraday')">⚡ Day Trades (MIS)</button>
            <button id="tab-swing-btn" class="tab-btn" onclick="switchDeskTab('swing')">📈 Stock Holdings (CNC)</button>
            <button id="tab-pro-btn" class="tab-btn" onclick="switchDeskTab('pro')">🔬 Quant & Audit Terminal</button>
        </div>
    </div>

    <!-- SECTION 1: THE PIGGY BANK (Total Balance & Jars) -->
    <div id="sec-overview" style="display:flex; flex-direction:column; gap:16px;">
        <div class="hero-card">
            <div class="hero-top">
                <div>
                    <div class="hero-equity-label">💰 My Total Balance (Cash + Safety Deposit + Profits)</div>
                    <div id="val-portfolio" class="hero-equity-val">₹0.00</div>
                    <div class="hero-kid-explainer">
                        <span>💡</span>
                        <span><strong>Automatic & Live:</strong> Updates every 2 seconds without selling! Time decay puts profit directly in your pocket.</span>
                    </div>
                </div>
                <div class="hero-badges">
                    <span id="return-badge" class="pill pill-cyan">0.00%</span>
                    <span id="pnl-status-pill" class="pill pill-long">PROFITABLE</span>
                </div>
            </div>

            <!-- 4 Visual Money Jars -->
            <div class="hero-stats-grid">
                <div class="stat-item">
                    <div class="stat-header">
                        <span class="stat-label">💵 Ready Cash</span>
                        <span class="pill pill-cyan" style="font-size:9px;">AVAILABLE</span>
                    </div>
                    <div id="val-cash" class="stat-val">₹0.00</div>
                    <div class="stat-desc">Cash ready in your wallet for safe trades.</div>
                </div>

                <div class="stat-item">
                    <div class="stat-header">
                        <span class="stat-label">🔒 Safety Deposit</span>
                        <span class="pill pill-amber" style="font-size:9px;">REFUNDABLE</span>
                    </div>
                    <div id="val-margin" class="stat-val">₹0.00</div>
                    <div class="stat-desc">Exchange margin. Returns 100% to cash when trades finish!</div>
                </div>

                <div class="stat-item">
                    <div class="stat-header">
                        <span class="stat-label">🟢 Live Profit Right Now</span>
                        <span class="pill pill-long" style="font-size:9px;">GROWING</span>
                    </div>
                    <div id="val-unrealized-hero" class="stat-val text-up">+₹0.00</div>
                    <div class="stat-desc">Live open profits decaying into green today.</div>
                </div>

                <div class="stat-item">
                    <div class="stat-header">
                        <span class="stat-label">🤖 AI Bot Status</span>
                        <span id="robot-status-pill" class="pill pill-cyan" style="font-size:9px;">ACTIVE</span>
                    </div>
                    <div id="val-bot-status" class="stat-val" style="font-size:16px;color:var(--cyan);">GUARDING</div>
                    <div id="progress-percent" class="stat-desc" style="color:var(--text-muted);">100% Capital Preserved</div>
                </div>
            </div>
        </div>

        <!-- Pro Mode Only: Exposure Strip & Allocation Controls -->
        <div class="pro-section">
            <div class="exposure-strip">
                <div class="exposure-box">
                    <div class="lbl">Gross Exposure</div>
                    <div id="val-gross" class="val">₹0.00</div>
                </div>
                <div class="exposure-box">
                    <div class="lbl">Net Exposure</div>
                    <div id="val-net" class="val">₹0.00</div>
                </div>
                <div class="exposure-box">
                    <div class="lbl">Long Notional</div>
                    <div id="val-long" class="val text-up">₹0.00</div>
                </div>
                <div class="exposure-box">
                    <div class="lbl">Short Notional</div>
                    <div id="val-short" class="val text-down">₹0.00</div>
                </div>
            </div>

            <!-- Allocation Card -->
            <div class="alloc-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                    <div>
                        <div style="font-weight:700; font-size:14px;">Multi-Desk Capital Allocation</div>
                        <div style="font-size:11px; color:var(--text-muted);">Adjust proportion of capital between Intraday, Swing, and F&O desks. Total must equal 100%.</div>
                    </div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span id="alloc-sum-badge" class="pill pill-cyan">TOTAL: 100%</span>
                        <button class="pill pill-long" style="cursor:pointer; background:var(--emerald); color:#070d18; border:none; padding:6px 12px;" onclick="saveCapitalAllocation()">Save Allocation</button>
                    </div>
                </div>
                <div class="alloc-bar">
                    <div id="bar-alloc-intra" style="background:var(--cyan); width:34%; display:flex; align-items:center; justify-content:center; color:#070d18; font-size:10px; font-weight:800; font-family:var(--font-mono);">34%</div>
                    <div id="bar-alloc-swing" style="background:var(--emerald); width:33%; display:flex; align-items:center; justify-content:center; color:#070d18; font-size:10px; font-weight:800; font-family:var(--font-mono);">33%</div>
                    <div id="bar-alloc-fno" style="background:var(--indigo); width:33%; display:flex; align-items:center; justify-content:center; color:#fff; font-size:10px; font-weight:800; font-family:var(--font-mono);">33%</div>
                </div>
                <div class="alloc-grid">
                    <div class="alloc-item">
                        <div style="font-size:12px; font-weight:700;">⚡ Day Trades (MIS)</div>
                        <input id="slider-alloc-intra" type="range" class="alloc-slider" min="0" max="100" value="34" oninput="onAllocSliderChange('intra', this.value)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; margin-top:4px;">
                            <span id="num-alloc-intra">34%</span>
                            <span id="val-alloc-intra-rupees" class="faint">₹34,000</span>
                        </div>
                    </div>
                    <div class="alloc-item">
                        <div style="font-size:12px; font-weight:700;">📈 Stocks (CNC)</div>
                        <input id="slider-alloc-swing" type="range" class="alloc-slider" min="0" max="100" value="33" oninput="onAllocSliderChange('swing', this.value)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; margin-top:4px;">
                            <span id="num-alloc-swing">33%</span>
                            <span id="val-alloc-swing-rupees" class="faint">₹33,000</span>
                        </div>
                    </div>
                    <div class="alloc-item">
                        <div style="font-size:12px; font-weight:700;">🎯 Options Spreads (F&O)</div>
                        <input id="slider-alloc-fno" type="range" class="alloc-slider" min="0" max="100" value="33" oninput="onAllocSliderChange('fno', this.value)">
                        <div style="display:flex; justify-content:space-between; font-size:11px; margin-top:4px;">
                            <span id="num-alloc-fno">33%</span>
                            <span id="val-alloc-fno-rupees" class="faint">₹33,000</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- SECTION 2: ACTIVE TRADES (Kid-Friendly Cards) -->
        <div>
            <div class="section-header">
                <div class="section-title">
                    <span>🎯</span> Active Investments (<span id="pos-count">0 OPEN</span>)
                </div>
                <div class="section-sub">Real-time defined-risk spreads working right now</div>
            </div>
            <div id="positions-container" class="cards-grid">
                <!-- Dynamically populated by JS renderGameCards -->
            </div>
        </div>

        <!-- SECTION 3: RECENT ACTIVITY & WINS -->
        <div>
            <div class="section-header">
                <div class="section-title">
                    <span>📜</span> Recent Wins & Activity
                </div>
                <div class="section-sub">Plain English explanations of what the AI did</div>
            </div>
            <div class="activity-card">
                <div id="trades-container">
                    <!-- Dynamically populated by JS renderActivityFeed -->
                </div>
            </div>
        </div>
    </div>

    <!-- DESK TABS (Intraday, Swing, F&O, Pro Terminal) -->
    <div id="sec-fno" style="display:none; flex-direction:column; gap:14px;">
        <div class="section-header">
            <div class="section-title">🎯 Futures & Options Desk (Defined-Risk Spreads)</div>
        </div>
        <div id="fno-cards-container" class="cards-grid"></div>
        <div class="activity-card" style="margin-top:14px;">
            <div style="font-size:14px; font-weight:700; margin-bottom:10px;">Options Trade History</div>
            <div id="fno-trades-container"></div>
        </div>
    </div>

    <div id="sec-intraday" style="display:none; flex-direction:column; gap:14px;">
        <div class="section-header">
            <div class="section-title">⚡ Day Trading Desk (MIS)</div>
        </div>
        <div id="intraday-cards-container" class="cards-grid"></div>
        <div class="activity-card" style="margin-top:14px;">
            <div style="font-size:14px; font-weight:700; margin-bottom:10px;">Day Trades Closed Today</div>
            <div id="intraday-trades-container"></div>
        </div>
    </div>

    <div id="sec-swing" style="display:none; flex-direction:column; gap:14px;">
        <div class="section-header">
            <div class="section-title">📈 Stock Investment Desk (CNC Delivery)</div>
        </div>
        <div id="swing-cards-container" class="cards-grid"></div>
        <div class="activity-card" style="margin-top:14px;">
            <div style="font-size:14px; font-weight:700; margin-bottom:10px;">Stock Portfolio History</div>
            <div id="swing-trades-container"></div>
        </div>
    </div>

    <div id="sec-pro" style="display:none; flex-direction:column; gap:14px;">
        <div class="section-header">
            <div class="section-title">🔬 Quantitative Research & Engine Health</div>
        </div>
        <div class="hero-card">
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px;">
                <div class="stat-item">
                    <div class="stat-label">System Peak Equity</div>
                    <div id="val-peak" class="stat-val">₹0.00</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Maximum Drawdown</div>
                    <div id="val-dd" class="stat-val" style="color:var(--rose);">0.00%</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Nifty Put-Call Ratio (PCR)</div>
                    <div id="val-pcr" class="stat-val" style="color:var(--cyan);">1.02</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Next Options Expiry</div>
                    <div id="val-expiry" class="stat-val" style="font-size:16px;">2026-11-05</div>
                </div>
            </div>
            <div style="margin-top:16px;">
                <div style="font-size:13px; font-weight:700; color:var(--text-muted); margin-bottom:8px;">Strategy Machine Learning Weights</div>
                <div id="learning-weights-container" style="display:flex; flex-wrap:wrap; gap:6px;"></div>
            </div>
        </div>
    </div>
</main>

<!-- MOBILE STICKY BOTTOM NAVIGATION BAR -->
<nav class="mobile-bottom-nav">
    <button id="mob-btn-overview" class="mob-nav-btn active" onclick="switchMobileTab('overview')">
        <span class="mob-icon">🏠</span>
        <span>Money</span>
    </button>
    <button id="mob-btn-trades" class="mob-nav-btn" onclick="switchMobileTab('trades')">
        <span class="mob-icon">🎯</span>
        <span>Trades</span>
    </button>
    <button id="mob-btn-activity" class="mob-nav-btn" onclick="switchMobileTab('activity')">
        <span class="mob-icon">📜</span>
        <span>Activity</span>
    </button>
    <button id="mob-btn-controls" class="mob-nav-btn" onclick="switchMobileTab('controls')">
        <span class="mob-icon">⚙️</span>
        <span>Controls</span>
    </button>
</nav>

<script>
// Format Currency in INR
const formatMoney = val => '₹' + Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatPct = val => (Number(val || 0) >= 0 ? '+' : '') + Number(val || 0).toFixed(2) + '%';

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Mode Switching (Kid-Simple vs Pro Trader)
function switchMode(mode) {
    const isPro = (mode === 'pro');
    document.body.classList.toggle('pro-mode', isPro);
    document.getElementById('btn-mode-simple').classList.toggle('active', !isPro);
    document.getElementById('btn-mode-pro').classList.toggle('active', isPro);
    try { localStorage.setItem('tradng_ai_mode', mode); } catch (e) {}
}

// Restore saved mode if any
try {
    const savedMode = localStorage.getItem('tradng_ai_mode');
    if (savedMode === 'pro') switchMode('pro');
} catch (e) {}

// Desktop Desk Tab Switcher
function switchDeskTab(tab) {
    const sections = ['overview', 'fno', 'intraday', 'swing', 'pro'];
    sections.forEach(s => {
        const el = document.getElementById('sec-' + s);
        const btn = document.getElementById('tab-' + s + '-btn');
        if (el) el.style.display = (s === tab) ? 'flex' : 'none';
        if (btn) btn.className = 'tab-btn' + (s === tab ? ' active' : '');
    });
}

// Mobile Bottom Navigation Tab Switcher
function switchMobileTab(tab) {
    document.querySelectorAll('.mob-nav-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.getElementById('mob-btn-' + tab);
    if (btn) btn.classList.add('active');

    // Show main overview container
    switchDeskTab('overview');

    if (tab === 'overview') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (tab === 'trades') {
        const posEl = document.getElementById('positions-container');
        if (posEl) posEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else if (tab === 'activity') {
        const actEl = document.getElementById('trades-container');
        if (actEl) actEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else if (tab === 'controls') {
        switchMode(document.body.classList.contains('pro-mode') ? 'simple' : 'pro');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// Auto-Trading Live Toggle
let autoTradingActive = true;
async function toggleAutoTrading() {
    try {
        const res = await fetch('/api/auto-trading/toggle', { method: 'POST' });
        const json = await res.json();
        autoTradingActive = json.enabled;
        const btn = document.getElementById('auto-trade-btn');
        const label = document.getElementById('auto-trade-label');
        if (btn) {
            btn.className = 'auto-trade-btn' + (autoTradingActive ? ' active' : ' paused');
        }
        if (label) {
            label.textContent = autoTradingActive ? 'AUTO TRADING ON' : 'AUTO TRADING OFF';
        }
    } catch (e) {
        console.error('Failed to toggle auto trading:', e);
    }
}

// Render Kid-Friendly Game Cards for Active Trades
function renderGameCard(p) {
    const sym = String(p.symbol || '');
    const pType = String(p.product_type || 'INTRADAY').toUpperCase();
    const isLong = (p.side === 'LONG');
    const entry = Number(p.entry_price || 0);
    const curr = Number(p.current_price || entry);
    const qty = Number(p.qty || 1);
    const pnl = isLong ? (curr - entry) * qty : (entry - curr) * qty;
    const pnlPct = entry > 0 ? ((pnl / (entry * qty)) * 100).toFixed(2) : '0.00';
    const isProfit = (pnl >= 0);

    let friendlyTitle = sym;
    let storyHtml = '';
    let decayHtml = '';
    let safetyHtml = '';
    let legsHtml = '';

    if (pType === 'FNO') {
        const maxProfitPerShare = entry * 0.50;
        const currentGainPerShare = Math.max(0, entry - curr);
        const progress = Math.min(100, Math.max(0, (currentGainPerShare / maxProfitPerShare) * 100)).toFixed(0);

        if (sym.includes('CONDOR')) {
            friendlyTitle = '🎯 Bank Nifty Safe Trap (Iron Condor)';
            storyHtml = `
                <div class="kid-story-box">
                    <strong>🤖 The AI's Prediction:</strong> Bank Nifty will stay trapped between <strong>54,000</strong> and <strong>55,600</strong>. It is right in the safe center! Every passing hour decays option price, putting money directly into your pocket.
                </div>`;
            safetyHtml = `
                <div class="safety-strip">
                    <span>🛡️ Floor: <strong>54,000</strong></span>
                    <span>📍 Spot: <strong>54,850</strong></span>
                    <span>🏰 Roof: <strong>55,600</strong></span>
                    <span class="text-down">Exit SL: ₹${(entry * 2.0).toFixed(1)}</span>
                </div>`;
        } else if (sym.includes('BPS')) {
            friendlyTitle = '🛡️ Nifty Safety Floor (Bull Put Spread)';
            storyHtml = `
                <div class="kid-story-box">
                    <strong>🤖 The AI's Prediction:</strong> Nifty 50 will stay above <strong>22,900</strong>. Right now Nifty is hundreds of points safely above the danger zone! As long as it holds, you keep 100% of the profits.
                </div>`;
            safetyHtml = `
                <div class="safety-strip">
                    <span>🛡️ Safety Floor: <strong>22,900</strong></span>
                    <span>📍 Spot: <strong>23,300 (+400 pts safe)</strong></span>
                    <span class="text-down">Exit SL: ₹${(entry * 2.0).toFixed(1)}</span>
                </div>`;
        }

        decayHtml = `
            <div class="decay-meter-container">
                <div class="decay-meter-header">
                    <span>⏳ 50% Profit Goal Progress</span>
                    <span class="text-up">${progress}% Reached</span>
                </div>
                <div class="decay-meter-bar">
                    <div class="decay-meter-fill" style="width:${progress}%;"></div>
                </div>
                <div class="decay-meter-footer">
                    <span>Entry: ${formatMoney(entry)}/sh</span>
                    <span class="text-cyan">Now: ${formatMoney(curr)}/sh</span>
                    <span class="text-up">Goal: ${formatMoney(entry * 0.50)}/sh</span>
                </div>
            </div>`;

        if (p.legs_info) {
            try {
                const legs = typeof p.legs_info === 'string' ? JSON.parse(p.legs_info) : p.legs_info;
                if (Array.isArray(legs) && legs.length > 0) {
                    legsHtml = `
                        <div class="legs-accordion">
                            <button class="legs-toggle-btn" onclick="toggleLegs(this)">
                                <span>🛡️</span> View ${legs.length} Insurance Wings ▼
                            </button>
                            <div class="legs-details" style="display:none;">
                                ${legs.map(l => {
                                    const isSell = (l.action || '').toUpperCase() === 'SELL';
                                    const actColor = isSell ? 'var(--rose)' : 'var(--emerald)';
                                    return `
                                        <div class="leg-row">
                                            <span><strong style="color:${actColor}">${l.action}</strong> ${l.name || (l.strike + ' ' + l.type)}</span>
                                            <span class="faint">${l.qty || qty} Qty</span>
                                        </div>`;
                                }).join('')}
                            </div>
                        </div>`;
                }
            } catch (e) {}
        }
    } else {
        friendlyTitle = `⚡ ${sym} (${pType})`;
        storyHtml = `<div class="kid-story-box">Holding ${qty} shares of ${sym}. Safety Stop Loss active.</div>`;
    }

    return `
        <div class="trade-game-card">
            <div class="card-top">
                <div class="card-title-box">
                    <h3>${escapeHtml(friendlyTitle)}</h3>
                    <div class="card-meta-line">
                        <span class="pill pill-cyan">${escapeHtml(pType)} · ${qty} QTY</span>
                        <span>Entry: ${formatMoney(entry)}</span>
                    </div>
                </div>
                <div class="card-pnl-box">
                    <div class="card-pnl-val ${isProfit ? 'text-up' : 'text-down'}">
                        ${isProfit ? '+ ' : ''}${formatMoney(pnl)}
                    </div>
                    <div class="card-pnl-sub ${isProfit ? 'text-up' : 'text-down'}">
                        (${isProfit ? '+' : ''}${pnlPct}%)
                    </div>
                </div>
            </div>

            ${storyHtml}
            ${decayHtml}
            ${safetyHtml}
            ${legsHtml}
        </div>`;
}

function toggleLegs(btn) {
    const details = btn.nextElementSibling;
    if (details) {
        const isHidden = (details.style.display === 'none');
        details.style.display = isHidden ? 'flex' : 'none';
        btn.innerHTML = isHidden ? '<span>🛡️</span> Hide Insurance Wings ▲' : '<span>🛡️</span> View Insurance Wings ▼';
    }
}

// Render Human-Readable Activity Feed
function renderActivityFeed(t) {
    const pnl = Number(t.pnl || 0);
    const isWin = (pnl >= 0);
    const sym = escapeHtml(t.symbol || '');
    const reason = escapeHtml(t.exit_reason || 'Target reached');
    const timeStr = escapeHtml(t.timing_display || t.exit_time_ist || t.created_at || '');

    return `
        <div class="activity-item">
            <div class="activity-icon-badge" style="background:${isWin ? 'var(--emerald-bg)' : 'var(--rose-bg)'}; color:${isWin ? 'var(--emerald)' : 'var(--rose)'};">
                ${isWin ? '🏆' : '🛡️'}
            </div>
            <div class="activity-content">
                <div class="activity-headline">
                    <span>${sym}</span>
                    <span class="${isWin ? 'text-up' : 'text-down'}" style="font-family:var(--font-mono); font-weight:800;">
                        ${isWin ? '+ ' : ''}${formatMoney(pnl)}
                    </span>
                </div>
                <div class="activity-desc">${reason}</div>
                <div class="activity-time">${timeStr}</div>
            </div>
        </div>`;
}

// Allocation Sliders
let currentAlloc = { intraday: 34, swing: 33, fno: 33 };
function onAllocSliderChange(desk, val) {
    val = Number(val);
    currentAlloc[desk === 'intra' ? 'intraday' : desk] = val;
    const sum = currentAlloc.intraday + currentAlloc.swing + currentAlloc.fno;
    
    document.getElementById('num-alloc-' + desk).textContent = val + '%';
    document.getElementById('bar-alloc-' + desk).style.width = val + '%';
    document.getElementById('bar-alloc-' + desk).textContent = val + '%';

    const sumBadge = document.getElementById('alloc-sum-badge');
    if (sumBadge) {
        sumBadge.textContent = 'TOTAL: ' + sum + '%';
        sumBadge.className = 'pill ' + (sum === 100 ? 'pill-long' : 'pill-short');
    }
}

async function saveCapitalAllocation() {
    try {
        const res = await fetch('/api/allocation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentAlloc)
        });
        const json = await res.json();
        alert('Capital Allocation saved: ' + JSON.stringify(json.allocation));
    } catch (e) {
        alert('Failed to save allocation: ' + e);
    }
}

// Clock IST
function updateClock() {
    const el = document.getElementById('clock');
    if (el) {
        const now = new Date();
        el.textContent = now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }) + ' IST';
    }
}
setInterval(updateClock, 1000);
updateClock();

// Live Dashboard State Poller (Every 2 Seconds)
async function updateDashboard() {
    try {
        const res = await fetch('/api/state');
        if (!res.ok) return;
        const data = await res.json();

        // 1. Total Balance & Badges
        const pf = Number(data.portfolio || 100000);
        const starting = 100000.0;
        const returnPct = ((pf - starting) / starting) * 100;
        
        document.getElementById('val-portfolio').textContent = formatMoney(pf);
        const retBadge = document.getElementById('return-badge');
        if (retBadge) {
            retBadge.textContent = formatPct(returnPct);
            retBadge.className = 'pill ' + (returnPct >= 0 ? 'pill-long' : 'pill-short');
        }

        // 2. Money Jars
        document.getElementById('val-cash').textContent = formatMoney(data.available_cash || data.cash);
        document.getElementById('val-margin').textContent = formatMoney(data.reserved_margin);
        
        const unEl = document.getElementById('val-unrealized-hero');
        const unVal = Number(data.unrealized || 0);
        if (unEl) {
            unEl.textContent = (unVal >= 0 ? '+ ' : '') + formatMoney(unVal);
            unEl.className = 'stat-val ' + (unVal >= 0 ? 'text-up' : 'text-down');
        }

        // Robot Status
        const isOpen = Boolean(data.market_open);
        const phaseBadge = document.getElementById('market-phase-badge');
        if (phaseBadge) {
            phaseBadge.textContent = isOpen ? 'MARKET LIVE' : 'MARKET CLOSED';
            phaseBadge.className = isOpen ? 'text-up' : 'faint';
        }

        const botStatus = document.getElementById('val-bot-status');
        if (botStatus) {
            botStatus.textContent = isOpen ? 'ACTIVE & GUARDING' : 'RESTING (CLOSED)';
            botStatus.style.color = isOpen ? 'var(--emerald)' : 'var(--cyan)';
        }

        // 3. Pro Mode Metrics
        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setEl('val-gross', formatMoney(data.gross_exposure));
        setEl('val-net', formatMoney(data.net_exposure));
        setEl('val-long', formatMoney(data.long_value));
        setEl('val-short', formatMoney(data.short_notional));
        setEl('val-peak', formatMoney(data.peak));
        setEl('val-dd', Number(data.drawdown || 0).toFixed(2) + '%');
        setEl('val-pcr', Number(data.fno_pcr || 1.02).toFixed(2));
        setEl('val-expiry', data.fno_expiry || 'Weekly');

        // 4. Render Active Game Cards
        const positions = data.positions || [];
        document.getElementById('pos-count').textContent = positions.length + ' OPEN';
        const posCont = document.getElementById('positions-container');
        if (posCont) {
            if (positions.length === 0) {
                posCont.innerHTML = `
                    <div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--text-muted); background: var(--bg-card); border-radius: var(--radius-lg); border: 1px solid var(--border);">
                        <div style="font-size: 28px; margin-bottom: 6px;">🛡️</div>
                        <div style="font-size: 14px; font-weight: 700;">Zero Risk: No Open Positions</div>
                        <div style="font-size: 12px; margin-top: 4px;">All money is 100% safe in cash wallet.</div>
                    </div>`;
            } else {
                posCont.innerHTML = positions.map(renderGameCard).join('');
            }
        }

        // Desk Sub-Containers
        const fnoCont = document.getElementById('fno-cards-container');
        if (fnoCont) {
            const fnoPos = positions.filter(p => String(p.product_type || '').toUpperCase() === 'FNO');
            fnoCont.innerHTML = fnoPos.length ? fnoPos.map(renderGameCard).join('') : '<div class="faint">No open F&O spreads</div>';
        }

        const intraCont = document.getElementById('intraday-cards-container');
        if (intraCont) {
            const intraPos = positions.filter(p => String(p.product_type || '').toUpperCase() === 'INTRADAY');
            intraCont.innerHTML = intraPos.length ? intraPos.map(renderGameCard).join('') : '<div class="faint">No open day trades</div>';
        }

        const swingCont = document.getElementById('swing-cards-container');
        if (swingCont) {
            const swingPos = positions.filter(p => String(p.product_type || '').toUpperCase() === 'SWING');
            swingCont.innerHTML = swingPos.length ? swingPos.map(renderGameCard).join('') : '<div class="faint">No open stock investments</div>';
        }

        // 5. Render Activity Feed
        const trades = data.trades || [];
        const tradesCont = document.getElementById('trades-container');
        if (tradesCont) {
            if (trades.length === 0) {
                tradesCont.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);">No closed trades logged yet.</div>';
            } else {
                tradesCont.innerHTML = trades.slice(0, 8).map(renderActivityFeed).join('');
            }
        }

        // 6. Strategy Learning Weights
        const weightsBox = document.getElementById('learning-weights-container');
        if (weightsBox && data.learning && data.learning.strategy_weights) {
            weightsBox.innerHTML = Object.entries(data.learning.strategy_weights).map(([k, v]) => `
                <div class="pill pill-cyan">${escapeHtml(k)}: ${Number(v).toFixed(2)}x</div>
            `).join('');
        }
    } catch (e) {
        console.error('Dashboard refresh error:', e);
    }
}

// Initial fetch & loop every 2 seconds
updateDashboard();
setInterval(updateDashboard, 2000);
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
                "version": "4.2",
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
            "version": "4.2",
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

