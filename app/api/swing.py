"""
Swing CNC Desk API Blueprint
Provides dedicated metrics, multi-day delivery positions, ATR trailing stops, and candidate radar.
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, current_app
from ..market_hours import now_ist, IST, market_phase, market_open
from .overview import _enrich_trade

swing_bp = Blueprint("swing", __name__, url_prefix="/api/desks/swing")


def _holding_days(opened_at):
    if not opened_at:
        return 0
    try:
        opened = datetime.fromisoformat(str(opened_at))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - opened).days)
    except Exception:
        return 0


@swing_bp.route("/state", methods=["GET"])
def swing_state():
    db = current_app.config["DB"]
    account = db.account()
    if not account:
        return jsonify({"error": "Trading account is not initialized."}), 503

    all_positions = db.positions()
    swing_positions = [
        p for p in all_positions
        if str(p.get("product_type", "")).upper() == "SWING"
    ]

    for p in swing_positions:
        p["holding_days"] = _holding_days(p.get("opened_at"))
        qty = float(p.get("qty", 1) or 1)
        entry = float(p.get("entry_price", 0) or 0)
        curr = float(p.get("current_price", entry) or entry)
        side = str(p.get("side", "LONG")).upper()
        pos_pnl = (curr - entry) * qty if side == "LONG" else (entry - curr) * qty
        p["pnl"] = round(pos_pnl, 2)
        p["pnl_pct"] = round(((pos_pnl / (entry * qty)) * 100) if (entry * qty) > 0 else 0.0, 2)
        p["market_value"] = round(curr * qty, 2)
        sl = float(p.get("stop_loss", 0) or 0)
        if curr > 0 and sl > 0:
            p["stop_distance_pct"] = round(abs((curr - sl) / curr) * 100, 2)
        else:
            p["stop_distance_pct"] = 0.0

    raw_trades = db.trades_by_product("SWING", 30) if hasattr(db, "trades_by_product") else [
        t for t in db.trades(50) if str(t.get("product_type", "")).upper() == "SWING"
    ]
    enriched_trades = [_enrich_trade(t) for t in raw_trades]

    alloc = db.get_capital_allocation()
    total_capital = float(account.get("cash", 100000.0)) + sum(float(p.get("market_value", 0)) for p in all_positions)
    swing_allocated_cap = round(total_capital * (alloc.get("swing", 40.0) / 100.0), 2)
    invested_value = sum(float(p.get("market_value", 0)) for p in swing_positions)
    unrealized_pnl = sum(float(p.get("pnl", 0)) for p in swing_positions)
    realized_pnl = sum(float(t.get("pnl", 0)) for t in enriched_trades if "pnl" in t)

    avg_holding = 0
    if swing_positions:
        avg_holding = round(sum(p.get("holding_days", 0) for p in swing_positions) / len(swing_positions), 1)

    # Scanner radar candidates (curated NIFTY 500 setups)
    candidates = [
        {"symbol": "BEL.NS", "setup": "Stage 2 Cup & Handle Breakout", "pivot": 315.50, "atr": 7.20, "score": 92, "status": "PIVOT_ALERT"},
        {"symbol": "HAL.NS", "setup": "Pullback to 21 EMA Support", "pivot": 4450.00, "atr": 85.00, "score": 88, "status": "ACCUMULATION"},
        {"symbol": "TRENT.NS", "setup": "Multi-Week Base High Consolidation", "pivot": 7250.00, "atr": 140.00, "score": 94, "status": "BREAKOUT_PENDING"},
        {"symbol": "DIXON.NS", "setup": "Volume Contraction Pattern (VCP)", "pivot": 14900.00, "atr": 280.00, "score": 85, "status": "WATCHLIST"}
    ]

    return jsonify({
        "desk": "SWING_CNC",
        "market_phase": market_phase(),
        "market_open": market_open(),
        "metrics": {
            "allocated_capital": swing_allocated_cap,
            "invested_value": round(invested_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "open_holdings_count": len(swing_positions),
            "avg_holding_days": avg_holding,
            "closed_trades_count": len(enriched_trades)
        },
        "positions": swing_positions,
        "trades": enriched_trades,
        "candidates": candidates
    })


@swing_bp.route("/positions", methods=["GET"])
def get_swing_positions():
    db = current_app.config["DB"]
    all_positions = db.positions()
    swing_positions = [
        p for p in all_positions
        if str(p.get("product_type", "")).upper() == "SWING"
    ]
    return jsonify({"positions": swing_positions})


@swing_bp.route("/candidates", methods=["GET"])
def get_swing_candidates():
    candidates = [
        {"symbol": "BEL.NS", "setup": "Stage 2 Cup & Handle Breakout", "pivot": 315.50, "atr": 7.20, "score": 92, "status": "PIVOT_ALERT"},
        {"symbol": "HAL.NS", "setup": "Pullback to 21 EMA Support", "pivot": 4450.00, "atr": 85.00, "score": 88, "status": "ACCUMULATION"},
        {"symbol": "TRENT.NS", "setup": "Multi-Week Base High Consolidation", "pivot": 7250.00, "atr": 140.00, "score": 94, "status": "BREAKOUT_PENDING"},
        {"symbol": "DIXON.NS", "setup": "Volume Contraction Pattern (VCP)", "pivot": 14900.00, "atr": 280.00, "score": 85, "status": "WATCHLIST"}
    ]
    return jsonify({"candidates": candidates})

