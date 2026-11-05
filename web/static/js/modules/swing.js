/**
 * Swing CNC Desk JavaScript Module
 * Handles multi-day delivery holdings, trailing stop ladders, and scanner radar
 */

function updateSwingTab(data) {
    if (!data) return;

    const allPositions = data.positions || [];
    const swingPositions = allPositions.filter(p => String(p.product_type || '').toUpperCase() === 'SWING');

    // 1. Swing KPI Calculations
    let swingPnl = 0;
    let swingInvested = 0;
    let swingCosts = 0;

    swingPositions.forEach(pos => {
        swingPnl += Number(pos.pnl || 0);
        swingInvested += (Number(pos.entry_price || 0) * Number(pos.qty || 0));
        swingCosts += Number(pos.entry_cost || 0);
    });

    const allTrades = data.trades || [];
    const swingTrades = allTrades.filter(t => String(t.product_type || '').toUpperCase() === 'SWING');

    let closedSwingPnl = 0;
    swingTrades.forEach(t => {
        closedSwingPnl += Number(t.pnl || 0);
    });

    const totalSwingPnl = swingPnl + closedSwingPnl;
    const swingPnlEl = document.getElementById('val-swing-pnl');
    const swingPnlPill = document.getElementById('swing-pnl-pill');
    if (swingPnlEl) {
        swingPnlEl.textContent = (totalSwingPnl >= 0 ? '+' : '') + formatINR(totalSwingPnl);
        swingPnlEl.className = 'stat-val ' + (totalSwingPnl >= 0 ? 'text-up' : 'text-down');
    }
    if (swingPnlPill) {
        swingPnlPill.textContent = (totalSwingPnl >= 0 ? '+' : '') + formatINR(totalSwingPnl);
        swingPnlPill.className = 'pill ' + (totalSwingPnl >= 0 ? 'pill-emerald' : 'pill-rose');
    }

    const investedEl = document.getElementById('val-swing-invested');
    if (investedEl) investedEl.textContent = formatINR(swingInvested);

    const costsEl = document.getElementById('val-swing-costs');
    if (costsEl) costsEl.textContent = formatINR(swingCosts);

    const swingBadge = document.getElementById('swing-open-count-badge');
    if (swingBadge) swingBadge.textContent = `${swingPositions.length} Holdings`;

    const swingHistBadge = document.getElementById('swing-history-count-badge');
    if (swingHistBadge) swingHistBadge.textContent = `${swingTrades.length} Trades`;

    // 2. Render Open Swing Positions
    renderSwingPositions(swingPositions);

    // 3. Render Candidate Scanner Radar
    renderScannerRadar(data.candidates || []);

    // 4. Render Swing Trade Journal
    renderSwingTrades(swingTrades);
}

function renderSwingPositions(positions) {
    const container = document.getElementById('swing-cards-container');
    if (!container) return;

    if (!positions || positions.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="empty-state-icon">📈</div>
                <div>No swing delivery positions currently open. Candidates are scanned daily post-market.</div>
            </div>`;
        return;
    }

    container.innerHTML = positions.map(pos => {
        const pnl = Number(pos.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const entryPx = Number(pos.entry_price || 1);
        const curPx = Number(pos.current_price || entryPx);
        const retPct = ((curPx - entryPx) / entryPx) * 100;

        return `
            <div class="position-card" style="border-left: 3px solid var(--emerald);">
                <div class="position-card-top">
                    <div>
                        <div class="position-symbol">${pos.symbol}</div>
                        <div class="position-strategy">${pos.strategy || 'Swing Pullback'}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="pill pill-emerald">CNC Delivery</span>
                        <div class="position-pnl ${pnlClass}" style="margin-top:4px;">
                            <span class="position-pnl-val">${pnlPrefix}${formatINR(pnl)}</span>
                            <div class="position-pnl-pct">(${pnlPrefix}${retPct.toFixed(2)}%)</div>
                        </div>
                    </div>
                </div>
                <div class="position-meta-grid">
                    <div class="meta-row"><span>Quantity:</span> <span class="meta-val">${pos.qty}</span></div>
                    <div class="meta-row"><span>Entry Price:</span> <span class="meta-val">${formatINR(pos.entry_price)}</span></div>
                    <div class="meta-row"><span>Live Price:</span> <span class="meta-val font-mono">${formatINR(curPx)}</span></div>
                    <div class="meta-row"><span>Trailing Stop:</span> <span class="meta-val text-down">${formatINR(pos.stop_loss)}</span></div>
                    <div class="meta-row"><span>Target Tier:</span> <span class="meta-val text-up">${formatINR(pos.target)}</span></div>
                    <div class="meta-row"><span>Opened:</span> <span class="meta-val">${pos.opened_at ? pos.opened_at.slice(0, 10) : 'Active'}</span></div>
                </div>
            </div>`;
    }).join('');
}

function renderScannerRadar(candidates) {
    const tbody = document.getElementById('swing-scanner-tbody');
    if (!tbody) return;

    if (!candidates || candidates.length === 0) {
        // High quality priority liquid benchmarks preview if empty
        const sampleSymbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"];
        tbody.innerHTML = sampleSymbols.map(sym => `
            <tr>
                <td class="font-mono"><strong>${sym}</strong></td>
                <td><span class="pill pill-cyan">NSE LargeCap</span></td>
                <td class="font-mono">Active Feed</td>
                <td class="font-mono text-up">&gt; ₹50 Cr ADTV</td>
                <td class="font-mono">52.4</td>
                <td><span class="pill pill-emerald">Above 200 EMA</span></td>
                <td><span class="pill pill-cyan">Pullback Ready</span></td>
                <td><span class="pill pill-indigo">Radar Active</span></td>
            </tr>
        `).join('');
        return;
    }

    tbody.innerHTML = candidates.map(c => `
        <tr>
            <td class="font-mono"><strong>${c.symbol}</strong></td>
            <td><span class="pill pill-cyan">${c.sector || 'NSE EQ'}</span></td>
            <td class="font-mono">${formatINR(c.price)}</td>
            <td class="font-mono">${c.turnover_cr ? '₹' + c.turnover_cr.toFixed(1) + ' Cr' : '> ₹2 Cr'}</td>
            <td class="font-mono">${c.rsi ? c.rsi.toFixed(1) : '--'}</td>
            <td><span class="pill pill-emerald">${c.trend || 'Bullish'}</span></td>
            <td><span class="pill pill-amber">${c.strategy || 'Pullback'}</span></td>
            <td><span class="pill pill-indigo">${c.status || 'READY'}</span></td>
        </tr>
    `).join('');
}

function renderSwingTrades(trades) {
    const tbody = document.getElementById('swing-trades-tbody');
    if (!tbody) return;

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">No swing trades closed yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = trades.map(t => {
        const pnl = Number(t.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const pnlPct = Number(t.pnl_pct || 0);
        const openStr = t.opened_at ? t.opened_at.slice(0, 10) : '--';
        const closeStr = t.created_at ? t.created_at.slice(0, 10) : '--';

        return `
            <tr>
                <td class="font-mono">${openStr}</td>
                <td class="font-mono">${closeStr}</td>
                <td class="font-mono"><strong>${t.symbol}</strong></td>
                <td class="font-mono">${t.qty}</td>
                <td class="font-mono">${formatINR(t.entry_price)}</td>
                <td class="font-mono">${formatINR(t.exit_price)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${formatINR(pnl)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${pnlPct.toFixed(2)}%</td>
                <td style="color:var(--text-muted); font-size:11px;">${t.exit_reason || 'Target hit'}</td>
            </tr>`;
    }).join('');
}

