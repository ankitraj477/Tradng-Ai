"""
Intraday MIS Desk API Blueprint
Provides dedicated metrics, positions, auto-squareoff countdown, and strategy radar for Day Trading.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, current_app
from ..market_hours import now_ist, IST, market_phase, market_open
from .overview import _enrich_trade, _holding_minutes

intraday_bp = Blueprint("intraday", __name__, url_prefix="/api/desks/intraday")


def _seconds_until_squareoff():
    ist_now = now_ist()
    target_dt = ist_now.replace(hour=15, minute=15, second=0, microsecond=0)
    secs = int((target_dt - ist_now).total_seconds())
    return max(0, secs) if market_open() and secs > 0 else 0


@intraday_bp.route("/state", methods=["GET"])
def intraday_state():
    db = current_app.config["DB"]
    cfg = current_app.config.get("CFG", {})
    account = db.account()
    if not account:
        return jsonify({"error": "Trading account is not initialized."}), 503

    all_positions = db.positions()
    intra_positions = [
        p for p in all_positions
        if str(p.get("product_type", "INTRADAY")).upper() == "INTRADAY"
    ]

    for p in intra_positions:
        p["holding_minutes"] = _holding_minutes(p.get("opened_at"))
        qty = float(p.get("qty", 1) or 1)
        entry = float(p.get("entry_price", 0) or 0)
        curr = float(p.get("current_price", entry) or entry)
        side = str(p.get("side", "LONG")).upper()
        if side in ("SHORT", "SELL"):
            pos_pnl = (entry - curr) * qty
        else:
            pos_pnl = (curr - entry) * qty
        p["pnl"] = round(pos_pnl, 2)
        p["pnl_pct"] = round(((pos_pnl / (entry * qty)) * 100) if (entry * qty) > 0 else 0.0, 2)
        p["market_value"] = round(curr * qty, 2)

    raw_trades = db.trades_by_product("INTRADAY", 50) if hasattr(db, "trades_by_product") else [
        t for t in db.trades(50) if str(t.get("product_type", "INTRADAY")).upper() == "INTRADAY"
    ]
    enriched_trades = [_enrich_trade(t) for t in raw_trades]

    # Calculate Intraday Specific Metrics
    alloc = db.get_capital_allocation()
    total_capital = float(account.get("cash", 100000.0)) + sum(float(p.get("market_value", 0)) for p in all_positions)
    intra_allocated_cap = round(total_capital * (alloc.get("intraday", 40.0) / 100.0), 2)
    intra_unrealized = sum(p.get("pnl", 0.0) for p in intra_positions)
    intra_realized = sum(t.get("pnl", 0.0) for t in enriched_trades if "pnl" in t)
    intra_margin = sum(float(p.get("market_value", 0)) * 0.20 for p in intra_positions)  # 5x leverage approx

    wins = [t for t in enriched_trades if t.get("pnl", 0) > 0]
    win_rate = round((len(wins) / len(enriched_trades) * 100) if enriched_trades else 0.0, 1)

    return jsonify({
        "desk": "INTRADAY_MIS",
        "market_phase": market_phase(),
        "market_open": market_open(),
        "squareoff_time": "15:15 IST",
        "seconds_to_squareoff": _seconds_until_squareoff(),
        "metrics": {
            "allocated_capital": intra_allocated_cap,
            "margin_used": round(intra_margin, 2),
            "unrealized_pnl": round(intra_unrealized, 2),
            "realized_pnl": round(intra_realized, 2),
            "daily_pnl": round(intra_unrealized + intra_realized, 2),
            "open_positions_count": len(intra_positions),
            "closed_trades_count": len(enriched_trades),
            "win_rate_pct": win_rate
        },
        "positions": intra_positions,
        "trades": enriched_trades,
        "strategy_radar": [
            {"name": "Opening Range Breakout (ORB)", "status": "ACTIVE", "active_window": "09:15 - 10:15 IST", "signal": "MONITORING"},
            {"name": "VWAP Trend Continuation", "status": "ACTIVE", "active_window": "10:00 - 14:30 IST", "signal": "SCANNING"},
            {"name": "Mean Reversion Exhaustion", "status": "ACTIVE", "active_window": "13:00 - 15:00 IST", "signal": "READY"}
        ]
    })


@intraday_bp.route("/positions", methods=["GET"])
def get_intraday_positions():
    db = current_app.config["DB"]
    all_positions = db.positions()
    intra_positions = [
        p for p in all_positions
        if str(p.get("product_type", "INTRADAY")).upper() == "INTRADAY"
    ]
    return jsonify({"positions": intra_positions})


@intraday_bp.route("/trades", methods=["GET"])
def get_intraday_trades():
    db = current_app.config["DB"]
    raw_trades = db.trades_by_product("INTRADAY", 50) if hasattr(db, "trades_by_product") else []
    return jsonify({"trades": [_enrich_trade(t) for t in raw_trades]})

