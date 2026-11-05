"""
Broker Adapter Factory.
Provides pluggable access to Paper simulator, Zerodha Kite Connect, or Angel One SmartAPI.
Strictly defaults to PaperBrokerAdapter for safety unless live trading is explicitly configured.
"""

import os
import logging
from typing import Dict, Any, Optional
from .base import AbstractBrokerAdapter
from .paper import PaperBrokerAdapter
from .zerodha import ZerodhaKiteAdapter
from .angel import AngelSmartApiAdapter
from .shoonya import ShoonyaBrokerAdapter

logger = logging.getLogger("tradng_ai.broker.factory")


def get_broker_adapter(cfg: Optional[Dict[str, Any]] = None, db=None) -> AbstractBrokerAdapter:
    """
    Instantiates and returns the configured broker adapter.
    Defaults to PaperBrokerAdapter for complete capital safety unless:
    - cfg["broker"]["type"] is explicitly set to "zerodha" or "angel"
    - live API credentials are valid and connection succeeds.
    """
    cfg = cfg or {}
    broker_cfg = cfg.get("broker", {})
    broker_type = os.getenv("BROKER_TYPE", broker_cfg.get("type", "paper")).lower().strip()

    # Safety check: enforce paper execution if paper mode is flagged
    is_paper_mode = cfg.get("runtime", {}).get("paper_only", True)
    if is_paper_mode and broker_type != "paper":
        logger.info(f"System configured in paper mode. Overriding requested broker '{broker_type}' with PaperBrokerAdapter.")
        return PaperBrokerAdapter(db=db, cfg=cfg)

    if broker_type in ("zerodha", "kite"):
        logger.info("Initializing Zerodha Kite Connect broker adapter...")
        adapter = ZerodhaKiteAdapter(
            api_key=broker_cfg.get("api_key") or os.getenv("ZERODHA_API_KEY"),
            access_token=broker_cfg.get("access_token") or os.getenv("ZERODHA_ACCESS_TOKEN")
        )
        if adapter.connect():
            return adapter
        logger.warning("Zerodha connection failed; safely falling back to PaperBrokerAdapter.")
        return PaperBrokerAdapter(db=db, cfg=cfg)

    elif broker_type in ("angel", "angel_one", "smartapi"):
        logger.info("Initializing Angel One SmartAPI broker adapter...")
        adapter = AngelSmartApiAdapter(
            api_key=broker_cfg.get("api_key") or os.getenv("ANGEL_API_KEY"),
            client_code=broker_cfg.get("client_code") or os.getenv("ANGEL_CLIENT_CODE"),
            password=broker_cfg.get("password") or os.getenv("ANGEL_PASSWORD"),
            totp_key=broker_cfg.get("totp_key") or os.getenv("ANGEL_TOTP_KEY")
        )
        if adapter.connect():
            return adapter
        logger.warning("Angel One connection failed; safely falling back to PaperBrokerAdapter.")
        return PaperBrokerAdapter(db=db, cfg=cfg)

    elif broker_type in ("shoonya", "finvasia", "zero_brokerage"):
        logger.info("Initializing Shoonya Zero-Brokerage broker adapter...")
        adapter = ShoonyaBrokerAdapter(
            user_id=broker_cfg.get("user_id") or os.getenv("SHOONYA_USER_ID"),
            password=broker_cfg.get("password") or os.getenv("SHOONYA_PASSWORD"),
            totp_key=broker_cfg.get("totp_key") or os.getenv("SHOONYA_TOTP_KEY"),
            vendor_code=broker_cfg.get("vendor_code") or os.getenv("SHOONYA_VENDOR_CODE"),
            api_secret=broker_cfg.get("api_secret") or os.getenv("SHOONYA_API_SECRET")
        )
        if adapter.connect():
            return adapter
        logger.warning("Shoonya connection failed; safely falling back to PaperBrokerAdapter.")
        return PaperBrokerAdapter(db=db, cfg=cfg)

    # Default to Paper Broker Simulator
    logger.info("Operating in 100% paper simulation mode with PaperBrokerAdapter.")
    return PaperBrokerAdapter(db=db, cfg=cfg)
