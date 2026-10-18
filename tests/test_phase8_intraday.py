from datetime import datetime, time
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pytest

from app.intraday.timing import IntradayTimingManager
from app.intraday.vwap import calculate_session_vwap
from app.intraday.orb_strategy import OpeningRangeBreakoutStrategy
from app.intraday.execution import IntradayExecutionEngine

IST = ZoneInfo("Asia/Kolkata")


def make_dt(date_str, time_str):
    return datetime.fromisoformat(f"{date_str}T{time_str}:00").replace(tzinfo=IST)


def test_intraday_timing_windows():
    timing = IntradayTimingManager()

    # 1. Opening range (09:15 - 09:30): no entries allowed
    dt_open = make_dt("2026-09-15", "09:20")
    assert timing.get_phase(dt_open) == "OPENING_RANGE"
    assert timing.can_enter(dt_open) is False
    assert timing.must_square_off(dt_open) is False

    # 2. Active trading window (09:30 - 14:45): entries allowed
    dt_active = make_dt("2026-09-15", "10:30")
    assert timing.get_phase(dt_active) == "ACTIVE_TRADING"
    assert timing.can_enter(dt_active) is True
    assert timing.must_square_off(dt_active) is False

    # 3. Late afternoon freeze (14:45 - 15:10): entries frozen
    dt_freeze = make_dt("2026-09-15", "14:50")
    assert timing.get_phase(dt_freeze) == "ENTRY_FROZEN"
    assert timing.can_enter(dt_freeze) is False
    assert timing.must_square_off(dt_freeze) is False

    # 4. Compulsory EOD Square-off (15:10 - 15:30)
    dt_sqoff = make_dt("2026-09-15", "15:12")
    assert timing.get_phase(dt_sqoff) == "SQUARE_OFF"
    assert timing.can_enter(dt_sqoff) is False
    assert timing.must_square_off(dt_sqoff) is True

    # 5. Weekend / Holiday: Closed
    dt_wknd = make_dt("2026-09-19", "11:00")  # Saturday
    assert timing.get_phase(dt_wknd) == "WEEKEND"
    assert timing.can_enter(dt_wknd) is False


def test_session_vwap_daily_boundary_reset():
    # Construct 2 days of 5-minute bars
    d1_times = pd.date_range("2026-09-15 09:15", "2026-09-15 15:25", freq="5min", tz=IST)
    d2_times = pd.date_range("2026-09-16 09:15", "2026-09-16 15:25", freq="5min", tz=IST)
    times = d1_times.append(d2_times)

    rows = []
    # Day 1: Price around 1000
    for _ in d1_times:
        rows.append({"Open": 1000, "High": 1005, "Low": 995, "Close": 1002, "Volume": 1000})
    # Day 2: Stock gaps up to 2000
    for _ in d2_times:
        rows.append({"Open": 2000, "High": 2010, "Low": 1990, "Close": 2005, "Volume": 2000})

    df = pd.DataFrame(rows, index=times)
    vwap_res = calculate_session_vwap(df)

    # Verify Day 1 final VWAP is ~1000
    d1_end_vwap = vwap_res.loc[d1_times[-1], "vwap"]
    assert 999 < d1_end_vwap < 1003

    # CRITICAL TEST: Day 2 first bar VWAP must reset to Day 2's typical price (~2001.67), NOT blend with Day 1
    d2_first_vwap = vwap_res.loc[d2_times[0], "vwap"]
    typ_d2_bar1 = (2010 + 1990 + 2005) / 3.0
    assert abs(d2_first_vwap - typ_d2_bar1) < 1e-4

    # Verify standard deviation bands
    assert (vwap_res["upper_1"] >= vwap_res["vwap"]).all()
    assert (vwap_res["lower_1"] <= vwap_res["vwap"]).all()


