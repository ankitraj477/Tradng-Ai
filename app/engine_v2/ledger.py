"""
Multi-sleeve transactional ledger.
Enforces Section 4 & Section 10 (Test 8) invariants:
- Positions keyed by (sleeve, symbol).
- Weighted average entry price and cumulative entry cost tracking.
- Cash delta updates in atomic transactions.
- Invariant: cash + marked positions == start + realized - open entry costs.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Tuple, Optional, Union
import copy


@dataclass
class Position:
    sleeve: str
    symbol: str
    qty: int
    entry_price: float
    entry_cost: float = 0.0
    opened_at: str = ""
    side: str = "LONG"
    highest_close: float = 0.0

    @property
    def key(self) -> Tuple[str, str]:
        return (self.sleeve, self.symbol)


@dataclass
class Fill:
    sleeve: str
    symbol: str
    side: str  # "BUY", "SELL"
    qty: int
    price: float
    costs: float = 0.0
    slippage_bps: float = 0.0
    asof: Optional[Union[date, str]] = None


class Ledger:
    """Institutional portfolio ledger maintaining strict accounting invariants."""

    def __init__(self, starting_capital: float = 100000.0):
        self.starting_capital: float = float(starting_capital)
        self.cash: float = float(starting_capital)
        self.realized_pnl: float = 0.0
        self.total_costs_paid: float = 0.0
        self.positions: Dict[Tuple[str, str], Position] = {}
        self.trade_history: list = []

    def get_position(self, sleeve: str, symbol: str) -> Optional[Position]:
        return self.positions.get((sleeve, symbol))

    @property
    def open_entry_costs(self) -> float:
        """Sum of all entry transaction costs for currently open positions."""
        return sum(pos.entry_cost for pos in self.positions.values())

    @property
    def marked_entry_value(self) -> float:
        """Sum of (qty * entry_price) for all open positions."""
        return sum(pos.qty * pos.entry_price for pos in self.positions.values())

    def marked_market_value(self, current_prices: Dict[str, float]) -> float:
        """Sum of (qty * current_price) for all open positions."""
        total = 0.0
        for pos in self.positions.values():
            price = current_prices.get(pos.symbol, pos.entry_price)
            total += pos.qty * price
        return total

    def execute_fill(self, fill: Fill) -> Dict[str, float]:
        """
        Execute an atomic fill and update ledger state.
        Cash updates are deltas:
        - BUY: cash decreases by (qty * price + costs).
        - SELL: cash increases by (qty * price - costs).
        """
        if fill.qty <= 0:
            raise ValueError(f"Fill quantity must be positive, got {fill.qty}")
        if fill.price <= 0:
            raise ValueError(f"Fill price must be positive, got {fill.price}")

        key = (fill.sleeve, fill.symbol)
        side = fill.side.upper()
        gross_value = fill.qty * fill.price
        costs = float(fill.costs)
        self.total_costs_paid += costs

        trade_record = {
            "sleeve": fill.sleeve,
            "symbol": fill.symbol,
            "side": side,
            "qty": fill.qty,
            "price": fill.price,
            "costs": costs,
            "asof": str(fill.asof) if fill.asof else "",
            "realized_pnl": 0.0
        }

        if side in ("BUY", "LONG"):
            total_debit = gross_value + costs
            if total_debit > self.cash + 1e-4:
                raise ValueError(
                    f"Insufficient cash for fill: required ₹{total_debit:.2f}, available ₹{self.cash:.2f}"
                )
            self.cash -= total_debit

            existing = self.positions.get(key)
            if existing is None:
                self.positions[key] = Position(
                    sleeve=fill.sleeve,
                    symbol=fill.symbol,
                    qty=fill.qty,
                    entry_price=fill.price,
                    entry_cost=costs,
                    opened_at=str(fill.asof) if fill.asof else "",
                    highest_close=fill.price
                )
            else:
                # Weighted average entry price & cumulative cost
                new_qty = existing.qty + fill.qty
                weighted_price = ((existing.qty * existing.entry_price) + gross_value) / new_qty
                existing.entry_price = weighted_price
                existing.qty = new_qty
                existing.entry_cost += costs

        elif side in ("SELL", "SHORT"):
            existing = self.positions.get(key)
            if existing is None or existing.qty < fill.qty:
                available = existing.qty if existing else 0
                raise ValueError(
                    f"Cannot sell {fill.qty} of {fill.symbol} in sleeve {fill.sleeve}; holding {available}"
                )

            # Proportional open entry cost being retired
            frac_closed = fill.qty / existing.qty
            retired_entry_cost = existing.entry_cost * frac_closed

            # Net proceeds to cash
            net_proceeds = gross_value - costs
            self.cash += net_proceeds

            # Realized PnL = gross profit - exit costs - entry costs
            gross_pnl = (fill.price - existing.entry_price) * fill.qty
            trade_realized_pnl = gross_pnl - costs - retired_entry_cost
            self.realized_pnl += trade_realized_pnl
            trade_record["realized_pnl"] = trade_realized_pnl

            # Update or remove position
            if existing.qty == fill.qty:
                del self.positions[key]
            else:
                existing.qty -= fill.qty
                existing.entry_cost -= retired_entry_cost

        self.trade_history.append(trade_record)
        return trade_record

    def assert_invariants(self, current_prices: Optional[Dict[str, float]] = None):
        """
        Asserts Section 4 invariant:
        cash + marked positions == start + realized - open entry costs.
        """
        # Formulation 1: Marked at entry (cost basis)
        left_side = self.cash + self.marked_entry_value
        right_side = self.starting_capital + self.realized_pnl - self.open_entry_costs

        if not abs(left_side - right_side) < 1e-4:
            raise AssertionError(
                f"Ledger invariant breached! "
                f"Left side (cash {self.cash:.4f} + marked_entry {self.marked_entry_value:.4f}) = {left_side:.4f} != "
                f"Right side (start {self.starting_capital:.4f} + realized {self.realized_pnl:.4f} - entry_costs {self.open_entry_costs:.4f}) = {right_side:.4f}"
            )

        # Formulation 2: Marked at market prices
        if current_prices is not None:
            market_val = self.marked_market_value(current_prices)
            unrealized = sum(pos.qty * (current_prices.get(pos.symbol, pos.entry_price) - pos.entry_price)
                             for pos in self.positions.values())
            total_equity = self.cash + market_val
            expected_equity = self.starting_capital + self.realized_pnl + unrealized - self.open_entry_costs

            if not abs(total_equity - expected_equity) < 1e-4:
                raise AssertionError(
                    f"Market equity invariant breached! "
                    f"Total equity {total_equity:.4f} != Expected equity {expected_equity:.4f}"
                )
        return True
