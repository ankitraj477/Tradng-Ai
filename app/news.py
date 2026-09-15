from dataclasses import dataclass
from datetime import datetime, timezone
try:
    import feedparser
except ImportError:
    feedparser = None

@dataclass
class NewsItem:
    title:str
    url:str
    source:str
    published:str
    materiality:str
    sentiment:str

class NewsProvider:
    """Free RSS-based news layer. It never invents news."""
    FEEDS={
        "Google News Finance":"https://news.google.com/rss/search?q=Indian%20stock%20market&hl=en-IN&gl=IN&ceid=IN:en"
    }
    def recent(self, limit=20):
        if feedparser is None:
            return []
        items=[]
        for source,url in self.FEEDS.items():
            try:
                feed=feedparser.parse(url)
                for e in feed.entries[:limit]:
                    title=e.get("title","").strip()
                    if not title: continue
                    items.append(NewsItem(title,e.get("link",""),source,e.get("published",""),
                                          self.materiality(title),self.sentiment(title)))
            except Exception:
                continue
        return items[:limit]

    def materiality(self,title):
        words=title.lower()
        if any(x in words for x in ["results","earnings","rbi","sebi","merger","acquisition","order","fraud","ban","approval","regulatory"]):
            return "potentially_material"
        return "unknown"

    def sentiment(self,title):
        t=title.lower()
        pos=sum(x in t for x in ["growth","profit","upgrade","approval","wins","surge"])
        neg=sum(x in t for x in ["loss","downgrade","fraud","ban","fall","crisis"])
        return "positive" if pos>neg else "negative" if neg>pos else "neutral"
