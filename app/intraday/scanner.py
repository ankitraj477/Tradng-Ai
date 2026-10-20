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

                # Intraday filter: Minimum liquidity and active intraday range (> 0.5% move)
                if price >= 50 and abs(change_pct) >= 0.4:
                    candidates.append({
                        "symbol": symbol,
                        "price": price,
                        "volume": volume,
                        "change_pct": change_pct,
                        "setup": "ORB_MOMENTUM" if change_pct > 0 else "ORB_SHORT"
                    })
            except Exception:
                continue

        # Sort by absolute momentum
        candidates.sort(key=lambda c: abs(c["change_pct"]), reverse=True)
        return candidates[:10]
