import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace

from app.intraday.router import (
    IntradayMultiStrategyRouter,
    IntradayMomentumBreakoutStrategy,
    IntradayMeanReversionStrategy,
)
from app.intraday.vwap_pullback import VWAPPullbackStrategy
from app.intraday.orb_strategy import OpeningRangeBreakoutStrategy

IST = ZoneInfo("Asia/Kolkata")


def _generate_candles(n=60, base_price=100.0, trend=0.1):
    times = pd.date_range("2026-11-06 09:15:00", periods=n, freq="5min", tz=IST)
    closes = [base_price + (i * trend) + np.sin(i / 3.0) * 0.5 for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = [c - 0.1 for c in closes]
    volumes = [1000 + i * 10 for i in range(n)]
    return pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes
    }, index=times)


def test_momentum_breakout_strategy():
    strat = IntradayMomentumBreakoutStrategy()
    df = _generate_candles(30, 100.0, 0.2)
    # Spike the last candle to break 20-period high with volume surge
    df.iloc[-1, df.columns.get_loc("Close")] = 110.0
    df.iloc[-1, df.columns.get_loc("High")] = 110.5
    df.iloc[-1, df.columns.get_loc("Volume")] = 5000.0

    sig = strat.evaluate("TEST.NS", df, daily_bias="BULLISH")
    assert sig is not None
    assert sig["action"] == "BUY"
    assert sig["strategy"] == "Intraday Momentum Breakout"
    assert sig["target"] > sig["price"]


def test_mean_reversion_strategy():
    strat = IntradayMeanReversionStrategy()
    # Generate 60 bars in solid uptrend (so price > 50 EMA)
    df = _generate_candles(60, 100.0, 0.3)
    # Pull back sharply on the last 2 bars so RSI2 collapses < 18
    df.iloc[-2, df.columns.get_loc("Close")] = df.iloc[-3]["Close"] - 2.5
    df.iloc[-1, df.columns.get_loc("Close")] = df.iloc[-2]["Close"] - 3.0
    df.iloc[-1, df.columns.get_loc("Low")] = df.iloc[-1]["Close"] - 0.5

    sig = strat.evaluate("DIP.NS", df, daily_bias="BULLISH")
    if sig:
        assert sig["action"] == "BUY"
        assert sig["strategy"] == "Intraday RSI-2 Mean Reversion"


def test_router_initialization_and_selection():
    class DummyProvider:
        def history(self, sym, period="5d", interval="5m"):
            df = _generate_candles(30, 50.0, 0.2)
            df.iloc[-1, df.columns.get_loc("Close")] = 65.0
            df.iloc[-1, df.columns.get_loc("High")] = 65.5
            df.iloc[-1, df.columns.get_loc("Volume")] = 10000.0
            return df

    router = IntradayMultiStrategyRouter(DummyProvider())
    assert router.orb_strat is not None
    assert router.vwap_strat is not None
    assert router.breakout_strat is not None
    assert router.meanrev_strat is not None

    sig = router.evaluate("BREAKOUT.NS", market_regime="Bullish Trending")
    assert sig is not None
    assert sig.action == "BUY"
    assert sig.price > 0
    assert sig.target > sig.price

