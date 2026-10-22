"""
Swing Execution Engine (CNC / Delivery).
Manages multi-day cash delivery purchases and exits using delivery cost models.
"""
from datetime import datetime, timezone
from ..exchange_rules import round_to_tick, validate_order_microstructure
from ..bracket_orders import BracketOrderManager


class SwingExecution:
    def __init__(self, db, cfg=None):
        self.db = db
        self.cfg = cfg or {}
        self.bracket_manager = BracketOrderManager(self.db)

    def _cost(self, notional: float, action: str) -> float:
        """Calculate delivery taxes and fees (STT 0.1% on buy & sell) using unified CostModel."""
        if not hasattr(self, "_cost_model"):
            from ..costs import CostModel
            self._cost_model = CostModel(self.cfg)
        return self._cost_model.calculate(notional, action, segment="DELIVERY")

    def buy_delivery(self, symbol: str, qty: int, price: float, stop_loss: float, target: float, force_fill: bool = False) -> bool:
        proposal = {
            "symbol": symbol,
            "price": price,
            "stop_loss": stop_loss,
            "target": target,
            "strategy": "Swing Pullback",
            "confidence": 80
        }
        return self.buy(proposal, qty, force_fill=force_fill)

    def buy(self, proposal: dict, qty: int, force_fill: bool = False) -> bool:
        """Execute a delivery swing purchase."""
        if qty <= 0:
            return False
        symbol = proposal["symbol"]
        price = round_to_tick(float(proposal["price"]))

        val = validate_order_microstructure(
            symbol, "BUY", price,
            stop_loss=proposal.get("stop_loss"),
            target=proposal.get("target"),
            prev_close=proposal.get("prev_close")
        )
        if not val["ok"]:
            self.db.log("WARN", f"[SWING] ORDER REJECTED by exchange rules: {val['reason']}")
            return False

        sl = round_to_tick(proposal["stop_loss"]) if proposal.get("stop_loss") is not None else None
        tp = round_to_tick(proposal["target"]) if proposal.get("target") is not None else None

        notional = round(price * qty, 2)
        cost = self._cost(notional, "BUY")
        total_req = notional + cost

        from ..market_hours import market_open
        enforce_hours = (
            self.cfg.get("execution", {}).get("enforce_market_hours", False)
            or self.cfg.get("enforce_market_hours", False)
            or self.cfg.get("live_data", False)
        )


        if enforce_hours and not force_fill and not market_open():
            self.db.add_order({
                "symbol": symbol,
                "action": "BUY",
                "side": "LONG",
                "qty": qty,
                "price": price,
                "stop_loss": proposal.get("stop_loss"),
                "target": proposal.get("target"),
                "product_type": "SWING",
                "order_type": "AMO",
                "status": "PENDING",
                "strategy": proposal.get("strategy", "Swing Pullback")
            })
            self.db.log("INFO", f"[AMO PLACED] Market CLOSED. Placed After-Market Order (AMO) for {symbol} x{qty} @ ₹{price:.2f}. Will execute at 09:15 AM IST.")
            return True

        with self.db.conn() as c:
            row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            if not row:
                now_str = datetime.now(timezone.utc).isoformat()
                c.execute("INSERT OR IGNORE INTO account VALUES(1, 100000.0, 100000.0, 200000.0, 100000.0, ?)", (now_str,))
                row = c.execute("SELECT * FROM account WHERE id=1").fetchone()
            acc = dict(row)

            short_margin_pct = float(self.cfg.get("execution", {}).get("short_margin_pct", 0.25))
            open_pos = [dict(r) for r in c.execute("SELECT * FROM positions").fetchall()]
            reserved = sum(float(x['entry_price']) * float(x['qty']) * short_margin_pct for x in open_pos if x['side'] == 'SHORT')
            avail = max(0.0, float(acc['cash']) - reserved)
            if total_req > avail:
                return False

            target_step = abs(float(proposal["target"]) - price) if proposal.get("target") else 0.0

            c.execute(
                """INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target,
                                         strategy, confidence, opened_at, sector, atr, entry_cost, target_step,
                                         product_type, days_held)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET
                   qty=qty+excluded.qty, current_price=excluded.current_price""",
                (
                    symbol, "LONG", qty, price, price, proposal.get("stop_loss"), proposal.get("target"),
                    proposal.get("strategy", "Swing Pullback"), proposal.get("confidence", 80),
                    datetime.now(timezone.utc).isoformat(), proposal.get("sector", "Unknown"),
                    proposal.get("atr", 0.0), cost, target_step, "SWING", 0
                )
            )
            c.execute("UPDATE account SET cash=cash-?, updated_at=? WHERE id=1",
                      (total_req, datetime.now(timezone.utc).isoformat()))

        if sl is not None and tp is not None:
            self.bracket_manager.create_bracket(symbol, "LONG", qty, price, sl, tp)

        self.db.log("INFO", f"SWING BUY {symbol} x{qty} @ {price:.2f} (Target: ₹{proposal.get('target', 0):.2f})")
        return True

    def close(self, symbol: str, price: float, reason: str) -> bool:
        """Close a swing position."""
        with self.db.conn() as c:
            row = c.execute("SELECT * FROM positions WHERE symbol=? AND UPPER(product_type)='SWING'", (symbol,)).fetchone()
            if not row:
                return False
            p = dict(row)
            qty = p["qty"]
            entry_price = float(p["entry_price"])
            notional = round(price * qty, 2)
            exit_cost = self._cost(notional, "SELL")
            entry_cost = float(p.get("entry_cost") or 0.0)

            gross_pnl = round((price - entry_price) * qty, 2)
            net_pnl = round(gross_pnl - exit_cost - entry_cost, 2)
            pnl_pct = round((net_pnl / (entry_price * qty)) * 100, 2) if entry_price > 0 else 0.0

            holding_sec = 0.0
            if p.get("opened_at"):
                try:
                    opened = datetime.fromisoformat(str(p["opened_at"]).replace("Z", "+00:00"))
                    holding_sec = (datetime.now(timezone.utc) - opened).total_seconds()
                except Exception:
                    pass

            days_held = int(p.get("days_held") or 0)

            c.execute(
                """INSERT INTO trades(symbol, action, side, entry_price, exit_price, qty, capital, stop_loss, target,
                                     holding_seconds, pnl, pnl_pct, strategy, confidence, regime, entry_reason,
                                     exit_reason, risk_decision, created_at, product_type, days_held)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol, "SELL", "LONG", entry_price, price, qty, entry_price * qty,
                    p.get("stop_loss"), p.get("target"), holding_sec, net_pnl, pnl_pct,
                    p.get("strategy"), p.get("confidence"), "Swing", "Swing 20 EMA Pullback",
                    reason, "APPROVED", datetime.now(timezone.utc).isoformat(), "SWING", days_held
                )
            )
            c.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            c.execute("UPDATE account SET cash=cash+?, updated_at=? WHERE id=1",
                      (notional - exit_cost, datetime.now(timezone.utc).isoformat()))

        self.bracket_manager.cancel_bracket(symbol, reason=reason)

        self.db.log("INFO", f"SWING SELL {symbol} @ {price:.2f} P&L: ₹{net_pnl:.2f} ({pnl_pct:+.2f}%) Reason: {reason}")
        return True

