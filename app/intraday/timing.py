from datetime import datetime, time
from zoneinfo import ZoneInfo
from ..market_hours import holiday_name

IST = ZoneInfo("Asia/Kolkata")

SESSION_START = time(9, 15)
OPENING_RANGE_END = time(9, 30)
LUNCH_LULL_START = time(11, 45)
LUNCH_LULL_END = time(13, 15)
ENTRY_CUTOFF = time(14, 45)
SQUARE_OFF_START = time(15, 10)
SESSION_END = time(15, 30)


class IntradayTimingManager:
    """
    Intraday market timing and session window enforcement.
    Strictly prohibits early opening entries (first 15 min), late afternoon entries,
    and enforces compulsory end-of-day square-off before 15:15 IST.
    """
    def __init__(self, tz=IST):
        self.tz = tz

    def _normalize_dt(self, dt):
        if dt is None:
            return datetime.now(self.tz)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)

    def get_phase(self, dt=None):
        dt = self._normalize_dt(dt)
        if dt.weekday() >= 5:
            return "WEEKEND"
        if holiday_name(dt):
            return "HOLIDAY"

        t = dt.time()
        if t < SESSION_START:
            return "PRE_MARKET"
        if SESSION_START <= t < OPENING_RANGE_END:
            return "OPENING_RANGE"
        if OPENING_RANGE_END <= t < ENTRY_CUTOFF:
            return "ACTIVE_TRADING"
        if ENTRY_CUTOFF <= t < SQUARE_OFF_START:
            return "ENTRY_FROZEN"
        if SQUARE_OFF_START <= t <= SESSION_END:
            return "SQUARE_OFF"
        return "CLOSED"

    def is_midday_lull(self, dt=None):
        """Institutional volume lull in Indian markets between 11:45 and 13:15 IST."""
        dt = self._normalize_dt(dt)
        return LUNCH_LULL_START <= dt.time() < LUNCH_LULL_END

    def can_enter(self, dt=None, allow_midday=False):
        """No entries in first 15 min (9:15-9:30), after 14:45 IST, or during 11:45-13:15 lunchtime lull."""
        phase = self.get_phase(dt)
        if phase != "ACTIVE_TRADING":
            return False
        if not allow_midday and self.is_midday_lull(dt):
            return False
        return True

    can_enter_trades = can_enter

    def must_square_off(self, dt=None):
        """Compulsory square-off starting at 15:10 IST."""
        dt = self._normalize_dt(dt)
        if dt.weekday() >= 5 or holiday_name(dt):
            return False
        return SQUARE_OFF_START <= dt.time() <= SESSION_END
