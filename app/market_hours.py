from datetime import datetime, time
from zoneinfo import ZoneInfo

IST=ZoneInfo("Asia/Kolkata")
OPEN=time(9,15)
CLOSE=time(15,30)

def now_ist():
    return datetime.now(IST)

def market_open(dt=None):
    dt=dt or now_ist()
    return dt.weekday()<5 and OPEN <= dt.time() <= CLOSE

def premarket(dt=None):
    dt=dt or now_ist()
    return dt.weekday()<5 and time(8,0) <= dt.time() < OPEN
