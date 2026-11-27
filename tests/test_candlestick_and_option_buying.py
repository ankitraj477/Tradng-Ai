import json
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest

from app.accounting import portfolio_metrics
from app.candlestick_patterns import CandlestickAnalyzer
from app.dashboard import create_app
from app.db import DB
from app.fno.execution import FNOExecution
from app.fno.index_chain import IndexChainManager
from app.fno.option_buying import OptionBuyingStrategy
from app.fno.position_manager import FNOPositionManager
from app.fno.runner import FnoDeskRunner


def _make_bars(rows):
    idx = pd.date_range("2026-11-27 09:30", periods=len(rows), freq="5min", tz="Asia/Kolkata")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


def _base_neutral_bars(n=20, base=25800.0):
    rows = []
    for i in range(n):
        p = base + (i % 2) * 4.0
        rows.append((p, p + 8.0, p - 6.0, p + 2.0, 100000.0))
    return rows


def test_candlestick_bullish_and_bearish_engulfing():
    # Bullish Engulfing after slight dip
    rows = _base_neutral_bars(20, base=25800.0)
    rows[-2] = (25810.0, 25812.0, 25792.0, 25795.0, 110000.0)   # Red candle
    rows[-1] = (25792.0, 25835.0, 25790.0, 25832.0, 190000.0)   # Large green engulfing
    df_bull = _make_bars(rows)
    res_bull = CandlestickAnalyzer.analyze(df_bull)
    assert res_bull["bias"] == "BULLISH"
    assert "Bullish Engulfing" in res_bull["patterns_detected"]
    assert res_bull["strength"] >= 78.0

    # Bearish Engulfing
    rows_b = _base_neutral_bars(20, base=25800.0)
    rows_b[-2] = (25795.0, 25814.0, 25794.0, 25810.0, 110000.0)  # Green candle
    rows_b[-1] = (25813.0, 25815.0, 25770.0, 25772.0, 195000.0)  # Large red engulfing
    df_bear = _make_bars(rows_b)
    res_bear = CandlestickAnalyzer.analyze(df_bear)
    assert res_bear["bias"] == "BEARISH"
    assert "Bearish Engulfing" in res_bear["patterns_detected"]
    assert res_bear["strength"] >= 78.0


def test_candlestick_hammer_and_shooting_star():
    rows = _base_neutral_bars(20, base=25800.0)
    rows[-1] = (25788.0, 25802.0, 25745.0, 25800.0, 160000.0)  # Long lower wick hammer (body ~21%)
    res_h = CandlestickAnalyzer.analyze(_make_bars(rows))
    assert res_h["bias"] == "BULLISH"
    assert "Hammer" in res_h["patterns_detected"]

    rows_s = _base_neutral_bars(20, base=25800.0)
    rows_s[-1] = (25812.0, 25855.0, 25798.0, 25800.0, 165000.0)  # Long upper wick shooting star (body ~21%)
    res_s = CandlestickAnalyzer.analyze(_make_bars(rows_s))
    assert res_s["bias"] == "BEARISH"
    assert "Shooting Star" in res_s["patterns_detected"]


def test_candlestick_morning_and_evening_star():
    rows = _base_neutral_bars(20, base=25800.0)
    rows[-3] = (25830.0, 25832.0, 25790.0, 25792.0, 120000.0)  # Big red
    rows[-2] = (25790.0, 25795.0, 25784.0, 25789.0, 90000.0)   # Small star
    rows[-1] = (25792.0, 25830.0, 25790.0, 25825.0, 175000.0)  # Strong green closing > mid
    res_m = CandlestickAnalyzer.analyze(_make_bars(rows))
    assert res_m["bias"] == "BULLISH"
    assert "Morning Star" in res_m["patterns_detected"]

    rows_e = _base_neutral_bars(20, base=25800.0)
    rows_e[-3] = (25790.0, 25832.0, 25788.0, 25830.0, 120000.0)  # Big green
    rows_e[-2] = (25831.0, 25838.0, 25827.0, 25832.0, 90000.0)   # Small star
    rows_e[-1] = (25828.0, 25830.0, 25792.0, 25795.0, 180000.0)  # Strong red closing < mid
    res_ev = CandlestickAnalyzer.analyze(_make_bars(rows_e))
    assert res_ev["bias"] == "BEARISH"
    assert "Evening Star" in res_ev["patterns_detected"]


class _MockOptionProvider:
    def __init__(self, spot, bars_df):
        self._spot = spot
        self._bars = bars_df

    def quote(self, sym):
        return {"price": self._spot, "volume": 1000000, "change_pct": 0.5}

    def history(self, sym, period="5d", interval="5m"):
        return self._bars


