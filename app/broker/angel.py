"""
Angel One SmartAPI Broker Gateway.
Implements the AbstractBrokerAdapter interface for live order execution
via Angel One SmartAPI with TOTP 2FA.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from .base import AbstractBrokerAdapter
from ..exchange_rules import round_to_tick, validate_order_microstructure

logger = logging.getLogger("tradng_ai.broker.angel")


class AngelSmartApiAdapter(AbstractBrokerAdapter):
    """
    Angel One SmartAPI Gateway.
    Supports secure programmatic login with API key, Client Code, MPIN/Password, and TOTP.
    Maps internal orders to SmartAPI parameters:
    - INTRADAY -> INTRADAY
    - DELIVERY / SWING -> DELIVERY
    - FNO -> CARRYFORWARD
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        client_code: Optional[str] = None,
        password: Optional[str] = None,
        totp_key: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("ANGEL_API_KEY", "")
        self.client_code = client_code or os.getenv("ANGEL_CLIENT_CODE", "")
        self.password = password or os.getenv("ANGEL_PASSWORD", "")
        self.totp_key = totp_key or os.getenv("ANGEL_TOTP_KEY", "")
        self.smart_api = None
        self._connected = False

    @property
    def name(self) -> str:
        return "ANGEL_ONE"

    @property
    def is_live(self) -> bool:
        return True

    def connect(self) -> bool:
        """Authenticates with Angel One SmartAPI using TOTP."""
        if not self.api_key or not self.client_code or not self.password:
            logger.warning("Angel One credentials missing in environment. Set ANGEL_API_KEY, ANGEL_CLIENT_CODE, and ANGEL_PASSWORD.")
            return False

        try:
            from smartapi import SmartConnect
            self.smart_api = SmartConnect(api_key=self.api_key)

            totp = ""
            if self.totp_key:
                try:
                    import pyotp
                    totp = pyotp.TOTP(self.totp_key).now()
                except ImportError:
                    logger.warning("pyotp not installed. Install with `pip install pyotp` for automatic Angel One 2FA TOTP.")
                    return False

            data = self.smart_api.generateSession(self.client_code, self.password, totp)
            if data and data.get("status"):
                self._connected = True
                logger.info("Successfully authenticated with Angel One SmartAPI.")
                return True
            else:
                logger.error(f"Angel One session generation failed: {data}")
                return False
        except ImportError:
            logger.warning("smartapi-python package not installed. Run `pip install smartapi-python` to enable Angel One live trading.")
            return False
        except Exception as e:
            logger.error(f"Angel One connection error: {e}")
            return False

    def get_funds(self) -> Dict[str, float]:
        if not self._connected or not self.smart_api:
            return {"available_cash": 0.0, "collateral": 0.0, "utilized_margin": 0.0, "total_balance": 0.0}
        try:
            rms = self.smart_api.rmsLimit()
            data = rms.get("data", {}) if rms else {}
            net = float(data.get("net", 0.0) or 0.0)
            avail = float(data.get("availablecash", 0.0) or 0.0)
            coll = float(data.get("collateral", 0.0) or 0.0)
            util = float(data.get("utiliseddebits", 0.0) or 0.0)
            return {
                "available_cash": avail,
                "collateral": coll,
                "utilized_margin": util,
                "total_balance": net if net > 0 else avail
            }
        except Exception as e:
            logger.error(f"Angel One rmsLimit query failed: {e}")
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
        """Places live order on NSE/BSE through Angel One SmartAPI."""
        if not self._connected or not self.smart_api:
            return {
                "success": False,
                "order_id": None,
                "status": "REJECTED",
                "reason": "Angel One SmartAPI not connected or credentials missing"
            }

        rounded_px = round_to_tick(price)
        val = validate_order_microstructure(symbol, action, rounded_px)
        if not val["ok"]:
            return {
                "success": False,
                "order_id": None,
                "status": "REJECTED",
                "reason": val["reason"]
            }

        clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
        exchange = "NFO" if "CONDOR" in symbol or "CE" in symbol or "PE" in symbol else "NSE"

        # Product mapping for Angel One
        prod_map = {
            "INTRADAY": "INTRADAY",
            "DELIVERY": "DELIVERY",
            "SWING": "DELIVERY",
            "FNO": "CARRYFORWARD"
        }
        variety = "NORMAL"
        angel_product = prod_map.get(product_type.upper(), "INTRADAY")
        tx_type = "BUY" if action.upper() in ("BUY", "LONG") else "SELL"

        order_params = {
            "variety": variety,
            "tradingsymbol": f"{clean_symbol}-EQ" if exchange == "NSE" and "-" not in clean_symbol else clean_symbol,
            "symboltoken": "",
            "transactiontype": tx_type,
            "exchange": exchange,
            "ordertype": order_type.upper(),
            "producttype": angel_product,
            "duration": "DAY",
            "price": str(rounded_px) if order_type.upper() == "LIMIT" else "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(qty)
        }
        if trigger_price:
            order_params["triggerprice"] = str(round_to_tick(trigger_price))

        try:
            res = self.smart_api.placeOrder(order_params)
            order_id = res if isinstance(res, (str, int)) else (res.get("data", {}).get("orderid") if isinstance(res, dict) else None)
            return {
                "success": True if order_id else False,
                "order_id": str(order_id) if order_id else None,
                "status": "SUBMITTED" if order_id else "FAILED",
                "symbol": symbol,
                "action": tx_type,
                "qty": qty,
                "product_type": angel_product
            }
        except Exception as e:
            logger.error(f"Angel One placeOrder failed for {symbol}: {e}")
            return {
                "success": False,
                "order_id": None,
                "status": "FAILED",
                "reason": str(e)
            }

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected or not self.smart_api:
            return False
        try:
            self.smart_api.cancelOrder(orderid=order_id, variety="NORMAL")
            return True
        except Exception as e:
            logger.error(f"Angel One cancelOrder failed for {order_id}: {e}")
            return False

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self._connected or not self.smart_api:
            return []
        try:
            res = self.smart_api.position()
            return res.get("data", []) if res else []
        except Exception:
            return []

    def get_orders(self) -> List[Dict[str, Any]]:
        if not self._connected or not self.smart_api:
            return []
        try:
            res = self.smart_api.orderBook()
            return res.get("data", []) if res else []
        except Exception:
            return []
