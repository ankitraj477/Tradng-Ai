from datetime import datetime, time
from pathlib import Path
import json
from zoneinfo import ZoneInfo

IST=ZoneInfo("Asia/Kolkata")
OPEN=time(9,15)
CLOSE=time(15,30)
PREOPEN=time(9,0)


def _load_holidays():
    path=Path(__file__).resolve().parents[1]/"config"/"market_holidays.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

HOLIDAYS=_load_holidays()


def now_ist():
    return datetime.now(IST)


def holiday_name(dt=None):
    dt=dt or now_ist()
    return HOLIDAYS.get(dt.date().isoformat())


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
