"""
Operations & Emergency Control API Blueprint
Provides auto-trading toggle, kill switch, emergency portfolio flattening, and log streaming.
"""
from flask import Blueprint, jsonify, request, current_app
from .auth import is_authorized

ops_bp = Blueprint("ops", __name__)


@ops_bp.route("/api/auto-trading", methods=["GET"])
def auto_trading_status():
    db = current_app.config["DB"]
    return jsonify({"auto_trading": db.is_auto_trading_enabled()})


@ops_bp.route("/api/auto-trading/toggle", methods=["POST"])
def toggle_auto_trading():
    if not is_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    db = current_app.config["DB"]
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        new_state = bool(data["enabled"])
    else:
        current = db.is_auto_trading_enabled()
        new_state = not current

    db.set_auto_trading(new_state)
    db.log("INFO", f"Auto-trading {'resumed' if new_state else 'paused'} by user from dashboard.")
    return jsonify({"auto_trading": new_state})


@ops_bp.route("/api/kill-switch", methods=["GET"])
def kill_switch_status():
    ks = current_app.config.get("KILL_SWITCH")
    if not ks:
        return jsonify({"tripped": False, "reason": "Not initialized"}), 200
    tripped, reason = ks.is_tripped()
    return jsonify({"tripped": tripped, "reason": reason})


@ops_bp.route("/api/kill-switch/flatten", methods=["POST"])
def emergency_flatten():
    if not is_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    ks = current_app.config.get("KILL_SWITCH")
    if not ks:
        return jsonify({"error": "Kill switch unavailable"}), 503

    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason", "Dashboard Emergency Flatten")
    closed = ks.flatten_portfolio(reason=reason)
    return jsonify({"status": "flattened", "closed_positions": closed})


@ops_bp.route("/api/kill-switch/reset", methods=["POST"])
def reset_kill_switch():
    if not is_authorized():
        return jsonify({"error": "Unauthorized"}), 401

    ks = current_app.config.get("KILL_SWITCH")
    if not ks:
        return jsonify({"error": "Kill switch unavailable"}), 503

    ks.reset()
    return jsonify({"status": "reset"})


@ops_bp.route("/api/logs", methods=["GET"])
def stream_logs():
    from ..logger import read_recent_logs
    try:
        n = int(request.args.get("lines", 100))
    except (ValueError, TypeError):
        n = 100
    logs = read_recent_logs(max_lines=min(500, max(10, n)))
    return jsonify({"logs": logs, "count": len(logs)})


@ops_bp.route("/api/capital-allocation", methods=["GET", "POST"])
@ops_bp.route("/api/allocation", methods=["GET", "POST"])
def handle_capital_allocation_alias():
    """Hyphenated route for backward compatibility."""
    db = current_app.config["DB"]
    if request.method == "POST":
        if not is_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        data = request.get_json(silent=True) or {}
        try:
            intraday = max(0.0, float(data.get("intraday", 40.0)))
            swing = max(0.0, float(data.get("swing", 40.0)))
            fno = max(0.0, float(data.get("fno", 20.0)))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid capital allocation numbers"}), 400
        updated = db.set_capital_allocation(intraday, swing, fno)
        db.log("INFO", f"Capital allocation updated: Intraday={updated['intraday']}%, Swing={updated['swing']}%, F&O={updated['fno']}%")
        return jsonify({"status": "ok", "capital_allocation": updated})
    return jsonify(db.get_capital_allocation())

