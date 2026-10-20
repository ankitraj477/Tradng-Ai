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
    event_type: str = "GENERAL"

class NewsProvider:
    """Free RSS news layer with conservative company-name/symbol matching and event classification."""
    FEEDS = {
        "Google News Finance":
        "https://news.google.com/rss/search?q=Indian%20stock%20market&hl=en-IN&gl=IN&ceid=IN:en"
    }

    POSITIVE = ("growth","profit","upgrade","approval","wins","surge","order win",
                "strong results","beats","expansion")
    NEGATIVE = ("loss","downgrade","fraud","ban","fall","crisis","probe",
                "weak results","misses","default")

    def __init__(self, archive=None, resolver=None, classifier=None):
        self.archive = archive
        self.resolver = resolver
        self.classifier = classifier

    def recent(self, limit=20, universe=None):
        if feedparser is None:
            return []
        import urllib.request
        universe = universe or {}
        items=[]
        for source,url in self.FEEDS.items():
            try:
                req=urllib.request.Request(url, headers={"User-Agent":"Tradng-Ai/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    feed=feedparser.parse(resp.read())
                for e in feed.entries[:limit]:
                    title=e.get("title","").strip()
                    if not title:
                        continue
                    matches=self.match_symbols(title, universe)
                    ev_type = "GENERAL"
                    mat = self.materiality(title)
                    sent = self.sentiment(title)
                    if self.classifier:
                        clf = self.classifier.classify(title)
                        ev_type = clf["event_type"]
                        mat = clf["materiality"].lower()
                        sent = clf["sentiment"].lower()
                    # BUG-041: Normalize published timestamp
                    raw_pub = e.get("published", "")
                    norm_pub = raw_pub
                    if raw_pub:
                        try:
                            from email.utils import parsedate_to_datetime
                            norm_pub = parsedate_to_datetime(raw_pub).astimezone(timezone.utc).isoformat()
                        except Exception:
                            pass

                    item = NewsItem(
                        title=title, url=e.get("link",""), source=source,
                        published=norm_pub,
                        materiality=mat,
                        sentiment=sent,
                        symbols=tuple(matches),
                        event_type=ev_type
                    )
                    items.append(item)
                    if self.archive:
                        self.archive.archive_item(source, title, e.get("link",""), norm_pub, matches, ev_type, sent, mat)
            except Exception as feed_err:
                # BUG-029: Log failures instead of silently swallowing them
                import logging
                logging.getLogger("tradng_ai.news").warning(
                    f"News feed fetch failed for {source} ({url}): {feed_err}"
                )
                continue
        return items[:limit]

    def match_symbols(self, title, universe):
        """Only return matches when a symbol or company name is explicitly present."""
        if self.resolver:
            res = self.resolver.resolve(title)
            if res: return res
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
        if any(re.search(rf"\b{re.escape(x)}\b", t) for x in (
            "results","earnings","rbi","sebi","merger","acquisition","order",
            "fraud","ban","approval","regulatory","guidance","rating","default"
        )):
            return "potentially_material"
        return "unknown"

    def sentiment(self,title):
        t=title.lower()
        pos=sum(bool(re.search(rf"\b{re.escape(x)}\b", t)) for x in self.POSITIVE)
        neg=sum(bool(re.search(rf"\b{re.escape(x)}\b", t)) for x in self.NEGATIVE)
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
