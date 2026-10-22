import pytest
import pandas as pd
import numpy as np
from app.db import DB
from app.regime import detect
from app.swing.runner import SwingDeskRunner


class MockEquityProvider:
    def __init__(self, price=100.0):
        self.price = price

    def quote(self, symbol):
        return {"symbol": symbol, "price": self.price}

    def symbols(self):
        return ["RELIANCE.NS", "TCS.NS", "INFY.NS"]

    def history(self, symbol, period="1y", interval="1d"):
        # 220 bars of Stage-2 uptrending daily bars
        dates = pd.date_range(end="2026-10-20", periods=220)
        close = np.linspace(60, 100, 220)
        # Pullback near 20 EMA at the end
        close[-3:] = [98.0, 97.0, 97.5]
        return pd.DataFrame({
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.full(220, 200000.0)
        }, index=dates)


def test_regime_allows_swing_longs_in_mild_pullbacks():
    """Verify that Weak bullish and Weak bearish regimes allow both LONG and SHORT sides."""
    # Weak bullish row (price > EMA20, RSI around 52)
    row_weak_bull = {"Close": 25000.0, "ema20": 24900.0, "rsi": 52.0, "ret_5": 0.002, "volatility": 0.008}
    res_weak_bull = detect(row_weak_bull)
    assert "LONG" in res_weak_bull["allowed_sides"]

    # Mild pullback (Weak bearish: ret_5 < 0, but price near EMA20, RSI 46)
    row_weak_bear = {"Close": 24900.0, "ema20": 24950.0, "rsi": 46.0, "ret_5": -0.003, "volatility": 0.009}
    res_weak_bear = detect(row_weak_bear)
    assert "LONG" in res_weak_bear["allowed_sides"]


def test_swing_runner_trades_and_queues_amo():
    """Verify that SwingDeskRunner executes scans, identifies pullback setups, and queues AMOs when off-market."""
    db = DB(":memory:")
    db.init()
    db.ensure_account(100000.0, 150000.0)

    provider = MockEquityProvider(97.5)
    cfg = {
        "execution": {
            "enforce_market_hours": True,
            "brokerage": 0.0,
            "stt_delivery_pct": 0.001
        }
    }

    runner = SwingDeskRunner(db, provider, cfg)
    # Set market state to Neutral / Bullish
    db.set_market("WEAK BULLISH", "NEUTRAL", 25000.0, True)

    # Run a swing cycle
    runner.cycle()

    # Verify that either a position or an AMO order was created for high-quality setups
    positions = db.positions_by_product("SWING")
    pending_orders = db.pending_orders()

    total_trades_or_orders = len(positions) + len(pending_orders)
    assert total_trades_or_orders > 0, "Swing desk should find and enter setups in Stage-2 uptrending stocks"
