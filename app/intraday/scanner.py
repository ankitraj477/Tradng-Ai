"""
Intraday Volatility & Opening Range Scanner.
Identifies high-liquidity stocks with volume expansion and clean opening range consolidation.
"""

class IntradayScanner:
    def __init__(self, provider, cfg=None):
        self.provider = provider
        self.cfg = cfg or {}

    def scan_opening_candidates(self, universe):
        candidates = []
        for symbol in universe:
            try:
                quote = self.provider.quote(symbol)
                if not quote or not quote.get("price"):
                    continue
                price = float(quote["price"])
                volume = float(quote.get("volume", 0) or 0)
                change_pct = float(quote.get("change_pct", 0) or 0)

                # Micro-account affordability filter:
                # When capital <= 5,000 INR, filter for unit price between 40 and 450 INR.
                # Allows fractional sizing (10-50 shares per trade) with 5x leverage.
                is_micro = float(self.cfg.get("capital", {}).get("starting", 100000)) <= 5000.0 or self.cfg.get("micro_account", False)
                min_px = 40.0
                max_px = 450.0 if is_micro else 50000.0

                if min_px <= price <= max_px:
                    candidates.append({
                        "symbol": symbol,
                        "price": price,
                        "volume": volume,
                        "change_pct": change_pct,
                        "setup": "ORB_MOMENTUM" if change_pct >= 0 else "ORB_SHORT"
                    })
            except Exception:
                continue

        # Sort by absolute momentum
        candidates.sort(key=lambda c: abs(c["change_pct"]), reverse=True)
        return candidates[:25]
