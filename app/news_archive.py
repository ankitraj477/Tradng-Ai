import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class NewsArchive:
    """
    Persistent raw news and corporate announcements archive.
    Deduplicates raw items by hash and timestamps fetch time from day one.
    """
    def __init__(self, db_path="data/news_archive.db"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS news_archive (
                item_hash TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                symbols TEXT,
                event_type TEXT,
                sentiment TEXT,
                materiality TEXT,
                raw_json TEXT
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news_archive(published_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_news_event ON news_archive(event_type)")

    def compute_hash(self, source, title, url=""):
        raw = f"{source.strip()}|{title.strip().lower()}|{url.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def archive_item(self, source, title, url="", published_at=None, symbols=None,
                     event_type="GENERAL", sentiment="NEUTRAL", materiality="LOW", raw_dict=None):
        h = self.compute_hash(source, title, url)
        now_ts = datetime.now(timezone.utc).isoformat()
        sym_str = json.dumps(list(symbols or []))
        raw_str = json.dumps(raw_dict or {})

        # BUG-041: Normalize publisher time (RFC-822 or ISO) to UTC ISO format
        norm_published = now_ts
        if published_at:
            try:
                from email.utils import parsedate_to_datetime
                norm_published = parsedate_to_datetime(published_at).astimezone(timezone.utc).isoformat()
            except Exception:
                try:
                    norm_published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
                except Exception:
                    norm_published = str(published_at)

        with sqlite3.connect(self.path) as c:
            c.execute("""INSERT INTO news_archive(
                item_hash, source, title, url, published_at, fetched_at,
                symbols, event_type, sentiment, materiality, raw_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(item_hash) DO NOTHING""", (
                h, source, title, url, norm_published, now_ts,
                sym_str, event_type, sentiment, materiality, raw_str
            ))
        return h

    def get_recent(self, limit=50, symbol=None):
        with sqlite3.connect(self.path) as c:
            if symbol:
                rows = c.execute("""SELECT item_hash, source, title, url, published_at,
                                           event_type, sentiment, materiality, symbols
                                    FROM news_archive WHERE symbols LIKE ?
                                    ORDER BY published_at DESC LIMIT ?""", (f'%"{symbol}"%', limit)).fetchall()
            else:
                rows = c.execute("""SELECT item_hash, source, title, url, published_at,
                                           event_type, sentiment, materiality, symbols
                                    FROM news_archive ORDER BY published_at DESC LIMIT ?""", (limit,)).fetchall()

            return [{
                "item_hash": r[0], "source": r[1], "title": r[2], "url": r[3],
                "published_at": r[4], "event_type": r[5], "sentiment": r[6],
                "materiality": r[7], "symbols": json.loads(r[8] or "[]")
            } for r in rows]
