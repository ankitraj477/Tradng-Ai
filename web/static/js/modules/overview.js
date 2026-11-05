/**
 * Overview Desk JavaScript Module
 * Handles executive summary, equity curve charting, and unified trade feed
 */

let equityChartInstance = null;

function formatINR(val) {
    const num = Number(val || 0);
    return '₹' + num.toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function initEquityChart() {
    const ctx = document.getElementById('equityChart');
    if (!ctx) return;

    equityChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Portfolio Equity (₹)',
                data: [],
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56, 189, 248, 0.08)',
                borderWidth: 2,
                fill: true,
                tension: 0.25,
                pointRadius: 2,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return 'Equity: ' + formatINR(context.raw);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.04)' },
                    ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.04)' },
                    ticks: {
                        color: '#64748b',
                        font: { family: 'JetBrains Mono', size: 10 },
                        callback: function(v) { return '₹' + (v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v); }
                    }
                }
            }
        }
    });
}

function updateOverviewTab(data) {
    if (!data) return;

    // 1. Total Portfolio Net Equity
    const portVal = data.equity || (data.cash + (data.margin_locked || 0) + (data.unrealized_pnl || 0));
    const valPortEl = document.getElementById('val-portfolio');
    if (valPortEl) valPortEl.textContent = formatINR(portVal);

    // 2. Daily P/L
    const dailyPnl = data.daily_pnl || 0;
    const dailyEl = document.getElementById('val-daily-pnl');
    const dailyHeroEl = document.getElementById('val-daily-pnl-hero');
    const pnlPrefix = dailyPnl >= 0 ? '+' : '';
    const pnlClass = dailyPnl >= 0 ? 'text-up' : 'text-down';

    if (dailyEl) {
        dailyEl.textContent = pnlPrefix + formatINR(dailyPnl);
        dailyEl.className = pnlClass;
    }
    if (dailyHeroEl) {
        dailyHeroEl.textContent = pnlPrefix + formatINR(dailyPnl);
        dailyHeroEl.className = 'stat-val ' + pnlClass;
    }

    const breakdownText = `Banked: ${formatINR(data.banked_pnl || 0)} · Live: ${formatINR(data.unrealized_pnl || 0)}`;
    const b1 = document.getElementById('val-daily-pnl-breakdown');
    const b2 = document.getElementById('val-daily-breakdown-hero');
    if (b1) b1.textContent = breakdownText;
    if (b2) b2.textContent = breakdownText;

    // 3. Ready Cash & Margin
    const cashEl = document.getElementById('val-cash');
    if (cashEl) cashEl.textContent = formatINR(data.available_cash || data.cash || 0);

    const marginEl = document.getElementById('val-margin');
    if (marginEl) marginEl.textContent = formatINR(data.margin_locked || 0);

    const positions = data.positions || [];
    const openCountEl = document.getElementById('val-open-count');
    if (openCountEl) openCountEl.textContent = positions.length;

    const allBadge = document.getElementById('all-positions-count-badge');
    if (allBadge) allBadge.textContent = `${positions.length} Open`;

    // 4. Return Badge
    const retPct = data.return_pct || 0;
    const retBadge = document.getElementById('return-badge');
    if (retBadge) {
        retBadge.textContent = (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%';
        retBadge.className = 'pill ' + (retPct >= 0 ? 'pill-emerald' : 'pill-rose');
    }

    // 5. Update All Cards Grid
    renderAllPositions(positions);

    // 6. Update Equity Chart if history provided
    if (data.equity_history && Array.isArray(data.equity_history) && equityChartInstance) {
        const labels = data.equity_history.map(item => item.time ? item.time.slice(11, 19) : '');
        const values = data.equity_history.map(item => Number(item.equity || 0));
        equityChartInstance.data.labels = labels;
        equityChartInstance.data.datasets[0].data = values;
        equityChartInstance.update('none');
    }

    // 7. Render Unified Trade Log
    if (data.trades && Array.isArray(data.trades)) {
        renderUnifiedTrades(data.trades.slice(0, 10));
    }
}

function renderAllPositions(positions) {
    const container = document.getElementById('all-cards-container');
    if (!container) return;

    if (!positions || positions.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="empty-state-icon">🛡️</div>
                <div>No open positions currently active. Capital is safely preserved in liquid cash.</div>
            </div>`;
        return;
    }

    container.innerHTML = positions.map(pos => {
        const ptype = String(pos.product_type || 'INTRADAY').toUpperCase();
        const pnl = Number(pos.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const badgeColor = ptype === 'FNO' ? 'pill-cyan' : (ptype === 'SWING' ? 'pill-emerald' : 'pill-amber');

        return `
            <div class="position-card">
                <div class="position-card-top">
                    <div>
                        <div class="position-symbol">${pos.symbol}</div>
                        <div class="position-strategy">${pos.strategy || 'Momentum'}</div>
                    </div>
                    <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                        <span class="pill ${badgeColor}">${ptype}</span>
                        <div class="position-pnl ${pnlClass}">
                            <span class="position-pnl-val">${pnlPrefix}${formatINR(pnl)}</span>
                        </div>
                    </div>
                </div>
                <div class="position-meta-grid">
                    <div class="meta-row"><span>Side:</span> <span class="meta-val">${pos.side || 'LONG'}</span></div>
                    <div class="meta-row"><span>Qty:</span> <span class="meta-val">${pos.qty}</span></div>
                    <div class="meta-row"><span>Entry:</span> <span class="meta-val">${formatINR(pos.entry_price)}</span></div>
                    <div class="meta-row"><span>Current:</span> <span class="meta-val font-mono">${formatINR(pos.current_price || pos.entry_price)}</span></div>
                    <div class="meta-row"><span>Stop Loss:</span> <span class="meta-val">${formatINR(pos.stop_loss)}</span></div>
                    <div class="meta-row"><span>Target:</span> <span class="meta-val">${formatINR(pos.target)}</span></div>
                </div>
            </div>`;
    }).join('');
}

function renderUnifiedTrades(trades) {
    const tbody = document.getElementById('overview-trades-tbody');
    if (!tbody) return;

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No trades recorded yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = trades.map(t => {
        const pnl = Number(t.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const ptype = String(t.product_type || 'INTRADAY').toUpperCase();
        const badgeColor = ptype === 'FNO' ? 'pill-cyan' : (ptype === 'SWING' ? 'pill-emerald' : 'pill-amber');
        const timeStr = t.created_at ? t.created_at.slice(11, 19) : '--:--:--';

        return `
            <tr>
                <td class="font-mono" style="color:var(--text-muted);">${timeStr}</td>
                <td><span class="pill ${badgeColor}">${ptype}</span></td>
                <td class="font-mono"><strong>${t.symbol}</strong></td>
                <td><span class="pill ${t.action === 'BUY' ? 'pill-cyan' : 'pill-rose'}">${t.action}</span></td>
                <td class="font-mono">${t.qty}</td>
                <td class="font-mono">${formatINR(t.exit_price || t.entry_price)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${formatINR(pnl)}</td>
                <td style="color:var(--text-muted); font-size:11px;">${t.exit_reason || t.strategy || 'System exit'}</td>
            </tr>`;
    }).join('');
}

