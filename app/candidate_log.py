import sqlite3
from pathlib import Path
import pandas as pd


class CandidateLog:
    """Stores every scanned candidate with technical features and forward returns."""
    def __init__(self, db_path="data/candidates.db"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS candidate_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                rsi REAL,
                ema20 REAL,
                ema50 REAL,
                rel_volume REAL,
                volatility REAL,
                ret_5 REAL,
                ret_20 REAL,
                bull_score REAL,
                bear_score REAL,
                action TEXT,
                forward_ret_1d REAL,
                forward_ret_5d REAL,
                forward_ret_20d REAL
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_cand_sym_ts ON candidate_log(symbol, timestamp)")

    def record(self, symbol, timestamp, price, feat, action=None):
        ts = str(timestamp)[:19]
        with sqlite3.connect(self.path) as c:
            c.execute("""INSERT INTO candidate_log(
                timestamp, symbol, price, rsi, ema20, ema50, rel_volume,
                volatility, ret_5, ret_20, bull_score, bear_score, action
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                ts, symbol, float(price),
                float(feat.get("rsi") or 0.0), float(feat.get("ema20") or 0.0),
                float(feat.get("ema50") or 0.0), float(feat.get("rel_volume") or 1.0),
                float(feat.get("volatility") or 0.0), float(feat.get("ret_5") or 0.0),
                float(feat.get("ret_20") or 0.0), float(feat.get("bull_score") or 0.0),
                float(feat.get("bear_score") or 0.0), action
            ))

    def update_forward_return(self, candidate_id, horizon, forward_price):
        col = f"forward_ret_{horizon}d"
        if col not in {"forward_ret_1d", "forward_ret_5d", "forward_ret_20d"}: return
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT price FROM candidate_log WHERE id=?", (candidate_id,)).fetchone()
            if row and row[0] > 0:
                ret = (float(forward_price) / float(row[0])) - 1.0
                c.execute(f"UPDATE candidate_log SET {col}=? WHERE id=?", (ret, candidate_id))

    def get_dataset(self, min_samples=10):
        with sqlite3.connect(self.path) as c:
            df = pd.read_sql_query("SELECT * FROM candidate_log ORDER BY id ASC", c)
        return df
