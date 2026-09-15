import numpy as np
import pandas as pd
from datetime import datetime, timezone

from .provider import MarketDataProvider


class DemoProvider(MarketDataProvider):
    """
    Deterministic synthetic market for local paper-trading tests.

    Price/volume data is deterministic.
    Timestamps are refreshed so demo data is treated as current.
    """

    def __init__(self, symbols=None):
        self._symbols = symbols or [
            "^NSEI",
            "RELIANCE.NS",
            "TCS.NS",
            "INFY.NS",
            "SBIN.NS",
            "ITC.NS",
            "WIPRO.NS",
        ]

        self._data = {
            symbol: self._make(symbol, i)
            for i, symbol in enumerate(self._symbols)
        }

    def symbols(self):
        return self._symbols

    def _make(self, symbol, seed):
        n = 1000

        base_prices = {
            "^NSEI": 25000.0,
            "RELIANCE.NS": 1400.0,
            "TCS.NS": 3000.0,
            "INFY.NS": 1700.0,
            "SBIN.NS": 800.0,
            "ITC.NS": 400.0,
            "WIPRO.NS": 500.0,
        }

        base = base_prices.get(symbol, 100.0)

        rng = np.random.default_rng(100 + seed)

        # Overall moderate trend.
        drift = np.linspace(0.0, 0.055, n)

        # Market cycles.
        cycle = (
            0.012 * np.sin(np.arange(n) / 35.0)
            + 0.006 * np.sin(np.arange(n) / 11.0)
        )

        # Small deterministic noise.
        noise = rng.normal(0.0, 0.0018, n)

        log_price = drift + cycle + noise

        # Recent pullback followed by recovery.
        pullback_start = 930
        pullback_end = 960

        pullback = np.zeros(n)

        pullback[pullback_start:pullback_end] = np.linspace(
            0.0,
            -0.025,
            pullback_end - pullback_start,
        )

        pullback[pullback_end:] = np.linspace(
            -0.025,
            0.012,
            n - pullback_end,
        )

        log_price += pullback

        close = base * np.exp(log_price)

        open_price = np.empty(n)
        open_price[0] = close[0]
        open_price[1:] = close[:-1]

        high = np.maximum(open_price, close) * (
            1.0 + rng.uniform(0.001, 0.004, n)
        )

        low = np.minimum(open_price, close) * (
            1.0 - rng.uniform(0.001, 0.004, n)
        )

        # Deterministic volume.
        volume_cycle = (
            1.0
            + 0.30 * np.sin(np.arange(n) / 18.0)
            + 0.15 * np.sin(np.arange(n) / 7.0)
        )

        volume_noise = rng.uniform(0.85, 1.15, n)

        volume = (
            50000
            * volume_cycle
            * volume_noise
        ).astype(int)

        volume = np.maximum(volume, 1000)

        # Temporary index. It will be refreshed in history().
        idx = pd.date_range(
            end=datetime.now(timezone.utc),
            periods=n,
            freq="5min",
        )

        return pd.DataFrame(
            {
                "Open": open_price,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            },
            index=idx,
        )

    def history(self, symbol, period="3mo", interval="5m"):
        if symbol not in self._data:
            self._data[symbol] = self._make(
                symbol,
                len(self._data),
            )

        df = self._data[symbol].copy()

        # Keep the deterministic prices but move the candle timestamps
        # forward so demo data is always considered fresh.
        now = datetime.now(timezone.utc)

        new_index = pd.date_range(
            end=now,
            periods=len(df),
            freq="5min",
        )

        df.index = new_index

        return df

    def quote(self, symbol):
        df = self.history(symbol)

        return {
            "symbol": symbol,
            "price": float(df["Close"].iloc[-1]),
            "timestamp": df.index[-1].to_pydatetime(),
        }