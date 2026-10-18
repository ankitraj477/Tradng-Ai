from datetime import datetime
from pathlib import Path
import sqlite3
import csv


class PointInTimeUniverse:
    """Point-in-time universe constituent manager preventing survivorship bias."""
    def __init__(self, db_path=":memory:"):
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS constituents (
                symbol TEXT NOT NULL,
                added_date TEXT NOT NULL,
                removed_date TEXT,
                PRIMARY KEY (symbol, added_date)
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_pit_dates ON constituents(added_date, removed_date)")

    def add_membership(self, symbol, added_date, removed_date=None):
        with sqlite3.connect(self.db_path) as c:
            c.execute("""INSERT INTO constituents(symbol, added_date, removed_date)
                         VALUES(?,?,?)
                         ON CONFLICT(symbol, added_date) DO UPDATE SET removed_date=excluded.removed_date""",
                      (symbol, str(added_date)[:10], str(removed_date)[:10] if removed_date else None))

    def get_constituents(self, dt):
        target = str(dt)[:10]
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute("""SELECT DISTINCT symbol FROM constituents
                                WHERE added_date <= ? AND (removed_date IS NULL OR removed_date > ?)
                                ORDER BY symbol""", (target, target)).fetchall()
            return {r[0] for r in rows}

    def seed_from_csv(self, csv_path, default_start="2010-01-01"):
        p = Path(csv_path)
        if not p.exists(): return 0
        symbols = []
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = (row.get("symbol") or row.get("Symbol") or "").strip()
                if sym: symbols.append(sym if sym.endswith(".NS") else f"{sym}.NS")
        for sym in symbols:
            self.add_membership(sym, default_start, None)
        return len(symbols)
