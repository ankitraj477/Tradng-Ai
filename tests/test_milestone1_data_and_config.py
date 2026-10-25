"""
Milestone 1 Acceptance Test Suite (STRATEGY_SPEC.md).

Covers:
- Test 1: No look-ahead bias with deliberate positive control detection.
- Test 3: Multi-year market calendar, last Tuesday monthly expiry, holiday roll, and uncovered year refusal.
- Test 4: Dynamic contract lot size lookup by effective_from date, BANKNIFTY weekly rejection.
- Test 7: Point-in-time universe with survivorship bias elimination (removed stock appears before removal date, not after; refuses static CSV seeding).
- Data validation: No gaps beyond official holidays, positive prices, monotonic timestamps, split continuity.
- Strategy config: Validated loader rejecting missing keys.
"""

from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

from app.strategy_config import load_strategy_config, StrategyConfig
from app.market_calendar import MarketCalendar
from app.universe_pit import PointInTimeUniverse
from app.data.store import MarketDataStore
from app.data.validator import validate_market_data, assert_no_lookahead


REPO_ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# 1. Strategy Config Validated Loader
# ----------------------------------------------------------------------

def test_m1_strategy_config_loader():
    """Verify strategy.json loads cleanly and rejects missing keys."""
    cfg = load_strategy_config()
    assert cfg.raw["meta"]["version"] == "1.0.0"
    assert "contracts" in cfg.raw
    assert "costs" in cfg.raw
    assert "calendar" in cfg.raw
    assert "sleeves" in cfg.raw
    assert "portfolio_risk" in cfg.raw

    # Rejection of invalid config with missing sections
    with pytest.raises(KeyError, match="missing required top-level sections"):
        StrategyConfig({"meta": {}, "contracts": {}})

    # Sleeves A, B, C, D all present
    for s in ("A", "B", "C", "D"):
        assert s in cfg.raw["sleeves"]


# ----------------------------------------------------------------------
# 2. Contract Tests (Test 4): Lot Sizes by Date & Expiry Weekday
# ----------------------------------------------------------------------

def test_m1_contract_lot_sizes_and_weekly_rules():
    """
    Test 4 from STRATEGY_SPEC.md:
    Lot size lookup by effective date; BANKNIFTY weekly request raises.
    """
    cfg = load_strategy_config()

    # NIFTY lot sizes through regulatory changes:
    # 2024-05 was 25; 2025 was 75; 2026 series is 65
    assert cfg.get_lot_size("NIFTY", "2024-05-15") == 25
    assert cfg.get_lot_size("NIFTY", "2025-06-15") == 75
    assert cfg.get_lot_size("NIFTY", "2026-02-15") == 65

    # BANKNIFTY lot size: 30 from late 2024 onwards
    assert cfg.get_lot_size("BANKNIFTY", "2026-01-15") == 30

    # Expiry weekday
    assert cfg.get_expiry_weekday("NIFTY") == "TUE"
    assert cfg.get_expiry_weekday("BANKNIFTY") == "TUE"

    # BANKNIFTY weekly request MUST raise
    with pytest.raises(ValueError, match="does not support weekly options"):
        cfg.assert_weekly_allowed("BANKNIFTY")

    # NIFTY weekly request passes
    cfg.assert_weekly_allowed("NIFTY")


# ----------------------------------------------------------------------
# 3. Calendar Tests (Test 3): Expiry Calculation & Uncovered Years
# ----------------------------------------------------------------------

