from dataclasses import dataclass
from datetime import datetime, timezone
import re

try:
    import feedparser
except ImportError:
    feedparser = None

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str
    materiality: str
    sentiment: str
    symbols: tuple = ()

class NewsProvider:
    """Free RSS news layer with conservative company-name/symbol matching."""
    FEEDS = {
        "Google News Finance":
        "https://news.google.com/rss/search?q=Indian%20stock%20market&hl=en-IN&gl=IN&ceid=IN:en"
    }

    POSITIVE = ("growth","profit","upgrade","approval","wins","surge","order win",
                "strong results","beats","expansion")
    NEGATIVE = ("loss","downgrade","fraud","ban","fall","crisis","probe",
                "weak results","misses","default")

    def recent(self, limit=20, universe=None):
        if feedparser is None:
            return []
        universe = universe or {}
        items=[]
        for source,url in self.FEEDS.items():
            try:
                feed=feedparser.parse(url)
                for e in feed.entries[:limit]:
                    title=e.get("title","").strip()
                    if not title:
                        continue
                    matches=self.match_symbols(title, universe)
                    items.append(NewsItem(
                        title=title, url=e.get("link",""), source=source,
                        published=e.get("published",""),
                        materiality=self.materiality(title),
                        sentiment=self.sentiment(title),
                        symbols=tuple(matches)
                    ))
            except Exception:
                continue
        return items[:limit]

    def match_symbols(self, title, universe):
        """Only return matches when a symbol or company name is explicitly present."""
        t=title.lower()
        found=[]
        for symbol, meta in universe.items():
            names=[symbol.replace(".NS","").lower()]
            company=getattr(meta,"company","") if not isinstance(meta,dict) else meta.get("company","")
            if company:
                names.append(company.lower())
            if any(re.search(rf"\b{re.escape(n)}\b", t) for n in names if n):
                found.append(symbol)
        return found

    def materiality(self,title):
        t=title.lower()
        if any(x in t for x in (
            "results","earnings","rbi","sebi","merger","acquisition","order",
            "fraud","ban","approval","regulatory","guidance","rating","default"
        )):
            return "potentially_material"
        return "unknown"

    def sentiment(self,title):
        t=title.lower()
        pos=sum(x in t for x in self.POSITIVE)
        neg=sum(x in t for x in self.NEGATIVE)
        return "positive" if pos>neg else "negative" if neg>pos else "neutral"

    def score_for_symbol(self, symbol, items):
        relevant=[x for x in items if symbol in x.symbols]
        score=0
        material=0
        for x in relevant:
            weight=2 if x.materiality=="potentially_material" else 1
            score += weight if x.sentiment=="positive" else -weight if x.sentiment=="negative" else 0
            material += int(x.materiality=="potentially_material")
        return {"score":score,"items":len(relevant),"material_items":material}
