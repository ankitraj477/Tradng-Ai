"""
Bracket Order & OCO (One-Cancels-the-Other) Order Manager.
Maintains linked conditional Stop-Loss and Take-Profit legs for every position.
Guarantees that when one exit leg triggers, the sibling leg is automatically cancelled
to prevent unintended reverse positions.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .exchange_rules import round_to_tick


class BracketOrderManager:
    """
    Manages conditional Bracket Orders with OCO logic.
    For each executed trade, registers:
    - SL Leg (Trigger order)
    - Target Leg (Limit order)
    Linked by a shared bracket_id (the position symbol).
    """

    def __init__(self, db):
        self.db = db
        self._init_bracket_table()

    def _init_bracket_table(self):
        """Ensures the bracket_orders table exists in the database."""
        with self.db.conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS bracket_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bracket_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    leg_type TEXT NOT NULL, -- 'SL' or 'TARGET'
                    action TEXT NOT NULL,   -- 'BUY' or 'SELL'
                    qty INTEGER NOT NULL,
                    trigger_price REAL NOT NULL,
                    status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE', 'FILLED', 'CANCELLED_OCO'
                    created_at TEXT NOT NULL,
                    executed_at TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_bracket_sym ON bracket_orders(symbol, status)")

    def create_bracket(self, symbol: str, side: str, qty: int, entry_price: float, stop_loss: float, target: float) -> Dict[str, Any]:
        """
        Registers an active OCO bracket pair for a newly opened position.
        If long: entry BUY -> SL leg is SELL at stop_loss, Target leg is SELL at target.
        If short: entry SHORT -> SL leg is BUY at stop_loss, Target leg is BUY at target.
        """
        now_ts = datetime.now(timezone.utc).isoformat()
        bracket_id = f"BRK-{symbol}-{int(datetime.now().timestamp())}"
        exit_action = "SELL" if side.upper() in ("LONG", "BUY") else "BUY"

        sl_px = round_to_tick(stop_loss)
        tp_px = round_to_tick(target)

        # Cancel any previous active brackets for this symbol to prevent duplicates
        self.cancel_bracket(symbol, reason="SUPERSEDED")

        with self.db.conn() as c:
            # 1. Stop-Loss Leg
            c.execute("""
                INSERT INTO bracket_orders(bracket_id, symbol, leg_type, action, qty, trigger_price, status, created_at)
                VALUES(?,?,?,?,?,?,'ACTIVE',?)
            """, (bracket_id, symbol, "SL", exit_action, qty, sl_px, now_ts))

            # 2. Take-Profit Target Leg
            c.execute("""
                INSERT INTO bracket_orders(bracket_id, symbol, leg_type, action, qty, trigger_price, status, created_at)
                VALUES(?,?,?,?,?,?,'ACTIVE',?)
            """, (bracket_id, symbol, "TARGET", exit_action, qty, tp_px, now_ts))

        return {
            "bracket_id": bracket_id,
            "symbol": symbol,
            "sl_price": sl_px,
            "target_price": tp_px,
            "qty": qty,
            "status": "ACTIVE"
        }

    def evaluate_bracket(self, symbol: str, side: str, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Evaluates active bracket orders for a symbol against live market price.
        If Target hits -> fills Target and automatically CANCELS Stop-Loss via OCO.
        If Stop-Loss hits -> fills SL and automatically CANCELS Target via OCO.
        """
        current_px = round_to_tick(current_price)
        with self.db.conn() as c:
            rows = c.execute("""
                SELECT * FROM bracket_orders WHERE symbol=? AND status='ACTIVE'
            """, (symbol,)).fetchall()

        if not rows:
            return None

        legs = {r["leg_type"]: dict(r) for r in rows}
        sl_leg = legs.get("SL")
        tp_leg = legs.get("TARGET")

        if not sl_leg or not tp_leg:
            return None

        is_long = side.upper() in ("LONG", "BUY")
        triggered_leg = None
        canceled_leg = None
        trigger_reason = ""

        if is_long:
            # Long position: SL triggers if price <= stop; Target triggers if price >= target
            if current_px <= sl_leg["trigger_price"]:
                triggered_leg = sl_leg
                canceled_leg = tp_leg
                trigger_reason = "STOP_LOSS_HIT"
            elif current_px >= tp_leg["trigger_price"]:
                triggered_leg = tp_leg
                canceled_leg = sl_leg
                trigger_reason = "TARGET_HIT"
        else:
            # Short position: SL triggers if price >= stop; Target triggers if price <= target
            if current_px >= sl_leg["trigger_price"]:
                triggered_leg = sl_leg
                canceled_leg = tp_leg
                trigger_reason = "STOP_LOSS_HIT"
            elif current_px <= tp_leg["trigger_price"]:
                triggered_leg = tp_leg
                canceled_leg = sl_leg
                trigger_reason = "TARGET_HIT"

        if triggered_leg and canceled_leg:
            now_ts = datetime.now(timezone.utc).isoformat()
            with self.db.conn() as c:
                # Fill triggered leg
                c.execute("""
                    UPDATE bracket_orders SET status='FILLED', executed_at=? WHERE id=?
                """, (now_ts, triggered_leg["id"]))

                # Cancel sibling leg via OCO
                c.execute("""
                    UPDATE bracket_orders SET status='CANCELLED_OCO', executed_at=? WHERE id=?
                """, (now_ts, canceled_leg["id"]))

            return {
                "triggered": True,
                "reason": trigger_reason,
                "leg_type": triggered_leg["leg_type"],
                "exit_action": triggered_leg["action"],
                "qty": triggered_leg["qty"],
                "fill_price": current_px,
                "canceled_leg_type": canceled_leg["leg_type"]
            }

        return None

    def cancel_bracket(self, symbol: str, reason: str = "POSITION_CLOSED"):
        """Cancels all active bracket legs when a position is closed manually, at EOD, or replaced."""
        now_ts = datetime.now(timezone.utc).isoformat()
        with self.db.conn() as c:
            c.execute("""
                UPDATE bracket_orders 
                SET status='CANCELLED_' || ?, executed_at=? 
                WHERE symbol=? AND status='ACTIVE'
            """, (reason, now_ts, symbol))

    def update_stop_loss(self, symbol: str, new_stop: float):
        """Updates the trigger price of the active Stop-Loss leg (e.g. for dynamic trailing stop / breakeven)."""
        rounded_sl = round_to_tick(new_stop)
        with self.db.conn() as c:
            c.execute("""
                UPDATE bracket_orders 
                SET trigger_price=? 
                WHERE symbol=? AND leg_type='SL' AND status='ACTIVE'
            """, (rounded_sl, symbol))

    def get_active_brackets(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns currently active bracket legs, optionally filtered by symbol."""
        with self.db.conn() as c:
            if symbol:
                rows = c.execute("SELECT * FROM bracket_orders WHERE symbol=? AND status='ACTIVE' ORDER BY id ASC", (symbol,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM bracket_orders WHERE status='ACTIVE' ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

    def get_all_brackets(self, symbol: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns bracket order history including FILLED and CANCELLED_OCO legs."""
        with self.db.conn() as c:
            if symbol:
                rows = c.execute("SELECT * FROM bracket_orders WHERE symbol=? ORDER BY id DESC LIMIT ?", (symbol, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM bracket_orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