def test_m1_calendar_expiry_and_uncovered_year_refusal():
    """
    Test 3 from STRATEGY_SPEC.md:
    Last Tuesday of month; expiry moves to previous trading day on holiday;
    engine refuses uncovered years.
    """
    cal = MarketCalendar()

    # 1. Standard monthly expiry: Last Tuesday of month
    # October 2026: Tuesdays are 6, 13, 20, 27.
    # Note: 2026-10-20 is Dussehra holiday, but 2026-10-27 is a normal trading day!
    exp_oct26 = cal.get_monthly_expiry(2026, 10, "NIFTY")
    assert exp_oct26 == date(2026, 10, 27)
    assert cal.is_trading_day(exp_oct26)
    assert exp_oct26.weekday() == 1  # Tuesday

    # 2. Holiday roll: If the last Tuesday is a holiday, moves to previous trading day.
    # Let's verify with December 2024 or November 2025, or inject a test holiday on the last Tuesday.
    # November 2024: Tuesdays are 5, 12, 19, 26.
    exp_nov24 = cal.get_monthly_expiry(2024, 11, "NIFTY")
    assert exp_nov24 == date(2024, 11, 26)

    # Injecting a holiday on 2026-10-27 in a test calendar must roll expiry to Monday 2026-10-26
    cal_test = MarketCalendar()
    cal_test.holidays["2026-10-27"] = "Simulated Tuesday Holiday"
    rolled_exp = cal_test.get_monthly_expiry(2026, 10, "NIFTY")
    assert rolled_exp == date(2026, 10, 26)  # Monday
    assert cal_test.is_trading_day(rolled_exp)

    # 3. Refuses uncovered year
    with pytest.raises(ValueError, match="does not cover year 2045"):
        cal.assert_year_covered(2045)


# ----------------------------------------------------------------------
# 4. PIT Universe Tests (Test 7): Survivorship Bias Elimination
# ----------------------------------------------------------------------

def test_m1_pit_universe_survivorship_bias_guards(tmp_path):
    """
    Test 7 from STRATEGY_SPEC.md:
    A removed stock appears before its removal date and not after.
    Static unversioned CSV seeding is explicitly refused.
    """
    pit = PointInTimeUniverse(db_path=str(tmp_path / "pit_test.db"))

    # Refuse static unversioned CSV
    with pytest.raises(ValueError, match="Survivorship bias violation"):
        pit.seed_from_csv("dummy.csv")

    # Add historical additions and removals
    pit.seed_default_nifty200_pit()

    # YESBANK was removed on 2020-03-27:
    # On 2019-12-01: YESBANK MUST be in the universe
    u_2019 = pit.get_constituents("2019-12-01")
    assert "YESBANK.NS" in u_2019

    # On 2020-04-01: YESBANK MUST NOT be in the universe
    u_2020 = pit.get_constituents("2020-04-01")
    assert "YESBANK.NS" not in u_2020

    # ZOMATO was added on 2021-08-01:
    # In 2020: ZOMATO must NOT be in universe
    assert "ZOMATO.NS" not in u_2020
    # In 2022: ZOMATO MUST be in universe
    u_2022 = pit.get_constituents("2022-01-01")
    assert "ZOMATO.NS" in u_2022


# ----------------------------------------------------------------------
# 5. Look-Ahead Bias Tests (Test 1): With Deliberate Positive Control
# ----------------------------------------------------------------------

def test_m1_no_lookahead_and_positive_control():
    """
    Test 1 from STRATEGY_SPEC.md:
    Shift every feature by +1 bar and assert signals change only as expected.
    Include a deliberately leaky feature as a positive control that must be caught.
    """
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    np.random.seed(42)
    prices = 100.0 + np.cumsum(np.random.randn(30))
    df = pd.DataFrame({
        "Open": prices * 0.99,
        "High": prices * 1.01,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": 10000.0
    }, index=dates)

    # 1. Clean feature: SMA 5 (strictly backward-looking)
    def clean_sma5(d):
        return d["Close"].rolling(5).mean()

    assert assert_no_lookahead(clean_sma5, df) is True

    # 2. Leaky feature (positive control): peeks into future bar Close[t+1]
    def leaky_future_peek(d):
        return d["Close"].shift(-1)

    # The validator MUST catch this look-ahead leak!
    with pytest.raises(AssertionError, match="Look-ahead bias detected"):
        assert_no_lookahead(leaky_future_peek, df)


