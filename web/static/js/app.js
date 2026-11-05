/**
 * Tradng-Ai Multi-Desk Application Controller
 * Orchestrates real-time state polling, tab switching, and operational controls
 */

let currentTab = 'overview';
let lastStateData = null;

// Initialize on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
    initEquityChart();
    fetchState();
    setInterval(fetchState, 2000);
    setInterval(updateClock, 1000);
});

// ----------------------------------------------------------------------
// 1. Tab Switching Controller
// ----------------------------------------------------------------------

function switchDeskTab(tabName) {
    currentTab = tabName;

    // 1. Update Navigation Buttons
    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => btn.classList.remove('active'));

    const activeBtn = document.getElementById(`tab-btn-${tabName}`);
    if (activeBtn) activeBtn.classList.add('active');

    // 2. Toggle Tab Content Visibility
    const allTabs = ['overview', 'intraday', 'swing', 'fno', 'risk'];
    allTabs.forEach(name => {
        const el = document.getElementById(`tab-${name}`);
        if (el) {
            el.style.display = (name === tabName) ? 'flex' : 'none';
        }
    });

    // 3. Re-render current tab with cached data
    if (lastStateData) {
        dispatchTabUpdates(lastStateData);
    }
}

// ----------------------------------------------------------------------
// 2. Real-Time State Polling Engine
// ----------------------------------------------------------------------

async function fetchState() {
    try {
        const res = await fetch('/api/state');
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();
        lastStateData = data;

        // 1. Update Header Status
        updateHeader(data);

        // 2. Dispatch to Active and Registered Modules
        dispatchTabUpdates(data);
    } catch (err) {
        console.error('State poll failed:', err);
        const pulse = document.getElementById('market-phase-badge');
        if (pulse) pulse.textContent = 'RECONNECTING...';
    }
}

function updateHeader(data) {
    // 1. Market Phase
    const phase = String(data.market_phase || 'CLOSED').toUpperCase();
    const phaseBadge = document.getElementById('market-phase-badge');
    const pulseDot = document.getElementById('pulse-dot');

    if (phaseBadge) phaseBadge.textContent = phase;
    if (pulseDot) {
        pulseDot.className = 'pulse-dot ' + (phase === 'REGULAR' ? 'open' : (phase === 'PRE_OPEN' ? 'preopen' : 'closed'));
    }

    // 2. Auto-Trading Button State
    const autoBtn = document.getElementById('auto-trade-btn');
    const autoLabel = document.getElementById('auto-trade-label');
    const isAuto = data.auto_trading !== false;

    if (autoBtn) {
        autoBtn.className = 'auto-trade-btn ' + (isAuto ? 'active' : '');
    }
    if (autoLabel) {
        autoLabel.textContent = isAuto ? 'AUTO TRADING ON' : 'AUTO TRADING PAUSED';
    }
}

function dispatchTabUpdates(data) {
    // Always update overview
    updateOverviewTab(data);

    // Update specific tab components
    if (currentTab === 'intraday' || currentTab === 'overview') {
        updateIntradayTab(data);
    }
    if (currentTab === 'swing' || currentTab === 'overview') {
        updateSwingTab(data);
    }
    if (currentTab === 'fno' || currentTab === 'overview') {
        updateFnoTab(data);
    }
    if (currentTab === 'risk' || currentTab === 'overview') {
        updateRiskTab(data);
    }
}

// ----------------------------------------------------------------------
// 3. Operational Action Controls & Authentication
// ----------------------------------------------------------------------

function getAuthToken() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    if (urlToken) {
        localStorage.setItem('tradng_dashboard_token', urlToken);
        document.cookie = `tradng_token=${urlToken}; path=/; SameSite=Strict`;
        return urlToken;
    }
    const stored = localStorage.getItem('tradng_dashboard_token');
    if (stored) return stored;
    return 'tradng-pro-2026';
}

async function fetchWithAuth(url, options = {}) {
    const token = getAuthToken();
    const headers = options.headers || {};
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
        headers['X-API-Token'] = token;
    }
    return fetch(url, { ...options, headers });
}

async function toggleAutoTrading() {
    try {
        const res = await fetchWithAuth('/api/auto-trading/toggle', { method: 'POST' });
        if (res.status === 401) {
            alert('Authentication Required: Invalid or missing token.');
            return;
        }
        const result = await res.json();
        fetchState();
    } catch (err) {
        alert('Failed to toggle auto trading: ' + err.message);
    }
}

function openKillSwitchModal() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'flex';
}

function closeKillSwitchModal() {
    const modal = document.getElementById('kill-switch-modal');
    if (modal) modal.style.display = 'none';
}

async function executeKillSwitch() {
    const btn = document.getElementById('btn-confirm-kill-switch');
    const reasonInput = document.getElementById('kill-switch-reason');
    const reason = reasonInput ? reasonInput.value : 'Operator Manual Flatten';

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'FLATTENING ALL...';
    }

    try {
        const res = await fetchWithAuth('/api/kill-switch/flatten', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason })
        });
        if (res.status === 401) {
            alert('Authentication Required: Invalid or missing token.');
            return;
        }
        const result = await res.json();
        closeKillSwitchModal();
        alert(`Emergency Flatten Complete: ${result.closed_count || 0} positions closed.`);
        fetchState();
    } catch (err) {
        alert('Kill switch execution failed: ' + err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Confirm & Flatten All';
        }
    }
}

function updateClock() {
    const clockEl = document.getElementById('clock');
    if (!clockEl) return;
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istNow = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);
    clockEl.textContent = istNow.toTimeString().slice(0, 8) + ' IST';
}

