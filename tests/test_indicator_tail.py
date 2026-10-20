import numpy as np
import pandas as pd
from app.indicators import indicators

def test_indicators_up_only_frame_preserves_tail():
    idx = pd.date_range("2026-01-01", periods=60, freq="5min")
    prices = np.linspace(100, 160, 60)
    df = pd.DataFrame({
        "Open": prices - 0.5,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": np.full(60, 1000.0),
    }, index=idx)

    out = indicators(df)
    assert not out.empty
    assert out.index[-1] == df.index[-1]
    assert out.iloc[-1]["rsi"] == 100.0

def test_indicators_flat_tail_preserves_tail():
    idx = pd.date_range("2026-01-01", periods=60, freq="5min")
    # First 30 bars moving, last 30 bars completely flat
    prices = np.concatenate([np.linspace(100, 120, 30), np.full(30, 120.0)])
    df = pd.DataFrame({
        "Open": prices,
        "High": prices + 1.0,
        "Low": prices - 1.0,
        "Close": prices,
        "Volume": np.full(60, 1000.0),
    }, index=idx)

    out = indicators(df)
    assert not out.empty
    assert out.index[-1] == df.index[-1]
    assert out.iloc[-1]["rsi"] == 50.0

def test_indicators_zero_volume_index_preserves_tail():
    idx = pd.date_range("2026-01-01", periods=60, freq="5min")
    prices = np.linspace(100, 160, 60)
    df = pd.DataFrame({
        "Open": prices - 0.5,
        "High": prices + 0.5,
        "Low": prices - 0.5,
        "Close": prices,
        "Volume": np.zeros(60),
    }, index=idx)

    out = indicators(df)
    assert not out.empty
    assert out.index[-1] == df.index[-1]
    assert out.iloc[-1]["vwap"] == out.iloc[-1]["Close"]
    assert out.iloc[-1]["rel_volume"] == 1.0

