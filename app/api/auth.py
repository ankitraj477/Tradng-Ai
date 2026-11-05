"""
Authentication and authorization helpers for Tradng-Ai REST API endpoints.
"""
import hmac
import os
from flask import current_app, request


def is_authorized() -> bool:
    """
    Validates dashboard and control-plane requests using constant-time comparison.
    Respects dashboard.fail_closed configuration.
    """
    cfg = current_app.config.get("CFG", {})
    token_cfg = (
        cfg.get("dashboard", {}).get("token")
        or os.environ.get("TRADING_AI_DASHBOARD_TOKEN", "")
    ).strip()

    fail_closed = cfg.get("dashboard", {}).get("fail_closed", False)
    if not token_cfg:
        return not fail_closed

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    else:
        token = request.headers.get("X-API-Token") or request.args.get("token", "")

    if not token:
        token = request.cookies.get("tradng_token", "")

    if not token:
        return False

    return hmac.compare_digest(token, token_cfg)

