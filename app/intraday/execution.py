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
