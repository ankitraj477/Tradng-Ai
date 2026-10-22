import pytest
import pandas as pd
import numpy as np
from app.db import DB
from app.global_markets import GlobalMarketScanner
from app.data.demo_provider import DemoProvider
from app.news import NewsProvider, NewsItem
from app.event_classifier import EventClassifier
from app.market_intelligence import MarketIntelligence
from app.risk import RiskManager


def test_global_market_scanner_sentiment():
    """Verify GlobalMarketScanner evaluates US and Asian benchmarks and outputs weighted sentiment."""
    provider = DemoProvider()
    scanner = GlobalMarketScanner(provider)
    res = scanner.scan_markets()

    assert "sentiment" in res
    assert res["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL", "HIGH RISK / CRASH")
    assert "benchmarks" in res
    assert "^GSPC" in res["benchmarks"]
    assert "^IXIC" in res["benchmarks"]
    assert "^N225" in res["benchmarks"]
    assert len(res["summary"]) > 0

    assert "indian_benchmarks" in res
    assert "^BSESN" in res["indian_benchmarks"]  # BSE SENSEX
    assert "^NSEI" in res["indian_benchmarks"]   # NIFTY 50
    assert "^NSEBANK" in res["indian_benchmarks"] # BANK NIFTY


def test_market_intelligence_with_global_scanner():
    """Verify MarketIntelligence incorporates both global market cues and financial news."""
    provider = DemoProvider()
    global_scanner = GlobalMarketScanner(provider)
    news_provider = NewsProvider()
    intel = MarketIntelligence(news_provider, global_scanner=global_scanner)

    nifty_row = {"Close": 25000.0, "ema20": 24900.0, "rsi": 55.0, "ret_5": 0.003, "volatility": 0.01}
    ctx = intel.build(nifty_row, {})

    assert "global_sentiment" in ctx
    assert ctx["global_sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL", "HIGH RISK / CRASH")
    assert "global_cues" in ctx
    assert "news_items" in ctx


def test_news_risk_gate_blocks_fraud_probe():
    """Verify that RiskManager blocks buying a stock with active regulatory/fraud probe news."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    cfg = {
        "risk": {
            "max_position_size": 20000.0,
            "max_portfolio_heat_pct": 0.10,
            "min_risk_reward": 1.5,
            "min_move_cost_multiplier": 1.5,
        }
    }
    rm = RiskManager(db, cfg)

    # 1. Proposal with FRAUD_PROBE news
    p_bad = {
        "symbol": "BAD_CORP.NS",
        "action": "BUY",
        "price": 100.0,
        "stop_loss": 95.0,
        "target": 115.0,
        "confidence": 80.0,
        "risk_reward": 3.0,
    }
    news_bad = [
        NewsItem(
            title="CBI conducts raid and searches at Bad Corp offices over accounting fraud",
            url="",
            source="ET",
            published="",
            materiality="high",
            sentiment="negative",
            symbols=("BAD_CORP.NS",),
            event_type="FRAUD_PROBE",
        )
    ]
    regime_bad = {"allowed_sides": ["LONG", "SHORT"], "size_multiplier": 1.0, "news_items": news_bad}
    decision_bad = rm.approve(p_bad, 10, regime_ctx=regime_bad)
    assert decision_bad == "REJECT", "Risk manager must reject buying stocks under fraud/raid probe"

    # 2. Proposal with benign / positive ORDER_WIN news
    p_good = {
        "symbol": "GOOD_CORP.NS",
        "action": "BUY",
        "price": 200.0,
        "stop_loss": 190.0,
        "target": 230.0,
        "confidence": 85.0,
        "risk_reward": 3.0,
    }
    news_good = [
        NewsItem(
            title="Good Corp secures major order win of 500 Cr from European client",
            url="",
            source="ET",
            published="",
            materiality="medium",
            sentiment="positive",
            symbols=("GOOD_CORP.NS",),
            event_type="ORDER_WIN",
        )
    ]
    regime_good = {"allowed_sides": ["LONG", "SHORT"], "size_multiplier": 1.0, "news_items": news_good}
    decision_good = rm.approve(p_good, 10, regime_ctx=regime_good)
    assert decision_good == "APPROVE", "Risk manager should approve good setups with positive catalyst"
