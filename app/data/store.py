"""
Institutional market data store under data/research/.
Supports:
- Daily split/bonus adjusted OHLCV bars with ADTV20 computation.
- India VIX daily series.
- Corporate actions log (splits, dividends, bonus).
- Fast indexed querying for systematic backtesting and live paper trading.
"""

import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Union


class MarketDataStore:
    """Research & execution daily market data store under data/research/."""

    def __init__(self, path: Union[str, Path] = "data/research/research.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")

            # Daily OHLCV table
            c.execute("""CREATE TABLE IF NOT EXISTS daily_bars (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                adjusted INTEGER NOT NULL DEFAULT 1,
                turnover REAL,
                PRIMARY KEY (symbol, date)
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_bars_date ON daily_bars(date)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_bars_sym ON daily_bars(symbol)")

            # India VIX table
            c.execute("""CREATE TABLE IF NOT EXISTS india_vix (
                date TEXT PRIMARY KEY,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL
            )""")

            # Corporate actions log
            c.execute("""CREATE TABLE IF NOT EXISTS corporate_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                action_type TEXT NOT NULL,
                ratio REAL NOT NULL,
                description TEXT
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_actions_sym ON corporate_actions(symbol, date)")

    def save_bars(self, symbol: str, df: pd.DataFrame, adjusted: bool = True) -> int:
        """Save OHLCV dataframe for symbol."""
        if df is None or df.empty:
            return 0
        sym = symbol.strip().upper()
        adj = 1 if adjusted else 0
        rows = []
        for idx, row in df.iterrows():
            d = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
            op = float(row["Open"])
            hi = float(row["High"])
            lo = float(row["Low"])
            cl = float(row["Close"])
            vol = float(row["Volume"])
            turnover = float(row.get("Turnover", cl * vol))
            rows.append((sym, d, op, hi, lo, cl, vol, adj, turnover))

        with sqlite3.connect(self.path) as c:
            c.executemany("""INSERT INTO daily_bars(symbol, date, open, high, low, close, volume, adjusted, turnover)
                             VALUES(?,?,?,?,?,?,?,?,?)
                             ON CONFLICT(symbol, date) DO UPDATE SET
                             open=excluded.open, high=excluded.high, low=excluded.low,
                             close=excluded.close, volume=excluded.volume,
                             adjusted=excluded.adjusted, turnover=excluded.turnover""", rows)
        return len(rows)

    def get_bars(
        self,
        symbol: str,
        start: Optional[Union[str, pd.Timestamp]] = None,
        end: Optional[Union[str, pd.Timestamp]] = None,
        with_adtv: bool = True
    ) -> pd.DataFrame:
        """Retrieve OHLCV bars for symbol, optionally with ADTV20 computed."""
        sym = symbol.strip().upper()
        query = "SELECT date, open, high, low, close, volume, adjusted, turnover FROM daily_bars WHERE symbol=?"
        params = [sym]
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
            cols = ["Open", "High", "Low", "Close", "Volume", "Adjusted", "Turnover"]
            if with_adtv:
                cols.append("ADTV20")
            return pd.DataFrame(columns=cols)

        df.index = pd.to_datetime(df.pop("date"))
        df.columns = ["Open", "High", "Low", "Close", "Volume", "Adjusted", "Turnover"]

        if with_adtv and len(df) > 0:
            # Turnover in INR = Close * Volume if not specified
            df["Turnover"] = df["Turnover"].fillna(df["Close"] * df["Volume"])
            df["ADTV20"] = df["Turnover"].rolling(20, min_periods=1).mean()

        return df

    def save_vix(self, df: pd.DataFrame) -> int:
        """Save India VIX series."""
        if df is None or df.empty:
            return 0
        rows = []
        for idx, row in df.iterrows():
            d = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
            rows.append((
                d,
                float(row.get("Open", row["Close"])),
                float(row.get("High", row["Close"])),
                float(row.get("Low", row["Close"])),
                float(row["Close"])
            ))
        with sqlite3.connect(self.path) as c:
            c.executemany("""INSERT INTO india_vix(date, open, high, low, close)
                             VALUES(?,?,?,?,?)
                             ON CONFLICT(date) DO UPDATE SET
                             open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close""", rows)
        return len(rows)

    def get_vix(self, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
        """Retrieve India VIX series."""
        query = "SELECT date, open, high, low, close FROM india_vix WHERE 1=1"
        params = []
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
            return pd.DataFrame(columns=["Open", "High", "Low", "Close"])
        df.index = pd.to_datetime(df.pop("date"))
        df.columns = ["Open", "High", "Low", "Close"]
        return df

    def log_corporate_action(self, symbol: str, date_str: str, action_type: str, ratio: float, description: str = ""):
        """Log stock split, bonus, or dividend corporate action."""
        with sqlite3.connect(self.path) as c:
            c.execute("""INSERT INTO corporate_actions(symbol, date, action_type, ratio, description)
                         VALUES(?,?,?,?,?)""", (symbol.upper(), str(date_str)[:10], action_type.upper(), float(ratio), description))

    def get_corporate_actions(self, symbol: str) -> List[Dict]:
        with sqlite3.connect(self.path) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute("SELECT * FROM corporate_actions WHERE symbol=? ORDER BY date ASC", (symbol.upper(),)).fetchall()
            return [dict(r) for r in rows]

    def symbols(self) -> List[str]:
        with sqlite3.connect(self.path) as c:
            return [r[0] for r in c.execute("SELECT DISTINCT symbol FROM daily_bars ORDER BY symbol").fetchall()]

    def latest_date(self, symbol: str) -> Optional[str]:
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT MAX(date) FROM daily_bars WHERE symbol=?", (symbol.upper(),)).fetchone()
            return row[0] if row else None
