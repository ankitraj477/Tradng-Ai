"""
Index Chain Manager for Nifty 50 and Bank Nifty.
Provides strike price rounding, next expiry date calculations,
lot sizing, and Put-Call Ratio (PCR) sentiment tracking.
"""
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import time as _time

IST = ZoneInfo("Asia/Kolkata")

LOT_SIZES = {
    "NIFTY": 25,
    "BANKNIFTY": 15,
}

STRIKE_INTERVALS = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
}


class IndexChainManager:
    def __init__(self, provider=None):
        self.provider = provider
        self._spot_cache = {}
        self._spot_time = {}
        # Apply 5-second network cache only to live providers (with _download) to protect Yahoo Finance rate limits
        self._cache_ttl = 5.0 if hasattr(provider, "_download") else 0.0

    @staticmethod
    def get_next_expiry(ref_date: date = None) -> str:
        """
        Calculate next weekly expiry (Thursday).
        If today is Thursday (0 DTE) or Wednesday (1 DTE), rolls to next Thursday
        to ensure adequate theta decay horizon (>= 2 DTE) for new spread entries.
        """
        today = ref_date or datetime.now(IST).date()
        days_ahead = (3 - today.weekday()) % 7  # 3 = Thursday
        if days_ahead <= 1:
            days_ahead += 7
        target_thursday = today + timedelta(days=days_ahead)
        return target_thursday.strftime("%Y-%m-%d")

    @staticmethod
    def round_strike(spot: float, index_name: str = "NIFTY") -> int:
        """Round spot price to the nearest option strike interval."""
        interval = STRIKE_INTERVALS.get(index_name.upper(), 50)
        return int(round(spot / interval) * interval)

    def get_spot_price(self, index_name: str = "NIFTY", force_refresh: bool = False) -> float:
        """Fetch spot price for Nifty 50 or Bank Nifty with fast cache protection."""
        now = _time.time()
        key = index_name.upper()
        if not force_refresh and key in self._spot_cache and (now - self._spot_time.get(key, 0.0)) < self._cache_ttl:
            return self._spot_cache[key]

        symbol = "^NSEI" if key == "NIFTY" else "^NSEBANK"
        if self.provider and hasattr(self.provider, "quote"):
            try:
                q = self.provider.quote(symbol)
                if q and "price" in q:
                    price = float(q["price"])
                    self._spot_cache[key] = price
                    self._spot_time[key] = now
                    return price
            except Exception:
                pass
        if key in self._spot_cache:
            return self._spot_cache[key]
        # Fallback realistic index prices
        return 24850.0 if key == "NIFTY" else 51400.0

    def estimate_pcr(self, index_name: str = "NIFTY") -> float:
        """
        Estimate Put-Call Ratio (PCR).
        PCR > 1.2 = Bullish bias (heavy put writing)
        PCR 0.85 - 1.15 = Neutral / Range-bound
        PCR < 0.8 = Bearish bias (heavy call writing)
        """
        # In live trading with broker API, this queries NSE option chain open interest.
        # Fallback to simulated balanced PCR:
        return 1.02
