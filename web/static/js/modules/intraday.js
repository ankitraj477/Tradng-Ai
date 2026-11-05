/**
 * Intraday MIS Desk JavaScript Module
 * Handles 15:15 IST square-off clock, MIS margin tracking, and day trade orders
 */

function updateIntradayTab(data) {
    if (!data) return;

    const allPositions = data.positions || [];
    const intradayPositions = allPositions.filter(p => String(p.product_type || 'INTRADAY').toUpperCase() === 'INTRADAY');

    // 1. Intraday KPI Calculations
    let intraPnl = 0;
    let intraMargin = 0;

    intradayPositions.forEach(pos => {
        intraPnl += Number(pos.pnl || 0);
        intraMargin += Number(pos.entry_cost || 0);
    });

    // Also add today's closed intraday trades to intraday PnL
    const allTrades = data.trades || [];
    const intraTrades = allTrades.filter(t => String(t.product_type || 'INTRADAY').toUpperCase() === 'INTRADAY');

    let closedIntraPnl = 0;
    intraTrades.forEach(t => {
        closedIntraPnl += Number(t.pnl || 0);
    });

    const totalIntraPnl = intraPnl + closedIntraPnl;
    const intraPnlEl = document.getElementById('val-intra-pnl');
    const intraPnlPill = document.getElementById('intra-pnl-pill');
    if (intraPnlEl) {
        intraPnlEl.textContent = (totalIntraPnl >= 0 ? '+' : '') + formatINR(totalIntraPnl);
        intraPnlEl.className = 'stat-val ' + (totalIntraPnl >= 0 ? 'text-up' : 'text-down');
    }
    if (intraPnlPill) {
        intraPnlPill.textContent = (totalIntraPnl >= 0 ? '+' : '') + formatINR(totalIntraPnl);
        intraPnlPill.className = 'pill ' + (totalIntraPnl >= 0 ? 'pill-emerald' : 'pill-rose');
    }

    const intraMarginEl = document.getElementById('val-intra-margin');
    if (intraMarginEl) intraMarginEl.textContent = formatINR(intraMargin);

    const intraBadge = document.getElementById('intraday-open-count-badge');
    if (intraBadge) intraBadge.textContent = `${intradayPositions.length} Positions`;

    const intraHistBadge = document.getElementById('intra-history-count-badge');
    if (intraHistBadge) intraHistBadge.textContent = `${intraTrades.length} Trades`;

    // 2. Render Intraday Cards
    renderIntradayPositions(intradayPositions);

    // 3. Render Intraday Trades Journal
    renderIntradayTrades(intraTrades);

    // 4. Update Square-off Countdown
    updateSquareOffCountdown();
}

function updateSquareOffCountdown() {
    const label = document.getElementById('intraday-squareoff-label');
    const badge = document.getElementById('intraday-clock-badge');
    if (!label) return;

    // Target is today at 15:15:00 IST
    const now = new Date();
    // UTC offset for IST is +5.5 hours
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istNow = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);

    const target = new Date(istNow);
    target.setHours(15, 15, 0, 0);

    const diffMs = target - istNow;

    if (diffMs <= 0) {
        label.textContent = "SQUARED OFF";
        label.style.color = "var(--text-faint)";
        if (badge) {
            badge.textContent = "SESSION CLOSED";
            badge.className = "pill pill-rose";
        }
    } else {
        const diffSec = Math.floor(diffMs / 1000);
        const hrs = Math.floor(diffSec / 3600);
        const mins = Math.floor((diffSec % 3600) / 60);
        const secs = diffSec % 60;
        const fmt = `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        label.textContent = fmt;
        label.style.color = "var(--amber)";
        if (badge) {
            badge.textContent = "ACTIVE MIS CLOCK";
            badge.className = "pill pill-amber";
        }
    }
}

function renderIntradayPositions(positions) {
    const container = document.getElementById('intraday-cards-container');
    if (!container) return;

    if (!positions || positions.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="empty-state-icon">⚡</div>
                <div>No intraday MIS positions currently open. The desk scans for momentum setups between 09:15 and 14:45 IST.</div>
            </div>`;
        return;
    }

    container.innerHTML = positions.map(pos => {
        const pnl = Number(pos.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';

        return `
            <div class="position-card" style="border-left: 3px solid var(--amber);">
                <div class="position-card-top">
                    <div>
                        <div class="position-symbol">${pos.symbol}</div>
                        <div class="position-strategy">${pos.strategy || 'ORB / VWAP Breakout'}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="pill pill-amber">MIS 5x</span>
                        <div class="position-pnl ${pnlClass}" style="margin-top:4px;">
                            <span class="position-pnl-val">${pnlPrefix}${formatINR(pnl)}</span>
                        </div>
                    </div>
                </div>
                <div class="position-meta-grid">
                    <div class="meta-row"><span>Action:</span> <span class="meta-val">${pos.side || 'LONG'}</span></div>
                    <div class="meta-row"><span>Quantity:</span> <span class="meta-val">${pos.qty}</span></div>
                    <div class="meta-row"><span>Entry:</span> <span class="meta-val">${formatINR(pos.entry_price)}</span></div>
                    <div class="meta-row"><span>Market:</span> <span class="meta-val font-mono">${formatINR(pos.current_price || pos.entry_price)}</span></div>
                    <div class="meta-row"><span>Stop Loss:</span> <span class="meta-val text-down">${formatINR(pos.stop_loss)}</span></div>
                    <div class="meta-row"><span>Target:</span> <span class="meta-val text-up">${formatINR(pos.target)}</span></div>
                </div>
            </div>`;
    }).join('');
}

function renderIntradayTrades(trades) {
    const tbody = document.getElementById('intraday-trades-tbody');
    if (!tbody) return;

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">No intraday trades completed yet today.</td></tr>`;
        return;
    }

    tbody.innerHTML = trades.map(t => {
        const pnl = Number(t.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const timeStr = t.created_at ? t.created_at.slice(11, 19) : '--:--:--';
        const pnlPct = Number(t.pnl_pct || 0);

        return `
            <tr>
                <td class="font-mono">${timeStr}</td>
                <td class="font-mono"><strong>${t.symbol}</strong></td>
                <td><span class="pill ${t.action === 'BUY' ? 'pill-cyan' : 'pill-rose'}">${t.action}</span></td>
                <td class="font-mono">${t.qty}</td>
                <td class="font-mono">${formatINR(t.entry_price)}</td>
                <td class="font-mono">${formatINR(t.exit_price)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${formatINR(pnl)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${pnlPct.toFixed(2)}%</td>
                <td style="color:var(--text-muted); font-size:11px;">${t.exit_reason || 'MIS Close'}</td>
            </tr>`;
    }).join('');
}

