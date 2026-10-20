from datetime import time
from ..costs import CostModel
from .timing import IntradayTimingManager


class IntradayExecutionEngine:
    """
    Intraday execution and position simulation engine.
    1. Gap-aware stop execution (fills at bar Open if price gaps through stop).
    2. Trading halt / circuit limit detection (zero volume halts execution).
    3. Compulsory EOD square-off before 15:15 IST (at or after 15:10 IST).
    4. Exact NSE intraday transaction cost deduction (STT only on sell, lower stamp).
    """
    def __init__(self, cost_model=None):
        self.costs = cost_model or CostModel()
        self.timing = IntradayTimingManager()
        self.positions = {}
        self.closed_trades = []

    def open_position(self, symbol, side, qty, entry_price, stop_loss, target, timestamp):
        """Enters an intraday position with next-bar entry fill."""
        val = qty * entry_price
        entry_cost = self.costs.calculate(val, action="BUY" if side == "LONG" else "SELL", segment="INTRADAY")
        pos = {
            "symbol": symbol,
            "side": side,
            "qty": int(qty),
            "entry_price": float(entry_price),
            "stop_loss": float(stop_loss),
            "target": float(target),
            "entry_time": timestamp,
            "entry_cost": entry_cost,
            "status": "OPEN"
        }
        self.positions[symbol] = pos
        return pos

    def process_bar(self, symbol, bar, timestamp):
        """
        Processes a single intraday bar against any open position.
        Returns trade exit event dict if closed, else None.
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        vol = float(bar.get("Volume", 1.0))
        o = float(bar["Open"])
        h = float(bar["High"])
        l = float(bar["Low"])
        c = float(bar["Close"])

        # 1. Trading Halt Detection
        if vol <= 0.0:
            return {"status": "HALTED", "symbol": symbol, "timestamp": timestamp}

        exit_price = None
        exit_reason = None

        # 2. Compulsory EOD Square-off at or after 15:10 IST
        if self.timing.must_square_off(timestamp):
            exit_price = c
            exit_reason = "EOD_SQUARE_OFF"

        # 3. Gap-aware Stop and Target execution
        elif pos["side"] == "LONG":
            if o <= pos["stop_loss"]:
                # Gapped down through stop: fill at Open
                exit_price = o
                exit_reason = "STOP_GAP_DOWN"
            elif l <= pos["stop_loss"]:
                # Normal stop hit
                exit_price = pos["stop_loss"]
                exit_reason = "STOP_HIT"
            elif h >= pos["target"]:
                exit_price = pos["target"]
                exit_reason = "TARGET_HIT"

        elif pos["side"] == "SHORT":
            if o >= pos["stop_loss"]:
                # Gapped up through stop: fill at Open
                exit_price = o
                exit_reason = "STOP_GAP_UP"
            elif h >= pos["stop_loss"]:
                # Normal stop hit
                exit_price = pos["stop_loss"]
                exit_reason = "STOP_HIT"
            elif l <= pos["target"]:
                exit_price = pos["target"]
                exit_reason = "TARGET_HIT"

        if exit_price is not None:
            return self._close_position(symbol, exit_price, exit_reason, timestamp)

        return None

    def _close_position(self, symbol, exit_price, reason, timestamp):
        pos = self.positions.pop(symbol)
        qty = pos["qty"]
        exit_val = qty * exit_price
        exit_action = "SELL" if pos["side"] == "LONG" else "BUY"
        exit_cost = self.costs.calculate(exit_val, action=exit_action, segment="INTRADAY")

        total_costs = pos["entry_cost"] + exit_cost
        gross_pnl = (exit_price - pos["entry_price"]) * qty if pos["side"] == "LONG" else (pos["entry_price"] - exit_price) * qty
        net_pnl = gross_pnl - total_costs

        trade = {
            "symbol": symbol,
            "side": pos["side"],
            "qty": qty,
            "entry_price": pos["entry_price"],
            "exit_price": float(exit_price),
            "entry_time": str(pos["entry_time"]),
            "exit_time": str(timestamp),
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "total_costs": round(total_costs, 2),
            "exit_reason": reason
        }
        self.closed_trades.append(trade)
        return trade


from datetime import datetime, timezone


class IntradayExecution:
    """
    Live / Paper Execution Engine dedicated to Intraday MIS trades.
    Uses exact NSE intraday cost deductions and tags all positions product_type='INTRADAY'.
    """
    def __init__(self, db, cfg=None):
        self.db = db
        self.cfg = cfg or {}
        self.costs = CostModel()

    def open_long(self, symbol, qty, price, stop_loss, target, atr=0.0):
        if qty <= 0:
            return False
        val = qty * price
        cost = self.costs.calculate(val, action="BUY", segment="INTRADAY")
        total_req = val + cost
        target_step = abs(target - price) if target else 0.0

        with self.db.conn() as c:
            acc = dict(c.execute("SELECT * FROM account WHERE id=1").fetchone())
            if total_req > acc["cash"]:
                return False
            c.execute(
                """INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target,
                                         strategy, confidence, opened_at, sector, atr, entry_cost, target_step,
                                         product_type, days_held)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET
                   qty=qty+excluded.qty, current_price=excluded.current_price""",
                (
                    symbol, "LONG", int(qty), float(price), float(price), float(stop_loss), float(target),
                    "Intraday ORB", 80, datetime.now(timezone.utc).isoformat(), "Unknown",
                    float(atr), cost, target_step, "INTRADAY", 0
                )
            )
            c.execute("UPDATE account SET cash=cash-?, updated_at=? WHERE id=1",
                      (total_req, datetime.now(timezone.utc).isoformat()))
        self.db.log("INFO", f"[Intraday] BUY {symbol} x{qty} @ {price:.2f} (SL: {stop_loss:.2f}, TP: {target:.2f})")
        return True

    def open_short(self, symbol, qty, price, stop_loss, target, atr=0.0):
        if qty <= 0:
            return False
        val = qty * price
        cost = self.costs.calculate(val, action="SELL", segment="INTRADAY")
        short_margin_pct = float(self.cfg.get("execution", {}).get("short_margin_pct", 0.25))
        margin_req = val * short_margin_pct + cost
        target_step = abs(price - target) if target else 0.0

        with self.db.conn() as c:
            acc = dict(c.execute("SELECT * FROM account WHERE id=1").fetchone())
            if margin_req > acc["cash"]:
                return False
            c.execute(
                """INSERT INTO positions(symbol, side, qty, entry_price, current_price, stop_loss, target,
                                         strategy, confidence, opened_at, sector, atr, entry_cost, target_step,
                                         product_type, days_held)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET
                   qty=qty+excluded.qty, current_price=excluded.current_price""",
                (
                    symbol, "SHORT", int(qty), float(price), float(price), float(stop_loss), float(target),
                    "Intraday ORB Short", 80, datetime.now(timezone.utc).isoformat(), "Unknown",
                    float(atr), cost, target_step, "INTRADAY", 0
                )
            )
            c.execute("UPDATE account SET cash=cash-?, updated_at=? WHERE id=1",
                      (margin_req, datetime.now(timezone.utc).isoformat()))
        self.db.log("INFO", f"[Intraday] SHORT {symbol} x{qty} @ {price:.2f} (SL: {stop_loss:.2f}, TP: {target:.2f})")
        return True

    def close(self, symbol, exit_price, reason, category=""):
        from ..execution import PaperExecution
        exec_engine = PaperExecution(self.db, self.cfg)
        return exec_engine.close(symbol, exit_price, reason, category)

    def mark(self, quotes):
        from ..execution import PaperExecution
        exec_engine = PaperExecution(self.db, self.cfg)
        return exec_engine.mark(quotes)
