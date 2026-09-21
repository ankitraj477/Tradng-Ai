from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.data.yfinance_provider import YFinanceProvider


def _frame(age_seconds=60):
    end = (
        datetime.now(timezone.utc)
        - timedelta(seconds=age_seconds)
    )

    idx = pd.date_range(
        end=end,
        periods=80,
        freq="5min",
    )

    return pd.DataFrame(
        {
            "Open": np.full(
                80,
                100.0,
            ),
            "High": np.full(
                80,
                101.0,
            ),
            "Low": np.full(
                80,
                99.0,
            ),
            "Close": np.full(
                80,
                100.0,
            ),
            "Volume": np.full(
                80,
                1000.0,
            ),
        },
        index=idx,
    )


def test_history_rejects_stale_live_data(
    monkeypatch,
):
    provider = YFinanceProvider(
        symbols=["AAA.NS"],
        max_age_seconds=420,
    )

    monkeypatch.setattr(
        provider,
        "_download",
        lambda *args, **kwargs: _frame(
            1000
        ),
    )

    try:
        provider.history("AAA.NS")

    except RuntimeError as exc:
        assert "stale data" in str(exc)

    else:
        raise AssertionError(
            "stale live data was accepted"
        )


def test_history_many_reports_stale_and_unavailable(
    monkeypatch,
):
    provider = YFinanceProvider(
        symbols=[
            "FRESH.NS",
            "STALE.NS",
            "MISSING.NS",
        ],
        max_age_seconds=420,
    )

    fresh = _frame(60)
    stale = _frame(1000)

    columns = pd.MultiIndex.from_product(
        [
            [
                "FRESH.NS",
                "STALE.NS",
            ],
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ],
        ]
    )

    batch = pd.concat(
        [
            fresh,
            stale,
        ],
        axis=1,
        keys=[
            "FRESH.NS",
            "STALE.NS",
        ],
    )

    batch.columns = columns

    class FakeYF:

        @staticmethod
        def download(
            *args,
            **kwargs,
        ):
            return batch

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        FakeYF,
    )

    result = provider.history_many(
        provider.symbols()
    )

    stats = provider.last_batch_stats

    assert list(result) == [
        "FRESH.NS"
    ]

    assert stats["requested"] == 3
    assert stats["fresh_valid"] == 1
    assert stats["stale"] == 1
    assert stats["unavailable"] == 1

    assert stats[
        "coverage_pct"
    ] == 1 / 3

    assert not stats[
        "coverage_ok"
    ]

    assert (
        "STALE.NS"
        in stats["stale_symbols"]
    )

    assert (
        "MISSING.NS"
        in stats[
            "unavailable_symbols"
        ]
    )


def test_history_many_coverage_gate_is_configurable(
    monkeypatch,
):
    provider = YFinanceProvider(
        symbols=[
            "A.NS",
            "B.NS",
        ],
        min_fresh_data_coverage_pct=0.50,
    )

    fresh = _frame(60)

    columns = pd.MultiIndex.from_product(
        [
            [
                "A.NS",
                "B.NS",
            ],
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ],
        ]
    )

    batch = pd.concat(
        [
            fresh,
            fresh,
        ],
        axis=1,
        keys=[
            "A.NS",
            "B.NS",
        ],
    )

    batch.columns = columns

    class FakeYF:

        @staticmethod
        def download(
            *args,
            **kwargs,
        ):
            return batch

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        FakeYF,
    )

    result = provider.history_many(
        provider.symbols()
    )

    assert len(result) == 2

    assert provider.last_batch_stats[
        "coverage_ok"
    ]