import pytest
from types import SimpleNamespace
from app.intraday.runner import IntradayDeskRunner

def test_intraday_stop_breathing_room_enforcement():
    class DummyDB:
        def __init__(self):
            self.opened_trades = []
            self.logged = []
        def is_auto_trading_enabled(self):
            return True
        def positions(self):
            return []
        def account(self):
            return {"cash": 10000.0, "starting_capital": 10000.0, "target_capital": 50000.0}
        def market(self):
            return {"regime": "Bullish Trend"}
        def get_capital_allocation(self):
            return {"intraday": 100.0, "swing": 0.0, "fno": 0.0}
        def log(self, level, msg):
            self.logged.append((level, msg))

    class DummyExecution:
        def __init__(self):
            self.calls = []
        def open_long(self, sym, qty, price, stop_loss, target, atr):
            self.calls.append({"sym": sym, "qty": qty, "price": price, "stop_loss": stop_loss, "target": target, "atr": atr})
            return True
        def open_short(self, sym, qty, price, stop_loss, target, atr):
            self.calls.append({"sym": sym, "qty": qty, "price": price, "stop_loss": stop_loss, "target": target, "atr": atr})
            return True

    class DummyProvider:
        def quote(self, sym):
            return {"price": 200.0, "volume": 1000000, "change_pct": 2.0}

    class DummyScanner:
        def scan_opening_candidates(self, universe):
            return [{"symbol": "TEST.NS", "price": 200.0, "volume": 1000000, "change_pct": 2.0}]

    class DummyStrategy:
        def evaluate(self, sym, market_regime=None):
            # Simulate a flawed strategy that proposes a 10-paise stop loss (0.05% away)
            return SimpleNamespace(
                action="BUY",
                price=200.0,
                stop_loss=199.90, # 10 paise away!
                target=205.0,
                atr=1.5,
                strategy="FlawedTightStop"
            )

    db = DummyDB()
    execution = DummyExecution()
    provider = DummyProvider()
    cfg = {
        "capital": {"starting": 10000.0, "target": 50000.0},
        "hyper_aggressive": True,
        "market": {"max_open_positions": 2},
        "risk": {"min_trade_notional": 0.0}
    }
    runner = IntradayDeskRunner(db=db, provider=provider, cfg=cfg)
    runner.execution = execution
    runner.scanner = DummyScanner()
    runner.strategy = DummyStrategy()

    # Trigger cycle
    from unittest.mock import patch
    with patch("app.intraday.runner.get_universe_symbols", return_value=["TEST.NS"]):
        runner.run_cycle()

    assert len(execution.calls) == 1
    call = execution.calls[0]
    # Entry price is 200.0
    # Minimum breathing room is max(200 * 0.008, 1.2 * 1.5) = max(1.60, 1.80) = 1.80
    # So stop_loss must be <= 200.0 - 1.80 = 198.20 (NOT 199.90!)
    assert call["stop_loss"] <= 198.20
    # Target must give at least 2:1 RR on the risk
    risk = 200.0 - call["stop_loss"]
    assert call["target"] >= 200.0 + (2.0 * risk)
