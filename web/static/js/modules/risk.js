/**
 * Risk & Quant Audit JavaScript Module
 * Handles peak equity, maximum drawdown, circuit breaker status, and news sentiment
 */

function updateRiskTab(data) {
    if (!data) return;

    // 1. Peak Equity & Drawdown
    const peakVal = Number(data.peak !== undefined ? data.peak : (data.peak_equity || data.portfolio || data.equity || 100000));
    const peakEl = document.getElementById('val-risk-peak');
    if (peakEl) peakEl.textContent = formatINR(peakVal);

    const maxDdPct = Math.abs(Number(data.drawdown !== undefined ? data.drawdown : (data.max_drawdown_pct || 0)));
    const ddEl = document.getElementById('val-risk-dd');
    const ddPill = document.getElementById('val-risk-dd-pill');
    if (ddEl) ddEl.textContent = maxDdPct.toFixed(2) + '%';
    if (ddPill) {
        ddPill.textContent = maxDdPct > 10.0 ? "TIER 1" : "HEALTHY";
        ddPill.className = 'pill ' + (maxDdPct > 10.0 ? 'pill-rose' : 'pill-emerald');
    }

    // 2. Circuit Breaker Status
    const circuitEl = document.getElementById('val-circuit-status');
    const halted = data.auto_trading === false || data.halted === true;
    if (circuitEl) {
        if (halted) {
            circuitEl.textContent = "CIRCUIT HALT ACTIVE";
            circuitEl.className = "stat-val text-down";
        } else {
            circuitEl.textContent = "NORMAL ACTIVE";
            circuitEl.className = "stat-val text-up";
        }
    }

    // 3. News Sentiment Feed
    const news = data.news_stats || { total: 0, positive: 0, negative: 0, neutral: 0 };
    const newsSentEl = document.getElementById('val-news-sentiment');
    const newsCountsEl = document.getElementById('val-news-counts');
    const newsPill = document.getElementById('val-news-sentiment-pill');

    if (newsCountsEl) {
        newsCountsEl.textContent = `Total: ${news.total || 0} · Pos: ${news.positive || 0} · Neg: ${news.negative || 0}`;
    }

    let sentimentLabel = "NEUTRAL / STABLE";
    let pillClass = "pill pill-cyan";
    if (news.positive > news.negative && news.positive > 0) {
        sentimentLabel = "BULLISH CATALYST";
        pillClass = "pill pill-emerald";
    } else if (news.negative > news.positive) {
        sentimentLabel = "CAUTION / HEADWINDS";
        pillClass = "pill pill-rose";
    }

    if (newsSentEl) newsSentEl.textContent = sentimentLabel;
    if (newsPill) {
        newsPill.textContent = sentimentLabel;
        newsPill.className = pillClass;
    }
}

