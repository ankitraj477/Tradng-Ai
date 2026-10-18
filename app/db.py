import sqlite3
import time
import random
from pathlib import Path
from datetime import datetime, timezone
def now(): return datetime.now(timezone.utc).isoformat()
class DB:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.path=path
        self._conn=None
        if path==":memory:":
            self._conn=sqlite3.connect(":memory:", check_same_thread=False, timeout=30.0)
            self._conn.row_factory=sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout=30000")
        self.init()
        self.migrate()
        if self._conn is not None:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        else:
            with self.conn() as c:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA busy_timeout=30000")
                c.execute("PRAGMA synchronous=NORMAL")

    def conn(self):
        if self._conn is not None:
            return self._conn
        c = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.execute("PRAGMA synchronous=NORMAL")
        return c

    def execute_with_retry(self, fn, max_retries=5, base_delay=0.05):
        """Executes a database callback with exponential backoff if lock contention occurs."""
        for attempt in range(max_retries):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                if ("locked" in str(exc).lower() or "busy" in str(exc).lower()) and attempt < max_retries - 1:
                    sleep_time = base_delay * (2 ** attempt) + random.uniform(0.01, 0.05)
                    time.sleep(sleep_time)
                else:
                    raise
    def init(self):
        from .schema import SCHEMA
        with self.conn() as c:c.executescript(SCHEMA)
    def migrate(self):
        # Backward-compatible schema migration for databases created before V8.1.
        with self.conn() as c:
            cols={r[1] for r in c.execute("PRAGMA table_info(positions)").fetchall()}
            if "atr" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN atr REAL")
            if "entry_cost" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN entry_cost REAL DEFAULT 0")

    def log(self, level, message, max_rows=2000):
        # 1. Stream to rotating log file and console
        try:
            from .logger import get_logger
            import logging
            lvl_name = str(level).lower()
            if lvl_name == "warn":
                lvl_name = "warning"
            log_fn = getattr(get_logger("db"), lvl_name, None)
            if callable(log_fn):
                log_fn(message)
            else:
                get_logger("db").info(f"[{level}] {message}")
        except Exception:
            pass

        # 2. Persist to SQLite events table with concurrency retry
        def _write():
            with self.conn() as c:
                c.execute("INSERT INTO events(level,message,created_at) VALUES(?,?,?)", (level, message, now()))
                c.execute("DELETE FROM events WHERE id <= (SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?)", (max_rows,))
        try:
            self.execute_with_retry(_write)
        except Exception:
            pass
    def account(self):
        with self.conn() as c:
            r=c.execute("SELECT * FROM account WHERE id=1").fetchone(); return dict(r) if r else None
    def ensure_account(self,starting,target):
        if not self.account():
            with self.conn() as c:c.execute("INSERT INTO account VALUES(1,?,?,?,?,?)",(starting,starting,target,starting,now()))
    def update_position_atr(self, symbol, atr):
        with self.conn() as c:
            c.execute("UPDATE positions SET atr=? WHERE symbol=?",(float(atr),symbol))

    def update_stop(self, symbol, stop_loss):
        with self.conn() as c:
            row=c.execute("SELECT stop_loss FROM positions WHERE symbol=?",(symbol,)).fetchone()
            if not row: return
            old=float(row["stop_loss"]) if row["stop_loss"] is not None else None
            new=float(stop_loss)
            if old is not None and abs(old-new) < 1e-12: return
            c.execute("UPDATE positions SET stop_loss=? WHERE symbol=?",(new,symbol))
            c.execute("INSERT INTO stop_updates(symbol,old_stop,new_stop,created_at) VALUES(?,?,?,?)",
                      (symbol,old,new,now()))

    def realized_pnl_today(self):
        from datetime import datetime, timezone
        day=datetime.now(timezone.utc).date().isoformat()
        with self.conn() as c:
            row=c.execute(
                "SELECT COALESCE(SUM(pnl),0) AS pnl FROM trades WHERE substr(created_at,1,10)=?",
                (day,)).fetchone()
            return float(row["pnl"] if row else 0.0)

    def day_start_equity(self, current_equity):
        # Persist the first observed equity for each UTC day in a small state table.
        day=datetime.now(timezone.utc).date().isoformat()
        with self.conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS daily_state(
                         day TEXT PRIMARY KEY, start_equity REAL NOT NULL)""")
            row=c.execute("SELECT start_equity FROM daily_state WHERE day=?",(day,)).fetchone()
            if row: return float(row["start_equity"])
            c.execute("INSERT INTO daily_state(day,start_equity) VALUES(?,?)",(day,float(current_equity)))
            return float(current_equity)

    def positions(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM positions ORDER BY opened_at")]
    def trades(self,limit=10):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?",(limit,))]
    def all_trades(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id")]
    def decisions(self,limit=10):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?",(limit,))]
    def update_account(self,cash,peak):
        with self.conn() as c:c.execute("UPDATE account SET cash=?,peak_value=?,updated_at=? WHERE id=1",(cash,peak,now()))
    def set_market(self,regime,sentiment,nifty,data_ok):
        with self.conn() as c:c.execute("""INSERT INTO market_state(id,regime,global_sentiment,nifty_condition,last_update,data_ok)
        VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET regime=excluded.regime,global_sentiment=excluded.global_sentiment,
        nifty_condition=excluded.nifty_condition,last_update=excluded.last_update,data_ok=excluded.data_ok""",(regime,sentiment,nifty,now(),int(data_ok)))
    def market(self):
        with self.conn() as c:
            r=c.execute("SELECT * FROM market_state WHERE id=1").fetchone();return dict(r) if r else {}
    def add_decision(self,d):
        with self.conn() as c:c.execute("""INSERT INTO decisions(symbol,action,confidence,strategy,reason,risk_decision,created_at)
        VALUES(?,?,?,?,?,?,?)""",(d["symbol"],d["action"],d["confidence"],d["strategy"],d["reason"],d["risk_decision"],now()))
    def total_realized_pnl(self):
        with self.conn() as c:
            row=c.execute("SELECT COALESCE(SUM(pnl),0) AS pnl FROM trades").fetchone()
            return float(row["pnl"] if row else 0.0)

    def add_equity(self,value,pnl,max_rows=2000):
        with self.conn() as c:
            c.execute("INSERT INTO equity_curve(value,pnl,created_at) VALUES(?,?,?)",(value,pnl,now()))
            c.execute("DELETE FROM equity_curve WHERE id <= (SELECT id FROM equity_curve ORDER BY id DESC LIMIT 1 OFFSET ?)",(max_rows,))
    def equity(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM equity_curve ORDER BY id")]

    def set_setting(self, key, value):
        with self.conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS system_settings(
                         key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            c.execute("""INSERT INTO system_settings(key, value) VALUES(?,?)
                         ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (str(key), str(value)))

    def get_setting(self, key, default="true"):
        with self.conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS system_settings(
                         key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            row = c.execute("SELECT value FROM system_settings WHERE key=?", (str(key),)).fetchone()
            return str(row["value"]) if row else str(default)

    def is_auto_trading_enabled(self):
        return self.get_setting("auto_trading", "true").lower() in ("true", "1", "yes")

    def set_auto_trading(self, enabled: bool):
        self.set_setting("auto_trading", "true" if enabled else "false")

