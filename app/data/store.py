import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np


class MarketDataStore:
    """Local daily OHLCV data store with explicit split/bonus adjustment tracking."""
    def __init__(self, path="data/daily_bars.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("""CREATE TABLE IF NOT EXISTS daily_bars (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                adjusted INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (symbol, date)
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_daily_bars_date ON daily_bars(date)")

    def save_bars(self, symbol, df, adjusted=True):
        if df is None or df.empty: return 0
        rows = []
        adj = 1 if adjusted else 0
        for idx, row in df.iterrows():
            d = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
            rows.append((
                symbol, d,
                float(row["Open"]), float(row["High"]), float(row["Low"]),
                float(row["Close"]), float(row["Volume"]), adj
            ))
        with sqlite3.connect(self.path) as c:
            c.executemany("""INSERT INTO daily_bars(symbol, date, open, high, low, close, volume, adjusted)
                             VALUES(?,?,?,?,?,?,?,?)
                             ON CONFLICT(symbol, date) DO UPDATE SET
                             open=excluded.open, high=excluded.high, low=excluded.low,
                             close=excluded.close, volume=excluded.volume, adjusted=excluded.adjusted""", rows)
        return len(rows)

    def get_bars(self, symbol, start=None, end=None):
        query = "SELECT date, open, high, low, close, volume, adjusted FROM daily_bars WHERE symbol=?"
        params = [symbol]
        if start:
            query += " AND date >= ?"
            params.append(str(start)[:10])
        if end:
            query += " AND date <= ?"
            params.append(str(end)[:10])
        query += " ORDER BY date ASC"

        with sqlite3.connect(self.path) as c:
            df = pd.read_sql_query(query, c, params=params)
        if df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Adjusted"])
        df.index = pd.to_datetime(df.pop("date"))
        df.columns = ["Open", "High", "Low", "Close", "Volume", "Adjusted"]
        return df

    def symbols(self):
        with sqlite3.connect(self.path) as c:
            return [r[0] for r in c.execute("SELECT DISTINCT symbol FROM daily_bars ORDER BY symbol").fetchall()]

    def dates(self):
        with sqlite3.connect(self.path) as c:
            return [r[0] for r in c.execute("SELECT DISTINCT date FROM daily_bars ORDER BY date").fetchall()]

    def latest_date(self, symbol):
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT MAX(date) FROM daily_bars WHERE symbol=?", (symbol,)).fetchone()
            return row[0] if row else None
