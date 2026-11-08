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

function updateRoadmapTracker(data, portVal, dailyPnl) {
    const starting = Number(data.starting_capital || 10000);
    const target = Number(data.target_capital || data.target || 50000);
    const currEquity = Number(portVal || starting);

    // Progress percentage from starting to target
    const totalDist = Math.max(1, target - starting);
    const achieved = Math.max(0, currEquity - starting);
    const progressPct = Math.min(100, Math.max(0, (achieved / totalDist) * 100));

    // Elements
    const fillEl = document.getElementById('roadmap-bar-fill');
    if (fillEl) fillEl.style.width = progressPct.toFixed(1) + '%';

    const progPctEl = document.getElementById('roadmap-progress-pct');
    if (progPctEl) progPctEl.textContent = progressPct.toFixed(1) + '%';

    const currEqEl = document.getElementById('roadmap-curr-equity');
    if (currEqEl) currEqEl.textContent = formatINR(currEquity);

    const targetEqEl = document.getElementById('roadmap-target-equity');
    if (targetEqEl) targetEqEl.textContent = formatINR(target);

    const remValEl = document.getElementById('roadmap-remaining-val');
    if (remValEl) {
        const remaining = Math.max(0, target - currEquity);
        const remPct = currEquity > 0 ? ((remaining / currEquity) * 100).toFixed(0) : Math.round((totalDist / starting) * 100);
        remValEl.textContent = `${formatINR(remaining)} remaining (+${remPct}%)`;
    }

    // Hyper-Aggressive Daily target: +5.0% of starting capital or current equity
    const dailyTargetRupees = Math.max(starting * 0.05, currEquity * 0.05);
    const dailyTargetEl = document.getElementById('roadmap-daily-target');
    if (dailyTargetEl) dailyTargetEl.textContent = '+' + formatINR(dailyTargetRupees);

    const dailyAchievedEl = document.getElementById('roadmap-daily-achieved');
    if (dailyAchievedEl) {
        const todayPnl = Number(dailyPnl || 0);
        const todayPct = currEquity > 0 ? ((todayPnl / currEquity) * 100).toFixed(1) : '0.0';
        const prefix = todayPnl >= 0 ? '+' : '';
        dailyAchievedEl.textContent = `Today's Net: ${prefix}${formatINR(todayPnl)} (${prefix}${todayPct}%)`;
    }

    // Dynamic Milestone thresholds (25% and 62.5% of progress journey)
    const t2 = starting + (target - starting) * 0.25;
    const t3 = starting + (target - starting) * 0.625;
    const fmtK = (val) => (val >= 1000 ? `₹${(val / 1000).toFixed(0)}k` : `₹${val}`);

    // Tier badge, mode title, and milestone dots
    const tierBadge = document.getElementById('roadmap-tier-badge');
    const modeTitle = document.getElementById('roadmap-mode-title');
    const tier2Dot = document.getElementById('marker-tier2-dot');
    const tier3Dot = document.getElementById('marker-tier3-dot');
    const targetDot = document.getElementById('marker-target-dot');

    if (currEquity < t2) {
        if (tierBadge) {
            tierBadge.textContent = `⚡ HYPER-AGGRESSIVE MIS (5% DAILY)`;
            tierBadge.className = 'pill pill-rose';
        }
        if (modeTitle) {
            modeTitle.innerHTML = '⚡ Hyper-Aggressive Sniper MIS';
            modeTitle.style.color = 'var(--rose)';
        }
        if (tier2Dot) tier2Dot.classList.remove('active');
        if (tier3Dot) tier3Dot.classList.remove('active');
        if (targetDot) targetDot.classList.remove('active');
    } else if (currEquity < t3) {
        if (tierBadge) {
            tierBadge.textContent = `TIER 2: EXPANDED CAPITAL (${fmtK(t2)} → ${fmtK(t3)})`;
            tierBadge.className = 'pill pill-emerald';
        }
        if (modeTitle) {
            modeTitle.innerHTML = '📈 MIS + Swing CNC Breakouts';
            modeTitle.style.color = 'var(--emerald)';
        }
        if (tier2Dot) tier2Dot.classList.add('active');
        if (tier3Dot) tier3Dot.classList.remove('active');
        if (targetDot) targetDot.classList.remove('active');
    } else if (currEquity < target) {
        if (tierBadge) {
            tierBadge.textContent = `TIER 3: MULTI-DESK SCALE (${fmtK(t3)} → ${fmtK(target)})`;
            tierBadge.className = 'pill pill-cyan';
        }
        if (modeTitle) {
            modeTitle.innerHTML = '🎯 Full Multi-Desk (MIS + Swing + F&O)';
            modeTitle.style.color = 'var(--cyan)';
        }
        if (tier2Dot) tier2Dot.classList.add('active');
        if (tier3Dot) tier3Dot.classList.add('active');
        if (targetDot) targetDot.classList.remove('active');
    } else {
        if (tierBadge) {
            tierBadge.textContent = `🏆 GOAL REACHED (${fmtK(target)}+)`;
            tierBadge.className = 'pill pill-emerald';
        }
        if (modeTitle) {
            modeTitle.innerHTML = '👑 5x Milestone Goal Completed!';
            modeTitle.style.color = 'var(--emerald)';
        }
        if (tier2Dot) tier2Dot.classList.add('active');
        if (tier3Dot) tier3Dot.classList.add('active');
        if (targetDot) targetDot.classList.add('active');
    }

    // Days remaining estimation: log(target/currEquity) / log(1 + 0.05)
    const daysEl = document.getElementById('roadmap-est-days');
    if (daysEl) {
        if (currEquity >= target) {
            daysEl.textContent = '0 Days (Target Reached)';
        } else {
            const days = Math.ceil(Math.log(target / currEquity) / Math.log(1.05));
            daysEl.textContent = `~${days} Days`;
        }
    }
}

