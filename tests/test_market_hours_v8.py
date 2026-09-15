from datetime import datetime
from zoneinfo import ZoneInfo
from app.market_hours import market_open, market_phase, holiday_name

IST=ZoneInfo("Asia/Kolkata")

def dt(s): return datetime.fromisoformat(s).replace(tzinfo=IST)

def test_weekday_regular_session():
    assert market_open(dt("2026-09-15T10:00:00"))
    assert market_phase(dt("2026-09-15T10:00:00")) == "REGULAR"

def test_nse_holiday_is_closed():
    d=dt("2026-09-14T10:00:00")
    assert holiday_name(d) == "Ganesh Chaturthi"
    assert not market_open(d)
    assert market_phase(d) == "HOLIDAY"

def test_weekend_is_closed():
    d=dt("2026-09-19T10:00:00")
    assert not market_open(d)
    assert market_phase(d) == "WEEKEND"
