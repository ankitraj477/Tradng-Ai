from abc import ABC, abstractmethod
from datetime import datetime, timezone

class MarketDataProvider(ABC):
    @abstractmethod
    def symbols(self): ...
    @abstractmethod
    def history(self, symbol, period="3mo", interval="5m"): ...
    @abstractmethod
    def quote(self, symbol): ...

def age_seconds(ts):
    if ts.tzinfo is None:
        ts=ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc)-ts).total_seconds()
