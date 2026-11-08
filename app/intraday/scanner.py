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

                # Dynamic capital affordability filter:
                # - When capital <= 2,500 INR, filter for unit price <= 450 INR.
                # - When capital <= 15,000 INR, filter for unit price <= 2,500 INR (liquid Nifty leaders like SBIN, INFY).
                # - Above 15k INR, open full universe up to 50,000 INR.
                starting_cap = float(self.cfg.get("capital", {}).get("starting", 100000))
                is_micro = starting_cap <= 15000.0 or self.cfg.get("micro_account", False)
                min_px = 10.0 if is_micro else 40.0
                if starting_cap <= 2500.0:
                    max_px = 450.0
                elif starting_cap <= 15000.0:
                    max_px = 2500.0
                else:
                    max_px = 50000.0

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
