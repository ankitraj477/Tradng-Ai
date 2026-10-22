"""
Global Markets Intelligence Scanner.
Monitors US, Asian, and commodity benchmarks to establish global sentiment
and risk-on/risk-off context before and during Indian market trading hours.
"""

from datetime import datetime, timezone
import logging

logger = logging.getLogger("tradng_ai.global_markets")


class GlobalMarketScanner:
    """
    Scans major international market indices and commodities:
    - US Markets: S&P 500 (^GSPC), Nasdaq Composite (^IXIC)
    - Asian Markets: Nikkei 225 (^N225), Hang Seng (^HSI)
    - Macro Drivers: Brent Crude (BZ=F), India VIX (^INDIAVIX)
    """

    BENCHMARKS = {
        "^GSPC": {"name": "S&P 500", "region": "US", "weight": 0.35},
        "^IXIC": {"name": "Nasdaq", "region": "US", "weight": 0.25},
        "^N225": {"name": "Nikkei 225", "region": "Asia", "weight": 0.25},
        "^HSI": {"name": "Hang Seng", "region": "Asia", "weight": 0.15},
    }

    INDIAN_BENCHMARKS = {
        "^NSEI": {"name": "NIFTY 50", "exchange": "NSE"},
        "^BSESN": {"name": "SENSEX", "exchange": "BSE"},
        "^NSEBANK": {"name": "BANK NIFTY", "exchange": "NSE"},
        "^INDIAVIX": {"name": "INDIA VIX", "exchange": "NSE"},
    }

    def __init__(self, provider=None):
        self.provider = provider

    def scan_markets(self, provider=None):
        """
        Fetches quotes and recent changes for all monitored global indices.
        Returns detailed performance dictionary and synthesized sentiment.
        """
        p = provider or self.provider
        results = {}
        weighted_score = 0.0
        total_weight = 0.0

        for symbol, meta in self.BENCHMARKS.items():
            try:
                chg_pct = 0.0
                price = 0.0
                if p and hasattr(p, "quote"):
                    q = p.quote(symbol)
                    price = float(q.get("price") or 0.0) if isinstance(q, dict) else 0.0

                # Compute change from history if available
                if p and hasattr(p, "history"):
                    try:
                        df = p.history(symbol, period="5d", interval="1d")
                        if df is not None and len(df) >= 2:
                            c_prev = float(df["Close"].iloc[-2])
                            c_curr = float(df["Close"].iloc[-1])
                            if c_prev > 0:
                                chg_pct = (c_curr / c_prev) - 1.0
                                price = c_curr
                    except Exception:
                        pass

                results[symbol] = {
                    "name": meta["name"],
                    "region": meta["region"],
                    "price": round(price, 2),
                    "change_pct": round(chg_pct * 100.0, 2),
                }

                w = meta["weight"]
                weighted_score += chg_pct * w
                total_weight += w

            except Exception as err:
                logger.debug(f"Global market lookup skipped for {symbol}: {err}")
                continue

        avg_return = (weighted_score / total_weight) if total_weight > 0 else 0.0

        # Sentiment classification
        if avg_return >= 0.004:
            sentiment = "BULLISH"
            bias = 1
        elif avg_return <= -0.015:
            sentiment = "HIGH RISK / CRASH"
            bias = -2
        elif avg_return <= -0.004:
            sentiment = "BEARISH"
            bias = -1
        else:
            sentiment = "NEUTRAL"
            bias = 0

        indian_results = self.scan_indian_benchmarks(p)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sentiment": sentiment,
            "bias": bias,
            "weighted_return_pct": round(avg_return * 100.0, 3),
            "benchmarks": results,
            "indian_benchmarks": indian_results,
            "summary": (
                f"Global Cues: {sentiment} (avg return {avg_return*100.0:+.2f}%). "
                + ", ".join(f"{v['name']}: {v['change_pct']:+.1f}%" for v in results.values() if v.get("price", 0) > 0)
            ),
            "indian_summary": (
                "Indian Benchmarks: "
                + ", ".join(f"{v['name']}: {v['change_pct']:+.1f}%" for v in indian_results.values() if v.get("price", 0) > 0)
            )
        }

    def scan_indian_benchmarks(self, provider=None):
        """Fetches quotes and daily change for NIFTY 50, BSE SENSEX, BANK NIFTY, and INDIA VIX."""
        p = provider or self.provider
        indian_res = {}
        for symbol, meta in self.INDIAN_BENCHMARKS.items():
            try:
                chg_pct = 0.0
                price = 0.0
                if p and hasattr(p, "quote"):
                    q = p.quote(symbol)
                    price = float(q.get("price") or 0.0) if isinstance(q, dict) else 0.0

                if p and hasattr(p, "history"):
                    try:
                        df = p.history(symbol, period="5d", interval="1d")
                        if df is not None and len(df) >= 2:
                            c_prev = float(df["Close"].iloc[-2])
                            c_curr = float(df["Close"].iloc[-1])
                            if c_prev > 0:
                                chg_pct = (c_curr / c_prev) - 1.0
                                price = c_curr
                    except Exception:
                        pass

                indian_res[symbol] = {
                    "name": meta["name"],
                    "exchange": meta["exchange"],
                    "price": round(price, 2),
                    "change_pct": round(chg_pct * 100.0, 2),
                }
            except Exception:
                continue
        return indian_res
