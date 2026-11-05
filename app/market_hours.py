import logging
from datetime import datetime, time
from pathlib import Path
import json
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

IST=ZoneInfo("Asia/Kolkata")
OPEN=time(9,15)
CLOSE=time(15,30)
PREOPEN=time(9,0)


def _load_holidays(custom_path=None):
    path = Path(custom_path) if custom_path else Path(__file__).resolve().parents[1] / "config" / "market_holidays.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        validated = {}
        for d_str, name in raw.items():
            try:
                datetime.fromisoformat(d_str)
                validated[d_str] = str(name)
            except ValueError:
                continue
        return validated
    except Exception:
        return {}


HOLIDAYS = _load_holidays()


def reload_holidays(custom_holidays=None, custom_path=None):
    """
    Standardized holiday calendar reloader.
    Supports injecting updated exchange holiday dictionaries or custom calendar files.
    """
    global HOLIDAYS
    if custom_holidays is not None and isinstance(custom_holidays, dict):
        HOLIDAYS = {str(k): str(v) for k, v in custom_holidays.items()}
    else:
        HOLIDAYS = _load_holidays(custom_path)
    return dict(HOLIDAYS)



def now_ist():
    return datetime.now(IST)


def is_year_covered(year: int) -> bool:
    """Checks whether the market holidays table contains any entries for the requested year."""
    return any(k.startswith(str(year)) for k in HOLIDAYS)


def validate_calendar_coverage(dt=None) -> bool:
    """BUG-028: Validates that the current calendar year is covered by config/market_holidays.json."""
    dt = dt or now_ist()
    yr = dt.year if hasattr(dt, "year") else dt.date().year
    if not is_year_covered(yr):
        logger.warning("Market holiday calendar does not have entries for year %d. Update config/market_holidays.json", yr)
        return False
    return True


def holiday_name(dt=None):
    dt = dt or now_ist()
    validate_calendar_coverage(dt)
    d = dt.date() if hasattr(dt, "date") else dt
    return HOLIDAYS.get(d.isoformat())


def market_open(dt=None):
    dt=dt or now_ist()
    return dt.weekday()<5 and holiday_name(dt) is None and OPEN <= dt.time() <= CLOSE


def premarket(dt=None):
    dt=dt or now_ist()
    return dt.weekday()<5 and holiday_name(dt) is None and PREOPEN <= dt.time() < OPEN


def market_phase(dt=None):
    dt=dt or now_ist()
    if dt.weekday()>=5: return "WEEKEND"
    if holiday_name(dt): return "HOLIDAY"
    if dt.time()<PREOPEN: return "CLOSED"
    if premarket(dt): return "PRE_OPEN"
    if market_open(dt): return "REGULAR"
    return "CLOSED"