def test_option_buying_strategy_proposes_call_and_put():
    # Bullish Engulfing -> Buy CE
    rows_ce = _base_neutral_bars(25, base=25800.0)
    rows_ce[-2] = (25812.0, 25814.0, 25790.0, 25792.0, 120000.0)
    rows_ce[-1] = (25790.0, 25850.0, 25788.0, 25846.0, 240000.0)
    prov_ce = _MockOptionProvider(25846.0, _make_bars(rows_ce))
    strat_ce = OptionBuyingStrategy(chain_manager=IndexChainManager(prov_ce))
    prop_ce = strat_ce.propose("NIFTY", market_regime="Weak bullish")
    assert prop_ce is not None
    assert prop_ce["action"] == "BUY"
    assert prop_ce["side"] == "LONG"
    assert prop_ce["option_type"] == "CE"
    assert prop_ce["stop_loss"] == round(prop_ce["price"] * 0.72, 2)
    assert prop_ce["target"] == round(prop_ce["price"] * 1.65, 2)
    assert "Bullish Engulfing" in prop_ce["strategy"]

    # Bearish Engulfing -> Buy PE
    rows_pe = _base_neutral_bars(25, base=25800.0)
    rows_pe[-2] = (25790.0, 25814.0, 25788.0, 25812.0, 120000.0)
    rows_pe[-1] = (25814.0, 25816.0, 25750.0, 25754.0, 250000.0)
    prov_pe = _MockOptionProvider(25754.0, _make_bars(rows_pe))
    strat_pe = OptionBuyingStrategy(chain_manager=IndexChainManager(prov_pe))
    prop_pe = strat_pe.propose("NIFTY", market_regime="Weak bearish")
    assert prop_pe is not None
    assert prop_pe["action"] == "BUY"
    assert prop_pe["side"] == "LONG"
    assert prop_pe["option_type"] == "PE"
    assert "Bearish Engulfing" in prop_pe["strategy"]


def test_long_option_execution_accounting_and_overview_pnl(tmp_path):
    db = DB(str(tmp_path / "opt_buy.db"))
    db.init()
    db.ensure_account(10000.0, 50000.0)
    cfg = {"execution": {"enforce_market_hours": False}}
    exe = FNOExecution(db, cfg)

    proposal = {
        "symbol": "NIFTY-2026-12-03-25800CE",
        "action": "BUY",
        "side": "LONG",
        "price": 60.0,
        "stop_loss": 43.2,
        "target": 99.0,
        "lot_size": 25,
        "strategy": "NIFTY Long Call (Bullish Engulfing)",
        "confidence": 85.0,
        "strike_price": 25800.0,
        "option_type": "CE",
        "expiry_date": "2026-12-03",
        "spot": 25800.0,
        "legs_info": json.dumps([{"action": "BUY", "type": "CE", "strike": 25800, "qty": 25}]),
    }

    assert exe.open_option_buy(proposal, lots=1, force_fill=True) is True
    acc = db.account()
    # 10000 - (60 * 25 + 25 fee) = 8475.0
    assert acc["cash"] == pytest.approx(8475.0)

    # Simulate option price rising to ₹85 (+₹25/sh = +₹625 unrealized)
    db.update_current_price("NIFTY-2026-12-03-25800CE", 85.0)
    metrics = portfolio_metrics(db.account(), db.positions(), 0.25)
    # Equity = 8475 + (25 * 85 = 2125) = 10600 (no double counting!)
    assert metrics["equity"] == pytest.approx(10600.0)
    assert metrics["long_unrealized"] == pytest.approx(625.0)

    # Overview API must compute positive PnL for LONG FNO option
    app = create_app(db=db, cfg=cfg)
    resp = app.test_client().get("/api/state")
    assert resp.status_code == 200
    data = resp.get_json()
    pos_fno = data["positions_fno"][0]
    assert pos_fno["pnl"] == pytest.approx(625.0)
    assert pos_fno["pnl_pct"] == pytest.approx(41.67, abs=0.1)

    # Trailing stop escalation and close (with 200-pt index rally for moneyness-scaled delta)
    prov = _MockOptionProvider(26000.0, _make_bars(_base_neutral_bars(20, 26000.0)))
    pm = FNOPositionManager(db, exe, IndexChainManager(prov), cfg)
    now_dt = datetime.now(timezone.utc) + timedelta(minutes=20)
    closed = pm.manage(dt=now_dt)
    assert closed == 1  # Target hit via delta+gamma expansion

    trades = db.trades(10)
    assert len(trades) == 1
    assert trades[0]["action"] == "SELL_TO_CLOSE"
    assert trades[0]["side"] == "LONG"
    assert trades[0]["pnl"] > 500.0
    assert db.account()["cash"] > 10500.0
