import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.news_archive import NewsArchive
from app.symbol_resolver import SymbolResolver
from app.event_classifier import EventClassifier
from app.event_study import EventStudy
from app.news import NewsProvider, NewsItem


def test_news_archive_deduplication(tmp_path):
    archive = NewsArchive(tmp_path / "news.db")
    h1 = archive.archive_item("Moneycontrol", "TCS bags major order", "http://test.com/1", symbols=["TCS.NS"])
    # Archiving identical item again should deduplicate
    h2 = archive.archive_item("Moneycontrol", "TCS bags major order", "http://test.com/1", symbols=["TCS.NS"])
    assert h1 == h2

    recent = archive.get_recent(limit=10)
    assert len(recent) == 1
    assert recent[0]["item_hash"] == h1

    # Filter by symbol
    by_sym = archive.get_recent(symbol="TCS.NS")
    assert len(by_sym) == 1
    by_other = archive.get_recent(symbol="NONEXISTENT.NS")
    assert len(by_other) == 0


def test_symbol_resolver_aliases_and_isins():
    resolver = SymbolResolver()

    # Match by common alias
    t1 = "Reliance Industries announced quarterly growth today"
    assert "RELIANCE.NS" in resolver.resolve(t1)

    t2 = "TCS wins digital transformation contract in Europe"
    assert "TCS.NS" in resolver.resolve(t2)

    t3 = "HDFC Bank expands branch network"
    assert "HDFCBANK.NS" in resolver.resolve(t3)

    # Match by ISIN
    t4 = "Corporate disclosure filed under ISIN INE002A01018"
    assert "RELIANCE.NS" in resolver.resolve(t4)

    # Negative check: common words should NOT trigger bogus matches
    t5 = "Government orders investigation on international borders"
    assert len(resolver.resolve(t5)) == 0


def test_event_classifier_taxonomy():
    clf = EventClassifier()

    # 1. Fraud / Probe
    res_fraud = clf.classify("CBI probe launched into accounting fraud and irregularities")
    assert res_fraud["event_type"] == "FRAUD_PROBE"
    assert res_fraud["sentiment"] == "NEGATIVE"
    assert res_fraud["materiality"] == "HIGH"

    # 2. Regulatory penalty
    res_reg = clf.classify("SEBI penalty and ban imposed on firm for compliance violation")
    assert res_reg["event_type"] == "REGULATORY"
    assert res_reg["sentiment"] == "NEGATIVE"

    # 3. Order Win
    res_order = clf.classify("Company bags order worth Rs 1,500 crore from defense ministry")
    assert res_order["event_type"] == "ORDER_WIN"
    assert res_order["sentiment"] == "POSITIVE"

    # 4. Results
    res_results = clf.classify("Q3 net profit rises 24% as revenue beats estimates")
    assert res_results["event_type"] == "RESULTS"
    assert res_results["sentiment"] == "POSITIVE"

    # 5. Caching check
    res_cached = clf.classify("Q3 net profit rises 24% as revenue beats estimates")
    assert res_cached["item_hash"] == res_results["item_hash"]


def test_news_as_risk_filter():
    clf = EventClassifier()

    # Fraud item should trigger hard halt
    bad_items = [
        NewsItem(title="ED raid and money laundering investigation initiated", url="", source="ET",
                 published="", materiality="HIGH", sentiment="NEGATIVE", symbols=("BAD_CO.NS",), event_type="FRAUD_PROBE")
    ]
    gate_bad = clf.evaluate_risk_filter("BAD_CO.NS", bad_items)
    assert gate_bad["block_entry"] is True
    assert gate_bad["reduce_size"] is True
    assert "HALT" in gate_bad["action"] or "BLOCK" in gate_bad["action"]

    # Regulatory action should block entry
    reg_items = [
        NewsItem(title="SEBI penalty notice issued to company", url="", source="ET",
                 published="", materiality="HIGH", sentiment="NEGATIVE", symbols=("REG_CO.NS",), event_type="REGULATORY")
    ]
    gate_reg = clf.evaluate_risk_filter("REG_CO.NS", reg_items)
    assert gate_reg["block_entry"] is True

    # Benign order win item should NOT block entry
    good_items = [
        NewsItem(title="Company secures order win of 200 Cr", url="", source="ET",
                 published="", materiality="MEDIUM", sentiment="POSITIVE", symbols=("GOOD_CO.NS",), event_type="ORDER_WIN")
    ]
    gate_good = clf.evaluate_risk_filter("GOOD_CO.NS", good_items)
    assert gate_good["block_entry"] is False


def test_event_study_abnormal_returns():
    dates = pd.date_range("2023-01-01", periods=30, freq="D")
    # Benchmark is flat
    bmk_df = pd.DataFrame({"Close": np.full(30, 20000.0)}, index=dates)

    # Stock jumps after event date (2023-01-10)
    stk_prices = [100.0] * 10 + [102.0, 104.0, 106.0, 107.0, 108.0] + [108.0] * 15
    stk_df = pd.DataFrame({"Close": stk_prices}, index=dates)

    events = [
        {"symbol": "WIN_CO.NS", "published_at": "2023-01-10", "event_type": "ORDER_WIN"}
    ]
    study = EventStudy(cost_pct=0.001)
    rep = study.analyze_events(events, {"WIN_CO.NS": stk_df}, bmk_df, horizons=(1, 3, 5))

    assert len(rep) == 1
    assert rep["event_type"].iloc[0] == "ORDER_WIN"
    # Post-announcement abnormal drift should be positive
    assert rep["aar_3d"].iloc[0] > 0
    assert bool(rep["profitable_3d"].iloc[0]) is True
