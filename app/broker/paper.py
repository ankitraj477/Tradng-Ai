"""
Paper Trading Broker Adapter.
Local paper execution implementation storing orders and state in SQLite.
Guarantees 100% paper trading without broker API keys or financial risk.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .base import AbstractBrokerAdapter
from ..exchange_rules import round_to_tick, validate_order_microstructure


class PaperBrokerAdapter(AbstractBrokerAdapter):
    """
    Paper Broker Adapter.
    Executes trades against internal ledger and market data quotes with realistic
    exchange microstructure (5-paise tick rounding, circuit limit checks).
    """

    def __init__(self, db, cfg=None):
        self.db = db
        self.cfg = cfg or {}

    @property
    def name(self) -> str:
        return "PAPER_SIMULATOR"

    @property
    def is_live(self) -> bool:
        return False

    def connect(self) -> bool:
        return True

    def get_funds(self) -> Dict[str, float]:
        a = self.db.account()
        if not a:
            self.db.ensure_account(100000.0, 200000.0)
            a = self.db.account()
        cash = float(a.get("cash", 0.0) if a else 0.0)
        return {
            "available_cash": cash,
            "collateral": 0.0,
            "utilized_margin": 0.0,
            "total_balance": cash
        }


    def place_order(
        self,
        symbol: str,
        action: str,
        qty: int,
        price: float,
        product_type: str = "INTRADAY",
        order_type: str = "MARKET",
        trigger_price: Optional[float] = None,
        tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validates exchange rules and records the paper order."""
        rounded_px = round_to_tick(price)
        side = "LONG" if action.upper() in ("BUY", "LONG") else "SHORT"

        # Check microstructure
        val = validate_order_microstructure(symbol, action, rounded_px)
        if not val["ok"]:
            return {
                "success": False,
                "order_id": None,
                "status": "REJECTED",
                "reason": val["reason"]
            }

        now_ts = datetime.now(timezone.utc).isoformat()
        with self.db.conn() as c:
            cur = c.execute("""
                INSERT INTO orders(symbol, action, side, qty, price, product_type, order_type, status, strategy, placed_at, executed_at)
                VALUES(?,?,?,?,?,?,?,'FILLED',?,?,?)
            """, (symbol, action.upper(), side, qty, rounded_px, product_type.upper(), order_type.upper(), tag or "STRATEGY", now_ts, now_ts))
            order_id = cur.lastrowid

        return {
            "success": True,
            "order_id": str(order_id),
            "status": "FILLED",
            "symbol": symbol,
            "action": action.upper(),
            "qty": qty,
            "fill_price": rounded_px,
            "product_type": product_type
        }

    def cancel_order(self, order_id: str) -> bool:
        with self.db.conn() as c:
            c.execute("UPDATE orders SET status='CANCELLED' WHERE id=?", (order_id,))
        return True

    def get_positions(self) -> List[Dict[str, Any]]:
        return self.db.positions()

    def get_orders(self) -> List[Dict[str, Any]]:
        return self.db.orders(100)