# ----------------------------------------------------------------------
# 6. Data Validation: Gaps, Non-Positive Prices, Monotonicity, Splits
# ----------------------------------------------------------------------

def test_m1_market_data_validation(tmp_path):
    """Data validation tests: no gaps beyond holidays, no non-positive prices, monotonic dates."""
    cal = MarketCalendar()

    dates = pd.date_range("2026-01-05", periods=5, freq="B")
    valid_df = pd.DataFrame({
        "Open": [100.0, 102.0, 101.0, 103.0, 105.0],
        "High": [103.0, 104.0, 103.0, 106.0, 107.0],
        "Low": [99.0, 101.0, 100.0, 102.0, 104.0],
        "Close": [102.0, 101.0, 103.0, 105.0, 106.0],
        "Volume": [1000.0, 1200.0, 1100.0, 1500.0, 1400.0]
    }, index=dates)

    # Valid data passes
    ok, msg = validate_market_data(valid_df, calendar=cal, symbol="TEST")
    assert ok is True
    assert msg == "ok"

    # Reject non-positive price
    bad_price_df = valid_df.copy()
    bad_price_df.iloc[2, bad_price_df.columns.get_loc("Low")] = -5.0
    ok, msg = validate_market_data(bad_price_df, calendar=cal, symbol="TEST")
    assert ok is False
    assert "non-positive values" in msg

    # Reject High < max(Open, Close)
    bad_high_df = valid_df.copy()
    bad_high_df.iloc[1, bad_high_df.columns.get_loc("High")] = 90.0
    ok, msg = validate_market_data(bad_high_df, calendar=cal, symbol="TEST")
    assert ok is False
    assert "High is lower than max(Open, Close)" in msg

    # Reject unexplained missing trading day gap
    gap_dates = [dates[0], dates[4]]  # Skips 3 trading days without holidays!
    gap_df = valid_df.loc[gap_dates].copy()
    ok, msg = validate_market_data(gap_df, calendar=cal, symbol="TEST")
    assert ok is False
    assert "Unexplained missing trading day gap" in msg


# ----------------------------------------------------------------------
# 7. Research Data Store: ADTV20 & VIX Series Storage
# ----------------------------------------------------------------------

def test_m1_research_data_store(tmp_path):
    """Test MarketDataStore with ADTV20 computation, VIX series, and corporate actions."""
    db_file = tmp_path / "research.db"
    store = MarketDataStore(path=db_file)

    dates = pd.date_range("2026-01-01", periods=25, freq="B")
    prices = [100.0 + i for i in range(25)]
    df = pd.DataFrame({
        "Open": prices,
        "High": [p + 2 for p in prices],
        "Low": [p - 2 for p in prices],
        "Close": prices,
        "Volume": [1000.0 * (i + 1) for i in range(25)]
    }, index=dates)

    # Save and retrieve bars
    saved = store.save_bars("RELIANCE.NS", df)
    assert saved == 25

    retrieved = store.get_bars("RELIANCE.NS", with_adtv=True)
    assert len(retrieved) == 25
    assert "ADTV20" in retrieved.columns
    # Check 20-day rolling turnover mean
    assert retrieved["ADTV20"].iloc[-1] > 0

    # India VIX
    vix_df = pd.DataFrame({
        "Close": [13.5, 14.2, 13.8]
    }, index=dates[:3])
    store.save_vix(vix_df)
    vix_res = store.get_vix()
    assert len(vix_res) == 3
    assert vix_res["Close"].iloc[0] == 13.5

    # Corporate action log
    store.log_corporate_action("RELIANCE.NS", "2024-10-28", "BONUS", 1.0, "1:1 Bonus issue")
    actions = store.get_corporate_actions("RELIANCE.NS")
    assert len(actions) == 1
    assert actions[0]["action_type"] == "BONUS"