function updateOverviewTab(data) {
    if (!data) return;

    // 1. Total Portfolio Net Equity
    const portVal = Number(data.portfolio !== undefined ? data.portfolio : (data.equity !== undefined ? data.equity : (Number(data.cash || 0) + Number(data.long_value || 0))));
    const valPortEl = document.getElementById('val-portfolio');
    if (valPortEl) valPortEl.textContent = formatINR(portVal);

    // 2. Daily P/L
    const dailyPnl = Number(data.daily_pnl !== undefined ? data.daily_pnl : ((data.realized || 0) + (data.unrealized || 0)));
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

    const realizedToday = Number(data.realized_today !== undefined ? data.realized_today : (data.realized !== undefined ? data.realized : (data.banked_pnl || 0)));
    const unrealizedToday = Number(data.unrealized !== undefined ? data.unrealized : (data.unrealized_pnl || 0));
    const breakdownText = `Banked: ${realizedToday >= 0 ? '+' : ''}${formatINR(realizedToday)} · Live: ${unrealizedToday >= 0 ? '+' : ''}${formatINR(unrealizedToday)}`;
    const b1 = document.getElementById('val-daily-pnl-breakdown');
    const b2 = document.getElementById('val-daily-breakdown-hero');
    if (b1) b1.textContent = breakdownText;
    if (b2) b2.textContent = breakdownText;

    // 2b. Road to ₹10K Milestone Ladder Update
    updateRoadmapTracker(data, portVal, dailyPnl);

    // 3. Ready Cash & Margin
    const cashVal = Number(data.available_cash !== undefined ? data.available_cash : (data.cash || 0));
    const cashEl = document.getElementById('val-cash');
    if (cashEl) cashEl.textContent = formatINR(cashVal);

    const marginVal = Number(data.reserved_margin !== undefined ? data.reserved_margin : (data.margin_used !== undefined ? data.margin_used : (data.margin_locked || 0)));
    const marginEl = document.getElementById('val-margin');
    if (marginEl) marginEl.textContent = formatINR(marginVal);

    const positions = data.positions || [];
    const openCountEl = document.getElementById('val-open-count');
    if (openCountEl) openCountEl.textContent = positions.length;

    const allBadge = document.getElementById('all-positions-count-badge');
    if (allBadge) allBadge.textContent = `${positions.length} Open`;

    // 4. Return Badge
    const retPct = Number(data.return_pct !== undefined ? data.return_pct : 0);
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

    // 8. Sync Capital Allocation if not actively editing
    lastPortfolioEquity = Number(data.portfolio || data.equity || 100000);
    if (!isUserEditingAlloc && data.capital_allocation) {
        const ca = data.capital_allocation;
        currentAllocState = {
            intraday: Math.round(Number(ca.intraday !== undefined && ca.intraday !== null ? ca.intraday : 40)),
            swing: Math.round(Number(ca.swing !== undefined && ca.swing !== null ? ca.swing : 40)),
            fno: Math.round(Number(ca.fno !== undefined && ca.fno !== null ? ca.fno : 20))
        };
        updateCapitalAllocationUI(currentAllocState, lastPortfolioEquity);
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

// ----------------------------------------------------------------------
// 8. Capital Allocation Interactive Controls
// ----------------------------------------------------------------------

let currentAllocState = { intraday: 40, swing: 40, fno: 20 };
let isUserEditingAlloc = false;
let lastPortfolioEquity = 100000;
let allocResetTimer = null;

function updateCapitalAllocationUI(alloc, totalEquity) {
    if (!alloc) return;
    const intra = Math.max(0, Math.round(Number(alloc.intraday !== undefined && alloc.intraday !== null ? alloc.intraday : 0)));
    const swing = Math.max(0, Math.round(Number(alloc.swing !== undefined && alloc.swing !== null ? alloc.swing : 0)));
    const fno = Math.max(0, Math.round(Number(alloc.fno !== undefined && alloc.fno !== null ? alloc.fno : 0)));
    const sum = intra + swing + fno;

    // 1. Sync Segmented Bar
    const barIntra = document.getElementById('bar-alloc-intra');
    const barSwing = document.getElementById('bar-alloc-swing');
    const barFno = document.getElementById('bar-alloc-fno');
    if (barIntra) {
        barIntra.style.width = intra + '%';
        barIntra.textContent = intra > 5 ? intra + '%' : '';
    }
    if (barSwing) {
        barSwing.style.width = swing + '%';
        barSwing.textContent = swing > 5 ? swing + '%' : '';
    }
    if (barFno) {
        barFno.style.width = fno + '%';
        barFno.textContent = fno > 5 ? fno + '%' : '';
    }

    // 2. Sync Sliders & Inputs
    const sIntra = document.getElementById('slider-alloc-intra');
    const sSwing = document.getElementById('slider-alloc-swing');
    const sFno = document.getElementById('slider-alloc-fno');
    const nIntra = document.getElementById('num-alloc-intra');
    const nSwing = document.getElementById('num-alloc-swing');
    const nFno = document.getElementById('num-alloc-fno');

    if (sIntra) sIntra.value = intra;
    if (sSwing) sSwing.value = swing;
    if (sFno) sFno.value = fno;
    if (nIntra) nIntra.value = intra;
    if (nSwing) nSwing.value = swing;
    if (nFno) nFno.value = fno;

    // 3. Sync Rupees
    const eq = totalEquity || lastPortfolioEquity || 100000;
    const rIntra = document.getElementById('val-alloc-intra-rupees');
    const rSwing = document.getElementById('val-alloc-swing-rupees');
    const rFno = document.getElementById('val-alloc-fno-rupees');
    if (rIntra) rIntra.textContent = formatINR(eq * (intra / 100));
    if (rSwing) rSwing.textContent = formatINR(eq * (swing / 100));
    if (rFno) rFno.textContent = formatINR(eq * (fno / 100));

    // 4. Sum Badge
    const sumBadge = document.getElementById('alloc-sum-badge');
    if (sumBadge) {
        sumBadge.textContent = `TOTAL: ${sum}%`;
        sumBadge.className = 'pill ' + (sum === 100 ? 'pill-emerald' : (sum < 100 ? 'pill-amber' : 'pill-rose'));
    }
}

function onAllocSliderChange(desk, val) {
    isUserEditingAlloc = true;
    val = Math.max(0, Math.min(100, Math.round(Number(val) || 0)));
    const key = desk === 'intra' ? 'intraday' : desk;
    currentAllocState[key] = val;

    const numInput = document.getElementById(`num-alloc-${desk}`);
    if (numInput) numInput.value = val;

    updateCapitalAllocationUI(currentAllocState, lastPortfolioEquity);
    markEditingTimeout();
}

function onAllocInputChange(desk, val) {
    isUserEditingAlloc = true;
    val = Math.max(0, Math.min(100, Math.round(Number(val) || 0)));
    const key = desk === 'intra' ? 'intraday' : desk;
    currentAllocState[key] = val;

    const slider = document.getElementById(`slider-alloc-${desk}`);
    if (slider) slider.value = val;

    updateCapitalAllocationUI(currentAllocState, lastPortfolioEquity);
    markEditingTimeout();
}

function applyAllocPreset(intra, swing, fno) {
    isUserEditingAlloc = true;
    currentAllocState = { intraday: intra, swing: swing, fno: fno };
    updateCapitalAllocationUI(currentAllocState, lastPortfolioEquity);
    markEditingTimeout();
}

function normalizeAllocation() {
    isUserEditingAlloc = true;
    let i = Math.max(0, Math.round(Number(currentAllocState.intraday !== undefined && currentAllocState.intraday !== null ? currentAllocState.intraday : 0)));
    let s = Math.max(0, Math.round(Number(currentAllocState.swing !== undefined && currentAllocState.swing !== null ? currentAllocState.swing : 0)));
    let f = Math.max(0, Math.round(Number(currentAllocState.fno !== undefined && currentAllocState.fno !== null ? currentAllocState.fno : 0)));
    const total = i + s + f;
    if (total <= 0) {
        i = 40; s = 40; f = 20;
    } else {
        i = Math.round((i / total) * 100);
        s = Math.round((s / total) * 100);
        f = 100 - i - s;
    }
    currentAllocState = { intraday: i, swing: s, fno: f };
    updateCapitalAllocationUI(currentAllocState, lastPortfolioEquity);
    markEditingTimeout();
}

function markEditingTimeout() {
    clearTimeout(allocResetTimer);
    allocResetTimer = setTimeout(() => {
        isUserEditingAlloc = false;
    }, 15000);
}

async function saveCapitalAllocation() {
    const btn = document.getElementById('btn-save-alloc');
    const msg = document.getElementById('alloc-status-msg');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span><span>Rebalancing Jars...</span>';
    }

    try {
        const payload = {
            intraday: Math.max(0, Math.round(Number(currentAllocState.intraday !== undefined && currentAllocState.intraday !== null ? currentAllocState.intraday : 0))),
            swing: Math.max(0, Math.round(Number(currentAllocState.swing !== undefined && currentAllocState.swing !== null ? currentAllocState.swing : 0))),
            fno: Math.max(0, Math.round(Number(currentAllocState.fno !== undefined && currentAllocState.fno !== null ? currentAllocState.fno : 0)))
        };

        const res = await fetchWithAuth('/api/capital-allocation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.status === 401) {
            alert('Authentication Required: Could not save capital allocation.');
            if (msg) msg.textContent = '❌ Error 401: Unauthorized. Please check token.';
            return;
        }

        const data = await res.json();
        const updated = data.capital_allocation || payload;
        currentAllocState = {
            intraday: Math.round(Number(updated.intraday !== undefined && updated.intraday !== null ? updated.intraday : 0)),
            swing: Math.round(Number(updated.swing !== undefined && updated.swing !== null ? updated.swing : 0)),
            fno: Math.round(Number(updated.fno !== undefined && updated.fno !== null ? updated.fno : 0))
        };
        isUserEditingAlloc = false;
        updateCapitalAllocationUI(currentAllocState, lastPortfolioEquity);

        if (msg) {
            msg.textContent = `✅ Capital rebalanced: Intraday ${updated.intraday}%, Swing ${updated.swing}%, F&O ${updated.fno}%`;
            msg.style.color = 'var(--emerald)';
            setTimeout(() => {
                if (msg) {
                    msg.textContent = 'Adjust sliders and click Apply to rebalance risk jars immediately.';
                    msg.style.color = 'var(--text-muted)';
                }
            }, 6000);
        }

        fetchState();
    } catch (err) {
        alert('Failed to save capital allocation: ' + err.message);
        if (msg) {
            msg.textContent = '❌ Failed to save: ' + err.message;
            msg.style.color = 'var(--rose)';
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<span>💾</span><span>Apply & Rebalance Jars</span>';
        }
    }
}

