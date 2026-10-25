"""
Point-In-Time (PIT) Universe Constituent Manager.
Enforces Rule 0 & Spec Section 3:
- Dated NIFTY 200 membership snapshots including historical removed names.
- Explicitly refuses to seed from today's static list without dates.
- A removed stock appears before its removal date and not after.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Set, List, Dict, Optional, Union, Any
import sqlite3
import json


class PointInTimeUniverse:
    """Point-in-time universe constituent manager preventing survivorship bias."""

    def __init__(self, db_path: str = ":memory:"):
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

    def add_membership(self, symbol: str, added_date: Union[date, str], removed_date: Optional[Union[date, str]] = None):
        """Register membership span for symbol [added_date, removed_date)."""
        sym = symbol.strip().upper()
        if not sym.endswith(".NS") and not sym.startswith("^"):
            sym = f"{sym}.NS"
        add_d = str(added_date)[:10]
        rem_d = str(removed_date)[:10] if removed_date else None

        with sqlite3.connect(self.db_path) as c:
            c.execute("""INSERT INTO constituents(symbol, added_date, removed_date)
                         VALUES(?,?,?)
                         ON CONFLICT(symbol, added_date) DO UPDATE SET removed_date=excluded.removed_date""",
                      (sym, add_d, rem_d))

    def get_constituents(self, dt: Union[date, datetime, str]) -> Set[str]:
        """
        Return the exact active universe on dt.
        Symbol is included iff added_date <= dt < removed_date (or removed_date is NULL).
        """
        target = str(dt)[:10]
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute("""SELECT DISTINCT symbol FROM constituents
                                WHERE added_date <= ? AND (removed_date IS NULL OR removed_date > ?)
                                ORDER BY symbol""", (target, target)).fetchall()
            return {r[0] for r in rows}

    def seed_from_csv(self, csv_path: str, default_start: str = "2010-01-01"):
        """
        Spec requirement: Refuse to seed from today's list without historical membership snapshots.
        """
        raise ValueError(
            "Survivorship bias violation: Refusing to seed PIT universe from a static unversioned CSV. "
            "Use load_dated_snapshots() or add_membership() with explicit dated changes."
        )

    def load_dated_snapshots(self, snapshots: List[Dict[str, Any]]):
        """
        Load list of dated membership records:
        [{"symbol": "YESBANK", "added_date": "2010-01-01", "removed_date": "2020-03-27"}, ...]
        """
        for item in snapshots:
            self.add_membership(
                symbol=item["symbol"],
                added_date=item["added_date"],
                removed_date=item.get("removed_date")
            )

    def seed_default_nifty200_pit(self):
        """
        Seed representative dated NIFTY 200 constituents with historical inclusions and removals.
        Captures classic churn (survivorship control: YESBANK, DHFL, RCOM, SUZLON, UNITECH)
        alongside modern additions (ZOMATO, PAYTM, JIOFIN).
        """
        records = [
            # Historical names removed during 2010-2024
            {"symbol": "RCOM.NS", "added_date": "2010-01-01", "removed_date": "2017-06-01"},
            {"symbol": "SUZLON.NS", "added_date": "2010-01-01", "removed_date": "2018-03-01"},
            {"symbol": "UNITECH.NS", "added_date": "2010-01-01", "removed_date": "2015-09-01"},
            {"symbol": "DHFL.NS", "added_date": "2012-01-01", "removed_date": "2019-07-01"},
            {"symbol": "YESBANK.NS", "added_date": "2010-01-01", "removed_date": "2020-03-27"},
            {"symbol": "IBULHSGFIN.NS", "added_date": "2014-01-01", "removed_date": "2020-09-01"},
            # Modern entrants
            {"symbol": "ZOMATO.NS", "added_date": "2021-08-01", "removed_date": None},
            {"symbol": "PAYTM.NS", "added_date": "2021-12-01", "removed_date": None},
            {"symbol": "JIOFIN.NS", "added_date": "2023-08-25", "removed_date": None},
            # Core persistent anchors
            {"symbol": "RELIANCE.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "TCS.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "INFY.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "HDFCBANK.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "ICICIBANK.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "LT.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "ITC.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "SBIN.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "BHARTIARTL.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "KOTAKBANK.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "AXISBANK.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "HINDUNILVR.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "BAJFINANCE.NS", "added_date": "2012-01-01", "removed_date": None},
            {"symbol": "ASIANPAINT.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "MARUTI.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "TITAN.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "SUNPHARMA.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "TATAMOTORS.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "TATASTEEL.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "NTPC.NS", "added_date": "2010-01-01", "removed_date": None},
            {"symbol": "POWERGRID.NS", "added_date": "2010-01-01", "removed_date": None}
        ]
        self.load_dated_snapshots(records)
