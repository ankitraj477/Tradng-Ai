"""
Official multi-year Indian market holiday, expiry, and event calendar.
Enforces Rule 0: Refuses to run if the year is not covered.
Handles NIFTY/BANKNIFTY monthly & weekly expiry rules with holiday backward roll.
"""

from datetime import date, datetime, timedelta
from typing import Set, Dict, List, Optional, Tuple, Union
from .strategy_config import StrategyConfig, load_strategy_config


class MarketCalendar:
    """Official multi-year NSE trading calendar and expiry calculator."""

    def __init__(self, cfg: Optional[StrategyConfig] = None):
        self.cfg = cfg or load_strategy_config()
        cal_data = self.cfg.raw.get("calendar", {})
        self.supported_years: Set[int] = set(cal_data.get("supported_years", []))
        self.holidays: Dict[str, str] = cal_data.get("holidays", {})
        self.events: List[Dict[str, str]] = cal_data.get("events", [])

    def assert_year_covered(self, year: int):
        """Engine refuses to run if the year is not covered by the official calendar."""
        if year not in self.supported_years:
            raise ValueError(
                f"Market calendar does not cover year {year}. "
                f"Supported years: {sorted(self.supported_years)}"
            )

    def is_trading_day(self, dt: Union[date, datetime, str]) -> bool:
        """Check if date is a valid trading day (weekday and non-holiday)."""
        d = self._to_date(dt)
        self.assert_year_covered(d.year)
        if d.weekday() >= 5:  # Saturday (5) or Sunday (6)
            return False
        return d.isoformat() not in self.holidays

    def holiday_name(self, dt: Union[date, datetime, str]) -> Optional[str]:
        d = self._to_date(dt)
        return self.holidays.get(d.isoformat())

    def previous_trading_day(self, dt: Union[date, datetime, str]) -> date:
        """Return the previous trading day strictly before dt."""
        cur = self._to_date(dt) - timedelta(days=1)
        while not self.is_trading_day(cur):
            cur -= timedelta(days=1)
        return cur

    def next_trading_day(self, dt: Union[date, datetime, str]) -> date:
        """Return the next trading day strictly after dt."""
        cur = self._to_date(dt) + timedelta(days=1)
        while not self.is_trading_day(cur):
            cur += timedelta(days=1)
        return cur

    def trading_days_between(self, start: Union[date, datetime, str], end: Union[date, datetime, str]) -> List[date]:
        """Return list of trading days in [start, end] inclusive."""
        s = self._to_date(start)
        e = self._to_date(end)
        days = []
        cur = s
        while cur <= e:
            if self.is_trading_day(cur):
                days.append(cur)
            cur += timedelta(days=1)
        return days

    def get_monthly_expiry(self, year: int, month: int, symbol: str = "NIFTY") -> date:
        """
        Calculate the monthly expiry for symbol in year/month.
        Per STRATEGY_SPEC.md:
        - Monthly expiry = last Tuesday of the month.
        - If the last Tuesday is a holiday, moves expiry to the previous trading day.
        """
        self.assert_year_covered(year)
        # Find the last day of the month
        if month == 12:
            next_month_first = date(year + 1, 1, 1)
        else:
            next_month_first = date(year, month + 1, 1)
        last_day = next_month_first - timedelta(days=1)

        # Tuesday is weekday() == 1
        cur = last_day
        while cur.weekday() != 1:
            cur -= timedelta(days=1)
        last_tuesday = cur

        # If holiday, move backwards to the previous trading day
        while not self.is_trading_day(last_tuesday):
            last_tuesday = self.previous_trading_day(last_tuesday)
        return last_tuesday

    def get_weekly_expiry(self, dt: Union[date, datetime, str], symbol: str = "NIFTY") -> date:
        """
        Calculate the weekly expiry for symbol given reference date dt.
        Per market rules:
        - BANKNIFTY raises ValueError (monthly expiry only, no weekly).
        - NIFTY weekly expiry is Tuesday (shifted to previous trading day if holiday).
        """
        self.cfg.assert_weekly_allowed(symbol)
        d = self._to_date(dt)
        self.assert_year_covered(d.year)

        # Days until Tuesday (weekday 1)
        days_ahead = (1 - d.weekday()) % 7
        target_tuesday = d + timedelta(days=days_ahead)

        # If target Tuesday is a holiday, shift to previous trading day
        exp = target_tuesday
        while not self.is_trading_day(exp):
            exp = self.previous_trading_day(exp)
        return exp

    def is_near_event(self, dt: Union[date, datetime, str], window_days: int = 3) -> Tuple[bool, str]:
        """
        Check if dt falls within +/- window_days trading days of any listed macro/policy event.
        Used by Sleeves C and D to avoid event volatility spikes.
        """
        d = self._to_date(dt)
        for ev in self.events:
            ev_date = self._to_date(ev["date"])
            # Count trading days distance
            if d <= ev_date:
                t_days = len(self.trading_days_between(d, ev_date)) - 1
            else:
                t_days = len(self.trading_days_between(ev_date, d)) - 1
            if abs(t_days) <= window_days:
                return True, f"{ev['name']} ({ev.get('type', 'EVENT')}) on {ev['date']}"
        return False, ""

    @staticmethod
    def _to_date(val: Union[date, datetime, str]) -> date:
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
