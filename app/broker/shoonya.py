"""
Shoonya (Finvasia NorenApi) Zero-Brokerage Adapter.
Enables lifetime ₹0 brokerage execution for micro-capital accounts (e.g. ₹1,000 bootstrapping).
Eliminates the ₹20/order retail brokerage fee drag.
"""

import logging
from typing import Dict, Any, List, Optional
from .base import AbstractBrokerAdapter

logger = logging.getLogger("tradng_ai.broker.shoonya")


class ShoonyaBrokerAdapter(AbstractBrokerAdapter):
    """
    Shoonya by Finvasia Broker Adapter.
    - Flat ₹0.00 Brokerage on Equity Intraday, Delivery, and F&O.
    - Essential for compounding micro-capital accounts without fee ruin.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        password: Optional[str] = None,
        totp_key: Optional[str] = None,
        vendor_code: Optional[str] = None,
        api_secret: Optional[str] = None,
        imei: str = "TRADNG_AI_PRO"
    ):
        self.user_id = user_id
        self.password = password
        self.totp_key = totp_key
        self.vendor_code = vendor_code
        self.api_secret = api_secret
        self.imei = imei
        self.api = None
        self._connected = False

    @property
    def name(self) -> str:
        return "Shoonya (Finvasia Zero-Brokerage)"

    @property
    def is_live(self) -> bool:
        return True

    def connect(self) -> bool:
        """Connects and authenticates with Shoonya NorenApi."""
        if not self.user_id or not self.password or not self.totp_key:
            logger.warning("Shoonya credentials missing; live adapter inactive.")
            return False

        try:
            # Dynamic import of NorenApi
            import pyotp
            from NorenRestApiPy.NorenApi import NorenApi

            self.api = NorenApi(
                host="https://api.shoonya.com/NorenWSText/",
                websocket="wss://api.shoonya.com/NorenWSTextWS/"
            )
            totp = pyotp.TOTP(self.totp_key).now()
            ret = self.api.login(
                userid=self.user_id,
                password=self.password,
                twoFA=totp,
                vendor_code=self.vendor_code or self.user_id,
                api_secret=self.api_secret or self.user_id,
                imei=self.imei
            )

            if ret and ret.get("stat") == "Ok":
                self._connected = True
                logger.info(f"Shoonya Zero-Brokerage session established successfully for {self.user_id}.")
                return True
            else:
                logger.error(f"Shoonya login failed: {ret}")
                return False
        except ImportError:
            logger.info("Shoonya SDK (NorenRestApiPy/pyotp) not installed. Use PaperBrokerAdapter for simulation.")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Shoonya API: {e}")
            return False

    def get_funds(self) -> Dict[str, float]:
        """Queries available limits from Shoonya."""
        if not self._connected or not self.api:
            return {"cash": 1000.0, "available_cash": 1000.0, "collateral": 0.0}
        try:
            limits = self.api.get_limits()
            if limits and limits.get("stat") == "Ok":
                cash = float(limits.get("cash", 0.0))
                margin = float(limits.get("marginused", 0.0))
                avail = float(limits.get("cash", 0.0)) - margin
                return {"cash": cash, "available_cash": max(0.0, avail), "collateral": margin}
        except Exception as e:
            logger.error(f"Shoonya get_funds failed: {e}")
        return {"cash": 1000.0, "available_cash": 1000.0, "collateral": 0.0}

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
        """Places a zero-brokerage order via Shoonya."""
        if not self._connected or not self.api:
            return {"status": "FAILED", "reason": "Shoonya not connected"}

        try:
            buy_or_sell = "B" if action.upper() in ("BUY", "LONG") else "S"
            clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
            is_fno = (
                product_type.upper() == "FNO"
                or any(k in symbol for k in ("-CONDOR-", "-BPS-", "-BCS-", "-BCALL-", "-BPUT-"))
                or symbol.endswith("CE")
                or symbol.endswith("PE")
            )
            exch = "NFO" if is_fno else "NSE"
            tsym = clean_symbol if is_fno else (clean_symbol if clean_symbol.endswith("-EQ") else f"{clean_symbol}-EQ")

            if product_type.upper() == "INTRADAY":
                prd = "I"
            elif product_type.upper() in ("DELIVERY", "SWING", "CNC"):
                prd = "C"
            else:
                prd = "M"

            prctyp = "MKT" if order_type.upper() == "MARKET" else "LMT"

            ret = self.api.place_order(
                buy_or_sell=buy_or_sell,
                product_type=prd,
                prd=prd,
                exchange=exch,
                exch=exch,
                tradingsymbol=tsym,
                tsym=tsym,
                quantity=qty,
                discloseqty=0,
                price_type=prctyp,
                price=price if prctyp == "LMT" else 0.0,
                trigger_price=trigger_price,
                retention="DAY",
                remarks=tag or "Tradng-Ai-ZeroFee"
            )

            if ret and ret.get("stat") == "Ok":
                oid = ret.get("norenordno")
                return {
                    "success": True,
                    "order_id": oid,
                    "broker_order_id": oid,
                    "status": "SUBMITTED",
                    "broker": "SHOONYA_ZERO_FEE",
                    "price": price,
                    "qty": qty
                }
            return {"success": False, "order_id": None, "status": "REJECTED", "reason": str(ret.get("emsg", "Order error"))}
        except Exception as e:
            logger.error(f"Shoonya place_order failed: {e}")
            return {"success": False, "order_id": None, "status": "ERROR", "error": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected or not self.api:
            return False
        try:
            ret = self.api.cancel_order(orderno=order_id)
            return ret and ret.get("stat") == "Ok"
        except Exception:
            return False

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self._connected or not self.api:
            return []
        try:
            positions = self.api.get_positions()
            if isinstance(positions, list):
                return positions
        except Exception:
            pass
        return []

    def get_orders(self) -> List[Dict[str, Any]]:
        if not self._connected or not self.api:
            return []
        try:
            book = self.api.get_order_book()
            if isinstance(book, list):
                return book
        except Exception:
            pass
        return []
