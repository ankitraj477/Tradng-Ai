from .regime import detect

class MarketIntelligence:
    """Combines index regime and company news into bounded, auditable context."""

    def __init__(self, news_provider):
        self.news=news_provider

    def build(self, index_row, universe_metadata):
        regime=detect(index_row)
        items=self.news.recent(limit=50, universe=universe_metadata)
        return {
            **regime,
            "news_items": items,
            "news_count": len(items),
        }

    def enrich(self, candidate, context):
        n=self.news.score_for_symbol(candidate["symbol"], context.get("news_items", []))
        out=dict(candidate)
        out["news_score"]=n["score"]
        out["news_items"]=n["items"]
        out["material_news"]=n["material_items"]
        # News is a bounded feature, never a standalone trade trigger.
        out["news_bias"] = max(-10, min(10, n["score"] * 2))
        return out
