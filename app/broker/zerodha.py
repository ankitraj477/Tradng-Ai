"""
Zerodha Kite Connect Broker Gateway.
Implements the AbstractBrokerAdapter interface for live order execution
via Zerodha's Kite Connect API v3.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from .base import AbstractBrokerAdapter
from ..exchange_rules import round_to_tick

logger = logging.getLogger("tradng_ai.broker.zerodha")


class ZerodhaKiteAdapter(AbstractBrokerAdapter):
    """
    Zerodha Kite Connect API Gateway.
    Maps internal orders to Kite order parameters:
    - MIS -> Intraday
    - CNC -> Delivery (Swing)
    - NRML -> F&O Options
    """

    def __init__(self, api_key: Optional[str] = None, access_token: Optional[str] = None):
        self.api_key = api_key or os.getenv("ZERODHA_API_KEY", "")
        self.access_token = access_token or os.getenv("ZERODHA_ACCESS_TOKEN", "")
        self.kite = None
        self._connected = False

    @property
    def name(self) -> str:
        return "ZERODHA_KITE"

    @property
    def is_live(self) -> bool:
        return True

    def connect(self) -> bool:
        """Initializes Kite Connect client with API key and access token."""
        if not self.api_key or not self.access_token:
            logger.warning("Zerodha Kite API Key or Access Token missing in environment. Set ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN.")
            return False

        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            self._connected = True
            logger.info("Successfully connected to Zerodha Kite Connect API.")
            return True
        except ImportError:
            logger.warning("kiteconnect package not installed. Run `pip install kiteconnect` to enable Zerodha live trading.")
            return False
        except Exception as e:
            logger.error(f"Failed to authenticate with Zerodha Kite: {e}")
            return False

    def get_funds(self) -> Dict[str, float]:
        if not self._connected or not self.kite:
            return {"available_cash": 0.0, "collateral": 0.0, "utilized_margin": 0.0, "total_balance": 0.0}
        try:
            margins = self.kite.margins()
            equity_margin = margins.get("equity", {})
            return {
                "available_cash": float(equity_margin.get("available", {}).get("live_balance", 0.0)),
                "collateral": float(equity_margin.get("available", {}).get("collateral", 0.0)),
                "utilized_margin": float(equity_margin.get("utilised", {}).get("debits", 0.0)),
                "total_balance": float(equity_margin.get("net", 0.0))
            }
        except Exception as e:
            logger.error(f"Zerodha margins query failed: {e}")
            return {"available_cash": 0.0, "collateral": 0.0, "utilized_margin": 0.0, "total_balance": 0.0}

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
        """Places live order on NSE/BSE through Zerodha Kite."""
        if not self._connected or not self.kite:
            return {
                "success": False,
                "order_id": None,
                "status": "REJECTED",
                "reason": "Zerodha Kite not connected or credentials missing"
            }

        clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
        exchange = "NFO" if "CONDOR" in symbol or "CE" in symbol or "PE" in symbol else "NSE"

        # Map internal product types to Kite product types
        product_map = {
            "INTRADAY": "MIS",
            "DELIVERY": "CNC",
            "SWING": "CNC",
            "FNO": "NRML"
        }
        kite_product = product_map.get(product_type.upper(), "MIS")
        kite_tx_type = "BUY" if action.upper() in ("BUY", "LONG") else "SELL"

        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=clean_symbol,
                transaction_type=kite_tx_type,
                quantity=qty,
                product=kite_product,
                order_type=order_type.upper(),
                price=round_to_tick(price) if order_type.upper() == "LIMIT" else None,
                trigger_price=round_to_tick(trigger_price) if trigger_price else None,
                tag=tag or "TradngAI"
            )
            return {
                "success": True,
                "order_id": str(order_id),
                "status": "SUBMITTED",
                "symbol": symbol,
                "action": action.upper(),
                "qty": qty,
                "product_type": kite_product
            }
        except Exception as e:
            logger.error(f"Zerodha place_order failed for {symbol}: {e}")
            return {
                "success": False,
                "order_id": None,
                "status": "FAILED",
                "reason": str(e)
            }

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected or not self.kite:
            return False
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception as e:
            logger.error(f"Zerodha cancel_order failed for {order_id}: {e}")
            return False

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self._connected or not self.kite:
            return []
        try:
            pos = self.kite.positions()
            return pos.get("net", [])
        except Exception:
            return []

    def get_orders(self) -> List[Dict[str, Any]]:
        if not self._connected or not self.kite:
            return []
        try:
            return self.kite.orders()
        except Exception:
            return []
