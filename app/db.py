import sqlite3
import time
import random
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def now(): return datetime.now(timezone.utc).isoformat()

def now_ist_date():
    """BUG-047: Use IST date for daily boundaries instead of UTC."""
    return datetime.now(IST).date().isoformat()

import threading

class DB:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.path=path
        self._conn=None
        self._local=threading.local()
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

        # Engine heartbeat: track last cycle time for health endpoint (BUG-031)
        self._last_cycle_at = None
        self._data_ok = False
        self._exception_counts = {"scanner": 0, "news": 0, "protection": 0}

    def conn(self):
        if self._conn is not None:
            return self._conn
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=30000")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = c
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
            if "target_step" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN target_step REAL DEFAULT 0")
            if "product_type" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN product_type TEXT DEFAULT 'INTRADAY'")
            if "days_held" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN days_held INTEGER DEFAULT 0")
            if "strike_price" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN strike_price REAL DEFAULT 0")
            if "option_type" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN option_type TEXT DEFAULT ''")
            if "expiry_date" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN expiry_date TEXT DEFAULT ''")
            if "legs_info" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN legs_info TEXT DEFAULT ''")
            if "sleeve" not in cols:
                c.execute("ALTER TABLE positions ADD COLUMN sleeve TEXT NOT NULL DEFAULT 'core'")

            t_cols={r[1] for r in c.execute("PRAGMA table_info(trades)").fetchall()}
            if "product_type" not in t_cols:
                c.execute("ALTER TABLE trades ADD COLUMN product_type TEXT DEFAULT 'INTRADAY'")
            if "days_held" not in t_cols:
                c.execute("ALTER TABLE trades ADD COLUMN days_held INTEGER DEFAULT 0")
            if "strike_price" not in t_cols:
                c.execute("ALTER TABLE trades ADD COLUMN strike_price REAL DEFAULT 0")
            if "option_type" not in t_cols:
                c.execute("ALTER TABLE trades ADD COLUMN option_type TEXT DEFAULT ''")
            if "expiry_date" not in t_cols:
                c.execute("ALTER TABLE trades ADD COLUMN expiry_date TEXT DEFAULT ''")

            c.execute("""CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, action TEXT NOT NULL, side TEXT NOT NULL,
                qty INTEGER NOT NULL, price REAL NOT NULL, stop_loss REAL, target REAL,
                product_type TEXT DEFAULT 'INTRADAY', order_type TEXT DEFAULT 'REGULAR',
                status TEXT DEFAULT 'PENDING', strategy TEXT, placed_at TEXT NOT NULL,
                executed_at TEXT, rejection_reason TEXT)""")

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

    def ensure_account(self, starting, target, force_reset=False):
        """Ensure account exists. R2-009: Never silently reset cash or peak_value."""
        acc = self.account()
        if not acc:
            with self.conn() as c:
                c.execute("INSERT INTO account VALUES(1,?,?,?,?,?)", (starting, starting, target, starting, now()))
        elif force_reset:
            with self.conn() as c:
                c.execute("UPDATE account SET starting_capital=?, cash=?, target_capital=?, peak_value=?, updated_at=? WHERE id=1",
                          (starting, starting, target, starting, now()))
        else:
            with self.conn() as c:
                if acc["target_capital"] != target and acc["starting_capital"] != starting:
                    c.execute("UPDATE account SET target_capital=?, starting_capital=?, updated_at=? WHERE id=1", (target, starting, now()))
                elif acc["target_capital"] != target:
                    c.execute("UPDATE account SET target_capital=?, updated_at=? WHERE id=1", (target, now()))
                elif acc["starting_capital"] != starting:
                    c.execute("UPDATE account SET starting_capital=?, updated_at=? WHERE id=1", (starting, now()))

    def update_position_atr(self, symbol, atr):
        with self.conn() as c:
            c.execute("UPDATE positions SET atr=? WHERE symbol=?",(float(atr),symbol))

    def update_current_price(self, symbol, price):
        with self.conn() as c:
            c.execute("UPDATE positions SET current_price=? WHERE symbol=?", (float(price), symbol))

    def update_stop(self, symbol, stop_loss, max_stop_updates=5000):
        """BUG-042: Added retention limit for stop_updates table."""
        with self.conn() as c:
            row=c.execute("SELECT stop_loss FROM positions WHERE symbol=?",(symbol,)).fetchone()
            if not row: return
            old=float(row["stop_loss"]) if row["stop_loss"] is not None else None
            new=float(stop_loss)
            if old is not None and abs(old-new) < 1e-12: return
            c.execute("UPDATE positions SET stop_loss=? WHERE symbol=?",(new,symbol))
            c.execute("INSERT INTO stop_updates(symbol,old_stop,new_stop,created_at) VALUES(?,?,?,?)",
                      (symbol,old,new,now()))
            # BUG-042: Trim stop_updates to prevent unbounded growth
            c.execute("DELETE FROM stop_updates WHERE id <= (SELECT id FROM stop_updates ORDER BY id DESC LIMIT 1 OFFSET ?)", (max_stop_updates,))

    def update_target(self, symbol, target):
        with self.conn() as c:
            c.execute("UPDATE positions SET target=? WHERE symbol=?", (float(target), symbol))

    def update_stop_and_target(self, symbol, stop_loss, target, max_stop_updates=5000):
        """Atomically update stop_loss and target for dynamic expansion."""
        with self.conn() as c:
            row = c.execute("SELECT stop_loss, target FROM positions WHERE symbol=?", (symbol,)).fetchone()
            if not row: return
            old_stop = float(row["stop_loss"]) if row["stop_loss"] is not None else None
            new_stop = float(stop_loss)
            new_target = float(target)
            c.execute("UPDATE positions SET stop_loss=?, target=? WHERE symbol=?", (new_stop, new_target, symbol))
            if old_stop is None or abs(old_stop - new_stop) >= 1e-12:
                c.execute("INSERT INTO stop_updates(symbol,old_stop,new_stop,created_at) VALUES(?,?,?,?)",
                          (symbol, old_stop, new_stop, now()))
                c.execute("DELETE FROM stop_updates WHERE id <= (SELECT id FROM stop_updates ORDER BY id DESC LIMIT 1 OFFSET ?)", (max_stop_updates,))

    def update_position_stops(self, symbol, stop_loss=None, target=None):
        """Update stop_loss and/or target for any position (e.g. F&O or Swing)."""
        with self.conn() as c:
            if stop_loss is not None and target is not None:
                c.execute("UPDATE positions SET stop_loss=?, target=? WHERE symbol=?", (float(stop_loss), float(target), symbol))
            elif stop_loss is not None:
                c.execute("UPDATE positions SET stop_loss=? WHERE symbol=?", (float(stop_loss), symbol))
            elif target is not None:
                c.execute("UPDATE positions SET target=? WHERE symbol=?", (float(target), symbol))

    def realized_pnl_today(self):
        # BUG-047: Use IST date for daily boundaries
        day = now_ist_date()
        with self.conn() as c:
            row=c.execute(
                "SELECT COALESCE(SUM(pnl),0) AS pnl FROM trades WHERE substr(created_at,1,10)=?",
                (day,)).fetchone()
            return float(row["pnl"] if row else 0.0)

    def day_start_equity(self, current_equity):
        # BUG-047: Use IST date for daily boundaries
        day = now_ist_date()
        with self.conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS daily_state(
                         day TEXT PRIMARY KEY, start_equity REAL NOT NULL)""")
            row=c.execute("SELECT start_equity FROM daily_state WHERE day=?",(day,)).fetchone()
            if row: return float(row["start_equity"])
            c.execute("INSERT INTO daily_state(day,start_equity) VALUES(?,?)",(day,float(current_equity)))
            return float(current_equity)

    def positions(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM positions ORDER BY opened_at")]

    def get_position(self, symbol, sleeve="core"):
        with self.conn() as c:
            r = c.execute("SELECT * FROM positions WHERE symbol=? AND sleeve=?", (symbol, sleeve)).fetchone()
            return dict(r) if r else None

    def upsert_position(self, p, sleeve="core"):
        """
        R2-006: Key positions by (sleeve, symbol).
        When adding to an existing position, compute weighted average entry price
        and cumulative entry cost.
        """
        symbol = p["symbol"]
        qty = int(p["qty"])
        entry_price = float(p["entry_price"])
        entry_cost = float(p.get("entry_cost", 0.0) or 0.0)
        current_price = float(p.get("current_price", entry_price))
        stop_loss = float(p["stop_loss"]) if p.get("stop_loss") is not None else None
        target = float(p["target"]) if p.get("target") is not None else None
        strategy = p.get("strategy", "")
        confidence = float(p.get("confidence", 0.0) or 0.0)
        opened_at = p.get("opened_at", now())
        sector = p.get("sector", "Unknown")
        atr = float(p.get("atr", 0.0) or 0.0)
        target_step = float(p.get("target_step", 0.0) or 0.0)
        product_type = p.get("product_type", "INTRADAY")
        days_held = int(p.get("days_held", 0) or 0)
        strike_price = float(p.get("strike_price", 0.0) or 0.0)
        option_type = p.get("option_type", "")
        expiry_date = p.get("expiry_date", "")
        legs_info = p.get("legs_info", "")

        with self.conn() as c:
            row = c.execute("SELECT * FROM positions WHERE sleeve=? AND symbol=?", (sleeve, symbol)).fetchone()
            if row:
                old = dict(row)
                old_qty = int(old["qty"])
                old_entry = float(old["entry_price"])
                old_cost = float(old.get("entry_cost", 0.0) or 0.0)
                tot_qty = old_qty + qty
                w_entry = ((old_qty * old_entry) + (qty * entry_price)) / tot_qty if tot_qty > 0 else entry_price
                cum_cost = old_cost + entry_cost
                c.execute("""UPDATE positions SET qty=?, entry_price=?, current_price=?, entry_cost=?,
                                                  stop_loss=COALESCE(?, stop_loss), target=COALESCE(?, target),
                                                  atr=COALESCE(?, atr), target_step=COALESCE(?, target_step),
                                                  days_held=COALESCE(?, days_held)
                             WHERE sleeve=? AND symbol=?""",
                          (tot_qty, w_entry, current_price, cum_cost, stop_loss, target, atr, target_step, days_held, sleeve, symbol))
            else:
                c.execute("""INSERT INTO positions(sleeve, symbol, side, qty, entry_price, current_price, stop_loss, target,
                                                    strategy, confidence, opened_at, sector, atr, entry_cost, target_step,
                                                    product_type, days_held, strike_price, option_type, expiry_date, legs_info)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (sleeve, symbol, p["side"], qty, entry_price, current_price, stop_loss, target,
                           strategy, confidence, opened_at, sector, atr, entry_cost, target_step,
                           product_type, days_held, strike_price, option_type, expiry_date, legs_info))

    def positions_by_sleeve(self, sleeve="core"):
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM positions WHERE sleeve=? ORDER BY opened_at", (sleeve,))]

    def delete_position(self, symbol, sleeve=None):
        with self.conn() as c:
            if sleeve:
                c.execute("DELETE FROM positions WHERE symbol=? AND sleeve=?", (symbol, sleeve))
            else:
                c.execute("DELETE FROM positions WHERE symbol=?", (symbol,))

    def trades(self,limit=10):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?",(limit,))]

    def all_trades(self):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id")]

    def decisions(self,limit=10):
        with self.conn() as c:return [dict(r) for r in c.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?",(limit,))]

    def update_account(self,cash,peak):
        with self.conn() as c:c.execute("UPDATE account SET cash=?,peak_value=?,updated_at=? WHERE id=1",(cash,peak,now()))

    def set_market(self,regime,sentiment,nifty,data_ok):
        self._data_ok = bool(data_ok)
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

    # BUG-031: Engine heartbeat tracking
    def set_last_cycle(self):
        self._last_cycle_at = now()

    def get_last_cycle(self):
        return self._last_cycle_at

    # BUG-029: Exception counting
    def count_exception(self, category):
        self._exception_counts[category] = self._exception_counts.get(category, 0) + 1

    def get_exception_counts(self):
        return dict(self._exception_counts)

    def reset_exception_counts(self):
        self._exception_counts = {k: 0 for k in self._exception_counts}

    def positions_by_product(self, product_type=None):
        with self.conn() as c:
            if product_type:
                return [dict(r) for r in c.execute("SELECT * FROM positions WHERE UPPER(product_type)=? ORDER BY opened_at", (product_type.upper(),))]
            return [dict(r) for r in c.execute("SELECT * FROM positions ORDER BY opened_at")]

    def trades_by_product(self, product_type=None, limit=50):
        with self.conn() as c:
            if product_type:
                return [dict(r) for r in c.execute("SELECT * FROM trades WHERE UPPER(product_type)=? ORDER BY id DESC LIMIT ?", (product_type.upper(), limit))]
            return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))]

    def get_capital_allocation(self):
        import json
        raw = self.get_setting("capital_allocation", "")
        if raw:
            try:
                data = json.loads(raw)
                if "intraday" in data and "swing" in data and "fno" in data:
                    return {k: float(v) for k, v in data.items()}
            except Exception:
                pass
        return {"intraday": 40.0, "swing": 40.0, "fno": 20.0}

    def set_capital_allocation(self, intraday, swing, fno):
        import json
        i = max(0.0, float(intraday))
        s = max(0.0, float(swing))
        f = max(0.0, float(fno))
        total = i + s + f
        if total <= 0:
            i, s, f = 40.0, 40.0, 20.0
            total = 100.0
        data = {
            "intraday": round(i / total * 100.0, 1),
            "swing": round(s / total * 100.0, 1),
            "fno": round(f / total * 100.0, 1)
        }
        self.set_setting("capital_allocation", json.dumps(data))
        return data

    def increment_all_swing_days_held(self):
        with self.conn() as c:
            c.execute("UPDATE positions SET days_held = COALESCE(days_held, 0) + 1 WHERE UPPER(product_type) = 'SWING'")

    def add_order(self, order):
        with self.conn() as c:
            cur = c.execute("""
                INSERT INTO orders(symbol, action, side, qty, price, stop_loss, target,
                                  product_type, order_type, status, strategy, placed_at, executed_at, rejection_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order["symbol"],
                order.get("action", "BUY"),
                order.get("side", "LONG"),
                int(order["qty"]),
                float(order["price"]),
                float(order["stop_loss"]) if order.get("stop_loss") is not None else None,
                float(order["target"]) if order.get("target") is not None else None,
                str(order.get("product_type", "INTRADAY")),
                str(order.get("order_type", "REGULAR")),
                str(order.get("status", "PENDING")),
                str(order.get("strategy", "")),
                str(order.get("placed_at", now())),
                order.get("executed_at"),
                order.get("rejection_reason")
            ))
            return cur.lastrowid

    def orders(self, limit=50, status=None):
        with self.conn() as c:
            if status:
                rows = c.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def pending_orders(self):
        with self.conn() as c:
            rows = c.execute("SELECT * FROM orders WHERE status='PENDING' ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    def fill_order(self, order_id, fill_price=None):
        with self.conn() as c:
            c.execute("UPDATE orders SET status='FILLED', executed_at=? WHERE id=?", (now(), order_id))

    def cancel_order(self, order_id, reason="Cancelled"):
        with self.conn() as c:
            c.execute("UPDATE orders SET status='CANCELLED', rejection_reason=? WHERE id=?", (reason, order_id))

    def clear_positions(self):
        with self.conn() as c:
            c.execute("DELETE FROM positions")
