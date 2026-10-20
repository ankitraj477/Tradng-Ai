from .regime import detect

class MarketIntelligence:
    """Combines index regime and company news into bounded, auditable context."""

    def __init__(self, news_provider, cfg=None):
        self.news = news_provider
        self.cfg = cfg or {}

    def build(self, index_row, universe_metadata):
        regime = detect(index_row)
        intel_cfg = self.cfg.get("intelligence", {})
        # BUG-044: Wire news_enabled and max_news_items
        if intel_cfg.get("news_enabled", True):
            limit = int(intel_cfg.get("max_news_items", 50))
            items = self.news.recent(limit=limit, universe=universe_metadata)
        else:
            items = []
        return {
            **regime,
            "news_items": items,
            "news_count": len(items),
        }

    def enrich(self, candidate, context):
        intel_cfg = self.cfg.get("intelligence", {})
        # BUG-044: Wire news_enabled and news_bias_cap
        if not intel_cfg.get("news_enabled", True):
            out = dict(candidate)
            out["news_score"] = 0
            out["news_items"] = []
            out["material_news"] = []
            out["news_bias"] = 0
            return out

        n = self.news.score_for_symbol(candidate["symbol"], context.get("news_items", []))
        out = dict(candidate)
        out["news_score"] = n["score"]
        out["news_items"] = n["items"]
        out["material_news"] = n["material_items"]
        # News is a bounded feature, never a standalone trade trigger.
        cap = int(intel_cfg.get("news_bias_cap", 10))
        out["news_bias"] = max(-cap, min(cap, n["score"] * 2))
        return out
