/**
 * Futures & Options (F&O) Desk JavaScript Module
 * Handles defined-risk spreads, Greeks meters, theta tracking, and expiry rules
 */

function updateFnoTab(data) {
    if (!data) return;

    const allPositions = data.positions || [];
    const fnoPositions = allPositions.filter(p => String(p.product_type || '').toUpperCase() === 'FNO');

    // 1. F&O KPI Calculations
    let fnoPnl = 0;
    let fnoMargin = 0;
    let netTheta = 0;
    let netDelta = 0;

    fnoPositions.forEach(pos => {
        fnoPnl += Number(pos.pnl || 0);
        const side = String(pos.side || 'SELL').toUpperCase();
        const isLongBuy = (side === 'LONG' || side === 'BUY');
        fnoMargin += isLongBuy
            ? (Number(pos.entry_price || 0) * Number(pos.qty || 1))
            : Number(pos.entry_cost || 0);
        // Theta decay positive for credit spreads, negative carry for long option buys
        const thetaAmt = Math.abs(Number(pos.entry_price || 0) * 0.015 * Number(pos.qty || 1));
        netTheta += isLongBuy ? -thetaAmt : thetaAmt;
    });

    const allTrades = data.trades || [];
    const fnoTrades = allTrades.filter(t => String(t.product_type || '').toUpperCase() === 'FNO');

    let closedFnoPnl = 0;
    fnoTrades.forEach(t => {
        closedFnoPnl += Number(t.pnl || 0);
    });

    const totalFnoPnl = fnoPnl + closedFnoPnl;
    const fnoPnlEl = document.getElementById('val-fno-pnl');
    const fnoPnlPill = document.getElementById('fno-pnl-pill');
    if (fnoPnlEl) {
        fnoPnlEl.textContent = (totalFnoPnl >= 0 ? '+' : '') + formatINR(totalFnoPnl);
        fnoPnlEl.className = 'stat-val ' + (totalFnoPnl >= 0 ? 'text-up' : 'text-down');
    }
    if (fnoPnlPill) {
        fnoPnlPill.textContent = (totalFnoPnl >= 0 ? '+' : '') + formatINR(totalFnoPnl);
        fnoPnlPill.className = 'pill ' + (totalFnoPnl >= 0 ? 'pill-emerald' : 'pill-rose');
    }

    const marginEl = document.getElementById('val-fno-margin');
    if (marginEl) marginEl.textContent = formatINR(fnoMargin);

    const thetaEl = document.getElementById('val-fno-theta');
    if (thetaEl) thetaEl.textContent = '+' + formatINR(netTheta) + ' / day';

    // PCR Sentiment
    const pcr = data.nifty_pcr || 1.15;
    const pcrEl = document.getElementById('val-fno-pcr');
    const pcrDescEl = document.getElementById('val-fno-pcr-desc');
    const pcrPill = document.getElementById('val-fno-pcr-pill');

    if (pcrEl) pcrEl.textContent = Number(pcr).toFixed(2);
    if (pcrDescEl) {
        pcrDescEl.textContent = pcr > 1.25 ? "Bullish Sentiment" : (pcr < 0.75 ? "Bearish Sentiment" : "Neutral Balanced");
    }
    if (pcrPill) {
        pcrPill.className = 'pill ' + (pcr > 1.25 ? 'pill-emerald' : (pcr < 0.75 ? 'pill-rose' : 'pill-cyan'));
    }

    // 2. Greeks Meters
    const deltaEl = document.getElementById('greek-delta');
    if (deltaEl) deltaEl.textContent = (netDelta >= 0 ? '+' : '') + netDelta.toFixed(2);

    const thetaMeterEl = document.getElementById('greek-theta');
    if (thetaMeterEl) thetaMeterEl.textContent = '+' + formatINR(netTheta);

    const dteEl = document.getElementById('greek-dte');
    if (dteEl && fnoPositions.length > 0 && fnoPositions[0].expiry_date) {
        dteEl.textContent = fnoPositions[0].expiry_date;
    }

    const fnoBadge = document.getElementById('fno-open-count-badge');
    if (fnoBadge) fnoBadge.textContent = `${fnoPositions.length} Spreads`;

    const fnoHistBadge = document.getElementById('fno-history-count-badge');
    if (fnoHistBadge) fnoHistBadge.textContent = `${fnoTrades.length} Trades`;

    // 3. Render Spreads Cards
    renderFnoSpreads(fnoPositions);

    // 4. Render F&O Trade Journal
    renderFnoTrades(fnoTrades);
}