def test_opening_range_breakout_strategy():
    times = pd.date_range("2026-09-15 09:15", "2026-09-15 11:00", freq="5min", tz=IST)
    rows = []
    # 09:15 to 09:30 (first 3 bars): High=505, Low=495
    for t in times[:3]:
        rows.append({"Open": 500, "High": 505, "Low": 495, "Close": 502, "Volume": 5000})

    # 09:30 to 09:45: Consolidates inside range
    for t in times[3:6]:
        rows.append({"Open": 502, "High": 504, "Low": 499, "Close": 501, "Volume": 2000})

    df = pd.DataFrame(rows, index=times[:6])
    strat = OpeningRangeBreakoutStrategy(min_rvol=1.0)

    # 1. Inside range: No signal
    sig_none = strat.decide("RELIANCE.NS", df)
    assert sig_none is None

    # 2. Bullish breakout bar at 09:45: Price breaks to 510 with volume surge
    breakout_time = times[6]
    df.loc[breakout_time] = {"Open": 502, "High": 512, "Low": 501, "Close": 510, "Volume": 8000}

    sig_long = strat.decide("RELIANCE.NS", df)
    assert sig_long is not None
    assert sig_long["action"] == "BUY"
    assert sig_long["side"] == "LONG"
    assert sig_long["price"] == 510.0
    assert sig_long["stop_loss"] < 510.0
    assert sig_long["target"] > 510.0
    assert "ORB breakout" in sig_long["reason"]

    # 3. Macro daily bias filter: if daily trend is BEARISH, long signal is rejected
    daily_rows = [{"Open": 600 - i, "High": 605 - i, "Low": 595 - i, "Close": 598 - i, "Volume": 50000} for i in range(60)]
    daily_df = pd.DataFrame(daily_rows, index=pd.date_range("2026-06-01", periods=60, freq="D"))
    sig_blocked = strat.decide("RELIANCE.NS", df, daily_df=daily_df)
    assert sig_blocked is None


def test_intraday_execution_engine():
    engine = IntradayExecutionEngine()

    # 1. Open Long position
    t0 = make_dt("2026-09-15", "10:00")
    engine.open_position("TCS.NS", side="LONG", qty=10, entry_price=3500.0, stop_loss=3450.0, target=3600.0, timestamp=t0)
    assert "TCS.NS" in engine.positions

    # 2. Trading halt handling (Volume = 0)
    t1 = make_dt("2026-09-15", "10:05")
    halt_res = engine.process_bar("TCS.NS", {"Open": 3510, "High": 3510, "Low": 3510, "Close": 3510, "Volume": 0.0}, t1)
    assert halt_res["status"] == "HALTED"
    assert "TCS.NS" in engine.positions  # Still open

    # 3. Target hit execution
    t2 = make_dt("2026-09-15", "10:10")
    win_res = engine.process_bar("TCS.NS", {"Open": 3550, "High": 3610, "Low": 3540, "Close": 3605, "Volume": 1000}, t2)
    assert win_res["exit_reason"] == "TARGET_HIT"
    assert win_res["exit_price"] == 3600.0
    assert win_res["gross_pnl"] == 1000.0  # (3600 - 3500) * 10
    assert win_res["total_costs"] > 0.0
    assert win_res["net_pnl"] == win_res["gross_pnl"] - win_res["total_costs"]

    # 4. Gap-aware stop execution (opens gap down through stop loss)
    t3 = make_dt("2026-09-15", "11:00")
    engine.open_position("INFY.NS", side="LONG", qty=20, entry_price=1500.0, stop_loss=1470.0, target=1550.0, timestamp=t3)

    t4 = make_dt("2026-09-15", "11:05")
    # Bar opens at 1450 (below stop 1470)
    gap_res = engine.process_bar("INFY.NS", {"Open": 1450, "High": 1460, "Low": 1445, "Close": 1455, "Volume": 2000}, t4)
    assert gap_res["exit_reason"] == "STOP_GAP_DOWN"
    assert gap_res["exit_price"] == 1450.0  # Filled at Open, not theoretical 1470 stop
    assert gap_res["gross_pnl"] == (1450.0 - 1500.0) * 20  # -1000.0

    # 5. Compulsory EOD Square-off at 15:10 IST
    t5 = make_dt("2026-09-15", "14:00")
    engine.open_position("HDFC.NS", side="LONG", qty=15, entry_price=1600.0, stop_loss=1560.0, target=1680.0, timestamp=t5)

    t6 = make_dt("2026-09-15", "15:10")
    sqoff_res = engine.process_bar("HDFC.NS", {"Open": 1620, "High": 1625, "Low": 1618, "Close": 1622, "Volume": 5000}, t6)
    assert sqoff_res["exit_reason"] == "EOD_SQUARE_OFF"
    assert sqoff_res["exit_price"] == 1622.0
    assert sqoff_res["gross_pnl"] == (1622.0 - 1600.0) * 15
    assert len(engine.positions) == 0
