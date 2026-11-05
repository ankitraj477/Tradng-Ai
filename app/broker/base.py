"""
Abstract Base Broker Adapter.
Defines the standard interface for order placement, cancellations,
position management, and account balance queries across paper and live brokers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class AbstractBrokerAdapter(ABC):
    """
    Unified broker interface.
    Allows the trading engine to interact seamlessly with paper simulation
    or live exchange APIs (Zerodha, Angel One, Upstox, Dhan) using the same contract.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the broker name identifier."""
        pass

    @property
    @abstractmethod
    def is_live(self) -> bool:
        """Returns True if trading with real exchange capital, False if paper simulation."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Authenticates with the broker or initializes local paper ledger."""
        pass

    @abstractmethod
    def get_funds(self) -> Dict[str, float]:
        """Returns available cash, margin, and collateral."""
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        action: str,  # 'BUY' or 'SELL'
        qty: int,
        price: float,
        product_type: str = "INTRADAY",  # 'INTRADAY', 'DELIVERY', 'FNO'
        order_type: str = "MARKET",      # 'MARKET', 'LIMIT', 'SL', 'SL-M'
        trigger_price: Optional[float] = None,
        tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Places an order with the broker."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancels an open pending order."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns currently open positions from the broker."""
        pass

    @abstractmethod
    def get_orders(self) -> List[Dict[str, Any]]:
        """Returns active and completed orders for the day."""
        pass