function renderFnoSpreads(positions) {
    const container = document.getElementById('fno-cards-container');
    if (!container) return;

    if (!positions || positions.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <div class="empty-state-icon">🎯</div>
                <div>No active F&O spreads currently open. Spreads are initiated during favorable volatility regimes.</div>
            </div>`;
        return;
    }

    container.innerHTML = positions.map(pos => {
        const pnl = Number(pos.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const entryPrem = Number(pos.entry_price || 0);
        const curPrem = Number(pos.current_price || entryPrem);
        const side = String(pos.side || 'SELL').toUpperCase();
        const isLongBuy = (side === 'LONG' || side === 'BUY');
        const optType = String(pos.option_type || 'CE').toUpperCase();
        const badgeText = isLongBuy ? `Long ${optType} Buy` : 'Defined-Risk';
        const badgeCls = isLongBuy ? (optType === 'CE' ? 'pill-emerald' : 'pill-rose') : 'pill-cyan';
        const capUsed = isLongBuy ? (entryPrem * Number(pos.qty || 1)) : Number(pos.entry_cost || 0);
        const targetDisp = pos.target ? formatINR(pos.target) : formatINR(entryPrem * (isLongBuy ? 1.65 : 0.5));

        return `
            <div class="position-card" style="border-left: 3px solid ${isLongBuy ? 'var(--emerald)' : 'var(--cyan)'};">
                <div class="position-card-top">
                    <div>
                        <div class="position-symbol">${pos.symbol}</div>
                        <div class="position-strategy">${pos.strategy || 'Bull Put Spread'}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="pill ${badgeCls}">${badgeText}</span>
                        <div class="position-pnl ${pnlClass}" style="margin-top:4px;">
                            <span class="position-pnl-val">${pnlPrefix}${formatINR(pnl)}</span>
                        </div>
                    </div>
                </div>
                <div class="position-meta-grid">
                    <div class="meta-row"><span>Quantity:</span> <span class="meta-val">${pos.qty}</span></div>
                    <div class="meta-row"><span>Entry Premium:</span> <span class="meta-val">${formatINR(entryPrem)}</span></div>
                    <div class="meta-row"><span>Live Premium:</span> <span class="meta-val font-mono">${formatINR(curPrem)}</span></div>
                    <div class="meta-row"><span>Target / SL:</span> <span class="meta-val text-up">${targetDisp} / ${formatINR(pos.stop_loss || 0)}</span></div>
                    <div class="meta-row"><span>${isLongBuy ? 'Cost Deployed:' : 'Margin Reserved:'}</span> <span class="meta-val">${formatINR(capUsed)}</span></div>
                    <div class="meta-row"><span>Expiry Date:</span> <span class="meta-val font-mono">${pos.expiry_date || 'Thursday'}</span></div>
                </div>
            </div>`;
    }).join('');
}

function renderFnoTrades(trades) {
    const tbody = document.getElementById('fno-trades-tbody');
    if (!tbody) return;

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">No F&O spread trades closed yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = trades.map(t => {
        const pnl = Number(t.pnl || 0);
        const pnlClass = pnl >= 0 ? 'text-up' : 'text-down';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        const pnlPct = Number(t.pnl_pct || 0);
        const dateStr = t.created_at ? t.created_at.slice(0, 10) : '--';

        return `
            <tr>
                <td class="font-mono">${dateStr}</td>
                <td class="font-mono"><strong>${t.symbol}</strong></td>
                <td><span class="pill pill-cyan">${t.strategy || 'Spread'}</span></td>
                <td class="font-mono">${t.qty}</td>
                <td class="font-mono">${formatINR(t.entry_price)}</td>
                <td class="font-mono">${formatINR(t.exit_price)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${formatINR(pnl)}</td>
                <td class="font-mono ${pnlClass}">${pnlPrefix}${pnlPct.toFixed(2)}%</td>
                <td style="color:var(--text-muted); font-size:11px;">${t.exit_reason || '50% Profit Target'}</td>
            </tr>`;
    }).join('');
}

