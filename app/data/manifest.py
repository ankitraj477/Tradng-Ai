import sqlite3
from datetime import datetime, timezone
from pathlib import Path

class DatasetManifest:
    def __init__(self, path="data/manifest.db"):
        self.path = Path(path)
        if self.path.suffix == ".json":
            self.path = self.path.with_suffix(".db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        with self._conn:
            self._conn.execute("""CREATE TABLE IF NOT EXISTS manifest (
                source TEXT, kind TEXT, symbol TEXT, day TEXT,
                start TEXT, end TEXT, rows INTEGER, adjusted INTEGER, recorded_at TEXT,
                PRIMARY KEY(source, kind, symbol, day)
            )""")

    def record(self, source, kind, symbol, start, end, rows, adjusted=False):
        day = str(end)[:10]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute("""INSERT OR REPLACE INTO manifest
                (source, kind, symbol, day, start, end, rows, adjusted, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(source), str(kind), str(symbol), day, str(start), str(end), int(rows), int(bool(adjusted)), now))

    def records(self):
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            return [{**dict(r), "adjusted": bool(r["adjusted"])} for r in self._conn.execute("SELECT source, kind, symbol, start, end, rows, adjusted, recorded_at FROM manifest ORDER BY recorded_at")]